"""End-to-end lifecycle of one small production analysis (MUSIC_KEEP_INTERMEDIATES=0):
analysis -> cleanup -> playback preview -> single-WAV download -> full ZIP -> ZIP temp removed -> analysis deleted -> nothing left.

usage: lifecycle-e2e.py [preset]   (default commercial_6, 5 s clip of separation/tests/fixtures/synthetic-mix-15s.wav)
"""
import os, shutil, sys, time, zipfile
from pathlib import Path
import numpy as np, soundfile as sf
os.environ["MUSIC_KEEP_INTERMEDIATES"] = "0"
from music_analyzer import lifecycle
from music_analyzer.common import project_root, read_json, write_json
from music_analyzer.commercial_eval import read_audio
from music_analyzer.commercial_pipeline import models_for
from music_analyzer.legal import RIGHTS_CONFIRMATION_VERSION
from music_analyzer.registry import paths
from music_analyzer.web_server import WebLibrary

base = project_root(); preset = sys.argv[1] if len(sys.argv) > 1 else "commercial_6"
root = base / "data/e2e-lifecycle"; shutil.rmtree(root, ignore_errors=True)
for model_id in models_for(preset):
    checkpoint, registration = paths(base / "data/separation", model_id)
    target = root / "models" / model_id; target.mkdir(parents=True, exist_ok=True)
    os.link(checkpoint, target / checkpoint.name)
    write_json(target / "registration.json", read_json(registration))

clip = root / "clip.wav"; sf.write(clip, read_audio(base / "separation/tests/fixtures/synthetic-mix-15s.wav")[: 44100 * 5], 44100, subtype="PCM_16")
size_of = lambda p: sum(f.stat().st_size for f in Path(p).rglob("*") if f.is_file()) if Path(p).exists() else 0
steps = {}
library = WebLibrary(root)
try:
    with clip.open("rb") as stream:
        public = library.create(clip.name, preset, stream, clip.stat().st_size, rights=RIGHTS_CONFIRMATION_VERSION)
    identifier = public["id"]
    while True:
        row = library.get(identifier)
        if row["state"] in ("SUCCEEDED", "FAILED") and (row["state"] == "FAILED" or "storage" in row):
            break
        time.sleep(.3)
    assert row["state"] == "SUCCEEDED", row.get("error")
    steps["analysis"] = {"state": row["state"], "tracks": len(row["tracks"]), "cleanup": row["storage"]["mode"], "freed_mb": round(row["storage"]["freed_bytes"] / 2**20, 1)}
    violations = lifecycle.contract_violations(root, identifier)
    assert violations == [], violations
    steps["cleanup"] = {"contract_violations": 0, "web_mb": round(size_of(root / "web") / 2**20, 1), "jobs_mb": round(size_of(root / "jobs") / 2**20, 2),
                        "inputs_mb": round(size_of(root / "inputs") / 2**20, 2), "files_in_analysis": sorted(p.relative_to(root / "web" / identifier).as_posix() for p in (root / "web" / identifier).rglob("*") if p.is_file())}
    family = row["tracks"][0]["family"]
    preview = library.preview(row, family)
    data, rate = sf.read(preview, dtype="float32"); assert rate == 44100 and np.isfinite(data).all() and len(data) > 44100
    window = library.audio_window(row, family, 0, 44100) if hasattr(library, "audio_window") else None
    steps["playback"] = {"preview": preview.name, "seconds": round(len(data) / rate, 2), "window_ok": window is not None}
    wav = library.track_path(row, family)
    assert sf.info(wav).frames == len(read_audio(library.track_path(row, "original")))
    steps["wav_download"] = {"family": family, "bytes": wav.stat().st_size}
    archive = library.archive(row)
    with zipfile.ZipFile(archive) as z:
        names = sorted(z.namelist()); assert z.testzip() is None
    expected = sorted([t["family"] + ".wav" for t in row["tracks"]] + ["manifest.json"]); assert names == expected, names
    steps["zip"] = {"entries": len(names), "mb": round(archive.stat().st_size / 2**20, 1), "temp_exists_before_discard": archive.exists()}
    library.discard_archive(archive)
    steps["zip"]["temp_exists_after_discard"] = archive.exists(); assert not archive.exists()
    assert not list((root / "web/archives").glob("*"))
    library.delete(identifier)
    leftovers = [p.relative_to(root).as_posix() for sub in ("web", "jobs", "inputs") for p in (root / sub).rglob("*") if p.is_file()] if (root / "web").exists() else []
    steps["delete"] = {"leftover_files": leftovers}
    assert leftovers == [], leftovers
finally:
    library.executor.shutdown(wait=True)
    lifecycle.discard_benchmark_audio(root, settings={})
    if not os.environ.get("KEEP_TEST_OUTPUT"):
        shutil.rmtree(root, ignore_errors=True)  # test analyses are not kept unless KEEP_TEST_OUTPUT=1
import json
print(json.dumps(steps, ensure_ascii=False, indent=1))
print("LIFECYCLE E2E OK")
