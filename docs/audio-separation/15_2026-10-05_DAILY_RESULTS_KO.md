# 2026-10-05 개발·실험·청취 결과 종합 기록

작성 기준: 한국 시간 2026-10-05, 오늘 대화와 단계별 검증 문서 및 현재 실행 설정.
프로젝트: C:\workspace\music_analyzer. 빈 폴더에서 시작한 독립 프로젝트다.

**현재 결론: 로컬 전체 곡 분리와 비교 흐름은 구현했다. 보컬은 Mel-Band RoFormer로 채택했다. 악기 분리는 BS-RoFormer 후보를 테스트 중이며, 기타와 패드/other 혼입은 아직 해결되지 않았다. 악보 변환과 일렉 내부 파트 분리는 구현하지 않았다.**

## 1. 목표와 진행 범위

최종 목표는 음원을 입력하면 악기별로 분리하고 악보까지 생성하는 프로그램이다. 이번 단계는 악기별 음원 분리에 집중했다. 실제 구현 전에 범위·설계·개발 단계·오디오 계약·모델 근거·검증 계획을 문서로 분리했고, 외부 피드백을 검토해 실행·복구·출력 검증 구조를 구체화했다.

현재는 로컬 MP3/WAV/FLAC 입력을 사용한다. YouTube URL 입력, 서비스 배포, 악보/MIDI 출력은 완료 범위가 아니다.

## 2. 구현된 기능

| 영역 | 오늘까지의 결과 |
|---|---|
| 실행 환경 | Windows, RTX 3060 12GiB, Python 3.12.14, torch/torchaudio 2.5.1+cu121, Demucs 4.0.1 |
| 입력 | MP3/WAV/FLAC 검증, 원본 사본·SHA-256 보존, 1초~15분 입력 계약 |
| 표준 오디오 | 44.1kHz stereo FLOAT WAV, decoded sample 기준 타임라인, silence trim/음량 정규화 없음 |
| 모델 준비 | 명시적 prepare-model, 고정 모델 ID·배포 경로, 체크섬 및 registration 기록 |
| 전체 곡 분리 | 별도 worker, 단일 GPU 실행 lock, 진행 상태, raw stem 및 manifest |
| 작업 관리 | 상태 조회·취소·시간 제한·비정상 종료 복구·새 작업 재시도·CUDA OOM 한 번 fallback |
| 출력 검사 | source label/순서, 프레임 수, finite, FLOAT readback, 파일 SHA-256 |
| 청취 비교 | 같은 입력·구간·fixed gain, 모델/트랙 전환, 원입력 비교, 청취 기록 저장 |
| 단계 연결 | 확정 보컬 → 보컬을 뺀 반주 → 악기 분리, 중간 오디오 sample 일치 검사 |
| 부분 개선 실험 | guitar+other만 재분리, 다른 트랙 보존, 원래 결과 덮어쓰기 없음 |
| 실행 안내 | 다른 곡 테스트·새 모델 비교·폴더 열기·오류/재시도 명령어 문서 |

## 3. 모델과 설정의 변화

### Demucs 기준선 및 설정 개선

처음에는 4트랙 분리를 연결했다. 실제로 분리는 됐지만 사용자는 음량 흔들림, 약한 악기 누출과 연주 누락을 보고했다. 이후 7.8초 문맥, 50% overlap, 두 시간 이동 추론 평균, 악기별 fine-tuned 모델을 비교했고 기타·피아노를 포함한 6트랙도 추가했다.

사용자는 millsage 결과에서 전체 6트랙이 대충 분리된 느낌이며 연주가 빠지고 물속에서 듣는 질감이 강하다고 평가했다. 같은 Demucs의 설정 조정만으로 충분하다고 판단하지 않고 다른 모델 계열로 실험 범위를 넓혔다.

### 보컬: Mel-Band RoFormer 채택

KimberleyJSN/melbandroformer의 고정 리비전과 공개 전체 SHA-256을 확인해 연결했다. 8초 구간, 75% overlap, batch 1, CUDA float16으로 실행했다.

보컬은 모델 추정치이며, 전체 반주 instrumental은 **원본 - 추정 보컬**이다. 합이 원본과 맞는 것은 잔차 구성의 결과이고 정확도 점수가 아니다.

사용자 평가: “아직 약간 다듬어야 하지만 내 기준 그래도 한 80프로는 더 정확한 것 같다.” 이 표현은 **기존 대비 주관적 청취 평가**로 기록한다. 객관적 정확도 80% 또는 SDR 개선율로 환산하지 않는다.

결정: **보컬은 이 모델로 확정.**

### 악기: BS-RoFormer 6트랙 후보

기존 악기 모델에서 기타에 피아노가 섞이고, 슬랩 베이스가 기타로 넘어가며, 피아노에 빈 부분이 있다는 피드백에 따라 다른 6트랙 BS-RoFormer를 연결했다.

출력 순서: bass / drums / other / vocals / guitar / piano. 같은 확정 보컬 제거 반주를 입력으로 비교했다. 게시 파일의 공개 전체 SHA-256과 실제 다운로드 일치를 확인하고 strict state_dict 로드를 사용했다.

이 후보는 community-published checkpoint이며 학습 내역과 비교 성능이 충분히 확인되지 않았다. 개발 실험 후보로 유지하고 품질을 보장하지 않는다.

사용자가 지정한 기사개전 구간:
- 13~14초: 슬랩 베이스가 기타로 넘어가는 현상.
- 20~40초: 기타에 피아노가 미세하게 섞이고 피아노 출력에는 빈 부분이 있는 현상.

### 기타와 other 집중 재분리

사용자 작업 job_570b38bffcb643db978641cc1a289919에서 나머지는 일단 괜찮지만 기타와 other가 겹쳐 들린다는 피드백을 받았다. 대상 구간은 처음부터 20초다.

실험 방식:
1. 기존 guitar + other를 합친다.
2. 같은 BS-RoFormer에 이 합만 다시 입력한다.
3. 새 guitar는 모델의 기타 추정값으로 사용한다.
4. 새 other는 기존 두 트랙 합에서 새 guitar를 뺀 잔차로 만든다.
5. drums/bass/piano/vocals는 원래 파일과 해시를 그대로 참조한다.

두 트랙 합의 보존은 검증했지만, 같은 모델의 분류 오류나 기존 합의 중복/누락까지 해결한 것은 아니다.

**최신 사용자 평가: 패드 사운드와 일렉 사운드가 여전히 약간 겹친다. 따라서 이 재분리 후보도 최종 개선안으로 채택하지 않았다.**

## 4. 주요 실제 실행 기록

| 곡/입력 | 설정 | 추론 시간 | 상태 |
|---|---|---:|---|
| SPYAIR | Demucs baseline | 15.837초 | 전체 4트랙 생성 |
| SPYAIR | Demucs quality | 22.408초 | 전체 4트랙 생성 |
| SPYAIR | Demucs quality_ft | 89.412초 | 전체 4트랙 생성 |
| SPYAIR | Demucs quality_6s | 23.172초 | 전체 6트랙 생성 |
| 기사개전 | Demucs quality_ft | 약91.687초 | 전체 4트랙 생성 |
| 기사개전 | Demucs quality_6s | 약23.785초 | 전체 6트랙 생성 |
| 기사개전 | Mel-Band RoFormer | 43.234초 | 보컬·전체 반주 생성 |
| SPYAIR | Mel-Band RoFormer | 41.858초 | 보컬·전체 반주 생성 |
| 기사개전의 보컬 제거 반주 | BS-RoFormer 6트랙 | 30.715초 | 악기 후보 생성 |
| 사용자 지정 작업의 guitar+other | 집중 재분리 | 단계 manifest에 기록 | 전체 길이 후보 생성 |

시간은 해당 실행의 추론 측정치이며 다른 곡/PC의 보장이 아니다. GPU 수치는 개별 보고서의 PyTorch allocator 측정이고 전체 장치 사용량과 구분한다.

첫 BS 모델 연결에서 Mel-Band 전용 생성자 옵션 전달 오류가 있었다. BS 고유 ISTFT 길이 처리로 수정하고 새 작업으로 재실행해 성공했다. 기존 실패 작업은 이력으로 보존했다.

## 5. 주요 작업·결과 위치

| 결과 | ID |
|---|---|
| 기사개전 확정 보컬 | job_a5b0e6a61f45478c902b72754700dba7 |
| SPYAIR 확정 보컬 | job_2d72bbda153f467fbfa13661414a69e8 |
| 기사개전 보컬→반주→기존 악기 연결 | pipeline_5ed2f61a401a4c10a0825d4feacab7ca |
| 위 연결의 기존 악기 작업 | job_da86237490c64ae786c577e6a0995ccd |
| 기사개전 새 악기 후보 | job_c2788a98d55c4aa091a429d40b6b007a |
| 사용자가 기타/other 문제를 확인한 작업 | job_570b38bffcb643db978641cc1a289919 |
| 해당 작업의 기타/other 재분리 | refine_14809c3105a84e1e9e1396c67483e50f |
| 재분리 내부 모델 작업 | job_a0a855472be942babeb37a5f7649d4b4 |

일반 작업은 data/separation/jobs/job_ID/result/stems에 raw WAV가 있다. 연결 결과 manifest는 data/separation/pipelines/pipeline_ID에 있으며 각 작업의 파일을 참조한다. 재분리의 새 guitar/other는 data/separation/refinements/refine_ID/stems에 있고 나머지는 원래 작업 파일을 참조한다.

사용자 지정 작업은 약348.206초의 보컬 제거 반주다. 오늘 확인한 기록만으로 그 원곡 이름을 확정하지 않아 임의로 곡 이름을 붙이지 않는다.

### 청취 페이지

- [기사개전 보컬 모델 비교](../../data/separation/comparisons/compare_a367a1fdde764b2885ef871cc398cc4d/comparison.html)
- [SPYAIR 보컬 모델 비교](../../data/separation/comparisons/compare_ee178b824bf6465aa130a2e9f2137ea9/comparison.html)
- [기사개전 악기 모델 비교](../../data/separation/comparisons/compare_28597ec671304d54b2f34a3c5c3ad06c/comparison.html)
- [사용자 지정 작업의 기타/other 재분리 비교](../../data/separation/refinements/refine_14809c3105a84e1e9e1396c67483e50f/comparison/comparison.html)

로컬 서버 주소는 각각 8770/8771/8773 등을 사용했다. 서버가 종료되면 주소가 열리지 않으므로 저장된 comparison.html이나 가이드의 http.server 명령으로 다시 연다. HTML과 clips 폴더를 함께 유지한다.

## 6. 검증 결과와 정확도 해석

단계별 회귀 테스트는 S1 16개 → S2 포함59개 → RoFormer 보컬 후보112개 → pipeline 테스트 추가 → BS-RoFormer119개 → 기타/other 재분리122개로 확장했다. **마지막 전체 실행은 122 passed, 30.10초**다. 이후 기록/표시 문구 변경이 있었으며 그 숫자를 새 추론 품질 점수로 해석하지 않는다.

확인한 내용:
- 원본·중간 입력·출력의 hash 및 오디오 계약.
- chunk overlap에서 단일/다중 출력의 순서·프레임·진폭 보존.
- 비정상 출력 및 잘못된 shape 거부, 취소와 작업 관리.
- 안전 YAML 로딩, 고정 코드/설정 및 checkpoint 검증.
- 실제 WAV 로딩, 모델/트랙 선택, 8초/20초 청취 파일 로딩.
- 기타/other 합 오차 최대 1.4901161193847656e-08.
- 나머지 트랙 참조와 SHA-256 보존.

미확인:
- 정답 stem 기준의 SDR/SI-SDR·객관적 악기 정확도.
- 모든 곡/모든 악기에서 누출·연주 누락이 해소됐는지.
- 악보 변환에 충분한 정확도인지.
- 미실행 OOM fallback의 실제 청취 품질.

예전 S3 보고서의 서로 다른 곡 1/3 판정은 그 단계 당시 기록이다. 이후 곡과 사용자 실행이 추가됐지만, 동일 검증 계획의 다양성 조건을 다시 감사하지 않았으므로 단순 job 수로 3/3 완료를 선언하지 않는다.

## 7. 지금 확정된 결정과 실행 기본값

| 항목 | 현재 결정 |
|---|---|
| 보컬 모델 | Mel-Band RoFormer 채택 |
| 후속 입력 | 원본 minus 확정 보컬인 전체 반주 |
| BS-RoFormer 악기 모델 | 후보 테스트 중, 최종 채택 선언 없음 |
| 기타/other 재분리 | 추가 실험, 패드/일렉 혼입 미해결 |
| 나머지 악기 | 해당 사용자 작업에서는 일단 괜찮다는 청취 의견 |
| 일렉 1/2/3 세분화 | 혼입 개선 이후로 보류, 구현 없음 |
| 악보/MIDI | 후속 단계, 구현 없음 |

현재 separation/configs/pipeline.json의 instrument_preset은 **quality_6s(Demucs)**이며 instrument_selection은 experimental이다. scripts/separate.ps1 기본값 pipeline도 이 설정을 따른다. BS-RoFormer를 쓰려면 separate --preset instrument_roformer_6s를 명시한다. 기본값이 이미 새 악기 후보로 교체됐다고 혼동하지 않는다.

## 8. 사용자가 직접 실행할 명령

프로젝트 루트 PowerShell:
```powershell
Set-Location "C:\workspace\music_analyzer"

# 확정 보컬 → 반주 → 현재 기본 악기 모델
.\.venv\Scripts\python.exe -m music_analyzer.cli separate-pipeline --input "C:\실제경로\노래.mp3"

# 동일 반주를 새 악기 후보로 시험
.\.venv\Scripts\python.exe -m music_analyzer.cli separate --asset-id asset_실제반주ID --preset instrument_roformer_6s

# 기존 성공 작업의 기타와 other만 재분리
.\.venv\Scripts\python.exe -m music_analyzer.cli refine-guitar-other --job-id job_570b38bffcb643db978641cc1a289919 --window 0:20
```

[다른 곡 테스트 전체 가이드](13_TESTING_GUIDE_KO.md)에 실제 변수 사용·결과 열기·동일 반주 비교·중단·재시도 방법을 정리했다.

## 9. 아직 남은 문제와 다음 단계

1. **패드와 일렉 혼입 해결이 우선이다.** 현재 재분리 방식을 더 정확한 것으로 채택하지 않는다.
2. 기타와 패드를 조건/음색으로 구분하는 다른 모델을 조사하고 같은 0~20초 구간으로 비교한다. 이 접근은 제안 단계이며 새 조건부 모델의 다운로드·연결·실행은 아직 하지 않았다.
3. 누출 감소와 함께 기타 지속음·잔향 및 패드의 보존을 평가한다. 기타가 잘려서 깨끗해진 결과를 개선으로 간주하지 않는다.
4. 악기 모델을 확정한 뒤, 추출된 guitar.wav를 다른 모델에 넣어 리드/리듬 등 연주 파트를 나누는 실험을 진행한다.
5. 일렉 1/2/3이 실제 원래 녹음 트랙과 일치한다고 보장하지 않는다. 같은 톤·같은 코드의 더블링은 특히 구분이 어렵다.
6. 분리 품질을 충분히 확인한 후 악보 변환 단계로 넘어간다.

## 10. 상세 문서 목록

- [범위·결정](01_SCOPE_AND_DECISIONS_KO.md)
- [구현 설계](02_IMPLEMENTATION_DESIGN_KO.md)
- [개발 단계·검증 계획](03_DELIVERY_AND_VALIDATION_KO.md)
- [모델 근거](04_MODEL_EVIDENCE_KO.md)
- [외부 피드백 검토](05_FEEDBACK_REVIEW_KO.md)
- [S1 환경·합성 추론 검증](06_S1_VERIFICATION_KO.md)
- [S2 입력·변환 검증](07_S2_VERIFICATION_KO.md)
- [S3 전체 곡·작업 관리](08_S3_VERIFICATION_KO.md)
- [S4 Demucs 품질 설정·6트랙](09_S4_QUALITY_AND_6STEM_KO.md)
- [S5 RoFormer 보컬 후보](10_S5_ROFORMER_VERIFICATION_KO.md)
- [S6 보컬→반주→악기 연결](11_S6_CASCADE_KO.md)
- [S7 BS-RoFormer 악기 후보](12_S7_INSTRUMENT_ROFORMER_KO.md)
- [다른 곡 실행 가이드](13_TESTING_GUIDE_KO.md)
- [S8 기타/other 재분리](14_S8_GUITAR_OTHER_REFINEMENT_KO.md)

이 종합 문서는 오늘의 최종 상태를 기록하며 단계별 문서는 당시 실행 증거로 유지한다.
