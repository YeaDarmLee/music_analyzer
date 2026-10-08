"""Local experiment tracking (no external service).

runs/<experiment_id>/
    experiment.json        id, timestamp, git, hashes, seed, environment, checkpoints, final metrics, status
    config/                verbatim copies of experiment/model/training/dataset YAML
    checkpoints/           step_XXXXXX.ckpt + .ckpt.provenance.json
    metrics.jsonl          one JSON object per logged event
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .config import ExperimentConfig
from .hashing import hash_obj
from .provenance import environment_info, git_info


class Run:
    def __init__(self, root: Path, meta: dict):
        self.root, self.meta = root, meta
        self.ckpt_dir = root / "checkpoints"
        self._metrics = root / "metrics.jsonl"

    @property
    def id(self) -> str:
        return self.meta["experiment_id"]

    @classmethod
    def create(cls, cfg: ExperimentConfig, dataset_manifest_hash: str, base_dir: str | Path = ".") -> "Run":
        now = datetime.now(timezone.utc)
        hashes = cfg.hashes
        eid = f"{now:%Y%m%dT%H%M%S}-{cfg.experiment['name']}-{hash_obj(hashes)[:8]}"
        root = Path(base_dir) / cfg.experiment["output_root"] / eid
        (root / "config").mkdir(parents=True)
        (root / "checkpoints").mkdir()
        for k, f in cfg.source_files.items():
            shutil.copyfile(f, root / "config" / f"{k}.yaml")
        meta = {
            "experiment_id": eid, "name": cfg.experiment["name"], "timestamp": now.isoformat(timespec="seconds"),
            **git_info(), "seed": cfg.training["seed"],
            "model_config": cfg.model, "training_config": cfg.training,
            "model_config_hash": hashes["model"], "training_config_hash": hashes["training"],
            "dataset_config_hash": hashes["dataset"], "dataset_manifest_hash": dataset_manifest_hash,
            "environment": environment_info(), "checkpoints": [], "metrics": {}, "status": "running",
        }
        run = cls(root, meta)
        run._write()
        return run

    def _write(self) -> None:
        (self.root / "experiment.json").write_text(json.dumps(self.meta, indent=2, sort_keys=True), encoding="utf-8")

    def log(self, event: dict) -> None:
        with open(self._metrics, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")

    def add_checkpoint(self, path: Path, step: int) -> None:
        self.meta["checkpoints"].append({"step": step, "path": str(path.relative_to(self.root))})
        self._write()

    def finalize(self, metrics: dict, status: str = "completed") -> None:
        self.meta["metrics"], self.meta["status"] = metrics, status
        self._write()
