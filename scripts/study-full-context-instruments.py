"""Compare whole-accompaniment Mega5 heads with staged residual heads on nine references."""
import time
from pathlib import Path
import numpy as np
import soundfile as sf
from music_analyzer.common import project_root,read_json,write_json
from music_analyzer.ingest import ingest_file
from music_analyzer.job_service import JobService
from music_analyzer.job_contracts import JobError,job_folder,verify_result
from music_analyzer.ground_truth import score

base=project_root();root=base/'data/separation';service=JobService(root)
study=base/'data/ground-truth/cases/full-context-instruments';study.mkdir(exist_ok=True)
summary=[]
for case in sorted((base/'data/ground-truth/cases').iterdir()):
    if not (case/'run.json').exists() or not (case/'prepared.json').exists():continue
    execution=read_json(case/'run.json');oldroot=Path(execution['root'])
    row=read_json(oldroot/'web'/execution['id']/'record.json')
    folder=study/case.name;folder.mkdir(exist_ok=True)
    if (folder/'job.json').exists():job=read_json(folder/'job.json')
    else:
        asset=ingest_file(oldroot/row['instrumental'],root)
        print(case.name,'FULL CONTEXT INFERENCE',flush=True)
        while True:
            try:job=service.run(asset.name,'instrument_mega5');break
            except JobError as error:
                if error.code!='GPU_BUSY':raise
                time.sleep(2)
        if job['state']!='SUCCEEDED':raise RuntimeError(job)
        write_json(folder/'job.json',job)
    resultdir=job_folder(root,job['job_id'])/'result';manifest=verify_result(resultdir,job)
    prepared=read_json(case/'prepared.json')
    mix=sf.read(prepared['input'],dtype='float32',always_2d=True)[0]
    item={'case':case.name,'job_id':job['job_id'],'metrics':{}}
    for stem in manifest['stems']:
        family={'bowed_strings':'strings','acoustic-guitar':'acoustic_guitar','electric-guitar':'guitar'}.get(stem['family'],stem['family'])
        estimate=sf.read(resultdir/stem['path'],dtype='float32',always_2d=True)[0]
        sf.write(folder/(family+'.wav'),estimate,44100,subtype='FLOAT')
        reference=prepared['references'].get(family)
        target=sf.read(reference['path'],dtype='float32',always_2d=True)[0] if reference else np.zeros_like(mix)
        before=sf.read(case/'without-recovery'/(family+'.wav'),dtype='float32',always_2d=True)[0]
        item['metrics'][family]={'staged':score(target,before,mix),'full_context':score(target,estimate,mix)}
    summary.append(item)
    write_json(study/'report.json',summary)
    print(case.name,{f:(v['staged']['raw_sdr_db'],v['full_context']['raw_sdr_db']) for f,v in item['metrics'].items()},flush=True)
write_json(base/'docs/FULL_CONTEXT_INSTRUMENT_RESULTS.json',summary)
