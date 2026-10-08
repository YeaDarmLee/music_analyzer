"""Checkpoint save/load with mandatory provenance sidecar.

Loading verifies the sidecar sha256 *before* unpickling (the checkpoint holds optimizer/RNG state, so it is
loaded with weights_only=False). A checkpoint without a matching sidecar is refused.
"""
from __future__ import annotations

import os
import random
from pathlib import Path

import numpy as np
import torch

from .provenance import verify_sidecar, write_sidecar


def capture_rng() -> dict:
    return {
        "python": random.getstate(), "numpy": np.random.get_state(), "torch": torch.get_rng_state(),
        "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
    }


def restore_rng(s: dict) -> None:
    random.setstate(s["python"])
    np.random.set_state(s["numpy"])
    torch.set_rng_state(s["torch"].cpu())
    if s.get("cuda") is not None and torch.cuda.is_available():
        torch.cuda.set_rng_state_all([x.cpu() for x in s["cuda"]])


def save_checkpoint(path: str | Path, state: dict, provenance: dict) -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    torch.save(state, tmp)
    os.replace(tmp, path)
    return write_sidecar(path, provenance)


def load_checkpoint(path: str | Path, map_location="cpu") -> tuple[dict, dict]:
    """Returns (state, provenance). Raises ProvenanceError on missing/mismatched sidecar."""
    prov = verify_sidecar(path)
    return torch.load(path, map_location=map_location, weights_only=False), prov
