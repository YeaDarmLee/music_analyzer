"""Small fixed listening/evaluation pack from the ingested real assets (DF-0 acceptance).
17 scenes: piano x3, bass x3, drums x3, synth x3, vocal+full band x5. Every scene passes the PRODUCTION_TRAINING gate + QC.
usage: python scripts/df_listening_pack.py [out_dir]"""
import dataclasses, json, sys
import numpy as np
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from data_factory.fixed import render_specs  # noqa: E402
from data_factory.scenes import Factory  # noqa: E402
from data_factory.mixer import active_rms  # noqa: E402
from data_factory.schema import ATOMIC_STEMS  # noqa: E402
from data_factory.util import read_wav  # noqa: E402

GROUPS = [("piano", ["piano"], "pack_piano"), ("bass", ["bass"], "pack_bass"), ("drums", ["drums"], "pack_drums"),
          ("synth", ["synth"], "pack_synth"), ("vocal_band", ["vocal", "drums", "bass", "piano", "synth"], "pack_vocal_band")]


def db(x):
    return round(float(20 * np.log10(max(x, 1e-9))), 2)


def diag(d, spec):
    """Per-stem active RMS / peak (dBFS), vocal-to-instrumental ratio, from the written wavs."""
    st, inst = {}, 0
    for k in ATOMIC_STEMS:
        if k in spec.active_stems:
            x = read_wav(d / f"{k}.wav")[0]
            st[k] = {"active_rms_dbfs": db(active_rms(x)), "peak_dbfs": db(float(np.abs(x).max()))}
            if k != "vocal":
                inst = inst + x.astype(np.float64)
    ratio = db(10 ** (st["vocal"]["active_rms_dbfs"] / 20) / max(active_rms(np.asarray(inst, np.float32)), 1e-9)) if "vocal" in st and not np.isscalar(inst) else None
    mix = read_wav(d / "mix.wav")[0]
    return {"stems": st, "vocal_to_instrumental_db": ratio, "mix_rms_dbfs": db(float(np.sqrt(np.mean(mix.astype(np.float64) ** 2)))),
            "mix_peak_dbfs": db(float(np.abs(mix).max()))}


def main(out="data/factory/listening_real"):
    f = Factory.from_yaml(REPO / "configs/data_factory/v0.yaml", REPO)
    specs = []
    for gi, (name, active, stype) in enumerate(GROUPS):
        for k in range(5 if name == "vocal_band" else 3):
            # split 'val' families, index offset keeps the pack disjoint from regular val scene indices
            sp = f.make_spec(10_000 + gi * 10 + k, "val", force={"active": active, "sample": True, "scene_type": stype})
            specs.append(dataclasses.replace(sp, scene_id=f"{name}_{k + 1}"))
    rep = render_specs(f, specs, out, two_stem_wavs=True)
    index = []
    for s in specs:
        m = json.loads((Path(out) / s.scene_id / "metadata.json").read_text()) if s.scene_id in rep["scenes"] else None
        index.append({"scene": s.scene_id, "seconds": round(s.duration_samples / 44100, 1), "profile": s.profile,
                      "active": s.active_stems, "renderers": m and m["renderers"], "vocal": m and m["vocal"],
                      "composition": m and m["composition"], "qc_peak": m and round(m["qc"]["peak"], 3),
                      "piano_pedal_mode": s.composition["performance"].get("piano", {}).get("pedal_mode"),
                      "synth_label": (s.renderers.get("synth") or {}).get("patch", {}).get("label"),
                      "seed": s.seeds["mix"], **(diag(Path(out) / s.scene_id, s) if m else {})})
    (Path(out) / "INDEX.json").write_text(json.dumps({"failed": rep["failed"], "scenes": index}, indent=1))
    print(json.dumps({"ok": len(rep["scenes"]), "failed": rep["failed"]}, indent=1))
    for r in index:
        print(r["scene"], r["seconds"], "s", r["profile"], r["active"], {k: (v["instrument_id"] or v["kind"]) for k, v in (r["renderers"] or {}).items()},
              (r["vocal"] or {}).get("singer"), (r["vocal"] or {}).get("category"))


if __name__ == "__main__":
    main(*sys.argv[1:2])
