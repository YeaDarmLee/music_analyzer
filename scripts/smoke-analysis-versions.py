"""Check all analysis versions on a short real clip in an isolated library."""
import argparse
import os
import time
import soundfile as sf
from music_analyzer.common import project_root,read_json,write_json
from music_analyzer.registry import paths
from music_analyzer.web_server import WebLibrary

parser=argparse.ArgumentParser()
parser.add_argument('input')
parser.add_argument('--versions',nargs='+',choices=['basic_2','basic_6','final_11'],default=['basic_2','basic_6','final_11'])
args=parser.parse_args()
project=project_root()
root=project/'data/part-studies/analysis-versions-smoke'
root.mkdir(parents=True,exist_ok=True)
for model_id in ('melband_roformer_kj','bs_roformer_6s','bs_karaoke','bs_roformer_mega5'):
    checkpoint,registration=paths(project/'data/separation',model_id)
    folder=root/'models'/model_id;folder.mkdir(parents=True,exist_ok=True)
    if not (folder/checkpoint.name).exists():os.link(checkpoint,folder/checkpoint.name)
    write_json(folder/'registration.json',read_json(registration))
with sf.SoundFile(args.input) as source:
    assert (source.samplerate,source.channels)==(44100,2)
    audio=source.read(10*44100,dtype='float32',always_2d=True)
clip=root/'clip.wav';sf.write(clip,audio,44100,subtype='FLOAT')
library=WebLibrary(root)
results=[]
try:
    for version,count in (('basic_2',2),('basic_6',6),('final_11',12)):
        if version not in args.versions:continue
        started=time.monotonic()
        with clip.open('rb') as stream:public=library.create(clip.name,version,stream,clip.stat().st_size)
        while True:
            row=library.get(public['id'])
            if row['state'] in ('SUCCEEDED','FAILED'):break
            if time.monotonic()-started>300:raise RuntimeError('Smoke timeout')
            time.sleep(.5)
        assert row['state']=='SUCCEEDED',row.get('error')
        assert len(row['tracks'])==count
        result={'version':version,'id':row['id'],'tracks':count,'wall_sec':round(time.monotonic()-started,2)}
        results.append(result);print(result,flush=True)
    write_json(root/'verification.json',results)
finally:library.executor.shutdown()
