"""Apply the production v16 context routing to verified v15 outputs and re-score (cached context inference, no GPU)."""
import copy,sys
from pathlib import Path
from uuid import uuid4
from music_analyzer.common import project_root,read_json,write_json,sha256_file
from music_analyzer.web_server import WebLibrary
from music_analyzer.job_contracts import job_folder,verify_result
from music_analyzer.context_routing import apply,CONTEXT
from music_analyzer.ground_truth import evaluate

base=project_root();cases=base/'data/ground-truth/cases';pad=base/'data/pad-eval';summary=[]
sets=[(cases/'stability-v15',cases/'stability-v16'),(cases/'controls-v15',cases/'controls-v16'),(pad/'cases',pad/'cases-v16')]
for source_dir,target_dir in sets:
    for case in sorted(source_dir.iterdir()):
        if not (case/'run.json').exists() or not (case/'report.json').exists():continue
        run=read_json(case/'run.json');root=Path(run['root']);before=read_json(root/'web'/run['id']/'record.json')
        destination=target_dir/case.name;destination.mkdir(parents=True,exist_ok=True)
        for name in ('prepared.json','case.json'):
            if (case/name).exists():write_json(destination/name,read_json(case/name))
        library=WebLibrary.__new__(WebLibrary);library.root=root;library.web=root/'web'
        row=copy.deepcopy(before)
        row.update(id='analysis_'+uuid4().hex,separation_version='staged-context-pads-v16',source_analysis=before['id'],
                   verification_method='cached-v15-plus-pad-routing',processing_seconds=None,timing_profile='cached-v15-plus-new-stage')
        row.pop('context_routing',None)
        # Start from the v14 tracks so the whole v15+v16 rule set runs once, exactly as the pipeline does.
        original=before['context_routing']['original_tracks'] if before.get('context_routing') else {}
        row['tracks']=[original.get(t['family'],t) for t in row['tracks']]
        context_id=row['job_ids'][1];context_dir=job_folder(root,context_id)/'result'
        context=verify_result(context_dir,read_json(job_folder(root,context_id)/'job.json'))
        sources={t['family']:context_dir/t['path'] for t in context['stems']}
        row=apply(root,row,{h:sources[h] for h in CONTEXT.values()},context_id)
        selected=[t for t in row['tracks'] if t['family']!='other']
        row=library.with_remaining(row,selected,'flat_v4','remaining-final13-v16.wav',row['instrumental'],[t for t in selected if t['family'] not in ('lead','backing')])
        library.validate_partition(row['instrumental'],[t for t in row['tracks'] if t['family'] not in ('lead','backing')])
        library.validate_partition(row['original'],row['tracks'])
        row['tracks']=[library.track_activity(t) for t in row['tracks']]
        write_json(root/'web'/row['id']/'record.json',row);write_json(destination/'run.json',{'root':str(root),'id':row['id'],'source_analysis':before['id']})
        evaluate(destination,root,row)
        summary.append({'case':case.name,'set':target_dir.name,'analysis_id':row['id'],'moved_rms':row['context_routing']['moved_rms']})
        print('V16',len(summary),case.name,flush=True)
write_json(base/'docs/THIRTEEN_TRACK_V16_VERIFICATION.json',summary)
print('V16 DONE',flush=True)
