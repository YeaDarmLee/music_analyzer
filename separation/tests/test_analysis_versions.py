import io
import numpy as np
import pytest
import soundfile as sf
from music_analyzer.common import read_json, write_json
from music_analyzer.web_server import WebLibrary


@pytest.mark.parametrize('version,count,presets,recoveries',[
    ('basic_2',2,['vocal_roformer'],[]),
    ('basic_6',6,['vocal_roformer','instrument_roformer_6s'],[]),
    ('final_11',12,['vocal_roformer','bs_karaoke','instrument_roformer_6s','instrument_mega5','instrument_mega5'],['synth','strings','brass']),
])
def test_versions_run_only_required_stages_and_preserve_sum(tmp_path,monkeypatch,version,count,presets,recoveries):
    import music_analyzer.web_server as web
    import music_analyzer.synth_recovery as recovery
    calls=[]; recovered=[]; manifests={}
    upload=tmp_path/'source.wav'
    sf.write(upload,np.full((4410,2),.8,dtype=np.float32),44100,subtype='FLOAT')
    def ingest(path,root):
        folder=root/'inputs'/('asset_'+str(len(list((root/'inputs').glob('*'))) if (root/'inputs').exists() else 0))
        folder.mkdir(parents=True)
        audio,rate=sf.read(path,dtype='float32',always_2d=True)
        sf.write(folder/'canonical.wav',audio,rate,subtype='FLOAT')
        return folder
    class Service:
        def __init__(self,root):self.root=root
        def run(self,asset,preset,callback):
            if version=='final_11' and preset=='instrument_mega5':
                input_audio=sf.read(self.root/'inputs'/asset/'canonical.wav')[0]
                np.testing.assert_allclose(input_audio,.03 if calls.count(preset)==0 else .48,atol=1e-7)
            calls.append(preset);jid='job_'+format(len(calls),'032x')
            folder=self.root/'jobs'/jid/'result';folder.mkdir(parents=True)
            labels={'vocal_roformer':['vocals','instrumental'],'instrument_roformer_6s':['vocals','piano','guitar','bass','drums','other'],'instrument_mega5':['synth','bowed_strings','brass','acoustic-guitar','electric-guitar'],'bs_karaoke':['lead','backing']}[preset]
            values=[.2,.6] if preset=='vocal_roformer' else [.1,.1] if preset=='bs_karaoke' else [.03]*len(labels)
            stems=[]
            for label,value in zip(labels,values):
                path=folder/(label+'.wav');sf.write(path,np.full((4410,2),value,dtype=np.float32),44100,subtype='FLOAT')
                stems.append({'family':label,'path':path.name})
            manifests[str(folder)]={'stems':stems}
            return {'job_id':jid,'state':'SUCCEEDED'}
    monkeypatch.setattr(web,'JobService',Service)
    monkeypatch.setattr(web,'ingest_file',ingest)
    monkeypatch.setattr(web,'load_asset',lambda *args:{'timeline':{'num_frames':4410}})
    monkeypatch.setattr(web,'verify_result',lambda folder,job:manifests[str(folder)])
    def recover(library,row,family,on_progress):
        recovered.append(family)
        for track in row['tracks']:
            if track['family'] in (family,'other'):
                path=library.root/track['path']
                audio,rate=sf.read(path,dtype='float32',always_2d=True)
                sf.write(path,audio+(.01 if track['family']==family else -.01),rate,subtype='FLOAT')
        return row
    monkeypatch.setattr(recovery,'run_for_library',recover)
    library=WebLibrary(tmp_path)
    try:
        folder=library.web/('analysis_'+'a'*32);folder.mkdir()
        row={'id':folder.name,'model':version,'progress':0,'job_ids':[]}
        library.analyze(folder,upload,row)
        result=read_json(folder/'record.json')
        assert result['state']=='SUCCEEDED',result.get('error')
        assert result['processing_seconds']>0
        assert result['timing_profile']=='staged-v8-overlap40'
        assert len(result['tracks'])==count
        assert calls==presets and recovered==recoveries
        if version=='final_11':
            other=next(t for t in result['tracks'] if t['family']=='other')
            assert other['path'].endswith('remaining-final11-v3.wav')
            np.testing.assert_allclose(sf.read(tmp_path/other['path'])[0],.36,atol=1e-7)
            residual=next(t for t in result['tracks'] if t['family']=='guitar_residual')
            np.testing.assert_allclose(sf.read(tmp_path/residual['path'])[0],-.03,atol=1e-7)
        if version=='basic_6':
            guitar=next(t for t in result['tracks'] if t['family']=='guitar')
            assert guitar['display_name']=='기타'
        target=result['original'] if version=='basic_2' else result['instrumental']
        excluded=() if version=='basic_2' else ('vocals','lead','backing')
        library.validate_partition(target,[t for t in result['tracks'] if t['family'] not in excluded])
    finally:library.executor.shutdown()


def test_brass_recovery_returns_estimate_to_brass_and_preserves_total(tmp_path):
    from music_analyzer.synth_recovery import settings,apply
    from music_analyzer.common import sha256_file
    folder=tmp_path/'web/analysis_test';folder.mkdir(parents=True)
    tracks=[]
    for family,value in [('brass',.1),('other',.3),('synth',.2),('guitar_residual',.05)]:
        path=folder/(family+'.wav');sf.write(path,np.full((4410,2),value,dtype=np.float32),44100,subtype='FLOAT')
        tracks.append({'family':family,'path':str(path.relative_to(tmp_path)),'sha256':sha256_file(path)})
    estimate=folder/'estimate.wav';sf.write(estimate,np.full((4410,2),.04,dtype=np.float32),44100,subtype='FLOAT')
    _,positive,negative,_=settings('brass')
    manifest=folder/'manifest.json'
    write_json(manifest,{'case':{'input_sha256':tracks[1]['sha256']},'results':{'part_b':{'positive':positive,'negative':negative,'sha256':sha256_file(estimate)}}})
    instrumental=folder/'instrumental.wav'
    sf.write(instrumental,np.full((4410,2),.65,dtype=np.float32),44100,subtype='FLOAT')
    result=apply(tmp_path,{'id':'analysis_test','tracks':tracks,'instrumental':str(instrumental.relative_to(tmp_path))},estimate,manifest,'brass')
    assert result['tracks'][2]==tracks[2]
    arrays={t['family']:sf.read(tmp_path/t['path'],dtype='float32')[0] for t in result['tracks']}
    np.testing.assert_allclose(arrays['brass'],.14,atol=1e-7)
    np.testing.assert_allclose(sum(arrays.values()),.65,atol=1e-7)
    np.testing.assert_allclose(arrays['guitar_residual'],.05,atol=1e-7)
