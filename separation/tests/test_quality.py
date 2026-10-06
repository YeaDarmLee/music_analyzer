from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from music_analyzer.audio import RATE, write_raw_streaming
from music_analyzer.common import sha256_file, write_json
from music_analyzer.demucs_adapter import chunk_count
from music_analyzer.job_contracts import JobError, preset, verify_result
from music_analyzer.registry import config, validate_registration


@pytest.mark.parametrize("shifts,members", [(0, 1), (2, 1), (2, 4)])
def test_chunk_progress_matches_upstream_execution(shifts, members):
    import random
    import torch
    from demucs.apply import apply_model, BagOfModels

    class Identity(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.anchor = torch.nn.Parameter(torch.zeros(1))
            self.sources, self.samplerate, self.audio_channels = ["target"], 100, 2
            self.segment = 2

        def forward(self, audio):
            return audio.unsqueeze(1)

    total = 0
    class Future:
        def __init__(self, fn, args, kwargs):
            self.fn, self.args, self.kwargs = fn, args, kwargs
        def result(self):
            return self.fn(*self.args, **self.kwargs)
    class Pool:
        def submit(self, fn, *args, **kwargs):
            nonlocal total
            total += 1
            return Future(fn, args, kwargs)

    models = [Identity() for _ in range(members)]
    model = models[0] if members == 1 else BagOfModels(models)
    raw = torch.sin(torch.arange(943) * .2).repeat(1, 2, 1)
    random.seed(0)
    output = apply_model(model, raw, shifts=shifts, split=True, overlap=.5,
                         segment=2, device="cpu", pool=Pool())
    assert total == chunk_count(943, 100, 2, .5, shifts, members, 0)
    # Chunk joining and reverse shifts must preserve input timing and amplitude.
    assert torch.allclose(output[:, 0], raw, atol=2e-7, rtol=1e-6)


def test_six_source_contract_and_wrong_model_are_rejected(tmp_path):
    families = config("demucs_htdemucs_6s")["source_labels"]
    job = {"job_id": "job_test", "asset_id": "asset_test", "num_frames": 100,
           "canonical_sha256": "input", "model_id": "demucs_htdemucs_6s"}
    stems = []
    for family in families:
        path = tmp_path / "stems" / (family + ".wav")
        raw = write_raw_streaming(path, np.zeros((100, 2), np.float32))
        stems.append({"family": family, "path": "stems/" + family + ".wav",
                      "sha256": sha256_file(path), **raw})
    manifest = {"kind": "separation_result", "schema_version": "1.0", "status": "succeeded",
                "job_id": job["job_id"], "asset_id": job["asset_id"],
                "source_sha256": "input", "timeline": {"sample_rate": RATE, "channels": 2,
                    "num_frames": 100, "origin_sec": 0},
                "model": {"model_id": "demucs_htdemucs_6s"}, "stems": stems}
    write_json(tmp_path / "manifest.json", manifest)
    assert len(verify_result(tmp_path, job)["stems"]) == 6
    manifest["model"]["model_id"] = "demucs_htdemucs"
    write_json(tmp_path / "manifest.json", manifest)
    with pytest.raises(JobError, match="model identity"):
        verify_result(tmp_path, job)


def test_ensemble_all_artifacts_are_pinned_and_checked(tmp_path, monkeypatch):
    import music_analyzer.registry as registry
    config_path = tmp_path / "demucs_htdemucs_ft.json"
    config_path.write_text("{}")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "demucs_htdemucs.json")
    paths = [tmp_path / "one.th", tmp_path / "two.th"]
    for path in paths:
        path.write_bytes(path.name.encode())
    entry = {"model_id": "demucs_htdemucs_ft", "commercial_release_status": "DEV_ONLY",
             "checkpoint_artifacts": [{"filename": p.name, "upstream_sha256_prefix": sha256_file(p)[:8]}
                                      for p in paths]}
    registration = {"artifact_hashes": {p.name: sha256_file(p) for p in paths},
                    "config_sha256": sha256_file(config_path)}
    validate_registration(paths[0], registration, entry)
    paths[1].write_bytes(b"corrupted second checkpoint")
    with pytest.raises(ValueError, match="CHECKPOINT_HASH_MISMATCH"):
        validate_registration(paths[0], registration, entry)


def test_quality_fallback_preserves_model_and_source_contract():
    from music_analyzer.job_contracts import fallback_for
    for name in ("quality", "quality_ft", "quality_6s"):
        selected = preset(name)
        fallback = preset(fallback_for(name))
        assert selected["model_id"] == fallback["model_id"]
        assert selected["segment_sec"] == 7.8 and selected["overlap"] == .4
        assert fallback["overlap"] == .4
        assert selected["shifts"] == 2 and fallback["shifts"] == 0


@pytest.mark.parametrize("model_id", ["demucs_htdemucs", "demucs_htdemucs_6s", "demucs_htdemucs_ft"])
def test_all_model_sources_have_taxonomy_mapping(model_id):
    entry = config(model_id)
    assert set(entry["source_mapping"]) == set(entry["source_labels"])
    assert entry["commercial_release_status"] == "DEV_ONLY"

def test_listening_comparison_preserves_common_gain_and_time(tmp_path, monkeypatch):
    from music_analyzer.comparison import compare_results
    from music_analyzer.ingest import ingest_file
    root = tmp_path / "data"
    source = tmp_path / "source.wav"
    original = np.full((RATE, 2), .2, np.float32)
    sf.write(source, original, RATE, subtype="FLOAT")
    asset_id = ingest_file(source, root).name
    from music_analyzer.ingest import load_asset
    asset = load_asset(root, asset_id)
    job_ids = []
    for index, amplitude in enumerate((1.2, .1)):
        job_id = "job_" + str(index + 1) * 32
        job_ids.append(job_id)
        folder = root / "jobs" / job_id
        result = folder / "result"
        result.mkdir(parents=True)
        stems = []
        for family in ("drums", "bass", "other", "vocals"):
            path = result / "stems" / (family + ".wav")
            raw = write_raw_streaming(path, np.full((RATE, 2), amplitude, np.float32))
            stems.append({"family": family, "path": "stems/" + family + ".wav",
                          "sha256": sha256_file(path), **raw})
        job = {"job_id": job_id, "asset_id": asset_id, "state": "SUCCEEDED", "num_frames": RATE,
               "canonical_sha256": asset["canonical"]["sha256"], "requested_preset": "baseline"}
        manifest = {"kind": "separation_result", "schema_version": "1.0", "status": "succeeded",
                    "job_id": job_id, "asset_id": asset_id, "source_sha256": job["canonical_sha256"],
                    "timeline": asset["timeline"], "stems": stems}
        write_json(folder / "job.json", job)
        write_json(result / "manifest.json", manifest)
    folder = compare_results(root, job_ids, [(.25, .5)])
    from music_analyzer.common import read_json
    comparison = read_json(folder / "manifest.json")
    gain = comparison["preview"]["common_gain"]
    assert abs(gain - .9 / 1.4) < 1e-6
    for key, amplitude in (("original", .2), ("v0_vocals", 1.2), ("v1_vocals", .1), ("v0_instrumental", -1.0), ("v1_instrumental", .1)):
        filename = comparison["windows"][0]["files"][key]
        decoded, rate = sf.read(folder / filename, dtype="float32", always_2d=True)
        assert len(decoded) == RATE // 2 and rate == RATE
        assert np.allclose(decoded, amplitude * gain, atol=1 / 32768 + 1e-7)
    assert comparison["assessment"]["quality_improvement_verified"] is False
    assert "__DATA__" not in (folder / "comparison.html").read_text(encoding="utf-8")
    with pytest.raises(JobError, match="exceeds"):
        compare_results(root, job_ids, [(.8, .5)])
    import music_analyzer.comparison as module
    from types import SimpleNamespace
    monkeypatch.setattr(module.shutil, "disk_usage", lambda path: SimpleNamespace(free=0))
    with pytest.raises(JobError, match="Insufficient space"):
        compare_results(root, job_ids, [(.25, .5)])
    assert not list((root / "comparisons").glob(".*.partial"))
