"""VocalSet ingest (non-excerpt only), singer-disjoint split, and vocal stem rendering.

Layout-agnostic: singer id = (female|male)N found in any path component, or an f/m+digits filename prefix; category =
scales | arpeggios | long_tones | excerpts found in path components or filename tokens. Excerpts and anything that cannot be
classified are EXCLUDED and counted (never silently used). Publisher-provided singer split: NEEDS_RESEARCH, so a fixed
project rule is used and recorded in the index."""
from __future__ import annotations

import json
import re
import wave
from pathlib import Path

import numpy as np

from .util import read_wav

ALLOWED = ("scales", "arpeggios", "long_tones")
SINGER_RE = re.compile(r"(?<![a-z])(female|male)[_-]?(\d+)", re.I)
PREFIX_RE = re.compile(r"^(f|m)(\d+)[_-]", re.I)
SPLIT_RULE = "project_fixed_rule_v1: per gender, highest id -> test, second highest -> val, rest -> train"


def _singer(rel: Path) -> tuple[str, str] | None:
    for part in rel.parts:
        m = SINGER_RE.search(part)
        if m:
            return f"{m.group(1).lower()}{int(m.group(2))}", m.group(1).lower()
    m = PREFIX_RE.match(rel.name)
    if m:
        g = "female" if m.group(1).lower() == "f" else "male"
        return f"{g}{int(m.group(2))}", g
    return None


def _category(rel: Path) -> str | None:
    toks = [t for part in rel.parts for t in re.split(r"[^a-z]+", part.lower().replace("long_tones", "longtones")) if t]
    for t in toks:
        if t.startswith("excerpt"):
            return "excerpts"
    for t in toks:
        if t in ("scales", "scale"):
            return "scales"
        if t in ("arpeggios", "arpeggio"):
            return "arpeggios"
        if t in ("longtones", "longtone", "long"):
            return "long_tones"
    return None


def _duration(p: Path) -> tuple[float, int]:
    try:
        with wave.open(str(p), "rb") as w:
            return w.getnframes() / w.getframerate(), w.getframerate()
    except (wave.Error, EOFError):
        x, sr = read_wav(p)
        return x.shape[1] / sr, sr


def singer_split(singers: dict[str, str], override: dict | None = None) -> dict[str, str]:
    """singers: singer -> gender. Fixed, deterministic, singer-disjoint."""
    if override:
        return dict(override)
    out = {}
    for g in sorted(set(singers.values())):
        ids = sorted((s for s, gg in singers.items() if gg == g), key=lambda s: int(re.sub(r"\D", "", s)))
        if len(ids) < 3:
            raise ValueError(f"need >= 3 singers per gender for train/val/test, {g} has {len(ids)}")
        for s in ids:
            out[s] = "train"
        out[ids[-1]], out[ids[-2]] = "test", "val"
    return out


def build_vocal_index(root: str | Path, asset_id: str = "vocalset", split_override: dict | None = None) -> dict:
    root = Path(root)
    clips, excluded = [], {"excerpts": 0, "unclassified": 0, "no_singer": 0}
    singers: dict[str, str] = {}
    for p in sorted(root.rglob("*.wav")):
        rel = p.relative_to(root)
        cat, sg = _category(rel), _singer(rel)
        if cat == "excerpts":
            excluded["excerpts"] += 1
        elif sg is None:
            excluded["no_singer"] += 1
        elif cat not in ALLOWED:
            excluded["unclassified"] += 1
        else:
            dur, sr = _duration(p)
            singers[sg[0]] = sg[1]
            clips.append({"clip_id": rel.as_posix(), "singer": sg[0], "gender": sg[1], "category": cat,
                          "duration_s": round(dur, 4), "sr": sr})
    if not clips:
        raise ValueError("no usable (non-excerpt) VocalSet clips found")
    split = singer_split(singers, split_override)
    return {"asset_id": asset_id, "allowed_categories": list(ALLOWED), "excluded": excluded, "split_policy": SPLIT_RULE,
            "publisher_split": "NEEDS_RESEARCH", "singer_split": split, "clips": clips}


def clips_for_split(index: dict, split: str) -> list[dict]:
    return [c for c in index["clips"] if index["singer_split"][c["singer"]] == split]


def choose_vocal(index: dict, split: str, rng: np.random.RandomState, duration_s: float) -> dict:
    """Pick clip + placement. Spec-level (JSON-able) so the scene is reproducible without the audio."""
    pool = clips_for_split(index, split)
    if not pool:
        raise ValueError(f"no vocal clips for split {split}")
    c = pool[rng.randint(len(pool))]
    d = c["duration_s"]
    spec = {"clip_id": c["clip_id"], "singer": c["singer"], "category": c["category"], "asset_id": index["asset_id"]}
    if d >= duration_s:
        spec.update(crop_start_s=float(rng.uniform(0, d - duration_s)), place_start_s=0.0)
    else:
        spec.update(crop_start_s=0.0, place_start_s=float(rng.uniform(0, duration_s - d)))
    spec["silence"] = []
    if rng.rand() < .4:  # inserted silence block (breath/phrase gap)
        a = float(rng.uniform(0, duration_s * .7))
        spec["silence"].append([a, float(min(a + rng.uniform(.3, 1.5), duration_s))])
    spec["double"] = None if rng.rand() < .6 else {"delay_ms": float(rng.uniform(10, 28)), "gain_db": float(rng.uniform(-9, -4)),
                                                  "pan": float(rng.uniform(.3, .8))}
    return spec


def render_vocal(spec: dict, root: str | Path, duration_samples: int, sr: int) -> np.ndarray:
    x, _ = read_wav(Path(root) / spec["clip_id"], sr)
    m = x.mean(0)
    s0 = int(spec["crop_start_s"] * sr)
    seg = m[s0:s0 + duration_samples]
    out = np.zeros(duration_samples, np.float32)
    p0 = int(spec["place_start_s"] * sr)
    n = min(len(seg), duration_samples - p0)
    if n > 0:
        out[p0:p0 + n] = seg[:n]
    for a, b in spec["silence"]:
        out[int(a * sr):int(b * sr)] = 0.0
    st = np.stack([out, out])
    d = spec.get("double")
    if d:
        k = int(d["delay_ms"] * 1e-3 * sr)
        dbl = np.zeros_like(out)
        dbl[k:] = out[:-k] if k else out
        g = 10 ** (d["gain_db"] / 20)
        th = (d["pan"] + 1) * np.pi / 4
        st = st * np.float32(1.0)
        st[0] += g * dbl * np.cos(th) * np.sqrt(2)
        st[1] += g * dbl * np.sin(th) * np.sqrt(2)
    return st.astype(np.float32)


def save_index(index: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(index, indent=1), encoding="utf-8")
