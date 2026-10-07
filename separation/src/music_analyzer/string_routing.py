"""Return bowed-string material scattered into synth, unclassified and backing tracks.

Evidence comes from the instrument model run on the original mix, where strings are
still intact; the later residual pass often hears partial violins as synth.
"""
import numpy as np
from scipy import signal

# Exponent per source: higher is more conservative. Tuned on 32 reference cases (v13 study).
STRENGTH = {'synth': 1, 'other': 3, 'backing': 2}
SOURCES = tuple(STRENGTH)


def transfer(mixture, tracks, evidence):
    """Return (revised source tracks, audio moved into strings). Sum is preserved exactly."""
    arrays = [np.asarray(a, dtype=np.float32) for a in (mixture, *(tracks[s] for s in SOURCES),
              *(evidence[f] for f in ('synth', 'bowed_strings', 'brass')))]
    if len(arrays[0]) < 2048 or any(a.ndim != 2 or a.shape[1] != 2 or a.shape != arrays[0].shape or not np.isfinite(a).all() for a in arrays):
        raise ValueError('String routing timeline mismatch')
    n = len(arrays[0])
    taken = {s: np.zeros_like(arrays[0]) for s in SOURCES}
    for start in range(0, n, 512*2048):
        end = min(n, start+512*2048); left = max(0, start-2048); right = min(n, end+2048)
        X, *rest = [signal.stft(a[left:right].T, fs=44100, nperseg=2048, noverlap=1536)[2] for a in arrays]
        S = dict(zip(SOURCES, rest[:3])); synth, strings, brass = rest[3:]
        power = np.abs(synth)**2+np.abs(strings)**2+np.abs(brass)**2+np.abs(X-synth-strings-brass)**2
        def share(c): return np.divide(np.abs(c)**2, power, out=np.zeros(power.shape), where=power > 0)
        w_strings = share(strings)
        for s in SOURCES:
            rival = share(synth) if s == 'synth' else share(brass)
            confidence = np.clip(w_strings-rival, 0, 1)**STRENGTH[s]
            d = np.abs(S[s])*np.abs(strings)
            coherence = np.divide(np.real(S[s]*strings.conj()), d, out=np.zeros(d.shape), where=d > 0)
            confidence *= np.clip(coherence, 0, 1)**2
            audio = signal.istft(S[s]*confidence, fs=44100, nperseg=2048, noverlap=1536)[1].T
            taken[s][start:end] = audio[start-left:end-left]
    revised = {s: arrays[1+i]-taken[s] for i, s in enumerate(SOURCES)}
    return revised, sum(taken.values()), taken['backing']


def apply(root, row, evidence, job_id, version='context-string-routing-v1'):
    """Move string material into strings; backing material moved also joins the instrumental."""
    from pathlib import Path
    import soundfile as sf
    from .common import sha256_file
    root = Path(root); source = {t['family']: t for t in row['tracks']}
    if row.get('string_routing'):
        if row['string_routing']['version'] == version: return row
        raise ValueError('Different string routing version requires the original tracks')
    def read(path):
        audio, rate = sf.read(path, dtype='float32', always_2d=True)
        if rate != 44100: raise ValueError('String routing rate mismatch')
        return audio
    tracks = {f: read(root/source[f]['path']) for f in (*SOURCES, 'strings')}
    instrumental = read(root/row['instrumental'])
    revised, moved, from_backing = transfer(read(root/row['original']), tracks, {f: read(Path(p)) for f, p in evidence.items()})
    revised['strings'] = tracks['strings']+moved
    after_instrumental = instrumental+from_backing
    error = float(np.max(np.abs(sum(tracks[f].astype(float) for f in tracks)-sum(revised[f].astype(float) for f in revised))))
    if error > 2e-6: raise ValueError('String routing partition reconstruction failed')
    folder = root/'web'/row['id']; folder.mkdir(parents=True, exist_ok=True)
    def write(name, audio):
        path = folder/name; temporary = path.with_suffix('.partial.wav')
        sf.write(temporary, audio, 44100, subtype='FLOAT'); temporary.replace(path)
        return path
    output = []
    for track in row['tracks']:
        family = track['family']
        if family in revised:
            path = write(family+'-string-routed-v1.wav', revised[family]); peak = float(np.abs(revised[family]).max())
            track = {k: v for k, v in track.items() if k not in ('silent', 'signal_rms')}
            track.update(path=str(path.relative_to(root)), sha256=sha256_file(path), peak=peak, over_full_scale=peak > 1,
                         derivation='context_string_routing', sample_rate=44100, channels=2, num_frames=len(revised[family]), subtype='FLOAT')
        output.append(track)
    path = write('instrumental-string-routed-v1.wav', after_instrumental)
    return {**row, 'tracks': output, 'instrumental': str(path.relative_to(root)), 'string_routing': {
        'version': version, 'context_job_id': job_id, 'partition_max_abs_error': error,
        'moved_rms': float(np.sqrt(np.mean(moved.astype(float)**2))),
        'from_backing_rms': float(np.sqrt(np.mean(from_backing.astype(float)**2))),
        'original_tracks': {f: source[f] for f in (*SOURCES, 'strings')}, 'original_instrumental': row['instrumental']}}
