"""Offline study: route unclassified/string material into synth using the original-mix synth head."""
import sys,json
from pathlib import Path
import numpy as np,soundfile as sf
from music_analyzer.common import project_root,read_json,write_json
from music_analyzer.context_routing import transfer,CONTEXT
from music_analyzer.ground_truth import score

base=project_root()/'data/pad-eval';rd=lambda p:sf.read(p,dtype='float32',always_2d=True)[0]
def evaluate(case,outs,mix,refs):
    r={}
    for f,keys in (('synth',['synth','synth_strings']),('strings',['strings']),('other',[])):
        ref=sum((refs[k] for k in keys if k in refs),np.zeros_like(mix));s=score(ref,outs[f],mix)
        r[f]=[s['raw_sdr_db'],s['target_gain'],s['output_to_mix_db'],s['reference_absent']]
    return r
configs=json.loads(sys.argv[1]);results=[]
for case in sorted((base/'cases').iterdir()):
    k=read_json(case/'case.json')
    if k['kind']=='pad_piano_only':continue
    prep=read_json(case/'prepared.json');mix=rd(prep['input']);refs={n:rd(v['path']) for n,v in prep['references'].items()}
    outs={f.stem:rd(f) for f in (case/'evaluation-outputs').glob('*.wav') if f.stem!='guitar_total'}
    H=np.load(base/'heads'/(case.name+'.npz'));zero=np.zeros_like(mix)
    ctx={h:(H[h].astype(np.float32) if h in H.files else zero) for h in CONTEXT.values()}
    item={'case':case.name,'kind':k['kind'],'split':k['split'],'timbre':k['pad_timbre'],'before':evaluate(case,outs,mix,refs)}
    for name,cfg in configs.items():
        moved=transfer(mix,outs,ctx,'synth',cfg);o={f:a.copy() for f,a in outs.items()}
        for s,m in moved.items():o[s]=o[s]-m;o['synth']=o['synth']+m
        item[name]=evaluate(case,o,mix,refs)
    results.append(item)
write_json(base/'routing.json',results);print('done',len(results))
