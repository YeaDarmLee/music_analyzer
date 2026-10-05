# 04. 모델 근거·환경·미결 사항

확인일: 2026-10-05. 사용자 제공 원문은 아이디어와 후보 목록의 출발점으로 사용했으며, 모든 내용을 검증된 성능 사실로 가져오지 않았다.

## 1. 후보와 채택 상태

| 후보 | 역할 | 확인한 사실 | 아직 확정하지 않은 것 |
|---|---|---|---|
| Demucs htdemucs | 4-stem 기준 adapter | 공식 저장소에서 drums/bass/vocals/other 지원 안내 | 이 PC의 호환성과 속도, 배포할 정확한 artifact |
| Demucs htdemucs_6s | 6-stem 초기 후보 | guitar/piano 추가, 공식 설명이 piano 누출·artifact 한계를 명시 | 우리 음원의 기타·피아노 품질 |
| MSST 기반 BS/Mel-Band RoFormer | 대안 및 전문 모델 실행 | MSST는 모델 학습·분리 코드 저장소이며 코드 MIT 확인 | architecture 이름만으로 출력 악기와 weight 이용조건을 확정할 수 없음 |
| MVSep Mega 53 | 세부 악기 탐색·비교 후보 | 공식 안내가 53종과 전문 모델 재분리 방향 설명 | RTX 3060 12GiB 실행 가능성, 다운로드할 정확한 파일과 taxonomy mapping |

Demucs의 Meta 저장소는 2025-01-01 archive 되었고 README는 유지보수 fork를 안내한다. 새 코드 기반 전체를 Demucs에 종속시키지 않고 adapter로 감싸는 이유다. 6-stem이 존재한다는 사실은 piano 품질 보장이 아니다. [Demucs 공식 저장소](https://github.com/facebookresearch/demucs)

MSST의 MIT 코드 라이선스를 그 저장소에서 소개하는 모든 checkpoint의 라이선스로 확장하지 않는다. 각 checkpoint의 게시자, config, hash, 조건을 별도 registry 항목으로 확정한다. [MSST 저장소](https://github.com/ZFTurbo/Music-Source-Separation-Training), [코드 LICENSE](https://raw.githubusercontent.com/ZFTurbo/Music-Source-Separation-Training/main/LICENSE)

Mega 53 공식 안내는 세부 악기 목록과 전문 모델을 후속으로 사용하는 접근을 설명한다. 서비스가 검출된 stem만 반환한다는 설명과 로컬 raw checkpoint가 반환하는 tensor 전체는 동일한 계약이라고 가정하지 않는다. [MVSep Mega 53 공식 안내](https://mvsep.com/algorithms/135)

## 2. 원문에서 정정·제한한 주장

| 원문 방향 | 문서에서의 처리 |
|---|---|
| 53-stem부터 상용 기본 엔진 | 확장 후보로 유지; 12GiB 실행·정확한 가중치·품질을 검증 후 선택 |
| 계층 분리가 항상 더 좋은 접근 | 운영 구조로 가능하지만 오류가 누적될 수 있어 직접 추출과 비교 |
| 악기 존재 점수로 실행 자동 생략 | 초기 무효화; detector 검증 전 조용한 악기 누락 위험 |
| separation confidence 0.93 | 보정된 확률 모델이 없으므로 사용하지 않음 |
| 모델을 조합하면 자동 품질 향상 | latency/phase/gain/누출 평가 전 ensemble 기본 적용하지 않음 |
| 모델 비용 0원 → 전체 비용 저렴 | 모델 이용조건과 장비·전력·저장·처리 시간을 별도 산정 |
| 분리 전에 beat/key 분석 필수 | 채보 단계의 요구; 이번 분리 엔진의 의존성에서 제외 |
| 기타 stem = 리드/리듬 기타까지 복원 | 동일 악기 다중 연주자·역할 분리는 별도 연구 과제 |

## 3. 라이선스 증거 관리

2026-09-25 작성자 답변에서 53-stem weights를 MIT로 공개했다고 명시한 것을 확인했다. 같은 답변은 학습 음원 전체의 저작권 보유나 관련 법적 보증을 제공하지 않는다고 설명한다. 이 증거를 다른 사람이 만든 checkpoint에 적용하지 않는다. [작성자 답변: MSST issue 245](https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/245)

실행·배포 검토 레코드는 `code_license`, `weight_license`, `training_data_disclosure`, `allowed_use_scope`, `redistribution_obligations`, `evidence_url`, `verified_at`, `artifact_hash`, `review_status`를 갖는다. 단일 `commercial_allowed=true`로 모든 조건을 압축하지 않는다. 조건 미확인은 금지 확정과도 구별하지만, 자동으로 사용 허용 상태로 바꾸지는 않는다.

출처 기록은 기술 문서의 dependency 관리 절차다. 정확한 파일과 사용 형태가 정해지기 전 모든 상업적 이용 가능성을 보장하지 않는다. ‘연구용이면 무엇이든 괜찮다’ 또는 ‘benchmark는 무조건 허용된다’는 전제도 두지 않는다.

## 4. YouTube 입력의 위치

초기 입력은 파일이다. 원래 구상한 YouTube URL은 별도 ingestion adapter 후보로 남긴다. YouTube API Developer Policies에는 허가 없는 다운로드·캐싱 관련 제한과 오디오 분리 관련 제한이 있으므로, API 기반 입력을 파일 업로드와 같은 방식으로 설계하지 않는다. [YouTube 공식 API 정책](https://developers.google.com/youtube/terms/developer-policies)

사용자가 확보한 음원 파일을 분석하는 경로만 먼저 완성한다. 이 결정은 후속 URL 지원을 영구 포기한다는 의미가 아니라, 허용된 공급 경로와 제공 기능을 별도로 검토한다는 의미다. 현재 downloader나 외부 전송은 구현하지 않는다.

## 5. 장비와 비용

이번 조회 결과: NVIDIA GeForce RTX 3060, VRAM 12,288MiB, driver 560.94. `nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader`로 확인했다. 시스템 RAM 조회는 접근 제한으로 확인하지 못했다. S1에서 프로젝트 전용 환경을 설치하고 CUDA 및 10초 추론을 검증한다. 성공 여부와 측정값은 S1 보고서에 기록한다.

12GiB에서 53-stem이 충분히 동작한다고 추정하지 않는다. 전체 output tensor와 chunk 방식에 따라 메모리 사용이 달라진다. 별도 전문 모델을 순차 실행하면 동시 모델 적재는 피할 수 있지만, 총 처리 시간이 늘어난다. 먼저 4/6-stem의 실제 peak와 RTF를 확보한다.

로컬 실험 비용은 `벽면 소비전력(kW) × 실행시간(h) × 전력 단가`에 저장장치와 장비 비용을 더해 추산한다. GPU TDP만으로 PC 전체 전력비를 확정하지 않는다. 클라우드 사용과 GPU 구매는 이번 단계의 전제가 아니며, 원문에 있는 과거 시간당 가격을 견적으로 재사용하지 않는다.

저장 용량은 4분 6-stem+기준 오디오 약593MB에서 시작한다. 같은 곡을 모델 3개로 반복할 때 공용 입력을 중복 저장하지 않아도 stem 결과·preview·export는 늘어난다. 실행 전 계산한 디스크 예산을 보여주는 이유다.

## 6. 미결 항목과 기본안

| 항목 | 현재 기본안 | 언제 확정하는가 |
|---|---|---|
| 처음 집중할 장르 | rock/acoustic/piano/electronic 혼합 | S0 검토, 평가곡 선정 전 |
| 우선 악기 | 6개 family, 기타·피아노 품질 별도 확인 | S0 검토 |
| 품질 vs 시간 | 한 곡씩 품질 비교, RTF 3 목표 | S4 실측 후 preset 분리 |
| Windows/WSL | Windows 직접 실행 우선 | S1 호환성 검증 |
| Python/PyTorch 정확한 버전 | Python 3.11 후보, 나머지 고정 전 | S1 lockfile 작성 |
| 모델 체크포인트 | Demucs baseline, 나머지 비교 후보 | S1 artifact 증거 + S4 품질 판단 |
| RAM·디스크 예산 | 실행 전 probe, 브라우저 60초 구간 | S1 장비 확인 |
| 테스트 음원 | 사용 범위가 확인된 20곡 | S2–S4 전 확보 |
| 로컬 UI 기술 선택 | 분리 엔진과 독립된 신규 웹 UI | S5 착수 시 결정 |
| 악보 생성 착수 | 분리 품질 보고서 이후 | 같은 제품의 Phase C–D 상세 범위 확정 |

미결 사항은 코딩을 무조건 막는 질문 목록이 아니다. 기본안으로 설계할 수 있는 것은 먼저 작성하고, 실제 실행에 필요한 artifact나 데이터는 해당 단계의 필수 산출물로 처리한다.

## 7. 변경 기록 작성 규칙

새 결정은 날짜, 기존안, 바뀐안, 근거 보고서, 사용자 영향, 다시 검토할 조건을 남긴다. 실험 결과와 제안을 분리한다. ‘모델 최신 버전으로 교체’ 같은 변경도 hash·taxonomy·환경 변경을 동반하면 새 result revision과 benchmark를 요구한다.


## 8. 피드백 후 모델 상태

Demucs 코드는 MIT VERIFIED, pretrained weights는 UNKNOWN/UNRESOLVED로 별도 기록한다. 로컬 개발 baseline 선택은 PROJECT_DEV_BASELINE이며 법적 이용 허가를 입증하는 값은 아니다. commercial_service=REVIEW_REQUIRED, redistribution=BLOCKED, commercial_release_status=DEV_ONLY, training_data_risk=UNKNOWN으로 시작한다. 실제 배포 모델 승격은 별도 증거 검토가 필요하다. [공식 weights 이슈](https://github.com/facebookresearch/demucs/issues/327)

모델 준비 시 공식 목록의 SHA-256 prefix를 검증하고 관측한 전체 SHA-256을 등록한다. 이후 실행은 전체 hash 일치가 필수다. 최초 다운로드의 독립적인 전체 hash 검증과는 구별한다.
