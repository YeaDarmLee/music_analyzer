"""Update existing final-ten records, preserving backups and account ownership."""
from music_analyzer.common import project_root, read_json, write_json
from music_analyzer.web_server import WebLibrary
from music_analyzer.synth_recovery import apply, run_for_library

root=project_root()/'data/separation'
records=[read_json(p) for p in (root/'web').glob('analysis_*/record.json')]
assert not any(r['state'] in ('RUNNING','QUEUED') for r in records),'Active analyses must finish first'
library=WebLibrary(root)
try:
    for row in records:
        if row['state']!='SUCCEEDED' or row.get('model')!='final_10' or row.get('synth_recovery'):continue
        print('UPDATING',row['id'],flush=True)
        validated=project_root()/'data/part-studies/synth-full-validation/miracle'
        if row['id']=='analysis_27127556cdff41d3a68abdc248433838':
            row=apply(root,row,validated/'part_b.wav',validated/'manifest.json')
        else:row=run_for_library(library,row)
        write_json(root/'web'/row['id']/'record.json',row)
        print('UPDATED',row['id'],flush=True)
finally:library.executor.shutdown(wait=True)
