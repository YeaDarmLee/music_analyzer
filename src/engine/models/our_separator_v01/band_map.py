"""Deterministic overlapping Mel-like band layout over STFT bins (self-contained: no librosa).

Each band is a contiguous bin slice [lo, hi). Bands overlap (triangular-filter support, as in Mel-Band RoFormer's
idea) but the *features* are the raw complex bins; the Mel scale only decides where slices start and end.
Guarantees (tested): every bin is covered by >= 1 band, DC and Nyquist included, slices are monotone,
the mapping depends only on (sample_rate, n_fft, num_bands).
"""
from __future__ import annotations

import numpy as np


def hz_to_mel(f):
    return 2595.0 * np.log10(1.0 + np.asarray(f, dtype=np.float64) / 700.0)


def mel_to_hz(m):
    return 700.0 * (10.0 ** (np.asarray(m, dtype=np.float64) / 2595.0) - 1.0)


def build_band_slices(sample_rate: int, n_fft: int, num_bands: int) -> tuple[tuple[int, int], ...]:
    n_bins = n_fft // 2 + 1
    freqs = np.arange(n_bins) * sample_rate / n_fft
    edges = mel_to_hz(np.linspace(0.0, hz_to_mel(sample_rate / 2), num_bands + 2))
    sl = []
    for b in range(num_bands):
        lo = int(np.searchsorted(freqs, edges[b], side="left"))
        hi = int(np.searchsorted(freqs, edges[b + 2], side="right"))
        lo = min(lo, n_bins - 1)
        sl.append([lo, min(max(hi, lo + 1), n_bins)])
    sl[0][0], sl[-1][1] = 0, n_bins
    for b in range(1, num_bands):  # close gaps: the earlier band absorbs bins up to the next band's start
        if sl[b][0] > sl[b - 1][1]:
            sl[b - 1][1] = sl[b][0]
    return tuple((lo, hi) for lo, hi in sl)


def bands_per_bin(slices, n_bins: int) -> np.ndarray:
    cnt = np.zeros(n_bins, dtype=np.int64)
    for lo, hi in slices:
        cnt[lo:hi] += 1
    return cnt
