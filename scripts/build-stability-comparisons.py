"""Summarize full reruns against their preserved baseline and expose aligned audio."""
import html
import argparse
import os
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import butter,sosfiltfilt
from music_analyzer.common import project_root,read_json,write_json,sha256_file
from music_analyzer.web_server import WebLibrary

parser=argparse.ArgumentParser();parser.add_argument('--version',choices=['v11','v12','v13','v14','v15'],default='v12');args=parser.parse_args();number=int(args.version[1:])
base=project_root();cases=base/'data/ground-truth/cases';study=cases/('stability-'+args.version);controls=cases/('controls-'+args.version)
families=('lead','backing','piano','synth','strings','brass','acoustic_guitar','guitar','bass','drums','percussion','other','guitar_total')
summary=[]
style='<style>body{font:16px system-ui;max-width:1250px;margin:32px auto;padding:16px;background:#111;color:#eee}a{color:#b4c9ff}td,th{padding:10px;border-bottom:1px solid #444}audio{width:280px}table{border-collapse:collapse}</style>'
for case in sorted([*study.iterdir(),*(controls.iterdir() if controls.exists() else [])]):
    if not (case/'report.json').exists():continue
    current=read_json(case/'report.json');original=cases/case.name
    if number>=13:baseline=cases/case.parent.name.replace(args.version,'v'+str(number-1))/case.name
    else:baseline=(cases/'controls-v11'/case.name) if case.parent==controls else (original/'v9' if (original/'v9/report.json').exists() else original)
    before=read_json(baseline/'report.json')
    prepared=read_json(case/'prepared.json')
    if not (case/'mix.wav').exists():os.link(prepared['input'],case/'mix.wav')
    run=read_json(case/'run.json');root=Path(run['root']);row=read_json(root/'web'/run['id']/'record.json')
    library=WebLibrary.__new__(WebLibrary);library.root=root
    library.validate_partition(row['instrumental'],[t for t in row['tracks'] if t['family'] not in ('lead','backing')])
    library.validate_partition(row['original'],row['tracks'])
    changes={};rows=[];peak=1.
    for f in families:
        a=before['metrics'].get(f,{});b=current['metrics'][f]
        changes[f]={k:{'before':a.get(k),'after':b[k]} for k in ('raw_sdr_db','target_gain','output_to_mix_db','reference_rms','error_rms')}
        if a.get('raw_sdr_db') is not None and b['raw_sdr_db'] is not None:changes[f]['sdr_delta_db']=b['raw_sdr_db']-a['raw_sdr_db']
        paths=[case/'evaluation-references'/(f+'.wav'),baseline/'evaluation-outputs'/(f+'.wav'),case/'evaluation-outputs'/(f+'.wav')]
        players=[]
        for p in paths:
            if not p.exists():players.append('<td>기존 분류 없음</td>');continue
            x=sf.read(p,dtype='float32',always_2d=True)[0];peak=max(peak,float(np.abs(x).max()))
            url=os.path.relpath(p,case).replace('\\','/')
            players.append('<td><audio controls preload="none" src="'+html.escape(url,quote=True)+'"></audio></td>')
        rows.append('<tr><th>'+f+'</th>'+''.join(players)+'</tr>')
    page='<!doctype html><meta charset=utf-8>'+style+'<h1>'+html.escape(case.name)+'</h1><p>동일 입력·정답·재생 게인. 기존 결과와 13트랙 보완 결과를 비교합니다.</p><p><audio controls src="mix.wav"></audio></p><table><tr><th>분류</th><th>정답</th><th>이전</th><th>보완 후</th></tr>'+''.join(rows)+'</table>'
    page+='<script>let previous;document.querySelectorAll("audio").forEach(p=>{p.volume='+str(min(1,.9/peak))+';p.onplay=()=>{if(previous&&previous!==p){const t=previous.currentTime;previous.pause();if(Number.isFinite(p.duration)&&t<p.duration)p.currentTime=t}previous=p}})</script>'
    (case/'before-after.html').write_text(page,encoding='utf-8')
    summary.append({'case':case.name,'group':case.parent.name,'before_version':before['separation_version'],'after_version':current['separation_version'],
                    'analysis_id':row['id'],'track_count':len(row['tracks']),'partition_verified':True,'original_sum_verified':True,
                    'processing_seconds':row['processing_seconds'],'input_sha256':prepared['input_sha256'],'metrics':changes})
write_json(base/('docs/THIRTEEN_TRACK_'+args.version.upper()+'_STABILITY_RESULTS.json'),summary)

if not (cases/('millsage-stability-'+args.version)/'run.json').exists():
    print('VERIFIED',len(summary),'CASES (no full-song rerun)');raise SystemExit
folder=cases/('millsage-stability-'+args.version);run=read_json(folder/'run.json');root=Path(run['root'])
row=read_json(root/'web'/run['id']/'record.json');assert row['state']=='SUCCEEDED'
if number>=13:
    previous=read_json(cases/('millsage-stability-'+{13:'v12',15:'v13'}[number])/'run.json');old_root=Path(previous['root']);old=read_json(old_root/'web'/previous['id']/'record.json')
else:old_root=base/'data/separation';old=read_json(old_root/'web'/run['before_id']/'record.json')
paths={t['family']:root/t['path'] for t in row['tracks']};old_paths={t['family']:old_root/t['path'] for t in old['tracks']}
clips={}
for label,path in {'original':root/row['original'],**{f+'-before':old_paths[f] for f in (('synth','strings','brass','guitar','backing','other') if number>=13 else ('piano','drums'))},
                   **{f+'-after':paths[f] for f in ('piano','drums','percussion','synth','strings','brass','guitar','backing','other')}}.items():
    with sf.SoundFile(path) as source:source.seek(5*44100);clips[label]=source.read(5*44100,dtype='float32',always_2d=True)
    sf.write(folder/(label+'.wav'),clips[label],44100,subtype='FLOAT')
band=butter(4,4000,fs=44100,btype='highpass',output='sos')
high={f:float(np.sqrt(np.mean(sosfiltfilt(band,x,axis=0)**2))) for f,x in clips.items()}
library=WebLibrary.__new__(WebLibrary);library.root=root
library.validate_partition(row['instrumental'],[t for t in row['tracks'] if t['family'] not in ('lead','backing')])
library.validate_partition(row['original'],row['tracks'])
write_json(base/('docs/MILLSAGE_STABILITY_'+args.version.upper()+'_RESULTS.json'),{'analysis_id':row['id'],'version':row['separation_version'],
    'processing_seconds':row['processing_seconds'],'track_count':len(row['tracks']),'full_song_partition_verified':True,'original_sum_verified':True,
    'high_frequency_change_db':None if number>=13 else float(20*np.log10(high['piano-after']/high['piano-before'])),
    'string_routing':row.get('string_routing',{}).get('moved_rms'),'context_routing':row.get('context_routing',{}).get('moved_rms'),'backing_percussion':row.get('backing_percussion',{}).get('moved_rms'),'string_routing_from_backing':row.get('string_routing',{}).get('from_backing_rms'),
    'high_frequency_rms':high,'cymbal_pair_max_abs_error':row['cymbal_recovery']['pair_max_abs_error'],
    'note':'No isolated ride ground truth; reduced high-frequency energy does not prove perceptual separation accuracy.'})
page='<!doctype html><meta charset=utf-8>'+style+'<h1>기사개전 5–10초 · 전체곡 재분석</h1><p>동일 재생 게인. 고역 감소는 수치 확인이며 라이드 정답 분리 정확도는 아닙니다.</p>'
for f in clips:page+='<p>'+f+' <audio controls preload="none" src="'+f+'.wav"></audio></p>'
page+='<script>let previous;document.querySelectorAll("audio").forEach(p=>{p.volume='+str(min(1,.9/max(np.abs(x).max() for x in clips.values())))+';p.onplay=()=>{if(previous&&previous!==p){const t=previous.currentTime;previous.pause();p.currentTime=t}previous=p}})</script>'
(folder/'comparison.html').write_text(page,encoding='utf-8')
index='<!doctype html><meta charset=utf-8>'+style+'<h1>13트랙 안정성 테스트</h1><p>정답이 있는 샘플과 실제 곡을 구분합니다. 일부 테스트는 실제 단음 샘플을 인공적으로 합성한 진단용 믹스입니다.</p><a href="millsage-stability-'+args.version+'/comparison.html">기사개전 5–10초</a><ul>'
index+=''.join('<li><a href="'+r['group']+'/'+r['case']+'/before-after.html">'+r['case']+'</a></li>' for r in summary)+'</ul>'
(cases/('stability-'+args.version+'.html')).write_text(index,encoding='utf-8')
print('VERIFIED',len(summary),'CASES + FULL MILLSAGE',flush=True)
