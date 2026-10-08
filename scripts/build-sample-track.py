"""Compose and render the original 13-instrument demo song (FluidSynth + GeneralUser GS).

Each instrument is rendered alone (ground-truth stem) and summed into the mix, so the homepage demo
has no third-party rights attached. Output: data/sample/{mix.wav,stems/*.wav}.
"""
import subprocess
from pathlib import Path
import numpy as np
import pretty_midi
import soundfile as sf
from music_analyzer.common import project_root

RATE = 44100
BPM = 96
BEAT = 60 / BPM
BAR = 4 * BEAT
BARS = 16
SECONDS = BARS * BAR + 2.5  # room for the release tail
base = project_root() / 'data/pad-eval'
FLUID = base / 'tools/fluidsynth/fluidsynth-v2.6.1-win10-x64-cpp11/bin/fluidsynth.exe'
FONT = base / 'tools/GeneralUser-GS.sf2'
import os
out = project_root() / os.environ.get('SAMPLE_DIR', 'data/sample')
VARIANT = os.environ.get('SAMPLE_VARIANT', 'a')
# progression Am F C G, pitch class + chord quality per bar
ROOTS = [9, 5, 0, 7]
TRIADS = [(0, 3, 7), (0, 4, 7), (0, 4, 7), (0, 4, 7)]
MELODY = [[69, 72, 76, 72], [72, 69, 77, 72], [72, 76, 79, 76], [71, 74, 79, 74]]  # per bar, one note per beat


def bars_of(start, end=BARS):
    return range(start, end)


def chord(bar, octave):
    root = ROOTS[bar % 4] + 12 * (octave + 1)
    return [root + i for i in TRIADS[bar % 4]]


def new(program, drum=False):
    return pretty_midi.Instrument(program=program, is_drum=drum)


def add(inst, pitch, start, length, velocity=80):
    inst.notes.append(pretty_midi.Note(int(velocity), int(pitch), float(start), float(start + length)))


def piano():
    i = new(0)
    for b in bars_of(0):
        for beat in range(4):
            for p in chord(b, 4): add(i, p, b * BAR + beat * BEAT, BEAT * .9, 66 if beat else 74)
    return [i]


def bass():
    i = new(33)
    for b in bars_of(4):
        r = ROOTS[b % 4] + 36
        for k, p in enumerate([r, r, r + 7, r, r, r + 12, r + 7, r]): add(i, p, b * BAR + k * BEAT / 2, BEAT / 2 * .85, 92)
    return [i]


def drums():
    i = new(0, True)
    for b in bars_of(2):
        for k in range(8): add(i, 42, b * BAR + k * BEAT / 2, .1, 60 if k % 2 else 78)
        for beat in (0, 2): add(i, 36, b * BAR + beat * BEAT, .2, 112)
        add(i, 36, b * BAR + 1.5 * BEAT, .2, 96)
        for beat in (1, 3): add(i, 38, b * BAR + beat * BEAT, .2, 104)
        if b % 4 == 3: [add(i, 38, b * BAR + 3 * BEAT + k * BEAT / 4, .1, 70 + k * 10) for k in range(4)]
        if b in (8, 12): add(i, 49, b * BAR, 1.5, 100)
    return [i]


def percussion():
    d = new(0, True); t = new(47)
    for b in bars_of(8):
        for beat in range(4): add(d, 54, b * BAR + beat * BEAT + BEAT / 2, .1, 82)
        if b % 2 == 0: add(d, 56, b * BAR, .3, 90)
        if b % 4 == 0: add(t, 33 + ROOTS[b % 4], b * BAR, 1.8, 105)
    return [d, t]


def strings():
    if VARIANT == 'b':
        v, c = new(40), new(42)
        for b in bars_of(4):
            ch = chord(b, 4)
            add(v, ch[2] + 12, b * BAR, BAR * .98, 92); add(v, ch[1] + 12, b * BAR, BAR * .98, 84)
            add(c, ch[0] - 12, b * BAR, BAR * .98, 96)
        return [v, c]
    i = new(48)
    for b in bars_of(4):
        for p in chord(b, 4): add(i, p, b * BAR, BAR * .98, 70)
    return [i]


def brass():
    i = new(61)
    for b in bars_of(8):
        for off, ln in ((0, BEAT * .6), (2.5 * BEAT, BEAT * .5)):
            for p in chord(b, 4): add(i, p, b * BAR + off, ln, 104)
    return [i]


def acoustic():
    i = new(24 if VARIANT == 'b' else 25)
    for b in bars_of(4):
        c = chord(b, 3)
        for k, p in enumerate([c[0], c[1], c[2], c[1], c[2], c[1], c[0] + 12, c[1]]): add(i, p, b * BAR + k * BEAT / 2, BEAT * .7, 76)
    return [i]


def electric():
    i = new(29)
    for b in bars_of(8):
        r = ROOTS[b % 4] + 48
        for half in range(2):
            for p in (r, r + 7, r + 12): add(i, p, b * BAR + half * 2 * BEAT, BEAT * 1.8, 98)
    return [i]


def synth():
    i = new(80)
    for b in bars_of(2):
        c = chord(b, 5)
        for k, p in enumerate([c[0], c[1], c[2], c[1]] * 2): add(i, p, b * BAR + k * BEAT / 2, BEAT * .4, 72)
    return [i]


def choir():
    i = new(52)
    for b in bars_of(8):
        for p in chord(b, 4): add(i, p, b * BAR, BAR * .97, 72)
    return [i]


def lead():
    i = new(53)
    for b in bars_of(4):
        for k, p in enumerate(MELODY[b % 4]): add(i, p + 12 * (b >= 8), b * BAR + k * BEAT, BEAT * .92, 96)
    return [i]


STEMS = {'lead': (lead, .9), 'choir': (choir, .7), 'piano': (piano, .8), 'synth': (synth, .55), 'strings': (strings, 1.0 if VARIANT == 'b' else .65),
         'brass': (brass, .7), 'acoustic_guitar': (acoustic, 1.0 if VARIANT == 'b' else .75), 'guitar': (electric, .6), 'bass': (bass, .85),
         'drums': (drums, .9), 'percussion': (percussion, .6)}


def render(name, builder):
    midi = pretty_midi.PrettyMIDI(initial_tempo=BPM)
    for inst in builder(): midi.instruments.append(inst)
    mid = out / 'stems' / (name + '.mid'); wav = mid.with_suffix('.wav'); mid.parent.mkdir(parents=True, exist_ok=True)
    midi.write(str(mid))
    subprocess.run([str(FLUID), '-ni', '-q', '-F', str(wav), '-r', str(RATE), str(FONT), str(mid)], check=True, capture_output=True)
    mid.unlink()
    audio, rate = sf.read(wav, dtype='float32', always_2d=True)
    n = int(SECONDS * RATE)
    return np.pad(audio, ((0, max(0, n - len(audio))), (0, 0)))[:n]


if __name__ == '__main__':
    stems = {k: render(k, f) * g for k, (f, g) in STEMS.items()}
    mix = sum(stems.values()); peak = float(np.abs(mix).max()); scale = .8 / peak
    for k, a in stems.items(): sf.write(out / 'stems' / (k + '.wav'), a * scale, RATE, subtype='FLOAT')
    sf.write(out / 'mix.wav', mix * scale, RATE, subtype='FLOAT')
    print('seconds', round(SECONDS, 1), 'peak before', round(peak, 3), 'scale', round(scale, 3))
