"""Lead/backing split from Mega53 lead-vocal / back-vocal head evidence with exact sum preservation.

The heads were trained on full mixes; on an isolated vocal stem their absolute level is off (~2x on the test song),
so they are used only as ownership evidence: backing = vocals * share, lead = vocals - backing.
"""
import numpy as np
from scipy import signal


def split(vocals, lead, backing, power=1):
    arrays = [np.asarray(a, dtype=np.float32) for a in (vocals, lead, backing)]
    if any(a.ndim != 2 or a.shape[1] != 2 or a.shape != arrays[0].shape or not np.isfinite(a).all() for a in arrays) or len(arrays[0]) < 2048:
        raise ValueError('Vocal split timeline mismatch')
    vocals = arrays[0]; moved = np.zeros_like(vocals)
    for start in range(0, len(vocals), 512 * 2048):
        end = min(len(vocals), start + 512 * 2048); left = max(0, start - 2048); right = min(len(vocals), end + 2048)
        V, L, B = [signal.stft(a[left:right].T, fs=44100, nperseg=2048, noverlap=1536)[2] for a in arrays]
        total = np.abs(L) ** 2 + np.abs(B) ** 2
        share = np.divide(np.abs(B) ** 2, total, out=np.zeros(total.shape), where=total > 0) ** power
        audio = signal.istft(V * share, fs=44100, nperseg=2048, noverlap=1536)[1].T
        moved[start:end] = audio[start - left:end - left]
    return vocals - moved, moved


def publish(root, folder, vocals_path, detail_dir, detail_result, version='mega-head-ownership-v1'):
    """Write the sum-preserving lead/backing pair next to the analysis record; job results stay untouched."""
    from pathlib import Path
    import soundfile as sf
    from .common import sha256_file
    root = Path(root).resolve(); folder = Path(folder)
    def read(path):
        audio, rate = sf.read(path, dtype='float32', always_2d=True)
        if rate != 44100 or audio.shape[1] != 2:
            raise ValueError('Vocal split sample format mismatch')
        return audio
    heads = {t['family']: read(Path(detail_dir) / t['path']) for t in detail_result['stems']}
    vocals = read(vocals_path)
    lead, backing = split(vocals, heads['lead'], heads['backing'])
    error = float(np.max(np.abs(lead.astype(np.float64) + backing - vocals)))
    if error > 2e-7:
        raise ValueError('Vocal split reconstruction failed')
    stems = []
    for template in detail_result['stems']:
        family = template['family']; audio = lead if family == 'lead' else backing
        path = folder / f'{family}-{version}.wav'; temporary = path.with_suffix('.partial.wav')
        sf.write(temporary, audio, 44100, subtype='FLOAT'); temporary.replace(path)
        stems.append({**{k: v for k, v in template.items() if k not in ('signal_rms', 'peak', 'silent')},
                      'path': str(path.relative_to(root)), 'sha256': sha256_file(path), 'peak': float(np.abs(audio).max()),
                      'derivation': 'mega53_head_ownership_split', 'split_version': version, 'pair_max_abs_error': error})
    return stems
