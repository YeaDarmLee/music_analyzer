"""Generic trainer: optimizer / scheduler / loss / metrics / AMP / accumulation / clipping all come from config.

Resume is exact at optimizer-step boundaries: model, optimizer, scheduler, GradScaler, RNG state and the
(epoch, batch_in_epoch) data position are restored; the data order of an epoch depends only on seed + epoch.
"""
from __future__ import annotations

import itertools
import os
import random
from pathlib import Path
from typing import Callable

import numpy as np
import torch
from torch.utils.data import DataLoader

from engine.checkpoint import capture_rng, load_checkpoint, restore_rng, save_checkpoint
from engine.interfaces import SeparatorModel
from engine.registry import METRICS
from engine.training.losses import build_composite


class TrainingOOMError(RuntimeError):
    pass


def seed_everything(seed: int, deterministic: bool) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    if deterministic:
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        torch.use_deterministic_algorithms(True, warn_only=True)
        torch.backends.cudnn.benchmark = False


def resolve_device(name: str) -> torch.device:
    if name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dev = torch.device(name)
    if dev.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("training.device requests CUDA but it is not available")
    return dev


def _to_device(x, dev):
    if isinstance(x, torch.Tensor):
        return x.to(dev, non_blocking=True)
    if isinstance(x, dict):
        return {k: _to_device(v, dev) for k, v in x.items()}
    return x


class Trainer:
    def __init__(self, model: SeparatorModel, tcfg: dict, train_ds, val_ds, ckpt_dir: str | Path,
                 provenance: dict, log: Callable[[dict], None] = lambda e: None,
                 on_checkpoint: Callable[[Path, int], None] = lambda p, s: None):
        self.tcfg, self.train_ds, self.val_ds = tcfg, train_ds, val_ds
        self.ckpt_dir, self.prov, self.log, self.on_checkpoint = Path(ckpt_dir), provenance, log, on_checkpoint
        self.device = resolve_device(tcfg["device"])
        seed_everything(tcfg["seed"], tcfg["deterministic"])
        self.model = model.to(self.device)
        self.model.set_gradient_checkpointing(tcfg["gradient_checkpointing"])
        o = tcfg["optimizer"]
        self.optimizer = getattr(torch.optim, o["name"])(self.model.parameters(), lr=o["lr"], **o["kwargs"])
        s = tcfg["scheduler"]
        self.scheduler = getattr(torch.optim.lr_scheduler, s["name"])(self.optimizer, **s["kwargs"]) if s else None
        amp = tcfg["amp"]
        self.amp_enabled = amp["enabled"]
        self.amp_dtype = getattr(torch, amp["dtype"])
        self.scaler = torch.amp.GradScaler(
            "cuda", enabled=self.amp_enabled and self.amp_dtype == torch.float16 and self.device.type == "cuda")
        self.loss_fn = build_composite(tcfg["losses"])
        self.metric_fns = [(m["name"], METRICS.get(m["name"]), m["kwargs"]) for m in tcfg["metrics"]]
        self.step = self.epoch = self.batch_in_epoch = 0
        if len(train_ds) < tcfg["batch_size"]:
            raise ValueError("train dataset smaller than batch_size")

    # --- helpers -----------------------------------------------------------------------------------------
    def _loader(self, ds, shuffle: bool, epoch: int = 0) -> DataLoader:
        g = torch.Generator().manual_seed(self.tcfg["seed"] + epoch)
        return DataLoader(ds, batch_size=self.tcfg["batch_size"], shuffle=shuffle, generator=g if shuffle else None,
                          drop_last=shuffle, num_workers=0, pin_memory=self.device.type == "cuda")

    def _forward_loss(self, batch):
        mix = batch["mix"]
        with torch.autocast(device_type=self.device.type, dtype=self.amp_dtype, enabled=self.amp_enabled):
            out = self.model(mix)
            loss, parts = self.loss_fn(out, batch["stems"], mix)
        return out, loss, parts

    def _oom(self, e: BaseException) -> TrainingOOMError:
        if self.device.type == "cuda":
            peak = torch.cuda.max_memory_allocated(self.device) / (1 << 20)
            torch.cuda.empty_cache()
        else:
            peak = None
        return TrainingOOMError(
            f"out of memory at step {self.step} (batch_size={self.tcfg['batch_size']}, "
            f"grad_accum_steps={self.tcfg['grad_accum_steps']}, gradient_checkpointing={self.tcfg['gradient_checkpointing']}, "
            f"amp={self.amp_enabled}, peak_mib={peak}). Reduce batch_size / chunk_seconds, raise grad_accum_steps, "
            f"or enable gradient_checkpointing. Original: {e}")

    # --- checkpointing -----------------------------------------------------------------------------------
    def state(self) -> dict:
        return {
            "model": self.model.state_dict(), "optimizer": self.optimizer.state_dict(),
            "scheduler": self.scheduler.state_dict() if self.scheduler else None,
            "scaler": self.scaler.state_dict(), "step": self.step, "epoch": self.epoch,
            "batch_in_epoch": self.batch_in_epoch, "rng": capture_rng(),
        }

    def save(self) -> Path:
        path = self.ckpt_dir / f"step_{self.step:06d}.ckpt"
        save_checkpoint(path, self.state(), self.prov)
        self.on_checkpoint(path, self.step)
        return path

    def resume(self, path: str | Path) -> dict:
        state, prov = load_checkpoint(path, map_location=self.device)
        self.model.load_state_dict(state["model"])
        self.optimizer.load_state_dict(state["optimizer"])
        if self.scheduler and state["scheduler"]:
            self.scheduler.load_state_dict(state["scheduler"])
        self.scaler.load_state_dict(state["scaler"])
        self.step, self.epoch, self.batch_in_epoch = state["step"], state["epoch"], state["batch_in_epoch"]
        restore_rng(state["rng"])
        return prov

    # --- validation --------------------------------------------------------------------------------------
    @torch.no_grad()
    def validate(self) -> dict:
        self.model.eval()
        losses, sums, n = [], {name: 0.0 for name, _, _ in self.metric_fns}, 0
        try:
            for batch in itertools.islice(self._loader(self.val_ds, False), self.tcfg["val_batches"]):
                batch = _to_device(batch, self.device)
                out, loss, _ = self._forward_loss(batch)
                losses.append(float(loss))
                for name, fn, kw in self.metric_fns:
                    sums[name] += fn(out, batch["stems"], batch["mix"], **kw)
                n += 1
        except torch.cuda.OutOfMemoryError as e:
            raise self._oom(e) from e
        finally:
            self.model.train()
        if n == 0:
            raise ValueError("validation produced no batches")
        return {"val_loss": sum(losses) / n, **{f"val_{k}": v / n for k, v in sums.items()}}

    # --- training ----------------------------------------------------------------------------------------
    def fit(self, max_steps: int | None = None) -> dict:
        """Train until `max_steps` optimizer steps (default: config). Returns final validation metrics."""
        target = max_steps if max_steps is not None else self.tcfg["max_steps"]
        accum, clip = self.tcfg["grad_accum_steps"], self.tcfg["grad_clip_norm"]
        self.model.train()
        self.optimizer.zero_grad(set_to_none=True)
        micro = 0
        last_val: dict = {}
        while self.step < target:
            for i, batch in enumerate(self._loader(self.train_ds, True, self.epoch)):
                if i < self.batch_in_epoch:
                    continue
                batch = _to_device(batch, self.device)
                try:
                    _, loss, parts = self._forward_loss(batch)
                    self.scaler.scale(loss / accum).backward()
                except torch.cuda.OutOfMemoryError as e:
                    self.optimizer.zero_grad(set_to_none=True)
                    raise self._oom(e) from e
                micro += 1
                self.batch_in_epoch = i + 1
                if micro % accum:
                    continue
                self.scaler.unscale_(self.optimizer)
                gnorm = None
                if clip is not None:
                    gnorm = float(torch.nn.utils.clip_grad_norm_(self.model.parameters(), clip))
                self.scaler.step(self.optimizer)
                self.scaler.update()
                self.optimizer.zero_grad(set_to_none=True)
                if self.scheduler:
                    self.scheduler.step()
                self.step += 1
                self.log({"event": "train", "step": self.step, "loss": float(loss), "parts": parts,
                          "lr": self.optimizer.param_groups[0]["lr"], "grad_norm": gnorm})
                if self.step % self.tcfg["val_every"] == 0 or self.step == target:
                    last_val = self.validate()
                    self.log({"event": "val", "step": self.step, **last_val})
                if self.step % self.tcfg["checkpoint_every"] == 0 or self.step == target:
                    self.save()
                if self.step >= target:
                    break
            else:
                self.epoch += 1
                self.batch_in_epoch = 0
        return last_val
