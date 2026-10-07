"""Return material to brass and electric guitar using original-mix context evidence.

The base model hears brass as guitar and clean electric guitar as unclassified; the
context model run on the untouched mix often knows better. Only bins where the target's
context share beats the source family's own share, and phases agree, are moved.
"""
import numpy as np
from scipy import signal

CONTEXT = {'synth': 'synth', 'strings': 'bowed_strings', 'brass': 'brass', 'guitar': 'electric-guitar',
           'acoustic_guitar': 'acoustic-guitar', 'percussion': 'percussion', 'timpani': 'timpani'}
# (target, {source: exponent}); higher exponent is more conservative. Tuned on 32 reference cases (v15 study); the synth rule on 64 synthetic pad cases (v16 study).
RULES = (('brass', {'guitar': 1, 'other': 2}), ('guitar', {'other': 2, 'synth': 1}),
         # Pads: unclassified residual and strings. Backing stays untouched so the vocal/instrumental split is unchanged.
         ('synth', {'other': .3}))


def transfer(mixture, tracks, evidence, target, sources):
    """Return {source: audio moved into target}; callers subtract/add so the sum is preserved."""
    names = list(sources)
    arrays = [np.asarray(a, dtype=np.float32) for a in (mixture, *(tracks[s] for s in names), *(evidence[h] for h in CONTEXT.values()))]
    if len(arrays[0]) < 2048 or any(a.ndim != 2 or a.shape[1] != 2 or a.shape != arrays[0].shape or not np.isfinite(a).all() for a in arrays):
        raise ValueError('Context routing timeline mismatch')
    n = len(arrays[0]); moved = {s: np.zeros_like(arrays[0]) for s in names}
    for start in range(0, n, 512*2048):
        end = min(n, start+512*2048); left = max(0, start-2048); right = min(n, end+2048)
        X, *rest = [signal.stft(a[left:right].T, fs=44100, nperseg=2048, noverlap=1536)[2] for a in arrays]
        S = dict(zip(names, rest[:len(names)])); C = dict(zip(CONTEXT, rest[len(names):]))
        C['percussion'] = C['percussion']+C.pop('timpani')
        power = sum(np.abs(c)**2 for c in C.values())+np.abs(X-sum(C.values()))**2
        share = {f: np.divide(np.abs(c)**2, power, out=np.zeros(power.shape), where=power > 0) for f, c in C.items()}
        T = C[target]
        for s in names:
            confidence = np.clip(share[target]-share.get(s, 0), 0, 1)**sources[s]
            d = np.abs(S[s])*np.abs(T)
            confidence *= np.clip(np.divide(np.real(S[s]*T.conj()), d, out=np.zeros(d.shape), where=d > 0), 0, 1)**2
            audio = signal.istft(S[s]*confidence, fs=44100, nperseg=2048, noverlap=1536)[1].T
            moved[s][start:end] = audio[start-left:end-left]
    return moved


def apply(root, row, evidence, job_id, version='context-family-routing-v1'):
    from pathlib import Path
    import soundfile as sf
    from .common import sha256_file
    root = Path(root); source = {t['family']: t for t in row['tracks']}
    if row.get('context_routing'):
        if row['context_routing']['version'] == version: return row
        raise ValueError('Different context routing version requires the original tracks')
    def read(path):
        audio, rate = sf.read(path, dtype='float32', always_2d=True)
        if rate != 44100: raise ValueError('Context routing rate mismatch')
        return audio
    families = sorted({f for target, sources in RULES for f in (target, *sources)})
    tracks = {f: read(root/source[f]['path']) for f in families}; before = {f: a.copy() for f, a in tracks.items()}
    mixture = read(root/row['original']); context = {h: read(Path(evidence[h])) for h in CONTEXT.values()}
    moved_rms = {}
    for target, sources in RULES:
        moved = transfer(mixture, tracks, context, target, sources)
        for s, audio in moved.items():
            tracks[s] = tracks[s]-audio; tracks[target] = tracks[target]+audio
            moved_rms[s+'->'+target] = float(np.sqrt(np.mean(audio.astype(float)**2)))
    error = float(np.max(np.abs(sum(a.astype(float) for a in before.values())-sum(a.astype(float) for a in tracks.values()))))
    if error > 2e-6: raise ValueError('Context routing partition reconstruction failed')
    folder = root/'web'/row['id']; folder.mkdir(parents=True, exist_ok=True); output = []
    for track in row['tracks']:
        family = track['family']
        if family in tracks:
            path = folder/(family+'-context-routed-v1.wav'); temporary = path.with_suffix('.partial.wav')
            sf.write(temporary, tracks[family], 44100, subtype='FLOAT'); temporary.replace(path); peak = float(np.abs(tracks[family]).max())
            track = {k: v for k, v in track.items() if k not in ('silent', 'signal_rms')}
            track.update(path=str(path.relative_to(root)), sha256=sha256_file(path), peak=peak, over_full_scale=peak > 1, derivation='context_family_routing')
        output.append(track)
    return {**row, 'tracks': output, 'context_routing': {'version': version, 'context_job_id': job_id, 'rules': [list(r) for r in RULES],
            'partition_max_abs_error': error, 'moved_rms': moved_rms, 'original_tracks': {f: source[f] for f in families}}}
