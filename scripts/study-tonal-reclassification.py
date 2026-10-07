"""Test replacement estimates to undo synth/string confusion, without publishing."""
import argparse
from pathlib import Path
import numpy as np
import soundfile as sf
from music_analyzer.common import project_root,read_json,write_json,sha256_file

parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','infer','score']);args=parser.parse_args()
base=project_root();cases=base/'data/ground-truth/cases';study=cases/'tonal-reclassification'
prompts={
    'synth':['electronic synthesizer pad playing sustained chords','acoustic bowed strings, brass, piano, electric guitar, acoustic guitar, bass and drums'],
    'strings':['acoustic bowed orchestral strings playing violin and cello','electronic synthesizer pad, brass, piano, electric guitar, acoustic guitar, bass and drums'],
    'brass':['acoustic brass instruments playing trumpet and trombone','electronic synthesizer, bowed orchestral strings, piano, electric guitar, acoustic guitar, bass and drums']}
plan=study/'plan.json'
if args.action=='prepare':
    jobs=[]
    for case in sorted(cases.iterdir()):
        if not (case/'prepared.json').exists() or not (case/'run.json').exists():continue
        prepared=read_json(case/'prepared.json')
        if prepared.get('exclude_from_evaluation'):continue
        execution=read_json(case/'run.json');root=Path(execution['root'])
        row=read_json(root/'web'/execution['id']/'record.json')
        if row['state']!='SUCCEEDED':continue
        tracks={t['family']:sf.read(root/t['path'],dtype='float32',always_2d=True)[0] for t in row['tracks']}
        if (case/'without-recovery/synth.wav').exists():
            for family in ('synth','strings','brass','other'):
                tracks[family]=sf.read(case/'without-recovery'/(family+'.wav'),dtype='float32',always_2d=True)[0]
        for family in prompts:
            folder=study/case.name/family;folder.mkdir(parents=True,exist_ok=True)
            source=tracks['brass']+tracks['other'] if family=='brass' else tracks['synth']+tracks['strings']+tracks['other']
            path=folder/'input-source.wav';sf.write(path,source,44100,subtype='FLOAT')
            jobs.append({'name':case.name+'/'+family,'family':'tonal_'+family,'input':str(path),
                         'input_sha256':sha256_file(path),'output':str(folder),'queries':['part_b']})
    write_json(plan,{'data_root':str(base/'data/separation'),'cases':jobs})
elif args.action=='infer':
    from music_analyzer import part_study
    from filelock import Timeout
    import time
    for family,text in prompts.items():
        part_study.PROMPTS['tonal_'+family]={'baseline':text,'a':text,'b':text,'labels':[family,family]}
    while True:
        try:part_study.infer_plan(plan);break
        except Timeout:time.sleep(2)
else:
    from music_analyzer.ground_truth import score
    summary=[]
    for job in read_json(plan)['cases']:
        folder=Path(job['output'])
        if not (folder/'manifest.json').exists():continue
        name,family=job['name'].split('/')
        case=cases/name;prepared=read_json(case/'prepared.json')
        mix=sf.read(prepared['input'],dtype='float32',always_2d=True)[0]
        ref=prepared['references'].get(family)
        target=sf.read(ref['path'],dtype='float32',always_2d=True)[0] if ref else np.zeros_like(mix)
        before=sf.read(case/'without-recovery'/(family+'.wav'),dtype='float32',always_2d=True)[0]
        estimate=sf.read(folder/'part_b.wav',dtype='float32',always_2d=True)[0]
        item={'case':name,'family':family,'before':score(target,before,mix),'replacement':score(target,estimate,mix)}
        summary.append(item)
        print(name,family,item['before']['raw_sdr_db'],item['replacement']['raw_sdr_db'],flush=True)
    write_json(base/'docs/TONAL_RECLASSIFICATION_RESULTS.json',summary)
