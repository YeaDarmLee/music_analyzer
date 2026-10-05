from dataclasses import replace
from pathlib import Path
import json
import subprocess

import numpy as np
import pytest
import soundfile as sf

from music_analyzer.audio import RATE
from music_analyzer.common import read_json, sha256_file
from music_analyzer.ingest import (AudioInputError, InputLimits, ingest_file, load_asset,
                                   probe, stream_decode)


def signal(rate, seconds=1.1, channels=2):
    t = np.arange(round(rate * seconds)) / rate
    mono = (.13 * np.sin(2 * np.pi * 330 * t)).astype(np.float32)
    return mono if channels == 1 else np.column_stack((mono, mono * .5))


def encode(src, dst):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(src), str(dst)],
                   check=True, capture_output=True, timeout=30)


@pytest.mark.parametrize("rate,channels,extension", [
    (44100, 2, ".wav"), (44100, 1, ".wav"), (48000, 2, ".wav"),
    (48000, 1, ".wav"), (8000, 1, ".wav"), (192000, 2, ".wav"),
    (48000, 2, ".flac"), (44100, 1, ".flac"), (48000, 2, ".mp3"),
    (44100, 1, ".mp3"),
])
def test_real_formats_rates_channels_and_original_preserved(tmp_path, rate, channels, extension):
    source_wav = tmp_path / "한글 입력 & 괄호 (원본).wav"
    data = signal(rate, channels=channels)
    sf.write(source_wav, data, rate, subtype="PCM_24" if extension == ".flac" else "FLOAT")
    source = source_wav
    if extension != ".wav":
        source = tmp_path / ("한글 입력 & 괄호 (원본)" + extension)
        encode(source_wav, source)
    before = source.read_bytes()
    folder = ingest_file(source, tmp_path / "managed")
    manifest = load_asset(tmp_path / "managed", folder.name)
    assert source.read_bytes() == before
    assert (folder / manifest["input"]["path"]).read_bytes() == before
    assert manifest["input"]["sha256"] == sha256_file(source)
    canonical, target_rate = sf.read(folder / "canonical.wav", dtype="float32", always_2d=True)
    expected_frames = (manifest["input"]["decoded_num_frames"] * RATE + rate // 2) // rate
    assert canonical.shape == (expected_frames, 2) and target_rate == RATE
    assert manifest["timeline"]["duration_sec"] == expected_frames / RATE
    assert manifest["preprocessing"]["mono_duplicated"] == (channels == 1)
    if channels == 1:
        np.testing.assert_array_equal(canonical[:, 0], canonical[:, 1])
    if rate == RATE and extension == ".wav":
        expected = np.column_stack((data, data)) if channels == 1 else data
        np.testing.assert_array_equal(canonical, expected)
    assert sf.info(folder / "canonical.wav").subtype == "FLOAT"
    assert not list((tmp_path / "managed/inputs").glob(".partial_*"))
    assert not (folder / "native.wav").exists()
    assert str(tmp_path) not in json.dumps(manifest)


def test_over_full_scale_preserved(tmp_path):
    source = tmp_path / "peaks.wav"
    data = signal(RATE)
    data[123, :] = [1.25, -1.75]
    sf.write(source, data, RATE, subtype="FLOAT")
    folder = ingest_file(source, tmp_path / "managed")
    actual, _ = sf.read(folder / "canonical.wav", dtype="float32")
    np.testing.assert_array_equal(actual, data)
    assert read_json(folder / "manifest.json")["canonical"]["over_full_scale"]


def test_impulse_resampling_alignment_and_stereo_gain(tmp_path):
    rate = 48000
    source = tmp_path / "impulse.wav"
    data = np.zeros((rate * 2, 2), dtype=np.float32)
    data[rate, :] = [1.0, .5]
    sf.write(source, data, rate, subtype="FLOAT")
    folder = ingest_file(source, tmp_path / "managed")
    audio, _ = sf.read(folder / "canonical.wav", dtype="float32")
    assert abs(int(np.argmax(np.abs(audio[:, 0]))) - RATE) <= 1
    np.testing.assert_allclose(audio[:, 1], audio[:, 0] * .5, atol=1e-7)


def test_silence_is_valid_asset_without_gpu(tmp_path):
    source = tmp_path / "silence.wav"
    sf.write(source, np.zeros((RATE, 1), dtype=np.float32), RATE, subtype="FLOAT")
    folder = ingest_file(source, tmp_path / "managed")
    manifest = read_json(folder / "manifest.json")
    assert manifest["canonical"]["rms"] == 0
    assert any("SILENT_INPUT" in warning for warning in manifest["warnings"])


@pytest.mark.parametrize("variant,code", [
    ("corrupt", "PROBE_FAILED"), ("empty", "FILE_SIZE_LIMIT"),
    ("missing", "INPUT_NOT_FOUND"), ("wrong_extension", "UNSUPPORTED_EXTENSION"),
    ("multi", "UNSUPPORTED_CHANNELS"), ("short", "DURATION_LIMIT"),
    ("low_rate", "SAMPLE_RATE_LIMIT"), ("mismatch", "FORMAT_MISMATCH"),
    ("nonfinite", "NONFINITE_AUDIO"),
])
def test_rejected_inputs_never_published_and_source_unchanged(tmp_path, variant, code):
    source = tmp_path / "source.wav"
    if variant == "corrupt":
        source.write_bytes(b"not an audio file")
    elif variant == "empty":
        source.touch()
    elif variant == "missing":
        pass
    elif variant == "wrong_extension":
        source = source.with_suffix(".ogg")
        source.write_bytes(b"not supported")
    elif variant == "multi":
        sf.write(source, np.zeros((RATE, 6)), RATE, subtype="FLOAT")
    elif variant == "short":
        sf.write(source, signal(RATE, .1), RATE, subtype="FLOAT")
    elif variant == "low_rate":
        sf.write(source, signal(4000), 4000, subtype="FLOAT")
    elif variant == "mismatch":
        real = tmp_path / "real.flac"
        sf.write(real, signal(RATE), RATE)
        source.write_bytes(real.read_bytes())
    elif variant == "nonfinite":
        audio = signal(RATE)
        audio[100, 0] = np.nan
        sf.write(source, audio, RATE, subtype="FLOAT")
    before = source.read_bytes() if source.exists() else None
    with pytest.raises(AudioInputError) as error:
        ingest_file(source, tmp_path / "managed")
    assert error.value.code == code
    assert (source.read_bytes() if source.exists() else None) == before
    if (tmp_path / "managed/inputs").exists():
        assert list((tmp_path / "managed/inputs").iterdir()) == []


@pytest.mark.parametrize("limit", ["file", "duration", "decoded"])
def test_resource_limits_enforced(tmp_path, limit):
    source = tmp_path / "limited.wav"
    sf.write(source, signal(RATE, 2), RATE, subtype="FLOAT")
    limits = InputLimits()
    if limit == "file":
        limits = replace(limits, max_file_bytes=100)
    elif limit == "duration":
        limits = replace(limits, max_duration_sec=1)
    else:
        limits = replace(limits, max_decoded_bytes=1024)
    with pytest.raises(AudioInputError):
        ingest_file(source, tmp_path / "managed", limits)
    if (tmp_path / "managed/inputs").exists():
        assert not list((tmp_path / "managed/inputs").iterdir())


def test_low_disk_space_rejected_before_copy(tmp_path, monkeypatch):
    source = tmp_path / "source.wav"
    sf.write(source, signal(RATE), RATE, subtype="FLOAT")
    from music_analyzer import ingest
    monkeypatch.setattr(ingest.shutil, "disk_usage", lambda _: type("Disk", (), {"free": 1})())
    with pytest.raises(AudioInputError, match="Insufficient"):
        ingest_file(source, tmp_path / "managed")
    assert source.is_file()


def test_decoder_timeout_kills_process_and_cleans_partial(tmp_path, monkeypatch):
    source = tmp_path / "source.wav"
    sf.write(source, signal(RATE), RATE, subtype="FLOAT")
    from music_analyzer import ingest
    real_popen = ingest.subprocess.Popen
    import sys
    children = []
    def delayed(*args, **kwargs):
        process = real_popen([sys.executable, "-c", "import time; time.sleep(20)"], **kwargs)
        children.append(process)
        return process
    monkeypatch.setattr(ingest.subprocess, "Popen", delayed)
    with pytest.raises(AudioInputError) as error:
        stream_decode(source, tmp_path / "temp.wav", 2, RATE, RATE * 2, 1024 ** 2, .1)
    assert error.value.code == "DECODE_TIMEOUT"
    assert children[0].poll() is not None


def test_manifest_hash_timeline_and_path_checks(tmp_path):
    source = tmp_path / "source.wav"
    sf.write(source, signal(RATE), RATE, subtype="FLOAT")
    folder = ingest_file(source, tmp_path / "managed")
    original_manifest = read_json(folder / "manifest.json")
    for mutation in ("path", "timeline", "hash"):
        changed = json.loads(json.dumps(original_manifest))
        if mutation == "path":
            changed["canonical"]["path"] = "../../source.wav"
        elif mutation == "timeline":
            changed["timeline"]["num_frames"] += 1
        else:
            changed["canonical"]["sha256"] = "0" * 64
        (folder / "manifest.json").write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(AudioInputError):
            load_asset(tmp_path / "managed", folder.name)
    for bad_id in ("../source", "asset_", folder.name + "/.."):
        with pytest.raises(AudioInputError):
            load_asset(tmp_path / "managed", bad_id)


def test_repeated_ingestion_keeps_previous_asset(tmp_path):
    source = tmp_path / "source.wav"
    sf.write(source, signal(RATE), RATE, subtype="FLOAT")
    first = ingest_file(source, tmp_path / "managed")
    before = (first / "manifest.json").read_bytes()
    second = ingest_file(source, tmp_path / "managed")
    assert first != second
    assert (first / "manifest.json").read_bytes() == before
    load_asset(tmp_path / "managed", first.name)
    load_asset(tmp_path / "managed", second.name)


def test_cli_ingest_and_inspect_without_torch_import(tmp_path):
    import sys
    source = tmp_path / "CLI 한글.wav"
    sf.write(source, signal(RATE), RATE, subtype="FLOAT")
    data_root = tmp_path / "managed"
    result = subprocess.run([sys.executable, "-m", "music_analyzer.cli", "--data-root", str(data_root),
                             "ingest", str(source)], capture_output=True, text=True,
                            encoding="utf-8", check=True, timeout=30)
    data = json.loads(result.stdout)
    result = subprocess.run([sys.executable, "-m", "music_analyzer.cli", "--data-root", str(data_root),
                             "inspect-asset", data["asset_id"]], capture_output=True, text=True,
                            encoding="utf-8", check=True, timeout=30)
    assert json.loads(result.stdout)["asset_id"] == data["asset_id"]
    check_imports = subprocess.run([sys.executable, "-c",
        "import sys; from music_analyzer.ingest import ingest_file; assert 'torch' not in sys.modules"],
        capture_output=True, check=True, timeout=10)
    assert check_imports.returncode == 0


def test_cli_failure_is_json_error_without_traceback(tmp_path):
    import sys
    result = subprocess.run([sys.executable, "-m", "music_analyzer.cli",
                             "--data-root", str(tmp_path / "managed"), "ingest", str(tmp_path / "missing.wav")],
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "INPUT_NOT_FOUND"
    assert "Traceback" not in result.stderr

@pytest.mark.parametrize("frames,expected,adjustment", [(48007, 44106, -1), (48001, 44101, 0)])
def test_fractional_resampling_frame_policy(tmp_path, frames, expected, adjustment):
    source = tmp_path / "fractional.wav"
    sf.write(source, signal(48000, frames / 48000), 48000, subtype="FLOAT")
    folder = ingest_file(source, tmp_path / "managed")
    manifest = read_json(folder / "manifest.json")
    assert manifest["timeline"]["num_frames"] == expected
    assert manifest["preprocessing"]["frame_adjustment"] == adjustment


def test_one_frame_padding_or_trim_never_shifts_start(tmp_path):
    from music_analyzer.ingest import _adjust_frames
    audio = np.array([[.2, .4], [.3, .6], [.5, 1.]], dtype=np.float32)
    source = tmp_path / "canonical.wav"
    sf.write(source, audio, RATE, subtype="FLOAT")
    assert _adjust_frames(source, 4) == 1
    padded, _ = sf.read(source, dtype="float32")
    np.testing.assert_array_equal(padded[:3], audio)
    np.testing.assert_array_equal(padded[3], [0, 0])
    assert _adjust_frames(source, 3) == -1
    np.testing.assert_array_equal(sf.read(source, dtype="float32")[0], audio)
    with pytest.raises(AudioInputError, match="one frame"):
        _adjust_frames(source, 5)


def test_manifest_write_failure_does_not_publish_or_touch_source(tmp_path, monkeypatch):
    from music_analyzer import ingest
    source = tmp_path / "source.wav"
    sf.write(source, signal(RATE), RATE, subtype="FLOAT")
    before = source.read_bytes()
    def disk_full(*_):
        raise OSError("simulated disk full during manifest write")
    monkeypatch.setattr(ingest, "write_json", disk_full)
    with pytest.raises(AudioInputError) as error:
        ingest_file(source, tmp_path / "managed")
    assert error.value.code == "IO_ERROR"
    assert not list((tmp_path / "managed/inputs").iterdir())
    assert source.read_bytes() == before


def test_antiphase_stereo_not_downmixed(tmp_path):
    source = tmp_path / "antiphase.wav"
    mono = signal(RATE, channels=1)
    audio = np.column_stack((mono, -mono))
    sf.write(source, audio, RATE, subtype="FLOAT")
    folder = ingest_file(source, tmp_path / "managed")
    actual, _ = sf.read(folder / "canonical.wav", dtype="float32")
    np.testing.assert_array_equal(actual, audio)


def test_failed_ingest_keeps_previous_success(tmp_path):
    source = tmp_path / "good.wav"
    sf.write(source, signal(RATE), RATE, subtype="FLOAT")
    data_root = tmp_path / "managed"
    folder = ingest_file(source, data_root)
    before = (folder / "canonical.wav").read_bytes()
    damaged = tmp_path / "damaged.wav"
    damaged.write_bytes(b"broken")
    with pytest.raises(AudioInputError):
        ingest_file(damaged, data_root)
    assert list((data_root / "inputs").iterdir()) == [folder]
    assert (folder / "canonical.wav").read_bytes() == before
    load_asset(data_root, folder.name)

@pytest.mark.parametrize("variant", ["invalid_json", "wrong_type", "missing_field", "canonical_metadata", "corrupt_original"])
def test_damaged_published_assets_rejected_with_controlled_error(tmp_path, variant):
    source = tmp_path / "source.wav"
    sf.write(source, signal(RATE), RATE, subtype="FLOAT")
    root = tmp_path / "managed"
    folder = ingest_file(source, root)
    manifest = read_json(folder / "manifest.json")
    if variant == "invalid_json":
        (folder / "manifest.json").write_text("{unfinished", encoding="utf-8")
    elif variant == "wrong_type":
        (folder / "manifest.json").write_text("[]", encoding="utf-8")
    elif variant == "missing_field":
        del manifest["canonical"]
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    elif variant == "canonical_metadata":
        manifest["canonical"]["num_frames"] += 1
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    else:
        (folder / "original.wav").write_bytes(b"modified")
    with pytest.raises(AudioInputError):
        load_asset(root, folder.name)
def test_full_15_minute_mono_input_streams_and_resamples(tmp_path):
    source = tmp_path / "15분 모노.wav"
    rate = 48000
    with sf.SoundFile(source, "w", samplerate=rate, channels=1, subtype="PCM_16") as output:
        block = np.zeros((rate, 1), dtype=np.float32)
        for _ in range(900):
            output.write(block)
    folder = ingest_file(source, tmp_path / "managed")
    manifest = load_asset(tmp_path / "managed", folder.name)
    assert manifest["input"]["decoded_num_frames"] == rate * 900
    assert manifest["timeline"]["num_frames"] == RATE * 900
    assert manifest["timeline"]["duration_sec"] == 900
    assert manifest["canonical"]["rms"] == 0
    assert manifest["preprocessing"]["mono_duplicated"]
