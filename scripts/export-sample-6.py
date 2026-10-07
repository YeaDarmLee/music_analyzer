"""Export an excerpt of the Mureka demo song (original + 6-track stems) as mp3 + manifest.json for the homepage player."""
import json, os, subprocess
import numpy as np, soundfile as sf
from music_analyzer.common import project_root, read_json

FFMPEG = os.environ.get('FFMPEG', 'C:/ffmpeg/bin/ffmpeg.exe')
START, LENGTH = float(os.environ.get('START', 40)), float(os.environ.get('LENGTH', 45))
NAMES = {'vocals': ('보컬', '#af8fff'), 'piano': ('피아노', '#e6c66d'), 'guitar': ('기타', '#73a9ff'), 'bass': ('베이스', '#6ad6b3'),
         'drums': ('드럼', '#ef9b63'), 'other': ('기타 악기', '#d090c7')}
base = project_root(); data = base / 'data/separation'
row = read_json(data / 'web/analysis_f94584b850e1489bbfce7f10365a7bf5/record.json')
out = base / 'frontend/public/samples'; out.mkdir(parents=True, exist_ok=True)


def cut(path):
    a, r = sf.read(path, dtype='float32', always_2d=True)
    return a[int(START * r):int((START + LENGTH) * r)], r


def mp3(audio, rate, name):
    wav = out / (name + '.tmp.wav'); sf.write(wav, audio, rate, subtype='PCM_16')
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-i', str(wav), '-b:a', '80k', str(out / (name + '.mp3'))], check=True); wav.unlink()


def peaks(a, n=200):
    m = np.abs(a).max(axis=1); k = len(m) // n
    return [round(float(m[i * k:(i + 1) * k].max()), 3) for i in range(n)]


orig, rate = cut(data / row['original']); mp3(orig, rate, 'original')
tracks = []
for t in row['tracks']:
    if t['family'] not in NAMES: continue
    a, r = cut(data / t['path']); mp3(a, r, t['family'])
    name, color = NAMES[t['family']]
    tracks.append({'key': t['family'], 'name': name, 'color': color, 'file': f"/samples/{t['family']}.mp3", 'peaks': peaks(a), 'db': round(float(20 * np.log10(np.sqrt(np.mean(a.astype('float64') ** 2)) + 1e-12))), })
(out / 'manifest.json').write_text(json.dumps({'duration': round(len(orig) / rate, 1), 'original': {'file': '/samples/original.mp3', 'peaks': peaks(orig)}, 'tracks': tracks}, ensure_ascii=False), encoding='utf-8')
print([(t['key'], t['db']) for t in tracks])
