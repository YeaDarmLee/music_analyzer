"""Repeat the same short analysis N times in ONE server process and record process/disk/GPU counters after each run.

Production setting (MUSIC_KEEP_INTERMEDIATES=0). Counters: RSS, open handles (Windows) / fds, threads, files and bytes under the library
(excluding models), GPU memory used (device-wide, nvidia-smi; inference runs in a worker subprocess that exits after each job, so a
persistent increase would mean a leaked worker or driver allocation).
usage: resource-leak-check.py [preset] [runs]   -> docs/OUTPUT_LEAK_CHECK.json
"""
import os, subprocess, sys, time
from pathlib import Path
import numpy as np, psutil, soundfile as sf
os.environ["MUSIC_KEEP_INTERMEDIATES"] = "0"
from music_analyzer.common import project_root, read_json, write_json
from music_analyzer.commercial_eval import read_audio
from music_analyzer.commercial_pipeline import models_for
from music_analyzer.legal import RIGHTS_CONFIRMATION_VERSION
from music_analyzer.registry import paths
from music_analyzer.web_server import WebLibrary

base = project_root(); preset = sys.argv[1] if len(sys.argv) > 1 else "commercial_6"; runs = int(sys.argv[2]) if len(sys.argv) > 2 else 30
root = base / f"data/commercial-eval/leak-{preset}"
import shutil; shutil.rmtree(root, ignore_errors=True)
for model_id in models_for(preset):
    checkpoint, registration = paths(base / "data/separation", model_id)
    target = root / "models" / model_id; target.mkdir(parents=True, exist_ok=True)
    os.link(checkpoint, target / checkpoint.name)
    write_json(target / "registration.json", read_json(registration))
prepared = read_json(base / "data/pad-eval/cases-v16/pad00-mix/prepared.json")
clip = root / "clip5.wav"; sf.write(clip, read_audio(prepared["input"])[: 44100 * 5], 44100, subtype="PCM_16")
process = psutil.Process()


def gpu_mb():
    try:
        return int(subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True).split()[0])
    except Exception:
        return None


def snapshot(index):
    size = files = 0
    for sub in ("web", "jobs", "inputs"):
        for d, _, names in os.walk(root / sub):
            for n in names:
                try: size += os.path.getsize(os.path.join(d, n)); files += 1
                except OSError: pass
    return {"run": index, "rss_mb": round(process.memory_info().rss / 2 ** 20, 1),
            "handles": process.num_handles() if hasattr(process, "num_handles") else process.num_fds(),
            "threads": process.num_threads(), "files": files, "disk_mb": round(size / 2 ** 20, 1), "gpu_used_mb": gpu_mb(),
            "child_processes": len(process.children(recursive=True)),
            "partial_or_tmp": sum(1 for p in root.rglob("*") if ".partial" in p.name or p.name.startswith("dl-"))}


library = WebLibrary(root); log = [snapshot(0)]
try:
    for index in range(1, runs + 1):
        with clip.open("rb") as stream:
            public = library.create(clip.name, preset, stream, clip.stat().st_size, rights=RIGHTS_CONFIRMATION_VERSION)
        while True:
            row = library.get(public["id"])
            if row["state"] in ("SUCCEEDED", "FAILED", "CANCELLED") and (row["state"] != "SUCCEEDED" or "storage" in row):
                break
            time.sleep(.2)
        assert row["state"] == "SUCCEEDED", row.get("error")
        archive = library.archive(row); library.discard_archive(archive)   # the download path as well
        library.delete(public["id"]) if index % 2 == 0 else None           # half of the analyses are deleted again
        log.append(snapshot(index)); print(log[-1], flush=True)
finally:
    library.executor.shutdown(wait=True)
log.append({**snapshot(runs + 1), "note": "after executor shutdown"})
write_json(base / f"docs/OUTPUT_LEAK_CHECK_{preset.upper()}.json", log)
from music_analyzer.lifecycle import discard_benchmark_audio
discard_benchmark_audio(root)
print("LEAK CHECK DONE", flush=True)
