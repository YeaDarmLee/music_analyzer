from __future__ import annotations

import os
import urllib.request
from pathlib import Path

from .common import project_root, read_json, sha256_file, write_json

CONFIG = project_root() / "separation/configs/models/demucs_htdemucs.json"
MODEL_IDS = ("demucs_htdemucs", "demucs_htdemucs_6s", "demucs_htdemucs_ft", "melband_roformer_kj", "bs_roformer_6s")
FILES = {"955717e8-8726e21a.th", "5c90dfd2-34c22ccb.th",
         "f7e0c4bc-ba3fe64a.th", "d12395a8-e57c48e6.th",
         "92cfc3b6-ef3bcb9c.th", "04573f0d-f3cf25b2.th"}
BASE_URL = "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/"


def config_path(model_id="demucs_htdemucs") -> Path:
    if model_id not in MODEL_IDS:
        raise ValueError("Unknown registered model")
    return CONFIG if model_id == "demucs_htdemucs" else CONFIG.parent / (model_id + ".json")


def config(model_id="demucs_htdemucs") -> dict:
    return read_json(config_path(model_id))


def paths(data_root: Path, model_id="demucs_htdemucs") -> tuple[Path, Path]:
    folder = data_root / "models" / model_id
    return folder / config(model_id)["checkpoint_filename"], folder / "registration.json"


def artifacts(entry):
    return entry.get("checkpoint_artifacts") or [{
        "filename": entry["checkpoint_filename"], "url": entry["checkpoint_url"],
        "upstream_sha256_prefix": entry["upstream_sha256_prefix"]}]


def verify_digest(actual: str, prefix: str, full: str | None = None) -> None:
    if not actual.startswith(prefix) or (full is not None and actual != full):
        raise ValueError("CHECKPOINT_HASH_MISMATCH: model will not be loaded")


def require_dev_only(entry: dict) -> None:
    if entry["commercial_release_status"] != "DEV_ONLY":
        raise ValueError("Runner accepts only registered development models")


def validate_registration(checkpoint: Path, registration: dict, entry: dict) -> None:
    require_dev_only(entry)
    records = registration.get("artifact_hashes", {})
    registered_artifacts = entry.get("checkpoint_artifacts") or [{
        "filename": checkpoint.name, "upstream_sha256_prefix": entry["upstream_sha256_prefix"]}]
    for artifact in registered_artifacts:
        path = checkpoint.parent / artifact["filename"]
        pinned = records.get(artifact["filename"])
        if pinned is None:
            if len(registered_artifacts) != 1:
                raise ValueError("Missing pinned ensemble checkpoint")
            pinned = registration["checkpoint_sha256"]
        verify_digest(sha256_file(path), artifact["upstream_sha256_prefix"], pinned)
    if registration["config_sha256"] != sha256_file(config_path(entry.get("model_id", "demucs_htdemucs"))):
        raise ValueError("MODEL_CONFIG_CHANGED: run prepare-model again")
    if entry.get("ensemble"):
        path = checkpoint.parent / (entry["checkpoint_signature"] + ".yaml")
        if sha256_file(path) != registration["ensemble_sha256"]:
            raise ValueError("ENSEMBLE_CONFIG_CHANGED")


def prepare(data_root: Path, model_id="demucs_htdemucs") -> dict:
    entry = config(model_id)
    require_dev_only(entry)
    checkpoint, registration_path = paths(data_root, model_id)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    existing = read_json(registration_path) if registration_path.exists() else None
    hashes = {}
    for artifact in artifacts(entry):
        path = checkpoint.parent / artifact["filename"]
        pinned = (existing.get("artifact_hashes", {}).get(path.name)
                  or (existing["checkpoint_sha256"] if path == checkpoint else None)) if existing else None
        if path.exists():
            digest = sha256_file(path)
            verify_digest(digest, artifact["upstream_sha256_prefix"], pinned)
        else:
            if existing:
                raise FileNotFoundError("MODEL_FILE_MISSING: stale registration must be reviewed before re-download")
            partial = path.with_suffix(".th.partial")
            is_roformer = model_id == "melband_roformer_kj" and artifact["url"] == "https://huggingface.co/KimberleyJSN/melbandroformer/resolve/ac9b0614ab3cd7f77219e18ba494dfd93956c348/MelBandRoformer.ckpt" and path.name == "MelBandRoformer.ckpt"
            is_roformer = is_roformer or (model_id == "bs_roformer_6s" and path.name == "bs_6stem_fixed.ckpt" and artifact["url"] == "https://huggingface.co/noblebarkrr/mvsepless_resources/resolve/030a01aa951b3908ed6b01b2e507c17953300c2d/bs_roformer/bs_6stem_fixed.ckpt")
            if not is_roformer and (path.name not in FILES or artifact["url"] != BASE_URL + path.name):
                raise ValueError("Checkpoint URL is outside the official allowlist")
            try:
                print("Downloading " + path.name, flush=True)
                request = urllib.request.Request(artifact["url"], headers={"User-Agent": "music-analyzer/0.1"})
                with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as output:
                    total = 0
                    for chunk in iter(lambda: response.read(1024 * 1024), b""):
                        total += len(chunk)
                        if total > (2048 if is_roformer else 512) * 1024 * 1024:
                            raise ValueError("Checkpoint exceeds download size limit")
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                digest = sha256_file(partial)
                verify_digest(digest, artifact["upstream_sha256_prefix"])
                os.replace(partial, path)
            finally:
                partial.unlink(missing_ok=True)
        hashes[path.name] = digest
    extra = {}
    if entry.get("ensemble"):
        ensemble = checkpoint.parent / (entry["checkpoint_signature"] + ".yaml")
        # JSON is valid YAML; exact weights are stored in the registered config.
        write_json(ensemble, entry["ensemble"])
        extra["ensemble_sha256"] = sha256_file(ensemble)
    registration = {**entry, "checkpoint_sha256": hashes[checkpoint.name],
                    "artifact_hashes": hashes, "config_sha256": sha256_file(config_path(model_id)), **extra,
                    "verification": {"upstream_hash": "published_sha256_full" if model_id in ("melband_roformer_kj", "bs_roformer_6s") else "sha256_prefix_8",
                                     "full_hash": "observed_on_first_download_then_pinned",
                                     "independent_full_hash_verified": model_id in ("melband_roformer_kj", "bs_roformer_6s")}}
    write_json(registration_path, registration)
    return registration


def resolve(data_root: Path, model_id="demucs_htdemucs") -> tuple[Path, dict]:
    checkpoint, registration_path = paths(data_root, model_id)
    if not checkpoint.is_file() or not registration_path.is_file():
        raise FileNotFoundError("MODEL_NOT_AVAILABLE: run prepare-model --model " + model_id + " first")
    registration = read_json(registration_path)
    validate_registration(checkpoint, registration, config(model_id))
    return checkpoint, registration
