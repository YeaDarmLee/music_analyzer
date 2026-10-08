from __future__ import annotations

import copy
from pathlib import Path

import pytest
import torch

import engine.data.synthetic  # noqa: F401
from engine.config import load_experiment
from engine.registry import DATASETS, build_model

CONFIGS = Path(__file__).resolve().parents[1] / "configs"
EXPERIMENT = CONFIGS / "experiment" / "phase2_smoke.yaml"


@pytest.fixture
def cfg():
    return load_experiment(EXPERIMENT)


@pytest.fixture
def tcfg(cfg):
    """CPU, deterministic copy of the smoke training config (unit tests must not depend on a GPU)."""
    t = copy.deepcopy(cfg.training)
    t["device"] = "cpu"
    return t


@pytest.fixture
def datasets(cfg):
    mk = lambda split: DATASETS.get(cfg.dataset["kind"])(cfg.dataset, cfg.model, split, cfg.training["seed"])
    return mk("train"), mk("val")


def make_model(cfg, seed=0):
    torch.manual_seed(seed)
    return build_model(cfg.model)


PROV = {
    "model_id": "tiny_test_separator", "model_config_hash": "m" * 8, "training_config_hash": "t" * 8,
    "dataset_manifest_sha256": "d" * 8, "training_run_id": "run-test", "git_commit": None, "parent_checkpoint": None,
}
