from __future__ import annotations

import copy
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from filelock import FileLock

from music_analyzer.audio import RATE, write_raw_streaming
from music_analyzer.common import read_json, write_json
from music_analyzer.ingest import ingest_file
from music_analyzer.job_contracts import JobError, preset, verify_result
from music_analyzer.job_service import JobService, alive, identity

HELPER = Path(__file__).parent / "helpers/fake_worker.py"


@pytest.fixture
def service(tmp_path):
    source = tmp_path / "source.wav"
    sf.write(source, np.zeros((RATE, 2), np.float32), RATE, subtype="FLOAT")
    root = tmp_path / "data"
    asset = ingest_file(source, root).name
    worker = JobService(root, tmp_path / "runtime", [sys.executable, str(HELPER.resolve())],
                        poll_sec=.02, cancel_grace_sec=.15, timeout_sec=20)
    worker.asset = asset
    write_json(root / "fake-mode.json", {"mode": "success"})
    return worker


def mode(service, value):
    write_json(service.root / "fake-mode.json", {"mode": value})


def test_success_and_immutable_result(service):
    job = service.run(service.asset)
    assert job["state"] == "SUCCEEDED"
    folder = service.root / "jobs" / job["job_id"]
    verify_result(folder / "result", job)
    assert service.cancel(job["job_id"])["cancel_requested"] is False
    with pytest.raises(JobError, match="Only failed"):
        service.retry(job["job_id"])
    assert not list(folder.glob("attempts/*/result.partial"))


def test_oom_retry_uses_fresh_worker_and_reduced_internal_segment(service):
    mode(service, "oom_once")
    job = service.run(service.asset)
    assert job["state"] == "SUCCEEDED"
    assert [a["preset_name"] for a in job["attempts"]] == ["baseline", "memory_safe"]
    assert job["attempts"][0]["worker"] != job["attempts"][1]["worker"]
    assert any(event["state"] == "RETRYING" for event in job["history"])
    assert preset("memory_safe")["model_segment_override_sec"] == 2
    assert preset("memory_safe")["cudnn_enabled"] is False


@pytest.mark.parametrize("initial,count", [("baseline", 2), ("memory_safe", 1)])
def test_oom_is_bounded(service, initial, count):
    mode(service, "oom_twice")
    job = service.run(service.asset, initial)
    assert job["state"] == "FAILED"
    assert job["error"]["code"] == "CUDA_OOM"
    assert len(job["attempts"]) == count
    assert not list((service.root / "jobs").glob("*/attempts/*/result.partial"))


def test_non_oom_does_not_retry_and_manual_retry_is_new_job(service):
    mode(service, "error")
    failed = service.run(service.asset)
    assert failed["state"] == "FAILED" and len(failed["attempts"]) == 1
    mode(service, "success")
    new = service.retry(failed["job_id"])
    assert new["state"] == "SUCCEEDED" and new["retry_of"] == failed["job_id"]
    assert new["job_id"] != failed["job_id"]
    assert service.status(failed["job_id"])["state"] == "FAILED"


def test_invalid_result_is_never_published(service):
    mode(service, "invalid")
    with pytest.raises(JobError):
        service.run(service.asset)
    folders = list((service.root / "jobs").glob("job_*"))
    assert read_json(folders[0] / "job.json")["state"] == "FAILED"
    assert not (folders[0] / "result").exists()
    assert not list(folders[0].glob("attempts/*/result.partial"))


@pytest.mark.parametrize("behavior", ["slow", "stuck"])
def test_cancel_cooperative_and_force_kill(service, behavior):
    mode(service, behavior)
    received = {}
    started = threading.Event()

    def update(job):
        received["id"] = job["job_id"]
        if job["state"] == "SEPARATING":
            started.set()

    output = []
    thread = threading.Thread(target=lambda: output.append(service.run(service.asset, on_update=update)))
    thread.start()
    assert started.wait(10)
    service.cancel(received["id"])
    thread.join(10)
    assert not thread.is_alive()
    assert output[0]["state"] == "CANCELLED"
    assert not alive(output[0]["attempts"][0]["worker"])
    assert not (service.root / "jobs" / received["id"] / "result").exists()


def test_timeout_is_failure(service):
    mode(service, "stuck")
    service.timeout_sec = .8
    job = service.run(service.asset)
    assert job["state"] == "FAILED" and job["error"]["code"] == "JOB_TIMEOUT"
    assert not alive(job["attempts"][0]["worker"])


def test_project_gpu_exclusion(service):
    with FileLock(str(service.runtime / "supervisor.lock")):
        with pytest.raises(JobError, match="already running"):
            service.run(service.asset)
        with pytest.raises(JobError, match="already running"):
            service.recover()


def test_recover_dead_owner_and_reconcile_published_commit(service):
    job = service.run(service.asset)
    folder = service.root / "jobs" / job["job_id"]
    job["state"] = "EXPORTING"
    job["owner"] = {"pid": 99999999, "create_time": 0}
    job["attempts"][-1]["state"] = "EXPORTING"
    write_json(folder / "job.json", job)
    assert service.recover() == [{"job_id": job["job_id"], "state": "SUCCEEDED"}]


def test_recover_partial_marks_interrupted(service):
    mode(service, "error")
    job = service.run(service.asset)
    folder = service.root / "jobs" / job["job_id"]
    job["state"] = "SEPARATING"
    job["owner"] = {"pid": 99999999, "create_time": 0}
    job["attempts"][-1]["state"] = "SEPARATING"
    partial = folder / "attempts" / job["attempts"][0]["attempt_id"] / "result.partial"
    partial.mkdir()
    write_json(folder / "job.json", job)
    assert service.recover()[0]["state"] == "INTERRUPTED"
    assert not partial.exists()


def test_owner_pid_reuse_is_not_alive():
    owner = identity()
    assert alive(owner)
    owner["create_time"] += 60
    assert not alive(owner)


@pytest.mark.parametrize("mutation", ["hash", "timeline", "family", "path", "gain", "identity"])
def test_manifest_mutation_rejected(service, mutation):
    job = service.run(service.asset)
    folder = service.root / "jobs" / job["job_id"] / "result"
    manifest = read_json(folder / "manifest.json")
    if mutation == "hash":
        manifest["stems"][0]["sha256"] = "0" * 64
    elif mutation == "timeline":
        manifest["timeline"]["num_frames"] += 1
    elif mutation == "family":
        manifest["stems"][0]["family"] = "vocals"
    elif mutation == "path":
        manifest["stems"][0]["path"] = "../../anything.wav"
    elif mutation == "gain":
        manifest["stems"][0]["gain"] = .5
    else:
        manifest["job_id"] = "wrong"
    write_json(folder / "manifest.json", manifest)
    with pytest.raises(JobError):
        verify_result(folder, job)


def test_streaming_raw_keeps_samples_above_full_scale(tmp_path):
    audio = np.full((RATE * 11, 2), 1.25, np.float32)
    path = tmp_path / "raw.wav"
    checks = []
    properties = write_raw_streaming(path, audio, lambda: checks.append(True))
    assert properties["over_full_scale"] and len(checks) == 4
    decoded, _ = sf.read(path, dtype="float32", always_2d=True)
    assert np.array_equal(decoded, audio)


def test_bad_job_and_preset_rejected(service):
    with pytest.raises(JobError):
        service.status("../../outside")
    with pytest.raises(JobError):
        service.run(service.asset, "unknown")


def test_json_replace_retries_windows_sharing_error(tmp_path, monkeypatch):
    import music_analyzer.common as common
    original = common.os.replace
    calls = []

    def transient(source, destination):
        calls.append(True)
        if len(calls) < 3:
            raise PermissionError("sharing violation")
        return original(source, destination)

    monkeypatch.setattr(common.os, "replace", transient)
    path = tmp_path / "state.json"
    write_json(path, {"state": "SEPARATING"})
    assert read_json(path)["state"] == "SEPARATING" and len(calls) == 3
    assert not list(tmp_path.glob("*.partial"))


def test_json_serialization_failure_preserves_previous_state(tmp_path):
    path = tmp_path / "state.json"
    write_json(path, {"state": "READY"})
    with pytest.raises(ValueError):
        write_json(path, {"invalid": float("nan")})
    assert read_json(path) == {"state": "READY"}
    assert not list(tmp_path.glob("*.partial"))


def test_worker_execution_lock_blocks_gpu_start(service):
    import subprocess
    job = service.run(service.asset)
    attempt = service.root / "jobs" / job["job_id"] / "attempts" / job["attempts"][0]["attempt_id"]
    with FileLock(str(service.runtime / "gpu-execution.lock")):
        process = subprocess.run([sys.executable, "-m", "music_analyzer.worker",
                                  "--request", str(attempt / "request.json")], timeout=10)
    assert process.returncode == 1
    assert read_json(attempt / "worker.json")["error"]["code"] == "GPU_BUSY"


def test_hard_supervisor_exit_recovers_verified_orphan_worker(service):
    import subprocess
    mode(service, "stuck")
    code = ("from pathlib import Path; from music_analyzer.job_service import JobService; "
            "JobService(Path(" + repr(str(service.root)) + "), Path(" + repr(str(service.runtime)) + "), "
            "[__import__('sys').executable, " + repr(str(HELPER.resolve())) + "]).run(" + repr(service.asset) + ")")
    parent = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    worker = None
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            descriptor = service.runtime / "supervisor.json"
            if descriptor.exists():
                current = read_json(descriptor)
                worker = current.get("worker")
                if worker:
                    break
            time.sleep(.05)
        assert worker and alive(worker)
        # On Windows .venv/python.exe is a launcher; terminate the actual supervisor owner.
        import psutil
        owner = current["owner"]
        assert alive(owner)
        psutil.Process(owner["pid"]).kill()
        parent.wait(timeout=10)
        recovered = service.recover()
        assert recovered[0]["state"] == "INTERRUPTED"
        assert not alive(worker)
        mode(service, "success")
        assert service.retry(recovered[0]["job_id"])["state"] == "SUCCEEDED"
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait()
        if worker and alive(worker):
            import psutil
            psutil.Process(worker["pid"]).kill()


def test_publication_obeys_late_cancel(service, monkeypatch):
    import music_analyzer.job_service as module
    original = module.verify_result

    def cancel_before_commit(folder, job):
        value = original(folder, job)
        service.cancel(job["job_id"])
        return value

    monkeypatch.setattr(module, "verify_result", cancel_before_commit)
    job = service.run(service.asset)
    assert job["state"] == "CANCELLED"
    assert not (service.root / "jobs" / job["job_id"] / "result").exists()


def test_json_read_retries_windows_sharing_error(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    write_json(path, {"state": "READY"})
    original = Path.read_text
    calls = []

    def transient(self, *args, **kwargs):
        if self == path:
            calls.append(True)
            if len(calls) < 3:
                raise PermissionError("sharing violation")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", transient)
    assert read_json(path) == {"state": "READY"}
    assert len(calls) == 3
