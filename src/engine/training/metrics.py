"""Metric registry. Only definitions that are unit-verified here are implemented.

Metric signature: fn(out, target, mix, **kwargs) -> float (mean over stems present in both, and over batch).
Leakage / stem-preservation metrics need a definition decision (Research Packet) and are intentionally absent.
"""
from __future__ import annotations

import time

import torch

from engine.registry import METRICS

EPS = 1e-8


def _flat(x: torch.Tensor) -> torch.Tensor:
    return x.float().reshape(x.shape[0], -1)


def sdr_db(est: torch.Tensor, ref: torch.Tensor) -> torch.Tensor:
    e, r = _flat(est), _flat(ref)
    return 10 * torch.log10((r ** 2).sum(-1).clamp_min(EPS) / ((r - e) ** 2).sum(-1).clamp_min(EPS))


def si_sdr_db(est: torch.Tensor, ref: torch.Tensor) -> torch.Tensor:
    e, r = _flat(est), _flat(ref)
    e, r = e - e.mean(-1, keepdim=True), r - r.mean(-1, keepdim=True)
    proj = (e * r).sum(-1, keepdim=True) / (r ** 2).sum(-1, keepdim=True).clamp_min(EPS) * r
    return 10 * torch.log10((proj ** 2).sum(-1).clamp_min(EPS) / ((e - proj) ** 2).sum(-1).clamp_min(EPS))


def _per_stem(fn, out, target):
    names = [n for n in out.stems if n in target]
    return torch.stack([fn(out.stems[n], target[n]) for n in names]).mean().item()


@METRICS.register("sdr")
def sdr(out, target, mix, **_):
    return _per_stem(sdr_db, out, target)


@METRICS.register("si_sdr")
def si_sdr(out, target, mix, **_):
    return _per_stem(si_sdr_db, out, target)


@METRICS.register("reconstruction_error_db")
def reconstruction_error_db(out, target, mix, **_):
    """10*log10(|sum(stems) - mix|^2 / |mix|^2). Lower (more negative) is better."""
    total = sum(out.stems.values())
    m, d = _flat(mix), _flat(total - mix)
    return (10 * torch.log10((d ** 2).sum(-1).clamp_min(EPS) / (m ** 2).sum(-1).clamp_min(EPS))).mean().item()


def measure_inference(fn, audio_seconds: float, device: torch.device) -> dict:
    """Wall-clock latency, real-time factor (processing time / audio time) and peak VRAM for one call of fn()."""
    if device.type == "cuda":
        torch.cuda.synchronize(device)
        torch.cuda.reset_peak_memory_stats(device)
    t0 = time.perf_counter()
    fn()
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    dt = time.perf_counter() - t0
    return {
        "latency_s": dt, "rtf": dt / audio_seconds,
        "peak_vram_mib": torch.cuda.max_memory_allocated(device) / (1 << 20) if device.type == "cuda" else None,
    }
