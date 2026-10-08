"""Complex-mask activation and output-consistency (mixture projection) modules. Both are swappable ablation points."""
from __future__ import annotations

import torch
from torch import nn

MASK_ACTIVATIONS = ("bounded_tanh", "unconstrained")
CONSISTENCY_MODES = ("residual", "soft", "project")  # A / B / C of the 2-stem question


class MaskActivation(nn.Module):
    """bounded_tanh: bound * tanh(raw / bound), applied to real and imaginary parts independently."""

    def __init__(self, kind: str, bound: float):
        super().__init__()
        if kind not in MASK_ACTIVATIONS:
            raise ValueError(f"mask_activation must be one of {MASK_ACTIVATIONS}")
        self.kind, self.bound = kind, float(bound)

    def forward(self, raw):
        return self.bound * torch.tanh(raw / self.bound) if self.kind == "bounded_tanh" else raw


class MixtureProjection(nn.Module):
    """Maps predicted waveforms (B, P, C, T) to the final stems (B, S, C, T).

    residual (A): P = S-1 predicted stems, the last stem is mix - sum(predicted).
    soft     (B): P = S, outputs untouched (use the `mixture_l1` loss).
    project  (C): P = S, equal split of the residual: s_i' = s_i + (mix - sum s) / S, so sum s' == mix.
    Equal weighting is the v0.1 default; the weights live here so energy-weighted / learned variants can replace it.
    """

    def __init__(self, mode: str):
        super().__init__()
        if mode not in CONSISTENCY_MODES:
            raise ValueError(f"output_consistency_mode must be one of {CONSISTENCY_MODES}")
        self.mode = mode

    def num_predicted(self, num_stems: int) -> int:
        return num_stems - 1 if self.mode == "residual" else num_stems

    def forward(self, mix: torch.Tensor, est: torch.Tensor) -> torch.Tensor:
        resid = mix[:, None] - est.sum(dim=1, keepdim=True)
        if self.mode == "residual":
            return torch.cat([est, resid], dim=1)
        if self.mode == "project":
            return est + resid / est.shape[1]
        return est
