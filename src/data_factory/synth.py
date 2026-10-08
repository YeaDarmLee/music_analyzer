"""OUR DSP synth: band-limited (PolyBLEP) oscillators, unison, FM(2-op), ADSR, biquad filter with envelope/LFO modulation,
vibrato/tremolo/PWM, glide, patch randomizer + rule-based patch labels, and a procedural drum synth.
Everything is deterministic given the RandomState and runs on NumPy/SciPy only."""
from __future__ import annotations

import numpy as np
from scipy.signal import lfilter

from .schema import NoteEvent

LABEL_RULES_VERSION = "labels_v1"
SHAPES = ("sine", "saw", "square", "triangle")


# --- oscillators ------------------------------------------------------------------------------------------------
def _polyblep(t, dt):
    out = np.zeros_like(t)
    m1 = t < dt
    x = t[m1] / dt[m1]
    out[m1] = x + x - x * x - 1.0
    m2 = t > 1.0 - dt
    x = (t[m2] - 1.0) / dt[m2]
    out[m2] = x * x + x + x + 1.0
    return out


def osc(shape: str, phase: np.ndarray, dt: np.ndarray, pw=0.5) -> np.ndarray:
    if shape == "sine":
        return np.sin(2 * np.pi * phase)
    if shape == "saw":
        return 2.0 * phase - 1.0 - _polyblep(phase, dt)
    if shape == "square":
        pw = np.broadcast_to(np.asarray(pw, dtype=np.float64), phase.shape)
        return np.where(phase < pw, 1.0, -1.0) + _polyblep(phase, dt) - _polyblep((phase + 1.0 - pw) % 1.0, dt)
    if shape == "triangle":
        return 2.0 * np.abs(2.0 * phase - 1.0) - 1.0
    raise ValueError(shape)


def adsr(n_hold: int, n_rel: int, a: float, d: float, s: float, r: float, sr: int) -> np.ndarray:
    """Envelope over hold + release samples. Release starts from the level reached at note-off."""
    na, nd = max(int(a * sr), 1), max(int(d * sr), 1)
    t = np.arange(n_hold)
    env = np.where(t < na, t / na, np.where(t < na + nd, 1.0 + (s - 1.0) * (t - na) / nd, s)).astype(np.float64)
    last = env[-1] if n_hold else 0.0
    rel = last * np.exp(-6.9 * np.arange(n_rel) / max(n_rel, 1))
    return np.concatenate([env, rel])


def biquad(kind: str, fc: float, q: float, sr: int):
    fc = float(np.clip(fc, 20.0, 0.45 * sr))
    w0 = 2 * np.pi * fc / sr
    al, cw = np.sin(w0) / (2 * q), np.cos(w0)
    if kind == "lp":
        b, a = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2], [1 + al, -2 * cw, 1 - al]
    elif kind == "hp":
        b, a = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2], [1 + al, -2 * cw, 1 - al]
    else:  # bp (constant 0 dB peak)
        b, a = [al, 0.0, -al], [1 + al, -2 * cw, 1 - al]
    a0 = a[0]
    return np.array(b) / a0, np.array(a) / a0


# --- patches ---------------------------------------------------------------------------------------------------------
def default_patch() -> dict:
    return {"osc": [{"shape": "saw", "level": 1.0, "detune_cents": 0.0, "octave": 0, "pw": 0.5}], "sub": 0.0, "noise": 0.0,
            "fm": None, "unison": {"voices": 1, "detune_cents": 0.0, "spread": 0.0},
            "amp_env": {"a": 0.01, "d": 0.2, "s": 0.7, "r": 0.2},
            "filter": {"type": "lp", "cutoff_hz": 4000.0, "res": 0.2, "env_amount": 0.0, "key_track": 0.5,
                       "env": {"a": 0.01, "d": 0.3, "s": 0.3, "r": 0.2}},
            "lfo": {"rate_hz": 5.0, "vibrato_cents": 0.0, "tremolo": 0.0, "pwm": 0.0, "filter": 0.0, "delay_s": 0.0},
            "glide_s": 0.0, "gain_db": 0.0, "pan": 0.0}


def random_patch(family: str, rng: np.random.RandomState) -> dict:
    u, ch = rng.uniform, lambda xs: xs[rng.randint(len(xs))]
    p = default_patch()
    p["family_hint"] = family
    if family == "pad":
        p["osc"] = [{"shape": ch(["saw", "square", "triangle"]), "level": 1.0, "detune_cents": 0.0, "octave": 0, "pw": u(.3, .5)},
                    {"shape": ch(["saw", "triangle"]), "level": u(.5, 1), "detune_cents": u(5, 15), "octave": ch([0, 1]), "pw": .5}]
        p["amp_env"] = {"a": u(.25, 1.2), "d": u(.3, 1), "s": u(.6, .95), "r": u(.6, 2.0)}
        p["unison"] = {"voices": int(ch([3, 5])), "detune_cents": u(8, 22), "spread": u(.5, 1)}
        p["filter"].update(cutoff_hz=u(800, 3500), res=u(.1, .4), env_amount=u(0, .3))
        p["lfo"].update(rate_hz=u(.2, .8), filter=u(0, .3), pwm=u(0, .3))
    elif family == "lead":
        p["osc"] = [{"shape": ch(["saw", "square"]), "level": 1.0, "detune_cents": 0.0, "octave": 0, "pw": u(.3, .6)}]
        p["amp_env"] = {"a": u(.005, .08), "d": u(.1, .4), "s": u(.6, .9), "r": u(.1, .35)}
        p["unison"] = {"voices": int(ch([1, 2, 3])), "detune_cents": u(5, 14), "spread": u(.2, .7)}
        p["filter"].update(cutoff_hz=u(1500, 6000), res=u(.2, .6), env_amount=u(.2, .6))
        p["lfo"].update(rate_hz=u(4.5, 6.5), vibrato_cents=u(5, 25), delay_s=u(.1, .4))
    elif family in ("pluck", "arp"):
        p["osc"] = [{"shape": ch(["saw", "square", "triangle"]), "level": 1.0, "detune_cents": 0.0, "octave": 0, "pw": u(.3, .5)}]
        p["amp_env"] = ({"a": u(.001, .01), "d": u(.15, .5), "s": u(0, .1), "r": u(.1, .4)} if family == "pluck"
                        else {"a": u(.001, .01), "d": u(.04, .14), "s": u(.2, .5), "r": u(.05, .18)})
        p["filter"].update(cutoff_hz=u(800, 3000), res=u(.2, .5), env_amount=u(.5, .9))
        p["filter"]["env"] = {"a": .002, "d": u(.1, .35), "s": 0.0, "r": .1}
        p["unison"] = {"voices": int(ch([1, 2])), "detune_cents": u(4, 10), "spread": u(.2, .6)}
    elif family == "synth_bass":
        p["osc"] = [{"shape": ch(["saw", "square"]), "level": 1.0, "detune_cents": 0.0, "octave": -1, "pw": u(.35, .5)}]
        p["sub"] = u(.4, .9)
        p["amp_env"] = {"a": u(.003, .02), "d": u(.15, .4), "s": u(.5, .9), "r": u(.08, .25)}
        p["filter"].update(cutoff_hz=u(300, 1200), res=u(.2, .5), env_amount=u(.3, .7), key_track=u(.2, .6))
        p["glide_s"] = ch([0.0, 0.0, u(.03, .1)])
    elif family == "keys":
        p["osc"] = [{"shape": "sine", "level": 1.0, "detune_cents": 0.0, "octave": 0, "pw": .5}]
        p["fm"] = {"ratio": ch([1.0, 2.0, 3.0, 4.0]), "index": u(1, 4), "index_decay_s": u(.15, .6)}
        p["amp_env"] = {"a": u(.002, .01), "d": u(.4, 1.0), "s": u(.1, .35), "r": u(.2, .6)}
        p["filter"].update(cutoff_hz=u(3000, 9000))
    else:  # fx
        p["osc"] = [{"shape": ch(["saw", "square"]), "level": u(.3, 1), "detune_cents": u(0, 40), "octave": ch([-1, 0, 1]), "pw": .5}]
        p["noise"] = u(.3, .9)
        p["fm"] = {"ratio": u(1.5, 7.5), "index": u(5, 10), "index_decay_s": u(.5, 2)}
        p["amp_env"] = {"a": u(.05, .6), "d": u(.3, 1), "s": u(.2, .6), "r": u(.5, 1.5)}
        p["filter"].update(cutoff_hz=u(500, 5000), res=u(.3, .7), env_amount=u(.3, .8))
        p["lfo"].update(rate_hz=u(.3, 6), filter=u(.2, .7))
    p["gain_db"] = float(u(-4, 0))
    p["pan"] = float(u(-.3, .3))
    p["label"] = label_patch(p)
    p["label_rules_version"] = LABEL_RULES_VERSION
    return p


def label_patch(p: dict) -> str:
    """Rule-based label from the generated parameters (labels_v1). Order matters; the first matching rule wins."""
    a, d, s, r = (p["amp_env"][k] for k in "adsr")
    lowest = min(o["octave"] for o in p["osc"])
    if lowest <= -1 and p["sub"] >= 0.3:
        return "SYNTH_BASS"
    if p["noise"] >= 0.3 or (p["fm"] and p["fm"]["index"] > 5):
        return "FX"
    if p["fm"]:
        return "KEYS"
    if a >= 0.25 and r >= 0.5 and s >= 0.5:
        return "PAD"
    if a <= 0.02 and s <= 0.15 and d >= 0.15:
        return "PLUCK"
    if a <= 0.02 and d < 0.15 and r <= 0.2:
        return "ARP"
    if s >= 0.5 and a < 0.25:
        return "LEAD"
    return "OTHER"


# --- voice rendering -------------------------------------------------------------------------------------------------
def render_note(patch: dict, midi_pitch: float, dur_s: float, velocity: int, sr: int, rng: np.random.RandomState,
                glide_from: float | None = None) -> np.ndarray:
    ae = patch["amp_env"]
    n_hold, n_rel = max(int(dur_s * sr), 1), max(int(ae["r"] * sr), 1)
    n = n_hold + n_rel
    t = np.arange(n) / sr
    lfo = patch["lfo"]
    lfo_sig = np.sin(2 * np.pi * lfo["rate_hz"] * t + rng.uniform(0, 2 * np.pi))
    lfo_ramp = np.clip((t - lfo["delay_s"]) / max(lfo["delay_s"], 1e-3), 0, 1) if lfo["delay_s"] > 0 else 1.0
    f0 = 440.0 * 2.0 ** ((midi_pitch - 69) / 12.0)
    pitch_mod = np.ones(n)
    if lfo["vibrato_cents"]:
        pitch_mod = 2.0 ** (lfo["vibrato_cents"] * lfo_sig * lfo_ramp / 1200.0)
    f_inst = f0 * pitch_mod
    if glide_from is not None and patch["glide_s"] > 0:
        g = np.exp(-t / max(patch["glide_s"] / 4, 1e-4))
        f_inst = f_inst * 2.0 ** ((glide_from - midi_pitch) / 12.0 * g)
    uni = patch["unison"]
    V = max(int(uni["voices"]), 1)
    left, right = np.zeros(n), np.zeros(n)
    for v in range(V):
        pos = (v / (V - 1) * 2 - 1) if V > 1 else 0.0
        cents = uni["detune_cents"] * pos
        voice = np.zeros(n)
        for k, o in enumerate(patch["osc"]):
            f = f_inst * 2.0 ** ((o["detune_cents"] + cents) / 1200.0 + o["octave"])
            dt = np.minimum(f / sr, 0.49)
            phase = (rng.uniform() + np.cumsum(dt)) % 1.0
            if k == 0 and patch["fm"]:
                fm = patch["fm"]
                idx = fm["index"] * np.exp(-t / max(fm["index_decay_s"], 1e-3))
                voice += o["level"] * np.sin(2 * np.pi * phase + idx * np.sin(2 * np.pi * fm["ratio"] * phase))
            else:
                pw = o["pw"] + 0.4 * lfo["pwm"] * lfo_sig if o["shape"] == "square" else o["pw"]
                voice += o["level"] * osc(o["shape"], phase, dt, np.clip(pw, 0.05, 0.95))
        if patch["sub"]:
            ph = (np.cumsum(np.minimum(f_inst * 0.5 / sr, 0.49))) % 1.0
            voice += patch["sub"] * np.sin(2 * np.pi * ph)
        if patch["noise"]:
            voice += patch["noise"] * rng.randn(n) * 0.5
        th = (pos * uni["spread"] + 1.0) * np.pi / 4.0
        left += voice * np.cos(th)
        right += voice * np.sin(th)
    x = np.stack([left, right]) * (np.sqrt(2.0) / np.sqrt(V))
    # filter: blend of a closed and an open static biquad driven by the filter envelope (+ LFO)
    fl = patch["filter"]
    fc = fl["cutoff_hz"] * 2.0 ** (fl["key_track"] * (midi_pitch - 60) / 12.0) * (0.7 + 0.6 * velocity / 127.0)
    q = 0.5 + 8.0 * fl["res"]
    if fl["env_amount"] > 0 or lfo["filter"] > 0:
        fe = fl["env"]
        e = adsr(n_hold, n_rel, fe["a"], fe["d"], fe["s"], fe["r"], sr)[:n] * fl["env_amount"]
        e = np.clip(e + 0.5 * lfo["filter"] * lfo_sig * lfo_ramp, 0.0, 1.0)
        bc, ac = biquad(fl["type"], fc, q, sr)
        bo, ao = biquad(fl["type"], fc * (1 + 5 * max(fl["env_amount"], lfo["filter"])), q, sr)
        x = (1 - e) * lfilter(bc, ac, x, axis=1) + e * lfilter(bo, ao, x, axis=1)
    else:
        b, a = biquad(fl["type"], fc, q, sr)
        x = lfilter(b, a, x, axis=1)
    env = adsr(n_hold, n_rel, ae["a"], ae["d"], ae["s"], ae["r"], sr)
    if lfo["tremolo"]:
        env = env * (1 - lfo["tremolo"] * 0.5 * (1 + lfo_sig))
    g = 10 ** (patch["gain_db"] / 20) * (velocity / 127.0) ** 0.8 * 0.35
    pan = (patch["pan"] + 1) * np.pi / 4
    x = x * env * g * np.array([[np.cos(pan)], [np.sin(pan)]]) * np.sqrt(2)
    return x.astype(np.float32)


class SynthEngine:
    def __init__(self, patch: dict, sr: int = 44100, saturation: float = 0.0):
        self.patch, self.sr, self.sat = patch, sr, saturation

    def render(self, events: list[NoteEvent], duration_samples: int, rng: np.random.RandomState) -> np.ndarray:
        out = np.zeros((2, duration_samples), np.float32)
        for ev in sorted(events, key=lambda e: (e.start, e.pitch)):
            s0 = int(round(ev.start * self.sr))
            if s0 >= duration_samples:
                continue
            y = render_note(self.patch, ev.pitch, max(ev.end - ev.start, 0.01), ev.velocity, self.sr, rng,
                            glide_from=ev.meta.get("glide_from"))
            n = min(y.shape[1], duration_samples - s0)
            out[:, s0:s0 + n] += y[:, :n]
        if self.sat > 0:
            out = np.tanh(out * (1 + self.sat)) / np.tanh(1 + self.sat)
        return out


# --- drums ------------------------------------------------------------------------------------------------------------
DRUM_KEYS = {"kick": 36, "snare": 38, "hat_closed": 42, "tom": 45, "hat_open": 46, "crash": 49}
KEY_TO_ROLE = {v: k for k, v in DRUM_KEYS.items()}


def random_kit(rng: np.random.RandomState) -> dict:
    u = rng.uniform
    return {"kick_f0": u(110, 180), "kick_f1": u(40, 58), "kick_decay": u(.2, .45), "kick_click": u(.2, .8),
            "snare_f": u(170, 230), "snare_noise": u(.5, 1.0), "snare_decay": u(.12, .25), "snare_bp": u(1500, 4000),
            "hat_decay": u(.03, .08), "open_decay": u(.25, .5), "hat_hp": u(6000, 9000), "tom_f": u(90, 180),
            "crash_decay": u(1.0, 2.0), "pan_hat": u(-.3, .3), "pan_tom": u(-.4, .4)}


def _hit(role: str, vel: int, kit: dict, sr: int, rng: np.random.RandomState) -> np.ndarray:
    g = (vel / 127.0) ** 0.8
    t = lambda d: np.arange(int(d * sr)) / sr
    if role == "kick":
        tt = t(kit["kick_decay"] * 1.5)
        f = kit["kick_f1"] + (kit["kick_f0"] - kit["kick_f1"]) * np.exp(-tt / 0.03)
        y = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-tt / kit["kick_decay"])
        y[:int(.003 * sr)] += kit["kick_click"] * rng.randn(int(.003 * sr)) * 0.5
        return y * g * 0.9, 0.0
    if role == "snare":
        tt = t(kit["snare_decay"] * 2)
        b, a = biquad("bp", kit["snare_bp"], 0.8, sr)
        noise = lfilter(b, a, rng.randn(len(tt))) * np.exp(-tt / kit["snare_decay"]) * kit["snare_noise"] * 2.2
        body = np.sin(2 * np.pi * kit["snare_f"] * tt) * np.exp(-tt / 0.07) * 0.6
        return (noise + body) * g * 0.7, 0.0
    if role in ("hat_closed", "hat_open"):
        dec = kit["hat_decay"] if role == "hat_closed" else kit["open_decay"]
        tt = t(dec * 3)
        b, a = biquad("hp", kit["hat_hp"], 0.7, sr)
        metal = sum(np.sign(np.sin(2 * np.pi * f * tt)) for f in (3100, 4300, 5700, 7100)) * 0.1
        y = lfilter(b, a, rng.randn(len(tt)) * 0.6 + metal) * np.exp(-tt / dec)
        return y * g * 0.5, kit["pan_hat"]
    if role == "tom":
        tt = t(.5)
        f = kit["tom_f"] * (1 + 0.5 * np.exp(-tt / 0.04))
        return np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-tt / 0.15) * g * 0.8, kit["pan_tom"]
    tt = t(kit["crash_decay"] * 2)  # crash
    b, a = biquad("hp", 4000, 0.7, sr)
    return lfilter(b, a, rng.randn(len(tt))) * np.exp(-tt / kit["crash_decay"]) * g * 0.45, 0.2


class DrumSynth:
    def __init__(self, kit: dict, sr: int = 44100):
        self.kit, self.sr = kit, sr

    def render(self, events: list[NoteEvent], duration_samples: int, rng: np.random.RandomState) -> np.ndarray:
        out = np.zeros((2, duration_samples), np.float32)
        for ev in sorted(events, key=lambda e: (e.start, e.pitch)):
            s0 = int(round(ev.start * self.sr))
            role = KEY_TO_ROLE.get(ev.pitch)
            if role is None or s0 >= duration_samples:
                continue
            y, pan = _hit(role, ev.velocity, self.kit, self.sr, rng)
            if role == "hat_open" and ev.end > ev.start:  # choke by next hat: end marks the choke time
                keep = int((ev.end - ev.start) * self.sr)
                if keep < len(y):
                    y = y[:keep + 1].copy()
                    y[-int(.01 * self.sr):] *= np.linspace(1, 0, min(int(.01 * self.sr), len(y)))
            th = (pan + 1) * np.pi / 4
            n = min(len(y), duration_samples - s0)
            out[0, s0:s0 + n] += y[:n] * np.cos(th) * np.sqrt(2)
            out[1, s0:s0 + n] += y[:n] * np.sin(th) * np.sqrt(2)
        return out
