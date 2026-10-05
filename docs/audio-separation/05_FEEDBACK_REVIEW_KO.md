# 05. 구현 전 피드백 검토 기록

검토일: 2026-10-05. 받은 피드백 중 실행·데이터 무결성과 관련된 수정은 우선 반영하고 S1 구현으로 진행한다.

| 항목 | 판단 | 반영 내용 |
|---|---|---|
| Demucs 저장의 rescale 기본값 | 수용, P0 | DEM-RAW-01: float32 WAV, clip 없음, per-stem normalization 없음. 저장 후 tensor와 sample 값 동일 여부 검사 |
| 코드/weights 이용조건 분리 | 수용 | 코드 MIT와 weights UNRESOLVED 별도 기록, DEV_ONLY, 상용 서비스 검토 필요, 프로젝트 내 재배포 비활성 |
| Mega 53 코드·weights·학습 데이터 구분 | 유지 | 저자 답변은 해당 모델에만 적용, training_data_risk=UNKNOWN 기본값 |
| RAW-SDR와 SI-SDR | 보완하여 수용 | RAW는 pipeline fidelity, SI는 품질 보조. SI도 delay에 민감하며 단독 채택 기준으로 삼지 않음 |
| Phase A–F 전체 제품 계획 | 수용 | [최상위 제품 로드맵](../PRODUCT_ROADMAP_KO.md), ‘후속 별도 프로젝트’를 ‘같은 제품의 후속 Phase’로 수정 |
| canonical taxonomy | 수용 | 6개 family의 1.0 ID와 Demucs mapping을 먼저 작성. 53개 전체 계층·role·overlap은 S7 전 검증 |
| PREPARING_MODEL 상태 | 수용 | 검증과 전처리 사이에 모델 준비 명시, 다운로드/hash/환경/load 진행 구분 |
| 12GiB 접근·OOM 한 번 fallback | 유지 | 10초 → 60초 → 전체 곡. S1은 OOM 시 진단 실패; 자동 fallback은 S3 작업 |
| 일정 확대 해석 | 참고 | 12–20일은 순수 구현 추정이며 실제 달력 일정과 별도, 실측 후 갱신 |

## 중요한 해석 보완

‘local_research: ALLOWED_FOR_PROJECT’를 법적인 이용 허가 증거로 해석하지 않는다. 현재 registry 값은 개발 baseline으로 선택한 내부 상태이며 weights의 포괄적인 상업 이용 허가를 확인했다는 의미가 아니다. 공식 상용 재배포 질문이 남아 있으므로 코드 MIT만으로 weights를 MIT로 선언하지 않는다. [공식 이슈 327](https://github.com/facebookresearch/demucs/issues/327)

Demucs 공식 audio 구현의 기본 저장은 peak에 따른 rescale을 사용할 수 있다. S1에서는 이 함수를 기본값으로 호출하는 대신 SoundFile FLOAT writer를 사용하며 1.0을 넘는 샘플도 그대로 보존하는 회귀 테스트를 둔다. 동일 의미의 직접 호출은 clip=none, as_float=True를 명시해야 한다. [Demucs audio 구현](https://github.com/facebookresearch/demucs/blob/v4.0.1/demucs/audio.py)

SI-SDR는 reference의 방향으로 estimate를 투영해 scale 차이를 제외하는 지표다. 시간 정렬을 수정하지 않는다. 구현은 stereo를 동일 순서로 펼쳐 하나의 scale을 추정하고 reference/estimate 평균 제거 여부, epsilon, 부재 구간 처리까지 고정한다. [SI-SDR 논문](https://arxiv.org/abs/1811.02508)

## 이번 구현 경계

S1은 GPU 실행과 원시 저장 무결성을 검증한다. 합성 10초 신호는 직접 생성하며 곡별 분리 품질이나 악기 인식률을 입증하지 않는다. 완전한 JobService, 모델 환경의 장기 운영 관리, OOM fallback, 긴 파일 decode/resample, PCM24 export, UI는 후속 단계다. 실제 음악·참조 stem이 없을 때 SDR 값을 꾸며 넣지 않는다.

Python은 설치된 일반 interpreter가 없어서 제공된 Python 3.12 runtime으로 전용 venv를 만들었다. 설계의 3.11은 후보였으므로 실제 Demucs 설치·추론 검증 결과에 따라 3.12를 선택 기록한다. CUDA wheel은 기존 드라이버를 변경하지 않는 PyTorch 2.5.1/cu121 조합으로 고정한다. [PyTorch 공식 설치 조합](https://pytorch.org/get-started/previous-versions/)
