import numpy as np
import soundfile as sf
from music_analyzer.leakage_rule import apply


def test_absent_recovery_is_suppressed_and_returned_to_other(tmp_path):
    folder=tmp_path/'web'/'analysis_test';folder.mkdir(parents=True)
    def save(name,value):
        path=folder/(name+'.wav')
        sf.write(path,np.full((44100,2),value,dtype=np.float32),44100,subtype='FLOAT')
        return str(path.relative_to(tmp_path))
    tracks=[]
    for family in ('piano','synth','strings','brass','acoustic_guitar','guitar','bass','drums','other'):
        value=.03 if family in ('synth','strings') else (.00001 if family=='brass' else .1)
        tracks.append({'family':family,'path':save(family,value),'silent':False})
    mix=sum(sf.read(tmp_path/t['path'],dtype='float32',always_2d=True)[0].astype(np.float64) for t in tracks)
    sf.write(folder/'mix.wav',mix,44100,subtype='FLOAT')
    row={'id':'analysis_test','tracks':tracks,'instrumental':str((folder/'mix.wav').relative_to(tmp_path))}
    for family in ('synth','strings'):
        row[family+'_recovery']={'original_tracks':{family:{'path':save(family+'-raw',.00001)}}}
    result=apply(tmp_path,row)
    for track in result['tracks']:
        if track['family'] in ('brass','strings'):
            assert np.max(np.abs(sf.read(tmp_path/track['path'])[0]))==0
            assert 'silent' not in track
    synth=next(t for t in result['tracks'] if t['family']=='synth')
    assert synth['path']==next(t for t in row['tracks'] if t['family']=='synth')['path']
    np.testing.assert_allclose(sf.read(tmp_path/synth['path'])[0],.03,atol=1e-8)
    combined=sum(sf.read(tmp_path/t['path'])[0] for t in result['tracks'])
    np.testing.assert_allclose(combined,mix,atol=2e-7,rtol=0)
    assert all((tmp_path/t['path']).exists() for t in row['tracks'])
    assert apply(tmp_path,result) is result
