import numpy as np
import pytest
import soundfile as sf
from music_analyzer.common import write_json, sha256_file
from music_analyzer.synth_recovery import apply, POSITIVE, NEGATIVE

def fixture(tmp_path):
    folder=tmp_path/'web/analysis_test';folder.mkdir(parents=True)
    tracks=[]
    for family,value in [('synth',.1),('other',.2),('guitar',.3)]:
        path=folder/(family+'.wav')
        sf.write(path,np.full((4410,2),value,dtype=np.float32),44100,subtype='FLOAT')
        tracks.append({'family':family,'path':str(path.relative_to(tmp_path)),'sha256':sha256_file(path)})
    estimate=folder/'estimate.wav'
    sf.write(estimate,np.full((4410,2),.04,dtype=np.float32),44100,subtype='FLOAT')
    manifest=folder/'manifest.json'
    write_json(manifest,{'case':{'input_sha256':tracks[1]['sha256']},'results':{'part_b':{
        'positive':POSITIVE,'negative':NEGATIVE,'sha256':sha256_file(estimate)}}})
    return {'id':'analysis_test','tracks':tracks},estimate,manifest

def test_recovery_preserves_sum_other_tracks_and_is_idempotent(tmp_path):
    row,estimate,manifest=fixture(tmp_path)
    result=apply(tmp_path,row,estimate,manifest)
    arrays=[sf.read(tmp_path/t['path'],dtype='float32')[0] for t in result['tracks'][:2]]
    np.testing.assert_allclose(arrays[0]+arrays[1],.3,atol=1e-7)
    assert result['tracks'][2]==row['tracks'][2]
    assert (tmp_path/'web/analysis_test/record-before-synth-recovery-v1.json').exists()
    assert apply(tmp_path,result,estimate,manifest)==result

def test_changed_input_or_wrong_timeline_is_rejected(tmp_path):
    row,estimate,manifest=fixture(tmp_path)
    sf.write(tmp_path/row['tracks'][1]['path'],np.zeros((4410,2)),44100,subtype='FLOAT')
    with pytest.raises(ValueError,match='input changed'):apply(tmp_path,row,estimate,manifest)
