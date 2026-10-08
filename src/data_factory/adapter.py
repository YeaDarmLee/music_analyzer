"""DF-7: Data Factory -> engine dataset contract. The ONLY module (besides assets.py) that imports `engine`.

Registered as dataset kind `datafactory_scenes`. Item = {"mix": (2,T) float32 tensor, "stems": {target_name: (2,T)}}.
mode "lazy"  : spec generated from (master_seed, split, index); the whole scene is rendered on demand, then cropped (training).
mode "fixed" : pre-rendered scene directories (validation/test), cropped deterministically.
Optional disk cache of rendered windows (LRU by mtime, size-capped)."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset

from engine.registry import DATASETS

from . import GENERATOR_VERSION, assets as A
from .scenes import Factory
from .schema import SceneSpec
from .targets import ATOMIC_ALL, SCHEMAS, build_targets
from .util import hash_obj, read_wav, sub_rng


def crop_start_samples(spec_seed: int, total: int, chunk: int) -> int:
    if total <= chunk:
        return 0
    return int(sub_rng(spec_seed, "crop").randint(0, total - chunk + 1))


class DiskCache:
    def __init__(self, root: str | Path, max_bytes: int):
        self.root, self.max = Path(root), max_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def get(self, key: str):
        p = self.root / f"{key}.npy"
        if p.exists():
            p.touch()
            return np.load(p)
        return None

    def put(self, key: str, arr: np.ndarray) -> None:
        np.save(self.root / f"{key}.npy", arr)
        files = sorted(self.root.glob("*.npy"), key=lambda f: f.stat().st_mtime)
        total = sum(f.stat().st_size for f in files)
        while total > self.max and len(files) > 1:
            f = files.pop(0)
            total -= f.stat().st_size
            f.unlink()


RENDER_MODULES = ("sampler", "synth", "fx", "mixer", "vocal", "scenes", "util", "performance", "composition", "targets", "sfz", "schema")


def renderer_version() -> str:
    """Hash of the render-path source files: any code change invalidates the scene cache automatically."""
    h = hashlib.sha256()
    for m in RENDER_MODULES:
        h.update((Path(__file__).parent / f"{m}.py").read_bytes())
    return h.hexdigest()[:16]


class SceneCache:
    """Persistent full-scene cache (no eviction): one float32 .npy per scene holding ONLY the active final atomic stems
    (n_active, 2, T); the mix is the float64 sum of the stems (== the mixer's definition), inactive stems are exact zeros.
    Key = scene spec hash + generator + renderer source hash + asset records + instrument manifests + mix config; it never
    depends on the crop, so every epoch can cut a different window from the same cached scene. Reads are memory-mapped, so a
    crop costs ~1 MB of I/O. Writes are atomic (tmp + rename), safe with several DataLoader workers / fill processes."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.npy"

    def load(self, key: str):
        p = self.path(key)
        try:
            return np.load(p, mmap_mode="r") if p.exists() else None
        except (ValueError, OSError):  # truncated/corrupt entry: treat as a miss and rewrite
            return None

    def put(self, key: str, arr: np.ndarray) -> None:
        p = self.path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
        with open(tmp, "wb") as f:
            np.save(f, np.ascontiguousarray(arr, dtype=np.float32))
        os.replace(tmp, p)


class SceneDataset(Dataset):
    def __init__(self, factory: Factory, split: str, n: int, schema: str, chunk_samples: int, mode: str = "lazy",
                 fixed_dir: str | Path | None = None, cache: DiskCache | None = None, epoch_salt: int = 0,
                 render_path: str = "full", activity_threshold: float = 1e-4, scene_cache: "SceneCache | None" = None):
        self.scene_cache = scene_cache
        self._ctx: str | None = None
        self.f, self.split, self.n, self.schema, self.chunk = factory, split, n, schema, chunk_samples
        self.mode, self.fixed_dir, self.cache, self.salt = mode, Path(fixed_dir) if fixed_dir else None, cache, epoch_salt
        self._specs: dict[int, SceneSpec] = {}
        self.render_path, self.act_thr = render_path, activity_threshold

    def __len__(self):
        return self.n

    def spec(self, i: int) -> SceneSpec:
        if i not in self._specs:
            self._specs[i] = self.f.make_spec(i, self.split)
        return self._specs[i]

    def set_epoch(self, epoch: int) -> None:
        """Deterministic per-epoch crop variation (training only); fixed val/test datasets are never given an epoch."""
        self.salt = int(epoch)

    def cache_key(self, sp: SceneSpec) -> str:
        if self._ctx is None:
            f = self.f
            self._ctx = hash_obj({
                "generator": GENERATOR_VERSION, "renderer": renderer_version(), "sr": f.sr, "mix": f.cfg["mix"],
                "assets": {a: [r.get("sha256"), r.get("version")] for a, r in sorted(f.records.items())},
                "instruments": {i: hash_obj(x.m) for i, x in sorted(f.instruments.items())}})
        return hash_obj([sp.hash(), self._ctx])[:32]

    def _cached_atomic(self, sp: SceneSpec):
        """-> ({stem: (2,T)} for active stems, cache_hit). Renders + stores on a miss."""
        key = self.cache_key(sp)
        arr = self.scene_cache.load(key)
        if arr is not None and arr.shape[0] == len(sp.active_stems):
            return {s: arr[j] for j, s in enumerate(sp.active_stems)}, True
        r = self.f.render(sp)
        arr = np.stack([r["atomic"][s] for s in sp.active_stems])
        self.scene_cache.put(key, arr)
        return {s: arr[j] for j, s in enumerate(sp.active_stems)}, False

    def ensure_cached(self, i: int) -> bool:
        """Cache fill helper. -> True if it was already cached."""
        sp = self.spec(i)
        if self.scene_cache.load(self.cache_key(sp)) is not None:
            return True
        self._cached_atomic(sp)
        return False

    def _group(self, i: int) -> dict:
        if self.mode == "fixed":
            m = json.loads((self.fixed_dir / f"{self.split}_{i:07d}" / "metadata.json").read_text(encoding="utf-8"))
            return {"category": m["scene_type"], "singer": (m.get("vocal") or {}).get("singer", "")}
        sp = self.spec(i)
        return {"category": sp.scene_type, "singer": (sp.vocal or {}).get("singer", "")}

    def __getitem__(self, i: int):
        t0 = time.perf_counter()
        self._hit = False
        if self.mode == "fixed":
            mix, tg = self._fixed(i)
        else:
            mix, tg = self.crop_item(i)
        mix = self._fit(mix)
        stems = {k: self._fit(v) for k, v in tg.items()}
        # activity is read from the cropped target itself: a stem that is active in the scene but silent in this crop
        # (rest, silence block) must also be treated as inactive by the loss
        active = {k: torch.tensor(bool(np.abs(v).max() > self.act_thr)) for k, v in stems.items()}
        return {"mix": torch.from_numpy(mix), "stems": {k: torch.from_numpy(v) for k, v in stems.items()}, "active": active,
                "group": self._group(i), "telemetry": {"load_s": torch.tensor(time.perf_counter() - t0), "hit": torch.tensor(float(self._hit))}}

    def full_scene(self, sp: SceneSpec):
        """Training path: the WHOLE scene is rendered (all FX, scene-level gain) and only then cropped, so a crop equals
        the corresponding slice of the full render exactly. Cached on disk when a cache is configured."""
        key = hash_obj([sp.hash(), self.schema, GENERATOR_VERSION, "full"])[:32]
        arr = self.cache.get(key) if self.cache else None
        if arr is None:
            mix, tg = self.f.render_targets(sp, self.schema, None)
            arr = np.stack([mix] + [tg[k] for k in SCHEMAS[self.schema]])
            if self.cache:
                self.cache.put(key, arr)
        return arr[0], {k: arr[1 + j] for j, k in enumerate(SCHEMAS[self.schema])}

    def crop_item(self, i: int):
        sp = self.spec(i)
        start = crop_start_samples(sp.seeds["mix"] + self.salt, sp.duration_samples, self.chunk)
        end = start + self.chunk
        if self.render_path == "window":  # experimental optimization path; NOT equal to the full render (see docs)
            win = (start / sp.sample_rate, min(end, sp.duration_samples) / sp.sample_rate)
            return self.f.render_targets(sp, self.schema, win)
        if self.scene_cache is not None:  # persistent full-scene cache: cut the crop out of the cached whole scene
            atomic, self._hit = self._cached_atomic(sp)
            sl = slice(start, end)
            crop = {s: np.asarray(a[:, sl]) for s, a in atomic.items()}
            mix = sum(crop[s].astype(np.float64) for s in ATOMIC_ALL if s in crop).astype(np.float32)  # mixer order: mix == sum(stems)
            ref = next(iter(crop.values()))
            full = {s: crop.get(s, np.zeros_like(ref)) for s in ATOMIC_ALL}
            return mix, build_targets(full, self.schema)
        mix, tg = self.full_scene(sp)
        return mix[:, start:end], {k: v[:, start:end] for k, v in tg.items()}

    def _fit(self, a: np.ndarray) -> np.ndarray:
        a = np.ascontiguousarray(a[:, :self.chunk], dtype=np.float32)
        if a.shape[1] < self.chunk:
            a = np.pad(a, ((0, 0), (0, self.chunk - a.shape[1])))
        return a

    def _fixed(self, i: int):
        d = self.fixed_dir / f"{self.split}_{i:07d}"
        meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
        atomic = {s: read_wav(d / f"{s}.wav")[0] for s in meta["active_stems"]}
        ref = next(iter(atomic.values()))
        full = {s: atomic.get(s, np.zeros_like(ref)) for s in meta["all_stems"]}
        mix = read_wav(d / "mix.wav")[0]
        start = crop_start_samples(meta["mix_seed"] + self.salt, mix.shape[1], self.chunk)
        sl = slice(start, start + self.chunk)
        return mix[:, sl], build_targets({s: a[:, sl] for s, a in full.items()}, self.schema)


@DATASETS.register("datafactory_scenes")
def build(ds_cfg: dict, model_cfg: dict, split: str, seed: int) -> SceneDataset:
    p = ds_cfg["params"]
    schema = p["target_schema"]
    if sorted(SCHEMAS[schema]) != sorted(model_cfg["stems"]):
        raise ValueError(f"model stems {model_cfg['stems']} do not match target schema {schema} {list(SCHEMAS[schema])}")
    records = A.load_records(p["asset_dir"]) if p.get("asset_dir") else None  # default: repo artifacts/assets
    factory = Factory.from_yaml(p["factory_config"], p.get("repo_root", "."), records)
    n = p["num_scenes"][split]
    cache = DiskCache(p["cache_dir"], int(p["cache_max_gb"] * 1e9)) if p.get("cache_dir") else None
    scene_cache = SceneCache(p["scene_cache_dir"]) if p.get("scene_cache_dir") and split == "train" else None
    mode = p.get("mode", {}).get(split, "lazy") if isinstance(p.get("mode"), dict) else p.get("mode", "lazy")
    return SceneDataset(factory, split, n, schema, int(p["chunk_samples"]), mode,
                        (p.get("fixed_dir") or None) and Path(p["fixed_dir"]), cache,
                        render_path=p.get("render_path", "full"), activity_threshold=float(p.get("activity_threshold", 1e-4)), scene_cache=scene_cache)
