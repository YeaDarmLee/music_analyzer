"""TinyTestSeparator: infrastructure test fixture. NOT an OUR MODEL architecture candidate.

A small waveform conv net with one output per stem. It exists only so forward/backward/AMP/
accumulation/checkpoint/resume/inference/provenance can be exercised end to end.
"""
from __future__ import annotations

import torch
from torch import nn
from torch.utils.checkpoint import checkpoint

from engine.interfaces import SeparationOutput, SeparatorModel
from engine.registry import MODELS


class TinyTestSeparator(SeparatorModel):
    def __init__(self, stems: list[str], channels: int, sample_rate: int, hidden: int, kernel: int):
        super().__init__()
        self.stem_names = list(stems)
        self.sample_rate = sample_rate
        self.channels = channels
        pad = kernel // 2
        self.body = nn.Sequential(
            nn.Conv1d(channels, hidden, kernel, padding=pad), nn.Tanh(),
            nn.Conv1d(hidden, hidden, kernel, padding=pad), nn.Tanh(),
        )
        self.head = nn.Conv1d(hidden, channels * len(stems), 1)
        self._ckpt = False

    def set_gradient_checkpointing(self, enabled: bool) -> None:
        self._ckpt = enabled

    def forward(self, mix: torch.Tensor) -> SeparationOutput:
        h = checkpoint(self.body, mix, use_reentrant=False) if (self._ckpt and self.training) else self.body(mix)
        y = self.head(h).view(mix.shape[0], len(self.stem_names), self.channels, mix.shape[-1])
        return SeparationOutput(
            stems={n: y[:, i] for i, n in enumerate(self.stem_names)},
            sample_rate=self.sample_rate,
            metadata={"model": "tiny_test_separator"},
        )


@MODELS.register("tiny_test_separator")
def build(cfg: dict) -> TinyTestSeparator:
    p = cfg["params"]
    return TinyTestSeparator(cfg["stems"], cfg["channels"], cfg["sample_rate"], p["hidden"], p["kernel"])


class DummySplit(SeparatorModel):
    """Splits the mix equally across stems. Registry/inference fixture."""

    def __init__(self, stems: list[str], sample_rate: int):
        super().__init__()
        self.stem_names = list(stems)
        self.sample_rate = sample_rate
        self.scale = nn.Parameter(torch.ones(1))

    def forward(self, mix):
        n = len(self.stem_names)
        return SeparationOutput({s: mix * self.scale / n for s in self.stem_names}, self.sample_rate)


@MODELS.register("dummy_split")
def build_dummy(cfg: dict) -> DummySplit:
    return DummySplit(cfg["stems"], cfg["sample_rate"])
