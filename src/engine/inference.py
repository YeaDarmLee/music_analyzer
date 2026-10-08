"""Generic chunked inference for any SeparatorModel (architecture-agnostic).

Chunk length / overlap are caller-supplied (they are architecture decisions, not engine constants).
"""
from __future__ import annotations

import torch

from .interfaces import SeparationOutput, SeparatorModel


@torch.no_grad()
def separate(model: SeparatorModel, mix: torch.Tensor, chunk_samples: int | None = None,
             overlap_samples: int = 0, device: torch.device | str | None = None) -> SeparationOutput:
    """mix: (channels, samples) or (batch, channels, samples). Returns stems on CPU with the same batch rank."""
    squeeze = mix.ndim == 2
    x = mix[None] if squeeze else mix
    dev = torch.device(device) if device is not None else next(model.parameters()).device
    was_training = model.training
    model.eval()
    try:
        if chunk_samples is None or x.shape[-1] <= chunk_samples:
            out = model(x.to(dev))
            stems = {k: v.float().cpu() for k, v in out.stems.items()}
            meta, sr = out.metadata, out.sample_rate
        else:
            if not 0 <= overlap_samples < chunk_samples:
                raise ValueError("need 0 <= overlap_samples < chunk_samples")
            total, step = x.shape[-1], chunk_samples - overlap_samples
            num, den, meta, sr = {}, torch.zeros(1, 1, total), {}, model.sample_rate
            ramp = torch.arange(1, overlap_samples + 1, dtype=torch.float32) / (overlap_samples + 1)
            for start in range(0, total, step):
                piece = x[..., start:start + chunk_samples]
                n = piece.shape[-1]
                if n < chunk_samples:
                    piece = torch.nn.functional.pad(piece, (0, chunk_samples - n))
                out = model(piece.to(dev))
                meta = out.metadata
                w = torch.ones(chunk_samples)
                if overlap_samples:
                    if start > 0:
                        w[:overlap_samples] = ramp
                    if start + chunk_samples < total:
                        w[-overlap_samples:] = torch.minimum(w[-overlap_samples:], ramp.flip(0))
                w = w[:n]
                for k, v in out.stems.items():
                    v = v.float().cpu()[..., :n]
                    if k not in num:
                        num[k] = torch.zeros(x.shape[0], v.shape[1], total)
                    num[k][..., start:start + n] += v * w
                den[..., start:start + n] += w
                if start + chunk_samples >= total:
                    break
            stems = {k: v / den.clamp_min(1e-8) for k, v in num.items()}
    finally:
        model.train(was_training)
    if squeeze:
        stems = {k: v[0] for k, v in stems.items()}
    return SeparationOutput(stems=stems, sample_rate=sr, metadata=meta)
