"""Export the demo song (original + separated tracks) as mp3 + manifest.json for the homepage player."""
import json, os, subprocess
import numpy as np, soundfile as sf
from music_analyzer.common import project_root, read_json

FFMPEG = os.environ.get('FFMPEG', 'C:/ffmpeg/bin/ffmpeg.exe')
NAMES = {'lead': '보컬', 'backing': '코러스', 'piano': '피아노', 'synth': '신디사이저', 'strings': '스트링', 'brass': '브라스',
         'acoustic_guitar': '통기타', 'guitar': '일렉기타', 'guitar_residual': '기타 보조', 'bass': '베이스', 'drums': '드럼',
         'percussion': '기타 타악기', 'other': '추가 반주'}
COLORS = {'lead': '#af8fff', 'backing': '#e4a6d3', 'piano': '#e6c66d', 'synth': '#d090c7', 'strings': '#93c5c0', 'brass': '#e6aa5b',
          'acoustic_guitar': '#cda76c', 'guitar': '#73a9ff', 'guitar_residual': '#6ad6b3', 'bass': '#6ad6b3', 'drums': '#ef9b63',
          'percussion': '#e8d27f', 'other': '#d090c7'}
MIN_DB = float(os.environ.get('MIN_DB', -55))
base = project_root(); sample = base / os.environ.get('SAMPLE_DIR', 'data/sample'); root = sample / 'library'
out = base / 'frontend/public/samples'; out.mkdir(parents=True, exist_ok=True)
row = read_json(root / 'web' / read_json(sample / 'run.json')['id'] / 'record.json')


def mp3(audio, name):
    wav = out / (name + '.tmp.wav'); sf.write(wav, audio, 44100, subtype='PCM_16')
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-i', str(wav), '-b:a', '96k', str(out / (name + '.mp3'))], check=True); wav.unlink()


def peaks(a, n=240):
    m = np.abs(a).max(axis=1); k = len(m) // n; m = m / (m.max() + 1e-9)
    return [round(float(m[i * k:(i + 1) * k].max()), 3) for i in range(n)]


tracks = []
scale = 1.0
orig, _ = sf.read(sample / 'mix.wav', dtype='float32', always_2d=True)
mp3(orig, 'original')
for fam in NAMES:
    t = next((t for t in row['tracks'] if t['family'] == fam), None)
    if not t: continue
    a, _ = sf.read(root / t['path'], dtype='float32', always_2d=True)
    db = 20 * np.log10(np.sqrt(np.mean(a.astype('float64') ** 2)) + 1e-12)
    if db < MIN_DB: print('skip', fam, round(db)); continue
    mp3(a, fam); tracks.append({'key': fam, 'name': NAMES[fam], 'color': COLORS[fam], 'file': f'/samples/{fam}.mp3', 'peaks': peaks(a)})
    print('ok', fam, round(db))
(out / 'manifest.json').write_text(json.dumps({'duration': round(len(orig) / 44100, 1), 'original': {'file': '/samples/original.mp3', 'peaks': peaks(orig)}, 'tracks': tracks}, ensure_ascii=False), encoding='utf-8')
print('tracks', len(tracks))
