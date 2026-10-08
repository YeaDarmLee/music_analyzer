"""Scene generation (spec) and deterministic rendering. The spec is the dataset's real content: seeds + chosen
parameters + note events + license-relevant asset ids. Audio is a pure function of (spec, assets)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import yaml

from . import GENERATOR_VERSION, SAMPLE_RATE, assets as A, composition, performance
from .fx import PROFILES, random_chain
from .mixer import mix_stems
from .sampler import SampleInstrument
from .schema import NoteEvent, SceneSpec
from .synth import DrumSynth, SynthEngine, random_kit, random_patch
from .targets import build_targets
from .util import derive_seeds, make_rng, sub_rng
from .vocal import choose_vocal, render_vocal

INSTRUMENTS = ("drums", "bass", "piano", "synth")
PREROLL_S = 2.0
MAX_PREROLL_S = 8.0


def family_split(family_id: str, ratios: dict) -> str:
    f = int(hashlib.sha256((family_id + "|split").encode()).hexdigest()[:8], 16) / 2 ** 32
    t = 0.0
    for k in ("train", "val", "test"):
        t += ratios[k]
        if f < t:
            return k
    return "test"


class Factory:
    """Holds config + loaded assets. Rendering needs the assets; spec generation only needs their ids/metadata."""

    def __init__(self, cfg: dict, instruments: dict[str, SampleInstrument] | None = None, vocal_index: dict | None = None,
                 vocal_root: str | Path | None = None, records: dict | None = None):
        self.cfg, self.sr = cfg, cfg.get("sample_rate", SAMPLE_RATE)
        self.instruments = instruments or {}
        self.vocal_index, self.vocal_root = vocal_index, vocal_root
        self.records = records or A.load_records()
        self.by_stem = {"piano": [], "bass": [], "drums": []}
        for iid, inst in self.instruments.items():
            self.by_stem.setdefault(cfg["instrument_stems"][iid], []).append(iid)

    @classmethod
    def from_yaml(cls, path: str | Path, repo_root: str | Path = ".", records: dict | None = None) -> "Factory":
        cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        records, root = records or A.load_records(), Path(repo_root)
        inst, stems = {}, {}
        for stem, items in (cfg.get("instruments") or {}).items():
            for it in items:
                man = json.loads((root / it["manifest"]).read_text(encoding="utf-8"))
                aroot = records[man["asset_id"]].get("root")
                if not aroot:
                    raise ValueError(f"asset {man['asset_id']} is not ingested (no root); cannot load {it['manifest']}")
                aroot = Path(aroot) if Path(aroot).is_absolute() else root / aroot
                if man.get("sample_root") and not Path(man["sample_root"]).is_absolute():
                    man["sample_root"] = str((root / man["sample_root"]).resolve())  # derived-sample dirs are repo-relative
                inst[man["instrument_id"]] = SampleInstrument(man, aroot, cfg.get("sample_rate", SAMPLE_RATE))
                stems[man["instrument_id"]] = stem
        cfg["instrument_stems"] = stems
        vi = vroot = None
        if cfg.get("vocal_index"):
            vi = json.loads((root / cfg["vocal_index"]).read_text(encoding="utf-8"))
            vroot = records[vi["asset_id"]]["root"]
            vroot = Path(vroot) if Path(vroot).is_absolute() else root / vroot
        return cls(cfg, inst, vi, vroot, records)

    # ------------------------------------------------------------------------------------------------------------
    def make_spec(self, index: int, split: str, git_commit: str = "", force: dict | None = None) -> SceneSpec:
        """force (listening/evaluation packs only): {"active": [stems], "sample": bool, "scene_type": str} overrides the
        random scene-type draw; it is part of the seed so forced scenes never collide with regular ones."""
        cfg, sr = self.cfg, self.sr
        family_target = "test" if split == "ood" else split
        for attempt in range(256):  # rejection sampling keeps whole composition families inside one split
            seeds = derive_seeds(cfg["master_seed"], index, f"{split}#{attempt}" + (f"#force{sorted(force.items())}" if force else ""))
            lo, hi = cfg["duration_seconds"]
            rc = make_rng(seeds["composition"])
            dur = float(rc.uniform(lo, hi))
            comp = composition.compose(dur, rc, tuple(cfg.get("bpm_range", (70, 150))))
            if family_split(comp["family_id"], cfg["split_ratios"]) == family_target:
                break
        else:
            raise RuntimeError("could not find a composition family for the requested split")
        n = int(round(dur * sr))
        rp = make_rng(seeds["performance"])
        ri = make_rng(seeds["instrument"])
        rf = make_rng(seeds["fx"])
        rm = make_rng(seeds["mix"])

        stype, active = self._scene_type(rp, split)
        if force and "active" in force:
            stype, active = force.get("scene_type", "forced"), set(force["active"])
            rp.rand()
        profile = list(cfg["profiles"])[rm.randint(len(cfg["profiles"]))]
        sparse = stype in ("sparse_instrument", "near_silence")
        comp = dict(comp, density=0.2 if sparse else comp["density"])

        events, renderers, assets_used, perf_meta = [], {}, {A.INTERNAL_ASSET_ID}, {}
        for stem in [s for s in INSTRUMENTS if s in active]:
            ev, meta, rend, aid = self._instrument(stem, comp, dur, rp, ri, split, bool(force and force.get("sample")))
            events += ev
            renderers[stem] = rend
            perf_meta[stem] = meta
            if aid:
                assets_used.add(aid)
        vocal = None
        if "vocal" in active:
            vocal = choose_vocal(self.vocal_index, "test" if split == "ood" else split, make_rng(seeds["instrument"] ^ 0x5EED), dur)
            assets_used.add(vocal["asset_id"])
        fx = {s: random_chain(s, profile, rf) for s in active}
        mix_cfg = cfg["mix"]
        gains = {s: float(rm.uniform(*mix_cfg["stem_gain_db"])) for s in active}
        if "vocal" in gains:
            gains["vocal"] = float(rm.uniform(*mix_cfg["vocal_gain_db"]))
        lvl = mix_cfg["near_silence_rms_db"] if stype == "near_silence" else mix_cfg["target_rms_db"]
        mix = {"stem_gain_db": gains, "target_rms_db": float(rm.uniform(*lvl)), "peak_limit": mix_cfg["peak_limit"],
               "stem_ref_rms_db": mix_cfg.get("stem_ref_rms_db")}
        comp_store = {k: v for k, v in comp.items() if k != "scale"} | {"performance": perf_meta}
        return SceneSpec(
            scene_id=f"{split}_{index:07d}", split=split, composition_family_id=comp["family_id"], duration_samples=n,
            sample_rate=sr, seeds=seeds, scene_type=stype, profile=profile, composition=comp_store,
            active_stems=sorted(active), note_events=[e.to_list() for e in sorted(events, key=lambda e: (e.start, e.instrument, e.pitch))],
            renderers=renderers, fx=fx, mix=mix, vocal=vocal, assets=sorted(assets_used),
            target_schema="atomic_v1", generator_version=GENERATOR_VERSION, git_commit=git_commit)

    def _scene_type(self, rp, split) -> tuple[str, set]:
        dist = dict(self.cfg["scene_types"])
        if not self.vocal_index:
            dist = {k: v for k, v in dist.items() if k not in ("vocal_plus_instruments", "vocal_only")}
        names = sorted(dist)
        p = np.array([dist[k] for k in names], dtype=np.float64)
        stype = names[rp.choice(len(names), p=p / p.sum())]
        k = int(rp.randint(1, 5))
        insts = list(rp.permutation(list(INSTRUMENTS))[:k])
        have_vocal = bool(self.vocal_index)
        if stype == "vocal_plus_instruments":
            return stype, {"vocal", *insts}
        if stype == "instrumental_only":
            return stype, set(insts)
        if stype == "vocal_only":
            return stype, {"vocal"}
        if stype == "sparse_instrument":
            act = set(insts[:1 + int(rp.randint(2))])
            return stype, act | ({"vocal"} if have_vocal and rp.rand() < .5 else set())
        act = set(insts[:1 + int(rp.randint(2))])  # near_silence
        return stype, act | ({"vocal"} if have_vocal and rp.rand() < .3 else set())

    def _pool(self, stem: str, split: str) -> list[str]:
        hold = set(self.cfg.get("holdout_instruments", []))
        ids = self.by_stem.get(stem, [])
        return [i for i in ids if (i in hold) == (split == "ood")] or ([] if split != "ood" else [i for i in ids if i not in hold])

    def _instrument(self, stem, comp, dur, rp, ri, split, force_sample=False):
        pool = self._pool(stem, split)
        use_sample = bool(pool) and (stem == "piano" or force_sample or ri.rand() < .5)
        if stem == "piano":
            ev, meta = performance.piano(comp, dur, rp)
            if use_sample:
                iid = pool[ri.randint(len(pool))]
                return ev, meta, {"kind": "sample", "instrument_id": iid}, self.instruments[iid].asset_id
            fam = "keys"
            patch = random_patch(fam, ri)
            return ev, meta, {"kind": "synth", "patch": patch, "fallback_for": "piano_sample"}, None
        if stem == "bass":
            sample = use_sample
            ev, meta = performance.bass(comp, dur, rp, glide=not sample)
            if sample:
                iid = pool[ri.randint(len(pool))]
                return ev, meta, {"kind": "sample", "instrument_id": iid}, self.instruments[iid].asset_id
            return ev, meta, {"kind": "synth", "patch": random_patch("synth_bass", ri), "saturation": float(ri.uniform(0, 1.5))}, None
        if stem == "drums":
            ev, meta = performance.drums(comp, dur, rp)
            if use_sample:
                iid = pool[ri.randint(len(pool))]
                return ev, meta, {"kind": "sample", "instrument_id": iid}, self.instruments[iid].asset_id
            return ev, meta, {"kind": "drum_synth", "kit": random_kit(ri)}, None
        ev, meta = performance.synth(comp, dur, rp)  # synth
        fam = {"pad": "pad", "lead": "lead", "arp": "arp", "pluck": "pluck"}[meta["role"]]
        return ev, meta, {"kind": "synth", "patch": random_patch(fam, ri)}, None

    # ------------------------------------------------------------------------------------------------------------
    def render(self, spec: SceneSpec, window: tuple[float, float] | None = None) -> dict:
        """Render the scene (or a (start_s, end_s) window with pre-roll). -> {"mix","atomic","info"}; all float32 (2, T)."""
        sr = self.sr
        t0, t1 = (0.0, spec.duration_samples / sr) if window is None else window
        events = spec.events()
        # pre-roll: at least PREROLL_S, extended back to the start of any note still sounding at t0 (capped)
        sounding = [e.start for e in events if e.start < t0 < e.end + 1.0]
        pre = min(t0, min(max(PREROLL_S, t0 - min(sounding) if sounding else 0.0), MAX_PREROLL_S))
        r0 = t0 - pre
        n_range = int(round((t1 - r0) * sr))
        crop = int(round(pre * sr))
        raw = {}
        for stem in spec.active_stems:
            if stem == "vocal":
                v = dict(spec.vocal)
                place = v["place_start_s"] - r0
                v["crop_start_s"] = v["crop_start_s"] + max(-place, 0.0)
                v["place_start_s"] = max(place, 0.0)
                v["silence"] = [[a - r0, b - r0] for a, b in v["silence"]]
                raw["vocal"] = render_vocal(v, self.vocal_root, n_range, sr)
                continue
            evs = [NoteEvent(e.instrument, e.pitch, e.velocity, e.start - r0, e.end - r0, e.articulation, e.channel, e.meta)
                   for e in events if e.instrument == stem and 0 <= e.start - r0 < n_range / sr]
            r, rng = spec.renderers[stem], sub_rng(spec.seeds["instrument"], stem)
            if r["kind"] == "sample":
                raw[stem] = self.instruments[r["instrument_id"]].render(evs, n_range, rng)
            elif r["kind"] == "synth":
                raw[stem] = SynthEngine(r["patch"], sr, r.get("saturation", 0.0)).render(evs, n_range, rng)
            else:
                raw[stem] = DrumSynth(r["kit"], sr).render(evs, n_range, rng)
        final, mix, info = mix_stems(raw, spec.fx, spec.mix, spec.seeds["fx"], sr, n_range, crop)
        return {"mix": mix, "atomic": final, "info": info, "samples": mix.shape[1]}

    def render_targets(self, spec: SceneSpec, schema: str, window=None) -> tuple[np.ndarray, dict]:
        r = self.render(spec, window)
        return r["mix"], build_targets(r["atomic"], schema)
