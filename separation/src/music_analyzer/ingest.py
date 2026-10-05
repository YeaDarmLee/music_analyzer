from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import numpy as np
import soundfile as sf

from . import __version__
from .audio import RATE
from .common import read_json, sha256_file, write_json

ALLOWED_FORMATS = {".wav": "wav", ".flac": "flac", ".mp3": "mp3"}
BLOCK_FRAMES = 16384


class AudioInputError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class InputLimits:
    max_file_bytes: int = 1024 ** 3
    min_duration_sec: float = 1
    max_duration_sec: float = 900
    min_sample_rate: int = 8000
    max_sample_rate: int = 192000
    max_decoded_bytes: int = 2 * 1024 ** 3
    probe_timeout_sec: float = 30
    decode_timeout_sec: float = 300
    disk_reserve_bytes: int = 1024 ** 3


def fail(code: str, message: str) -> None:
    raise AudioInputError(code, message)


def _capture(args: list[str], timeout: float) -> str:
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout, check=False,
                                encoding="utf-8", errors="replace")
    except FileNotFoundError:
        fail("TOOL_NOT_AVAILABLE", f"{args[0]} is required on PATH")
    except subprocess.TimeoutExpired:
        fail("TOOL_TIMEOUT", f"{args[0]} exceeded {timeout}s")
    if result.returncode:
        fail("PROBE_FAILED", result.stderr[-4096:].strip() or "Tool returned a nonzero exit code")
    return result.stdout


@lru_cache(maxsize=1)
def tool_versions() -> dict:
    return {name: _capture([name, "-version"], 30).splitlines()[0]
            for name in ("ffmpeg", "ffprobe")}


def probe(path: Path, limits: InputLimits = InputLimits()) -> dict:
    path = path.resolve()
    if path.suffix.lower() not in ALLOWED_FORMATS:
        fail("UNSUPPORTED_EXTENSION", "Supported input formats: WAV, FLAC, MP3")
    if not path.is_file():
        fail("INPUT_NOT_FOUND", "Input must be an existing local file")
    if not 0 < path.stat().st_size <= limits.max_file_bytes:
        fail("FILE_SIZE_LIMIT", "Input is empty or exceeds the file size limit")
    # Only regular local input; no URL or indirect network protocol.
    data = json.loads(_capture([
        "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
        "-show_entries",
        "format=format_name,duration:stream=index,codec_type,codec_name,sample_rate,channels,duration",
        "-of", "json", str(path),
    ], limits.probe_timeout_sec))
    streams = [item for item in data.get("streams", []) if item.get("codec_type") == "audio"]
    if len(streams) != 1:
        fail("AUDIO_STREAM_COUNT", "Input must contain exactly one audio stream")
    stream = streams[0]
    rate, channels = int(stream.get("sample_rate", 0)), int(stream.get("channels", 0))
    if channels not in (1, 2):
        fail("UNSUPPORTED_CHANNELS", "Only mono or stereo input is supported; automatic downmix is disabled")
    if not limits.min_sample_rate <= rate <= limits.max_sample_rate:
        fail("SAMPLE_RATE_LIMIT", "Input sample rate must be between 8kHz and 192kHz")
    formats = data.get("format", {}).get("format_name", "").split(",")
    expected_format = ALLOWED_FORMATS[path.suffix.lower()]
    if expected_format not in formats:
        fail("FORMAT_MISMATCH", "File contents do not match the file extension")
    duration_text = stream.get("duration", data.get("format", {}).get("duration"))
    try:
        reported_duration = float(duration_text)
    except (TypeError, ValueError):
        reported_duration = None
    if reported_duration is not None:
        if not math.isfinite(reported_duration) or reported_duration < 0:
            fail("INVALID_DURATION", "Invalid reported duration")
        # MP3 container padding is not the authoritative sample count.
        if reported_duration > limits.max_duration_sec + 1:
            fail("DURATION_LIMIT", "Reported duration exceeds the preflight limit")
    return {"format": expected_format, "codec": stream.get("codec_name"),
            "sample_rate": rate, "channels": channels,
            "reported_duration_sec": reported_duration}


def _copy_original(source: Path, destination: Path, limits: InputLimits) -> tuple[str, int]:
    before = source.stat()
    digest, count = hashlib.sha256(), 0
    with source.open("rb") as src, destination.open("xb") as dst:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            count += len(block)
            if count > limits.max_file_bytes:
                fail("FILE_SIZE_LIMIT", "Source grew beyond the size limit during copy")
            digest.update(block)
            dst.write(block)
        dst.flush()
        os.fsync(dst.fileno())
    after = source.stat()
    if count != before.st_size or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        fail("INPUT_CHANGED", "Input changed while copying; retry with a stable file")
    if sha256_file(destination) != digest.hexdigest():
        fail("COPY_HASH_MISMATCH", "Original copy verification failed")
    return digest.hexdigest(), count


def stream_decode(source: Path, destination: Path, source_channels: int, out_rate: int,
                  max_frames: int, max_bytes: int, timeout: float,
                  duplicate_mono: bool = False, resample: bool = False) -> dict:
    """Bounded pipe reader. No output file is trusted until EOF and decoder success."""
    args = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror",
            "-err_detect", "explode", "-protocol_whitelist", "file,pipe",
            "-i", str(source), "-map", "0:a:0", "-vn", "-sn", "-dn", "-threads", "1"]
    if resample:
        args += ["-af", f"aresample={out_rate}:async=0", "-ar", str(out_rate)]
    args += ["-c:a", "pcm_f32le", "-f", "f32le", "pipe:1"]
    output_channels = 2 if duplicate_mono else source_channels
    frame_bytes = 4 * source_channels
    max_frames = min(max_frames, max_bytes // (4 * output_channels))
    timed_out = threading.Event()
    process = None
    timer = None
    count, peak, tail = 0, 0.0, b""
    with tempfile.TemporaryFile() as errors:
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors, stdin=subprocess.DEVNULL)
            def abort():
                timed_out.set()
                if process.poll() is None:
                    process.kill()
            timer = threading.Timer(timeout, abort)
            timer.daemon = True
            timer.start()
            with sf.SoundFile(destination, "w", samplerate=out_rate, channels=output_channels,
                              format="WAV", subtype="FLOAT") as output:
                while True:
                    block = process.stdout.read(BLOCK_FRAMES * frame_bytes)
                    if not block:
                        break
                    block = tail + block
                    usable = len(block) - len(block) % frame_bytes
                    tail = block[usable:]
                    if not usable:
                        continue
                    audio = np.frombuffer(block[:usable], dtype="<f4").reshape(-1, source_channels)
                    if not np.isfinite(audio).all():
                        fail("NONFINITE_AUDIO", "Decoder produced NaN or Infinity")
                    count += len(audio)
                    if count > max_frames:
                        fail("DECODE_SIZE_LIMIT", "Decoded audio exceeds the duration or PCM size limit")
                    if duplicate_mono:
                        audio = np.repeat(audio, 2, axis=1)
                    peak = max(peak, float(np.abs(audio).max()))
                    output.write(audio)
            process.wait(timeout=10)
            if timed_out.is_set():
                fail("DECODE_TIMEOUT", f"Decoder exceeded {timeout}s")
            if process.returncode != 0:
                errors.seek(0)
                message = errors.read(4096).decode("utf-8", errors="replace")
                fail("DECODE_FAILED", message.strip() or "Decoder failed")
            if tail or count == 0:
                fail("INVALID_PCM", "Decoded output is empty or contains an incomplete frame")
            return {"num_frames": count, "peak": peak, "args": args}
        except FileNotFoundError:
            fail("TOOL_NOT_AVAILABLE", "FFmpeg is required on PATH")
        finally:
            if timer:
                timer.cancel()
            if process:
                if process.poll() is None:
                    process.kill()
                process.wait()
                if process.stdout:
                    process.stdout.close()


def _wave_properties(path: Path) -> dict:
    peak, samples, energy = 0.0, 0, 0.0
    with sf.SoundFile(path) as audio:
        rate, frames, channels, subtype = audio.samplerate, audio.frames, audio.channels, audio.subtype
        for block in audio.blocks(blocksize=BLOCK_FRAMES, dtype="float32", always_2d=True):
            if not np.isfinite(block).all():
                fail("NONFINITE_AUDIO", "Canonical output contains NaN or Infinity")
            peak = max(peak, float(np.abs(block).max()))
            energy += float(np.sum(block.astype(np.float64) ** 2))
            samples += block.size
    if not samples:
        fail("INVALID_PCM", "Canonical output is empty")
    return {"sample_rate": rate, "num_frames": frames, "channels": channels, "subtype": subtype,
            "peak": peak, "rms": math.sqrt(energy / samples), "over_full_scale": peak > 1}


def _adjust_frames(path: Path, expected: int) -> int:
    # Native decode is authoritative. Correct only a one-frame resampler rounding difference.
    info = sf.info(path)
    adjustment = expected - info.frames
    if abs(adjustment) > 1:
        fail("TIMELINE_MISMATCH", "Resampled frame count differs by more than one frame")
    if adjustment:
        fixed = path.with_name("canonical.adjusting.wav")
        with sf.SoundFile(path) as src, sf.SoundFile(fixed, "w", samplerate=RATE, channels=2,
                                                     format="WAV", subtype="FLOAT") as dst:
            remaining = expected
            while remaining and src.tell() < src.frames:
                block = src.read(min(BLOCK_FRAMES, remaining), dtype="float32", always_2d=True)
                dst.write(block)
                remaining -= len(block)
            if remaining:
                dst.write(np.zeros((remaining, 2), dtype=np.float32))
        os.replace(fixed, path)
    return adjustment


def _validate_asset(folder: Path) -> dict:
    manifest = read_json(folder / "manifest.json")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0" or manifest.get("kind") != "audio_asset" or manifest.get("status") != "ready":
        fail("ASSET_SCHEMA", "Unsupported or incomplete audio asset")
    original_name = manifest["input"]["path"]
    if original_name not in ("original.wav", "original.flac", "original.mp3"):
        fail("ASSET_PATH", "Invalid original path in asset manifest")
    if manifest["canonical"]["path"] != "canonical.wav":
        fail("ASSET_PATH", "Invalid canonical path in asset manifest")
    for field, name in (("input", original_name), ("canonical", "canonical.wav")):
        path = folder / name
        if not path.is_file() or path.is_symlink() or sha256_file(path) != manifest[field]["sha256"]:
            fail("ASSET_HASH_MISMATCH", f"Asset file verification failed: {name}")
    if (folder / original_name).stat().st_size != manifest["input"]["size_bytes"]:
        fail("ASSET_SIZE", "Original size differs from its manifest")
    info = sf.info(folder / "canonical.wav")
    canonical = manifest["canonical"]
    if (canonical["sample_rate"], canonical["channels"], canonical["num_frames"], canonical["subtype"]) != (info.samplerate, info.channels, info.frames, info.subtype):
        fail("ASSET_TIMELINE", "Canonical metadata differs from audio")
    timeline = manifest["timeline"]
    if (info.samplerate, info.channels, info.frames, info.subtype) != (RATE, 2, timeline["num_frames"], "FLOAT"):
        fail("ASSET_TIMELINE", "Canonical audio differs from its timeline")
    if timeline["sample_rate"] != RATE or timeline["channels"] != 2 or timeline["origin_sec"] != 0:
        fail("ASSET_TIMELINE", "Invalid canonical timeline")
    if timeline["duration_sec"] != info.frames / RATE:
        fail("ASSET_TIMELINE", "Duration must be derived from canonical frame count")
    return manifest


def validate_asset(folder: Path) -> dict:
    try:
        return _validate_asset(folder)
    except AudioInputError:
        raise
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise AudioInputError("ASSET_SCHEMA", "Missing, malformed or unreadable asset manifest/files") from error

def load_asset(data_root: Path, asset_id: str) -> dict:
    if not re.fullmatch(r"asset_[0-9a-f]{32}", asset_id):
        fail("ASSET_ID", "Invalid asset ID")
    folder = data_root.resolve() / "inputs" / asset_id
    if not folder.is_dir() or folder.is_symlink():
        fail("ASSET_NOT_FOUND", "No published asset with this ID")
    manifest = validate_asset(folder)
    if manifest["asset_id"] != asset_id:
        fail("ASSET_ID", "Asset manifest ID mismatch")
    return manifest


def ingest_file(source: Path, data_root: Path, limits: InputLimits = InputLimits()) -> Path:
    """S2 asset ingestion only: no model, no GPU, no automatic source deletion."""
    source = source.resolve()
    if source.suffix.lower() not in ALLOWED_FORMATS:
        fail("UNSUPPORTED_EXTENSION", "Supported input formats: WAV, FLAC, MP3")
    if not source.is_file():
        fail("INPUT_NOT_FOUND", "Input must be an existing local file")
    source_size = source.stat().st_size
    if not 0 < source_size <= limits.max_file_bytes:
        fail("FILE_SIZE_LIMIT", "Input is empty or exceeds 1GiB")
    parent = data_root.resolve() / "inputs"
    parent.mkdir(parents=True, exist_ok=True)
    # Conservative budget before touching the original: full native + canonical + copies.
    native_budget = min(limits.max_decoded_bytes, int(limits.max_duration_sec * limits.max_sample_rate * 2 * 4))
    canonical_budget = int(limits.max_duration_sec * RATE * 2 * 4)
    required_space = 2 * (source_size + native_budget + canonical_budget) + limits.disk_reserve_bytes
    if shutil.disk_usage(parent).free < required_space:
        fail("DISK_SPACE", "Insufficient free space for bounded preprocessing")
    asset_id = "asset_" + uuid4().hex
    temporary = parent / (".partial_" + asset_id)
    published = parent / asset_id
    temporary.mkdir()
    try:
        original = temporary / ("original" + source.suffix.lower())
        source_hash, copied_bytes = _copy_original(source, original, limits)
        metadata = probe(original, limits)
        native = temporary / "native.wav"
        native_rate, native_channels = metadata["sample_rate"], metadata["channels"]
        decoded = stream_decode(original, native, native_channels, native_rate,
                                int(limits.max_duration_sec * native_rate),
                                limits.max_decoded_bytes, limits.decode_timeout_sec)
        native_frames = decoded["num_frames"]
        native_duration = native_frames / native_rate
        if not limits.min_duration_sec <= native_duration <= limits.max_duration_sec:
            fail("DURATION_LIMIT", "Decoded duration must be between 1s and 15min")
        canonical = temporary / "canonical.wav"
        expected_frames = (native_frames * RATE + native_rate // 2) // native_rate
        if native_rate == RATE and native_channels == 2:
            shutil.copyfile(native, canonical)
            raw_frames = native_frames
        else:
            converted = stream_decode(native, canonical, native_channels, RATE,
                                      int(limits.max_duration_sec * RATE) + 1,
                                      limits.max_decoded_bytes, limits.decode_timeout_sec,
                                      duplicate_mono=native_channels == 1,
                                      resample=native_rate != RATE)
            raw_frames = converted["num_frames"]
        correction = _adjust_frames(canonical, expected_frames)
        properties = _wave_properties(canonical)
        if (properties["sample_rate"], properties["channels"], properties["num_frames"], properties["subtype"]) != (RATE, 2, expected_frames, "FLOAT"):
            fail("OUTPUT_CONTRACT", "Canonical output contract failed")
        warnings = []
        if native_rate < 22050:
            warnings.append("LOW_SAMPLE_RATE: input bandwidth is limited")
        if metadata["format"] == "mp3":
            warnings.append("LOSSY_INPUT: canonical origin is decoded audio, not container/video timing")
        if properties["rms"] < 1e-8:
            warnings.append("SILENT_INPUT: valid asset; S3 must bypass unsafe model normalization")
        if properties["over_full_scale"]:
            warnings.append("OVER_FULL_SCALE: float32 values are preserved without clipping")
        if correction:
            warnings.append("RESAMPLE_ROUNDING: corrected at most one final frame")
        versions = tool_versions()
        manifest = {
            "schema_version": "1.0", "kind": "audio_asset", "status": "ready",
            "asset_id": asset_id, "pipeline_version": __version__,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "input": {"path": original.name, "original_name": source.name, "sha256": source_hash, "size_bytes": copied_bytes,
                      **metadata, "decoded_num_frames": native_frames,
                      "decoded_duration_sec": native_duration},
            "canonical": {"path": "canonical.wav", "sha256": sha256_file(canonical), **properties},
            "timeline": {"sample_rate": RATE, "channels": 2, "num_frames": expected_frames,
                         "duration_sec": expected_frames / RATE, "origin_sec": 0,
                         "origin_definition": "first decoded sample; no silence trimming"},
            "preprocessing": {
                "mono_duplicated": native_channels == 1, "gain": 1.0, "normalization": "none",
                "resampler": "ffmpeg_swr_aresample_async0" if native_rate != RATE else "none",
                "native_rate": native_rate, "target_rate": RATE,
                "expected_frames_policy": "nearest rational integer, half-up",
                "resampler_raw_frames": raw_frames, "frame_adjustment": correction,
                "frame_adjustment_policy": "trim or zero-pad at most one final frame",
                "decoder": versions, "limits": asdict(limits),
                "implementation_sha256": sha256_file(Path(__file__)),
            },
            "warnings": warnings,
        }
        # Private absolute paths are deliberately not included in the portable manifest.
        write_json(temporary / "manifest.json", manifest)
        validate_asset(temporary)
        native.unlink()
        temporary.rename(published)
        return published
    except OSError as error:
        raise AudioInputError("IO_ERROR", str(error)) from error
    finally:
        # Only remove our uniquely created temporary directory, never the user's source.
        if temporary.exists():
            shutil.rmtree(temporary)
