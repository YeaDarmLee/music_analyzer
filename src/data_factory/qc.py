"""Per-scene QC (Packet 04/05 §27). A scene that fails any mandatory check must not enter training."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .targets import ATOMIC_ALL, build_targets
from .util import rms, sha256_array


@dataclass
class QCResult:
    passed: bool
    failures: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def qc_scene(mix: np.ndarray, atomic: dict[str, np.ndarray], active: list[str], sr: int, expected_samples: int,
             expected_sr: int = 44100, peak_limit: float = 0.999, sum_tol: float = 2e-6,
             min_active_rms_db: float = -80.0, manifest_problems: list | None = None) -> QCResult:
    f, st = [], {}
    if sr != expected_sr:
        f.append(f"sample_rate {sr} != {expected_sr}")
    for name, a in [("mix", mix)] + list(atomic.items()):
        if a.ndim != 2 or a.shape[0] != 2:
            f.append(f"{name}: expected 2 channels, shape {a.shape}")
        elif a.shape[1] != expected_samples:
            f.append(f"{name}: {a.shape[1]} samples != {expected_samples}")
        if not np.isfinite(a).all():
            f.append(f"{name}: NaN/Inf")
    if f:
        return QCResult(False, f, st)
    peak = max(float(np.abs(mix).max()), max(float(np.abs(a).max()) for a in atomic.values()))
    st["peak"] = peak
    if peak > peak_limit:
        f.append(f"clipping: peak {peak:.6f} > {peak_limit}")
    total = sum(atomic[s].astype(np.float64) for s in atomic)
    err = float(np.abs(total - mix.astype(np.float64)).max())
    st["mix_sum_max_abs_err"] = err
    if err > sum_tol:
        f.append(f"mix != sum(stems): max abs err {err:.3e} > {sum_tol}")
    for s in ATOMIC_ALL:
        a = atomic.get(s)
        if a is None:
            continue
        if s in active:
            db = 20 * np.log10(max(rms(a), 1e-12))
            st[f"rms_db_{s}"] = db
            if db < min_active_rms_db:
                f.append(f"active stem {s} below {min_active_rms_db} dBFS RMS")
        elif np.any(a != 0):
            f.append(f"inactive stem {s} is not exactly zero")
    two = build_targets(atomic, "2stem_v1")
    e2 = float(np.abs(two["vocals"].astype(np.float64) + two["instrumental"] - mix).max())
    st["two_stem_sum_err"] = e2
    if e2 > sum_tol:
        f.append(f"2-stem targets do not sum to mix: {e2:.3e}")
    if manifest_problems:
        f.append(f"asset policy: {manifest_problems}")
    st["mix_sha256"] = sha256_array(mix)
    return QCResult(not f, f, st)
