"""Full pipeline controls for quiet voices and piano; preserve all earlier outputs."""
from pathlib import Path
import numpy as np
import soundfile as sf
from music_analyzer.common import project_root,read_json,write_json
from music_analyzer.ground_truth import prepare,run,score
from music_analyzer.job_contracts import job_folder,verify_result

base=project_root();cases=base/'data/ground-truth/cases';summary=[]
names=['vocal-violin','quiet-vocal-violin','very-quiet-vocal-violin','vocal-quiet-violin','vocal-no-violin']
for name,gain in [('piano-only',1),('quiet-piano-only',.1),('very-quiet-piano-only',.01)]:
    folder=cases/name
    if not (folder/'prepared.json').exists():
        write_json(folder/'case.json',{'name':name,'start_sec':0,'duration_sec':15,
            'reference_sources':{'piano':['../slakh20-pad-15-30/references/piano.wav']},'reference_gains':{'piano':gain},
            'scope':'Native sampled piano, no other instruments; quiet control.'})
        prepare(folder/'case.json')
    names.append(name)
for name in names:
    original=cases/name;folder=cases/'controls-v11'/name;folder.mkdir(parents=True,exist_ok=True)
    prepared=read_json(original/'prepared.json');write_json(folder/'prepared.json',prepared)
    if not (folder/'report.json').exists():run(folder)
    execution=read_json(folder/'run.json');root=Path(execution['root']);row=read_json(root/'web'/execution['id']/'record.json')
    tracks={t['family']:sf.read(root/t['path'],dtype='float32',always_2d=True)[0] for t in row['tracks']}
    mix=sf.read(prepared['input'],dtype='float32',always_2d=True)[0]
    if name in names[:5]:
        baseline=read_json(original/'vocal_roformer-job.json');directory=job_folder(base/'data/separation',baseline['job_id'])/'result'
        manifest=verify_result(directory,baseline);stem=next(t for t in manifest['stems'] if t['family']=='vocals')
        before=sf.read(directory/stem['path'],dtype='float32',always_2d=True)[0]
        target=sf.read(prepared['references']['lead']['path'],dtype='float32',always_2d=True)[0]
        item={'case':name,'before_vocal':score(target,before,mix),'after_vocal_total':score(target,tracks['lead']+tracks['backing'],mix),
              'baseline_note':'Before is initial vocal separator output; after is lead plus backing from full final pipeline.'}
    else:
        target=sf.read(prepared['references']['piano']['path'],dtype='float32',always_2d=True)[0]
        item={'case':name,'piano':score(target,tracks['piano'],mix),'false_tracks':{f:score(np.zeros_like(mix),a,mix) for f,a in tracks.items() if f!='piano'}}
    item.update(analysis_id=row['id'],track_count=len(row['tracks']),separation_version=row['separation_version'])
    summary.append(item);write_json(base/'docs/THIRTEEN_TRACK_CONTROL_RESULTS.json',summary)
    print('CONTROL',name,flush=True)
