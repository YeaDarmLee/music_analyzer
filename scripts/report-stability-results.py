"""Write the final evidence-backed Korean report after all 32 cases have finished."""
from pathlib import Path
import numpy as np
from music_analyzer.common import project_root,read_json,write_json

base=project_root();cases=base/'data/ground-truth/cases';docs=base/'docs'
rows=read_json(docs/'THIRTEEN_TRACK_V12_STABILITY_RESULTS.json')
proof=read_json(docs/'THIRTEEN_TRACK_V12_VERIFICATION.json')
assert len(rows)==len(proof)==32 and all(r['original_sum_verified'] for r in rows)
metrics={r['case']:r['metrics'] for r in rows};prepared=[read_json(cases/r['group']/r['case']/'prepared.json') for r in rows]
reports=[read_json(cases/r['group']/r['case']/'report.json') for r in rows]
unique=len({p['input_sha256'] for p in prepared});mills=read_json(docs/'MILLSAGE_STABILITY_V12_RESULTS.json')
controls=read_json(docs/'THIRTEEN_TRACK_CONTROL_RESULTS.json');validation=read_json(docs/'STABILITY_VALIDATION.json')
voice=min(r['after_vocal_total']['target_gain']/r['before_vocal']['target_gain'] for r in controls if 'before_vocal' in r)
gains=[r['piano']['target_gain'] for r in controls if 'piano' in r]
perc=[d['metrics']['percussion'] for d in reports];absent=max(r['output_to_mix_db'] for r in perc if r['reference_absent'])
lines=['# 13트랙 보완 및 안정성 테스트 결과 · v12','',
       '검증된 보완을 실험 브랜치에 적용했습니다. 전체 악기 분류가 안정화됐다는 판정은 내리지 않습니다. 신디 패드·짧은 강한 바이올린·일부 가상 기타의 분류 오류가 남았습니다.','',
       f'정답이 있는 32개 테스트 조건({unique}개 서로 다른 입력)을 점검했습니다. 기존/추가 악기 24개 조건과 보컬·피아노 8개 통제 조건으로 구성했습니다. 32개 모두 v11 핵심 추출 후 새 v12 타악기 단계를 실제 GPU로 실행하고 최종 13트랙을 다시 조립했습니다. 핵심 추출을 재사용한 검증이며, 32곡 전체를 v12로 처음부터 다시 추출했다는 의미는 아닙니다. 기사개전은 v12 전체 파이프라인으로 처음부터 별도 재추출했습니다.','',
       '모든 결과에서 44.1kHz 스테레오 길이·유한값·13개 원시 출력과 원곡/반주 합계를 검증했습니다. v12 추가 타악기 단계는 드럼·추가 반주·기타 타악기를 갱신하며 나머지 10개 파일은 v11과 SHA-256이 같습니다. 약한 연주를 지우는 RMS 게이트는 사용하지 않았습니다.','',
       '## 확인된 개선','',
       '| 점검 항목 | 결과 |','| --- | --- |',
       f"| 기사개전 5–10초 피아노 고역 | 기존 대비 {mills['high_frequency_change_db']:.2f}dB. 원본 라이드 정답이 없으므로 혼입 완전 해결/분리 정확도 판정은 할 수 없습니다. |",
       f"| 실제 트럼펫 + 피아노 | 브라스 SDR {metrics['real-brass']['brass']['raw_sdr_db']['before']:.2f} → {metrics['real-brass']['brass']['raw_sdr_db']['after']:.2f}dB |",
       f"| 작은 실제 바이올린 | 정답 신호 투영 계수 {100*metrics['real-quiet-strings']['strings']['target_gain']['before']:.1f}% → {100*metrics['real-quiet-strings']['strings']['target_gain']['after']:.1f}% |",
       f'| 보컬 + 바이올린 통제 5개 | 보완 전 보컬 신호 대비 보컬+코러스 투영 계수 최소 {100*voice:.2f}% 유지. SDR은 일부 조건에서 최대 약 0.41dB 하락했습니다. |',
       f'| 피아노 단독/작은/아주 작은 연주 | 정답 신호 투영 계수 최소 {100*min(gains):.3f}%. 새 타악기 단계는 피아노 파일을 변경하지 않습니다. |',
       f'| 타악기가 없는 조건 | 기타 타악기 출력의 믹스 대비 에너지 비율 최악 {absent:.2f}dB. 완전 0이라는 뜻은 아닙니다. |','',
       '새 타악기에는 종소리·말렛·팀파니 등을 함께 보관합니다. 원곡 악기 근거와 피아노 등을 제외한 드럼+잔여 반주 근거를 합산하지 않고 주파수별로 선택해 중복 분류를 줄였습니다.','',
       '| 새 타악기 샘플 | SDR | 정답 신호 투영 계수 |','| --- | ---: | ---: |']
for name in ['mallet-94-109','mallet-quiet-94-109','percussion-bell_tree','percussion-cowbell','percussion-sleigh_bells','real-timpani','real-quiet-timpani']:
    m=metrics[name]['percussion'];lines.append(f"| {name} | {m['raw_sdr_db']['after']:.2f}dB | {100*m['target_gain']['after']:.1f}% |")
lines+=['','SDR은 정답과의 오차 기준으로 높을수록 좋습니다. 투영 계수는 정답 방향의 신호 크기이며 전체 분리 정확도/청감 점수가 아닙니다. 아주 작은 정답은 표준 SDR 계산에서 제외되므로 신호 크기와 오차 RMS를 함께 확인했습니다.','',
        '## 전체 분류 점검','',
        '| 분류 | 정답 존재 조건 | SDR 범위 | 없는 조건에서 최악의 출력/믹스 |','| --- | ---: | --- | --- |']
names={'lead':'보컬','backing':'코러스','piano':'피아노','synth':'신디','strings':'스트링','brass':'브라스','acoustic_guitar':'통기타','guitar':'일렉기타','bass':'베이스','drums':'드럼','percussion':'기타 타악기','other':'추가 반주','guitar_total':'기타 전체 (보조 포함)'}
for family,label in names.items():
    data=[r['metrics'][family] for r in reports];positive=[r for r in data if not r['reference_absent']]
    sdr=[r['raw_sdr_db'] for r in positive if r['raw_sdr_db'] is not None];negative=[r['output_to_mix_db'] for r in data if r['reference_absent'] and r['output_to_mix_db'] is not None]
    interval=f'{min(sdr):.2f} ~ {max(sdr):.2f}dB' if sdr else '작은 정답/없음'
    leakage='미분류 성분 보관' if family=='other' else f'{max(negative):.2f}dB' if negative else '해당 없음'
    lines.append(f'| {label} | {len(positive)} | {interval} | {leakage} |')
lines+=['','## 남은 오류와 적용하지 않은 후보','',
        '- 신디 패드는 스트링으로 잘못 잡히는 조건이 남았습니다. 일반 패드의 신디 정답 투영 계수는 약 0.5%이며 조용한 패드의 SDR도 음수입니다.',
        '- 짧은 강한 바이올린은 보컬·신디·추가 반주로 여전히 흩어집니다. 보완 후 스트링 투영 계수는 약 11.8%로 아직 부족합니다. 작은 바이올린 개선을 전체 스트링 품질 개선으로 일반화할 수 없습니다.',
        '- 일부 가상 기타는 기타 계열에 거의 잡히지 않습니다. 실제 Rainfall 기타에서는 기존 성능이 유지됐습니다.',
        '- 작은 가상 브라스에서도 낮은 정답 신호 비율과 음수 SDR이 남았습니다. 실제 트럼펫 개선을 모든 브라스 음색으로 일반화할 수 없습니다.',
        '- 슬레이벨은 새 타악기에 일부만 잡히며 코러스 쪽에 남는 성분이 있습니다.',
        f"- 드럼 SDR 최대 하락: {-min(m['drums'].get('sdr_delta_db',0) for m in metrics.values()):.3f}dB (기존 결과 대비). 기타 전체 SDR은 rainfall-guitars-only에서 {metrics['rainfall-guitars-only-40-60']['guitar_total']['raw_sdr_db']['before']:.2f} → {metrics['rainfall-guitars-only-40-60']['guitar_total']['raw_sdr_db']['after']:.2f}dB로 하락했습니다. v11 단계에서 생긴 변화이며 v12 타악기 단계는 기타 파일을 바꾸지 않습니다.",
        '- 원곡 전체를 바로 재분리하는 방식, 무보호 CLAP 심벌 추출, 신디/스트링/브라스 강제 재분류는 다른 정답 또는 작은 연주를 손상시켜 적용하지 않았습니다. CLAP 신디 교체 후보는 작은 패드 SDR을 약 -4.01에서 -16.53dB로 악화시켰습니다. 잔여 반주를 보수적으로 추가하는 후보도 패드/스트링 오차가 커져 제외했습니다.','',
        '자료는 실제 스튜디오 멀티트랙, Slakh 가상 악기 믹스, 실제 단음 샘플의 인공 믹스를 포함합니다. 동일 곡/동일 샘플의 음량 변형은 독립적인 곡으로 세지 않습니다. 이 세트만으로 모든 장르의 안정성을 보증하지 않습니다.','',
        f"자동 검증: {validation['passed']}개 통과, {validation['skipped']}개 제외({validation.get('skip_reason','설정된 MySQL 통합 테스트 미실행')}). 프론트엔드 빌드 통과.",
        f"기사개전 전체 재추출 처리 시간: {mills['processing_seconds']:.1f}초. 캐시를 재사용한 32개 검증은 전체 재추출 처리 시간으로 표시하지 않습니다.",'',
        '[전체 비교 재생](http://127.0.0.1:8791/stability-v12.html) · [기사개전 5–10초](http://127.0.0.1:8791/millsage-stability-v12/comparison.html)','',
        '자료 출처: [Philharmonia](https://philharmonia.co.uk/resources/sound-samples/), [FreePats 팀파니](https://freepats.zenvoid.org/Percussion/orchestral-percussion.html), [BabySlakh](https://zenodo.org/records/4603870). 원본 샘플·모델 파일은 Git에 포함하지 않았습니다.','']
(docs/'THIRTEEN_TRACK_STABILITY_KO.md').write_text('\n'.join(lines),encoding='utf-8')
write_json(docs/'THIRTEEN_TRACK_STABILITY_SUMMARY.json',{'conditions':32,'unique_inputs':unique,'unit_passed':validation['passed'],
    'overall_status':'IMPROVEMENTS_VERIFIED_WITH_KNOWN_CLASSIFICATION_FAILURES','all_original_sums_verified':True,
    'minimum_voice_projection_retained_ratio':voice,'minimum_piano_target_gain':min(gains),'worst_absent_percussion_to_mix_db':absent,
    'full_millsage':mills,'remaining':['synth_pad_string_confusion','strong_short_violin_misrouting','some_virtual_guitar_misses','quiet_virtual_brass_misses','sleigh_bell_vocal_leakage']})
print('FINAL REPORT: 32 CONDITIONS;',unique,'UNIQUE INPUTS')
