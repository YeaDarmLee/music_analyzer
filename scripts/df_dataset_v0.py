"""Dataset v0 build + report (Data Factory v0 FROZEN; only distribution lives in configs/data_factory/dataset_v0.yaml).
 1. spec stats for train (lazy specs) / val / test, family-leakage check, vocal + instrument usage
 2. fixed render of val/test to data/factory/dataset_v0 (QC + production gate per scene)
 3. license manifest for all scenes (PRODUCTION_TRAINING gate)
 4. dataloader throughput on the new distribution
usage: python scripts/df_dataset_v0.py [--no-render]  -> docs/benchmark/dataset_v0_report.json"""
import collections
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from data_factory import assets as A  # noqa: E402
from data_factory.fixed import render_specs  # noqa: E402
from data_factory.scenes import Factory  # noqa: E402
from data_factory.synth import label_patch  # noqa: E402
from data_factory.util import hash_obj  # noqa: E402

CFG = REPO / "configs/data_factory/dataset_v0.yaml"
OUT = REPO / "data/factory/dataset_v0"
CHUNK = 131584


def stats(specs, f, vocal_clips_total):
    st = {"scenes": len(specs), "seconds_total": 0.0}
    st["category"] = dict(collections.Counter(s.scene_type for s in specs))
    st["duration_s"] = {k: round(float(v), 2) for k, v in zip(("min", "mean", "max"), (min(s.duration_samples for s in specs) / 44100,
                        np.mean([s.duration_samples for s in specs]) / 44100, max(s.duration_samples for s in specs) / 44100))}
    st["hours_total"] = round(sum(s.duration_samples for s in specs) / 44100 / 3600, 2)
    st["active_stem_count_hist"] = dict(sorted(collections.Counter(len(s.active_stems) for s in specs).items()))
    st["stem_presence"] = {k: sum(k in s.active_stems for s in specs) for k in ("vocal", "piano", "bass", "drums", "synth")}
    st["composition_families"] = len({s.composition_family_id for s in specs})
    st["bpm"] = dict(zip(("min", "mean", "max"), (min(s.composition["bpm"] for s in specs), round(float(np.mean([s.composition["bpm"] for s in specs])), 1),
                                                  max(s.composition["bpm"] for s in specs))))
    st["key_root_hist"] = dict(sorted(collections.Counter(s.composition["key_root"] for s in specs).items()))
    st["mode"] = dict(collections.Counter(s.composition["mode"] for s in specs))
    st["fx_profile"] = dict(collections.Counter(s.profile for s in specs))
    inst = collections.defaultdict(collections.Counter)
    patches = collections.defaultdict(set)
    for s in specs:
        for stem, r in s.renderers.items():
            if r["kind"] == "sample":
                inst[stem][r["instrument_id"]] += 1
            elif r["kind"] == "drum_synth":
                inst[stem]["own_drum_synth"] += 1
                patches[stem].add(hash_obj(r["kit"]))
            else:
                inst[stem]["own_synth:" + (r["patch"].get("family_hint") or "?")] += 1
                patches[stem].add(hash_obj(r["patch"]))
    st["instrument_usage"] = {k: dict(v) for k, v in inst.items()}
    st["unique_synth_or_kit_patches"] = {k: len(v) for k, v in patches.items()}
    st["performance"] = {
        "piano_pattern": dict(collections.Counter(s.composition["performance"]["piano"]["pattern"] for s in specs if "piano" in s.active_stems)),
        "piano_pedal_mode": dict(collections.Counter(s.composition["performance"]["piano"]["pedal_mode"] for s in specs if "piano" in s.active_stems)),
        "bass_pattern": dict(collections.Counter(s.composition["performance"]["bass"]["pattern"] for s in specs if "bass" in s.active_stems)),
        "drum_groove": dict(collections.Counter(s.composition["performance"]["drums"]["groove"] for s in specs if "drums" in s.active_stems)),
        "synth_role": dict(collections.Counter(s.composition["performance"]["synth"]["role"] for s in specs if "synth" in s.active_stems))}
    v = [s for s in specs if s.vocal]
    clips = collections.Counter(s.vocal["clip_id"] for s in v)
    st["vocal"] = {"scenes": len(v), "singers": dict(sorted(collections.Counter(s.vocal["singer"] for s in v).items())),
                   "category": dict(collections.Counter(s.vocal["category"] for s in v)), "unique_clips_used": len(clips),
                   "unique_clips_available_in_split": vocal_clips_total, "max_uses_of_one_clip": max(clips.values()) if clips else 0,
                   "doubled_vocal_scenes": sum(bool(s.vocal.get("double")) for s in v)}
    dur = {c["clip_id"]: c["duration_s"] for c in f.vocal_index["clips"]}
    st["vocal"]["vocal_minutes_approx"] = round(sum(min(dur[s.vocal["clip_id"]], s.duration_samples / 44100) for s in v) / 60, 1)
    return st


def main(render=True):
    f = Factory.from_yaml(CFG, REPO)
    sizes = f.cfg["dataset_sizes"]
    rep = {"config": str(CFG.relative_to(REPO)), "config_sha256": hash_obj(f.cfg)[:16], "sizes": sizes,
           "ratios": f.cfg["scene_types"], "split_ratios_by_family": f.cfg["split_ratios"]}
    t = time.time()
    specs = {sp: [f.make_spec(i, sp) for i in range(sizes[sp])] for sp in ("train", "val", "test")}
    rep["spec_generation_seconds"] = round(time.time() - t, 1)
    idx = f.vocal_index
    for sp in specs:
        n_clips = sum(1 for c in idx["clips"] if idx["singer_split"][c["singer"]] == sp)
        rep[sp] = stats(specs[sp], f, n_clips)
    fam = {sp: {s.composition_family_id for s in specs[sp]} for sp in specs}
    rep["leakage"] = {"family_overlap_train_val": len(fam["train"] & fam["val"]), "family_overlap_train_test": len(fam["train"] & fam["test"]),
                      "family_overlap_val_test": len(fam["val"] & fam["test"]),
                      "singer_overlap": {f"{a}_{b}": sorted({s.vocal["singer"] for s in specs[a] if s.vocal} & {s.vocal["singer"] for s in specs[b] if s.vocal})
                                         for a, b in (("train", "val"), ("train", "test"), ("val", "test"))},
                      "duplicate_scene_spec_hashes_in_train": len(specs["train"]) - len({s.hash() for s in specs["train"]})}
    # license manifest for every scene (PRODUCTION_TRAINING gate)
    from engine.data.manifest import require_valid
    per = {s.scene_id: s.assets for sp in specs for s in specs[sp]}
    man = A.build_manifest("dataset_v0", f.records, per)
    rep["manifest_sha256"] = require_valid(man, "PRODUCTION_TRAINING")
    (REPO / "artifacts/manifests/dataset_v0.manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    rep["assets_used"] = sorted(man["assets"])
    # throughput on the new distribution: per-category full-scene render cost + DataLoader items/s
    from torch.utils.data import DataLoader
    from data_factory.adapter import SceneDataset
    cat_t = collections.defaultdict(list)
    for i in range(100, 100 + 70):
        s = specs["train"][i]
        t = time.perf_counter(); r = f.render(s); cat_t[s.scene_type].append((time.perf_counter() - t, s.duration_samples / 44100))
    rep["render_seconds_per_scene_by_category"] = {k: {"n": len(v), "s_per_scene": round(float(np.mean([a for a, _ in v])), 3),
                                                       "rtf": round(sum(a for a, _ in v) / sum(b for _, b in v), 3)} for k, v in cat_t.items()}
    ds = SceneDataset(f, "train", sizes["train"], "2stem_v1", CHUNK, "lazy")
    thr = {}
    for w in (0, 4, 8):
        dl = DataLoader(torch_subset(ds, 1000), batch_size=4, shuffle=False, num_workers=w, persistent_workers=w > 0)
        it = iter(dl); next(it); t = time.perf_counter(); k = 0
        for b in it:
            k += b["mix"].shape[0]
            if k >= 48:
                break
        thr[f"workers_{w}"] = round(k / (time.perf_counter() - t), 2)
        del it, dl
    rep["dataloader_items_per_second_full_scene_render"] = thr
    mean_bytes = int(np.mean([(1 + 2) * 2 * s.duration_samples * 4 for s in specs["train"][:2000]]))
    rep["full_scene_cache_bytes_per_scene_2stem_float32"] = mean_bytes
    if render:
        OUT.mkdir(parents=True, exist_ok=True)
        for sp in ("val", "test"):
            t = time.time()
            r = render_specs(f, specs[sp], OUT)
            rep[sp]["fixed_render"] = {"ok": len(r["scenes"]), "failed": r["failed"], "seconds": round(time.time() - t, 1)}
        rep["fixed_bytes"] = sum(p.stat().st_size for p in OUT.rglob("*.wav"))
    (REPO / "docs/benchmark/dataset_v0_report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("spec_generation_seconds", "leakage", "render_seconds_per_scene_by_category",
                                          "dataloader_items_per_second_full_scene_render", "full_scene_cache_bytes_per_scene_2stem_float32")}, indent=1))
    for sp in ("train", "val", "test"):
        print(sp, rep[sp]["scenes"], rep[sp]["hours_total"], "h", rep[sp]["category"], rep[sp].get("fixed_render"))


def torch_subset(ds, off):
    from torch.utils.data import Subset
    return Subset(ds, list(range(off, off + 200)))


if __name__ == "__main__":
    main("--no-render" not in sys.argv)
