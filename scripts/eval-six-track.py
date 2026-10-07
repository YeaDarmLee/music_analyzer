"""6-track SDR: basic_6 (dev baseline, bs_6stem_fixed) vs commercial_6 (KJ + Mega53 core4) on the license-clean pad-eval cases.

usage: eval-six-track.py <basic_6|commercial_6> case ...   -> data/commercial-eval/six/<preset>/<case>.json
Targets: piano/guitar/bass/drums = their GT stems; other = strings+brass+synth GT; vocals has no GT (N/A).
"""
import os, sys, time, json
from pathlib import Path
import numpy as np, soundfile as sf
from music_analyzer.common import project_root, read_json, write_json
from music_analyzer.ground_truth import score
from music_analyzer.legal import RIGHTS_CONFIRMATION_VERSION
from music_analyzer.registry import paths
from music_analyzer.web_server import WebLibrary

preset = sys.argv[1]; base = project_root()
MODELS = {"basic_6": ("melband_roformer_kj", "bs_roformer_6s"), "commercial_6": ("melband_roformer_kj", "bs_roformer_core4")}[preset]
OTHER = ("strings", "brass", "synth")
out_dir = base / "data/commercial-eval/six" / preset; out_dir.mkdir(parents=True, exist_ok=True)
for name in sys.argv[2:]:
    if (out_dir / f"{name}.json").exists():
        continue
    case = base / "data/pad-eval/cases-v16" / name; prepared = read_json(case / "prepared.json")
    root = out_dir / "libs" / name
    for model_id in MODELS:
        checkpoint, registration = paths(base / "data/separation", model_id)
        target = root / "models" / model_id; target.mkdir(parents=True, exist_ok=True)
        if not (target / checkpoint.name).exists():
            os.link(checkpoint, target / checkpoint.name)
        write_json(target / "registration.json", read_json(registration))
    library = WebLibrary(root)
    try:
        clip = Path(prepared["input"])
        with clip.open("rb") as stream:
            public = library.create(clip.name, preset, stream, clip.stat().st_size, rights=RIGHTS_CONFIRMATION_VERSION)
        started = time.monotonic()
        while True:
            row = library.get(public["id"])
            if row["state"] in ("SUCCEEDED", "FAILED", "CANCELLED") or time.monotonic() - started > 900:
                break
            time.sleep(.5)
        if row["state"] != "SUCCEEDED":
            raise RuntimeError(row.get("error", row["state"]))
        read = lambda p: sf.read(p, dtype="float32", always_2d=True)[0]
        mixture = read(library.track_path(row, "original"))
        refs = lambda names: sum((read(case / "evaluation-references" / f"{n}.wav") for n in names if (case / "evaluation-references" / f"{n}.wav").exists()), np.zeros_like(mixture))
        outputs = {t["family"]: read(library.track_path(row, t["family"])) for t in row["tracks"]}
        targets = {f: refs([f]) for f in ("piano", "guitar", "bass", "drums")}; targets["other"] = refs(OTHER)
        metrics = {f: score(targets[f], outputs[f], mixture) for f in targets}
        # leakage view: how much of each GT instrument ended up in 'other'
        result = {"case": name, "preset": preset, "seconds": row["processing_seconds"], "stems": sorted(outputs),
                  "metrics": {f: {k: m[k] for k in ("raw_sdr_db", "si_sdr_db", "output_to_mix_db", "reference_absent")} for f, m in metrics.items()},
                  "sum_error": float(np.max(np.abs(sum(outputs.values()).astype(np.float64) - mixture)))}
    finally:
        library.executor.shutdown(wait=True)
    write_json(out_dir / f"{name}.json", result); print(name, "done", flush=True)
print("SIX DONE", flush=True)
