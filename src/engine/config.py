"""Config loading and validation.

Four independent groups: model / training / dataset / experiment. Required keys are checked,
but no architecture or training value gets a default here: a missing value is an error.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .hashing import hash_obj

NONE = type(None)


class ConfigError(ValueError):
    pass


def load_yaml(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return data


def _check(cfg: dict, spec: dict[str, Any], where: str) -> None:
    problems = []
    for key, typ in spec.items():
        if key not in cfg:
            problems.append(f"missing '{key}'")
            continue
        types = typ if isinstance(typ, tuple) else (typ,)
        v = cfg[key]
        if isinstance(v, bool) and bool not in types:
            problems.append(f"'{key}' must not be bool")
        elif not isinstance(v, types):
            problems.append(f"'{key}' must be {'/'.join(t.__name__ for t in types)}, got {type(v).__name__}")
    if problems:
        raise ConfigError(f"{where}: " + "; ".join(problems))


MODEL_SPEC = {"model_id": str, "sample_rate": int, "channels": int, "stems": list, "params": dict}
TRAINING_SPEC = {
    "seed": int, "device": str, "deterministic": bool, "max_steps": int, "batch_size": int,
    "optimizer": dict, "scheduler": (dict, NONE), "amp": dict, "grad_accum_steps": int,
    "grad_clip_norm": (int, float, NONE), "gradient_checkpointing": bool,
    "losses": list, "metrics": list, "val_every": int, "val_batches": int, "checkpoint_every": int,
}
DATASET_SPEC = {"name": str, "kind": str, "usage": str, "chunk_seconds": (int, float), "params": dict}
EXPERIMENT_SPEC = {"name": str, "output_root": str, "model": str, "training": str, "dataset": str}


def validate_model(cfg: dict) -> dict:
    _check(cfg, MODEL_SPEC, "model config")
    if not cfg["stems"] or len(set(cfg["stems"])) != len(cfg["stems"]):
        raise ConfigError("model config: 'stems' must be a non-empty list of unique names")
    return cfg


def validate_training(cfg: dict) -> dict:
    _check(cfg, TRAINING_SPEC, "training config")
    _check(cfg["optimizer"], {"name": str, "lr": (int, float), "kwargs": dict}, "training.optimizer")
    _check(cfg["amp"], {"enabled": bool, "dtype": str}, "training.amp")
    if cfg["amp"]["dtype"] not in ("float16", "bfloat16"):
        raise ConfigError("training.amp.dtype must be float16 or bfloat16")
    if cfg["scheduler"] is not None:
        _check(cfg["scheduler"], {"name": str, "kwargs": dict}, "training.scheduler")
    for i, l in enumerate(cfg["losses"]):
        _check(l, {"name": str, "weight": (int, float), "kwargs": dict}, f"training.losses[{i}]")
    for i, m in enumerate(cfg["metrics"]):
        _check(m, {"name": str, "kwargs": dict}, f"training.metrics[{i}]")
    if not cfg["losses"]:
        raise ConfigError("training: at least one loss is required")
    if min(cfg["grad_accum_steps"], cfg["batch_size"], cfg["max_steps"]) < 1:
        raise ConfigError("training: grad_accum_steps, batch_size, max_steps must be >= 1")
    return cfg


def validate_dataset(cfg: dict) -> dict:
    _check(cfg, DATASET_SPEC, "dataset config")
    return cfg


@dataclass(frozen=True)
class ExperimentConfig:
    experiment: dict
    model: dict
    training: dict
    dataset: dict
    source_files: dict

    @property
    def hashes(self) -> dict[str, str]:
        return {k: hash_obj(getattr(self, k)) for k in ("model", "training", "dataset")}


def load_experiment(path: str | Path) -> ExperimentConfig:
    """The experiment file names model/training/dataset files relative to the configs root
    (the parent of the folder that holds the experiment file)."""
    path = Path(path).resolve()
    exp = load_yaml(path)
    _check(exp, EXPERIMENT_SPEC, "experiment config")
    root = path.parent.parent
    files = {k: root / exp[k] for k in ("model", "training", "dataset")}
    return ExperimentConfig(
        experiment=exp,
        model=validate_model(load_yaml(files["model"])),
        training=validate_training(load_yaml(files["training"])),
        dataset=validate_dataset(load_yaml(files["dataset"])),
        source_files={k: str(v) for k, v in files.items()} | {"experiment": str(path)},
    )
