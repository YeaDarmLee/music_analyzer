"""Measure first-stage instrument loss and restoration against exact mixture references."""
from pathlib import Path
import numpy as np
import soundfile as sf
from music_analyzer.common import project_root,read_json,write_json
from music_analyzer.instrumental_restoration import restore
from music_analyzer.ground_truth import score

base=project_root()/'data/ground-truth/cases';summary=[]
for case in sorted(base.iterdir()):
    if not (case/'prepared.json').exists() or not (case/'run.json').exists():continue
    prepared=read_json(case/'prepared.json')
    if prepared.get('exclude_from_evaluation'):continue
    execution=read_json(case/'run.json');root=Path(execution['root'])
    row=read_json(root/'web'/execution['id']/'record.json')
    if row['state']!='SUCCEEDED':continue
    first=root/'jobs'/row['job_ids'][0]/'result/stems/vocals.wav'
    if not first.exists():continue
    directory=base/'extended-head-study'/case.name
    if not (directory/'bowed_strings.wav').exists():continue
    vocals=sf.read(first,dtype='float32',always_2d=True)[0]
    instrumental=sf.read(root/row['instrumental'],dtype='float32',always_2d=True)[0]
    evidence=[sf.read(directory/(family+'.wav'),dtype='float32',always_2d=True)[0] for family in ['bowed_strings','brass','synth']]
    after,inst,moved=restore(vocals,instrumental,evidence)
    mix=sf.read(prepared['input'],dtype='float32',always_2d=True)[0]
    target=np.zeros_like(mix)
    for family in ('lead','backing'):
        ref=prepared['references'].get(family)
        if ref:target+=sf.read(ref['path'],dtype='float32',always_2d=True)[0]
    item={'case':case.name,'vocal_before':score(target,vocals,mix),'vocal_after':score(target,after,mix),
          'instrumental_before':score(mix-target,instrumental,mix),'instrumental_after':score(mix-target,inst,mix)}
    output=case/'restoration-candidate';output.mkdir(exist_ok=True)
    for family,audio in [('vocals',after),('instrumental',inst),('moved',moved)]:sf.write(output/(family+'.wav'),audio,44100,subtype='FLOAT')
    summary.append(item);print(case.name,item['vocal_before']['raw_sdr_db'],item['vocal_after']['raw_sdr_db'],
        item['instrumental_before']['raw_sdr_db'],item['instrumental_after']['raw_sdr_db'],flush=True)
write_json(project_root()/'docs/VOCAL_INSTRUMENT_RESTORATION_RESULTS.json',summary)
