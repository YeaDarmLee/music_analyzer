"""Offline study: return percussion lost to backing vocals using original-mix context evidence."""
import sys,json
from pathlib import Path
import numpy as np,soundfile as sf
from scipy import signal
from music_analyzer.common import project_root,read_json,write_json
from music_analyzer.job_contracts import job_folder
from music_analyzer.ground_truth import score

base=project_root();cases=base/'data/ground-truth/cases'
def rd(p):return sf.read(p,dtype='float32',always_2d=True)[0]
def stft(a):return signal.stft(a.T,fs=44100,nperseg=2048,noverlap=1536)[2]

def route(tracks,mix,ctx,power,sources=('backing',)):
    X=stft(mix);P=stft(ctx['percussion']+ctx['timpani'])
    rivals=[stft(ctx[f]) for f in ('synth','bowed_strings','brass','acoustic-guitar','electric-guitar')]
    den=np.abs(P)**2+sum(np.abs(r)**2 for r in rivals)+np.abs(X-P-sum(rivals))**2
    w=np.divide(np.abs(P)**2,den,out=np.zeros(den.shape),where=den>0)
    out={f:a.copy() for f,a in tracks.items()}
    for s in sources:
        S=stft(tracks[s]);d=np.abs(S)*np.abs(P)
        coh=np.divide(np.real(S*P.conj()),d,out=np.zeros(d.shape),where=d>0)
        m=signal.istft(S*w**power*np.clip(coh,0,1)**2,fs=44100,nperseg=2048,noverlap=1536)[1].T[:len(mix)]
        out[s]=tracks[s]-m;out['percussion']=out['percussion']+m
    return out

FAM={'percussion':['percussion'],'vocal':['lead','backing'],'lead':['lead'],'backing':['backing'],'drums':['drums']}
REF={'percussion':['percussion','pitched_percussion'],'vocal':['lead','backing']}
def evaluate(t,mix,refs):
    r={}
    for f,ms in FAM.items():
        ref=sum((refs[k] for k in REF.get(f,[f]) if k in refs),np.zeros_like(mix));s=score(ref,sum(t[m] for m in ms),mix)
        r[f]=s['raw_sdr_db'] if s['raw_sdr_db'] is not None else ['absent',s['output_to_mix_db'],s['target_gain']]
    return r

configs=json.loads(sys.argv[1]);results=[]
for group in ('stability-v13','controls-v13'):
    for case in sorted((cases/group).iterdir()):
        prep=read_json(case/'prepared.json');run=read_json(case/'run.json');root=Path(run['root'])
        row=read_json(root/'web'/run['id']/'record.json');tracks={t['family']:rd(root/t['path']) for t in row['tracks']}
        d=job_folder(root,row['job_ids'][1])/'result';ctx={s['family']:rd(d/s['path']) for s in read_json(d/'manifest.json')['stems']}
        refs={k:rd(v['path']) for k,v in prep['references'].items()};mix=rd(prep['input'])
        item={'case':case.name,'before':evaluate(tracks,mix,refs)}
        for k,c in configs.items():item[k]=evaluate(route(tracks,mix,ctx,**c),mix,refs)
        results.append(item)
write_json(cases/'string-family-study'/'routing.json',results);print('done')
