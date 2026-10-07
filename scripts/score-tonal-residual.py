from pathlib import Path
import numpy as np
import soundfile as sf
from music_analyzer.common import project_root,read_json,write_json
from music_analyzer.ground_truth import score
from tonal_refinement_candidate import recover

base=project_root()/'data/ground-truth/cases';summary=[]
for case in sorted(base.iterdir()):
    if not (case/'run.json').exists() or not (case/'prepared.json').exists():continue
    prepared=read_json(case/'prepared.json')
    if prepared.get('exclude_from_evaluation'):continue
    directory=base/'extended-head-study'/case.name
    if not (directory/'brass.wav').exists():continue
    latest=base/'stability-v11'/case.name
    execution=read_json((latest if (latest/'report.json').exists() else case)/'run.json');root=Path(execution['root']);row=read_json(root/'web'/execution['id']/'record.json')
    tracks={t['family']:sf.read(root/t['path'],dtype='float32',always_2d=True)[0] for t in row['tracks']}
    if not (latest/'report.json').exists():
        for f in ('synth','strings','brass'):
            recovery=row.get(f+'_recovery')
            if recovery:tracks[f]=sf.read(root/recovery['original_tracks'][f]['path'],dtype='float32',always_2d=True)[0]
        if (case/'without-recovery/other.wav').exists():tracks['other']=sf.read(case/'without-recovery/other.wav',dtype='float32',always_2d=True)[0]
    evidence={f:sf.read(directory/(head+'.wav'),dtype='float32',always_2d=True)[0] for f,head in [('synth','synth'),('strings','bowed_strings'),('brass','brass')]}
    after,remaining=recover(tracks['other'],tracks,evidence)
    mix=sf.read(prepared['input'],dtype='float32',always_2d=True)[0];item={'case':case.name,'baseline_version':row['separation_version'],'metrics':{}}
    for f in after:
        ref=prepared['references'].get(f);target=sf.read(ref['path'],dtype='float32',always_2d=True)[0] if ref else np.zeros_like(mix)
        item['metrics'][f]={'before':score(target,tracks[f],mix),'after':score(target,after[f],mix)}
    summary.append(item)
    print(case.name,{f:[round(m['before']['raw_sdr_db'] or 0,2),round(m['after']['raw_sdr_db'] or 0,2)] for f,m in item['metrics'].items()},flush=True)
write_json(project_root()/'docs/TONAL_RESIDUAL_RESULTS.json',summary)
