from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

RATE = 44100


def write_raw(path: Path, audio: np.ndarray) -> dict:
    """DEM-RAW-01: frames x channels; lossless float32, no clamp or normalization."""
    if audio.dtype != np.float32 or audio.ndim != 2 or audio.shape[1] != 2:
        raise ValueError("Raw audio must be float32 stereo [frames, channels]")
    if len(audio) == 0 or not np.isfinite(audio).all():
        raise ValueError("Empty or non-finite raw output")
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio, RATE, format="WAV", subtype="FLOAT")
    decoded, rate = sf.read(path, dtype="float32", always_2d=True)
    info = sf.info(path)
    if rate != RATE or info.subtype != "FLOAT" or not np.array_equal(audio, decoded):
        raise ValueError("RAW_ROUNDTRIP_MISMATCH")
    peak = float(np.abs(audio).max())
    return {"sample_rate": rate, "channels": info.channels, "num_frames": info.frames,
            "subtype": info.subtype, "peak": peak, "over_full_scale": peak > 1,
            "roundtrip_exact": True, "clip_mode": "none", "gain": 1.0}


def make_fixture(path: Path, seconds: int = 10) -> Path:
    """Synthetic engineering signal. Not a real song or separation-quality benchmark."""
    rng = np.random.default_rng(0)
    t = np.arange(seconds * RATE, dtype=np.float64) / RATE
    left = .12 * np.sin(2 * np.pi * 110 * t) + .07 * np.sin(2 * np.pi * 440 * t)
    right = .10 * np.sin(2 * np.pi * 110 * t) + .09 * np.sin(2 * np.pi * 660 * t)
    bursts = np.exp(-35 * (t % .5)) * rng.standard_normal(len(t)) * .04
    audio = np.column_stack((left + bursts, right + .8 * bursts)).astype(np.float32)
    write_raw(path, audio)
    return path


def write_raw_streaming(path: Path, audio: np.ndarray, check=lambda: None) -> dict:
    """Bounded-memory exact float32 storage verification for full songs."""
    if audio.dtype != np.float32 or audio.ndim != 2 or audio.shape[1] != 2 or not len(audio):
        raise ValueError("Expected nonempty float32 stereo")
    path.parent.mkdir(parents=True, exist_ok=True)
    block_frames = RATE * 10
    peak = 0.0
    with sf.SoundFile(path, "w", samplerate=RATE, channels=2, format="WAV", subtype="FLOAT") as output:
        for start in range(0, len(audio), block_frames):
            check()
            block = audio[start:start + block_frames]
            if not np.isfinite(block).all():
                raise ValueError("Non-finite raw output")
            peak = max(peak, float(np.abs(block).max()))
            output.write(block)
    with sf.SoundFile(path) as decoded:
        for start in range(0, len(audio), block_frames):
            check()
            block = decoded.read(min(block_frames, len(audio) - start), dtype="float32", always_2d=True)
            if not np.array_equal(audio[start:start + len(block)], block) or len(block) != min(block_frames, len(audio) - start):
                raise ValueError("RAW_ROUNDTRIP_MISMATCH")
    info = sf.info(path)
    if (info.samplerate, info.channels, info.frames, info.subtype) != (RATE, 2, len(audio), "FLOAT"):
        raise ValueError("RAW_METADATA_MISMATCH")
    return {"sample_rate": RATE, "channels": 2, "num_frames": len(audio),
            "subtype": "FLOAT", "peak": peak, "over_full_scale": peak > 1,
            "roundtrip_exact": True, "clip_mode": "none", "gain": 1.0}
