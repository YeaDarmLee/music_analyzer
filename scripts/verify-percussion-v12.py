"""Reuse validated v11 core outputs, infer the new registered percussion stage, reassemble."""
import copy,time,os
from pathlib import Path
from uuid import uuid4
import numpy as np,soundfile as sf
from music_analyzer.common import project_root,read_json,write_json,sha256_file
from music_analyzer.web_server import WebLibrary
from music_analyzer.ingest import ingest_file
from music_analyzer.job_service import JobService
from music_analyzer.job_contracts import JobError,job_folder,verify_result
from music_analyzer.percussion_refinement import prepare_source,apply
from music_analyzer.ground_truth import evaluate

base=project_root();cases=base/'data/ground-truth/cases';completed=set();summary=[]
while len(completed)<32:
    progressed=False
    for group in ('stability-v11','controls-v11'):
        for case in sorted((cases/group).iterdir()):
            key=(group,case.name)
            if key in completed or not (case/'report.json').exists():continue
            execution=read_json(case/'run.json');root=Path(execution['root']);before=read_json(root/'web'/execution['id']/'record.json')
            if before['state']!='SUCCEEDED':continue
            destination=cases/group.replace('v11','v12')/case.name;destination.mkdir(parents=True,exist_ok=True)
            write_json(destination/'prepared.json',read_json(case/'prepared.json'))
            if not (destination/'mix.wav').exists():os.link(read_json(case/'prepared.json')['input'],destination/'mix.wav')
            library=WebLibrary.__new__(WebLibrary);library.root=root;library.web=root/'web'
            if (destination/'run.json').exists():
                saved=read_json(destination/'run.json');row=read_json(root/'web'/saved['id']/'record.json')
            else:row={}
            if row.get('state')!='SUCCEEDED':
                row=copy.deepcopy(before);original=row.pop('percussion_refinement')['original_tracks']
                row.update(id='analysis_'+uuid4().hex,state='RUNNING',separation_version='staged-context-percussion-v12',
                    source_analysis=before['id'],verification_method='cached-core-plus-new-registered-percussion-inference',
                    tonal_job_id=before.get('tonal_job_id',before['job_ids'][-1]))
                row['tracks']=[original.get(t['family'],t) for t in row['tracks'] if t['family']!='percussion']
                record=root/'web'/row['id']/'record.json';write_json(record,row)
                write_json(destination/'run.json',{'root':str(root),'id':row['id'],'source_analysis':before['id']})
                source=prepare_source(root,row);asset=ingest_file(source,root);service=JobService(root)
                print(case.name,'REGISTERED PERCUSSION INFERENCE',flush=True)
                while True:
                    try:job=service.run(asset.name,'instrument_mega7');break
                    except JobError as e:
                        if e.code!='GPU_BUSY':raise
                        time.sleep(1)
                if job['state']!='SUCCEEDED':raise RuntimeError(job)
                directory=job_folder(root,job['job_id'])/'result';manifest=verify_result(directory,job)
                secondary={t['family']:directory/t['path'] for t in manifest['stems']}
                context_id=before['job_ids'][1];context_dir=job_folder(root,context_id)/'result'
                context=verify_result(context_dir,read_json(job_folder(root,context_id)/'job.json'))
                primary={t['family']:context_dir/t['path'] for t in context['stems']}
                row['job_ids'].append(job['job_id']);row['percussion_context_job_id']=job['job_id']
                row=apply(root,row,primary['percussion'],context_id,
                    additional=(primary['timpani'],secondary['percussion'],secondary['timpani']),version='context-supported-percussion-v2')
                selected=[t for t in row['tracks'] if t['family']!='other']
                row=library.with_remaining(row,selected,'flat_v4','remaining-final13-v12.wav',row['instrumental'],[t for t in selected if t['family'] not in ('lead','backing')])
                library.validate_partition(row['instrumental'],[t for t in row['tracks'] if t['family'] not in ('lead','backing')]);library.validate_partition(row['original'],row['tracks'])
                row.update(state='SUCCEEDED',stage='분석 완료',progress=100,active_job_id=None,tracks=[library.track_activity(t) for t in row['tracks']])
                write_json(record,row)
                # The new stage must not change any existing tonal or vocal track.
                old_tracks={t['family']:t for t in before['tracks']}
                for t in row['tracks']:
                    if t['family'] not in ('drums','other','percussion'):
                        assert sha256_file(root/t['path'])==sha256_file(root/old_tracks[t['family']]['path'])
            row.update(core_processing_seconds=before.get('processing_seconds'),processing_seconds=None,
                       timing_profile='cached-core-plus-new-registered-stage')
            write_json(root/'web'/row['id']/'record.json',row)
            if not (destination/'report.json').exists():evaluate(destination,root,row)
            else:
                report=read_json(destination/'report.json');report['processing_seconds']=None
                report['timing_note']='Core inference reused; this is not a fresh complete-pipeline timing measurement.'
                write_json(destination/'report.json',report)
            item={'case':case.name,'group':group,'analysis_id':row['id'],'method':row['verification_method'],
                  'unchanged_other_ten_tracks':True,'original_and_instrumental_sums_verified':True,'percussion_job_id':row['percussion_context_job_id']}
            summary.append(item);write_json(base/'docs/THIRTEEN_TRACK_V12_VERIFICATION.json',summary)
            completed.add(key);progressed=True;print('V12 VERIFIED',len(completed),case.name,flush=True)
    if not progressed:time.sleep(2)
print('ALL 32 V12 SAMPLES VERIFIED',flush=True)
