"""Replay the changed final assembly using cached, real model outputs; no GPU rerun."""
import contextlib
import io
import shutil
import uuid
from pathlib import Path
import numpy as np
import soundfile as sf
from music_analyzer.common import project_root, read_json, write_json
from music_analyzer.web_server import WebLibrary
from music_analyzer.ground_truth import evaluate

cases = project_root()/'data/ground-truth/cases'
summary = []
for case in sorted(cases.iterdir()):
    if not (case/'run.json').exists():
        continue
    execution = read_json(case/'run.json')
    root = Path(execution['root'])
    old = read_json(root/'web'/execution['id']/'record.json')
    if not all(family+'_recovery' in old for family in ('synth','strings','brass')):continue
    assert old['state']=='SUCCEEDED'
    tracks = {t['family']:dict(t) for t in old['tracks']}
    for family in ('synth','strings','brass'):
        tracks[family] = dict(old[family+'_recovery']['original_tracks'][family])
    tracks.pop('other')
    for source, target in (('strings','bowed_strings'),('acoustic_guitar','acoustic-guitar'),('guitar','electric-guitar')):
        tracks[source]['family'] = target
    row = {k:v for k,v in old.items() if not k.endswith('_recovery')}
    row.update(id='analysis_'+uuid.uuid4().hex, tracks=list(tracks.values()),
               separation_version='staged-guitar-residual-v9', recovery_policy='base-estimates-only-v1',
               verification_method='cached-model-output-final-assembly', source_analysis=old['id'])
    library = WebLibrary(root)
    try:
        row = library.final_session(row)
        selected = [t for t in row['tracks'] if t['family']!='other']
        row = library.with_remaining(row,selected,'flat_v4','remaining-final11-v3.wav',row['instrumental'],
                                    [t for t in selected if t['family'] not in ('lead','backing')])
        library.validate_partition(row['instrumental'],[t for t in row['tracks'] if t['family'] not in ('lead','backing')])
        assert len(row['tracks'])==12
        maximum = 0.
        for track in row['tracks']:
            actual = sf.read(root/track['path'],dtype='float32',always_2d=True)[0]
            expected = sf.read(case/'without-recovery'/(track['family']+'.wav'),dtype='float32',always_2d=True)[0]
            maximum = max(maximum,float(np.max(np.abs(actual-expected))))
        assert maximum < 2e-6
        write_json(root/'web'/row['id']/'record.json',row)
    finally:
        library.executor.shutdown()
    folder = case/'v9'
    folder.mkdir(exist_ok=True)
    shutil.copyfile(case/'prepared.json',folder/'prepared.json')
    shutil.copyfile(case/'mix.wav',folder/'mix.wav')
    write_json(folder/'run.json',{'root':str(root),'id':row['id']})
    with contextlib.redirect_stdout(io.StringIO()):
        result = evaluate(folder,root,row)
    summary.append({'case':case.name,'max_difference_from_tested_candidate':maximum,
                    'method':row['verification_method'],'report':str(folder/'report.json')})
    print(case.name,'PASS',maximum,flush=True)
write_json(project_root()/'docs/TWELVE_TRACK_V9_VERIFICATION.json',summary)
(cases/'v9.html').write_text('<!doctype html><meta charset="utf-8"><title>12트랙 v9 검증</title>'
    '<h1>12트랙 v9 검증</h1><p>자동 잔여음 보완 제거 · 기존 모델 출력으로 최종 조립 재검증</p>'
    '<p>각 페이지의 현재 결과는 v9입니다. 이전 결과는 기존 테스트 목록에서 비교할 수 있습니다.</p>'
    '<a href="index.html">이전 결과 목록</a><ul>'
    +''.join(f'<li><a href="{item["case"]}/v9/comparison.html">{item["case"]}</a></li>' for item in summary)
    +'</ul>',encoding='utf-8')
