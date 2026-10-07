"""Full isolated v10 rerun; never replaces the user's existing analysis."""
import os
import time
from pathlib import Path
from music_analyzer.common import project_root,read_json,write_json
from music_analyzer.registry import paths
from music_analyzer.web_server import WebLibrary

base=project_root()
source=base/'data/separation'
old=read_json(source/'web/analysis_d4b524e77ed94bbabeff20ac0d991426/record.json')
folder=base/'data/ground-truth/cases/millsage-cymbal-v10'
root=folder/'library'
for model in ('melband_roformer_kj','bs_roformer_6s','bs_karaoke','bs_roformer_mega5'):
    checkpoint,registration=paths(source,model)
    target=root/'models'/model;target.mkdir(parents=True,exist_ok=True)
    if not (target/checkpoint.name).exists():os.link(checkpoint,target/checkpoint.name)
    write_json(target/'registration.json',read_json(registration))
library=WebLibrary(root)
try:
    original=source/old['original']
    with original.open('rb') as stream:
        public=library.create('millsage-original.wav','final_11',stream,original.stat().st_size)
    write_json(folder/'run.json',{'id':public['id'],'root':str(root.resolve()),'before_id':old['id']})
    previous=None
    while True:
        row=library.get(public['id'])
        if previous!=row['stage']:
            print(row['stage'],flush=True);previous=row['stage']
        if row['state'] in ('SUCCEEDED','FAILED','CANCELLED'):break
        time.sleep(.5)
    if row['state']!='SUCCEEDED':raise RuntimeError(row.get('error',row))
    print('FULL V10 SUCCEEDED',row['id'],flush=True)
finally:
    library.executor.shutdown(wait=True)
