"""OurSeparatorV01: complex STFT -> overlapping band projection -> shared axial T/F backbone ->
shared decoder trunk + band-specific output layers -> complex masks -> iSTFT -> output-consistency module.

Specification: docs/architecture/OUR_SEPARATOR_ARCHITECTURE.md (Research Packet 02). Written from the spec, not
copied from any RoFormer implementation. Nothing here knows the stem names or their count.
"""
from __future__ import annotations

import torch
from torch import nn

from engine.interfaces import SeparationOutput, SeparatorModel

from .band_map import bands_per_bin, build_band_slices
from .heads import MaskActivation, MixtureProjection
from .layers import AxialBlock, RMSNorm, run_block

PARAM_KEYS = ("n_fft", "hop_length", "win_length", "num_bands", "dim", "depth", "heads", "dim_head", "ff_expansion",
              "ff_activation", "attn_dropout", "decoder_hidden", "mask_activation", "mask_bound",
              "output_consistency_mode", "input_normalization", "norm_min_rms", "gradient_checkpointing")


class OurSeparatorV01(SeparatorModel):
    def __init__(self, stems: list[str], channels: int, sample_rate: int, p: dict):
        super().__init__()
        missing = [k for k in PARAM_KEYS if k not in p]
        if missing:
            raise KeyError(f"our_separator_v01 params missing: {missing}")
        if p["heads"] * p["dim_head"] != p["dim"]:
            raise ValueError("heads * dim_head must equal dim (spec: attention width == model dim)")
        self.stem_names, self.sample_rate, self.channels = list(stems), sample_rate, channels
        self.n_fft, self.hop, self.win = p["n_fft"], p["hop_length"], p["win_length"]
        self.input_norm, self.min_rms = p["input_normalization"], p["norm_min_rms"]
        self.use_ckpt = p["gradient_checkpointing"]
        dim = p["dim"]

        self.projection = MixtureProjection(p["output_consistency_mode"])
        self.num_predicted = self.projection.num_predicted(len(self.stem_names))
        self.mask_act = MaskActivation(p["mask_activation"], p["mask_bound"])

        n_bins = self.n_fft // 2 + 1
        self.band_slices = build_band_slices(sample_rate, self.n_fft, p["num_bands"])
        self.register_buffer("band_slices_buf", torch.tensor(self.band_slices, dtype=torch.int64))
        self.register_buffer("bins_per_band_count",
                             torch.from_numpy(bands_per_bin(self.band_slices, n_bins)).float(), persistent=False)
        self.register_buffer("window", torch.hann_window(self.win), persistent=False)

        widths = [hi - lo for lo, hi in self.band_slices]
        self.band_proj = nn.ModuleList([nn.Sequential(RMSNorm(channels * w * 2), nn.Linear(channels * w * 2, dim))
                                        for w in widths])
        self.blocks = nn.ModuleList([AxialBlock(dim, p["heads"], p["dim_head"], p["ff_expansion"], p["ff_activation"],
                                                p["attn_dropout"]) for _ in range(p["depth"])])
        act = nn.SiLU if p["ff_activation"] == "silu" else nn.GELU
        self.decoder_trunk = nn.Sequential(RMSNorm(dim), nn.Linear(dim, p["decoder_hidden"]), act(),
                                           nn.Linear(p["decoder_hidden"], dim))
        self.out_proj = nn.ModuleList([nn.Linear(dim, self.num_predicted * channels * w * 2) for w in widths])
        for m in self.out_proj:  # zero-init: masks start at 0 (bounded activation), outputs start as the projection of silence
            nn.init.zeros_(m.weight)
            nn.init.zeros_(m.bias)

    def set_gradient_checkpointing(self, enabled: bool) -> None:
        self.use_ckpt = enabled

    def load_state_dict(self, state_dict, strict: bool = True, assign: bool = False):
        saved = state_dict.get("band_slices_buf")
        if saved is not None and not torch.equal(saved.cpu(), self.band_slices_buf.cpu()):
            raise ValueError("checkpoint band layout differs from this model's band layout")
        return super().load_state_dict(state_dict, strict=strict, assign=assign)

    # ---------------------------------------------------------------------------------------------------
    def forward(self, mix: torch.Tensor) -> SeparationOutput:
        b, c, t = mix.shape
        if c != self.channels:
            raise ValueError(f"expected {self.channels} channels, got {c}")
        x = mix.float()
        if self.input_norm:  # one scale per chunk, shared by mixture and (via aux) targets
            scale = x.pow(2).mean(dim=(1, 2), keepdim=True).sqrt().clamp_min(self.min_rms)
        else:
            scale = torch.ones(b, 1, 1, device=x.device)
        x = x / scale

        with torch.autocast(device_type=x.device.type, enabled=False):
            spec = torch.stft(x.reshape(b * c, t), self.n_fft, self.hop, self.win, window=self.window,
                              center=True, return_complex=True)
        n_bins, frames = spec.shape[-2:]
        spec = spec.view(b, c, n_bins, frames)

        feats = []
        for (lo, hi), proj in zip(self.band_slices, self.band_proj):
            f = torch.view_as_real(spec[:, :, lo:hi]).permute(0, 3, 1, 2, 4).reshape(b, frames, -1)
            feats.append(proj(f))
        h = torch.stack(feats, dim=2)  # (B, Frames, Bands, D)
        for blk in self.blocks:
            h = run_block(blk, h, self.use_ckpt and self.training)
        h = self.decoder_trunk(h)

        with torch.autocast(device_type=x.device.type, enabled=False):
            raw = torch.zeros(b, self.num_predicted, c, n_bins, frames, 2, device=x.device)
            for i, ((lo, hi), proj) in enumerate(zip(self.band_slices, self.out_proj)):
                y = proj(h[:, :, i].float()).view(b, frames, self.num_predicted, c, hi - lo, 2)
                raw[:, :, :, lo:hi] += y.permute(0, 2, 3, 4, 1, 5)
            raw = raw / self.bins_per_band_count.view(1, 1, 1, n_bins, 1, 1)
            mask = torch.view_as_complex(self.mask_act(raw).contiguous())
            est = spec[:, None] * mask
            wav = torch.istft(est.reshape(-1, n_bins, frames), self.n_fft, self.hop, self.win, window=self.window,
                              center=True, length=t).view(b, self.num_predicted, c, t)
            final = self.projection(x, wav)

        final = final * scale[:, None]
        aux = {"input_scale": scale}
        aux.update({f"raw_{n}": (wav[:, i] * scale) for i, n in enumerate(self.stem_names[:self.num_predicted])})
        return SeparationOutput(
            stems={n: final[:, i] for i, n in enumerate(self.stem_names)}, sample_rate=self.sample_rate,
            metadata={"model": "our_separator_v01", "output_consistency_mode": self.projection.mode}, aux=aux)

    # ---------------------------------------------------------------------------------------------------
    def parameter_breakdown(self) -> dict[str, int]:
        n = lambda m: sum(p.numel() for p in m.parameters())
        return {"band_projector": n(self.band_proj), "backbone": n(self.blocks),
                "decoder_trunk": n(self.decoder_trunk), "output_projection": n(self.out_proj),
                "total": n(self)}


def build(cfg: dict) -> OurSeparatorV01:
    return OurSeparatorV01(cfg["stems"], cfg["channels"], cfg["sample_rate"], cfg["params"])
