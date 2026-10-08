"""Generic trainer: optimizer / scheduler / loss / metrics / AMP / accumulation / clipping all come from config.

Resume is exact at optimizer-step boundaries: model, optimizer, scheduler, GradScaler, RNG state and the
(epoch, batch_in_epoch) data position are restored; the data order of an epoch depends only on seed + epoch.
"""
from __future__ import annotations

import itertools
import json
import os
import random
import subprocess
import time
from pathlib import Path
from typing import Callable

import numpy as np
import torch
from torch.utils.data import DataLoader

from engine.checkpoint import capture_rng, load_checkpoint, restore_rng, save_checkpoint
from engine.interfaces import SeparatorModel
from engine.registry import METRICS
from engine.training.losses import build_composite
from engine.training.metrics import ValAggregator


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
        self.plateau = isinstance(self.scheduler, torch.optim.lr_scheduler.ReduceLROnPlateau)
        self.monitor = s.get("monitor") if s else None
        if self.plateau and not self.monitor:
            raise ValueError("ReduceLROnPlateau needs training.scheduler.monitor (a validation metric key)")
        amp = tcfg["amp"]
        self.amp_enabled = amp["enabled"]
        self.amp_dtype = getattr(torch, amp["dtype"])
        self.scaler = torch.amp.GradScaler(
            "cuda", enabled=self.amp_enabled and self.amp_dtype == torch.float16 and self.device.type == "cuda")
        self.loss_fn = build_composite(tcfg["losses"])
        self.metric_fns = [(m["name"], METRICS.get(m["name"]), m["kwargs"]) for m in tcfg["metrics"]]
        self.step = self.epoch = self.batch_in_epoch = 0
        self.best: dict = {}  # metadata only: best value + step per tracked metric (checkpoints are pruned, see _prune)
        self._psutil = None
        try:
            import psutil
            self._psutil = psutil
            psutil.cpu_percent(None)
        except ImportError:
            pass
        if len(train_ds) < tcfg["batch_size"]:
            raise ValueError("train dataset smaller than batch_size")

    # --- helpers -----------------------------------------------------------------------------------------
    def _loader(self, ds, shuffle: bool, epoch: int = 0) -> DataLoader:
        g = torch.Generator().manual_seed(self.tcfg["seed"] + epoch)
        nw = int(self.tcfg.get("num_workers", 0))  # optional; data order does not depend on it (sampler seeded by seed+epoch)
        return DataLoader(ds, batch_size=self.tcfg["batch_size"], shuffle=shuffle, generator=g if shuffle else None,
                          drop_last=shuffle, num_workers=nw, persistent_workers=False, pin_memory=self.device.type == "cuda")

    def _forward_loss(self, batch):
        mix = batch["mix"]
        with torch.autocast(device_type=self.device.type, dtype=self.amp_dtype, enabled=self.amp_enabled):
            out = self.model(mix)
            loss, parts = self.loss_fn(out, batch["stems"], mix, batch.get("active"))
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
        self._prune()
        return path

    def _prune(self) -> None:
        """keep_recent (optional): keep the N newest step checkpoints plus the best-val_si_sdr one; best.json tracks the rest."""
        keep = self.tcfg.get("keep_recent")
        if not keep:
            return
        ckpts = sorted(self.ckpt_dir.glob("step_*.ckpt"))
        protect = {f"step_{self.best['val_si_sdr']['step']:06d}.ckpt"} if "val_si_sdr" in self.best else set()
        for p in ckpts[:-keep]:
            if p.name not in protect:
                p.unlink()
                side = p.with_name(p.name + ".provenance.json")
                if side.exists():
                    side.unlink()

    def _track_best(self, val: dict) -> None:
        for key in ("val_si_sdr", "val_si_sdr_vocals", "val_si_sdr_instrumental"):
            v = val.get(key)
            if v is not None and v == v and (key not in self.best or v > self.best[key]["value"]):
                self.best[key] = {"value": v, "step": self.step}
        self.ckpt_dir.mkdir(parents=True, exist_ok=True)
        (self.ckpt_dir / "best.json").write_text(json.dumps(self.best, indent=1), encoding="utf-8")

    def resume(self, path: str | Path) -> dict:
        state, prov = load_checkpoint(path, map_location=self.device)
        self.model.load_state_dict(state["model"])
        self.optimizer.load_state_dict(state["optimizer"])
        if self.scheduler and state["scheduler"]:
            self.scheduler.load_state_dict(state["scheduler"])
        self.scaler.load_state_dict(state["scaler"])
        self.step, self.epoch, self.batch_in_epoch = state["step"], state["epoch"], state["batch_in_epoch"]
        restore_rng(state["rng"])
        b = Path(path).parent / "best.json"
        if b.exists():
            self.best = json.loads(b.read_text(encoding="utf-8"))
        return prov

    # --- validation --------------------------------------------------------------------------------------
    @torch.no_grad()
    def validate(self, ds=None) -> dict:
        ds = ds if ds is not None else self.val_ds
        self.model.eval()
        losses, sums, n = [], {name: 0.0 for name, _, _ in self.metric_fns}, 0
        counts = {name: 0 for name, _, _ in self.metric_fns}
        agg = ValAggregator()
        try:
            for batch in itertools.islice(self._loader(ds, False), self.tcfg["val_batches"]):
                group = batch.pop("group", None)
                batch.pop("telemetry", None)
                batch = _to_device(batch, self.device)
                out, loss, _ = self._forward_loss(batch)
                losses.append(float(loss))
                for name, fn, kw in self.metric_fns:
                    v = fn(out, batch["stems"], batch["mix"], active=batch.get("active"), **kw)
                    if v == v:  # NaN = metric undefined for this batch (e.g. no active item)
                        sums[name] += v
                        counts[name] += 1
                agg.add(out, batch["stems"], batch["mix"], batch.get("active"), group)
                n += 1
        except torch.cuda.OutOfMemoryError as e:
            raise self._oom(e) from e
        finally:
            self.model.train()
        if n == 0:
            raise ValueError("validation produced no batches")
        return {"val_loss": sum(losses) / n, **{f"val_{k}": (v / counts[k] if counts[k] else float("nan")) for k, v in sums.items()},
                **agg.summary()}

    def evaluate(self, ds, event: str = "test") -> dict:
        res = self.validate(ds)
        self.log({"event": event, "step": self.step, **res})
        return res

    @staticmethod
    def _gpu_util():
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"], capture_output=True,
                               text=True, timeout=5)
            return float(r.stdout.strip().splitlines()[0])
        except Exception:
            return None

    def _timed(self, loader):
        """Iterate a DataLoader while accumulating the time spent blocked waiting for the next batch."""
        it = iter(loader)
        while True:
            t = time.perf_counter()
            try:
                b = next(it)
            except StopIteration:
                return
            self._wait += time.perf_counter() - t
            yield b

    # --- training ----------------------------------------------------------------------------------------
    def fit(self, max_steps: int | None = None) -> dict:
        """Train until `max_steps` optimizer steps (default: config). Returns final validation metrics."""
        target = max_steps if max_steps is not None else self.tcfg["max_steps"]
        accum, clip = self.tcfg["grad_accum_steps"], self.tcfg["grad_clip_norm"]
        self.model.train()
        self.optimizer.zero_grad(set_to_none=True)
        micro = 0
        last_val: dict = {}
        self._wait, t_step, tele = 0.0, time.perf_counter(), {"load_s": [], "hit": []}
        while self.step < target:
            if hasattr(self.train_ds, "set_epoch"):
                self.train_ds.set_epoch(self.epoch)  # epoch-dependent crop (deterministic: depends only on the epoch)
            for i, batch in enumerate(self._timed(self._loader(self.train_ds, True, self.epoch))):
                if i < self.batch_in_epoch:
                    continue
                batch.pop("group", None)
                t = batch.pop("telemetry", None)
                if t:
                    tele["load_s"] += t["load_s"].tolist()
                    tele["hit"] += t["hit"].tolist()
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
                if self.scheduler and not self.plateau:
                    self.scheduler.step()
                self.step += 1
                now = time.perf_counter()
                perf = {"step_s": now - t_step, "data_wait_s": self._wait, "chunks_per_s": accum * self.tcfg["batch_size"] / (now - t_step),
                        "epoch": self.epoch, "cache_hit_rate": sum(tele["hit"]) / max(len(tele["hit"]), 1),
                        "item_load_s": sum(tele["load_s"]) / max(len(tele["load_s"]), 1)}
                if self.device.type == "cuda":
                    perf["peak_vram_mib"] = torch.cuda.max_memory_allocated(self.device) / (1 << 20)
                    if self.step % 25 == 0 or self.step <= 5:
                        perf["gpu_util_pct"] = self._gpu_util()
                if self._psutil and (self.step % 25 == 0 or self.step <= 5):
                    perf["cpu_util_pct"] = self._psutil.cpu_percent(None)
                self._wait, t_step, tele = 0.0, now, {"load_s": [], "hit": []}
                self.log({"event": "train", "step": self.step, "loss": float(loss), "parts": parts,
                          "lr": self.optimizer.param_groups[0]["lr"], "grad_norm": gnorm, **perf})
                if self.step % self.tcfg["val_every"] == 0 or self.step == target:
                    last_val = self.validate()
                    self._track_best(last_val)
                    self.log({"event": "val", "step": self.step, **last_val})
                    t_step = time.perf_counter()
                    if self.plateau:
                        self.scheduler.step(last_val[self.monitor])
                if self.step % self.tcfg["checkpoint_every"] == 0 or self.step == target:
                    self.save()
                if self.step >= target:
                    break
            else:
                self.epoch += 1
                self.batch_in_epoch = 0
        return last_val
