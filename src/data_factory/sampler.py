"""Minimal deterministic sampler: zone selection (key/velocity/round-robin), repitch by playback rate, loop, ADSR-like
envelope, equal-power pan, note mixing. No external playback engine.

Instrument manifest (`instrument_manifest.json`):
  {instrument_id, asset_id, kind: "pitched" | "drumkit", source_version, license, source_sha256,
   zones: [{sample, root_key, lo_key, hi_key, lo_vel, hi_vel, volume_db, pan, tune_cents, offset, keytrack, one_shot,
            loop?, seq?, rand?, release_s?}]}
Sample paths are relative to the asset root directory recorded for `asset_id`.
"""
from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

import numpy as np

from .schema import NoteEvent
from .util import read_wav, to_stereo


class SampleInstrument:
    def __init__(self, manifest: dict, asset_root: str | Path, sr: int = 44100, cache_bytes: int = 512 << 20,
                 attack_s: float = 0.003, default_release_s: float = 0.25, vel_exp: float = 0.6,
                 max_sample_seconds: float = 14.0):
        self.m, self.sr = manifest, sr
        self.root = Path(asset_root)
        if manifest.get("sample_root"):  # derived (e.g. FLAC->WAV decoded) copy of the pinned asset
            sr_root = Path(manifest["sample_root"])
            self.root = sr_root if sr_root.is_absolute() else self.root / sr_root
        self.max_sample_seconds = max_sample_seconds
        self.zones = manifest["zones"]
        self.zones_pedal_up = manifest.get("zones_pedal_up") or self.zones  # CC64<64 region set (only if the SFZ provides one)
        self.kind = manifest.get("kind", "pitched")
        self.attack_s, self.release_s, self.vel_exp = attack_s, default_release_s, vel_exp
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._cache_bytes, self._cache_used = cache_bytes, 0
        self.skipped = 0

    @property
    def instrument_id(self) -> str:
        return self.m["instrument_id"]

    @property
    def asset_id(self) -> str:
        return self.m["asset_id"]

    # -- sample cache ------------------------------------------------------------------------------------------
    def _audio(self, zone: dict) -> np.ndarray:
        k = zone["sample"]
        if k in self._cache:
            self._cache.move_to_end(k)
            return self._cache[k]
        a = to_stereo(read_wav(self.root / k, self.sr, self.max_sample_seconds)[0])
        self._cache[k] = a
        self._cache_used += a.nbytes
        while self._cache_used > self._cache_bytes and len(self._cache) > 1:
            _, old = self._cache.popitem(last=False)
            self._cache_used -= old.nbytes
        return a

    # -- zone choice ---------------------------------------------------------------------------------------------
    def select_zone(self, pitch: int, velocity: int, rr: float, counter: int, pedal_down: bool = True) -> dict | None:
        zones = self.zones if pedal_down else self.zones_pedal_up
        cand = [z for z in zones if z["lo_key"] <= pitch <= z["hi_key"] and z["lo_vel"] <= velocity <= z["hi_vel"]]
        if not cand:  # nearest key range, same velocity window: tolerate small gaps in a mapping
            vel_ok = [z for z in zones if z["lo_vel"] <= velocity <= z["hi_vel"]] or zones
            z = min(vel_ok, key=lambda z: min(abs(pitch - z["lo_key"]), abs(pitch - z["hi_key"])))
            if min(abs(pitch - z["lo_key"]), abs(pitch - z["hi_key"])) > 12:
                return None
            cand = [z]
        seq = [z for z in cand if "seq" in z]
        if seq:
            L = seq[0]["seq"][1]
            want = counter % L + 1
            sel = [z for z in seq if z["seq"][0] == want]
            cand = sel or cand
        rnd = [z for z in cand if "rand" in z]
        if rnd:
            sel = [z for z in rnd if z["rand"][0] <= rr < z["rand"][1]]
            cand = sel or cand
        if len(cand) > 1:  # several equivalent zones: pick by rr, deterministic given rr
            cand = sorted(cand, key=lambda z: (z["sample"]))
            return cand[int(rr * len(cand)) % len(cand)]
        return cand[0]

    # -- one note --------------------------------------------------------------------------------------------------
    def _note(self, zone: dict, pitch: int, velocity: int, held: int) -> np.ndarray:
        a = self._audio(zone)
        off = int(zone.get("offset", 0))
        a = a[:, off:]
        n_src = a.shape[1]
        if n_src < 2:
            return np.zeros((2, 0), np.float32)
        ratio = 2.0 ** (((pitch - zone["root_key"]) if zone.get("keytrack", True) else 0) / 12.0
                        + zone.get("tune_cents", 0.0) / 1200.0)
        rel = int(round(zone.get("release_s", self.release_s) * self.sr))
        one_shot = zone.get("one_shot") or self.kind == "drumkit"
        loop = zone.get("loop")
        if one_shot:
            n_out = int((n_src - 1) / ratio)
        elif loop:
            n_out = held + rel
        else:
            n_out = min(held + rel, int((n_src - 1) / ratio))
        n_out = max(n_out, 0)
        pos = np.arange(n_out, dtype=np.float64) * ratio
        if loop and not one_shot:
            ls, le = max(loop[0] - off, 0), min(loop[1] - off, n_src - 1)
            if le > ls:
                pos = np.where(pos >= le, ls + np.mod(pos - ls, le - ls), pos)
        pos = np.minimum(pos, n_src - 1.001)
        i0 = pos.astype(np.int64)
        fr = (pos - i0).astype(np.float32)
        y = a[:, i0] * (1 - fr) + a[:, i0 + 1] * fr
        env = np.ones(n_out, np.float32)
        att = min(int(self.attack_s * self.sr), n_out)
        if att:
            env[:att] = np.linspace(0, 1, att, dtype=np.float32)
        if not one_shot and n_out > held:  # release: exponential to -60 dB over `rel`
            r = n_out - held
            env[held:] *= np.exp(np.linspace(0, -6.9, r, dtype=np.float32))
        elif one_shot and n_out > 64:
            env[-64:] *= np.linspace(1, 0, 64, dtype=np.float32)
        v = max(velocity, 1) / 127.0
        if "amp_veltrack" in zone:  # SFZ: gain = (1 - t) + t * curve(v), default curve v^2 (sfizz/ARIA convention)
            t = zone["amp_veltrack"] / 100.0
            vg = (1.0 - t) + t * v * v
        else:
            vg = v ** self.vel_exp
        g = 10.0 ** (zone.get("volume_db", 0.0) / 20.0) * vg
        th = (zone.get("pan", 0.0) / 100.0 + 1.0) * np.pi / 4.0
        pan = np.array([[np.cos(th)], [np.sin(th)]], np.float32) * np.float32(np.sqrt(2.0))
        return (y * env * g * pan).astype(np.float32)

    def render(self, events: list[NoteEvent], duration_samples: int, rng: np.random.RandomState) -> np.ndarray:
        out = np.zeros((2, duration_samples), np.float32)
        counter = 0
        for ev in sorted(events, key=lambda e: (e.start, e.pitch)):
            s0 = int(round(ev.start * self.sr))
            if s0 >= duration_samples:
                continue
            rr = float(rng.rand())
            z = self.select_zone(ev.pitch, ev.velocity, rr, counter, ev.meta.get("cc64", 127) >= 64)
            counter += 1
            if z is None:
                self.skipped += 1
                continue
            held = max(int(round((ev.end - ev.start) * self.sr)), 1)
            y = self._note(z, ev.pitch, ev.velocity, held)
            n = min(y.shape[1], duration_samples - s0)
            if n > 0:
                out[:, s0:s0 + n] += y[:, :n]
        return out


def load_instrument(manifest_path: str | Path, asset_roots: dict[str, str | Path], sr: int = 44100, **kw) -> SampleInstrument:
    m = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    return SampleInstrument(m, asset_roots[m["asset_id"]], sr, **kw)


def build_manifest_from_sfz(sfz_path: str | Path | list, asset_root: str | Path, instrument_id: str, asset_id: str,
                            source_version: str, license: str, source_sha256: str, kind: str = "pitched",
                            strict: bool = True, base_dir: str | None = None, cc_state: dict | None = None,
                            sample_root: str | None = None, cc_variants: dict | None = None) -> tuple[dict, dict]:
    """Ingest SFZ file(s) into an instrument manifest. -> (manifest, report).

    sfz_path: one path, or a list of (path, overrides_dict) pairs. Overrides are explicit opcodes prepended as a <group>
    to that file (e.g. {"hivel": 63, "seq_length": 5} for a Karoryfer velocity map whose program file would set them);
    they are recorded in manifest["ingest_overrides"]. base_dir (relative to asset_root) is the directory that
    `sample=` paths are relative to - SFZ resolves them against the ROOT program file, not an #include'd map file."""
    from .sfz import parse_sfz, regions_to_zones
    asset_root = Path(asset_root)
    items = [(Path(sfz_path), {})] if isinstance(sfz_path, (str, Path)) else [(Path(p), dict(o)) for p, o in sfz_path]
    regions, unsupported, notes_all, overrides = [], {}, {}, {}
    texts = []
    for path, ov in items:
        text = path.read_text(encoding="utf-8", errors="replace")
        if ov:
            text = "<group> " + " ".join(f"{k}={v}" for k, v in ov.items()) + "\n" + text
            overrides[path.relative_to(asset_root).as_posix()] = ov
        texts.append(text)
        reg, uns = parse_sfz(text, strict=strict, cc_state=cc_state)
        for k, v in uns.items():
            unsupported[k] = unsupported.get(k, 0) + v
        regions += reg
    here = base_dir if base_dir is not None else (items[0][0].parent.relative_to(asset_root).as_posix() or ".")
    zones, notes = regions_to_zones(regions, here)
    missing = [z["sample"] for z in zones if not (asset_root / z["sample"]).exists()]
    zones = [z for z in zones if (asset_root / z["sample"]).exists()]
    variants = {}
    for name, st in (cc_variants or {}).items():  # alternative fixed-controller states, e.g. pedal_up = {64: 0}
        vreg = []
        for text in texts:
            vreg += parse_sfz(text, strict=strict, cc_state=st)[0]
        vz, _ = regions_to_zones(vreg, here)
        vz = [z for z in vz if (asset_root / z["sample"]).exists()]
        variants[name] = {"cc_state": {str(k): v for k, v in st.items()}, "differs": vz != zones, "zones": vz if vz != zones else None}
    man = {"instrument_id": instrument_id, "asset_id": asset_id, "kind": kind, "source_version": source_version,
           "license": license, "source_sha256": source_sha256, "ingest_overrides": overrides,
           "cc_state": {str(k): v for k, v in (cc_state or {}).items()}, "zones": zones}
    if "pedal_up" in variants:
        pu = variants["pedal_up"]
        man["pedal_up"] = {"cc_state": pu["cc_state"], "separate_region_set": pu["differs"]}
        if pu["differs"]:
            man["zones_pedal_up"] = pu["zones"]
    man["ingest_report"] = {"unsupported_opcodes": unsupported, "skipped": dict(notes),
                            "note": "trigger=release (key-off noise) and on_locc* regions are excluded by design"}
    return man, {"unsupported_opcodes": unsupported, "notes": dict(notes), "missing_samples": missing,
                 "regions": len(regions), "zones": len(zones)}
