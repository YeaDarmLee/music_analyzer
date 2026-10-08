"""Long Listening Pack (evaluation artifact, NOT training data): 8 songs of ~45-60 s with section structure, built from the
existing Composition/Performance generators and the PRODUCTION-gated real assets. dataset_usage = LISTENING_EVALUATION.
Vocal singers are VocalSet *val* singers (never train). Training scenes keep the 5-15 s lazy-render format.
usage: python scripts/df_long_listening.py [out_dir]"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.signal import lfilter

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from data_factory import SAMPLE_RATE, assets as A, composition, performance  # noqa: E402
from data_factory.fx import random_chain  # noqa: E402
from data_factory.mixer import active_rms  # noqa: E402
from data_factory.qc import qc_scene  # noqa: E402
from data_factory.scenes import Factory  # noqa: E402
from data_factory.schema import ATOMIC_STEMS, SceneSpec  # noqa: E402
from data_factory.synth import label_patch, random_patch  # noqa: E402
from data_factory.targets import ATOMIC_ALL, build_targets  # noqa: E402
from data_factory.util import derive_seeds, hash_obj, make_rng, sub_rng, write_wav  # noqa: E402

TAIL_S = 2.0
NOTE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def sec(name, bars, prog, **parts):
    """parts: piano=<pattern>, bass=<pattern>, drums=<groove>, synth=True, vocal=<categories tuple>"""
    return {"name": name, "bars": bars, "prog": prog, "parts": parts}


L, SC, AR = ("long_tones",), ("scales", "arpeggios"), ("long_tones", "scales", "arpeggios")
SONGS = [
    dict(id="01_piano_band", brief="Piano-centered: vocal+piano+bass+drums, weak pad", key=9, mode="minor", target_s=56, profile="pop_clean",
         singer="female9", piano="vcsl_keys_grand_k", bass="sneakybass_pluck", drums="vcsl_drums", synth_role="pad",
         gains={"vocal": 1.0, "piano": 0.0, "bass": -3.0, "drums": -3.0, "synth": -10.0},
         sections=[sec("intro", 2, "A", piano="ballad"), sec("verse", 8, "A", piano="broken", bass="root_whole", vocal=L, synth=True),
                   sec("pre", 2, "B", piano="comping", bass="root_eighths", drums="ballad", vocal=SC, synth=True),
                   sec("chorus", 8, "B", piano="block", bass="root_fifth_octave", drums="pop", vocal=AR, synth=True),
                   sec("outro", 2, "A", piano="ballad")]),
    dict(id="02_full_band", brief="Full band: vocal+piano+bass+drums+synth", key=2, mode="major", target_s=57, profile="rock_dense",
         singer="male11", piano="vcsl_keys_steinway_b", bass="blb_pluck_center", drums="stargate_drums", synth_role="pluck",
         gains={"vocal": 2.0, "piano": -2.0, "bass": -2.0, "drums": -2.0, "synth": -5.0},
         sections=[sec("intro", 2, "A", piano="octave_bass", drums="rock", synth=True),
                   sec("verse", 8, "A", piano="comping", bass="root_eighths", drums="pop", vocal=SC, synth=True),
                   sec("pre", 2, "B", piano="block", bass="syncopated", drums="rock", vocal=SC, synth=True),
                   sec("chorus", 8, "B", piano="octave_bass", bass="root_fifth_octave", drums="rock", vocal=AR, synth=True),
                   sec("outro", 2, "A", piano="block", bass="root_whole", drums="halftime", synth=True)]),
    dict(id="03_ballad", brief="Ballad: vocal+piano+bass+pad", key=5, mode="major", target_s=55, profile="ballad",
         singer="female9", piano="vcsl_keys_upright_knight", bass="blb_pluck_center", drums=None, synth_role="pad",
         gains={"vocal": 1.0, "piano": -1.0, "bass": -2.0, "synth": -6.0},
         sections=[sec("intro", 2, "A", piano="ballad", synth=True), sec("verse", 4, "A", piano="ballad", bass="root_whole", vocal=L, synth=True),
                   sec("verse2", 4, "A", piano="arpeggio", bass="root_whole", vocal=L, synth=True),
                   sec("chorus", 4, "B", piano="block", bass="root_whole", vocal=L, synth=True), sec("outro", 2, "A", piano="ballad", synth=True)]),
    dict(id="04_upbeat", brief="Up-tempo: vocal+drums+bass+piano+synth", key=7, mode="major", target_s=52, profile="electronic",
         singer="male11", piano="vcsl_keys_upright_y", bass="sneakybass_pluck", drums="vcsl_drums", synth_role="arp",
         gains={"vocal": 2.0, "piano": -3.0, "bass": -1.0, "drums": -1.0, "synth": -5.0},
         sections=[sec("intro", 2, "A", drums="four_floor", bass="root_eighths", synth=True),
                   sec("verse", 8, "A", piano="comping", bass="syncopated", drums="four_floor", vocal=SC, synth=True),
                   sec("pre", 2, "B", piano="block", bass="root_eighths", drums="pop", vocal=SC),
                   sec("chorus", 8, "B", piano="octave_bass", bass="root_fifth_octave", drums="four_floor", vocal=AR, synth=True),
                   sec("break", 2, "A", piano="comping", drums="sparse", synth=True),
                   sec("chorus2", 6, "B", piano="octave_bass", bass="root_fifth_octave", drums="rock", vocal=AR, synth=True)]),
    dict(id="05_instrumental", brief="Instrumental: piano+bass+drums+synth, no vocal", key=0, mode="minor", target_s=57, profile="pop_clean",
         singer=None, piano="vcsl_keys_grand_k", bass="blb_pluck_center", drums="stargate_drums", synth_role="lead",
         gains={"piano": -1.0, "bass": -2.0, "drums": -2.0, "synth": -3.0},
         sections=[sec("intro", 4, "A", piano="arpeggio", drums="sparse"), sec("A", 8, "A", piano="comping", bass="walking", drums="pop", synth=True),
                   sec("B", 8, "B", piano="octave_bass", bass="root_fifth_octave", drums="rock", synth=True),
                   sec("A2", 8, "A", piano="broken", bass="walking", drums="pop", synth=True), sec("outro", 2, "A", piano="ballad", bass="root_whole")]),
    dict(id="06_sparse", brief="Sparse: vocal+piano (+very light pad)", key=3, mode="major", target_s=52, profile="dry_rehearsal",
         singer="female9", piano="vcsl_keys_steinway_b", bass=None, drums=None, synth_role="pad",
         gains={"vocal": 2.0, "piano": 0.0, "synth": -9.0},
         sections=[sec("intro", 2, "A", piano="ballad"), sec("verse", 6, "A", piano="broken", vocal=L), sec("verse2", 6, "B", piano="ballad", vocal=L, synth=True),
                   sec("outro", 2, "A", piano="ballad")]),
    dict(id="07_dense", brief="Dense mix: every stem active throughout", key=10, mode="minor", target_s=55, profile="rock_dense",
         singer="male11", piano="vcsl_keys_upright_knight", bass="sneakybass_pluck", drums="vcsl_drums", synth_role="pluck",
         gains={"vocal": 1.0, "piano": -2.0, "bass": -2.0, "drums": -1.0, "synth": -4.0},
         sections=[sec("A", 8, "A", piano="comping", bass="root_eighths", drums="rock", vocal=SC, synth=True),
                   sec("B", 8, "B", piano="octave_bass", bass="syncopated", drums="rock", vocal=AR, synth=True),
                   sec("A2", 8, "A", piano="comping", bass="walking", drums="pop", vocal=SC, synth=True),
                   sec("B2", 6, "B", piano="octave_bass", bass="root_fifth_octave", drums="rock", vocal=AR, synth=True)]),
    dict(id="08_dynamic_build", brief="Sparse -> full band build", key=7, mode="minor", target_s=57, profile="pop_clean",
         singer="female9", piano="vcsl_keys_grand_k", bass="blb_pluck_center", drums="vcsl_drums", synth_role="pad",
         gains={"vocal": 1.5, "piano": -1.0, "bass": -2.0, "drums": -2.0, "synth": -6.0},
         sections=[sec("intro", 4, "A", piano="ballad"), sec("verse", 6, "A", piano="broken", vocal=L),
                   sec("pre", 2, "B", piano="comping", bass="root_whole", vocal=SC, synth=True),
                   sec("chorus", 8, "B", piano="block", bass="root_fifth_octave", drums="pop", vocal=AR, synth=True),
                   sec("chorus2", 8, "B", piano="octave_bass", bass="root_eighths", drums="rock", vocal=AR, synth=True),
                   sec("outro", 2, "A", piano="ballad", bass="root_whole", synth=True)]),
]


def lufs(x, sr):
    """BS.1770-style integrated loudness (own implementation; K-weighting biquads from the standard's analog prototype)."""
    def shelf(fs):
        f0, G, Q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
        K = np.tan(np.pi * f0 / fs); Vh = 10 ** (G / 20); Vb = Vh ** 0.4996667741545416; a0 = 1 + K / Q + K * K
        return [(Vh + Vb * K / Q + K * K) / a0, 2 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0], [1, 2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0]
    def hp(fs):
        f0, Q = 38.13547087602444, 0.5003270373238773
        K = np.tan(np.pi * f0 / fs); a0 = 1 + K / Q + K * K
        return [1, -2, 1], [1, 2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0]
    y = [lfilter(*hp(sr), lfilter(*shelf(sr), c.astype(np.float64))) for c in x]
    n, hop = int(0.4 * sr), int(0.1 * sr)
    blocks = np.array([[np.mean(c[i:i + n] ** 2) for i in range(0, len(c) - n + 1, hop)] for c in y]).sum(0)
    if blocks.size == 0:
        return float("nan")
    l = -0.691 + 10 * np.log10(np.maximum(blocks, 1e-12))
    g = blocks[l > -70]
    if g.size == 0:
        return float("-inf")
    rel = -0.691 + 10 * np.log10(g.mean()) - 10
    g = blocks[l > max(rel, -70)]
    return float(-0.691 + 10 * np.log10(g.mean())) if g.size else float("-inf")


def db(x):
    return float(20 * np.log10(max(x, 1e-9)))


def build(f: Factory, idx: int, song: dict) -> tuple[SceneSpec, dict]:
    cfg = f.cfg
    seeds = derive_seeds(cfg["master_seed"], 20_000 + idx, "listening_long")
    total_bars = sum(s["bars"] for s in song["sections"])
    bpm = int(round(total_bars * 240.0 / (song["target_s"] - TAIL_S)))
    assert 66 <= bpm <= 150, (song["id"], bpm)
    bar_s = 240.0 / bpm
    parts_all = {p for s in song["sections"] for p in s["parts"]}
    comps = {}  # one chord progression per (prog letter, bars): repeated sections share harmony
    events, t, plan, perf_meta = [], 0.0, [], {}
    vocal_segs = []
    rv = make_rng(seeds["instrument"] ^ 0x5EED)
    index, sing_pool = f.vocal_index, None
    if song["singer"]:
        assert index["singer_split"][song["singer"]] == "val", "listening singers must not come from train"
        sing_pool = [c for c in index["clips"] if c["singer"] == song["singer"]]
    swing = float(make_rng(seeds["performance"]).uniform(0, .2))
    for si, s in enumerate(song["sections"]):
        dur = s["bars"] * bar_s
        key = (s["prog"], s["bars"])
        if key not in comps:
            comps[key] = composition.compose(dur, sub_rng(seeds["composition"], *key), (66, 150),
                                             fixed={"bpm": bpm, "key_root": song["key"], "mode": song["mode"], "n_bars": s["bars"]})
        comp = dict(comps[key], density={"intro": .35, "verse": .55, "verse2": .55, "pre": .6, "chorus": .85, "chorus2": 1.0, "outro": .3,
                                         "break": .25}.get(s["name"], .8))
        sec_meta = {}
        for stem, p in s["parts"].items():
            if stem == "vocal":
                continue
            r = sub_rng(seeds["performance"], stem, s["prog"], str(p), s["bars"])  # same style for same prog+pattern
            if stem == "piano":
                ev, m = performance.piano(comp, dur, r, pattern=p)
            elif stem == "bass":
                ev, m = performance.bass(comp, dur, r, pattern=p)
            elif stem == "drums":
                ev, m = performance.drums(comp, dur, r, groove=p, swing=swing)
            else:
                ev, m = performance.synth(comp, dur, r, role=song["synth_role"])
            for e in ev:
                e.start += t
                e.end += t
            events += ev
            sec_meta[stem] = m
        if "vocal" in s["parts"]:
            cats = s["parts"]["vocal"]
            pool = [c for c in sing_pool if c["category"] in cats]
            tt, end = t + 0.4, t + dur - 0.2
            while tt < end - 1.0:
                c = pool[rv.randint(len(pool))]
                ln = float(min(c["duration_s"], end - tt))
                dbl = {"delay_ms": float(rv.uniform(12, 24)), "gain_db": float(rv.uniform(-9, -6)), "pan": float(rv.uniform(.3, .7))} \
                    if s["name"].startswith("chorus") else None
                vocal_segs.append({"clip_id": c["clip_id"], "singer": c["singer"], "category": c["category"], "asset_id": index["asset_id"],
                                   "crop_start_s": 0.0, "place_start_s": float(tt), "len_s": ln, "silence": [], "double": dbl})
                tt += ln + float(rv.uniform(0.3, 1.0))
        plan.append({"section": s["name"], "start_s": round(t, 3), "end_s": round(t + dur, 3), "bars": s["bars"], "chords": s["prog"],
                     "stems": sorted(s["parts"]), "patterns": {k: v for k, v in s["parts"].items() if isinstance(v, str)}, "performance": sec_meta})
        t += dur
    n = int(round((t + TAIL_S) * f.sr))
    ri = make_rng(seeds["instrument"])
    renderers = {}
    for stem in ("piano", "bass", "drums"):
        if stem in parts_all:
            renderers[stem] = {"kind": "sample", "instrument_id": song[stem]}
    if "synth" in parts_all:
        fam = song["synth_role"]
        renderers["synth"] = {"kind": "synth", "patch": random_patch(fam, ri)}
    active = sorted((set(renderers) | ({"vocal"} if vocal_segs else set())))
    assets = {A.INTERNAL_ASSET_ID} | {f.instruments[r["instrument_id"]].asset_id for r in renderers.values() if r["kind"] == "sample"}
    vocal = None
    if vocal_segs:
        vocal = {"singer": song["singer"], "asset_id": index["asset_id"], "clip_id": vocal_segs[0]["clip_id"], "category": "mixed",
                 "segments": vocal_segs}
        assets.add(index["asset_id"])
    rf = make_rng(seeds["fx"])
    fx = {s_: random_chain(s_, song["profile"], rf) for s_ in active}
    mix = {"stem_gain_db": {k: v for k, v in song["gains"].items() if k in active}, "target_rms_db": -18.0, "peak_limit": cfg["mix"]["peak_limit"],
           "stem_ref_rms_db": cfg["mix"]["stem_ref_rms_db"]}
    comp0 = comps[next(iter(comps))]
    ev_rows = [e.to_list() for e in sorted(events, key=lambda e: (e.start, e.instrument, e.pitch))]
    spec = SceneSpec(
        scene_id=f"long_{song['id']}", split="val", composition_family_id=hash_obj({"song": song["id"]})[:12], duration_samples=n,
        sample_rate=f.sr, seeds=seeds, scene_type="long_listening", profile=song["profile"],
        composition={"bpm": bpm, "key_root": song["key"], "mode": song["mode"], "section_type": "song", "sections": plan,
                     "progressions": {f"{k[0]}x{k[1]}": [(c["degree"], c["quality"] + c["ext"], c["start_beat"], c["dur_beats"]) for c in v["chords"]]
                                      for k, v in comps.items()}, "rules_version": composition.RULES_VERSION},
        active_stems=active, note_events=ev_rows, renderers=renderers, fx=fx, mix=mix, vocal=vocal, assets=sorted(assets),
        generator_version="df0.1+long_listening")
    return spec, plan


def main(out="data/factory/listening_long"):
    out = Path(out)
    f = Factory.from_yaml(REPO / "configs/data_factory/v0.yaml", REPO)
    index = []
    for i, song in enumerate(SONGS):
        spec, plan = build(f, i, song)
        A.gate(f.records, spec.assets, "PRODUCTION_TRAINING")
        r = f.render(spec)
        qc = qc_scene(r["mix"], r["atomic"], spec.active_stems, spec.sample_rate, spec.duration_samples)
        assert qc.passed, (song["id"], qc.failures)
        d = out / song["id"]
        write_wav(d / "mix.wav", r["mix"], spec.sample_rate)
        for s in ATOMIC_STEMS:  # all five v0 atomic stems always written (inactive = exact zeros)
            write_wav(d / f"{s}.wav", r["atomic"][s], spec.sample_rate)
        for k, v in build_targets(r["atomic"], "2stem_v1").items():
            write_wav(d / f"target_{k}.wav", v, spec.sample_rate)
        sr = spec.sample_rate
        inst = sum(r["atomic"][s].astype(np.float64) for s in ATOMIC_STEMS if s != "vocal")
        stems = {s: {"active": s in spec.active_stems, "active_rms_dbfs": round(db(active_rms(r["atomic"][s])), 2) if s in spec.active_stems else None,
                     "peak_dbfs": round(db(float(np.abs(r["atomic"][s]).max())), 2) if s in spec.active_stems else None} for s in ATOMIC_STEMS}
        voc = db(active_rms(r["atomic"]["vocal"])) - db(active_rms(inst.astype(np.float32))) if "vocal" in spec.active_stems else None
        ren = {k: (v.get("instrument_id") or v["kind"]) for k, v in spec.renderers.items()}
        sy = spec.renderers.get("synth")
        meta = {"scene_id": spec.scene_id, "dataset_usage": "LISTENING_EVALUATION", "training_use": False, "brief": song["brief"],
                "duration_s": round(spec.duration_samples / sr, 2), "bpm": spec.composition["bpm"],
                "key": f"{NOTE[song['key']]} {song['mode']}", "profile": song["profile"], "sections": plan,
                "vocal_singer": song["singer"], "vocal_singer_split": f.vocal_index["singer_split"].get(song["singer"]) if song["singer"] else None,
                "vocal_phrases": len(spec.vocal["segments"]) if spec.vocal else 0,
                "piano_instrument": ren.get("piano"), "bass_instrument": ren.get("bass"), "drum_kit": ren.get("drums"),
                "synth_patch": sy and {"family": song["synth_role"], "label": label_patch(sy["patch"])}, "fx": spec.fx,
                "stems": stems, "vocal_to_instrumental_active_rms_db": None if voc is None else round(voc, 2),
                "mix": {"rms_dbfs": round(db(float(np.sqrt(np.mean(r["mix"].astype(np.float64) ** 2)))), 2),
                        "peak_dbfs": round(db(float(np.abs(r["mix"]).max())), 2), "lufs_bs1770_own_impl": round(lufs(r["mix"], sr), 2),
                        "mix_sum_max_abs_err": qc.stats["mix_sum_max_abs_err"]},
                "seeds": spec.seeds, "spec_hash": spec.hash(), "assets": spec.assets, "generator_version": spec.generator_version,
                "rules": {"composition": composition.RULES_VERSION, "performance": performance.RULES_VERSION}}
        prov = {"assets": {a: {k: v for k, v in f.records[a].items() if k not in ("notes", "packet_ref", "root")} for a in spec.assets},
                "usage_checked": "PRODUCTION_TRAINING"}
        (d / "metadata.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        (d / "provenance.json").write_text(json.dumps(prov, indent=1), encoding="utf-8")
        (d / "spec.json").write_text(json.dumps(spec.to_dict()), encoding="utf-8")
        index.append({k: meta[k] for k in ("scene_id", "brief", "duration_s", "bpm", "key", "profile", "vocal_singer", "piano_instrument",
                                           "bass_instrument", "drum_kit", "synth_patch", "vocal_to_instrumental_active_rms_db", "stems", "mix", "seeds")}
                     | {"sections": [(p["section"], p["start_s"], p["end_s"], p["stems"]) for p in plan]})
        print(song["id"], meta["duration_s"], "s", meta["bpm"], "bpm", meta["key"], "| v/i", meta["vocal_to_instrumental_active_rms_db"],
              "| lufs", meta["mix"]["lufs_bs1770_own_impl"], "| err", qc.stats["mix_sum_max_abs_err"])
    (out / "INDEX.json").write_text(json.dumps({"dataset_usage": "LISTENING_EVALUATION", "scenes": index}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:2])
