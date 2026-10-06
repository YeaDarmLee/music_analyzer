import numpy as np
import pytest
from music_analyzer.ground_truth import score


def test_reference_metrics_detect_gain_loss_and_false_output():
    t = np.arange(44100)/44100
    target = np.column_stack([.1*np.sin(2*np.pi*440*t)]*2)
    interference = np.column_stack([.1*np.sin(2*np.pi*770*t)]*2)
    mix = target+interference
    correct = score(target,target,mix)
    reduced = score(target,target*.1,mix)
    leaked = score(target,target+interference,mix)
    absent = score(np.zeros_like(target),interference,mix)
    assert correct['raw_sdr_db'] > leaked['raw_sdr_db']
    assert reduced['target_gain'] == pytest.approx(.1)
    assert absent['reference_absent'] and absent['raw_sdr_db'] is None
    assert absent['output_to_mix_db'] == pytest.approx(-3.0103,abs=1e-4)
    quiet = score(target*.001,target*.0001,mix)
    assert quiet['target_gain'] == pytest.approx(.1)
    assert quiet['error_rms'] > 0
    silence = np.zeros_like(target)
    assert score(silence,silence,silence)['output_to_mix_db'] is None
    with pytest.raises(ValueError):
        score(target,target[:-1],mix)


def test_native_sources_and_quiet_control_keep_the_same_reference_mix(tmp_path):
    import soundfile as sf
    from music_analyzer.common import write_json,read_json
    from music_analyzer.ground_truth import prepare
    signal = (.1*np.sin(2*np.pi*440*np.arange(16000)/16000)).astype(np.float32)
    sf.write(tmp_path/'source.wav',signal,16000,subtype='FLOAT')
    case = tmp_path/'case.json'
    write_json(case,{'start_sec':0,'duration_sec':1,'reference_sources':{'synth':['source.wav']},
                     'reference_gains':{'synth':.1}})
    prepare(case)
    mix,rate = sf.read(tmp_path/'mix.wav',dtype='float32',always_2d=True)
    ref,_ = sf.read(tmp_path/'references/synth.wav',dtype='float32',always_2d=True)
    assert rate==44100 and mix.shape==(44100,2)
    np.testing.assert_array_equal(mix,ref)
    np.testing.assert_array_equal(mix[:,0],mix[:,1])
    assert np.max(np.abs(mix)) == pytest.approx(.01,rel=.02)
    assert read_json(tmp_path/'prepared.json')['sources'][0]['native_rate']==16000


def test_evaluation_rejects_new_mix_against_an_old_analysis(tmp_path):
    import soundfile as sf
    from music_analyzer.common import write_json,sha256_file
    from music_analyzer.ground_truth import evaluate
    root = tmp_path/'library'
    root.mkdir()
    sf.write(root/'original.wav',np.full((44100,2),.1,np.float32),44100,subtype='FLOAT')
    mixture = tmp_path/'mix.wav'
    sf.write(mixture,np.full((44100,2),.2,np.float32),44100,subtype='FLOAT')
    write_json(tmp_path/'prepared.json',{'input':str(mixture),'input_sha256':sha256_file(mixture)})
    with pytest.raises(ValueError,match='audio actually analyzed'):
        evaluate(tmp_path,root,{'original':'original.wav'})
