"""Run commercial_13 on license-clean synthetic cases and score it with the same ground_truth.evaluate() as final_11.

Case folders are copied from data/pad-eval/cases-v16 into data/commercial-eval/pad/<case> so the final_11 baseline
reports stay untouched. Baseline = the existing v16 report.json of the same case (staged-context-pads-v16).
usage: run-commercial-eval.py pad00-mix pad01-mix ...
"""
import os as _os; _os.environ.setdefault("MUSIC_KEEP_INTERMEDIATES", "1")  # dev/benchmark scripts read intermediates
import os, shutil, sys, time
from pathlib import Path
from music_analyzer.common import project_root, read_json, write_json, sha256_file
from music_analyzer.ground_truth import evaluate
from music_analyzer.registry import paths
from music_analyzer.commercial_pipeline import MODELS as COMMERCIAL_MODELS
MODELS = COMMERCIAL_MODELS if os.environ.get("EVAL_MODEL", "commercial_13") == "commercial_13" else ("melband_roformer_kj", "bs_roformer_6s", "bs_karaoke", "bs_roformer_mega5", "bs_roformer_mega7")
from music_analyzer.legal import RIGHTS_CONFIRMATION_VERSION
from music_analyzer.web_server import WebLibrary

base = project_root()
MODEL = os.environ.get("EVAL_MODEL", "commercial_13")   # final_11 re-runs the baseline in the same session for timing/VRAM parity
src_root = base / "data/pad-eval/cases-v16"; dst_root = base / ("data/commercial-eval/pad" if MODEL == "commercial_13" else "data/commercial-eval/pad-baseline")
KEEP = ("case.json", "prepared.json", "evaluation-references")
for name in sys.argv[1:]:
    folder = dst_root / name
    if (folder / "report.json").exists():
        continue
    folder.mkdir(parents=True, exist_ok=True)
    for item in KEEP:
        s, d = src_root / name / item, folder / item
        if not d.exists():
            shutil.copytree(s, d) if s.is_dir() else shutil.copyfile(s, d)
    prepared = read_json(folder / "prepared.json")
    root = folder / "library"
    for model_id in MODELS:
        checkpoint, registration = paths(base / "data/separation", model_id)
        target = root / "models" / model_id; target.mkdir(parents=True, exist_ok=True)
        if not (target / checkpoint.name).exists():
            os.link(checkpoint, target / checkpoint.name)
        write_json(target / "registration.json", read_json(registration))
    if (folder / "run.json").exists():  # resume: pipeline already finished, only (re)score
        previous = read_json(folder / "run.json"); record = read_json(Path(previous["root"]) / "web" / previous["id"] / "record.json")
        if record["state"] == "SUCCEEDED":
            evaluate(folder, Path(previous["root"]), record); continue
    library = WebLibrary(root)
    try:
        clip = Path(prepared["input"])
        assert sha256_file(clip) == prepared["input_sha256"], "mixture changed"
        with clip.open("rb") as stream:
            public = library.create(clip.name, MODEL, stream, clip.stat().st_size, rights=RIGHTS_CONFIRMATION_VERSION)
        write_json(folder / "run.json", {"id": public["id"], "root": str(root.resolve())})
        started = time.monotonic(); stage = None
        while True:
            row = library.get(public["id"])
            if row["stage"] != stage:
                stage = row["stage"]; print(name, stage, flush=True)
            if row["state"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
                break
            if time.monotonic() - started > 1500:
                library.stopping.set(); raise TimeoutError("exceeded 25 minutes")
            time.sleep(.5)
        if row["state"] != "SUCCEEDED":
            raise RuntimeError(row.get("error", row["state"]))
    finally:
        library.executor.shutdown(wait=True)
    evaluate(folder, root, row)
print("COMMERCIAL EVAL RUN DONE", flush=True)
