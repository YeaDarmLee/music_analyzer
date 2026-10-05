"""Protocol-only subprocess fixture. Never used by production CLI."""
import argparse
import time
from pathlib import Path

import numpy as np

from music_analyzer.audio import RATE, write_raw_streaming
from music_analyzer.common import read_json, write_json, sha256_file
from music_analyzer.job_service import alive

parser = argparse.ArgumentParser()
parser.add_argument("--request", type=Path, required=True)
request_path = parser.parse_args().request
request = read_json(request_path)
root, attempt = Path(request["data_root"]), Path(request["attempt_dir"])
job = read_json(attempt.parents[1] / "job.json")
mode = read_json(root / "fake-mode.json")["mode"]
telemetry = attempt / "worker.json"
write_json(telemetry, {"state": "SEPARATING", "progress": {"completed": 0, "total": 1}})
if mode in ("slow", "stuck"):
    while True:
        if mode == "slow" and ((attempt.parents[1] / "cancel.request").exists() or not alive(request["owner"])):
            write_json(telemetry, {"state": "CANCELLED"})
            raise SystemExit(130)
        time.sleep(.05)
if mode == "error" or mode == "oom_twice" or (mode == "oom_once" and request["preset_name"] == "baseline"):
    partial = attempt / "result.partial"
    partial.mkdir()
    (partial / "unused").write_text("partial")
    oom = mode.startswith("oom")
    write_json(telemetry, {"state": "FAILED", "error": {
        "code": "CUDA_OOM" if oom else "DECODE_ERROR", "message": "test injection"}})
    raise SystemExit(12 if oom else 1)
partial = attempt / "result.partial"
partial.mkdir()
stems = []
for family in ("drums", "bass", "other", "vocals"):
    path = partial / "stems" / (family + ".wav")
    properties = write_raw_streaming(path, np.zeros((job["num_frames"], 2), dtype=np.float32))
    stems.append({"family": family, "path": "stems/" + family + ".wav",
                  "sha256": sha256_file(path), **properties})
manifest = {"kind": "separation_result", "schema_version": "1.0", "status": "succeeded",
            "job_id": job["job_id"], "asset_id": job["asset_id"],
            "source_sha256": job["canonical_sha256"], "timeline": {
                "sample_rate": RATE, "channels": 2, "num_frames": job["num_frames"], "origin_sec": 0},
            "stems": stems}
if mode == "invalid":
    manifest["stems"].pop()
write_json(partial / "manifest.json", manifest)
write_json(telemetry, {"state": "READY_TO_PUBLISH", "progress": {"completed": 1, "total": 1}})
