"""Hierarchical target builder: atomic stems -> 2-stem / 6-stem (/ atomic) target dictionaries.
Every atomic stem belongs to exactly one target group, so the sum of the targets always equals the sum of the atomic stems."""
from __future__ import annotations

import numpy as np

ATOMIC_ALL = ("vocal", "drums", "bass", "guitar", "piano", "synth", "strings", "brass", "organ")
SCHEMAS = {
    "atomic_v1": {s: [s] for s in ATOMIC_ALL},
    "2stem_v1": {"vocals": ["vocal"], "instrumental": ["drums", "bass", "guitar", "piano", "synth", "strings", "brass", "organ"]},
    "6stem_v1": {"vocals": ["vocal"], "drums": ["drums"], "bass": ["bass"], "guitar": ["guitar"], "piano": ["piano"],
                 "rest": ["synth", "strings", "brass", "organ"]},
}


def check_schemas() -> None:
    for name, groups in SCHEMAS.items():
        flat = [a for g in groups.values() for a in g]
        if sorted(flat) != sorted(ATOMIC_ALL):
            raise ValueError(f"schema {name} must cover every atomic stem exactly once")


check_schemas()


def build_targets(atomic: dict[str, np.ndarray], schema: str) -> dict[str, np.ndarray]:
    """Missing atomic stems count as silence. Sums in float64, returns float32."""
    unknown = set(atomic) - set(ATOMIC_ALL)
    if unknown:
        raise KeyError(f"unknown atomic stems {sorted(unknown)}")
    ref = next(iter(atomic.values()))
    out = {}
    for tgt, members in SCHEMAS[schema].items():
        acc = np.zeros(ref.shape, np.float64)
        for m in members:
            if m in atomic:
                acc += atomic[m]
        out[tgt] = acc.astype(np.float32)
    return out
