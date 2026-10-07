"""Build the synth-pad evaluation set: 32 distinct pad timbres, hard negatives, quiet pads, no-pad controls.

Pad timbres 0-7 are GM Pad 1-8 rendered with GeneralUser GS; 8-31 are parametric numpy pads.
Even timbres are the dev split, odd timbres the held-out test split (split by timbre, never by clip).
Policy: synth strings (GM 50/51) count as synth, because that matches the model's allocation (8.0 dB vs 0.1 dB measured).
"""
import subprocess
import sys
from pathlib import Path
import numpy as np
import pretty_midi
import soundfile as sf
from scipy.signal import butter, sosfilt, fftconvolve
from music_analyzer.common import project_root, write_json
from music_analyzer.ground_truth import prepare

RATE = 44100
SECONDS = 15
MASTER = .5
base = project_root() / 'data/pad-eval'
FLUID = base / 'tools/fluidsynth/fluidsynth-v2.6.1-win10-x64-cpp11/bin/fluidsynth.exe'
FONT = base / 'tools/GeneralUser-GS.sf2'
STRING_PROGRAMS = [40, 41, 42, 44, 48, 49, 50, 51]  # violin viola cello tremolo ensembles synth-strings (policy: strings)
CHORDS = [(0, 4, 7), (0, 3, 7), (0, 4, 7, 11), (0, 3, 7, 10), (0, 2, 7), (0, 4, 7, 14), (0, 5, 7)]


def progression(rng):
    root = int(rng.integers(0, 12)); mode = rng.choice([0, 1])
    degrees = [0, 5, 3, 4] if mode == 0 else [0, 3, 5, 4]
    return [(root + (0, 2, 4, 5, 7, 9, 11)[d % 7]) % 12 for d in degrees], [CHORDS[int(rng.integers(0, len(CHORDS)))] for _ in degrees]


def voicing(root, chord, octave, wide):
    notes = [12 * octave + root + i for i in chord]
    if wide:
        notes = [n + (12 if k % 2 else 0) for k, n in enumerate(notes)]
    return notes


def pad_midi(rng, kind, program):
    roots, chords = progression(rng); m = pretty_midi.PrettyMIDI(); inst = pretty_midi.Instrument(program=program)
    octave = {'low': 3, 'high': 6}.get(kind, 4); step = {'fast': 1.5, 'slow': 7.5}.get(kind, 3.75)
    t = 0.; k = 0
    while t < SECONDS:
        r, c = roots[k % 4], chords[k % 4]
        notes = voicing(r, c[:1] if kind == 'single' else c, octave, kind == 'wide')
        for n in notes:
            inst.notes.append(pretty_midi.Note(int(rng.integers(70, 100)), int(np.clip(n, 28, 100)), t, min(t + step + .5, SECONDS)))
        t += step; k += 1
    m.instruments.append(inst); return m


def line_midi(rng, program, octave=4):
    roots, chords = progression(rng); m = pretty_midi.PrettyMIDI(); inst = pretty_midi.Instrument(program=program)
    t = 0.; k = 0
    while t < SECONDS:
        notes = voicing(roots[k % 4], chords[k % 4], octave, bool(rng.integers(0, 2)))
        for j, n in enumerate(notes):
            inst.notes.append(pretty_midi.Note(int(rng.integers(60, 95)), n, t + .08 * j, min(t + 3.4, SECONDS)))
        t += 3.75; k += 1
    m.instruments.append(inst); return m


def comp_midi(rng, program, octave, rhythm):
    roots, chords = progression(rng); m = pretty_midi.PrettyMIDI(); inst = pretty_midi.Instrument(program=program)
    t = 0.; k = 0; beat = 60 / 100
    while t < SECONDS:
        for n in voicing(roots[(k // rhythm) % 4], chords[(k // rhythm) % 4], octave, False):
            inst.notes.append(pretty_midi.Note(int(rng.integers(60, 90)), n, t, min(t + beat * .9, SECONDS)))
        t += beat * 2 / rhythm; k += 1
    m.instruments.append(inst); return m


def bass_midi(rng):
    roots, _ = progression(rng); m = pretty_midi.PrettyMIDI(); inst = pretty_midi.Instrument(program=33)
    t = 0.; k = 0
    while t < SECONDS:
        inst.notes.append(pretty_midi.Note(95, 36 + roots[(k // 4) % 4], t, min(t + .55, SECONDS))); t += .6; k += 1
    m.instruments.append(inst); return m


def drum_midi():
    m = pretty_midi.PrettyMIDI(); inst = pretty_midi.Instrument(program=0, is_drum=True); t = 0.; k = 0
    while t < SECONDS:
        inst.notes.append(pretty_midi.Note(100, 42, t, t + .1))
        if k % 4 == 0: inst.notes.append(pretty_midi.Note(110, 36, t, t + .1))
        if k % 4 == 2: inst.notes.append(pretty_midi.Note(105, 38, t, t + .1))
        t += .3; k += 1
    m.instruments.append(inst); return m


def render(midi, path):
    path.parent.mkdir(parents=True, exist_ok=True); mid = path.with_suffix('.mid'); midi.write(str(mid))
    subprocess.run([str(FLUID), '-ni', '-q', '-F', str(path), '-r', str(RATE), str(FONT), str(mid)], check=True, capture_output=True)
    audio, rate = sf.read(path, dtype='float32', always_2d=True)
    n = SECONDS * RATE; audio = np.pad(audio, ((0, max(0, n - len(audio))), (0, 0)))[:n]
    sf.write(path, audio, RATE, subtype='FLOAT'); mid.unlink(); return audio


def parametric_pad(rng, midi, seed):
    """Distinct synthesized pad: wave, unison, detune, filter, envelope, chorus, reverb all drawn per timbre."""
    p = np.random.default_rng(10_000 + seed)
    wave = p.choice(['saw', 'square', 'tri', 'stack']); unison = int(p.choice([1, 3, 5, 7])); detune = float(p.uniform(4, 30))
    cutoff = float(p.uniform(500, 6000)); attack = float(p.uniform(.1, 1.6)); release = float(p.uniform(.4, 2.5))
    lfo = float(p.uniform(.05, .6)); reverb = float(p.uniform(.8, 3.5)); width = float(p.uniform(.2, 1.))
    n = SECONDS * RATE; out = np.zeros((n, 2), dtype=np.float64); time = np.arange(n) / RATE
    def osc(freq, phase):
        ph = (freq * time + phase) % 1.
        if wave == 'saw': return 2 * ph - 1
        if wave == 'square': return np.sign(ph - .5)
        if wave == 'tri': return 4 * np.abs(ph - .5) - 1
        return sum(np.sin(2 * np.pi * freq * h * time + phase) / h for h in (1, 2, 3, 4, 5)) / 2
    for note in midi.instruments[0].notes:
        a, b = int(note.start * RATE), int(min(note.end + release, SECONDS) * RATE)
        if b - a < 100: continue
        f0 = 440 * 2 ** ((note.pitch - 69) / 12); tt = np.arange(b - a) / RATE
        left = right = 0.
        for u in range(unison):
            cents = 0 if unison == 1 else detune * (2 * u / (unison - 1) - 1)
            f = f0 * 2 ** (cents / 1200); sub = np.arange(a, b) / RATE
            ph = (f * sub + p.uniform()) % 1.
            if wave == 'saw': w = 2 * ph - 1
            elif wave == 'square': w = np.sign(ph - .5)
            elif wave == 'tri': w = 4 * np.abs(ph - .5) - 1
            else: w = sum(np.sin(2 * np.pi * f * h * sub + ph[0]) / h for h in (1, 2, 3, 4, 5)) / 2
            pan = .5 + (u / max(unison - 1, 1) - .5) * width
            left = left + w * (1 - pan); right = right + w * pan
        env = np.minimum(tt / attack, 1.) * np.where(tt > note.end - note.start, np.exp(-(tt - (note.end - note.start)) * 5 / release), 1.)
        mod = .6 + .4 * np.sin(2 * np.pi * lfo * tt + p.uniform(0, 6))
        out[a:b, 0] += left * env * mod * note.velocity / 127; out[a:b, 1] += right * env * mod * note.velocity / 127
    sos = butter(2, cutoff, fs=RATE, output='sos'); out = sosfilt(sos, out, axis=0)
    ir_len = int(reverb * RATE); ir = p.standard_normal((ir_len, 2)) * np.exp(-np.arange(ir_len) / (reverb * RATE / 4))[:, None]
    wet = np.stack([fftconvolve(out[:, c], ir[:, c])[:n] for c in range(2)], axis=1)
    out = out + .25 * wet / max(np.abs(wet).max(), 1e-9) * np.abs(out).max()
    return out.astype(np.float32)


def level(audio, dbfs):
    rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2)); return audio * (10 ** (dbfs / 20) / max(rms, 1e-9))


def main():
    stems_dir = base / 'stems'; cases_dir = base / 'cases'; manifest = []
    pad_stems = {}
    for i in range(32):
        rng = np.random.default_rng(100 + i); kind = ['normal', 'wide', 'low', 'high', 'slow', 'fast', 'single', 'normal'][i % 8]
        path = stems_dir / f'pad{i:02d}.wav'
        if not path.exists():
            if i < 8: audio = render(pad_midi(rng, kind, 88 + i), path)
            else:
                audio = parametric_pad(rng, pad_midi(rng, kind, 88), i)
            sf.write(path, level(audio, -18).astype(np.float32), RATE, subtype='FLOAT')
        pad_stems[i] = path
    common = {}
    def stem(name, builder):
        path = stems_dir / (name + '.wav')
        if not path.exists():
            audio = builder(path); sf.write(path, level(audio, common_level.get(name.split('-')[0], -20)).astype(np.float32), RATE, subtype='FLOAT')
        return path
    common_level = {'strings': -18, 'piano': -20, 'bass': -20, 'drums': -20, 'guitar': -22, 'brass': -22}
    for i in range(32):
        rng = np.random.default_rng(500 + i)
        stem(f'strings-{i:02d}', lambda p: render(line_midi(rng, STRING_PROGRAMS[i % len(STRING_PROGRAMS)]), p))
        stem(f'piano-{i:02d}', lambda p: render(comp_midi(rng, 0, 4, 2), p))
        stem(f'bass-{i:02d}', lambda p: render(bass_midi(rng), p))
        stem(f'drums-{i:02d}', lambda p: render(drum_midi(), p))
        stem(f'guitar-{i:02d}', lambda p: render(line_midi(rng, 29, 4), p))
        stem(f'brass-{i:02d}', lambda p: render(line_midi(rng, 61, 4), p))
    def rel(path, folder): return Path(*(['..'] * len(folder.relative_to(base).parts)), path.relative_to(base)).as_posix()
    def make(name, i, pad_gain, with_pad, roles, split, kind):
        folder = cases_dir / name; folder.mkdir(parents=True, exist_ok=True)
        # Measured policy: the model files synth strings under synth and that allocation scored 8.0 dB vs 0.1 dB.
        sources = {('synth_strings' if STRING_PROGRAMS[i % len(STRING_PROGRAMS)] in (50, 51) else 'strings'): [rel(stems_dir / f'strings-{i:02d}.wav', folder)]}
        for role in roles: sources[role] = [rel(stems_dir / f'{role}-{i:02d}.wav', folder)]
        sources['synth'] = [rel(pad_stems[i], folder)]
        # MASTER keeps every mix below full scale; a pad-free control keeps a zero-gain pad reference.
        gains = {family: MASTER for family in sources}; gains['synth'] = MASTER * (pad_gain if with_pad else 0.)
        write_json(folder / 'case.json', {'name': name, 'start_sec': 0, 'duration_sec': SECONDS, 'reference_sources': sources,
            'reference_gains': gains, 'split': split, 'kind': kind, 'pad_timbre': i, 'pad_gm_program': 88 + i if i < 8 else None,
            'scope': 'Synthetic pad evaluation mix; FluidSynth/GeneralUser GS and numpy pads; not a real-song benchmark.'})
        prepare(folder / 'case.json'); manifest.append({'case': name, 'split': split, 'kind': kind, 'pad_timbre': i})
    for i in range(32):
        split = 'dev' if i % 2 == 0 else 'test'
        roles = ['piano', 'bass', 'drums'] + (['guitar'] if i % 3 == 0 else []) + (['brass'] if i % 5 == 0 else [])
        make(f'pad{i:02d}-mix', i, 1., True, roles, split, 'pad_with_strings')
        if i % 2 == 0: make(f'pad{i:02d}-quiet', i, 10 ** (-12 / 20), True, roles, split, 'quiet_pad')
        if i < 16: make(f'pad{i:02d}-nopad', i, 0., False, roles, split, 'no_pad_control')
        if i < 8: make(f'pad{i:02d}-piano', i, 1., True, ['piano'], split, 'pad_piano_only')
    write_json(base / 'manifest.json', manifest); print('BUILT', len(manifest), 'cases', flush=True)


if __name__ == '__main__':
    main()
