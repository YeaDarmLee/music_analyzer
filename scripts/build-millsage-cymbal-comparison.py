"""Verify and expose the isolated full-song v10 result and the reported excerpt."""
import numpy as np
import soundfile as sf
from scipy import signal
from music_analyzer.common import project_root,read_json,write_json
from music_analyzer.web_server import WebLibrary
from pathlib import Path

base=project_root();folder=base/'data/ground-truth/cases/millsage-cymbal-v10'
run=read_json(folder/'run.json');root=Path(run['root'])
row=read_json(root/'web'/run['id']/'record.json')
assert row['state']=='SUCCEEDED' and row['separation_version']=='staged-guitar-residual-v10'
library=WebLibrary(root)
try:library.validate_partition(row['instrumental'],[t for t in row['tracks'] if t['family'] not in ('lead','backing')])
finally:library.executor.shutdown()
tracks={t['family']:root/t['path'] for t in row['tracks']}
before=row['cymbal_recovery']['original_tracks']
paths={'original':root/row['original'],'piano-before':root/before['piano']['path'],
       'piano-after':tracks['piano'],'drums-before':root/before['drums']['path'],'drums-after':tracks['drums']}
clips={}
for family,path in paths.items():
    with sf.SoundFile(path) as source:
        source.seek(5*44100);clips[family]=source.read(5*44100,dtype='float32',always_2d=True)
clips['moved']=clips['piano-before']-clips['piano-after']
error=float(np.max(np.abs(clips['piano-before'].astype(float)+clips['drums-before']-clips['piano-after'].astype(float)-clips['drums-after'])))
assert error<2e-7
band=signal.butter(4,4000,fs=44100,btype='highpass',output='sos')
high={family:float(np.sqrt(np.mean(signal.sosfiltfilt(band,audio,axis=0)**2))) for family,audio in clips.items()}
report={'analysis_id':row['id'],'state':row['state'],'version':row['separation_version'],
        'processing_seconds':row['processing_seconds'],'track_count':len(row['tracks']),
        'full_song_partition_verified':True,'excerpt_pair_max_abs_error':error,
        'high_frequency_change_db':float(20*np.log10(high['piano-after']/high['piano-before'])),
        'high_frequency_rms':high,'note':'No ground-truth ride stem or perceptual confirmation; high-frequency reduction is not separation accuracy.'}
write_json(base/'docs/MILLSAGE_CYMBAL_V10_RESULTS.json',report)
gain=min(1,.9/max(float(np.abs(a).max()) for a in clips.values()))
html='<meta charset=utf-8><title>기사개전 v10 보완 비교</title><h1>기사개전 5–10초 · 전체곡 재분석 결과</h1><p>기존 결과 보존 · 동일 재생 게인 · 같은 시점에서 비교</p>'
for family,audio in clips.items():
    sf.write(folder/(family+'.wav'),audio,44100,subtype='FLOAT')
    html+=f'<p>{family} <audio controls preload="metadata" src="{family}.wav"></audio></p>'
html+='<script>let previous;document.querySelectorAll("audio").forEach(p=>{p.volume='+str(gain)+';p.onplay=()=>{if(previous&&previous!==p){const t=previous.currentTime;previous.pause();p.currentTime=t}previous=p}})</script>'
(folder/'comparison.html').write_text(html,encoding='utf-8')
print(report)
