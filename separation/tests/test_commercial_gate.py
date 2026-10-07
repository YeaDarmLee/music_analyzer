import json
from pathlib import Path

import pytest

from music_analyzer import registry
from music_analyzer.common import project_root, read_json
from music_analyzer.job_contracts import preset

CONFIGS = project_root() / "separation/configs"
UNKNOWN_WEIGHT_MODELS = ("bs_roformer_6s", "bs_karaoke", "melband_karaoke", "clapsep")


def approvals():
    return read_json(CONFIGS / "commercial_approval.json")["models"]


def test_unknown_weight_models_are_never_approved():
    for model_id in UNKNOWN_WEIGHT_MODELS:
        assert approvals()[model_id]["status"] != "APPROVED"
        with pytest.raises(ValueError, match="COMMERCIAL_GATE_BLOCKED"):
            registry.commercial_gate([model_id])


def test_missing_model_counts_as_unknown():
    with pytest.raises(ValueError, match="UNKNOWN"):
        registry.commercial_gate(["not_registered"])


def test_approved_entries_have_license_evidence_and_known_weight_license():
    for model_id, entry in approvals().items():
        if entry["status"] != "APPROVED":
            continue
        assert entry["evidence_url"].startswith("https://") and entry["basis"]
        model = read_json(CONFIGS / "models" / f"{model_id}.json")
        assert model["weight_license"]["value"] not in ("UNKNOWN", "", None)
        assert model["weight_license"]["evidence_url"]


def test_commercial_presets_only_use_approved_models():
    from music_analyzer import commercial_pipeline as pipeline
    for name in pipeline.stage_presets():
        assert preset(name)["model_id"] in pipeline.MODELS
    for model_id in pipeline.MODELS:
        assert model_id not in UNKNOWN_WEIGHT_MODELS


def test_commercial_presets_are_flagged_and_baseline_presets_are_untouched():
    assert preset("instrument_core4")["profile"] == "commercial"
    assert preset("vocal2_mega")["profile"] == "commercial"
    for name in ("instrument_roformer_6s", "bs_karaoke", "instrument_mega7", "vocal_roformer"):
        assert "profile" not in preset(name)
    assert preset("instrument_roformer_6s")["model_id"] == "bs_roformer_6s"
    assert preset("bs_karaoke")["model_id"] == "bs_karaoke"


def test_baseline_model_configs_stay_dev_only():
    for model_id in ("bs_roformer_6s", "bs_karaoke", "melband_roformer_kj", "bs_roformer_mega5", "bs_roformer_mega7"):
        assert read_json(CONFIGS / "models" / f"{model_id}.json")["commercial_release_status"] == "DEV_ONLY"


def test_hash_mismatch_blocks(tmp_path, monkeypatch):
    manifest = tmp_path / "approval.json"
    manifest.write_text(json.dumps({"models": {"m": {"status": "APPROVED", "checkpoint_sha256": "a" * 64}}}))
    monkeypatch.setattr(registry, "APPROVAL", manifest)
    folder = tmp_path / "models" / "m"
    folder.mkdir(parents=True)
    (folder / "registration.json").write_text(json.dumps({"checkpoint_sha256": "b" * 64}))
    monkeypatch.setattr(registry, "paths", lambda root, model_id: (folder / "x.ckpt", folder / "registration.json"))
    with pytest.raises(ValueError, match="differs from the approved hash"):
        registry.commercial_gate(["m"], tmp_path)
    (folder / "registration.json").write_text(json.dumps({"checkpoint_sha256": "a" * 64}))
    registry.commercial_gate(["m"], tmp_path)


def test_commercial_modules_do_not_import_clap_or_medleydb():
    root = Path(__file__).parents[1] / "src/music_analyzer"
    for name in ("commercial_pipeline.py", "commercial_cymbal.py"):
        if not (root / name).exists():
            continue
        source = (root / name).read_text(encoding="utf8").lower()
        for forbidden in ("import synth_recovery", "from .synth_recovery", "laion", "medleydb", "part_study"):
            assert forbidden not in source, (name, forbidden)


def test_worker_gate_is_wired():
    text = (Path(__file__).parents[1] / "src/music_analyzer/worker.py").read_text(encoding="utf8")
    assert 'selected.get("profile") == "commercial"' in text and "commercial_gate" in text


def test_commercial_2_and_6_run_only_approved_models():
    from music_analyzer import release
    from music_analyzer.commercial_pipeline import models_for
    assert models_for("commercial_2") == ("melband_roformer_kj",)
    assert models_for("commercial_6") == ("melband_roformer_kj", "bs_roformer_core4")
    for name in ("commercial_2", "commercial_6", "commercial_13"):
        plan = release.preset_plan(name)
        assert not plan["problems"], plan["problems"]
        assert "bs_roformer_6s" not in {m["model_id"] for m in plan["models"]}
