"""Measured (not estimated) cost of a model config: params, VRAM, latency, RTF, FLOPs."""
from __future__ import annotations

import time

import torch
from torch.utils.flop_counter import FlopCounterMode

from engine.registry import build_model
from engine.training.losses import build_composite


def _sync(dev):
    if dev.type == "cuda":
        torch.cuda.synchronize(dev)


def _timed(fn, dev, reps):
    fn()  # warmup
    _sync(dev)
    t0 = time.perf_counter()
    for _ in range(reps):
        fn()
    _sync(dev)
    return (time.perf_counter() - t0) / reps * 1000


def profile_model(model_cfg: dict, loss_cfgs: list[dict], chunk_samples: int, batch_size: int = 1,
                  amp_dtype: str | None = "float16", checkpointing: bool = True, reps: int = 3,
                  device: str = "cuda") -> dict:
    dev = torch.device(device)
    torch.manual_seed(0)
    model = build_model(model_cfg).to(dev)
    model.set_gradient_checkpointing(checkpointing)
    loss_fn = build_composite(loss_cfgs)
    n_params = sum(p.numel() for p in model.parameters())
    res = {
        "params_total": n_params, "params_trainable": sum(p.numel() for p in model.parameters() if p.requires_grad),
        "fp32_checkpoint_mib": n_params * 4 / (1 << 20),
        "breakdown": model.parameter_breakdown() if hasattr(model, "parameter_breakdown") else None,
        "chunk_samples": chunk_samples, "batch_size": batch_size, "amp": amp_dtype, "gradient_checkpointing": checkpointing,
        "device": torch.cuda.get_device_name(dev) if dev.type == "cuda" else "cpu",
    }
    ch, sr = model_cfg["channels"], model_cfg["sample_rate"]
    mix = torch.randn(batch_size, ch, chunk_samples, device=dev) * 0.1
    tgt = {n: torch.randn_like(mix) * 0.05 for n in model_cfg["stems"]}
    ctx = lambda: torch.autocast(dev.type, dtype=getattr(torch, amp_dtype), enabled=amp_dtype is not None)

    model.train()

    def fwd():
        with ctx():
            return loss_fn(model(mix), tgt, mix)[0]

    def fwd_bwd():
        model.zero_grad(set_to_none=True)
        fwd().backward()

    if dev.type == "cuda":
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(dev)
    fwd_bwd()
    _sync(dev)
    res["train_peak_vram_mib"] = torch.cuda.max_memory_allocated(dev) / (1 << 20) if dev.type == "cuda" else None
    res["train_step_ms_fwd_bwd"] = _timed(fwd_bwd, dev, reps)
    res["train_fwd_ms"] = _timed(lambda: fwd().detach(), dev, reps)
    res["train_bwd_ms_est"] = res["train_step_ms_fwd_bwd"] - res["train_fwd_ms"]

    model.eval()
    if dev.type == "cuda":
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(dev)

    def infer():
        with torch.no_grad(), ctx():
            return model(mix)

    res["inference_ms"] = _timed(infer, dev, reps)
    res["inference_peak_vram_mib"] = torch.cuda.max_memory_allocated(dev) / (1 << 20) if dev.type == "cuda" else None
    res["rtf"] = res["inference_ms"] / 1000 / (batch_size * chunk_samples / sr)
    try:
        model.set_gradient_checkpointing(False)
        with torch.no_grad(), FlopCounterMode(display=False) as fc:
            model(mix)
        res["forward_flops"] = fc.get_total_flops()
    except Exception as e:  # pragma: no cover - counter coverage varies by op
        res["forward_flops"] = f"unavailable: {type(e).__name__}"
    res["frames"] = chunk_samples // model_cfg["params"].get("hop_length", 1) + 1
    return res
