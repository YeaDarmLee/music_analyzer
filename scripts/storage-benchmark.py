"""Storage benchmark: MUSIC_KEEP_INTERMEDIATES=1 (before) vs 0 (after) for commercial_2/6/13 on a 90 s clip.

Measures peak scratch (sampled every 0.5 s while the analysis runs), persistent size/file count after success, cleanup duration,
temporary ZIP size, and checks the delivered stems still validate (partition sum, preview, archive).
usage: storage-benchmark.py [preset ...]   -> docs/OUTPUT_STORAGE_BENCHMARK.json
"""
import os, sys, threading, time
from pathlib import Path
import numpy as np, soundfile as sf
from music_analyzer.common import project_root, read_json, write_json
from music_analyzer.commercial_eval import read_audio, partition_stats
from music_analyzer.commercial_pipeline import models_for
from music_analyzer.legal import RIGHTS_CONFIRMATION_VERSION
from music_analyzer.registry import paths

base = project_root(); work = base / "data/commercial-eval/storage"; work.mkdir(parents=True, exist_ok=True)
OUT = base / "docs/OUTPUT_STORAGE_BENCHMARK.json"
presets = sys.argv[1:] or ["commercial_2", "commercial_6", "commercial_13"]
results = read_json(OUT) if OUT.exists() else {}
mix, _ = sf.read(base / "data/pad-eval/cases-v16/pad00-mix/mix.wav", dtype="float32", always_2d=True) if (base / "data/pad-eval/cases-v16/pad00-mix/mix.wav").exists() else (None, None)
if mix is None:
    from music_analyzer.commercial_eval import read_audio as _r
    prepared = read_json(base / "data/pad-eval/cases-v16/pad00-mix/prepared.json")
    mix = _r(prepared["input"])
clip = work / "clip90.wav"
sf.write(clip, np.concatenate([mix] * 6)[: 44100 * 90], 44100, subtype="PCM_16")


def scan(root):
    size = files = 0
    for sub in ("web", "jobs", "inputs", "pipelines"):
        for dirpath, _, names in os.walk(root / sub):
            for name in names:
                try:
                    size += os.path.getsize(os.path.join(dirpath, name)); files += 1
                except OSError:
                    pass
    return size, files


def breakdown(root):
    out = {}
    for sub in ("web", "jobs", "inputs"):
        out[sub] = round(sum(os.path.getsize(os.path.join(d, n)) for d, _, ns in os.walk(root / sub) for n in ns) / 2 ** 20, 1)
    return out


for preset in presets:
    for keep in ("1", "0"):
        os.environ["MUSIC_KEEP_INTERMEDIATES"] = keep
        from music_analyzer.web_server import WebLibrary
        root = work / f"{preset}-keep{keep}"
        if (root / "done.json").exists():
            continue
        import shutil
        shutil.rmtree(root, ignore_errors=True)
        for model_id in models_for(preset):
            checkpoint, registration = paths(base / "data/separation", model_id)
            target = root / "models" / model_id; target.mkdir(parents=True, exist_ok=True)
            os.link(checkpoint, target / checkpoint.name)
            write_json(target / "registration.json", read_json(registration))
        library = WebLibrary(root); peak = [0]; stop = threading.Event()
        def poll():
            while not stop.is_set():
                peak[0] = max(peak[0], scan(root)[0]); time.sleep(.5)
        thread = threading.Thread(target=poll, daemon=True); thread.start()
        started = time.monotonic()
        try:
            with clip.open("rb") as stream:
                public = library.create(clip.name, preset, stream, clip.stat().st_size, rights=RIGHTS_CONFIRMATION_VERSION)
            while True:
                row = library.get(public["id"])
                if row["state"] in ("SUCCEEDED", "FAILED", "CANCELLED") and (keep == "1" or "storage" in row or row["state"] != "SUCCEEDED"):
                    break
                if time.monotonic() - started > 1200: raise TimeoutError("analysis or cleanup did not finish")
                time.sleep(.3)
        finally:
            library.executor.shutdown(wait=True); stop.set(); thread.join()
        seconds = time.monotonic() - started
        assert row["state"] == "SUCCEEDED", row.get("error")
        size, files = scan(root)
        final_bytes = sum(Path(library.track_path(row, t["family"])).stat().st_size for t in row["tracks"])
        original = read_audio(library.track_path(row, "original"))
        stats = partition_stats(original, [read_audio(library.track_path(row, t["family"])) for t in row["tracks"]])
        preview = library.preview(row, row["tracks"][0]["family"])
        archive = library.archive(row); zip_mb = archive.stat().st_size / 2 ** 20; library.discard_archive(archive)
        record = {"preset": preset, "keep_intermediates": keep == "1", "seconds": round(seconds, 1), "tracks": len(row["tracks"]),
                  "peak_scratch_mb": round(peak[0] / 2 ** 20, 1), "persistent_mb": round(size / 2 ** 20, 1), "persistent_files": files,
                  "persistent_breakdown_mb": breakdown(root), "final_tracks_mb": round(final_bytes / 2 ** 20, 1),
                  "cleanup": row.get("storage"), "zip_temp_mb": round(zip_mb, 1), "zip_left_after_discard": len(list((root / "web/archives").glob("*"))),
                  "partition_max_abs_error": stats["max_abs_error"], "preview_ok": preview.exists()}
        results[f"{preset}|keep={keep}"] = record
        write_json(OUT, results); write_json(root / "done.json", record); print(record, flush=True)
from music_analyzer.lifecycle import discard_benchmark_audio
discard_benchmark_audio(work)
print("STORAGE BENCH DONE", flush=True)
