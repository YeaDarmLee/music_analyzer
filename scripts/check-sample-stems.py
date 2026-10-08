"""Where does each rendered ground-truth stem of the demo song end up? (share of its energy projected onto each output track)"""
import numpy as np, soundfile as sf
from music_analyzer.common import project_root, read_json
import os
b = project_root() / os.environ.get('SAMPLE_DIR', 'data/sample'); run = read_json(b / 'run.json'); root = b / 'library'
row = read_json(root / 'web' / run['id'] / 'record.json')
def rd(p):
    a, _ = sf.read(p, dtype='float64', always_2d=True); return a
out = {t['family']: rd(root / t['path']) for t in row['tracks'] if t['family'] != 'original' and not t.get('reference')}
gt = {p.stem: rd(p) for p in (b / 'stems').glob('*.wav')}
n = min(min(len(a) for a in out.values()), min(len(a) for a in gt.values()))
print('outputs:', ', '.join(f"{k}({20*np.log10(np.sqrt(np.mean(v[:n]**2))+1e-12):.0f}dB)" for k, v in out.items()))
for g, a in gt.items():
    a = a[:n]; e = float((a * a).sum())
    shares = {k: float((a * v[:n]).sum()) / e for k, v in out.items()}
    top = sorted(shares.items(), key=lambda x: -x[1])[:3]
    print(f"{g:16s}", '  '.join(f"{k} {s*100:5.1f}%" for k, s in top))
