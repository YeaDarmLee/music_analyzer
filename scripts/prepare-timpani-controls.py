"""Real CC0 timpani hits, rhythmically placed with a known piano reference."""
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from math import gcd
from music_analyzer.common import project_root,write_json,sha256_file
from music_analyzer.ground_truth import prepare

base=project_root()/'data/ground-truth'
path=base/'freepats/Timpani SFZ+WAV-20240810/samples/1C_v5_rr1.wav'
audio,rate=sf.read(path,dtype='float32',always_2d=True)
factor=gcd(rate,44100);audio=resample_poly(audio,44100//factor,rate//factor,axis=0).astype(np.float32)
if audio.shape[1]==1:audio=np.repeat(audio,2,axis=1)
rhythm=np.zeros((44100*15,2),np.float32)
for start in (0,3,6,9):
    offset=start*44100;length=min(len(audio),len(rhythm)-offset)
    rhythm[offset:offset+length]+=audio[:length]
sf.write(base/'freepats/timpani-rhythm-15s.wav',rhythm,44100,subtype='FLOAT')
for prefix,gain in [('',1),('quiet-',.1),('no-',0)]:
    folder=base/'cases'/('real-'+prefix+'timpani')
    write_json(folder/'case.json',{'name':folder.name,'start_sec':0,'duration_sec':15,
        'reference_sources':{'piano':['../../philharmonia/piano-15s.wav'],
            'pitched_percussion':['../../freepats/timpani-rhythm-15s.wav']},
        'reference_gains':{'pitched_percussion':gain},'sample_sha256':sha256_file(path),
        'source_url':'https://freepats.zenvoid.org/Percussion/orchestral-percussion.html','license':'CC0 1.0',
        'scope':'Real recorded timpani hit arranged four times with virtual piano; not a mastered full song.'})
    prepare(folder/'case.json')
