"""CLAPSep-free piano -> drums cymbal transfer for commercial_13.

Evidence = the drums stem of the approved Mega53 core4 head (identical weights to the official `drums` head, which beat
the hh / percussion / DSP-only candidates on synthetic GT, see docs/COMMERCIAL_CLEAN_MIGRATION_KO.md). Harmonic protection,
HPSS and the 3-5 kHz band gate are the unchanged final_11 logic; only the semantic (CLAP) mask is replaced.
Whatever leaves piano is added to drums, so the pair sum is preserved.
"""
from pathlib import Path
import numpy as np
import soundfile as sf
from .common import write_json, sha256_file
from .piano_drum_refinement import cymbal_extract

VERSION = 'core4-drums-evidence-cymbal-v1'


def apply(root, row):
    root = Path(root).resolve()
    if row.get('cymbal_recovery', {}).get('version') == VERSION:
        return row
    tracks = {t['family']: t for t in row['tracks']}
    arrays = {}
    for family in ('piano', 'drums'):
        audio, rate = sf.read(root / tracks[family]['path'], dtype='float32', always_2d=True)
        if rate != 44100 or audio.shape[1] != 2 or not np.isfinite(audio).all():
            raise ValueError('Invalid cymbal audio')
        arrays[family] = audio
    if arrays['piano'].shape != arrays['drums'].shape:
        raise ValueError('Cymbal timeline mismatch')
    moved = cymbal_extract(arrays['piano'], arrays['drums'])
    revised = {'piano': arrays['piano'] - moved, 'drums': arrays['drums'] + moved}
    error = float(np.max(np.abs(revised['piano'].astype(np.float64) + revised['drums'] - arrays['piano'].astype(np.float64) - arrays['drums'])))
    if error > 2e-7:
        raise ValueError('Cymbal pair reconstruction failed')
    folder = root / 'web' / row['id']
    backup = folder / 'record-before-cymbal-commercial-v1.json'
    if not backup.exists():
        write_json(backup, row)
    updated = []
    for track in row['tracks']:
        family = track['family']
        if family in revised:
            path = folder / f'{family}-cymbal-commercial-v1.wav'; temporary = path.with_suffix('.partial.wav')
            sf.write(temporary, revised[family], 44100, subtype='FLOAT'); temporary.replace(path)
            peak = float(np.abs(revised[family]).max())
            track = {k: v for k, v in track.items() if k not in ('silent', 'signal_rms')}
            track.update(path=str(path.relative_to(root)), sha256=sha256_file(path), peak=peak, over_full_scale=peak > 1,
                         derivation='harmonic_protected_cymbal_transfer_core4_evidence')
        updated.append(track)
    return {**row, 'tracks': updated, 'cymbal_recovery': {
        'version': VERSION, 'evidence': 'core4_drums_stem', 'pair_max_abs_error': error,
        'moved_rms': float(np.sqrt(np.mean(moved.astype(np.float64) ** 2))),
        'original_tracks': {f: tracks[f] for f in ('piano', 'drums')}}}
