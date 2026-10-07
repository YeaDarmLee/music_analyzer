"""Inspect the reported 5–10 second piano/drum overlap without modifying results."""
import json
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy import signal
from music_analyzer.common import project_root, read_json, write_json, sha256_file

root = project_root()/'data/separation'
identifier = 'analysis_d4b524e77ed94bbabeff20ac0d991426'
row = read_json(root/'web'/identifier/'record.json')
output = project_root()/'data/ground-truth/cases/millsage-ride-5-10'
output.mkdir(parents=True,exist_ok=True)
paths = {t['family']:root/t['path'] for t in row['tracks']}
paths.update(original=root/row['original'],instrumental=root/row['instrumental'])
clips = {}
metrics = {}
for family in ('original','instrumental','piano','drums','other'):
    with sf.SoundFile(paths[family]) as source:
        assert source.samplerate==44100
        source.seek(5*44100)
        audio = source.read(5*44100,dtype='float32',always_2d=True)
    clips[family] = audio
    sf.write(output/(family+'.wav'),audio,44100,subtype='FLOAT')
    high = signal.sosfiltfilt(signal.butter(4,4000,fs=44100,btype='highpass',output='sos'),audio,axis=0)
    metrics[family] = {'rms':float(np.sqrt(np.mean(audio.astype(float)**2))),
                       'above_4khz_rms':float(np.sqrt(np.mean(high**2)))}

envelopes = {}
for family in ('piano','drums'):
    high = signal.sosfiltfilt(signal.butter(4,4000,fs=44100,btype='highpass',output='sos'),clips[family],axis=0)
    # 10 ms stereo energy envelopes: timing evidence, not an instrument classifier.
    envelopes[family] = np.sqrt(np.mean(high.reshape(500,441,2)**2,axis=(1,2)))
correlation = float(np.corrcoef(envelopes['piano'],envelopes['drums'])[0,1])
stage = root/'jobs/job_d81435a195b44c1591214101a49db698/result/stems/piano.wav'
assert sha256_file(paths['piano'])==sha256_file(stage)
report = {'analysis_id':identifier,'separation_version':row['separation_version'],
          'interval_seconds':[5,10],'metrics':metrics,'high_frequency_envelope_correlation':correlation,
          'final_piano_identical_to_base_model':True,'model':'bs_roformer_6s',
          'interpretation':'Timing correlation is not proof of ride identity; no ground truth available.'}
write_json(output/'report.json',report)
gain = min(1,.9/max(float(np.abs(a).max()) for a in clips.values()))
html = '<!doctype html><meta charset=utf-8><title>기사개전 5–10초 점검</title><h1>기사개전 5–10초 점검</h1><p>동일 구간 · 동일 재생 게인 · 기존 결과 수정 없음</p>'
for family in clips:
    html += f'<p>{family} <audio controls preload="metadata" src="{family}.wav"></audio></p>'
html += '<script>let previous;document.querySelectorAll("audio").forEach(p=>{p.volume='+str(gain)+';p.onplay=()=>{if(previous&&previous!==p){const t=previous.currentTime;previous.pause();p.currentTime=t}previous=p}})</script>'
(output/'comparison.html').write_text(html,encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
