"""Compare a vocal-detail complaint with context; never replace original results."""
import argparse,json,time
from pathlib import Path
from uuid import uuid4
import numpy as np
import soundfile as sf
from music_analyzer.common import read_json,write_json,sha256_file,project_root
from music_analyzer.ingest import ingest_file
from music_analyzer.job_service import JobService
from music_analyzer.job_contracts import verify_result,job_folder

parser=argparse.ArgumentParser()
parser.add_argument('--analysis-id',required=True)
parser.add_argument('--start',type=float,default=145)
parser.add_argument('--duration',type=float,default=30)
args=parser.parse_args()
root=project_root()/'data/separation'
parent=read_json(root/'web'/args.analysis_id/'record.json')
if parent['state']!='SUCCEEDED':raise ValueError('Completed parent required')
tracks={t['family']:t for t in parent['tracks']}
if not {'vocals','lead','backing'}<=tracks.keys():raise ValueError('Vocal detail tracks required')
rate=44100;start=round(args.start*rate);count=round(args.duration*rate);context=15*rate
if start<0 or count<=0 or count>60*rate:raise ValueError('Invalid comparison range')
folder=root/'vocal-comparisons'/('comparison_'+uuid4().hex);folder.mkdir(parents=True)
source=root/tracks['vocals']['path']
with sf.SoundFile(source) as f:
    if start+count>f.frames:raise ValueError('Comparison exceeds parent')
    offset=max(0,start-context);end=min(f.frames,start+count+context)
    f.seek(offset);audio=f.read(end-offset,dtype='float32',always_2d=True)
clip=folder/'context.wav';sf.write(clip,audio,rate,subtype='FLOAT')
reference=folder/'vocals.wav';sf.write(reference,audio[start-offset:start-offset+count],rate,subtype='FLOAT')
manifest={'parent_analysis_id':parent['id'],'start_frame':start,'num_frames':count,'context_start_frame':offset,'context_num_frames':end-offset,'source_sha256':sha256_file(source),'quality_improvement_verified':False,'results':[]}

def row(label,model):
    result={'id':'analysis_'+uuid4().hex,'name':f"{parent['name']} · 리드/코러스 비교 {args.start:g}–{args.start+args.duration:g}초 · {label}", 'state':'RUNNING','stage':'비교 구간 분리 중','progress':0,'created':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'model':model,'duration':count/rate,'original':str(reference.relative_to(root)),'tracks':[],'job_ids':[], 'comparison_parent_id':parent['id'],'source_start_sec':start/rate,'quality_improvement_verified':False}
    return result

def save(result):write_json(root/'web'/result['id']/'record.json',result)

def publish(result,estimates):
    output=folder/result['id'];output.mkdir(exist_ok=True);stems=[]
    for family,samples in estimates.items():
        if samples.shape!=(count,2) or not np.isfinite(samples).all():raise ValueError('Invalid comparison timeline')
        path=output/(family+'.wav');sf.write(path,samples,rate,subtype='FLOAT')
        stems.append({'family':family,'path':str(path.relative_to(root)),'sha256':sha256_file(path),'peak':float(np.abs(samples).max()),'derivation':'comparison_crop'})
    result.update(state='SUCCEEDED',progress=100,stage='비교 완료 · 청취 검증 필요',tracks=stems);save(result)
    manifest['results'].append({'analysis_id':result['id'],'model':result['model'],'job_ids':result['job_ids']});write_json(folder/'manifest.json',manifest)
    print(json.dumps({'analysis_id':result['id'],'state':result['state']},ensure_ascii=False),flush=True)

baseline=row('기존 BS','bs_karaoke');baseline['job_ids']=parent.get('job_ids',[])
old={}
for family in ('lead','backing'):
    with sf.SoundFile(root/tracks[family]['path']) as f:f.seek(start);old[family]=f.read(count,dtype='float32',always_2d=True)
publish(baseline,old)
asset=ingest_file(clip,root)
for preset,label in [('bs_karaoke_refined','BS 고겹침 후보'),('karaoke_roformer','Mel-Band 대체 후보')]:
    result=row(label,preset);save(result)
    try:
        def update(job):
            p=job.get('progress') or {};result.update(progress=min(97,round(95*p.get('completed',0)/max(1,p.get('total',0)))),active_job_id=job['job_id']);save(result)
        job=JobService(root).run(asset.name,preset,update)
        if job['state']!='SUCCEEDED':raise ValueError(str(job.get('error') or job['state']))
        out=job_folder(root,job['job_id'])/'result';verified=verify_result(out,job);estimates={}
        for stem in verified['stems']:
            with sf.SoundFile(out/stem['path']) as f:f.seek(start-offset);estimates[stem['family']]=f.read(count,dtype='float32',always_2d=True)
        result['job_ids']=[job['job_id']];result.pop('active_job_id',None);publish(result,estimates)
    except Exception as e:
        result.update(state='FAILED',stage='비교 실패',error=str(e));save(result);raise
print(json.dumps({'manifest':str(folder/'manifest.json')},ensure_ascii=False),flush=True)
