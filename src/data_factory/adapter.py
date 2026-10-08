"""DF-7: Data Factory -> engine dataset contract. The ONLY module (besides assets.py) that imports `engine`.

Registered as dataset kind `datafactory_scenes`. Item = {"mix": (2,T) float32 tensor, "stems": {target_name: (2,T)}}.
mode "lazy"  : spec generated from (master_seed, split, index), window-rendered on demand (training).
mode "fixed" : pre-rendered scene directories (validation/test), cropped deterministically.
Optional disk cache of rendered windows (LRU by mtime, size-capped)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset

from engine.registry import DATASETS

from . import GENERATOR_VERSION, assets as A
from .scenes import Factory
from .schema import SceneSpec
from .targets import SCHEMAS, build_targets
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


class SceneDataset(Dataset):
    def __init__(self, factory: Factory, split: str, n: int, schema: str, chunk_samples: int, mode: str = "lazy",
                 fixed_dir: str | Path | None = None, cache: DiskCache | None = None, epoch_salt: int = 0):
        self.f, self.split, self.n, self.schema, self.chunk = factory, split, n, schema, chunk_samples
        self.mode, self.fixed_dir, self.cache, self.salt = mode, Path(fixed_dir) if fixed_dir else None, cache, epoch_salt
        self._specs: dict[int, SceneSpec] = {}

    def __len__(self):
        return self.n

    def spec(self, i: int) -> SceneSpec:
        if i not in self._specs:
            self._specs[i] = self.f.make_spec(i, self.split)
        return self._specs[i]

    def __getitem__(self, i: int):
        if self.mode == "fixed":
            mix, tg = self._fixed(i)
        else:
            sp = self.spec(i)
            start = crop_start_samples(sp.seeds["mix"] + self.salt, sp.duration_samples, self.chunk)
            win = (start / sp.sample_rate, (start + min(self.chunk, sp.duration_samples)) / sp.sample_rate)
            key = hash_obj([sp.hash(), win, self.schema, GENERATOR_VERSION])[:32]
            arr = self.cache.get(key) if self.cache else None
            if arr is None:
                mix, tg = self.f.render_targets(sp, self.schema, win)
                arr = np.stack([mix] + [tg[k] for k in SCHEMAS[self.schema]])
                if self.cache:
                    self.cache.put(key, arr)
            mix, tg = arr[0], {k: arr[1 + j] for j, k in enumerate(SCHEMAS[self.schema])}
        mix = self._fit(mix)
        return {"mix": torch.from_numpy(mix), "stems": {k: torch.from_numpy(self._fit(v)) for k, v in tg.items()}}

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
    mode = p.get("mode", {}).get(split, "lazy") if isinstance(p.get("mode"), dict) else p.get("mode", "lazy")
    return SceneDataset(factory, split, n, schema, int(p["chunk_samples"]), mode,
                        (p.get("fixed_dir") or None) and Path(p["fixed_dir"]), cache)
