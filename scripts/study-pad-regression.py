"""Offline regression check of synth routing rules on the 32 ground-truth conditions (synth leakage and strings change)."""
import sys,json
from pathlib import Path
import numpy as np,soundfile as sf
from music_analyzer.common import project_root,read_json
from music_analyzer.job_contracts import job_folder
from music_analyzer.context_routing import transfer,CONTEXT
from music_analyzer.ground_truth import score
base=project_root()/'data/ground-truth/cases';rd=lambda p:sf.read(p,dtype='float32',always_2d=True)[0]
configs=json.loads(sys.argv[1]);table={}
for g in ('stability-v15','controls-v15'):
    for case in sorted((base/g).iterdir()):
        prep=read_json(case/'prepared.json');run=read_json(case/'run.json');root=Path(run['root']);row=read_json(root/'web'/run['id']/'record.json')
        mix=rd(prep['input']);refs={n:rd(v['path']) for n,v in prep['references'].items()}
        # v14 tracks are what the routing sees in the pipeline; v15 outputs differ only by earlier rules, close enough for a leak/regression comparison.
        outs={f.stem:rd(f) for f in (case/'evaluation-outputs').glob('*.wav') if f.stem!='guitar_total'}
        d=job_folder(root,row['job_ids'][1])/'result';stems={s['family']:rd(d/s['path']) for s in read_json(d/'manifest.json')['stems']}
        zero=np.zeros_like(mix);ctx={h:stems.get(h,zero) for h in CONTEXT.values()}
        def ev(o):
            r={}
            for f in ('synth','strings'):
                s=score(refs.get(f,zero),o[f],mix);r[f]=(s['raw_sdr_db'],s['output_to_mix_db'],s['reference_absent'])
            return r
        table[case.name]={'before':ev(outs)}
        for name,cfg in configs.items():
            moved=transfer(mix,outs,ctx,'synth',cfg);o={f:a.copy() for f,a in outs.items()}
            for s,m in moved.items():o[s]=o[s]-m;o['synth']=o['synth']+m
            table[case.name][name]=ev(o)
for name in configs:
    worst_leak=[];sdr_drop=[]
    for c,t in table.items():
        b,a=t['before'],t[name]
        if b['synth'][2]:worst_leak.append((round(a['synth'][1]-b['synth'][1],1),c,round(a['synth'][1],1)))
        for f in ('synth','strings'):
            if b[f][0] is not None and a[f][0] is not None:sdr_drop.append((round(a[f][0]-b[f][0],2),c,f))
    print(name,'| largest synth leak increase (dB, case, new level):',sorted(worst_leak)[-4:],'| worst SDR change:',sorted(sdr_drop)[:3])
