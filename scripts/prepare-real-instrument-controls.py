"""Known real instrument recordings mixed with virtual piano; paired gain controls."""
import io
import zipfile
import subprocess
import numpy as np
import soundfile as sf
from music_analyzer.common import project_root,write_json,sha256_file
from music_analyzer.ground_truth import prepare

base=project_root()/'data/ground-truth';source=base/'philharmonia'
selection={'strings':('violin','violin_A3_15_forte_arco-normal.mp3'),
           'brass':('trumpet','trumpet_A3_15_forte_normal.mp3')}
with zipfile.ZipFile(source/'all-samples.zip') as outer:
    assert outer.testzip() is None
    for family,(instrument,member) in selection.items():
        with zipfile.ZipFile(io.BytesIO(outer.read('all-samples/'+instrument+'.zip'))) as inner:
            target=source/(family+'.mp3');target.write_bytes(inner.read(member))
        decoded=source/(family+'-decoded.wav')
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(target),'-ar','44100','-ac','2','-c:a','pcm_f32le',str(decoded)],check=True)
        audio,_=sf.read(decoded,dtype='float32',always_2d=True)
        prepared=np.zeros((15*44100,2),np.float32)
        prepared[:min(len(audio),len(prepared))]=audio[:len(prepared)]
        sf.write(source/(family+'-15s.wav'),prepared,44100,subtype='FLOAT')
        for prefix,gain in [('',1),('quiet-',.1),('no-',0)]:
            folder=base/'cases'/('real-'+prefix+family)
            write_json(folder/'case.json',{'name':folder.name,'start_sec':0,'duration_sec':15,
                'reference_sources':{'piano':['../../philharmonia/piano-15s.wav'],family:[f'../../philharmonia/{family}-15s.wav']},
                'reference_gains':{family:gain},'sample_member':member,'archive_sha256':sha256_file(source/'all-samples.zip'),
                'source_url':'https://philharmonia.co.uk/resources/sound-samples/',
                'scope':'Single real-instrument note plus virtual piano remix; not full-song generalization.'})
            prepare(folder/'case.json')
