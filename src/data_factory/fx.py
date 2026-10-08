"""Own FX (NumPy/SciPy): gain, pan(balance), RBJ EQ, block compressor, saturation, delay, algorithmic reverb, chorus,
stereo width. All effects are stem-local and parameterised by plain dicts (logged in the scene spec).
Effects keep silence silent (a zero input stays exactly zero), which the inactive-stem QC rule relies on."""
from __future__ import annotations

import numpy as np
from scipy.signal import fftconvolve, lfilter

PROFILES = {
    #  p_* = probability that the effect is present; ranges are (lo, hi)
    "pop_clean": {"reverb": (.5, (.08, .22), (.8, 1.6)), "delay": (.2, (.05, .15)), "comp": .7, "sat": .2, "chorus": .15, "tilt": (-2, 2)},
    "ballad": {"reverb": (.9, (.2, .4), (1.4, 2.4)), "delay": (.3, (.1, .25)), "comp": .4, "sat": .05, "chorus": .2, "tilt": (-3, 1)},
    "rock_dense": {"reverb": (.4, (.05, .15), (.5, 1.1)), "delay": (.1, (.03, .1)), "comp": .9, "sat": .7, "chorus": .1, "tilt": (0, 4)},
    "electronic": {"reverb": (.5, (.1, .3), (.6, 1.8)), "delay": (.6, (.1, .3)), "comp": .8, "sat": .4, "chorus": .5, "tilt": (-1, 3)},
    "dry_rehearsal": {"reverb": (.1, (.02, .08), (.3, .7)), "delay": (.05, (.02, .06)), "comp": .2, "sat": .05, "chorus": 0.0, "tilt": (-2, 2)},
}


def _balance(x, pos):
    th = (pos + 1.0) * np.pi / 4.0
    return x * (np.array([[np.cos(th)], [np.sin(th)]], np.float32) * np.float32(np.sqrt(2.0)))


def _rbj(kind, fc, gain_db, q, sr):
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * min(fc, 0.45 * sr) / sr
    cw, sw = np.cos(w0), np.sin(w0)
    al = sw / (2 * q)
    if kind == "peak":
        b = [1 + al * A, -2 * cw, 1 - al * A]
        a = [1 + al / A, -2 * cw, 1 - al / A]
    else:
        sq = 2 * np.sqrt(A) * al
        if kind == "low_shelf":
            b = [A * ((A + 1) - (A - 1) * cw + sq), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - sq)]
            a = [(A + 1) + (A - 1) * cw + sq, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sq]
        else:
            b = [A * ((A + 1) + (A - 1) * cw + sq), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - sq)]
            a = [(A + 1) - (A - 1) * cw + sq, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sq]
    return np.array(b) / a[0], np.array(a) / a[0]


def eq(x, p, sr):
    for band in p["bands"]:
        b, a = _rbj(band["kind"], band["fc"], band["gain_db"], band.get("q", 0.8), sr)
        x = lfilter(b, a, x, axis=1)
    return x.astype(np.float32)


def comp(x, p, sr, block=64):
    n = x.shape[1]
    nb = (n + block - 1) // block
    pad = np.pad(np.abs(x).max(0), (0, nb * block - n))
    lvl_db = 20 * np.log10(np.maximum(pad.reshape(nb, block).max(1), 1e-9))
    over = np.maximum(lvl_db - p["threshold_db"], 0.0)
    target = -over * (1 - 1 / p["ratio"])  # desired gain change in dB per block
    att = np.exp(-block / (p["attack_ms"] * 1e-3 * sr))
    rel = np.exp(-block / (p["release_ms"] * 1e-3 * sr))
    g, cur = np.empty(nb), 0.0
    for i in range(nb):
        c = att if target[i] < cur else rel
        cur = c * cur + (1 - c) * target[i]
        g[i] = cur
    gain = 10 ** ((np.interp(np.arange(n), (np.arange(nb) + 0.5) * block, g) + p["makeup_db"]) / 20)
    return (x * gain.astype(np.float32)).astype(np.float32)


def sat(x, p, sr):
    d = p["drive"]
    if p["mode"] == "tanh":
        return (np.tanh(d * x) / np.tanh(d)).astype(np.float32)
    return (np.clip(x * d, -1, 1) - (np.clip(x * d, -1, 1) ** 3) / 3.0).astype(np.float32) / (d if d > 1 else 1.0)


def delay(x, p, sr):
    d = int(p["time_ms"] * 1e-3 * sr)
    y = x.copy()
    for k in range(1, p.get("taps", 4) + 1):
        s = d * k
        if s >= x.shape[1]:
            break
        src = x[::-1] if (p.get("pingpong") and k % 2) else x
        y[:, s:] += (p["feedback"] ** k) * src[:, :-s]
    return (x + p["mix"] * (y - x)).astype(np.float32)


def make_ir(rt60, damping, predelay_ms, sr, rng):
    n = int(min(rt60, 2.5) * sr)
    t = np.arange(n) / sr
    ir = rng.randn(2, n) * np.exp(-6.9 * t / rt60)
    if damping > 0:
        k = 1 - damping * 0.9
        ir = lfilter([k], [1, -(1 - k)], ir, axis=1)
    for _ in range(6):  # early reflections
        i = int(rng.uniform(.005, .06) * sr)
        ir[:, i] += rng.uniform(.3, 1.0) * rng.choice([-1, 1], 2)
    ir[:, :int(predelay_ms * 1e-3 * sr)] = 0
    ir /= np.sqrt((ir ** 2).sum(1, keepdims=True)) + 1e-9
    return ir.astype(np.float32)


def reverb(x, p, sr, rng):
    if not np.any(x):
        return x
    ir = make_ir(p["rt60_s"], p["damping"], p["predelay_ms"], sr, rng)
    wet = np.stack([fftconvolve(x[c], ir[c])[:x.shape[1]] for c in range(2)]).astype(np.float32)
    return (1 - p["mix"]) * x + p["mix"] * wet * np.sqrt(np.mean(x ** 2) / max(np.mean(wet ** 2), 1e-12))


def chorus(x, p, sr):
    n = x.shape[1]
    t = np.arange(n)
    d = (p["delay_ms"] + p["depth_ms"] * np.sin(2 * np.pi * p["rate_hz"] * t / sr)) * 1e-3 * sr
    pos = np.clip(t - d, 0, n - 1)
    wet = np.stack([np.interp(pos, t, x[c]) for c in range(2)]).astype(np.float32)
    return ((1 - p["mix"]) * x + p["mix"] * wet).astype(np.float32)


def width(x, p, sr):
    m, s = (x[0] + x[1]) / 2, (x[0] - x[1]) / 2
    return np.stack([m + p["amount"] * s, m - p["amount"] * s]).astype(np.float32)


def apply_chain(x: np.ndarray, chain: list[dict], sr: int, rng: np.random.RandomState) -> np.ndarray:
    for e in chain:
        t = e["type"]
        if t == "gain":
            x = x * np.float32(10 ** (e["db"] / 20))
        elif t == "pan":
            x = _balance(x, e["pos"])
        elif t == "eq":
            x = eq(x, e, sr)
        elif t == "comp":
            x = comp(x, e, sr)
        elif t == "sat":
            x = sat(x, e, sr)
        elif t == "delay":
            x = delay(x, e, sr)
        elif t == "reverb":
            x = reverb(x, e, sr, rng)
        elif t == "chorus":
            x = chorus(x, e, sr)
        elif t == "width":
            x = width(x, e, sr)
        else:
            raise ValueError(f"unknown fx {t}")
    return x.astype(np.float32)


def random_chain(stem: str, profile: str, rng: np.random.RandomState) -> list[dict]:
    pr, u = PROFILES[profile], rng.uniform
    ch: list[dict] = []
    tilt = u(*pr["tilt"])
    ch.append({"type": "eq", "bands": [
        {"kind": "low_shelf", "fc": 120.0, "gain_db": float(u(-3, 3) if stem != "bass" else u(-1, 3)), "q": 0.7},
        {"kind": "peak", "fc": float(np.exp(u(np.log(300), np.log(4000)))), "gain_db": float(u(-3, 3)), "q": float(u(.5, 1.5))},
        {"kind": "high_shelf", "fc": 6000.0, "gain_db": float(tilt), "q": 0.7}]})
    if rng.rand() < pr["sat"]:
        ch.append({"type": "sat", "drive": float(u(1.2, 3.0)), "mode": "tanh" if rng.rand() < .6 else "softclip"})
    if rng.rand() < pr["comp"]:
        ch.append({"type": "comp", "threshold_db": float(u(-24, -10)), "ratio": float(u(2, 6)), "attack_ms": float(u(3, 30)),
                   "release_ms": float(u(60, 250)), "makeup_db": float(u(0, 4))})
    if stem != "bass" and rng.rand() < pr["chorus"]:
        ch.append({"type": "chorus", "rate_hz": float(u(.3, 1.5)), "depth_ms": float(u(1, 4)), "delay_ms": float(u(8, 16)), "mix": float(u(.2, .5))})
    if stem != "bass" and rng.rand() < pr["delay"][0]:
        ch.append({"type": "delay", "time_ms": float(u(120, 420)), "feedback": float(u(.2, .5)), "mix": float(u(*pr["delay"][1])),
                   "taps": 4, "pingpong": bool(rng.rand() < .5)})
    if stem != "bass" and rng.rand() < pr["reverb"][0]:
        ch.append({"type": "reverb", "rt60_s": float(u(*pr["reverb"][2])), "damping": float(u(.2, .7)),
                   "predelay_ms": float(u(0, 30)), "mix": float(u(*pr["reverb"][1]))})
    if stem != "bass":
        ch.append({"type": "width", "amount": float(u(.7, 1.4))})
    ch.append({"type": "pan", "pos": float(u(-.5, .5) if stem in ("piano", "synth") else (u(-.15, .15) if stem != "drums" else u(-.2, .2)))})
    return ch
