"""Loss registry + composition. Phase 2 ships only trivial waveform losses to exercise the plumbing.

Loss signature: fn(out: SeparationOutput, target: dict[str, Tensor], mix: Tensor, **kwargs) -> scalar tensor.
Real loss candidates (spectral, multi-res STFT, SI-SDR, mixture consistency, leakage, hierarchy, ...) are added
after the Research Packets; each one is switched on/off purely from `training.losses` in config.
"""
from __future__ import annotations

import torch

from engine.registry import LOSSES


def _scale(out):
    return out.aux.get("input_scale") if hasattr(out, "aux") else None


def _pairs(out, target, use_input_scale: bool = True):
    """(pred, target) float pairs. If the model reports the chunk scale it used for input normalization
    (aux["input_scale"], shape (B,1,1)), both sides are divided by it so loud chunks do not dominate."""
    names = [n for n in out.stems if n in target]
    if not names:
        raise KeyError(f"no common stems between output {list(out.stems)} and target {list(target)}")
    sc = _scale(out) if use_input_scale else None
    div = (lambda x: x.float() / sc) if sc is not None else (lambda x: x.float())
    return [(div(out.stems[n]), div(target[n])) for n in names]


@LOSSES.register("waveform_l1")
def waveform_l1(out, target, mix, use_input_scale=True, **_):
    return torch.stack([(p - t).abs().mean() for p, t in _pairs(out, target, use_input_scale)]).mean()


@LOSSES.register("waveform_l2")
def waveform_l2(out, target, mix, use_input_scale=True, **_):
    return torch.stack([((p - t) ** 2).mean() for p, t in _pairs(out, target, use_input_scale)]).mean()


@LOSSES.register("multires_stft")
def multires_stft(out, target, mix, resolutions, use_input_scale=True, eps=1e-7, sc_floor_rel=None,
                  inactive_linear_weight=1.0, linear_weight=0.0, active=None, **_):
    """Mean over resolutions of a per-item spectral term. resolutions: [[n_fft, hop, win], ...].

    active=None (no activity metadata) :
        spectral convergence + log-magnitude L1 for every item (Research Packet 02 form). With sc_floor_rel=None the
        convergence uses the whole-batch target norm and explodes (~1e10, measured) for exactly-silent targets;
        sc_floor_rel=r bounds it with a per-item denominator max(|T|, r*|M|) (numerical-safety fallback only).
    active={stem: bool tensor (B,)} (Data Factory knows which stems are inactive) :
        active items   -> spectral convergence + log magnitude (+ linear_weight * linear magnitude L1)
        inactive items -> inactive_linear_weight * linear magnitude L1 (absolute spectral error); spectral convergence and
                          the log term are NOT computed, since relative error against a silent target is meaningless."""
    terms = []
    sc_in = _scale(out) if use_input_scale else None
    m_all = mix.float() / sc_in if sc_in is not None else mix.float()
    names = [n for n in out.stems if n in target]
    for n, (p, t) in zip(names, _pairs(out, target, use_input_scale)):
        b = p.shape[0]
        act = None
        if active is not None and n in active:
            act = active[n].to(p.device).bool().reshape(b)
        p, t = p.reshape(-1, p.shape[-1]), t.reshape(-1, t.shape[-1])
        m = m_all.reshape(-1, m_all.shape[-1])
        for n_fft, hop, win in resolutions:
            w = torch.hann_window(win, device=p.device)
            P = torch.stft(p, n_fft, hop, win, window=w, return_complex=True).abs()
            T = torch.stft(t, n_fft, hop, win, window=w, return_complex=True).abs()
            if act is None and sc_floor_rel is None:
                sc = torch.linalg.vector_norm(T - P) / torch.linalg.vector_norm(T).clamp_min(eps)
                lm = (torch.log(T + eps) - torch.log(P + eps)).abs().mean()
                terms.append(sc + lm)
                continue
            num = torch.linalg.vector_norm((T - P).reshape(b, -1), dim=1)
            nt = torch.linalg.vector_norm(T.reshape(b, -1), dim=1)
            if sc_floor_rel is not None:
                M = torch.stft(m, n_fft, hop, win, window=w, return_complex=True).abs()
                nt = torch.maximum(nt, sc_floor_rel * torch.linalg.vector_norm(M.reshape(b, -1), dim=1))
            keep = act if act is not None else torch.ones(b, dtype=torch.bool, device=p.device)
            sc = num / torch.where(keep, nt.clamp_min(eps), torch.ones_like(nt))  # safe denominator: no inf in masked rows
            lm = (torch.log(T + eps) - torch.log(P + eps)).abs().reshape(b, -1).mean(1)
            lin = (T - P).abs().reshape(b, -1).mean(1)
            item = torch.where(keep, sc + lm + linear_weight * lin, inactive_linear_weight * lin)
            terms.append(item.mean())
    return torch.stack(terms).mean()


@LOSSES.register("si_sdr")
def si_sdr_loss(out, target, mix, use_input_scale=True, eps=1e-8, **_):
    """Negative SI-SDR in dB (minimize). Registered but off by default."""
    vals = []
    for p, t in _pairs(out, target, use_input_scale):
        p, t = p.reshape(p.shape[0], -1), t.reshape(t.shape[0], -1)
        p, t = p - p.mean(-1, keepdim=True), t - t.mean(-1, keepdim=True)
        proj = (p * t).sum(-1, keepdim=True) / (t ** 2).sum(-1, keepdim=True).clamp_min(eps) * t
        vals.append(10 * torch.log10((proj ** 2).sum(-1).clamp_min(eps) / ((p - proj) ** 2).sum(-1).clamp_min(eps)))
    return -torch.stack(vals).mean()


@LOSSES.register("mixture_l1")
def mixture_l1(out, target, mix, use_input_scale=True, **_):
    """|mix - sum(stems)| for output_consistency_mode=soft (B). Meaningless under `project`."""
    sc = _scale(out) if use_input_scale else None
    total = sum(out.stems.values()).float()
    m = mix.float()
    if sc is not None:
        total, m = total / sc, m / sc
    return (m - total).abs().mean()


def build_composite(loss_cfgs: list[dict]):
    """Returns fn(out, target, mix) -> (total, {name: value}). Terms with weight 0 are skipped."""
    terms = [(c["name"], float(c["weight"]), LOSSES.get(c["name"]), c["kwargs"]) for c in loss_cfgs if c["weight"] != 0]
    if not terms:
        raise ValueError("all loss weights are zero")

    def composite(out, target, mix, active=None):
        total, parts = 0.0, {}
        for name, w, fn, kw in terms:
            v = fn(out, target, mix, active=active, **kw)
            parts[name] = float(v.detach())
            total = total + w * v
        return total, parts

    return composite
