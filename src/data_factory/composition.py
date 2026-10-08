"""Procedural composition: key, mode, tempo, functional chord progression. No external corpus.
RULES_VERSION is recorded in every scene; change it whenever the grammar changes."""
from __future__ import annotations

import numpy as np

from .util import hash_obj

RULES_VERSION = "comp_rules_v1"
SCALES = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10]}
# degree index (0 = I/i ... 6 = VII) -> next-degree probabilities
TRANSITIONS = {
    0: {3: .30, 4: .25, 5: .22, 1: .10, 2: .05, 0: .05, 6: .03},
    1: {4: .50, 6: .08, 3: .20, 0: .17, 5: .05},
    2: {5: .38, 3: .38, 1: .16, 4: .08},
    3: {4: .38, 0: .28, 1: .14, 5: .14, 6: .06},
    4: {0: .48, 5: .28, 3: .14, 2: .06, 6: .04},
    5: {3: .33, 1: .23, 4: .24, 0: .14, 2: .06},
    6: {0: .66, 2: .26, 5: .08},
}
START = {0: .62, 5: .20, 3: .10, 1: .05, 4: .03}
SECTIONS = {"intro": .35, "verse": .55, "chorus": .85, "breakdown": .3, "bridge": .6, "sparse": .2, "dense": 1.0}
QUALITY_BY_THIRD_FIFTH = {(4, 7): "maj", (3, 7): "min", (3, 6): "dim", (4, 8): "aug"}


def _pick(table: dict, rng) -> int:
    ks = sorted(table)
    p = np.array([table[k] for k in ks], dtype=np.float64)
    return int(ks[rng.choice(len(ks), p=p / p.sum())])


def chord_at(scale: list[int], degree: int, key_root: int, rng, allow_ext: bool = True) -> dict:
    tri = [scale[(degree + k) % 7] + 12 * ((degree + k) // 7) for k in (0, 2, 4)]
    third, fifth = tri[1] - tri[0], tri[2] - tri[0]
    quality = QUALITY_BY_THIRD_FIFTH.get((third, fifth), "maj")
    pcs = tri[:]
    ext = ""
    r = rng.rand()
    if allow_ext and r < 0.30:
        pcs.append(scale[(degree + 6) % 7] + 12 * ((degree + 6) // 7))
        ext = "7"
    elif allow_ext and r < 0.38 and quality in ("maj", "min"):
        pcs[1] = tri[0] + (2 if rng.rand() < .5 else 5)  # sus2 / sus4
        ext = "sus"
    return {"degree": degree, "root_pc": (key_root + tri[0]) % 12, "quality": quality, "ext": ext,
            "pcs": [int((key_root + x) % 12) for x in pcs]}


def compose(duration_s: float, rng: np.random.RandomState, bpm_range=(70, 150)) -> dict:
    bpm = int(rng.randint(bpm_range[0], bpm_range[1] + 1))
    key_root = int(rng.randint(12))
    mode = "major" if rng.rand() < 0.6 else "minor"
    scale = SCALES[mode]
    beats_per_bar = 4
    n_bars = max(int(np.ceil(duration_s * bpm / 60.0 / beats_per_bar)), 1)
    total_beats = n_bars * beats_per_bar
    section = sorted(SECTIONS)[rng.randint(len(SECTIONS))]
    chords, beat = [], 0.0
    deg = _pick(START, rng)
    while beat < total_beats:
        dur = float(rng.choice([4, 4, 4, 2, 8]))
        dur = min(dur, total_beats - beat)
        c = chord_at(scale, deg, key_root, rng)
        c.update(start_beat=beat, dur_beats=dur)
        chords.append(c)
        beat += dur
        deg = _pick(TRANSITIONS[deg], rng)
    degrees = tuple(c["degree"] for c in chords)
    durs = tuple(c["dur_beats"] for c in chords)
    family = hash_obj({"mode": mode, "key": key_root, "degrees": degrees, "durs": durs, "rules": RULES_VERSION})[:12]
    return {"rules_version": RULES_VERSION, "bpm": bpm, "key_root": key_root, "mode": mode, "scale": scale,
            "beats_per_bar": beats_per_bar, "n_bars": n_bars, "section_type": section, "density": SECTIONS[section],
            "chords": chords, "family_id": family}
