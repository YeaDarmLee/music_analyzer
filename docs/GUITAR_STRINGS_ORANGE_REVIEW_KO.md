# Orange 일렉·스트링 중복 추출 검증

2026-10-06. 사용자는 Orange 9초부터 스트링이 들린다고 지정했다. 브라스는 해당 곡에 없다는 청취 판단을 반영했다. 연구 비교용 결과이며 웹 기본 분석은 변경하지 않았다.

## 관찰과 원인

기존 Mega53 electric-guitar(index 16)와 strings(index 37)는 0–8초 파형 상관 0.9976, 9–20초 0.9868이었다. 스트링이 시작되기 전에도 strings 출력이 거의 같은 기타 신호를 내보냈다. 공식 선택 head와 프로젝트 축소 모델의 동일성은 확인했으므로 head 변환 오류보다 원본 모델의 클래스 중복/오검출이 원인으로 지목된다. 독립 추정치는 배타적인 source partition이 아니다.

상관은 악기 정답 지표가 아니다. 다만 이번처럼 청취상 중복과 대상 부재 구간의 큰 출력을 함께 확인하면 오검출을 조사하는 근거로 사용할 수 있다.

## 비교한 경로

1. 기존 broad strings head 유지.
2. 공식 bowed_strings(index 7)로 스트링 head만 교체. 다른 네 head와 encoder를 유지한다.
3. 로컬 CLAPSep의 양방향 text query: electric guitar를 추출하고 orchestral strings를 negative query로 지정, 반대 방향도 독립 추출. 원곡 0–20초 입력.
4. 같은 CLAPSep query에 Mega53 일렉 출력 0–20초를 입력.

CLAPSep은 기존 `part_study.infer_plan()`과 고정 가중치를 재사용했다. 일렉/현악 prompt만 추가했고 raw 모델 출력을 비교했다. 신호 단순 차감, 위너 필터, EQ, 에너지 gate는 적용하지 않았다. CLAPSep의 두 출력도 완전한 partition이라고 가정하지 않는다.

## 같은 청크 문맥에서의 결과

처음 짧은 clip으로 후보를 확인한 뒤 bowed_strings를 전체 곡(234.777초)으로 재실행했다. 기존 전체 곡과 같은 batch 1 / 10초 chunk / 50% overlap / AMP FP16이다. 다른 네 트랙(어쿠스틱·일렉·신스·브라스)은 디코딩한 전체 곡 float32 sample을 비교했다. WAV 파일 자체 hash는 부가 header 때문에 다를 수 있으므로 waveform 동일성과 구분한다.

| 경로 | 0–8초 strings RMS | 9–20초 strings RMS | 9–20초 guitar/strings 상관 |
| --- | ---: | ---: | ---: |
| 기존 strings | 0.097731 | 0.098580 | 0.986803 |
| bowed_strings | 0.000403 | 0.022171 | 0.092506 |
| CLAPSep 원곡 입력 | 0.141809 | 0.172052 | 0.473677 |
| CLAPSep 일렉 입력 | 0.058124 | 0.052961 | 0.480563 |

bowed_strings는 사용자 기준의 스트링 부재 구간에서 출력이 줄고 등장 구간에서 출력이 커진다. 따라서 가장 유망한 후보로 남긴다. 상관 감소와 낮은 RMS만으로 실제 스트링 보존이나 완벽 분리를 증명하지는 않는다. 일렉 head 자체는 바뀌지 않았으므로 일렉에 남은 스트링 누출은 청취로 별도 확인해야 한다.

CLAPSep은 9초 이전에도 큰 strings 출력을 냈다. 낮은 상관만 보고 이 경로를 승격하지 않는다. L/R 독립 mono 처리에 따른 스테레오 변화 가능성도 있다.

전체 곡 bowed 모델 추론은 37.18초, allocator peak allocated 약 0.996GiB였다. 공식 selected-head와 축소 모델의 검사 probe에서 FP32/AMP 최대 오차는 0. 관련 테스트 41개 통과.

## 산출물과 재실행

- `data/part-studies/guitar-strings-orange/comparison.html`: 기존/현악 후보/CLAPSep 두 입력의 0–20초 비교.
- `bowed-full/`: 전체 곡 raw와 benchmark JSON.
- `mix/`, `guitar-parent/`: CLAPSep raw, prompt, 모델 provenance, 진단값.
- `diagnostics.json`: 구간별 RMS와 상관, preview gain. accuracy score는 없음.
- 청취용 RMS 조정은 최대 4배이며 raw는 보존했다. preview 9개 파일의 stereo/sample rate/frame 수를 확인했다.

```powershell
.\.venv\Scripts\python.exe -m music_analyzer.mega53_experiment prepare --bowed-strings
.\.venv\Scripts\python.exe -m music_analyzer.mega53_experiment benchmark data/reset-backups/reset-20261006-193853/inputs/asset_d8b1327923bd43c98a4cca041db58c25/canonical.wav --output data/part-studies/guitar-strings-orange/bowed-full --start 0 --duration 235 --chunk 10 --bowed-strings
.\data\separation\tools\clapsep-env\Scripts\python.exe -m music_analyzer.part_study --infer-plan data/part-studies/guitar-strings-orange/plan.json
.\.venv\Scripts\python.exe scripts/build-guitar-strings-comparison.py
```

다음 판단은 9초 이후 bowed_strings의 정상 연주 보존과 일렉의 스트링 누출에 대한 청취다. 두 항목을 만족하면 broad strings 대신 bowed_strings를 웹 통합 후보로 채택한다. 아직 완벽 분리나 자동 품질 통과를 주장하지 않는다.
