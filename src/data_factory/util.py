"""Deterministic RNG derivation, WAV I/O (scipy only), small DSP helpers shared by the factory."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

SEED_NAMES = ("composition", "performance", "instrument", "fx", "mix")


def derive_seeds(master_seed: int, index: int, split: str) -> dict[str, int]:
    """Scene seeds from (master_seed, split, index). SeedSequence is stable across NumPy versions."""
    base = [int(master_seed), int(hashlib.sha256(split.encode()).hexdigest()[:8], 16), int(index)]
    return {n: int(np.random.SeedSequence(base + [i]).generate_state(1)[0]) for i, n in enumerate(SEED_NAMES)}


def make_rng(seed: int) -> np.random.RandomState:
    """Legacy RandomState: its stream is frozen by NumPy, which is what scene reproducibility needs."""
    return np.random.RandomState(int(seed) & 0xFFFFFFFF)


def sub_rng(seed: int, *tags) -> np.random.RandomState:
    h = hashlib.sha256((str(seed) + "|" + "|".join(map(str, tags))).encode()).hexdigest()
    return make_rng(int(h[:8], 16))


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def hash_obj(obj) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def sha256_array(a: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(a, dtype=np.float32).tobytes()).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(1 << 20):
            h.update(b)
    return h.hexdigest()


def tree_sha256(root: str | Path, skip_dirs=(".git",)) -> tuple[str, int, int]:
    """Deterministic hash of a directory tree: sha256 over sorted 'relpath<TAB>filehash' lines. -> (hash, files, bytes)."""
    root = Path(root)
    lines, n, total = [], 0, 0
    for p in sorted(x for x in root.rglob("*") if x.is_file() and not set(x.relative_to(root).parts) & set(skip_dirs)):
        lines.append(f"{p.relative_to(root).as_posix()}\t{sha256_file(p)}")
        n += 1
        total += p.stat().st_size
    return hashlib.sha256("\n".join(lines).encode()).hexdigest(), n, total


def read_wav(path: str | Path, target_sr: int | None = None) -> tuple[np.ndarray, int]:
    """-> (float32 array (channels, samples), sample_rate). PCM8/16/24/32 and float WAV; optional resample."""
    sr, x = wavfile.read(str(path))
    if x.dtype == np.uint8:
        x = (x.astype(np.float32) - 128.0) / 128.0
    elif x.dtype == np.int16:
        x = x.astype(np.float32) / 32768.0
    elif x.dtype == np.int32:  # 24- and 32-bit PCM are both returned left-justified in int32
        x = x.astype(np.float32) / 2147483648.0
    else:
        x = x.astype(np.float32)
    x = x[None, :] if x.ndim == 1 else x.T
    if target_sr and sr != target_sr:
        g = np.gcd(sr, target_sr)
        x = resample_poly(x, target_sr // g, sr // g, axis=1).astype(np.float32)
        sr = target_sr
    return np.ascontiguousarray(x), sr


def write_wav(path: str | Path, x: np.ndarray, sr: int) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(str(path), sr, np.ascontiguousarray(x.T.astype(np.float32)))


def to_stereo(x: np.ndarray) -> np.ndarray:
    if x.shape[0] == 1:
        return np.repeat(x, 2, axis=0)
    return x[:2]


def db_to_lin(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64)))) if x.size else 0.0
