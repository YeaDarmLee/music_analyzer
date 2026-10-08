"""Architecture-neutral model contract.

Input : mix (batch, channels, samples)
Output: SeparationOutput with named stems, so 2-stem / 6-stem / query / hierarchical /
        waveform / STFT / hybrid models can all share it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import torch
from torch import nn


@dataclass
class SeparationOutput:
    stems: dict[str, torch.Tensor]            # name -> (batch, channels, samples)
    sample_rate: int
    metadata: dict = field(default_factory=dict)
    aux: dict[str, torch.Tensor] = field(default_factory=dict)  # optional auxiliary outputs (masks, latents, ...)


class SeparatorModel(nn.Module):
    """Base class. Subclasses set `stem_names` and `sample_rate`; `forward` returns SeparationOutput."""

    stem_names: list[str]
    sample_rate: int

    def forward(self, mix: torch.Tensor) -> SeparationOutput:  # pragma: no cover - interface
        raise NotImplementedError

    def set_gradient_checkpointing(self, enabled: bool) -> None:
        """Optional hook. Models that cannot checkpoint raise if it is requested."""
        if enabled:
            raise NotImplementedError(f"{type(self).__name__} does not support gradient checkpointing")
