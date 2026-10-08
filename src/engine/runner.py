"""Config-driven end-to-end run: manifest check -> train -> checkpoint+provenance -> reload -> inference -> metrics."""
from __future__ import annotations

import importlib
from pathlib import Path

import torch

import engine.data.synthetic  # noqa: F401  (registers dataset kinds)
from engine.checkpoint import load_checkpoint
from engine.config import ExperimentConfig, load_experiment
from engine.data.manifest import load_manifest, require_valid
from engine.experiment import Run
from engine.inference import separate
from engine.provenance import git_info, parent_ref
from engine.registry import DATASETS, METRICS, build_model
from engine.training.metrics import measure_inference
from engine.training.trainer import Trainer, resolve_device


def configs_root(cfg: ExperimentConfig) -> Path:
    return Path(cfg.source_files["experiment"]).parent.parent


def run_experiment(experiment_path: str | Path, base_dir: str | Path = ".", resume: str | Path | None = None,
                   max_steps: int | None = None, parent_checkpoint: str | Path | None = None) -> dict:
    cfg = load_experiment(experiment_path)
    manifest_path = configs_root(cfg) / cfg.dataset["params"]["manifest"]
    manifest_sha = require_valid(load_manifest(manifest_path), cfg.dataset["usage"])  # raises on policy violation

    if "plugin" in cfg.dataset:  # dataset provider package (e.g. data_factory.adapter) registers its own DATASETS kind
        importlib.import_module(cfg.dataset["plugin"])
    run = Run.create(cfg, manifest_sha, base_dir)
    seed = cfg.training["seed"]
    model_cfg = cfg.model
    train_ds = DATASETS.get(cfg.dataset["kind"])(cfg.dataset, model_cfg, "train", seed)
    val_ds = DATASETS.get(cfg.dataset["kind"])(cfg.dataset, model_cfg, "val", seed)

    prov = {
        "model_id": model_cfg["model_id"], "model_config_hash": cfg.hashes["model"],
        "training_config_hash": cfg.hashes["training"], "dataset_manifest_sha256": manifest_sha,
        "training_run_id": run.id, "git_commit": git_info()["git_commit"],
        "parent_checkpoint": parent_ref(parent_checkpoint),
        "dataset_usage": cfg.dataset["usage"],
    }
    trainer = Trainer(build_model(model_cfg), cfg.training, train_ds, val_ds, run.ckpt_dir, prov,
                      log=run.log, on_checkpoint=run.add_checkpoint)
    if resume:
        trainer.resume(resume)
    try:
        val = trainer.fit(max_steps)
    except Exception as e:
        run.finalize({}, status=f"failed: {type(e).__name__}")
        raise

    last = run.root / run.meta["checkpoints"][-1]["path"]
    result = evaluate_checkpoint(last, cfg, val_ds)
    result["train_val"] = val
    if cfg.training.get("final_test") and "test" in cfg.dataset["params"].get("num_scenes", {}):  # test split: final only
        test_ds = DATASETS.get(cfg.dataset["kind"])(cfg.dataset, model_cfg, "test", seed)
        result["test"] = trainer.evaluate(test_ds, "test")
    run.finalize(result)
    return {"run_dir": run.root, "checkpoint": last, **result}


def evaluate_checkpoint(ckpt: str | Path, cfg: ExperimentConfig, val_ds, device: str | None = None) -> dict:
    """Reload from disk (sidecar-verified), run inference on one validation item, compute configured metrics."""
    dev = resolve_device(device or cfg.training["device"])
    state, prov = load_checkpoint(ckpt, map_location=dev)
    model = build_model(cfg.model).to(dev)
    model.load_state_dict(state["model"])
    item = val_ds[0]
    mix, stems = item["mix"], item["stems"]
    secs = mix.shape[-1] / cfg.model["sample_rate"]
    holder = {}
    perf = measure_inference(lambda: holder.update(out=separate(model, mix, device=dev)), secs, dev)
    out = holder["out"]
    batch_t = {k: v[None] for k, v in stems.items()}
    metrics = {m["name"]: METRICS.get(m["name"])(out_b(out), batch_t, mix[None], **m["kwargs"])
               for m in cfg.training["metrics"]}
    return {"checkpoint_step": state["step"], "provenance": prov, "inference": perf, "metrics": metrics}


def out_b(out):
    """separate() returns unbatched stems for 2-D input; metrics expect a batch dim."""
    from engine.interfaces import SeparationOutput
    return SeparationOutput({k: v[None] for k, v in out.stems.items()}, out.sample_rate, out.metadata)
