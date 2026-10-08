"""Transformer building blocks written for this project (RMSNorm, RoPE, SDPA attention, FFN, axial T/F block)."""
from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.checkpoint import checkpoint

ACTIVATIONS = {"silu": nn.SiLU, "gelu": nn.GELU}


class RMSNorm(nn.Module):
    def __init__(self, dim: int, eps: float = 1e-6):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(dim))
        self.eps = eps

    def forward(self, x):
        xf = x.float()
        y = xf * torch.rsqrt(xf.pow(2).mean(-1, keepdim=True) + self.eps)
        return (y * self.weight.float()).to(x.dtype)


class Rotary(nn.Module):
    """Rotary position embedding (half-split rotation) applied to q and k of shape (N, H, L, Dh)."""

    def __init__(self, dim_head: int, base: float = 10000.0):
        super().__init__()
        if dim_head % 2:
            raise ValueError("dim_head must be even for RoPE")
        inv = 1.0 / (base ** (torch.arange(0, dim_head, 2, dtype=torch.float32) / dim_head))
        self.register_buffer("inv_freq", inv, persistent=False)

    def forward(self, q, k):
        L = q.shape[-2]
        ang = torch.outer(torch.arange(L, device=q.device, dtype=torch.float32), self.inv_freq)
        cos, sin = ang.cos(), ang.sin()

        def rot(x):
            x1, x2 = x.float().chunk(2, dim=-1)
            return torch.cat([x1 * cos - x2 * sin, x1 * sin + x2 * cos], dim=-1).to(x.dtype)

        return rot(q), rot(k)


class Attention(nn.Module):
    def __init__(self, dim: int, heads: int, dim_head: int, dropout: float):
        super().__init__()
        self.heads, self.dim_head, self.dropout = heads, dim_head, dropout
        self.qkv = nn.Linear(dim, 3 * heads * dim_head, bias=False)
        self.out = nn.Linear(heads * dim_head, dim, bias=False)
        self.rotary = Rotary(dim_head)

    def forward(self, x):  # (N, L, D)
        n, l, _ = x.shape
        q, k, v = self.qkv(x).view(n, l, 3, self.heads, self.dim_head).permute(2, 0, 3, 1, 4)
        q, k = self.rotary(q, k)
        o = F.scaled_dot_product_attention(q, k, v, dropout_p=self.dropout if self.training else 0.0)
        return self.out(o.transpose(1, 2).reshape(n, l, self.heads * self.dim_head))


class FeedForward(nn.Module):
    def __init__(self, dim: int, expansion: int, activation: str):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(dim, dim * expansion), ACTIVATIONS[activation](),
                                 nn.Linear(dim * expansion, dim))

    def forward(self, x):
        return self.net(x)


class AxialBlock(nn.Module):
    """x: (B, Frames, Bands, D). Time attention -> FFN -> band(frequency) attention -> FFN, pre-norm residuals."""

    def __init__(self, dim, heads, dim_head, ff_expansion, activation, attn_dropout):
        super().__init__()
        self.norm_t, self.attn_t = RMSNorm(dim), Attention(dim, heads, dim_head, attn_dropout)
        self.norm_t2, self.ff_t = RMSNorm(dim), FeedForward(dim, ff_expansion, activation)
        self.norm_f, self.attn_f = RMSNorm(dim), Attention(dim, heads, dim_head, attn_dropout)
        self.norm_f2, self.ff_f = RMSNorm(dim), FeedForward(dim, ff_expansion, activation)

    def forward(self, x):
        b, fr, bd, d = x.shape
        t = x.permute(0, 2, 1, 3).reshape(b * bd, fr, d)
        t = t + self.attn_t(self.norm_t(t))
        t = t + self.ff_t(self.norm_t2(t))
        f = t.view(b, bd, fr, d).permute(0, 2, 1, 3).reshape(b * fr, bd, d)
        f = f + self.attn_f(self.norm_f(f))
        f = f + self.ff_f(self.norm_f2(f))
        return f.view(b, fr, bd, d)


def run_block(block: nn.Module, x: torch.Tensor, use_checkpoint: bool):
    if use_checkpoint and torch.is_grad_enabled():
        return checkpoint(block, x, use_reentrant=False)
    return block(x)
