"""Validate paired controls, save a compact snapshot and build a listening index."""
import html
from pathlib import Path
import numpy as np
import soundfile as sf

from music_analyzer.common import project_root,read_json,write_json

project = project_root()
root = project/'data/ground-truth/cases'
cases = []
for track,label,target,start in [('20','pad','synth',15),('16','brass','brass',60)]:
    group = [root/f'slakh{track}-{prefix}{label}-{start}-{start+15}' for prefix in ('','quiet-','no-')]
    prepared = [read_json(folder/'prepared.json') for folder in group]
    for family in prepared[0]['references']:
        arrays = [sf.read(p['references'][family]['path'],dtype='float32',always_2d=True)[0] for p in prepared]
        if family == target:
            np.testing.assert_array_equal(arrays[1],arrays[0]*np.float32(.1))
            assert not np.any(arrays[2]), 'Absent reference must be exactly zero'
        else:
            np.testing.assert_array_equal(arrays[0],arrays[1])
            np.testing.assert_array_equal(arrays[0],arrays[2])
    for folder in group:
        run = read_json(folder/'run.json')
        row = read_json(Path(run['root'])/'web'/run['id']/'record.json')
        assert row['state']=='SUCCEEDED'
        report = read_json(folder/'report.json')
        metrics = {}
        for family,m in report['metrics'].items():
            metrics[family] = {key:m[key] for key in ('reference_rms','raw_sdr_db','target_gain','output_to_mix_db','error_rms')}
            metrics[family]['without_recovery'] = {key:m['without_recovery'][key] for key in metrics[family]}
        cases.append({'case':report['case'],'target':target,'target_gain_setting':prepared[group.index(folder)]['reference_gains'][target],
                      'processing_seconds':report['processing_seconds'],'input_sha256':read_json(folder/'prepared.json')['input_sha256'],
                      'candidate_partition_max_abs_error':report['candidate_partition_max_abs_error'],
                      'metrics':metrics,'guitar_stage_scores':report['guitar_stage_scores']})
write_json(project/'docs/TWELVE_TRACK_CONTROLLED_RESULTS.json',{
    'date':'2026-10-07','pipeline_baseline_commit':'ee9c333','dataset':'BabySlakh 16kHz mono',
    'archive_md5':'311096dc2bde7d61c97e930edbfc7f78','paired_reference_controls_verified':True,'cases':cases})
labels = ['신디 정상','신디 20dB 감쇠','신디 제거','브라스 정상','브라스 20dB 감쇠','브라스 제거']
rows = []
fmt = lambda value: '—' if value is None else f'{value:.2f}'
for label,r in zip(labels,cases):
    m = r['metrics'][r['target']]
    rows.append('<tr><td><a href="'+html.escape(r['case'])+'/comparison.html">'+label+'</a></td>'
                '<td>'+fmt(m['without_recovery']['raw_sdr_db'])+'</td><td>'+fmt(m['raw_sdr_db'])+'</td>'
                '<td>'+fmt(m['target_gain'])+'</td><td>'+fmt(m['output_to_mix_db'])+'</td></tr>')
previous = ''.join('<li><a href="'+name+'/comparison.html">'+name+'</a></li>' for name in
                   ('phoenix-30-50','rainfall-40-60','rainfall-guitars-only-40-60'))
(root/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>12트랙 테스트</title>'
    '<style>body{font:16px system-ui;max-width:960px;margin:40px auto;padding:20px;background:#111;color:#eee}'
    'a{color:#9fd9ff}table{width:100%;border-collapse:collapse}td,th{padding:14px;text-align:left;border-bottom:1px solid #444}</style>'
    '<h1>12트랙 정답 비교 · 9개 테스트</h1><p>새 6개 테스트는 16kHz mono 가상악기 stem의 통제 실험입니다. 실제 녹음의 음질 평가와 구분해 보세요.</p>'
    '<p>SDR은 높을수록 정답에 가깝습니다. 정답이 없는 조건은 SDR 대신 원곡 대비 출력량을 봅니다. 목표 gain은 파형 투영 계수이며 음악 보존 비율을 뜻하지 않습니다.</p>'
    '<table><thead><tr><th>청취 비교</th><th>보완 전 SDR</th><th>현재 SDR</th><th>현재 목표 gain</th><th>출력/원곡 dB</th></tr></thead><tbody>'
    +''.join(rows)+'</tbody></table><h2>실제 녹음 stem 테스트</h2><ul>'+previous+'</ul>',encoding='utf-8')
print('SIX PAIRED CONTROLS VERIFIED; snapshot and listening index saved',flush=True)
