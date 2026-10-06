# 12트랙 정답 stem 비교 — 초기 실험

2026-10-07. 기준 main `cc8a6cb`, 실험 브랜치 `codex/12-track-ground-truth-evaluation`.

공개 [MedleyDB 샘플](https://medleydb.weebly.com/downloads.html)의 실제 녹음 stem으로 20초 입력을 만든다. 원래 MIX.wav는 마스터링·믹싱 음량이 stem 단순합과 일치한다고 보장하지 않으므로 사용하지 않는다. 선택한 stem을 동일 gain으로 합성하며, 원본과 결과는 정규화하거나 noise gate를 적용하지 않는다. Phoenix의 Main System은 밴드 전체를 포함할 수 있어 제외한다.

| 샘플 | 구간 | 정답 악기 | 목적 |
|---|---|---|---|
| Phoenix / Scotch Morris | 30–50초 | 통기타, 바이올린, 플루트(other) | 실제 bleed 및 관악·현악이 신디·브라스로 이동하는 문제 |
| Liz Nelson & Jennifer Davies / Rainfall | 40–60초 | 리드, 코러스 2개, 통기타, clean 일렉기타 | 보컬·두 기타의 정밀 비교, 부재 악기 출력 |
| Rainfall 기타만 합성 | 40–60초 | 통기타, 일렉기타 | 같은 연주에서 보컬 유무를 통제한 부재 테스트 |

Phoenix 메타데이터는 has_bleed=yes다. 정답은 지정 stem의 파형이며, 각 마이크에서 들리는 소리가 해당 악기만이라고 해석하지 않는다. Rainfall은 has_bleed=no다. 이 테스트의 리드/코러스 라벨은 메타데이터의 melody 여부를 사용하며 상용곡 전체의 역할 정의를 보장하지 않는다.

출력 12개를 모두 읽는다. 기타 보조(guitar_residual)는 독립 악기의 정답이 없으므로 통기타+일렉기타+기타 보조 합계를 원본 두 기타 stem 합계와 별도로 비교한다. 플루트는 브라스가 아니라 other 정답에 배정한다.

SDR/SI-SDR, 목표 파형 gain, 출력·오차 RMS, 원곡 대비 출력 에너지 dB를 전체 구간과 1초 창별로 기록한다. 정확히 0인 정답은 SDR 대신 부재 출력량으로 평가한다. 기존 SDR 함수는 -60dBFS 미만 정답에 null을 반환하므로 약한 연주의 유지율은 target_gain/error_rms도 함께 본다. 여기의 dB는 loudness나 사람의 청취 승인 점수가 아니다.

## 실행

공식 다운로드 페이지의 Sample 링크를 `data/ground-truth/medleydb/MedleyDB_Sample.tar.gz`로 저장한다. 이 샘플은 CC BY-NC-SA 4.0이며 비상업 연구 용도다. 오디오와 모델은 Git에 포함하지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts/prepare-medleydb-ground-truth.py data/ground-truth/medleydb/MedleyDB_Sample.tar.gz
.\.venv\Scripts\python.exe -m music_analyzer.ground_truth run data/ground-truth/cases/phoenix-30-50
.\.venv\Scripts\python.exe -m music_analyzer.ground_truth run data/ground-truth/cases/rainfall-40-60
.\.venv\Scripts\python.exe -m music_analyzer.ground_truth run data/ground-truth/cases/rainfall-guitars-only-40-60
```

각 케이스의 library는 별도 WebLibrary다. 회원 DB와 기존 서비스 결과를 수정하지 않는다. 모델 파일은 기존 로컬 체크포인트를 hardlink하고 기존 해시 검증과 GPU 잠금을 사용한다. 실제 실행 단계와 오류는 콘솔·record.json에 남는다.

각 폴더에 prepared.json, run.json, report.json, comparison.html, evaluation-references, evaluation-outputs, evaluation-candidates를 기록한다. 준비 단계는 원본 stem/아카이브와 합성 입력 해시를, 평가 단계는 참조·프리셋·구현 코드 해시와 job ID를 기록한다. 전체 원시 결과와 보완 제거 후보 WAV도 보존한다.

`comparison.html`은 정답/현재 결과/보완 제거 후보를 같은 고정 재생 음량으로 듣는 페이지다. 비교 후보는 현재 synth/strings/brass에서 보완 추출분을 제거하고 그 신호를 other에 반환한다. 다른 출력과 전체 출력 합계를 유지하는지 2e-6 이내로 검증한다. 기존 모델 추출 결과를 그대로 사용한 보완 단계 ablation이며 새 모델을 학습한 결과가 아니다.

이미 완료한 실행을 최신 평가 코드로 다시 계산하려면:

```powershell
.\.venv\Scripts\python.exe -m music_analyzer.ground_truth evaluate data/ground-truth/cases/phoenix-30-50
```

## 발견과 범위

Phoenix에서 없는 신디의 출력이 보완 전 원곡 대비 -27.94dB에서 보완 후 -8.20dB로 증가했다. 브라스도 -55.48dB에서 -24.92dB로 증가했다. 플루트 정답(other)의 SDR은 보완 없는 후보 5.49dB에서 현재 결과 0.78dB로 하락했다. 스트링 SDR은 4.70→4.54dB로 약간 하락했다. 보완 단계가 이 샘플의 잔여 실제 악기를 다른 라벨로 이동시키는 원인이며, 단순 합계 검사는 이 문제를 발견하지 못한다.

Rainfall에서 리드 SDR 18.63dB, 코러스 8.69dB, 통기타 18.92dB, 일렉기타 16.22dB다. 부재 신디는 -53.56→-35.12dB, 스트링은 -95.36→-51.00dB, 브라스는 -107.38→-62.06dB로 증가했다. 신디 등 부재 전용 트랙을 줄이는 후보는 other 출력량을 키우므로, 후보를 모든 곡에 적용하는 것이 곧 전체 정확도 개선이라고 주장하지 않는다.

수치 요약은 같은 폴더의 `TWELVE_TRACK_GROUND_TRUTH_RESULTS.json`에 저장한다. 실측 처리시간은 짧은 구간의 여러 모델 로딩을 포함하며, 곡 전체 예상시간 기준으로 사용하지 않는다.

기타만 합성한 Rainfall은 통기타 SDR 26.27dB, 일렉기타 17.24dB, 기타 합계 37.77dB다. 부재 신디는 보완 전 -98.37dB에서 보완 후 -40.86dB로 증가했다. 보완 제거 후보의 합계 보존 최대 오차는 세 케이스에서 5.96e-8~8.94e-8이다. 원곡 대비 전체 출력 합계 오차 RMS는 약 4e-9 수준이지만, 이는 소스 라벨 정확도를 의미하지 않는다.

이번은 2곡·3구간의 초기 테스트다. 리드/코러스/통기타/일렉기타/스트링의 존재 샘플과 나머지 악기의 부재 샘플을 제공한다. 피아노·신디·브라스·베이스·드럼의 실제 존재 샘플, dense mix, quiet passage 다양성, 마스터링된 입력은 아직 부족하다. 신디 보완의 기존 승인된 긍정 사례가 있으므로 이 부재 테스트만으로 서비스 기본 보완을 일괄 끄지 않는다. 이후 긍정/부정 샘플을 추가해 같은 정답 비교로 회귀 여부를 검증해야 한다.
