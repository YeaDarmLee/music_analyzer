"""Phase 2 unit tests (CPU unless marked cuda). The Phase 2 model is TinyTestSeparator, a fixture."""
from __future__ import annotations

import copy
import json

import pytest
import torch

from conftest import CONFIGS, EXPERIMENT, PROV, make_model
from engine.checkpoint import load_checkpoint, save_checkpoint
from engine.config import ConfigError, load_experiment, validate_training
from engine.data.manifest import ManifestError, load_manifest, manifest_hash, require_valid, validate_manifest
from engine.hashing import hash_obj, sha256_file
from engine.inference import separate
from engine.interfaces import SeparationOutput
from engine.provenance import ProvenanceError, parent_ref, read_sidecar, sidecar_path
from engine.registry import LOSSES, METRICS, MODELS, Registry, build_model
from engine.runner import run_experiment
from engine.training.metrics import sdr_db, si_sdr_db
from engine.training.trainer import Trainer, TrainingOOMError


def trainer_for(cfg, tcfg, datasets, tmp_path, seed=0, name="ck"):
    return Trainer(make_model(cfg, seed), tcfg, datasets[0], datasets[1], tmp_path / name, dict(PROV))


# 1 config -------------------------------------------------------------------------------------------------
def test_config_load_and_hash_stable(cfg):
    assert cfg.model["model_id"] == "tiny_test_separator"
    assert hash_obj({"a": 1, "b": [1, 2]}) == hash_obj({"b": [1, 2], "a": 1})
    assert len(cfg.hashes["model"]) == 64


def test_config_validation_errors(cfg):
    t = copy.deepcopy(cfg.training)
    del t["optimizer"]
    with pytest.raises(ConfigError, match="optimizer"):
        validate_training(t)
    t = copy.deepcopy(cfg.training)
    t["seed"] = True  # bool is not an int here
    with pytest.raises(ConfigError, match="seed"):
        validate_training(t)
    t = copy.deepcopy(cfg.training)
    t["losses"] = []
    with pytest.raises(ConfigError, match="loss"):
        validate_training(t)


# 2 registry -----------------------------------------------------------------------------------------------
def test_registry(cfg):
    build_model(cfg.model)
    assert {"tiny_test_separator", "dummy_split"} <= set(MODELS.names())
    assert "waveform_l1" in LOSSES.names() and "si_sdr" in METRICS.names()
    with pytest.raises(KeyError, match="unknown model"):
        MODELS.get("kj_melband")  # legacy models are deliberately not registered
    r = Registry("x")
    r.register("a")(lambda: 1)
    with pytest.raises(KeyError):
        r.register("a")(lambda: 2)


# 3 forward / 14 inference interface ---------------------------------------------------------------------
def test_tiny_forward_and_inference_interface(cfg, datasets):
    m = make_model(cfg)
    item = datasets[0][0]
    out = m(item["mix"][None])
    assert isinstance(out, SeparationOutput) and list(out.stems) == cfg.model["stems"]
    assert out.stems["stem_a"].shape == item["mix"][None].shape and out.sample_rate == 8000
    res = separate(m, item["mix"])  # unbatched in -> unbatched out
    assert res.stems["stem_b"].shape == item["mix"].shape


def test_chunked_inference_matches_full_for_pointwise_model():
    cfg2 = {"model_id": "dummy_split", "sample_rate": 100, "channels": 1, "stems": ["a", "b", "c"], "params": {}}
    m = build_model(cfg2)
    x = torch.randn(1, 1000)
    full = separate(m, x).stems
    chunked = separate(m, x, chunk_samples=300, overlap_samples=60).stems
    for k in full:
        assert torch.allclose(full[k], chunked[k], atol=1e-6)


# 4/5 train & validation step ----------------------------------------------------------------------------------
def test_train_step_and_validation_step(cfg, tcfg, datasets, tmp_path):
    t = trainer_for(cfg, tcfg, datasets, tmp_path)
    before = [p.clone() for p in t.model.parameters()]
    t.fit(max_steps=1)
    assert t.step == 1
    assert any(not torch.equal(a, b) for a, b in zip(before, t.model.parameters()))
    v = t.validate()
    assert {"val_loss", "val_sdr", "val_si_sdr", "val_reconstruction_error_db"} <= set(v)
    assert all(map(lambda x: x == x, v.values()))  # no NaN


# 6 AMP path (CPU bf16 autocast; fp16+GradScaler is covered by the cuda test) -----------------------------
def test_amp_cpu_bf16(cfg, tcfg, datasets, tmp_path):
    tcfg["amp"] = {"enabled": True, "dtype": "bfloat16"}
    t = trainer_for(cfg, tcfg, datasets, tmp_path)
    t.fit(max_steps=2)
    assert t.step == 2 and not t.scaler.is_enabled()


# 7 gradient accumulation ----------------------------------------------------------------------------------
def test_gradient_accumulation_equals_big_batch(cfg, tcfg, datasets, tmp_path):
    tcfg["grad_clip_norm"], tcfg["scheduler"] = None, None
    big = trainer_for(cfg, {**tcfg, "batch_size": 4, "grad_accum_steps": 1}, datasets, tmp_path, name="a")
    acc = trainer_for(cfg, {**tcfg, "batch_size": 2, "grad_accum_steps": 2}, datasets, tmp_path, name="b")
    big.fit(max_steps=1)
    acc.fit(max_steps=1)
    for p, q in zip(big.model.parameters(), acc.model.parameters()):
        assert torch.allclose(p, q, atol=1e-6)


def test_gradient_checkpointing_runs(cfg, tcfg, datasets, tmp_path):
    tcfg["gradient_checkpointing"] = True
    trainer_for(cfg, tcfg, datasets, tmp_path).fit(max_steps=1)


# 8/10/11 checkpoint, provenance, sha256 -----------------------------------------------------------------
def test_checkpoint_roundtrip_provenance_and_tamper(cfg, tcfg, datasets, tmp_path):
    t = trainer_for(cfg, tcfg, datasets, tmp_path)
    t.fit(max_steps=3)
    ck = tmp_path / "ck" / "step_000003.ckpt"
    rec = read_sidecar(ck)
    assert rec["checkpoint_sha256"] == sha256_file(ck)
    assert rec["parent_checkpoint"] is None and rec["training_run_id"] == "run-test"
    for k in ("model_id", "model_config_hash", "training_config_hash", "dataset_manifest_sha256", "git_commit", "created_at"):
        assert k in rec
    state, _ = load_checkpoint(ck)
    assert state["step"] == 3
    with open(ck, "r+b") as f:  # flip one byte
        f.seek(100)
        b = f.read(1)
        f.seek(100)
        f.write(bytes([b[0] ^ 1]))
    with pytest.raises(ProvenanceError, match="mismatch"):
        load_checkpoint(ck)


def test_missing_sidecar_and_incomplete_provenance_refused(tmp_path):
    with pytest.raises(ProvenanceError):
        save_checkpoint(tmp_path / "x.ckpt", {"a": 1}, {"model_id": "m"})  # fields missing
    p = tmp_path / "y.ckpt"
    torch.save({"a": 1}, p)
    with pytest.raises(ProvenanceError, match="no provenance"):
        load_checkpoint(p)


def test_parent_checkpoint_lineage(tmp_path):
    save_checkpoint(tmp_path / "parent.ckpt", {"a": 1}, dict(PROV))
    ref = parent_ref(tmp_path / "parent.ckpt")
    assert ref["sha256"] == sha256_file(tmp_path / "parent.ckpt")
    save_checkpoint(tmp_path / "child.ckpt", {"a": 2}, {**PROV, "parent_checkpoint": ref})
    assert read_sidecar(tmp_path / "child.ckpt")["parent_checkpoint"]["sha256"] == ref["sha256"]
    assert sidecar_path(tmp_path / "child.ckpt").name == "child.ckpt.provenance.json"


# 9 resume determinism -------------------------------------------------------------------------------------
def test_resume_is_bit_exact(cfg, tcfg, datasets, tmp_path):
    straight = trainer_for(cfg, tcfg, datasets, tmp_path, seed=0, name="s")
    straight.fit(max_steps=6)

    first = trainer_for(cfg, tcfg, datasets, tmp_path, seed=0, name="r")
    first.fit(max_steps=3)
    second = trainer_for(cfg, tcfg, datasets, tmp_path, seed=99, name="r2")  # different init, must be overwritten
    second.resume(tmp_path / "r" / "step_000003.ckpt")
    assert second.step == 3
    second.fit(max_steps=6)
    for k, v in straight.model.state_dict().items():
        assert torch.equal(v, second.model.state_dict()[k]), k


# 12/13 dataset manifest policy ------------------------------------------------------------------------------
def _manifest(**over):
    a = {"asset_id": "a1", "source": "s", "source_url": "https://example.test/a1", "license": "CC0-1.0",
         "license_url": "https://example.test/license", "version": "1", "sha256": "ab" * 32, "grade": "GREEN",
         "commercial_allowed": True, "training_allowed": True, "derivative_allowed": True,
         "redistribution_allowed": True, "attribution_required": False, "attribution_text": "", "notice_required": False}
    a.update(over)
    return {"assets": {"a1": a}, "samples": [{"sample_id": "s1", "asset_ids": ["a1"]}]}


def test_shipped_manifest_ok_for_declared_usage():
    m = load_manifest(CONFIGS / "dataset" / "synthetic_tiny.manifest.json")
    assert validate_manifest(m, "RESEARCH") == []


@pytest.mark.parametrize("flag", ["commercial_allowed", "training_allowed", "derivative_allowed"])
@pytest.mark.parametrize("value", [None, "UNKNOWN", False])
def test_unknown_or_false_flag_rejected_for_production(flag, value):
    with pytest.raises(ManifestError, match=flag):
        require_valid(_manifest(**{flag: value}), "PRODUCTION_TRAINING")


def test_missing_flag_is_unknown():
    m = _manifest()
    del m["assets"]["a1"]["training_allowed"]
    assert validate_manifest(m, "PRODUCTION_TRAINING")


def test_redistribution_flag_is_use_specific():
    m = _manifest(redistribution_allowed=False)
    assert validate_manifest(m, "PRODUCTION_TRAINING") == []  # internal training does not need redistribution
    assert validate_manifest(m, "DATASET_REDISTRIBUTION")
    m2 = _manifest(redistribution_allowed=None)
    assert validate_manifest(m2, "PRODUCTION_TRAINING") == []
    assert validate_manifest(m2, "DATASET_REDISTRIBUTION")


def test_grades_per_usage():
    assert validate_manifest(_manifest(grade="YELLOW"), "RESEARCH") == []
    assert validate_manifest(_manifest(grade="YELLOW"), "PRODUCTION_TRAINING")
    assert validate_manifest(_manifest(grade="GREEN_CONDITIONAL"), "PRODUCTION_TRAINING") == []
    for u in ("RESEARCH", "BENCHMARK", "PRODUCTION_TRAINING"):
        assert validate_manifest(_manifest(grade="RED"), u)
    assert validate_manifest(_manifest(grade="GREEN", sha256="bad"), "PRODUCTION_TRAINING")
    assert validate_manifest(_manifest(), "NOPE")


def test_manifest_hash_is_order_independent():
    m = _manifest()
    rev = {"samples": m["samples"], "assets": {"a1": dict(reversed(list(m["assets"]["a1"].items())))}}
    assert manifest_hash(m) == manifest_hash(rev)


def test_run_refuses_unknown_asset_for_production(tmp_path, cfg):
    """Runner path: production usage + shipped (placeholder-hash, RESEARCH-grade) setup must not slip through."""
    import shutil
    root = tmp_path / "configs"
    shutil.copytree(CONFIGS, root)
    ds = (root / "dataset" / "synthetic_tiny.yaml")
    ds.write_text(ds.read_text().replace("usage: RESEARCH", "usage: PRODUCTION_TRAINING"))
    mf = json.loads((root / "dataset" / "synthetic_tiny.manifest.json").read_text())
    mf["assets"]["procedural-sine-sum"]["training_allowed"] = None
    (root / "dataset" / "synthetic_tiny.manifest.json").write_text(json.dumps(mf))
    with pytest.raises(ManifestError, match="training_allowed"):
        run_experiment(root / "experiment" / "phase2_smoke.yaml", base_dir=tmp_path)


# 7b OOM reporting ------------------------------------------------------------------------------------------
def test_oom_is_reported_with_context(cfg, tcfg, datasets, tmp_path, monkeypatch):
    t = trainer_for(cfg, tcfg, datasets, tmp_path)

    def boom(batch):
        raise torch.cuda.OutOfMemoryError("CUDA out of memory (simulated)")
    monkeypatch.setattr(t, "_forward_loss", boom)
    with pytest.raises(TrainingOOMError, match="batch_size=4"):
        t.fit(max_steps=1)


# metrics -------------------------------------------------------------------------------------------------------
def test_metric_definitions():
    ref = torch.randn(2, 2000)
    assert si_sdr_db(2 * ref, ref).min() > 60   # scale invariant
    assert abs(sdr_db(2 * ref, ref).mean()) < 0.1  # error == ref -> 0 dB
    assert sdr_db(ref, ref).min() > 60
    assert si_sdr_db(torch.randn(2, 2000), ref).max() < 5


# 15/16 end to end: CPU smoke + CUDA smoke ---------------------------------------------------------------------
def _e2e(tmp_path, device):
    root = tmp_path / "configs"
    import shutil
    shutil.copytree(CONFIGS, root)
    tp = root / "training" / "test_smoke.yaml"
    txt = tp.read_text().replace("device: auto", f"device: {device}")
    if device == "cuda":
        txt = txt.replace("amp: {enabled: false, dtype: float16}", "amp: {enabled: true, dtype: float16}")
    tp.write_text(txt)
    return run_experiment(root / "experiment" / "phase2_smoke.yaml", base_dir=tmp_path)


def test_end_to_end_cpu(tmp_path):
    r = _e2e(tmp_path, "cpu")
    run = r["run_dir"]
    meta = json.loads((run / "experiment.json").read_text())
    assert meta["status"] == "completed"
    assert {"experiment_id", "timestamp", "seed", "model_config", "training_config", "dataset_manifest_hash",
            "environment", "checkpoints", "metrics"} <= set(meta)
    assert (run / "metrics.jsonl").read_text().count('"event": "train"') == 6
    assert r["provenance"]["checkpoint_sha256"] == sha256_file(r["checkpoint"])
    assert set(r["metrics"]) == {"sdr", "si_sdr", "reconstruction_error_db"}
    assert r["inference"]["rtf"] > 0 and r["inference"]["peak_vram_mib"] is None


@pytest.mark.cuda
@pytest.mark.skipif(not torch.cuda.is_available(), reason="no CUDA device")
def test_end_to_end_cuda_fp16_amp(tmp_path):
    r = _e2e(tmp_path, "cuda")
    assert r["inference"]["peak_vram_mib"] > 0
    meta = json.loads((r["run_dir"] / "experiment.json").read_text())
    assert meta["environment"]["cuda_available"] and meta["environment"]["gpu"]


def test_attribution_obligation_enforced():
    ok = _manifest(grade="GREEN_CONDITIONAL", attribution_required=True, attribution_text="VocalSet, CC BY 4.0")
    assert validate_manifest(ok, "PRODUCTION_TRAINING") == []
    missing = _manifest(grade="GREEN_CONDITIONAL", attribution_required=True, attribution_text="")
    with pytest.raises(ManifestError, match="attribution_text"):
        require_valid(missing, "PRODUCTION_TRAINING")
    unstated = _manifest(attribution_required=None)
    with pytest.raises(ManifestError, match="attribution_required"):
        require_valid(unstated, "PRODUCTION_TRAINING")
    assert validate_manifest(_manifest(license_url=""), "PRODUCTION_TRAINING")
    assert validate_manifest(unstated, "RESEARCH") == []  # research does not demand obligations
