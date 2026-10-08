"""Re-run commercial_6 and commercial_13 on the EXACT listening-package clips (data/listening/raw/<song>/clip.wav) and keep
  raw/<song>/<preset>/<family>.wav       final stems (commercial_13 added; commercial_6 refreshed only if missing)
  raw/<song>/core4raw_<preset>/<family>.wav   the bs_roformer_core4 stage output exactly as the model wrote it (before any post step)
usage: run-listening-extra.py [commercial_6 commercial_13]
"""
import os as _os; _os.environ.setdefault("MUSIC_KEEP_INTERMEDIATES", "1")
import shutil, sys, time
from pathlib import Path
import soundfile as sf
from music_analyzer.common import project_root, read_json, write_json
from music_analyzer.commercial_pipeline import models_for
from music_analyzer.job_contracts import job_folder
from music_analyzer.legal import RIGHTS_CONFIRMATION_VERSION
from music_analyzer.registry import paths
from music_analyzer.web_server import WebLibrary

base = project_root(); out = base / "data/listening"; RATE = 44100
presets = sys.argv[1:] or ["commercial_13", "commercial_6"]
write = lambda dest, p: sf.write(dest, sf.read(p, dtype="float32", always_2d=True)[0], RATE, subtype="FLOAT")
for song in sorted(p.name for p in (out / "raw").iterdir() if p.is_dir()):
    clip = out / "raw" / song / "clip.wav"
    for preset in presets:
        final = out / "raw" / song / preset; core = out / "raw" / song / f"core4raw_{preset}"
        if final.exists() and core.exists():
            continue
        root = out / "libs" / song / preset
        for model_id in models_for(preset):
            checkpoint, registration = paths(base / "data/separation", model_id)
            dest = root / "models" / model_id; dest.mkdir(parents=True, exist_ok=True)
            if not (dest / checkpoint.name).exists():
                _os.link(checkpoint, dest / checkpoint.name)
            write_json(dest / "registration.json", read_json(registration))
        library = WebLibrary(root)
        try:
            with clip.open("rb") as stream:
                public = library.create(clip.name, preset, stream, clip.stat().st_size, rights=RIGHTS_CONFIRMATION_VERSION)
            started = time.monotonic()
            while True:
                row = library.get(public["id"])
                if row["state"] in ("SUCCEEDED", "FAILED", "CANCELLED") or time.monotonic() - started > 2400:
                    break
                time.sleep(1)
            if row["state"] != "SUCCEEDED":
                raise RuntimeError(f"{song}/{preset}: {row.get('error', row['state'])}")
            final.mkdir(parents=True, exist_ok=True); core.mkdir(parents=True, exist_ok=True)
            for t in row["tracks"]:
                write(final / f"{t['family']}.wav", library.track_path(row, t["family"]))
            found = 0
            for job_id in row["job_ids"]:
                job = read_json(job_folder(root, job_id) / "job.json")
                if "core4" in str(job.get("requested_preset")) or job.get("requested_preset") == "instrument_roformer_6s":
                    result = job_folder(root, job_id) / "result"
                    for s in read_json(result / "manifest.json")["stems"]:
                        write(core / f"{s['family']}.wav", result / s["path"]); found += 1
            assert found, f"no core4 stage job among {row['job_ids']}"
            print(song, preset, "done", round(time.monotonic() - started), "s; core4 stems", found, flush=True)
        finally:
            library.executor.shutdown(wait=True)
        shutil.rmtree(root, ignore_errors=True)
print("EXTRA DONE", flush=True)
