"""Loss registry + composition. Phase 2 ships only trivial waveform losses to exercise the plumbing.

Loss signature: fn(out: SeparationOutput, target: dict[str, Tensor], mix: Tensor, **kwargs) -> scalar tensor.
Real loss candidates (spectral, multi-res STFT, SI-SDR, mixture consistency, leakage, hierarchy, ...) are added
after the Research Packets; each one is switched on/off purely from `training.losses` in config.
"""
from __future__ import annotations

import torch

from engine.registry import LOSSES


def _pairs(out, target):
    names = [n for n in out.stems if n in target]
    if not names:
        raise KeyError(f"no common stems between output {list(out.stems)} and target {list(target)}")
    return [(out.stems[n].float(), target[n].float()) for n in names]


@LOSSES.register("waveform_l1")
def waveform_l1(out, target, mix, **_):
    return torch.stack([(p - t).abs().mean() for p, t in _pairs(out, target)]).mean()


@LOSSES.register("waveform_l2")
def waveform_l2(out, target, mix, **_):
    return torch.stack([((p - t) ** 2).mean() for p, t in _pairs(out, target)]).mean()


def build_composite(loss_cfgs: list[dict]):
    """Returns fn(out, target, mix) -> (total, {name: value}). Terms with weight 0 are skipped."""
    terms = [(c["name"], float(c["weight"]), LOSSES.get(c["name"]), c["kwargs"]) for c in loss_cfgs if c["weight"] != 0]
    if not terms:
        raise ValueError("all loss weights are zero")

    def composite(out, target, mix):
        total, parts = 0.0, {}
        for name, w, fn, kw in terms:
            v = fn(out, target, mix, **kw)
            parts[name] = float(v.detach())
            total = total + w * v
        return total, parts

    return composite
