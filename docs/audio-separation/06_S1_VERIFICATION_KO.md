# 06. S1 환경·GPU 추론 검증 결과

검증일: 2026-10-05 (한국 시간). 상태: S1 수용 기준 통과. 실제 음악의 분리 품질 평가는 미수행.

## 결과

| 항목 | 실제 측정 |
|---|---|
| OS | Windows 11, native Python 실행 |
| GPU | RTX 3060, VRAM 12GiB, driver 560.94 |
| host RAM | 63.93GiB |
| Python | 3.12.14 (Codex 제공 runtime 기반 전용 venv) |
| PyTorch / torchaudio | 2.5.1+cu121 / 2.5.1+cu121 |
| Demucs | 4.0.1, htdemucs single checkpoint |
| 입력 | 직접 생성한 합성 10초, 44.1kHz stereo float32 |
| preset | fp32, segment=4초, overlap=0.25, shifts=0, seed=0, TF32 off |
| 모델 load | 0.426초 |
| 추론 | 2.676초 |
| RTF | 0.2676 |
| pipeline wall | 4.265초 |
| 최대 GPU allocated | 550.71MiB |
| 최대 GPU reserved | 796.00MiB |
| 출력 tensor | [4, 2, 441000] |
| 출력 | drums / bass / other / vocals, FLOAT WAV |
| 저장 gain | 모든 파트 1.0, per-stem normalization 없음 |
| 저장 검증 | 4개 파일 모두 원시 float32 samples와 정확히 일치 |
| 회귀 테스트 | 16 passed |
| 의존성 검사 | pip check 통과 |

단일 cold-model 추론이며 CUDA tensor 연산 확인은 먼저 수행했다. 모델 forward warm-up을 별도로 제외하지 않았다. pipeline wall은 runner 시작부터 manifest 생성 직전까지이며 Python import/CLI 시작·최종 상태 쓰기 시간은 포함하지 않는다. GPU 수치는 PyTorch allocator 기록이며 드라이버·디스플레이·다른 앱까지 포함하는 전체 device peak가 아니다.

이 preset의 shifts=0은 빠른 smoke 확인용이다. 실사용 품질 preset으로 확정하지 않았다. 합성 10초 결과에서 전체 곡의 시간, OOM 여부, 실제 악기 분리 품질을 외삽하지 않는다.

## 재현 자료

- [실행 manifest](../../data/separation/smoke/20261005T031503Z_d1ada57f/result/manifest.json)
- [상태와 전이 이력](../../data/separation/smoke/20261005T031503Z_d1ada57f/status.json)
- [실행 환경](../../data/separation/smoke/20261005T031503Z_d1ada57f/environment/environment.json)
- [테스트 실행 결과](../../data/separation/test-results.xml)
- [휴대 가능한 버전 snapshot](../../separation/requirements/windows-py312-cu121.lock.txt)

run ID: `20261005T031503Z_d1ada57f`

checkpoint SHA-256: `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`

공식 파일 목록의 8자리 SHA-256 prefix를 확인한 후 첫 다운로드 전체 hash를 등록했다. 이후 추론 전 전체 hash·config hash를 재검사했다. 독립적으로 제공된 전체 SHA-256과 대조한 것은 아니며 manifest의 verification 필드에 명시했다. checkpoint는 data에 보관하고 Git 제외한다.

4개 WAV의 길이·채널·rate·subtype·hash를 추론 이후 다시 검증했다. 추가 회귀 테스트는 1.0 초과 raw 값과 파트 간 gain 보존, NaN/Inf 거절, 체크포인트 변조·config 변경 거절, 오프라인 모델 부재, SI-SDR scale invariance 및 시간 이동 민감도를 확인한다.

## 품질 지표의 현재 상태

참조 instrument stem이 없어 RAW-SDR와 SI-SDR는 null이며 품질 점수를 부여하지 않았다. 합성 입력을 vocals 등 실제 악기 정답으로 취급하지 않는다.

재합성 오차 RMS는 0.00099519, peak는 0.03406012다. 이는 원본과 stem 합계의 차이 진단이며 악기별 순도를 뜻하지 않는다. Demucs 공식 방식의 mixture mean/std와 역변환을 그대로 사용하며 평균을 각 source에 더하는 방식을 provenance에 기록했다. 저장 과정에는 추가 gain/clamp가 없다.

## S1 완료와 다음 범위

- 환경 고정, CUDA tensor 연산, 실제 10초 추론, source label·frame 검증 완료.
- raw FLOAT 저장 계약과 초기 taxonomy mapping 및 지표 함수 구현 완료.
- models/config/checkpoint·환경·핵심 모델 코드 hash와 실행 설정 기록 완료.
- 사용자 음원 품질, 60초/전체 곡, 6-stem, MP3/FLAC, export, UI, 정식 작업 관리 기능은 후속 단계다.

다음은 S2의 AudioIO와 canonical asset/manifest다. raw 저장 불변조건을 유지하며 파일 형식·mono·sample rate·손상 파일·디코딩 크기 제한을 검증한다.
