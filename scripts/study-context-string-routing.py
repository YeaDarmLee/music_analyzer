"""Offline study: route violin material back to strings using original-mix context evidence."""
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
def istft(s,n):return signal.istft(s,fs=44100,nperseg=2048,noverlap=1536)[1].T[:n]

def route(tracks,mix,ctx,sources,power,vocal_power):
    """Move content judged as strings by context from `sources` into strings."""
    n=len(mix);X=stft(mix);C={f:stft(ctx[f]) for f in ('synth','bowed_strings','brass')}
    rest=X-sum(C.values());den=sum(np.abs(c)**2 for c in C.values())+np.abs(rest)**2
    w={f:np.divide(np.abs(c)**2,den,out=np.zeros(den.shape),where=den>0) for f,c in C.items()}
    out={f:a.copy() for f,a in tracks.items()};moved=np.zeros_like(mix)
    for s in sources:
        S=stft(tracks[s]);cs=C['bowed_strings']
        rival=w['synth'] if s=='synth' else w['brass']
        conf=np.clip(w["bowed_strings"]-rival,0,1)**(vocal_power if s=="backing" else power[s] if isinstance(power,dict) else power)
        d=np.abs(S)*np.abs(cs);coh=np.divide(np.real(S*cs.conj()),d,out=np.zeros(d.shape),where=d>0)
        conf*=np.clip(coh,0,1)**2
        m=istft(S*conf,n);out[s]=tracks[s]-m;moved+=m
    out['strings']=tracks['strings']+moved
    return out

def load(group,name):
    c=cases/group/name;prep=read_json(c/'prepared.json');run=read_json(c/'run.json');root=Path(run['root'])
    row=read_json(root/'web'/run['id']/'record.json')
    tracks={t['family']:rd(root/t['path']) for t in row['tracks']}
    d=job_folder(root,row['job_ids'][1])/'result';m=read_json(d/'manifest.json')
    ctx={s['family']:rd(d/s['path']) for s in m['stems']}
    refs={k:rd(v['path']) for k,v in prep['references'].items()}
    return tracks,rd(prep['input']),ctx,refs

FAM={'synth':['synth'],'strings':['strings'],'brass':['brass'],'vocal':['lead','backing'],'lead':['lead'],'other':['other'],'piano':['piano'],'guitar':['guitar','acoustic_guitar','guitar_residual']}
def evaluate(tracks,mix,refs):
    r={}
    for f,members in FAM.items():
        est=sum(tracks[m] for m in members if m in tracks)
        ref=sum((refs[k] for k in ({'vocal':['lead','backing'],'guitar':['guitar','acoustic_guitar']}.get(f,[f])) if k in refs),np.zeros_like(mix))
        s=score(ref,est,mix);r[f]=s['raw_sdr_db'] if s['raw_sdr_db'] is not None else ('absent',s['output_to_mix_db'])
    return r

if __name__=='__main__':
    configs=json.loads(sys.argv[1]);results=[]
    for group in ('stability-v12','controls-v12'):
        for case in sorted((cases/group).iterdir()):
            tracks,mix,ctx,refs=load(group,case.name);row={'case':case.name,'before':evaluate(tracks,mix,refs)}
            for k,cfg in configs.items():row[k]=evaluate(route(tracks,mix,ctx,**cfg),mix,refs)
            results.append(row);print(case.name,flush=True)
    write_json(cases/'string-family-study'/'routing.json',results)
