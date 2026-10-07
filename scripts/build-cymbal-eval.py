"""License-clean piano + cymbal ground truth (FluidSynth + GeneralUser GS; GS License v2.0 permits commercial use).

Per case: piano.wav, cymbals.wav (ride/crash/open hi-hat), body.wav (kick/snare/closed hh/toms), mix.wav.
Output: data/commercial-eval/cymbal-gt/case_XX/ . 12 cases = 4 seeds x piano level 0/-6/-12 dB vs drums.
"""
import subprocess
import numpy as np, pretty_midi, soundfile as sf
from music_analyzer.common import project_root, write_json

RATE, SECONDS = 44100, 15
base = project_root() / "data/pad-eval"
FLUID = base / "tools/fluidsynth/fluidsynth-v2.6.1-win10-x64-cpp11/bin/fluidsynth.exe"
FONT = base / "tools/GeneralUser-GS.sf2"
out = project_root() / "data/commercial-eval/cymbal-gt"


def render(midi, path):
    path.parent.mkdir(parents=True, exist_ok=True); mid = path.with_suffix(".mid"); midi.write(str(mid))
    subprocess.run([str(FLUID), "-ni", "-q", "-F", str(path), "-r", str(RATE), str(FONT), str(mid)], check=True, capture_output=True)
    audio, _ = sf.read(path, dtype="float32", always_2d=True); n = SECONDS * RATE
    audio = np.pad(audio, ((0, max(0, n - len(audio))), (0, 0)))[:n]; mid.unlink(); path.unlink(); return audio


def piano(rng):
    m = pretty_midi.PrettyMIDI(); i = pretty_midi.Instrument(program=int(rng.choice([0, 1, 4]))); t = 0.
    root = int(rng.integers(48, 60)); chords = [(0, 4, 7), (5, 9, 12), (7, 11, 14), (0, 4, 7)]; k = 0
    while t < SECONDS:
        for n in chords[k % 4]:
            i.notes.append(pretty_midi.Note(int(rng.integers(70, 100)), root + n + (12 if rng.random() < .3 else 0), t, min(t + .55, SECONDS)))
        if rng.random() < .6:
            i.notes.append(pretty_midi.Note(int(rng.integers(75, 105)), root + 24 + int(rng.choice([0, 4, 7, 12])), t + .3, min(t + .8, SECONDS)))
        t += .6; k += 1
    m.instruments.append(i); return m


def drums(rng, cymbals):
    m = pretty_midi.PrettyMIDI(); i = pretty_midi.Instrument(program=0, is_drum=True); t = 0.; k = 0
    while t < SECONDS:
        if cymbals:
            if rng.random() < .85: i.notes.append(pretty_midi.Note(int(rng.integers(70, 100)), 51, t, t + .3))   # ride
            if k % 16 == 0: i.notes.append(pretty_midi.Note(110, int(rng.choice([49, 57])), t, t + 1.5))        # crash
            if k % 8 == 5: i.notes.append(pretty_midi.Note(95, 46, t, t + .4))                                  # open hi-hat
        else:
            i.notes.append(pretty_midi.Note(80, 42, t, t + .1))                                                 # closed hi-hat
            if k % 4 == 0: i.notes.append(pretty_midi.Note(112, 36, t, t + .2))
            if k % 4 == 2: i.notes.append(pretty_midi.Note(106, 38, t, t + .2))
            if k % 8 == 7: i.notes.append(pretty_midi.Note(95, int(rng.choice([45, 47, 50])), t, t + .3))      # toms
        t += .3; k += 1
    m.instruments.append(i); return m


cases = []
for seed in range(4):
    for ratio in (0, -6, -12):
        rng = np.random.default_rng(seed)
        p = render(piano(rng), out / "tmp_p.wav"); rng2 = np.random.default_rng(100 + seed)
        c = render(drums(rng2, True), out / "tmp_c.wav"); b = render(drums(np.random.default_rng(200 + seed), False), out / "tmp_b.wav")
        p = p * .6 * 10 ** (ratio / 20); c = c * .6; b = b * .6
        name = f"case_{seed}_{ratio:+d}"; folder = out / name; folder.mkdir(parents=True, exist_ok=True)
        for k, a in (("piano", p), ("cymbals", c), ("body", b), ("mix", p + c + b)):
            sf.write(folder / f"{k}.wav", a, RATE, subtype="FLOAT")
        cases.append({"case": name, "seed": seed, "piano_ratio_db": ratio})
write_json(out / "manifest.json", {"cases": cases, "license": "FluidSynth + GeneralUser GS License v2.0 (permissive, commercial use allowed); synthetic, no third-party recordings"})
print(len(cases), "cases")
