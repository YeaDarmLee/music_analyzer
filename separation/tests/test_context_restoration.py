import numpy as np
import pytest
from music_analyzer.instrumental_restoration import restore
from music_analyzer.percussion_refinement import transfer


def tone(hz,gain=.1):
    t=np.arange(16384)/44100
    return np.repeat((gain*np.sin(2*np.pi*hz*t))[:,None],2,axis=1).astype('float32')


def test_restoration_preserves_sum_and_quiet_independent_voice():
    voice=tone(441,.001);strings=tone(3101,.1)
    vocals=voice+strings
    after,instrumental,moved=restore(vocals,np.zeros_like(vocals),[strings,strings])
    np.testing.assert_allclose(after+instrumental,vocals,atol=2e-8)
    assert np.linalg.norm(after-voice)<np.linalg.norm(vocals-voice)*.1
    # Quiet real voice must survive while the instrumental leakage is removed.
    gain=np.sum(after*voice)/np.sum(voice**2)
    assert .98<gain<1.02


def test_empty_evidence_keeps_performance_exactly():
    voice=tone(441)
    after,instrumental,moved=restore(voice,voice*.2,[np.zeros_like(voice)])
    np.testing.assert_array_equal(after,voice)
    np.testing.assert_array_equal(instrumental,voice*.2)
    assert not moved.any()


def test_percussion_heads_do_not_double_count_and_preserve_other_instrument():
    drums=tone(901);mallet=tone(3101);piano=tone(441)
    after_drums,other,percussion=transfer(drums,piano+mallet,mallet,mallet)
    np.testing.assert_allclose(after_drums+other+percussion,drums+piano+mallet,atol=5e-8)
    gain=np.sum(percussion*mallet)/np.sum(mallet**2)
    assert .95<gain<1.05
    assert np.linalg.norm(other-piano)<np.linalg.norm(mallet)*.1
    single=transfer(drums,piano+mallet,mallet)[2]
    np.testing.assert_array_equal(single,percussion)


@pytest.mark.parametrize('bad',[np.zeros((10,2)),np.full((16384,2),np.nan)])
def test_bad_timelines_are_rejected(bad):
    good=tone(441)
    with pytest.raises(ValueError):restore(good,good,[bad])
    with pytest.raises(ValueError):transfer(good,good,bad)


def test_published_percussion_preserves_original_files_and_is_idempotent(tmp_path):
    import soundfile as sf
    from music_analyzer.common import sha256_file
    from music_analyzer.percussion_refinement import apply
    folder=tmp_path/'web/analysis_test';folder.mkdir(parents=True)
    tracks=[]
    for f,audio in [('drums',tone(901)),('other',tone(441)+tone(3101)),('piano',tone(2001))]:
        path=folder/(f+'.wav');sf.write(path,audio,44100,subtype='FLOAT')
        tracks.append({'family':f,'path':str(path.relative_to(tmp_path)),'sha256':sha256_file(path)})
    estimate=folder/'evidence.wav';sf.write(estimate,tone(3101),44100,subtype='FLOAT')
    row={'id':'analysis_test','tracks':tracks}
    updated=apply(tmp_path,row,estimate,'context_job',additional=(estimate,))
    assert len(updated['tracks'])==4
    assert updated['tracks'][2]==tracks[2]
    assert updated['percussion_refinement']['context_job_id']=='context_job'
    assert apply(tmp_path,updated,estimate,'context_job')==updated
    with pytest.raises(ValueError,match='original unrefined'):
        apply(tmp_path,updated,estimate,'context_job',version='context-supported-percussion-v2')
    assert all(sha256_file(tmp_path/t['path'])==t['sha256'] for t in tracks)
    before=sum(sf.read(tmp_path/t['path'],dtype='float32')[0] for t in tracks)
    after=sum(sf.read(tmp_path/t['path'],dtype='float32')[0] for t in updated['tracks'])
    np.testing.assert_allclose(after,before,atol=5e-8)


def test_restoration_does_not_mutate_verified_manifests_or_job_files(tmp_path):
    import copy
    import soundfile as sf
    from music_analyzer.instrumental_restoration import apply
    from music_analyzer.common import sha256_file
    first_dir=tmp_path/'jobs/first/result';first_dir.mkdir(parents=True)
    context_dir=tmp_path/'jobs/context/result';context_dir.mkdir(parents=True)
    first={'stems':[]};context={'stems':[]}
    for f,audio in [('vocals',tone(441)+tone(3101)),('instrumental',tone(901))]:
        path=first_dir/(f+'.wav');sf.write(path,audio,44100,subtype='FLOAT')
        first['stems'].append({'family':f,'path':path.name,'sha256':sha256_file(path)})
    for f in ['bowed_strings','brass','synth']:
        path=context_dir/(f+'.wav');sf.write(path,tone(3101) if f=='bowed_strings' else tone(3101,0),44100,subtype='FLOAT')
        context['stems'].append({'family':f,'path':path.name})
    snapshot=copy.deepcopy(first)
    row,revised=apply(tmp_path,{'id':'analysis_test'},first_dir,first,context_dir,context)
    assert first==snapshot
    assert all(sha256_file(first_dir/t['path'])==t['sha256'] for t in first['stems'])
    assert all(sha256_file(first_dir/t['path'])==t['sha256'] for t in revised['stems'])
    assert row['vocal_instrument_restoration']['moved_rms']>0


def test_percussion_source_keeps_quiet_and_over_full_scale_samples(tmp_path):
    import soundfile as sf
    from music_analyzer.percussion_refinement import prepare_source
    folder=tmp_path/'web/analysis_test';folder.mkdir(parents=True)
    drums=tone(441,1.2);quiet=tone(3101,1e-5);tracks=[]
    for f,a in [('drums',drums),('other',quiet)]:
        p=folder/(f+'.wav');sf.write(p,a,44100,subtype='FLOAT')
        tracks.append({'family':f,'path':str(p.relative_to(tmp_path))})
    path=prepare_source(tmp_path,{'id':'analysis_test','tracks':tracks})
    actual,rate=sf.read(path,dtype='float32',always_2d=True)
    assert rate==44100 and np.abs(actual).max()>1
    np.testing.assert_array_equal(actual,drums+quiet)
