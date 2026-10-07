"""Summarize cached official-head experiments without occupying the GPU."""
from pathlib import Path
import numpy as np
import soundfile as sf
from music_analyzer.common import project_root,read_json,write_json
from music_analyzer.mega53_experiment import configuration,CHECKPOINT_SHA
from music_analyzer.ground_truth import score

base=project_root();cases=base/'data/ground-truth/cases';study=cases/'extended-head-study'
labels=configuration()['training']['instruments'];heads={i:labels[i] for i in [6,7,8,12,17,19,25,29,31,32,37,38,40,51,52]};summary=[]
for case in sorted(cases.iterdir()):
    if not (case/'prepared.json').exists():continue
    prepared=read_json(case/'prepared.json');directory=study/case.name
    if prepared.get('exclude_from_evaluation') or not all((directory/(name+'.wav')).exists() for name in heads.values()):continue
    mix=sf.read(prepared['input'],dtype='float32',always_2d=True)[0]
    refs={f:sf.read(r['path'],dtype='float32',always_2d=True)[0] for f,r in prepared['references'].items()}
    estimates=[sf.read(directory/(name+'.wav'),dtype='float32',always_2d=True)[0] for name in heads.values()]
    coefficients=np.linalg.lstsq(np.column_stack([a.reshape(-1)[::8] for a in refs.values()]),np.column_stack([a.reshape(-1)[::8] for a in estimates]),rcond=None)[0]
    item={'case':case.name,'input_sha256':prepared['input_sha256'],'head_reference_coefficients':{name:dict(zip(refs,coefficients[:,i].tolist())) for i,name in enumerate(heads.values())},'scores':{}}
    for family,names in {'synth':['synth','keys','organ'],'strings':['bowed_strings','strings'],'brass':['brass'],'pitched_percussion':['bells','glockenspiel','marimba','timpani','wind-chimes']}.items():
        prediction=sum(estimates[list(heads.values()).index(name)] for name in names)
        item['scores'][family]=score(refs.get(family,np.zeros_like(mix)),prediction,mix)
    summary.append(item)
write_json(base/'docs/EXTENDED_INSTRUMENT_HEAD_RESULTS.json',{'source_checkpoint_sha256':CHECKPOINT_SHA,'heads':heads,'cases':summary,
    'note':'Naive group sums are experimental diagnostics, not the production routing method.'})
print('CACHED OFFICIAL HEAD CASES',len(summary))
