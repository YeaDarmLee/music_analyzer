"""Offline study: generic context routing into brass / electric guitar from other tracks."""
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
CTX={'synth':'synth','strings':'bowed_strings','brass':'brass','guitar':'electric-guitar','acoustic_guitar':'acoustic-guitar','percussion':'percussion'}
def route(tracks,mix,ctx,target,sources,power):
    X=stft(mix);C={f:stft(ctx[h]) for f,h in CTX.items()};C['percussion']=C['percussion']+stft(ctx['timpani'])
    den=sum(np.abs(c)**2 for c in C.values())+np.abs(X-sum(C.values()))**2
    w={f:np.divide(np.abs(c)**2,den,out=np.zeros(den.shape),where=den>0) for f,c in C.items()}
    out={f:a.copy() for f,a in tracks.items()};T=C[target]
    for s in sources:
        S=stft(tracks[s]);conf=np.clip(w[target]-w.get(s,0),0,1)**power[s]
        d=np.abs(S)*np.abs(T);conf*=np.clip(np.divide(np.real(S*T.conj()),d,out=np.zeros(d.shape),where=d>0),0,1)**2
        m=signal.istft(S*conf,fs=44100,nperseg=2048,noverlap=1536)[1].T[:len(mix)];out[s]-=m;out[target]+=m
    return out
FAM={'synth':['synth'],'strings':['strings'],'brass':['brass'],'guitar':['guitar'],'guitar_total':['guitar','acoustic_guitar','guitar_residual'],'piano':['piano'],'other':['other'],'vocal':['lead','backing']}
REF={'guitar_total':['guitar','acoustic_guitar'],'vocal':['lead','backing']}
def evaluate(t,mix,refs):
    r={}
    for f,ms in FAM.items():
        ref=sum((refs[k] for k in REF.get(f,[f]) if k in refs),np.zeros_like(mix));s=score(ref,sum(t[m] for m in ms),mix)
        r[f]=s['raw_sdr_db'] if s['raw_sdr_db'] is not None else ['absent',s['output_to_mix_db']]
    return r
configs=json.loads(sys.argv[1]);results=[]
for group in ('stability-v14','controls-v14'):
    for case in sorted((cases/group).iterdir()):
        prep=read_json(case/'prepared.json');run=read_json(case/'run.json');root=Path(run['root'])
        row=read_json(root/'web'/run['id']/'record.json');tracks={t['family']:rd(root/t['path']) for t in row['tracks']}
        d=job_folder(root,row['job_ids'][1])/'result';ctx={s['family']:rd(d/s['path']) for s in read_json(d/'manifest.json')['stems']}
        refs={k:rd(v['path']) for k,v in prep['references'].items()};mix=rd(prep['input'])
        item={'case':case.name,'before':evaluate(tracks,mix,refs)}
        for k,c in configs.items():item[k]=evaluate(route(tracks,mix,ctx,**c),mix,refs)
        results.append(item)
write_json(cases/'string-family-study'/'routing.json',results);print('done')
