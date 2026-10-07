"""Apply the v15 brass/guitar context routing to verified v14 outputs (context inference reused), reassemble, score."""
import copy
from pathlib import Path
from uuid import uuid4
from music_analyzer.common import project_root,read_json,write_json,sha256_file
from music_analyzer.web_server import WebLibrary
from music_analyzer.job_contracts import job_folder,verify_result
from music_analyzer.context_routing import apply,CONTEXT
from music_analyzer.ground_truth import evaluate

base=project_root();cases=base/'data/ground-truth/cases';summary=[]
for group in ('stability-v14','controls-v14'):
    for case in sorted((cases/group).iterdir()):
        run=read_json(case/'run.json');root=Path(run['root']);before=read_json(root/'web'/run['id']/'record.json')
        assert before['state']=='SUCCEEDED'
        destination=cases/group.replace('v14','v15')/case.name;destination.mkdir(parents=True,exist_ok=True)
        write_json(destination/'prepared.json',read_json(case/'prepared.json'))
        library=WebLibrary.__new__(WebLibrary);library.root=root;library.web=root/'web'
        row=copy.deepcopy(before)
        row.update(id='analysis_'+uuid4().hex,separation_version='staged-context-families-v15',source_analysis=before['id'],
                   verification_method='cached-v14-plus-context-routing',processing_seconds=None,timing_profile='cached-v14-plus-new-stage')
        context_id=row['job_ids'][1];context_dir=job_folder(root,context_id)/'result'
        context=verify_result(context_dir,read_json(job_folder(root,context_id)/'job.json'))
        sources={t['family']:context_dir/t['path'] for t in context['stems']}
        row=apply(root,row,{h:sources[h] for h in CONTEXT.values()},context_id)
        selected=[t for t in row['tracks'] if t['family']!='other']
        row=library.with_remaining(row,selected,'flat_v4','remaining-final13-v15.wav',row['instrumental'],[t for t in selected if t['family'] not in ('lead','backing')])
        library.validate_partition(row['instrumental'],[t for t in row['tracks'] if t['family'] not in ('lead','backing')])
        library.validate_partition(row['original'],row['tracks'])
        row['tracks']=[library.track_activity(t) for t in row['tracks']]
        write_json(root/'web'/row['id']/'record.json',row);write_json(destination/'run.json',{'root':str(root),'id':row['id'],'source_analysis':before['id']})
        old={t['family']:t for t in before['tracks']}
        changed=sorted(t['family'] for t in row['tracks'] if sha256_file(root/t['path'])!=sha256_file(root/old[t['family']]['path']))
        assert set(changed)<={'brass','guitar','synth','other'},changed
        evaluate(destination,root,row)
        summary.append({'case':case.name,'group':group.replace('v14','v15'),'analysis_id':row['id'],'changed_tracks':changed,
                        'moved_rms':row['context_routing']['moved_rms'],
                        'original_and_instrumental_sums_verified':True})
        write_json(base/'docs/THIRTEEN_TRACK_V15_VERIFICATION.json',summary);print('V15',len(summary),case.name,changed,flush=True)
