"""Performance generators: turn a composition into NoteEvents per instrument (piano, bass, drums, synth roles).
All humanization uses the supplied deterministic RNG. RULES_VERSION is recorded in each scene."""
from __future__ import annotations

import numpy as np

from .schema import NoteEvent
from .synth import DRUM_KEYS

RULES_VERSION = "perf_rules_v2"  # v2: per-chord sustain pedal state (CC64) on piano events
PIANO_PATTERNS = ("block", "broken", "arpeggio", "comping", "octave_bass", "ballad")
BASS_PATTERNS = ("root_whole", "root_eighths", "root_fifth_octave", "syncopated", "walking")
DRUM_GROOVES = ("pop", "rock", "four_floor", "halftime", "ballad", "sparse")
SYNTH_ROLES = ("pad", "lead", "arp", "pluck")


class _Clock:
    def __init__(self, comp: dict, duration_s: float):
        self.spb, self.dur = 60.0 / comp["bpm"], duration_s

    def t(self, beat: float) -> float:
        return beat * self.spb


def _voicing(chord: dict, center: int, rng, n_notes=None) -> list[int]:
    pcs = chord["pcs"]
    base = [center - 12 + ((pc - (center - 12)) % 12) for pc in pcs]  # lowest placement above center-12
    inv = int(rng.randint(len(base)))
    notes = sorted(base)
    for _ in range(inv):
        notes = notes[1:] + [notes[0] + 12]
    if n_notes and n_notes > len(notes):
        notes = notes + [notes[0] + 12]
    return [int(n) for n in notes]


def _ev(inst, pitch, vel, s, e, rng, jitter_ms, art="", meta=None):
    s = max(s + rng.randn() * jitter_ms * 1e-3, 0.0)
    return NoteEvent(inst, int(pitch), int(np.clip(vel, 1, 127)), float(s), float(max(e, s + 0.02)), art, 0, meta or {})


def piano(comp: dict, dur: float, rng, pattern: str | None = None) -> tuple[list[NoteEvent], dict]:
    clk, ev = _Clock(comp, dur), []
    pattern = pattern or PIANO_PATTERNS[rng.randint(len(PIANO_PATTERNS))]
    r = rng.rand()  # pedal mode: scene-level up / down, or per-chord (phrase) changes
    pedal_mode = "up" if r < 0.3 else "mixed" if r < 0.6 else "down"
    center = int(rng.randint(58, 68))
    base_vel = int(rng.randint(55, 100))
    for c in comp["chords"]:
        b0, b1 = c["start_beat"], c["start_beat"] + c["dur_beats"]
        pedal = pedal_mode == "down" or (pedal_mode == "mixed" and rng.rand() < 0.5)
        n_before = len(ev)
        v = _voicing(c, center, rng)
        end_default = clk.t(b1) + (0.3 if pedal else -0.05)
        if pattern == "block" or pattern == "ballad":
            for i, p in enumerate(v):
                ev.append(_ev("piano", p, base_vel + rng.randint(-8, 8), clk.t(b0) + i * 0.012, end_default, rng, 10))
            if pattern == "ballad" and rng.rand() < .6:
                ev.append(_ev("piano", v[-1] + 12 if v[-1] < 84 else v[-1], base_vel - 10, clk.t(b0 + 2), clk.t(b0 + 3.5), rng, 15))
        elif pattern in ("broken", "arpeggio"):
            step = 0.5 if pattern == "broken" else 0.25
            seq = v + v[::-1][1:-1] if pattern == "arpeggio" else v
            b, i = b0, 0
            while b < b1 - 1e-6:
                ev.append(_ev("piano", seq[i % len(seq)], base_vel + rng.randint(-10, 6) + (8 if i % 4 == 0 else 0),
                              clk.t(b), clk.t(min(b + step * 3, b1)) + (0.2 if pedal else 0), rng, 8))
                b, i = b + step, i + 1
        elif pattern == "comping":
            for off in (0, 1.5, 2, 3.5):
                if off < c["dur_beats"] and rng.rand() < .85:
                    for p in v:
                        ev.append(_ev("piano", p, base_vel + rng.randint(-8, 8), clk.t(b0 + off), clk.t(b0 + off + .45), rng, 10))
        else:  # octave_bass: left-hand octave + right-hand chord
            root = c["root_pc"] + 36 if c["root_pc"] + 36 >= 36 else c["root_pc"] + 48
            ev.append(_ev("piano", root, base_vel, clk.t(b0), clk.t(b1), rng, 10))
            ev.append(_ev("piano", root + 12, base_vel - 10, clk.t(b0), clk.t(b1), rng, 10))
            for off in np.arange(0, c["dur_beats"], 1.0):
                for p in v:
                    ev.append(_ev("piano", p, base_vel - 5 + rng.randint(-6, 6), clk.t(b0 + off), clk.t(b0 + off + .8), rng, 10))
        for e in ev[n_before:]:
            e.meta = {"cc64": 127 if pedal else 0}
    return [e for e in ev if e.start < dur], {"pattern": pattern, "pedal_mode": pedal_mode, "rules": RULES_VERSION}


def bass(comp: dict, dur: float, rng, pattern: str | None = None, glide: bool = False) -> tuple[list[NoteEvent], dict]:
    clk, ev = _Clock(comp, dur), []
    pattern = pattern or BASS_PATTERNS[rng.randint(len(BASS_PATTERNS))]
    base_vel = int(rng.randint(70, 110))
    prev = None
    chords = comp["chords"]
    for ci, c in enumerate(chords):
        b0, bl = c["start_beat"], c["dur_beats"]
        r = 28 + (c["root_pc"] - 28) % 12  # E1..D#2
        nxt = chords[ci + 1]["root_pc"] if ci + 1 < len(chords) else None
        fifth = r + 7
        plan: list[tuple[float, float, int, int]] = []  # (offset beats, length, pitch, vel delta)
        if pattern == "root_whole":
            plan = [(0, bl * .95, r, 0)]
        elif pattern == "root_eighths":
            plan = [(o, .45, r if i % 4 != 3 else r + 12, -10 if i % 2 else 0) for i, o in enumerate(np.arange(0, bl, .5))]
        elif pattern == "root_fifth_octave":
            seq = [r, fifth, r + 12, fifth]
            plan = [(o, .9, seq[i % 4], 0) for i, o in enumerate(np.arange(0, bl, 1.0))]
        elif pattern == "syncopated":
            plan = [(o, .4, r, -6 * (i % 2)) for i, o in enumerate(x for x in (0, 1.5, 2.5, 3) if x < bl)]
            if bl > 3.5 and rng.rand() < .5:
                plan.append((3.5, .3, r + 12, -15))
        else:  # walking: root, third-ish, fifth, approach to next root
            third = r + (3 if c["quality"] in ("min", "dim") else 4)
            seq = [r, third, fifth, r + 12]
            plan = [(o, .9, seq[i % 4], 0) for i, o in enumerate(np.arange(0, bl, 1.0))]
            if nxt is not None and bl >= 1:
                ap = 28 + (nxt - 28) % 12
                plan[-1] = (plan[-1][0], .9, ap + (1 if rng.rand() < .5 else -1), -5)
        for off, ln, p, dv in plan:
            if b0 + off >= comp["n_bars"] * comp["beats_per_bar"]:
                continue
            meta = {"glide_from": prev} if (glide and prev is not None and prev != p and rng.rand() < .5) else {}
            ev.append(_ev("bass", p, base_vel + dv + rng.randint(-6, 6), clk.t(b0 + off), clk.t(b0 + off + ln), rng, 8, meta=meta))
            prev = p
            if rng.rand() < .08:  # ghost note
                ev.append(_ev("bass", p, 28 + rng.randint(10), clk.t(b0 + off + .75), clk.t(b0 + off + .95), rng, 8, "ghost"))
    return [e for e in ev if e.start < dur], {"pattern": pattern, "glide": glide, "rules": RULES_VERSION}


GROOVES = {
    "pop": {"kick": [0, 8, 10], "snare": [4, 12], "hat_closed": list(range(0, 16, 2))},
    "rock": {"kick": [0, 6, 8, 14], "snare": [4, 12], "hat_closed": list(range(0, 16, 2)), "hat_open": [15]},
    "four_floor": {"kick": [0, 4, 8, 12], "snare": [4, 12], "hat_closed": [], "hat_open": [2, 6, 10, 14]},
    "halftime": {"kick": [0, 10], "snare": [8], "hat_closed": list(range(0, 16, 2))},
    "ballad": {"kick": [0, 10], "snare": [8], "hat_closed": [0, 4, 8, 12]},
    "sparse": {"kick": [0], "snare": [], "hat_closed": [0, 4, 8, 12]},
}


def drums(comp: dict, dur: float, rng, groove: str | None = None, swing: float | None = None) -> tuple[list[NoteEvent], dict]:
    clk, ev = _Clock(comp, dur), []
    groove = groove or DRUM_GROOVES[rng.randint(len(DRUM_GROOVES))]
    swing = float(rng.uniform(0, .25) if swing is None else swing)
    g = GROOVES[groove]
    dens = comp["density"]
    fill_bar = comp["n_bars"] - 1 if rng.rand() < .4 else -1
    step_beats = 0.25
    for bar in range(comp["n_bars"]):
        for role, steps in g.items():
            for st in steps:
                if role in ("hat_closed",) and rng.rand() > .55 + .45 * dens:
                    continue
                beat = bar * 4 + st * step_beats + (swing * step_beats * 0.5 if st % 2 else 0.0)
                vel = {"kick": 100, "snare": 96, "hat_closed": 70 + (14 if st % 4 == 0 else 0), "hat_open": 85}[role]
                if bar == fill_bar and st >= 12 and role in ("hat_closed", "kick"):
                    continue
                ev.append(_ev("drums", DRUM_KEYS[role], vel + rng.randint(-8, 8), clk.t(beat), clk.t(beat + .2), rng, 5))
        if rng.rand() < .35 and "snare" in g and g["snare"]:
            st = int(rng.choice([3, 7, 11, 15]))
            ev.append(_ev("drums", DRUM_KEYS["snare"], 25 + rng.randint(15), clk.t(bar * 4 + st * step_beats), clk.t(bar * 4 + st * step_beats + .1), rng, 5, "ghost"))
        if bar == 0 and rng.rand() < .5:
            ev.append(_ev("drums", DRUM_KEYS["crash"], 100, clk.t(0), clk.t(1), rng, 4))
        if bar == fill_bar:
            for k, st in enumerate(range(12, 16)):
                ev.append(_ev("drums", DRUM_KEYS["tom" if k < 3 else "snare"], 80 + 6 * k, clk.t(bar * 4 + st * step_beats), clk.t(bar * 4 + st * step_beats + .2), rng, 5, "fill"))
    # open-hat choke: an open hat ends where the next closed/open hat begins
    hats = sorted((e for e in ev if e.pitch in (DRUM_KEYS["hat_closed"], DRUM_KEYS["hat_open"])), key=lambda e: e.start)
    for a, b in zip(hats, hats[1:]):
        if a.pitch == DRUM_KEYS["hat_open"]:
            a.end = max(b.start, a.start + .03)
    return [e for e in ev if e.start < dur], {"groove": groove, "swing": swing, "fill_bar": fill_bar, "rules": RULES_VERSION}


def synth(comp: dict, dur: float, rng, role: str | None = None) -> tuple[list[NoteEvent], dict]:
    clk, ev = _Clock(comp, dur), []
    role = role or SYNTH_ROLES[rng.randint(len(SYNTH_ROLES))]
    vel = int(rng.randint(60, 105))
    scale, root = comp["scale"], comp["key_root"]
    center = int(rng.randint(60, 72))
    last = None
    for c in comp["chords"]:
        b0, bl = c["start_beat"], c["dur_beats"]
        v = _voicing(c, center, rng, n_notes=4)
        if role == "pad":
            for p in v:
                ev.append(_ev("synth", p, vel + rng.randint(-5, 5), clk.t(b0), clk.t(b0 + bl) + .05, rng, 4))
        elif role == "pluck":
            for off in (0.5, 1.5, 2.5, 3.5):
                if off < bl and rng.rand() < .8:
                    for p in v[:3]:
                        ev.append(_ev("synth", p, vel + rng.randint(-8, 8), clk.t(b0 + off), clk.t(b0 + off + .3), rng, 4))
        elif role == "arp":
            seq = v + [x + 12 for x in v]
            for i, o in enumerate(np.arange(0, bl, .25)):
                ev.append(_ev("synth", seq[i % len(seq)], vel + (8 if i % 4 == 0 else 0), clk.t(b0 + o), clk.t(b0 + o + .2), rng, 3))
        else:  # lead: stepwise walk over the scale, biased to chord tones
            pos = b0
            while pos < b0 + bl - 1e-6:
                ln = float(rng.choice([.5, 1.0, 1.0, 1.5, 2.0]))
                ln = min(ln, b0 + bl - pos)
                if rng.rand() < .2:
                    pos += ln
                    continue
                if last is None or rng.rand() < .3:
                    cand = [p for p in range(66, 88) if p % 12 in c["pcs"]]
                    last = int(cand[rng.randint(len(cand))])
                else:
                    deg = [i for i in range(60, 92) if (i - root) % 12 in scale]
                    idx = deg.index(min(deg, key=lambda x: abs(x - last)))
                    last = int(deg[int(np.clip(idx + rng.choice([-2, -1, 1, 2]), 0, len(deg) - 1))])
                    last = int(np.clip(last, 62, 90))
                ev.append(_ev("synth", last, vel + rng.randint(-8, 8), clk.t(pos), clk.t(pos + ln * .95), rng, 6))
                pos += ln
    return [e for e in ev if e.start < dur], {"role": role, "rules": RULES_VERSION}
