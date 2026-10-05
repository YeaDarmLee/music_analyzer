import json

import numpy as np
import pytest
import soundfile as sf

from music_analyzer.audio import RATE, make_fixture, write_raw
from music_analyzer.evaluation import raw_sdr, si_sdr
from music_analyzer.registry import config, verify_digest
from music_analyzer.common import project_root, write_json


def test_raw_float32_preserves_above_full_scale_and_relative_gain(tmp_path):
    signal = np.array([[1.25, -1.75], [.1, -.3], [0, 0]], dtype=np.float32)
    for name, scale in [("a", 1), ("b", .125)]:
        properties = write_raw(tmp_path / f"{name}.wav", signal * scale)
        restored, rate = sf.read(tmp_path / f"{name}.wav", dtype="float32", always_2d=True)
        assert rate == RATE and sf.info(tmp_path / f"{name}.wav").subtype == "FLOAT"
        np.testing.assert_array_equal(restored, signal * scale)
        assert properties["gain"] == 1.0
    assert sf.read(tmp_path / "a.wav", dtype="float32")[0].min() == -1.75


@pytest.mark.parametrize("audio", [
    np.array([[np.nan, 0]], dtype=np.float32),
    np.array([[np.inf, 0]], dtype=np.float32),
    np.zeros((1, 1), dtype=np.float32),
    np.zeros((1, 2), dtype=np.float64),
    np.zeros((0, 2), dtype=np.float32),
])
def test_invalid_raw_not_written(tmp_path, audio):
    path = tmp_path / "bad.wav"
    with pytest.raises(ValueError):
        write_raw(path, audio)
    assert not path.exists()


def test_hash_mismatch_rejected():
    verify_digest("a" * 64, "a" * 8, "a" * 64)
    with pytest.raises(ValueError):
        verify_digest("b" * 64, "a" * 8)
    with pytest.raises(ValueError):
        verify_digest("a" * 64, "a" * 8, "a" * 63 + "b")


def test_si_sdr_is_scale_invariant_but_raw_sdr_is_not():
    rng = np.random.default_rng(2)
    reference = rng.normal(size=(1000, 2))
    estimate = reference + .1 * rng.normal(size=reference.shape)
    assert si_sdr(reference, estimate) == pytest.approx(si_sdr(reference, estimate * .25), abs=1e-7)
    assert abs(raw_sdr(reference, estimate) - raw_sdr(reference, estimate * .25)) > 10


def test_si_sdr_does_not_remove_timing_error():
    ref = np.random.default_rng(3).normal(size=(1000, 2))
    assert si_sdr(ref, np.roll(ref, 1, axis=0)) < si_sdr(ref, ref) - 20


def test_silent_reference_and_zero_estimate_not_given_quality_score():
    silence = np.zeros((100, 2))
    assert raw_sdr(silence, silence) is None
    assert si_sdr(silence, silence) is None
    assert si_sdr(np.ones((100, 2)), silence) is None
    assert si_sdr(np.random.default_rng(3).normal(size=(100, 2)), silence) is None


def test_mismatched_or_nonfinite_metrics_rejected():
    for bad in [np.zeros((10, 1)), np.full((10, 2), np.nan)]:
        with pytest.raises(ValueError):
            raw_sdr(np.ones((10, 2)), bad)
        with pytest.raises(ValueError):
            si_sdr(np.ones((10, 2)), bad)


def test_fixture_deterministic_stereo_10_seconds(tmp_path):
    first = make_fixture(tmp_path / "신호 A.wav")
    second = make_fixture(tmp_path / "신호 B.wav")
    a, rate = sf.read(first, dtype="float32")
    b, _ = sf.read(second, dtype="float32")
    assert a.shape == (441000, 2) and rate == RATE
    np.testing.assert_array_equal(a, b)


def test_registry_all_sources_have_explicit_taxonomy_and_dev_gate():
    entry = config()
    taxonomy = json.loads((project_root() / "separation/configs/instrument_taxonomy.v1.json").read_text(encoding="utf-8-sig"))
    ids = {item["id"] for item in taxonomy["instruments"]}
    assert set(entry["source_mapping"]) == set(entry["source_labels"])
    assert set(entry["source_mapping"].values()) <= ids
    assert entry["weight_license"]["status"] == "UNRESOLVED"
    assert entry["commercial_release_status"] == "DEV_ONLY"
    assert entry["usage_status"]["redistribution"] == "BLOCKED"


def test_atomic_json_rejects_nan_and_keeps_last_valid_file(tmp_path):
    path = tmp_path / "state.json"
    write_json(path, {"state": "VALIDATING"})
    with pytest.raises(ValueError):
        write_json(path, {"bad": float("nan")})
    assert json.loads(path.read_text()) == {"state": "VALIDATING"}

def test_registered_checkpoint_corruption_and_changed_config_are_rejected(tmp_path, monkeypatch):
    from music_analyzer import registry
    from music_analyzer.common import sha256_file
    artifact = tmp_path / "test.th"
    artifact.write_bytes(b"original checkpoint")
    model_config = tmp_path / "config.json"
    model_config.write_text('{"revision": 1}', encoding="utf-8")
    monkeypatch.setattr(registry, "CONFIG", model_config)
    digest = sha256_file(artifact)
    entry = {"commercial_release_status": "DEV_ONLY", "upstream_sha256_prefix": digest[:8]}
    registered = {"checkpoint_sha256": digest, "config_sha256": sha256_file(model_config)}
    registry.validate_registration(artifact, registered, entry)
    artifact.write_bytes(b"modified checkpoint")
    with pytest.raises(ValueError, match="CHECKPOINT_HASH_MISMATCH"):
        registry.validate_registration(artifact, registered, entry)
    artifact.write_bytes(b"original checkpoint")
    model_config.write_text('{"revision": 2}', encoding="utf-8")
    with pytest.raises(ValueError, match="MODEL_CONFIG_CHANGED"):
        registry.validate_registration(artifact, registered, entry)


def test_missing_prepared_model_never_downloads_implicitly(tmp_path):
    from music_analyzer.registry import resolve
    with pytest.raises(FileNotFoundError, match="MODEL_NOT_AVAILABLE"):
        resolve(tmp_path)
