"""Exact-sum mixer. Stem-local FX -> stem gains -> ONE common scale (level target) -> ONE common peak scale.
mix is defined as the float64 sum of the final stems, so mix == sum(final_stems) holds to float32 rounding (<= 2e-6).
No nonlinear master processing is ever applied to the mix alone."""
from __future__ import annotations

import numpy as np

from .fx import apply_chain
from .targets import ATOMIC_ALL
from .util import db_to_lin, sub_rng


def mix_stems(raw: dict[str, np.ndarray], chains: dict[str, list], mix_cfg: dict, fx_seed: int, sr: int,
              duration_samples: int, crop_start: int = 0) -> tuple[dict[str, np.ndarray], np.ndarray, dict]:
    """raw stems cover `duration_samples`; FX run on all of it (so reverb/delay tails from a pre-roll are present), then
    the first `crop_start` samples are dropped before level/peak scaling."""
    final: dict[str, np.ndarray] = {}
    for s in ATOMIC_ALL:
        if s not in raw:
            final[s] = np.zeros((2, duration_samples - crop_start), np.float32)  # inactive stems are exactly zero
            continue
        x = apply_chain(raw[s], chains.get(s, []), sr, sub_rng(fx_seed, s))[:, crop_start:]
        final[s] = (x * np.float32(db_to_lin(mix_cfg["stem_gain_db"].get(s, 0.0)))).astype(np.float32)
    total = sum(final[s].astype(np.float64) for s in ATOMIC_ALL)
    rms = float(np.sqrt(np.mean(total ** 2)))
    scale = db_to_lin(mix_cfg["target_rms_db"]) / rms if rms > 1e-12 else 1.0
    peak = max(float(np.abs(total).max()) * scale, max((float(np.abs(f).max()) * scale for f in final.values()), default=0.0))
    clip_scale = 1.0
    if peak > mix_cfg["peak_limit"]:
        clip_scale = mix_cfg["peak_limit"] / peak
    g = scale * clip_scale
    final = {s: (f.astype(np.float64) * g).astype(np.float32) for s, f in final.items()}
    mix = sum(f.astype(np.float64) for f in final.values()).astype(np.float32)
    return final, mix, {"level_scale": scale, "clip_scale": clip_scale, "peak": float(np.abs(mix).max())}
