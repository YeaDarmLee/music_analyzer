"""Minimal SFZ -> zone list parser. SFZ is only an *input metadata format*; playback is our own sampler.

Supported opcodes: sample, key, lokey, hikey, pitch_keycenter, lovel, hivel, volume, pan, tune, transpose, offset,
loop_mode, loop_start, loop_end, seq_length, seq_position, lorand, hirand, group, off_by, pitch_keytrack,
ampeg_release, ampeg_attack, amp_veltrack (percent), global_volume (dB, added to volume), trigger (release regions are
skipped), default_path (<control>).
Opcodes that change *which* regions sound (keyswitches, CC/channel gates, crossfades, #include/#define) are CRITICAL:
with strict=True ingest is rejected, never silently ignored. All other unknown opcodes are counted and returned.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path, PurePosixPath

HEADERS = ("control", "global", "master", "group", "region", "curve", "effect", "midi", "sample")
CRITICAL_EXACT = {"sw_last", "sw_previous", "sw_lokey", "sw_hikey", "sw_default", "sw_down", "sw_up", "sw_label",
                  "lochan", "hichan", "lobend", "hibend", "lochanaft", "hichanaft", "lopolyaft", "hipolyaft",
                  "lobpm", "hibpm", "lorand_cc"}
CRITICAL_RE = re.compile(r"^(locc\d+|hicc\d+|xfin_.*|xfout_.*|on_locc\d+|on_hicc\d+)$")
NOTE_RE = re.compile(r"^([a-gA-G])([#bB]?)(-?\d+)$")
NOTE_BASE = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}


class SfzUnsupported(ValueError):
    pass


def note_to_midi(v: str) -> int:
    v = v.strip()
    m = NOTE_RE.match(v)
    if m:
        n, acc, octv = m.groups()
        return NOTE_BASE[n.lower()] + (1 if acc == "#" else -1 if acc in ("b", "B") else 0) + (int(octv) + 1) * 12
    return int(float(v))


def _opcodes(block: str) -> dict:
    out = {}
    pos = [(m.start(), m.end(), m.group(1)) for m in re.finditer(r"(?:(?<=\s)|^)([A-Za-z_][\w$]*)=", block)]
    for i, (s, e, k) in enumerate(pos):
        end = pos[i + 1][0] if i + 1 < len(pos) else len(block)
        out[k] = block[e:end].strip()
    return out


def parse_sfz(text: str, strict: bool = True, cc_state: dict | None = None) -> tuple[list[dict], Counter]:
    """-> (regions as flat opcode dicts with inheritance applied, counter of unsupported opcodes).

    cc_state={64: 127}: evaluate loccN/hiccN gates for a FIXED controller state (here: sustain pedal down). A region is kept iff
    every gated controller lies inside its [lo, hi] range; this is region selection, not ignoring. A gate on a controller that
    is not in cc_state stays CRITICAL. on_loccN/on_hiccN regions (CC-triggered note-ons) are dropped and counted."""
    if re.search(r"^\s*#(include|define)\b", text, flags=re.M):
        raise SfzUnsupported("#include/#define change region definitions and are not supported")
    text = re.sub(r"//[^\n]*", "", text)
    parts = re.split(r"<(\w+)>", text)
    levels = {"global": {}, "master": {}, "group": {}}
    control: dict = {}
    regions: list[dict] = []
    unsupported: Counter = Counter()
    for i in range(1, len(parts), 2):
        h, body = parts[i], parts[i + 1]
        ops = _opcodes(body)
        if h == "control":
            control.update(ops)
        elif h in levels:
            order = ["global", "master", "group"]
            for lv in order[order.index(h):]:
                levels[lv] = {}
            levels[h] = ops
        elif h == "region":
            r = {**levels["global"], **levels["master"], **levels["group"], **ops}
            r["_default_path"] = control.get("default_path", "")
            regions.append(r)
    cc_state = cc_state or {}
    if cc_state:
        kept = []
        for r in regions:
            if any(re.match(r"^on_(lo|hi)cc\d+$", k) for k in r):
                unsupported["dropped region: CC-triggered (on_loccN)"] += 1
                continue
            ok = True
            for k in list(r):
                m = re.match(r"^(lo|hi)cc(\d+)$", k)
                if m and int(m.group(2)) in cc_state:
                    n = int(m.group(2))
                    lo, hi = float(r.get(f"locc{n}", 0)), float(r.get(f"hicc{n}", 127))
                    ok &= lo <= cc_state[n] <= hi
                    r.pop(k)
            if ok:
                kept.append(r)
            else:
                unsupported[f"dropped region: outside cc_state {cc_state}"] += 1
        regions = kept
    known = {"sample", "key", "lokey", "hikey", "pitch_keycenter", "lovel", "hivel", "volume", "pan", "tune", "transpose",
             "offset", "loop_mode", "loop_start", "loop_end", "seq_length", "seq_position", "lorand", "hirand", "group",
             "off_by", "pitch_keytrack", "ampeg_release", "ampeg_attack", "trigger", "_default_path", "end", "loopmode",
             "amp_veltrack", "global_volume"}
    critical = set()
    for r in regions:
        for k in r:
            if k in known:
                continue
            if k in CRITICAL_EXACT or CRITICAL_RE.match(k):
                critical.add(k)
            else:
                unsupported[k] += 1
    if critical and strict:
        raise SfzUnsupported(f"critical opcodes present (would change which regions sound): {sorted(critical)}")
    for k in critical:
        unsupported[k + " (CRITICAL, regions kept)"] += 1
    return regions, unsupported


def regions_to_zones(regions: list[dict], sfz_dir: Path | str = ".") -> tuple[list[dict], Counter]:
    """Flat SFZ regions -> manifest zones. Sample paths are normalized to POSIX relative to `sfz_dir`'s root usage."""
    zones, notes = [], Counter()
    base = PurePosixPath(str(sfz_dir).replace("\\", "/"))
    for r in regions:
        if r.get("trigger", "attack") != "attack":
            notes["skipped trigger=" + r["trigger"]] += 1
            continue
        if "sample" not in r:
            notes["skipped region without sample"] += 1
            continue
        rel = PurePosixPath((r["_default_path"] + r["sample"]).replace("\\", "/"))
        parts = []
        for p in (base / rel).parts:
            if p == "..":
                if parts:
                    parts.pop()
            elif p != ".":
                parts.append(p)
        key = r.get("key")
        lo = note_to_midi(r.get("lokey", key if key is not None else "0"))
        hi = note_to_midi(r.get("hikey", key if key is not None else "127"))
        root = note_to_midi(r.get("pitch_keycenter", key if key is not None else str(lo)))
        z = {"sample": "/".join(parts), "root_key": root, "lo_key": lo, "hi_key": hi,
             "lo_vel": int(r.get("lovel", 0)), "hi_vel": int(r.get("hivel", 127)),
             "volume_db": float(r.get("volume", 0)) + float(r.get("global_volume", 0)), "pan": float(r.get("pan", 0)),
             "tune_cents": float(r.get("tune", 0)) + 100.0 * float(r.get("transpose", 0)),
             "offset": int(float(r.get("offset", 0))), "keytrack": int(float(r.get("pitch_keytrack", 100))) != 0}
        if "amp_veltrack" in r:
            z["amp_veltrack"] = float(r["amp_veltrack"])  # percent; see SampleInstrument._note
        mode = r.get("loop_mode", r.get("loopmode", "no_loop"))
        z["one_shot"] = mode == "one_shot"
        if mode in ("loop_continuous", "loop_sustain") and "loop_start" in r and "loop_end" in r:
            z["loop"] = [int(float(r["loop_start"])), int(float(r["loop_end"]))]
        if "seq_length" in r:
            z["seq"] = [int(r.get("seq_position", 1)), int(r["seq_length"])]
        if "lorand" in r or "hirand" in r:
            z["rand"] = [float(r.get("lorand", 0)), float(r.get("hirand", 1))]
        if "ampeg_release" in r:
            z["release_s"] = float(r["ampeg_release"])
        if "group" in r or "off_by" in r:
            z["group"], z["off_by"] = r.get("group"), r.get("off_by")
        zones.append(z)
    return zones, notes
