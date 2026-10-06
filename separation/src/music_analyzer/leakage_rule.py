"""Experimental gentle energy gate. No instrument identity classification."""
import numpy as np
import soundfile as sf
from pathlib import Path
from .common import write_json, sha256_file
RATE = 44100

def envelope(raw, mix, on, off, hold):
    """100 ms energy evidence, hysteresis, 50 ms attack and 300 ms release."""
    hop = RATE // 10
    levels, states = [], []
    active, remaining = False, 0
    for start in range(0, len(raw), hop):
        a, b = raw[start:start+hop], mix[start:start+hop]
        energy = float(np.sqrt(np.mean(a.astype(np.float64)**2)))
        reference = float(np.sqrt(np.mean(b.astype(np.float64)**2)))
        relative = 20*np.log10((energy+1e-12)/(reference+1e-12))
        if energy < 1e-5:
            active = False
        elif relative >= on:
            active, remaining = True, hold
        elif active and relative < off:
            remaining -= .1
            if remaining <= 0:
                active = False
        levels.append(relative)
        states.append(float(active))
    gain = np.empty(len(raw), dtype=np.float64)
    previous = 0.
    for index, state in enumerate(states):
        start, end = index*hop, min(len(raw), (index+1)*hop)
        tau = .05 if state > previous else .3
        decay = np.exp(-np.arange(1, end-start+1)/(RATE*tau))
        gain[start:end] = state + (previous-state)*decay
        previous = gain[end-1]
    return gain[:, None], levels


def apply(root, row):
    """Apply the approved gentle comparison to new results; retain pre-gate files."""
    if row.get('leakage_rule', {}).get('version') == 'energy-gentle-synth-preserved-v2':
        return row
    root = Path(root).resolve()
    folder = root/'web'/row['id']
    def load(path):
        path = (root/path).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Invalid leakage input path')
        audio, rate = sf.read(path, dtype='float32', always_2d=True)
        if rate != RATE or audio.shape[1] != 2 or not np.isfinite(audio).all():
            raise ValueError('Invalid leakage input audio')
        return audio
    source = {t['family']:t for t in row['tracks']}
    mix = load(row['instrumental'])
    other = load(source['other']['path']).astype(np.float64)
    if other.shape != mix.shape:
        raise ValueError('Leakage timeline mismatch')
    revised, errors = {}, {}
    for family in ('brass', 'strings'):
        track = source[family]
        raw = row.get(family+'_recovery', {}).get('original_tracks', {}).get(family, track)
        before, current = load(raw['path']), load(track['path'])
        if before.shape != mix.shape or current.shape != mix.shape:
            raise ValueError('Leakage timeline mismatch')
        gain, _ = envelope(before, mix, -38, -44, .1 if family == 'brass' else .3)
        audio = (current*gain).astype(np.float32)
        removed = current.astype(np.float64)-audio
        # Return every removed sample to other; reference accompaniment is immutable.
        other += removed
        revised[family] = audio
        errors[family] = float(np.mean(gain > .5))
    revised['other'] = other.astype(np.float32)
    reconstructed = revised['other'].astype(np.float64)
    for family in ('piano','synth','strings','brass','acoustic_guitar','guitar','bass','drums'):
        reconstructed += revised[family] if family in revised else load(source[family]['path'])
    error = float(np.max(np.abs(reconstructed-mix)))
    if error > 2e-6:
        raise ValueError('Leakage instrumental reconstruction failed')
    write_json(folder/'record-before-leakage-rule-v2.json', row)
    tracks = []
    for track in row['tracks']:
        family = track['family']
        if family in revised:
            audio = revised[family]
            target = folder/(family+'-leakage-gentle-v2.wav')
            partial = target.with_suffix('.partial.wav')
            sf.write(partial, audio, RATE, subtype='FLOAT')
            partial.replace(target)
            track = {k:v for k,v in track.items() if k not in ('silent','signal_rms')}
            track.update(path=str(target.relative_to(root)),sha256=sha256_file(target),
                         peak=float(np.abs(audio).max()),derivation='experimental_gentle_leakage_gate')
        tracks.append(track)
    return {**row,'tracks':tracks,'leakage_rule':{'version':'energy-gentle-synth-preserved-v2',
            'on_relative_db':-38,'off_relative_db':-44,'active_fraction':errors,
            'instrumental_max_abs_error':error,'experimental':True,'synth_policy':'preserve_post_recovery'}}

