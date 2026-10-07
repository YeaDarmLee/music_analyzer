import numpy as np
import pytest
from music_analyzer.piano_drum_refinement import extract


def test_cymbal_transfer_keeps_other_tracks_backups_sum_and_provenance(tmp_path):
    import soundfile as sf
    from music_analyzer.common import write_json,sha256_file
    from music_analyzer.synth_recovery import settings,apply
    folder=tmp_path/'web/analysis_test';folder.mkdir(parents=True)
    t=np.arange(44100)/44100
    piano=np.column_stack([.1*np.sin(2*np.pi*440*t)]*2).astype(np.float32)
    rng=np.random.default_rng(13)
    cymbal=(rng.normal(0,.02,piano.shape)).astype(np.float32)
    tracks=[]
    for family,audio in [('piano',piano+cymbal),('drums',cymbal),('other',piano*.1)]:
        path=folder/(family+'.wav');sf.write(path,audio,44100,subtype='FLOAT')
        tracks.append({'family':family,'path':str(path.relative_to(tmp_path)),'sha256':sha256_file(path)})
    estimate=folder/'estimate.wav';sf.write(estimate,cymbal,44100,subtype='FLOAT')
    _,positive,negative,_=settings('cymbal')
    manifest=folder/'manifest.json'
    write_json(manifest,{'case':{'input_sha256':tracks[0]['sha256']},'results':{'part_b':{'positive':positive,'negative':negative,'sha256':sha256_file(estimate)}}})
    row={'id':'analysis_test','tracks':tracks}
    revised=apply(tmp_path,row,estimate,manifest,'cymbal')
    assert revised['tracks'][2]==tracks[2]
    assert revised['cymbal_recovery']['moved_rms']>0
    original=sum(sf.read(tmp_path/t['path'],dtype='float32')[0] for t in tracks)
    actual=sum(sf.read(tmp_path/t['path'],dtype='float32')[0] for t in revised['tracks'])
    np.testing.assert_allclose(actual,original,atol=3e-8)
    assert apply(tmp_path,revised,estimate,manifest,'cymbal')==revised
    assert (folder/'record-before-cymbal-recovery-v1.json').exists()
    sf.write(estimate,cymbal*.1,44100,subtype='FLOAT')
    with pytest.raises(ValueError,match='provenance'):apply(tmp_path,row,estimate,manifest,'cymbal')


def test_harmonic_protection_keeps_a_high_piano_harmonic():
    from music_analyzer.piano_drum_refinement import cymbal_extract
    t=np.arange(44100)/44100
    piano=np.column_stack([.1*np.sin(2*np.pi*6000*t)]*2).astype(np.float32)
    # Even a wrong semantic estimate matching the whole tone must retain its harmonic structure.
    moved=cymbal_extract(piano,piano)
    assert np.sqrt(np.mean(moved[8192:-8192]**2))<1e-5


def test_contextual_mask_removes_drum_band_and_preserves_piano_and_sum():
    t=np.arange(44100)/44100
    piano=np.column_stack([.1*np.sin(2*np.pi*440*t)]*2).astype(np.float32)
    drum=np.column_stack([.03*np.sin(2*np.pi*7000*t)]*2).astype(np.float32)
    contaminated=piano+drum
    removed=extract(contaminated,{'drums':drum,'other':piano})
    revised=contaminated-removed
    assert np.sqrt(np.mean((revised[2048:-2048]-piano[2048:-2048])**2))<1e-5
    np.testing.assert_allclose(revised+(drum+removed),contaminated+drum,atol=3e-8)
    np.testing.assert_array_equal(extract(piano,{'drums':np.zeros_like(piano),'other':piano}),np.zeros_like(piano))


def test_bad_estimates_are_rejected():
    piano=np.zeros((44100,2),np.float32)
    with pytest.raises(ValueError):extract(piano,{'other':piano})
    with pytest.raises(ValueError):extract(piano,{'drums':piano[:-1]})
    with pytest.raises(ValueError):extract(piano,{'drums':piano+np.nan})
