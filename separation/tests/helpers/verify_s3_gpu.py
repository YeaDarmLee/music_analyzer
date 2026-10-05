from pathlib import Path
import json
import numpy as np
import soundfile as sf
from music_analyzer.audio import RATE
from music_analyzer.common import project_root, write_json, read_json
from music_analyzer.ingest import ingest_file
from music_analyzer.job_service import JobService, alive
from music_analyzer.job_contracts import verify_result

root = project_root() / "data/separation"
service = JobService(root)
results = []
for name, audio in (
        ("silence", np.zeros((RATE * 2, 2), np.float32)),
        ("antiphase", np.column_stack((.1 * np.sin(2 * np.pi * 220 * np.arange(RATE * 4) / RATE),
                                      -.1 * np.sin(2 * np.pi * 220 * np.arange(RATE * 4) / RATE))).astype(np.float32))):
    path = root / "s3-validation" / (name + ".wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio, RATE, subtype="FLOAT")
    asset = ingest_file(path, root)
    job = service.run(asset.name)
    assert job["state"] == "SUCCEEDED", job
    manifest = verify_result(root / "jobs" / job["job_id"] / "result", job)
    if name == "silence":
        assert manifest["inference_performed"] is False
    else:
        assert manifest["normalization"]["basis"] == "channelwise_std_for_cancelling_stereo"
    results.append({"case": name, "job_id": job["job_id"], "state": job["state"]})
cancelled = False
def update(job):
    global cancelled
    if job["state"] == "SEPARATING" and not cancelled:
        cancelled = True
        service.cancel(job["job_id"])
job = service.run("asset_3bc078c970334e599708862126362e40", on_update=update)
assert job["state"] == "CANCELLED", job
assert not alive(job["attempts"][0]["worker"])
assert not (root / "jobs" / job["job_id"] / "result").exists()
results.append({"case": "actual_gpu_cancel", "job_id": job["job_id"], "state": job["state"]})
job = service.run("asset_3bc078c970334e599708862126362e40")
assert job["state"] == "SUCCEEDED", job
manifest = verify_result(root / "jobs" / job["job_id"] / "result", job)
results.append({"case": "actual_song_baseline", "job_id": job["job_id"], "state": job["state"],
                "timing": manifest["timing"], "memory": manifest["memory"]})
write_json(root / "s3-validation" / "results.json", results)
print(json.dumps(results, ensure_ascii=False, indent=2))
