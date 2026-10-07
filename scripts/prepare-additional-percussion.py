"""Build real bell and virtual mallet diagnostic mixes with exact references."""
from pathlib import Path
import zipfile
import subprocess
import numpy as np
import soundfile as sf
from music_analyzer.common import project_root,write_json,sha256_file
from music_analyzer.ground_truth import prepare

base=project_root()/'data/ground-truth'
source=base/'philharmonia'
selection={'bell_tree':'Percussion/bell tree/bell-tree__long_mezzo-forte_glissando.mp3',
           'cowbell':'Percussion/cowbell/cowbell__long_mezzo-forte_rhythm.mp3',
           'sleigh_bells':'Percussion/sleigh bells/sleigh-bells__long_mezzo-forte_shaken.mp3'}
with zipfile.ZipFile(source/'Percussion.zip') as archive:
    assert archive.testzip() is None
    for name,member in selection.items():
        target=source/(name+'.mp3');target.write_bytes(archive.read(member))
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(target),'-ar','44100','-ac','2','-c:a','pcm_f32le',str(source/(name+'.wav'))],check=True)
        audio,rate=sf.read(source/(name+'.wav'),dtype='float32',always_2d=True)
        padded=np.zeros((44100*15,2),np.float32)
        padded[:min(len(audio),len(padded))]=audio[:len(padded)]
        sf.write(source/(name+'-15s.wav'),padded,44100,subtype='FLOAT')
        write_json(source/(name+'-source.json'),{'url':'https://philharmonia.co.uk/resources/sound-samples/',
            'archive_sha256':sha256_file(source/'Percussion.zip'),'member':member,
            'license_note':'Free use; do not redistribute unmodified samples or sampler instruments.'})
references={'piano':['../../slakh/Track00020/stems/S03.wav'],
            'drums':['../../slakh/Track00020/stems/S00.wav'],
            'pitched_percussion':['../../slakh/Track00020/stems/S08.wav']}
for prefix,gain in [('',1),('quiet-',.1),('no-',0)]:
    folder=base/'cases'/('mallet-'+prefix+'94-109')
    write_json(folder/'case.json',{'name':folder.name,'start_sec':94,'duration_sec':15,
               'reference_sources':references,'reference_gains':{'pitched_percussion':gain},
               'dataset_url':'https://zenodo.org/records/4603870','license':'CC BY 4.0',
               'instrument_note':'GM Vibraphone label but actual plugin glockenspiel.nkm; 16kHz mono VST diagnostic.'})
    prepare(folder/'case.json')
for name in selection:
    folder=base/'cases'/('percussion-'+name)
    # Both sources start at zero; isolated piano is a known, contemporaneous counterexample.
    piano,_=sf.read(base/'cases/slakh20-pad-15-30/references/piano.wav',dtype='float32',always_2d=True)
    sf.write(source/'piano-15s.wav',piano,44100,subtype='FLOAT')
    write_json(folder/'case.json',{'name':folder.name,'start_sec':0,'duration_sec':15,
        'reference_sources':{'piano':['../../philharmonia/piano-15s.wav'],
                             'pitched_percussion':[f'../../philharmonia/{name}-15s.wav']},
        'dataset_url':'https://philharmonia.co.uk/resources/sound-samples/',
        'scope':'Artificial remix of real percussion recording plus virtual piano; no mastered-song quality claim.'})
    prepare(folder/'case.json')
