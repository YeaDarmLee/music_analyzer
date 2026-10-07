"""commercial_13 edge-input smoke: mono 48 kHz, silence, very short, long (90 s), stereo 44.1 kHz. Checks success + partition integrity.

Inputs are built from the license-clean synthetic pad-eval mix. Output: docs/COMMERCIAL_CLEAN_SMOKE_RESULTS.json
"""
import os, time
from pathlib import Path
import numpy as np, soundfile as sf
from scipy.signal import resample_poly
from music_analyzer.common import project_root, read_json, write_json
from music_analyzer.commercial_eval import read_audio, partition_stats
from music_analyzer.commercial_pipeline import MODELS
from music_analyzer.legal import RIGHTS_CONFIRMATION_VERSION
from music_analyzer.registry import paths
from music_analyzer.web_server import WebLibrary

base = project_root(); work = base / "data/commercial-eval/smoke"; work.mkdir(parents=True, exist_ok=True)
mix, _ = sf.read(base / "data/pad-eval/cases/pad00-mix/mix.wav", dtype="float32", always_2d=True)
cases = {
    "stereo44k_5s": (mix[:44100 * 5], 44100),
    "mono48k_5s": (resample_poly(mix[:44100 * 5].mean(axis=1), 160, 147).astype(np.float32)[:, None], 48000),
    "short_0.5s": (mix[:22050], 44100),
    "silence_3s": (np.zeros((44100 * 3, 2), np.float32), 44100),
    "long_90s": (np.concatenate([mix] * 6), 44100),
}
root = work / "library"
for model_id in MODELS:
    checkpoint, registration = paths(base / "data/separation", model_id)
    target = root / "models" / model_id; target.mkdir(parents=True, exist_ok=True)
    if not (target / checkpoint.name).exists():
        os.link(checkpoint, target / checkpoint.name)
    write_json(target / "registration.json", read_json(registration))
library = WebLibrary(root); results = []
try:
    for name, (audio, rate) in cases.items():
        path = work / f"{name}.wav"; sf.write(path, audio, rate, subtype="PCM_16")
        started = time.monotonic()
        with path.open("rb") as stream:
            public = library.create(path.name, "commercial_13", stream, path.stat().st_size, rights=RIGHTS_CONFIRMATION_VERSION)
        while True:
            row = library.get(public["id"])
            if row["state"] in ("SUCCEEDED", "FAILED", "CANCELLED") or time.monotonic() - started > 1500:
                break
            time.sleep(.5)
        item = {"case": name, "state": row["state"], "error": row.get("error"), "seconds": round(time.monotonic() - started, 1), "stems": len(row.get("tracks", []))}
        if row["state"] == "SUCCEEDED":
            original = read_audio(library.track_path(row, "original"))
            item["partition"] = partition_stats(original, [read_audio(library.track_path(row, t["family"])) for t in row["tracks"]])
        results.append(item); print(item, flush=True)
finally:
    library.executor.shutdown(wait=True)
write_json(base / "docs/COMMERCIAL_CLEAN_SMOKE_RESULTS.json", results)
print("SMOKE DONE", flush=True)
