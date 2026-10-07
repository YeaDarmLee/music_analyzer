"""Test independent drum extraction from piano estimates against known references."""
from pathlib import Path
import time
import argparse
import numpy as np
import soundfile as sf
from music_analyzer.common import project_root, read_json, write_json
from music_analyzer.ingest import ingest_file
from music_analyzer.job_service import JobService
from music_analyzer.job_contracts import job_folder, verify_result, JobError
from music_analyzer.ground_truth import score
from music_analyzer.piano_drum_refinement import extract

parser=argparse.ArgumentParser()
parser.add_argument('--context',action='store_true')
args=parser.parse_args()

base=project_root()
root=base/'data/separation'
study=base/'data/ground-truth/cases'/('piano-drum-context-study' if args.context else 'piano-drum-study')
study.mkdir(parents=True,exist_ok=True)
cases=[]
for folder in sorted((base/'data/ground-truth/cases').iterdir()):
    if not (folder/'run.json').exists():continue
    execution=read_json(folder/'run.json')
    library=Path(execution['root'])
    row=read_json(library/'web'/execution['id']/'record.json')
    prepared=read_json(folder/'prepared.json')
    tracks={t['family']:library/t['path'] for t in row['tracks']}
    mix=sf.read(prepared['input'],dtype='float32',always_2d=True)[0]
    target=np.zeros_like(mix)
    if 'piano' in prepared['references']:
        target=sf.read(prepared['references']['piano']['path'],dtype='float32',always_2d=True)[0]
    drums=np.zeros_like(mix)
    if 'drums' in prepared['references']:
        drums=sf.read(prepared['references']['drums']['path'],dtype='float32',always_2d=True)[0]
    cases.append((folder.name,tracks['piano'],target,drums,mix,None))
    if folder.name=='slakh20-pad-15-30':
        isolated=study/'piano-only.wav';sf.write(isolated,target,44100,subtype='FLOAT')
        cases.append(('piano-only-control',isolated,target,np.zeros_like(target),target,None))
row=read_json(root/'web/analysis_d4b524e77ed94bbabeff20ac0d991426/record.json')
tracks={t['family']:root/t['path'] for t in row['tracks']}
real_mix=sf.read(root/row['instrumental'],dtype='float32',always_2d=True)[0][:20*44100]
cases.append(('millsage-0-20',tracks['piano'],None,None,real_mix,(0,20)))
results=[]
service=JobService(root)
for name,path,target,drums,mix,crop in cases:
    folder=study/name;folder.mkdir(exist_ok=True)
    piano=sf.read(path,dtype='float32',always_2d=True)[0]
    if crop:piano=piano[int(crop[0]*44100):int(crop[1]*44100)]
    input_path=folder/'model-input.wav'
    sf.write(input_path,mix if args.context else piano,44100,subtype='FLOAT')
    sf.write(folder/'piano-before.wav',piano,44100,subtype='FLOAT')
    if (folder/'job.json').exists():
        job=read_json(folder/'job.json')
    else:
        asset=ingest_file(input_path,root)
        print(name,'INFERENCE',flush=True)
        while True:
            try:
                job=service.run(asset.name,'baseline')
                break
            except JobError as error:
                if error.code!='GPU_BUSY':raise
                time.sleep(2)
        if job['state']!='SUCCEEDED':raise RuntimeError(job)
        write_json(folder/'job.json',job)
    result_dir=job_folder(root,job['job_id'])/'result'
    manifest=verify_result(result_dir,job)
    stem=next(t for t in manifest['stems'] if t['family']=='drums')
    estimate=sf.read(result_dir/stem['path'],dtype='float32',always_2d=True)[0]
    if args.context:
        sources={}
        for source in manifest['stems']:
            audio=sf.read(result_dir/source['path'],dtype='float32',always_2d=True)[0]
            sources[source['family']]=audio
        estimate=extract(piano,sources)
    revised=piano-estimate
    sf.write(folder/'drums-removed.wav',estimate,44100,subtype='FLOAT')
    sf.write(folder/'piano-after.wav',revised,44100,subtype='FLOAT')
    item={'name':name,'job_id':job['job_id'],'removed_rms':float(np.sqrt(np.mean(estimate.astype(float)**2))),
          'before_rms':float(np.sqrt(np.mean(piano.astype(float)**2)))}
    if target is not None:
        item.update(before=score(target,piano,mix),after=score(target,revised,mix),
                    removed_vs_actual_drums=score(drums,estimate,mix))
    results.append(item)
    write_json(study/'report.json',results)
    print(name, {k:item[k] for k in ('removed_rms','before_rms')},
          None if target is None else (item['before']['raw_sdr_db'],item['after']['raw_sdr_db']),flush=True)
