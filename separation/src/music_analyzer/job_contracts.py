from __future__ import annotations

import re
from pathlib import Path

import soundfile as sf

from .audio import RATE
from .common import project_root, read_json, sha256_file

TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED", "INTERRUPTED"}
WORKER_STAGES = {"PREPARING_MODEL", "PREPROCESSING", "SEPARATING", "VALIDATING_OUTPUT", "EXPORTING"}
PRESETS = project_root() / "separation/configs/presets/demucs.json"


class JobError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class WorkCancelled(Exception):
    pass


def preset(name: str) -> dict:
    config = read_json(PRESETS)
    if name not in config["presets"]:
        raise JobError("PRESET", "Unknown separation preset")
    return dict(config["presets"][name])


def fallback_for(name: str) -> str | None:
    return read_json(PRESETS)["oom_fallback"].get(name)


def job_folder(data_root: Path, job_id: str) -> Path:
    if not re.fullmatch(r"job_[0-9a-f]{32}", job_id):
        raise JobError("JOB_ID", "Invalid job ID")
    folder = data_root.resolve() / "jobs" / job_id
    if not folder.is_dir() or folder.is_symlink():
        raise JobError("JOB_NOT_FOUND", "No job with this ID")
    return folder


def verify_result(folder: Path, job: dict) -> dict:
    try:
        manifest = read_json(folder / "manifest.json")
        if (manifest["kind"], manifest["schema_version"], manifest["status"],
            manifest["job_id"], manifest["asset_id"]) != (
                "separation_result", "1.0", "succeeded", job["job_id"], job["asset_id"]):
            raise ValueError("Result identity mismatch")
        if manifest["source_sha256"] != job["canonical_sha256"]:
            raise ValueError("Result input hash mismatch")
        timeline = manifest["timeline"]
        if (timeline["sample_rate"], timeline["channels"], timeline["num_frames"], timeline["origin_sec"]) != (
                RATE, 2, job["num_frames"], 0):
            raise ValueError("Result timeline mismatch")
        from .registry import config
        model_id = job.get("model_id", "demucs_htdemucs")
        expected = set(config(model_id)["source_labels"])
        if "model" in manifest and manifest["model"]["model_id"] != model_id:
            raise ValueError("Result model identity mismatch")
        if len(manifest["stems"]) != len(expected) or {s["family"] for s in manifest["stems"]} != expected:
            raise ValueError("Missing or duplicate output stem")
        for stem in manifest["stems"]:
            expected_path = f"stems/{stem['family']}.wav"
            if stem["path"] != expected_path:
                raise ValueError("Invalid stem path")
            path = folder / expected_path
            if path.is_symlink() or sha256_file(path) != stem["sha256"]:
                raise ValueError("Stem hash mismatch")
            info = sf.info(path)
            if (info.samplerate, info.channels, info.frames, info.subtype) != (RATE, 2, job["num_frames"], "FLOAT"):
                raise ValueError("Stem audio contract mismatch")
            if not stem["roundtrip_exact"] or stem["gain"] != 1.0 or stem["clip_mode"] != "none":
                raise ValueError("Raw storage contract mismatch")
        return manifest
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise JobError("RESULT_INVALID", str(error)) from error
