"""Score both text candidates against the same piano and drum references."""
import numpy as np
import soundfile as sf
from scipy import signal
from music_analyzer.common import project_root,read_json,write_json
from music_analyzer.ground_truth import score
from music_analyzer.piano_drum_refinement import cymbal_extract
import argparse

parser=argparse.ArgumentParser()
parser.add_argument('--protected',action='store_true')
args=parser.parse_args()

base=project_root()/'data/ground-truth/cases'
study=base/'piano-cymbal-text-study'
results=[]
for folder in sorted(study.iterdir()):
    if not (folder/'manifest.json').exists():continue
    piano=sf.read(base/'piano-drum-context-study'/folder.name/'piano-before.wav',dtype='float32',always_2d=True)[0]
    if folder.name=='millsage-0-20':
        target=None; mix=piano
    elif folder.name.startswith('piano-only-'):
        target=piano;mix=piano
    else:
        prepared=read_json(base/folder.name/'prepared.json')
        mix=sf.read(prepared['input'],dtype='float32',always_2d=True)[0]
        target=np.zeros_like(piano)
        if 'piano' in prepared['references']:
            target=sf.read(prepared['references']['piano']['path'],dtype='float32',always_2d=True)[0]
    for query in ('part_a','part_b'):
        removed=sf.read(folder/(query+'.wav'),dtype='float32',always_2d=True)[0]
        if args.protected:removed=cymbal_extract(piano,removed)
        after=piano-removed
        suffix='-protected' if args.protected else ''
        sf.write(folder/(query+suffix+'-piano-after.wav'),after,44100,subtype='FLOAT')
        sf.write(folder/(query+suffix+'-moved.wav'),removed,44100,subtype='FLOAT')
        item={'case':folder.name,'query':query,'removed_rms':float(np.sqrt(np.mean(removed.astype(float)**2)))}
        if target is not None:
            item.update(before=score(target,piano,mix),after=score(target,after,mix))
        else:
            band=signal.butter(4,4000,fs=44100,btype='highpass',output='sos')
            before_high=signal.sosfiltfilt(band,piano[5*44100:10*44100],axis=0)
            after_high=signal.sosfiltfilt(band,after[5*44100:10*44100],axis=0)
            item['high_frequency_change_db']=float(10*np.log10(np.sum(after_high**2)/np.sum(before_high**2)))
        results.append(item)
        print(folder.name,query,item.get('high_frequency_change_db'),
              (item.get('before',{}).get('raw_sdr_db'),item.get('after',{}).get('raw_sdr_db')),flush=True)
write_json(study/('protected-report.json' if args.protected else 'report.json'),results)
