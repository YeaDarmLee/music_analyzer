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


def _per_stem(fn, out, target, active=None):
    """Mean of fn over (stem, item) pairs. Items whose target stem is inactive (silent) are skipped: SDR against silence is
    undefined and would dominate the mean (~ -80 dB)."""
    vals = []
    for n in out.stems:
        if n not in target:
            continue
        v = fn(out.stems[n], target[n])
        if active is not None and n in active:
            v = v[active[n].to(v.device).bool()]
        vals.append(v)
    vals = torch.cat([v.reshape(-1) for v in vals]) if vals else torch.zeros(0)
    if vals.numel() == 0:
        return float("nan")
    return vals.mean().item()


@METRICS.register("sdr")
def sdr(out, target, mix, active=None, **_):
    return _per_stem(sdr_db, out, target, active)


@METRICS.register("si_sdr")
def si_sdr(out, target, mix, active=None, **_):
    return _per_stem(si_sdr_db, out, target, active)


@METRICS.register("inactive_rms_ratio_db")
def inactive_rms_ratio_db(out, target, mix, active=None, **_):
    """Hallucination monitor: 20*log10(rms(estimate) / rms(mixture)) over items whose target stem is inactive. Lower is
    better (-inf: perfectly silent). NaN when the batch has no inactive items."""
    if active is None:
        return float("nan")
    m = _flat(mix).pow(2).mean(-1).sqrt().clamp_min(EPS)
    vals = []
    for n in out.stems:
        if n in active:
            inact = ~active[n].to(m.device).bool()
            if inact.any():
                e = _flat(out.stems[n]).pow(2).mean(-1).sqrt()
                vals.append((20 * torch.log10((e / m).clamp_min(EPS)))[inact])
    return torch.cat(vals).mean().item() if vals else float("nan")


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


class ValAggregator:
    """Per-item validation detail: per-stem SDR / SI-SDR (active items only), inactive-stem RMS ratio, reconstruction error,
    each also grouped by the batch's `group` labels (e.g. scene category, singer). Pure bookkeeping; no model/data knowledge."""

    def __init__(self):
        self.rows: list[dict] = []

    def add(self, out, target, mix, active=None, group=None):
        B = mix.shape[0]
        m = _flat(mix).pow(2).mean(-1).sqrt().clamp_min(EPS)
        total = sum(out.stems.values())
        rec = (10 * torch.log10((_flat(total - mix) ** 2).sum(-1).clamp_min(EPS) / (_flat(mix) ** 2).sum(-1).clamp_min(EPS))).cpu()
        per = {}
        for n in out.stems:
            if n not in target:
                continue
            act = active[n].to(mix.device).bool() if active is not None and n in active else torch.ones(B, dtype=torch.bool, device=mix.device)
            ratio = 20 * torch.log10((_flat(out.stems[n]).pow(2).mean(-1).sqrt() / m).clamp_min(EPS))
            per[n] = (sdr_db(out.stems[n], target[n]).cpu(), si_sdr_db(out.stems[n], target[n]).cpu(), act.cpu(), ratio.cpu())
        for b in range(B):
            row = {"recon": float(rec[b]), "group": {k: v[b] for k, v in (group or {}).items()}, "stems": {}}
            for n, (sd, ssd, act, inr) in per.items():
                row["stems"][n] = (float(sd[b]), float(ssd[b]), bool(act[b]), float(inr[b]))
            self.rows.append(row)

    @staticmethod
    def _mean(v):
        return sum(v) / len(v) if v else float("nan")

    def summary(self) -> dict:
        out, stems = {"val_items": len(self.rows), "val_recon_err_db": self._mean([r["recon"] for r in self.rows])}, set()
        for r in self.rows:
            stems |= set(r["stems"])
        for n in sorted(stems):
            act = [r["stems"][n] for r in self.rows if n in r["stems"] and r["stems"][n][2]]
            out[f"val_sdr_{n}"] = self._mean([a[0] for a in act])
            out[f"val_si_sdr_{n}"] = self._mean([a[1] for a in act])
            out[f"val_n_active_{n}"] = len(act)
        groups: dict[tuple, list] = {}
        for r in self.rows:
            for gk, gv in r["group"].items():
                if gv != "":
                    groups.setdefault((gk, gv), []).append(r)
        for (gk, gv), rs in sorted(groups.items()):
            act = [(n, s) for r in rs for n, s in r["stems"].items() if s[2]]
            ina = [s[3] for r in rs for s in r["stems"].values() if not s[2]]
            pre = f"val_{gk}/{gv}"
            out[f"{pre}/sdr"] = self._mean([s[0] for _, s in act])
            out[f"{pre}/si_sdr"] = self._mean([s[1] for _, s in act])
            out[f"{pre}/inactive_rms_db"] = self._mean(ina)
            out[f"{pre}/n"] = len(rs)
            for n in sorted(stems):  # per stem within the group (vocal vs instrumental per singer / category)
                a = [s for nn, s in act if nn == n]
                if a:
                    out[f"{pre}/si_sdr_{n}"] = self._mean([s[1] for s in a])
                    out[f"{pre}/sdr_{n}"] = self._mean([s[0] for s in a])
        return out
