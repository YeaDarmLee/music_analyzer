"""Checkpoint provenance sidecar: `<ckpt>.provenance.json`, plus environment / git capture."""
from __future__ import annotations

import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import torch

from .hashing import canonical_json, sha256_file

FORMAT_VERSION = 1
REQUIRED = ("checkpoint_sha256", "model_id", "model_config_hash", "training_config_hash",
            "dataset_manifest_sha256", "training_run_id", "git_commit", "created_at", "parent_checkpoint")
NULLABLE = ("git_commit", "parent_checkpoint")  # parent_checkpoint is null for from-scratch training


class ProvenanceError(RuntimeError):
    pass


def sidecar_path(ckpt: str | Path) -> Path:
    p = Path(ckpt)
    return p.with_name(p.name + ".provenance.json")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git_info(cwd: str | Path | None = None) -> dict:
    def run(*a):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    try:
        return {"git_commit": run("rev-parse", "HEAD"), "git_dirty": bool(run("status", "--porcelain"))}
    except (OSError, subprocess.SubprocessError):
        return {"git_commit": None, "git_dirty": None}


def environment_info() -> dict:
    cuda = torch.cuda.is_available()
    return {
        "python": platform.python_version(), "platform": platform.platform(),
        "torch": torch.__version__, "cuda_runtime": torch.version.cuda, "cuda_available": cuda,
        "gpu": torch.cuda.get_device_name(0) if cuda else None,
        "gpu_total_mib": torch.cuda.get_device_properties(0).total_memory // (1 << 20) if cuda else None,
    }


def parent_ref(parent_ckpt: str | Path | None) -> dict | None:
    """Reference for fine-tuning lineage; verifies the parent's own sidecar first."""
    if parent_ckpt is None:
        return None
    verify_sidecar(parent_ckpt)
    return {"sha256": sha256_file(parent_ckpt), "path": str(parent_ckpt)}


def write_sidecar(ckpt: str | Path, fields: dict) -> dict:
    """`fields` supplies everything except checkpoint_sha256/created_at (computed here)."""
    rec = {"format_version": FORMAT_VERSION, **fields,
           "checkpoint_sha256": sha256_file(ckpt), "created_at": utc_now()}
    missing = [k for k in REQUIRED if k not in rec or (rec[k] is None and k not in NULLABLE)]
    if missing:
        raise ProvenanceError(f"provenance fields missing/None: {missing}")
    out = sidecar_path(ckpt)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_bytes(json.dumps(rec, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    os.replace(tmp, out)
    return rec


def read_sidecar(ckpt: str | Path) -> dict:
    p = sidecar_path(ckpt)
    if not p.exists():
        raise ProvenanceError(f"no provenance sidecar for {ckpt}")
    return json.loads(p.read_text(encoding="utf-8"))


def verify_sidecar(ckpt: str | Path) -> dict:
    rec = read_sidecar(ckpt)
    actual = sha256_file(ckpt)
    if rec.get("checkpoint_sha256") != actual:
        raise ProvenanceError(f"checkpoint sha256 mismatch for {ckpt}: sidecar {rec.get('checkpoint_sha256')} != actual {actual}")
    return rec
