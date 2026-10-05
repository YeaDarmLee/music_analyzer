# 03. 개발 단계와 검증 계획

## 1. 실행 순서와 단계 종료 조건

아래 기간은 1인 개발의 작업 분해용 추정이다. 순수 개발일 기준이며 장비 문제, 모델 조사, 테스트 음원 확보, 품질 개선 반복은 별도다. 일정 약속이나 이미 측정된 개발 속도가 아니다.

| 단계 | 주요 작업 | 산출물 | 완료 조건 | 예상 |
|---|---|---|---|---|
| S0 설계 검토 | 범위, 합격 기준, 데이터 계약, 미결 항목 정리 | 이 문서와 결정 기록 | 막히는 제품 결정에 기본안 또는 결정 담당 명시 | 구현 전 |
| S1 환경·모델 준비 | Python/PyTorch/CUDA 호환 확인, FFmpeg, checkpoint 출처·hash 등록 | environment lock, registry, 환경 보고서 | GPU tensor smoke test와 10초 추론 성공, 모델별 이용조건 증거 저장 | 1–2일 |
| S2 오디오 기반 | decode/resample, timeline, manifest, atomic write | 모델 없는 입출력 CLI | mono/stereo, 한글 경로, 잘못된 파일, frame 수 검증 통과 | 1–2일 |
| S3 기준 분리 | htdemucs 4-stem adapter, 취소, OOM 처리 | 1곡 → 4stem + manifest | 정상 곡 3개 완주, 재실행 provenance, 실패 파일 미게시 | 2–3일 |
| S4 6-stem·평가 | 6-stem adapter, benchmark runner, blind 비교 | 모델·악기별 성능 보고서 | 분리 품질과 처리 성능을 분리해 보고, 채택/보류 결정 | 3–5일 |
| S5 로컬 도구 | localhost API, 구간 재생, Solo/Mute, export | 로컬 사용자 워크플로 | 시나리오 테스트와 동기 재생·메모리 검증 통과 | 3–5일 |
| S6 안정화 | 중단 복구, 저장 공간, 반복 실행, 오류 안내 | 로컬 v0.1 릴리스 후보 | 아래 기능·품질·운영 gate 통과 | 2–3일 |
| S7 세부 악기 | 전문 모델, 드럼 하위 분리, 53 탐색 비교 | 별도 실험 보고서 | 기존 대비 유의한 개선과 자원 예산 만족 | 실측 후 산정 |

S1–S6 단순 합계는 12–20 개발일이다. 품질 미달로 후보 재선정이 발생하면 늘어난다. 특히 S4는 날짜가 지나면 완료되는 단계가 아니라 품질 판단이 나와야 끝나는 단계다.

## 2. 구현 티켓과 의존성

| ID | 작업 | 의존 | 수용 기준 |
|---|---|---|---|
| ENV-01 | GPU·runtime 호환표 확정 | S0 | 설치 버전과 실제 GPU 추론 로그 기록 |
| MOD-01 | 모델 registry·download 검사 | ENV-01 | 변조 hash 거절, 출처·license 기록 없는 모델 비활성 |
| AUD-01 | probe·decode·입력 제한 | ENV-01 | 손상/다채널/초과 길이 파일을 명시 오류로 처리 |
| AUD-02 | canonical timeline·resample | AUD-01 | 임펄스와 mono/stereo fixture의 frame 계약 만족 |
| JOB-01 | 상태 파일·atomic 게시·lock | AUD-01 | 같은 GPU의 중복 실행 거절, 중단 후 상태 회복 |
| SEP-01 | 4-stem adapter | MOD-01, AUD-02, JOB-01 | labels 정확성, 크기·시간축·finite 검증 |
| SEP-02 | 6-stem adapter | SEP-01 | 같은 interface, 기타/피아노 warning 포함 |
| EVAL-01 | benchmark catalog·report | SEP-01 | 입력/설정/hash로 결과 재추적 가능 |
| EVAL-02 | 모델 선정 비교 | SEP-02, EVAL-01 | 곡별·악기별·장르별 실패가 평균에 가려지지 않음 |
| EXP-01 | PCM24·ZIP export | SEP-01 | 공통gain·누락 없는 manifest·안전한 파일명 |
| UI-01 | 파일·작업·결과 화면 | JOB-01, SEP-02 | 성공/실패/취소 흐름 완결 |
| UI-02 | 구간 동기 재생 | UI-01 | 공동 clock, seek/loop/Solo/Mute 정의 충족 |
| REL-01 | 안정화·사용 안내 | EVAL-02, EXP-01, UI-02 | 모든 필수 gate 결과 첨부 |

## 3. 테스트 음원 구성

우선 20곡을 목표로 시작한다. 10곡은 참조 stem이 있는 평가용, 10곡은 실제 사용 조건의 청취용이다. 권리와 용도가 확인된 자체 연주 또는 사용 가능한 multitrack으로 확보한다. 유명 데이터셋이라고 평가·상용 사용이 자동 허용된다고 간주하지 않는다.

참조 10곡 중 6곡은 개발·설정 선택에 사용하고 4곡은 최종 확인용으로 잠근다. 같은 곡의 다른 구간을 양쪽으로 나누지 않는다. 작은 표본이므로 전체 음악에 대한 정확도 추정으로 광고하지 않는다. 확대 평가 시 50곡 이상으로 확장하되 장르 구성과 권리 확보를 먼저 기록한다.

곡에는 rock, acoustic, piano 중심, electronic, dense mix를 포함하고, 다음 조건을 중복 태그한다: 무보컬, 무피아노, 약한 bass, 짧은 guitar solo, 강한 reverb, distorted guitar, mono, 저비트레이트 MP3, live noise. 없는 악기가 결과에 나타나는 오류도 평가한다.

catalog 필드: song ID, 원본 hash, 출처, 사용 허용 범위, 참조 유무, instruments, genre, duration, split, 평가 구간, 제외 사유. 참조 stems의 합이 평가 mixture와 다른 mastering이면 reference-compatible=false로 표시하고 직접 SDR 비교를 하지 않는다. 참조 없는 곡의 SDR은 null이다.

## 4. 정량 측정

### 오디오 계약과 성능

- 모든 출력의 rate/channels/frame 수가 canonical과 일치해야 한다.
- NaN/Inf, 누락 파일, 0-byte 파일은 즉시 실패다. 무음 stem 자체는 오류가 아니다.
- chunk 경계에서의 임펄스/연속 파형 연결 시험으로 chunk 결합 결함을 확인한다.
- RTF = inference wall seconds / audio seconds. 모델 로딩 포함 시간과 제외 시간을 모두 저장한다.
- GPU peak allocated/reserved와 가능한 경우 device 사용량, host RAM, 결과 용량을 구분한다.
- 4분 곡의 정상 preset 완료 목표는 RTF ≤ 3, 즉 추론 12분 이내로 제안한다. RTX 3060에서 미측정이며 목표를 넘으면 품질/속도 preset을 다시 정한다.
- 12GiB 전체를 쓸 수 있다고 가정하지 않는다. 첫 10초·60초·전체 곡 순서로 peak를 확인하고 디스플레이 사용분 여유를 남긴다.

### 참조 기반 지표

RAW-SDR는 gain을 맞추지 않는 waveform fidelity 지표로 고정한다:

`SDR = 10 log10((sum(reference²) + ε) / (sum((reference - estimate)²) + ε))`

stereo의 두 채널과 정렬된 평가 구간을 함께 집계한다. ε는 float 연산용 작은 고정값으로 기록한다. 참조 RMS가 -60 dBFS 미만인 구간은 SDR에서 제외하고 absent-target leakage로 별도 평가한다. 평가 시 임의 gain 또는 delay 최적화로 점수를 올리지 않는다.

이는 논문의 BSS Eval SDR과 동일한 지표가 아니다. 논문 수치와 직접 비교하지 않는다. SI-SDR를 품질 보조 지표로 별도 구현한다. 평가 reference와 estimate는 float64, 동일 순서로 stereo를 펼치고 각각 평균을 제거한다. alpha=dot(estimate, reference)/(dot(reference, reference)+epsilon), target=alpha*reference, noise=estimate-target로 계산한다. epsilon=1e-12다. 평균 제거 후 참조 RMS가 -60dBFS 미만이거나 target projection이 퇴화하면 null로 둔다. SI-SDR도 delay 차이를 제거하지 않는다. BSS Eval을 추가하면 구현·버전·filter·window 설정을 별도 기록한다.

`reconstruction_error = RMS(reference_mix - sum(stems))`는 pipeline 진단이다. 합이 원곡과 비슷해도 각 악기가 잘 분리되었다는 뜻은 아니다. 개별 악기 순도는 참조와 청취로 평가한다.

### 청취 평가

20–30초 고정 구간을 모델명이 숨겨진 A/B로 듣는다. 원본과 비교하되 loudness 차이로 선호가 왜곡되지 않게 비교용 gain을 기록한다. 가능하면 2명이 독립 평가하고 불일치를 남긴다. 1명 평가일 경우 그 한계를 보고한다.

각 stem에 1–5점으로 target 보존, 타 악기 누출 억제, artifact 억제의 세 점수를 남긴다. 1=식별/사용 곤란, 3=음악 구문을 따라갈 수 있으나 간섭 명확, 5=평가 구간에서 방해가 거의 없음. ‘멜로디와 리듬을 듣고 연습할 수 있는가’는 yes/no로 별도 기록한다. 정확한 채보 가능성은 이번에 검증하지 않는다.

## 5. 모델 선택 규칙과 품질 gate

후보는 동일 입력과 동일 평가 구간으로 실행한다. 모든 모델을 모든 곡에 여러 설정으로 무제한 실행하지 않는다. 기준 모델 + 대안 1개부터 시작하고, 설정 조정은 개발 split에만 적용한다.

RAW-SDR는 gain·시간축 fidelity 진단으로 보고하고 수치 개선만으로 모델을 교체하지 않는다. SI-SDR와 blind 청취를 함께 본다. 향후 Phase C에서는 별도 downstream evaluator가 Note/Onset/Offset F1 및 pitch 정확도를 반환하도록 확장한다.

초기 제안 gate:

1. 최종 holdout의 악기별 청취 3개 항목 median이 각각 3 이상이며, target 보존 1점 사례는 원인을 공개한다.
2. 실제 존재하는 guitar/piano 평가 구간에서 ‘연습 가능’이 각 80% 이상이어야 해당 파트를 실험적 표시 없이 제공하는 후보가 된다. 각 악기 최소 5개 구간·서로 다른 3곡이 없으면 판정 보류다.
3. 기준 모델을 교체할 후보는 비교 가능한 instrument의 median SI-SDR이 0.5dB 이상 개선되고 청취 점수가 악화되지 않거나 blind 청취에서 60% 이상 선호되어야 한다. 동률은 별도 기록하며 유효 비교 10개 미만이면 결론 보류다.
4. 다른 핵심 instrument의 median SI-SDR이 1dB 초과 하락하거나 청취 품질이 명확히 악화되면 전체 교체 대신 모델별 preset으로 분리한다.
5. 모든 성공 결과는 오디오 계약 gate를 통과해야 한다. 음질이 좋아도 손상 파일이나 타임라인 불일치는 출하하지 않는다.

수치는 내부 의사결정용 제안이지 통계적 우월성의 증명은 아니다. S0에서 동결하고 S4 결과를 보고 바꿀 경우 변경 이유와 기존 기준의 실패를 함께 남긴다. 기준을 사후 낮추고 원래 통과한 것처럼 기록하지 않는다.

## 6. 기능·운영 수용 테스트

| 시나리오 | 기대 결과 |
|---|---|
| WAV/FLAC/MP3, mono/stereo, 44.1/48kHz | 일관된 canonical, 입력 속성 기록 |
| 한글·공백·기호 경로 | shell 해석 없이 정상 처리 |
| 손상/0초/다채널/제한초과 파일 | GPU 사용 전에 이해 가능한 오류 |
| 악기 부재와 전체 무음 | presence 미확정 유지, 에너지 지표와 warning 구분 |
| 10초/60초/4분/15분 파일 | 메모리·시간·디스크 측정, 길이 누락 없음 |
| OOM 주입 | 등록된 fallback 1회, 실제 설정 기록, 실패 시 결과 미게시 |
| 추론/쓰기 중 취소·강제 종료 | 부분 결과 노출 없음, 재시작 및 새attempt 가능 |
| 디스크 부족·export 실패 | 원시 성공 결과 보존, export 오류 분리 |
| 10회 반복 작업 | 누적 GPU 메모리 누수 여부와 종료 후 회수 확인 |
| seek 20회·Solo/Mute·구간 loop | 같은 frame offset 유지, 중복 source가 남지 않음 |
| offline 상태 | 준비된 모델 실행 가능, 미준비 모델은 명확히 실패 |

동기 재생은 공통 임펄스 fixture의 render 결과에서 track 간 1 sample 이내 정렬을 확인하고 청취로 click과 드리프트를 확인한다. UI 동기 테스트와 AI 모델의 phase 오차를 혼동하지 않는다.

## 7. 보고서 양식과 중단 조건

각 실행 보고서: 환경, 입력 집합 hash, model/checkpoint/config hash, 실제 preset, seed, run ID, 성공/실패 수, 악기별 지표, 청취 점수, RTF, peak memory, 비용 산식, 실패 예시, 채택 결정, 다음 실험 1개.

10초 실험에서 OOM이 반복되면 전체 곡을 실행하지 않는다. 모델 출처·입출력 taxonomy가 불명확하면 adapter를 고정하지 않는다. 기타·피아노가 기준 미달이면 UI 확장보다 모델 비교를 우선한다. 53개 출력을 만드는 데 성공했다는 사실만으로 S7을 통과하지 않는다.

## 8. 개발 착수 전 체크리스트

- [x] 사용자 선택: 로컬 PC에서 시작.
- [x] GPU 이름·VRAM 확인: RTX 3060, 12GiB.
- [x] 단계, 데이터 계약, 실패 처리, 품질 평가 방법 문서화.
- [ ] 제안 범위와 품질 기준 검토.
- [ ] 사용할 테스트 음원과 참조 stem 확보.
- [x] S1 개발 baseline의 checkpoint URL/hash와 실행 환경 고정.
- [x] 10초 S1 smoke의 fp32/4초 preset 실측. 실사용 preset 확정은 S3–S4.

S1 실험 결과는 [검증 보고서](06_S1_VERIFICATION_KO.md)에 기록했다. 실제 곡의 품질과 실사용 preset은 다음 실험 항목이다. 피드백 검토 후 S1 구현에 착수했다. 현재 코드·환경·실험 결과는 S1 보고서를 기준으로 확인한다.



## 9. 진행 기록

2026-10-05: S1 GPU 검증 후 S2 완료. [S2 검증 보고서](07_S2_VERIFICATION_KO.md)에 59개 테스트와 실제 CLI 예제를 기록했다. AUD-01/AUD-02 및 입력 asset의 atomic 발행을 구현했다. JOB-01의 GPU 작업 관리·lock·취소·복구는 S3 작업이다.

## S3 현재 구현 판정 (2026-10-05)

전체 곡 4-stem CLI, 작업 잠금·취소·복구·한 번의 OOM fallback을 구현했다. 실제 정상 곡은 서로 다른 곡 기준 1/3이며, 나머지 2개 완주와 청취 검증은 남아 있다. 합성 신호와 같은 곡의 다른 preset 실행을 정상 곡 수에 포함하지 않는다. [S3 실행 증거](08_S3_VERIFICATION_KO.md)를 참고한다.

## S4 구현 반영 (2026-10-05)

사용자 음질 피드백에 따라 7.8초 문맥·50% overlap·두 시간 이동 평균, 악기별 fine-tuned 및 6-stem을 구현했다. 같은 곡을 세 후보로 완주하고 고정 gain 청취 비교 페이지를 만들었다. 다곡/reference/blind 청취 gate는 남아 있다. [S4 구현·측정·청취 안내](09_S4_QUALITY_AND_6STEM_KO.md)를 참고한다.
