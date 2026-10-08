"""Blind A/B listening package: basic_6 (baseline) vs commercial_6 on real songs from song/.

usage: make-listening-package.py [song-substring ...]     (default: SONGS below)
Output (all under data/listening/, git-ignored because the audio is copyrighted):
  raw/<song>/<preset>/<family>.wav     separated stems, untouched
  blind/<song>/<family>_A.wav|_B.wav   RMS-matched, A/B order randomised per (song, family) with a fixed seed
  blind/<song>/mix.wav                 the excerpt
  answer_key.json                      A/B -> preset mapping and applied gains  (do NOT open before scoring)
  score_sheet.csv                      one row per (song, family) to fill in
"""
import os as _os; _os.environ.setdefault("MUSIC_KEEP_INTERMEDIATES", "1")  # we read the stems of the finished job
import csv, json, random, sys, time
from pathlib import Path
import numpy as np, soundfile as sf
from music_analyzer.common import project_root, read_json, write_json
from music_analyzer.legal import RIGHTS_CONFIRMATION_VERSION
from music_analyzer.registry import paths
from music_analyzer.web_server import WebLibrary

SONGS = ["아이유(IU) - Blueming", "스파이에어(SPYAIR) - Orange", "imase - Fiction", "너의 이름은 OST - Sparkle", "MyGO!!!!!-壱雫空", "QWER - 고민중독"]
PRESETS = {"basic_6": ("melband_roformer_kj", "bs_roformer_6s"), "commercial_6": ("melband_roformer_kj", "bs_roformer_core4")}
FAMILIES = ["vocals", "piano", "guitar", "bass", "drums", "other"]
SECONDS = 40; RATE = 44100
base = project_root(); out = base / "data/listening"; (out / "raw").mkdir(parents=True, exist_ok=True)

def excerpt(path):
    """Loudest SECONDS-window inside 20-80% of the song (skips intros/outros)."""
    audio, rate = sf.read(path, dtype="float32", always_2d=True); assert rate == RATE, rate
    n = SECONDS * RATE; lo, hi = int(len(audio) * .2), int(len(audio) * .8) - n
    starts = range(lo, max(lo + 1, hi), 5 * RATE)
    start = max(starts, key=lambda s: float(np.sqrt(np.mean(audio[s:s + n] ** 2))))
    return audio[start:start + n], start / RATE

def separate(song, clip):
    for preset, models in PRESETS.items():
        target = out / "raw" / song / preset
        if all((target / f"{f}.wav").exists() for f in FAMILIES):
            continue
        root = out / "libs" / song / preset
        for model_id in models:
            checkpoint, registration = paths(base / "data/separation", model_id)
            dest = root / "models" / model_id; dest.mkdir(parents=True, exist_ok=True)
            if not (dest / checkpoint.name).exists():
                _os.link(checkpoint, dest / checkpoint.name)
            write_json(dest / "registration.json", read_json(registration))
        library = WebLibrary(root)
        try:
            with clip.open("rb") as stream:
                public = library.create(clip.name, preset, stream, clip.stat().st_size, rights=RIGHTS_CONFIRMATION_VERSION)
            started = time.monotonic()
            while True:
                row = library.get(public["id"])
                if row["state"] in ("SUCCEEDED", "FAILED", "CANCELLED") or time.monotonic() - started > 1800:
                    break
                time.sleep(1)
            if row["state"] != "SUCCEEDED":
                raise RuntimeError(f"{song}/{preset}: {row.get('error', row['state'])}")
            target.mkdir(parents=True, exist_ok=True)
            for t in row["tracks"]:
                if t["family"] in FAMILIES:
                    sf.write(target / f"{t['family']}.wav", sf.read(library.track_path(row, t["family"]), dtype="float32", always_2d=True)[0], RATE, subtype="FLOAT")
            print(song, preset, "done in", round(time.monotonic() - started), "s", flush=True)
        finally:
            library.executor.shutdown(wait=True)
        import shutil; shutil.rmtree(root, ignore_errors=True)  # the stems are copied; the throw-away library is not needed

def package(song, rng, key, rows):
    blind = out / "blind" / song; blind.mkdir(parents=True, exist_ok=True)
    sf.write(blind / "mix.wav", sf.read(out / "raw" / song / "clip.wav", dtype="float32", always_2d=True)[0], RATE, subtype="PCM_16")
    for family in FAMILIES:
        stems = {p: sf.read(out / "raw" / song / p / f"{family}.wav", dtype="float32", always_2d=True)[0] for p in PRESETS}
        rms = {p: float(np.sqrt(np.mean(s.astype(np.float64) ** 2))) for p, s in stems.items()}
        if max(rms.values()) < 1e-4:
            continue  # nothing to hear in either system
        target = float(np.sqrt(np.prod([max(r, 1e-9) for r in rms.values()])))  # geometric mean keeps the pair's overall level
        gains = {p: target / max(rms[p], 1e-9) for p in PRESETS}
        peak = max(float(np.max(np.abs(stems[p]))) * gains[p] for p in PRESETS)
        guard = min(1.0, .98 / peak) if peak > 0 else 1.0  # same extra attenuation for both: never clip, never break the match
        order = list(PRESETS); rng.shuffle(order)
        for label, preset in zip("AB", order):
            sf.write(blind / f"{family}_{label}.wav", (stems[preset] * gains[preset] * guard).astype(np.float32), RATE, subtype="PCM_16")
        key[f"{song}/{family}"] = {"A": order[0], "B": order[1], "gain_db": {p: round(20 * np.log10(gains[p] * guard), 2) for p in PRESETS},
                                   "rms_db_before_match": {p: round(20 * np.log10(max(rms[p], 1e-9)), 1) for p in PRESETS}}
        rows.append([song, family, "", "", "", "", "", "", "", ""])

def main():
    wanted = sys.argv[1:] or SONGS
    mp3 = {p.stem: p for p in (base / "song").glob("*.mp3")}
    rng = random.Random(20261008); key = {}; rows = []; meta = {}
    for needle in wanted:
        name = next(k for k in mp3 if needle in k)
        song = f"s{len(meta) + 1:02d}"; folder = out / "raw" / song; folder.mkdir(parents=True, exist_ok=True)
        clip = folder / "clip.wav"
        if not clip.exists():
            audio, start = excerpt(mp3[name]); sf.write(clip, audio, RATE, subtype="PCM_16"); meta[song] = {"title": name, "excerpt_start_s": round(start, 1)}
        else:
            meta[song] = {"title": name, "excerpt_start_s": None}
        separate(song, clip)
        package(song, rng, key, rows)
    write_json(out / "answer_key.json", {"songs": meta, "pairs": key})
    with (out / "score_sheet.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["song", "family", "better(A/B/tie)", "kick/snare lost", "cymbal broken", "drum/level pumping", "cross-stem bleed", "sustain cut / unnatural dips", "other artifact", "note"])
        w.writerows(rows)
    print("PACKAGE DONE", len(rows), "pairs", flush=True)

main()
