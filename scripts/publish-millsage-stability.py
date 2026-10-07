"""Expose the verified new result to the original owner, preserving the old analysis."""
import os,argparse
from pathlib import Path
from music_analyzer.common import project_root,read_json,write_json,sha256_file
from music_analyzer.auth import AuthStore
from music_analyzer.web_server import WebLibrary

parser=argparse.ArgumentParser();parser.add_argument('--version',choices=['v11','v12'],default='v12');args=parser.parse_args()
base=project_root();destination=base/'data/separation'
run=read_json(base/('data/ground-truth/cases/millsage-stability-'+args.version+'/run.json'));source=Path(run['root'])
row=read_json(source/'web'/run['id']/'record.json')
assert row['state']=='SUCCEEDED' and len(row['tracks'])==13
auth=AuthStore();owners=auth.query('SELECT user_id FROM analysis_owners WHERE analysis_id=%s',(run['before_id'],))
if len(owners)!=1:raise ValueError('Original analysis must have exactly one owner')
original=read_json(destination/'web'/run['before_id']/'record.json')
for name in ['jobs','inputs','web']:
    for path in (source/name).rglob('*'):
        if not path.is_file():continue
        target=destination/path.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if path.name=='record.json' and name=='web':continue
            if sha256_file(path)!=sha256_file(target):raise ValueError('Publication path collision')
        else:os.link(path,target)
row.update(name=original['name']+' · 13트랙 보완 '+args.version,source_analysis=original['id'],publication='verified-isolated-rerun')
library=WebLibrary.__new__(WebLibrary);library.root=destination
library.validate_partition(row['instrumental'],[t for t in row['tracks'] if t['family'] not in ('lead','backing')])
library.validate_partition(row['original'],row['tracks'])
write_json(destination/'web'/row['id']/'record.json',row)
if not auth.owns(owners[0]['user_id'],row['id']):auth.assign(owners[0]['user_id'],row['id'])
print('NEW OWNED ANALYSIS',row['id'])
