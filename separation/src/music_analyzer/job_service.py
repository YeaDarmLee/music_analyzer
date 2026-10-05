from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psutil
from filelock import FileLock, Timeout

from .common import project_root, read_json, write_json
from .ingest import load_asset
from .job_contracts import (TERMINAL, WORKER_STAGES, JobError, fallback_for,
                            job_folder, preset, verify_result)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def identity(pid: int | None = None) -> dict:
    process = psutil.Process(pid or os.getpid())
    return {"pid": process.pid, "create_time": process.create_time()}


def alive(owner: dict | None) -> bool:
    if not owner:
        return False
    try:
        return abs(psutil.Process(owner["pid"]).create_time() - owner["create_time"]) < .01
    except (psutil.Error, KeyError, TypeError):
        return False


def kill_process_tree(pid: int) -> None:
    """Windows venv executables may be launchers with a separate Python child."""
    try:
        parent = psutil.Process(pid)
        descendants = [(p, p.create_time()) for p in parent.children(recursive=True)]
        for process, created in reversed(descendants):
            try:
                if abs(process.create_time() - created) < .01:
                    process.kill()
            except psutil.NoSuchProcess:
                pass
        parent.kill()
        psutil.wait_procs([p for p, _ in descendants] + [parent], timeout=10)
    except psutil.NoSuchProcess:
        pass


class JobService:
    def __init__(self, data_root: Path, runtime_dir: Path | None = None,
                 worker_command: list[str] | None = None, poll_sec: float = .1,
                 cancel_grace_sec: float = 10, timeout_sec: float = 7200):
        self.root = data_root.resolve()
        # This project-wide runtime is shared even when --data-root changes.
        self.runtime = (runtime_dir or project_root() / "data/separation/runtime").resolve()
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.worker_command = worker_command or [sys.executable, "-m", "music_analyzer.worker"]
        self.poll_sec = poll_sec
        self.cancel_grace_sec = cancel_grace_sec
        self.timeout_sec = timeout_sec

    def status(self, job_id: str) -> dict:
        return read_json(job_folder(self.root, job_id) / "job.json")

    def cancel(self, job_id: str) -> dict:
        folder = job_folder(self.root, job_id)
        with FileLock(str(folder / "control.lock"), timeout=5):
            job = read_json(folder / "job.json")
            if job["state"] in TERMINAL or (folder / "result").is_dir():
                return {"job_id": job_id, "cancel_requested": False, "state": job["state"]}
            (folder / "cancel.request").touch()
            return {"job_id": job_id, "cancel_requested": True, "state": job["state"]}

    def _save(self, folder: Path, job: dict, state: str | None = None) -> None:
        if state is not None and state != job["state"]:
            if job["state"] in TERMINAL:
                raise JobError("TERMINAL_STATE", "A terminal job cannot be changed")
            job["history"].append({"state": state, "at_utc": now()})
            job["state"] = state
        job["updated_at_utc"] = now()
        write_json(folder / "job.json", job)

    def _remove_attempt_partial(self, folder: Path, attempt: dict) -> None:
        name = attempt["attempt_id"]
        if len(name) != 34 or not name.startswith("a_") or any(c not in "0123456789abcdef" for c in name[2:]):
            raise JobError("ATTEMPT_ID", "Invalid attempt ID")
        partial = folder / "attempts" / name / "result.partial"
        # The verified job folder and fixed child path are the only deletion targets.
        if not partial.resolve().is_relative_to(folder.resolve()):
            raise JobError("PARTIAL_PATH", "Partial result escaped job folder")
        if partial.is_dir() and not partial.is_symlink():
            shutil.rmtree(partial)

    def _terminate_verified(self, worker: dict | None, request_path: Path) -> bool:
        if not alive(worker):
            return True
        process = psutil.Process(worker["pid"])
        try:
            args = process.cmdline()
            marker = self.worker_command[-1]
            if marker not in args or "--request" not in args:
                return False
            supplied = Path(args[args.index("--request") + 1]).resolve()
            if supplied != request_path.resolve():
                return False
            kill_process_tree(process.pid)
            return True
        except (psutil.Error, ValueError, IndexError, OSError):
            return not alive(worker)

    def _recover_locked(self) -> list[dict]:
        owner_path = self.runtime / "supervisor.json"
        if owner_path.exists():
            old = read_json(owner_path)
            if not alive(old.get("owner")) and old.get("worker"):
                if not self._terminate_verified(old["worker"], Path(old["request_path"])):
                    raise JobError("ORPHAN_WORKER", "Cannot verify or stop an old worker; no GPU work will start")
        recovered = []
        jobs = self.root / "jobs"
        if not jobs.exists():
            return recovered
        for folder in jobs.glob("job_*"):
            if not folder.is_dir() or folder.is_symlink() or not (folder / "job.json").is_file():
                continue
            job = read_json(folder / "job.json")
            if job["state"] in TERMINAL or alive(job.get("owner")):
                continue
            if job["attempts"]:
                attempt = job["attempts"][-1]
                request_path = folder / "attempts" / attempt["attempt_id"] / "request.json"
                if not self._terminate_verified(attempt.get("worker"), request_path):
                    raise JobError("ORPHAN_WORKER", "Old worker identity check failed")
            with FileLock(str(folder / "control.lock"), timeout=5):
                if (folder / "result").is_dir():
                    try:
                        verify_result(folder / "result", job)
                    except JobError:
                        job["error"] = {"code": "RECOVERY_RESULT_INVALID", "message": "Published result failed validation"}
                        self._save(folder, job, "FAILED")
                    else:
                        if job["attempts"]:
                            job["attempts"][-1]["state"] = "SUCCEEDED"
                        self._save(folder, job, "SUCCEEDED")
                else:
                    for attempt in job["attempts"]:
                        if attempt["state"] not in TERMINAL:
                            attempt["state"] = "INTERRUPTED"
                        self._remove_attempt_partial(folder, attempt)
                    job["error"] = {"code": "OWNER_EXITED", "message": "Supervisor ended before publishing"}
                    self._save(folder, job, "INTERRUPTED")
            recovered.append({"job_id": job["job_id"], "state": job["state"]})
        return recovered

    def recover(self) -> list[dict]:
        try:
            with FileLock(str(self.runtime / "supervisor.lock"), timeout=0):
                return self._recover_locked()
        except Timeout:
            raise JobError("GPU_BUSY", "A separation supervisor is already running") from None

    def retry(self, job_id: str, on_update=None) -> dict:
        self.recover()
        old = self.status(job_id)
        if old["state"] not in {"FAILED", "CANCELLED", "INTERRUPTED"}:
            raise JobError("RETRY_STATE", "Only failed, cancelled or interrupted jobs can be retried")
        return self.run(old["asset_id"], old["requested_preset"], on_update, retry_of=job_id)

    def run(self, asset_id: str, preset_name: str = "baseline", on_update=None,
            retry_of: str | None = None) -> dict:
        chosen = preset(preset_name)
        supervisor_lock = FileLock(str(self.runtime / "supervisor.lock"), timeout=0)
        try:
            supervisor_lock.acquire()
        except Timeout:
            raise JobError("GPU_BUSY", "A separation supervisor is already running") from None
        folder = None
        job = None
        child = None
        owner_path = self.runtime / "supervisor.json"
        started = time.monotonic()
        try:
            self._recover_locked()
            asset = load_asset(self.root, asset_id)
            job_id = "job_" + uuid4().hex
            folder = self.root / "jobs" / job_id
            folder.mkdir(parents=True, exist_ok=False)
            job = {"schema_version": "1.0", "kind": "separation_job",
                   "job_id": job_id, "asset_id": asset_id, "state": "CREATED",
                   "created_at_utc": now(), "updated_at_utc": now(),
                   "owner": identity(), "canonical_sha256": asset["canonical"]["sha256"],
                   "num_frames": asset["timeline"]["num_frames"], "requested_preset": preset_name,
                   "model_id": chosen.get("model_id", "demucs_htdemucs"),
                   "retry_of": retry_of, "attempts": [], "history": [{"state": "CREATED", "at_utc": now()}],
                   "progress": None, "error": None}
            self._save(folder, job)
            if on_update:
                on_update(job)
            self._save(folder, job, "VALIDATING")
            for number in range(2):
                selected = preset_name if number == 0 else fallback_for(preset_name)
                if selected is None:
                    break
                if (folder / "cancel.request").exists():
                    self._save(folder, job, "CANCELLED")
                    return job
                attempt_id = "a_" + uuid4().hex
                attempt_dir = folder / "attempts" / attempt_id
                attempt_dir.mkdir(parents=True)
                attempt = {"attempt_id": attempt_id, "number": number + 1, "preset_name": selected,
                           "state": "PREPARING_MODEL", "worker": None, "error": None}
                job["attempts"].append(attempt)
                request_path = attempt_dir / "request.json"
                request = {"schema_version": "1.0", "job_id": job_id, "asset_id": asset_id,
                           "data_root": str(self.root), "attempt_dir": str(attempt_dir),
                           "runtime_dir": str(self.runtime), "owner": job["owner"],
                           "preset_name": selected, "requested_preset": preset_name}
                write_json(request_path, request)
                self._save(folder, job, "PREPARING_MODEL")
                descriptor = {"owner": job["owner"], "job_id": job_id,
                              "worker": None, "request_path": str(request_path)}
                write_json(owner_path, descriptor)
                with (attempt_dir / "worker.log").open("wb") as log:
                    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                    child = subprocess.Popen(self.worker_command + ["--request", str(request_path)],
                                             stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                             creationflags=flags)
                    attempt["worker"] = identity(child.pid)
                    descriptor["worker"] = attempt["worker"]
                    write_json(owner_path, descriptor)
                    self._save(folder, job)
                    cancel_started = None
                    timeout_reached = False
                    while child.poll() is None:
                        try:
                            if time.monotonic() - started >= self.timeout_sec:
                                timeout_reached = True
                                (folder / "cancel.request").touch()
                            if (folder / "cancel.request").exists():
                                if cancel_started is None:
                                    cancel_started = time.monotonic()
                                    self._save(folder, job, "CANCELLING")
                                if time.monotonic() - cancel_started >= self.cancel_grace_sec:
                                    kill_process_tree(child.pid)
                                    break
                            telemetry_path = attempt_dir / "worker.json"
                            if telemetry_path.exists() and cancel_started is None:
                                telemetry = read_json(telemetry_path)
                                stage = telemetry.get("state")
                                if stage in WORKER_STAGES:
                                    attempt["state"] = stage
                                    job["progress"] = telemetry.get("progress")
                                    self._save(folder, job, stage)
                                    if on_update:
                                        on_update(job)
                            time.sleep(self.poll_sec)
                        except KeyboardInterrupt:
                            (folder / "cancel.request").touch()
                            if cancel_started is not None:
                                kill_process_tree(child.pid)
                                break
                    child.wait()
                    return_code = child.returncode
                    child = None
                if (folder / "cancel.request").exists():
                    attempt["state"] = "FAILED" if timeout_reached else "CANCELLED"
                    job["error"] = {"code": "JOB_TIMEOUT" if timeout_reached else "CANCELLED",
                                    "message": "Job exceeded its time limit" if timeout_reached else "Cancelled by user"}
                    self._remove_attempt_partial(folder, attempt)
                    self._save(folder, job, attempt["state"])
                    return job
                telemetry_path = attempt_dir / "worker.json"
                telemetry = read_json(telemetry_path) if telemetry_path.exists() else {}
                error = telemetry.get("error") or {"code": "WORKER_EXITED", "message": f"Worker exit code: {return_code}"}
                if return_code == 0 and telemetry.get("state") == "READY_TO_PUBLISH":
                    candidate = attempt_dir / "result.partial"
                    verify_result(candidate, job)
                    with FileLock(str(folder / "control.lock"), timeout=5):
                        if (folder / "cancel.request").exists():
                            attempt["state"] = "CANCELLED"
                            self._remove_attempt_partial(folder, attempt)
                            self._save(folder, job, "CANCELLED")
                        else:
                            candidate.rename(folder / "result")
                            attempt["state"] = "SUCCEEDED"
                            job["progress"] = {"completed": telemetry.get("progress", {}).get("total", 0),
                                               "total": telemetry.get("progress", {}).get("total", 0)}
                            self._save(folder, job, "SUCCEEDED")
                    return job
                attempt["state"] = "FAILED"
                attempt["error"] = error
                self._remove_attempt_partial(folder, attempt)
                if return_code == 12 and error["code"] == "CUDA_OOM" and number == 0 and fallback_for(preset_name):
                    job["progress"] = None
                    self._save(folder, job, "RETRYING")
                    continue
                job["error"] = error
                self._save(folder, job, "FAILED")
                return job
            raise JobError("ATTEMPTS_EXHAUSTED", "No eligible preset")
        except BaseException as error:
            if child is not None and child.poll() is None:
                kill_process_tree(child.pid)
                child.wait()
            if folder is not None and job is not None and job["state"] not in TERMINAL:
                for attempt in job["attempts"]:
                    if attempt["state"] not in TERMINAL:
                        attempt["state"] = "CANCELLED" if isinstance(error, KeyboardInterrupt) else "FAILED"
                    self._remove_attempt_partial(folder, attempt)
                job["error"] = {"code": getattr(error, "code", "SUPERVISOR_ERROR"), "message": str(error)}
                self._save(folder, job, "CANCELLED" if isinstance(error, KeyboardInterrupt) else "FAILED")
            raise
        finally:
            # Result reconciliation after hard process termination is handled by recover().
            if owner_path.exists():
                try:
                    owner = read_json(owner_path)
                    if job and owner.get("job_id") == job["job_id"]:
                        owner_path.unlink()
                except OSError:
                    pass
            supervisor_lock.release()
