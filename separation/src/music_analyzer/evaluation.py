from __future__ import annotations

import numpy as np

EPSILON = 1e-12


def _pair(reference: np.ndarray, estimate: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    reference = np.asarray(reference, dtype=np.float64)
    estimate = np.asarray(estimate, dtype=np.float64)
    if reference.shape != estimate.shape or reference.size == 0:
        raise ValueError("Metric requires equal, non-empty shapes")
    if not np.isfinite(reference).all() or not np.isfinite(estimate).all():
        raise ValueError("Non-finite metric input")
    return reference.ravel(), estimate.ravel()


def raw_sdr(reference: np.ndarray, estimate: np.ndarray) -> float | None:
    ref, est = _pair(reference, estimate)
    if np.sqrt(np.mean(ref ** 2)) < 1e-3:  # -60 dBFS
        return None
    return float(10 * np.log10((np.dot(ref, ref) + EPSILON) /
                              (np.dot(ref - est, ref - est) + EPSILON)))


def si_sdr(reference: np.ndarray, estimate: np.ndarray) -> float | None:
    ref, est = _pair(reference, estimate)
    ref, est = ref - ref.mean(), est - est.mean()
    if np.sqrt(np.mean(ref ** 2)) < 1e-3:
        return None
    target = ref * (np.dot(est, ref) / (np.dot(ref, ref) + EPSILON))
    noise = est - target
    if np.dot(target, target) <= EPSILON:
        return None  # degenerate scale projection, not a high-quality score
    return float(10 * np.log10((np.dot(target, target) + EPSILON) /
                              (np.dot(noise, noise) + EPSILON)))
