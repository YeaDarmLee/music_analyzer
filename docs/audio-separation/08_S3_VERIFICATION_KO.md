# 08. S3 전체 곡 분리와 작업 관리 검증

작성: 2026-10-05 · 환경: Windows / RTX 3060 12GiB / Python 3.12 / torch 2.5.1+cu121 / Demucs 4.0.1

## 현재 판정

**실제 로컬 MP3 한 곡을 입력해 곡 전체의 4-stem WAV와 manifest를 만드는 CLI를 구현·실행 검증했다.** 작업 상태, 단일 작업 lock, 취소, 강제 종료 복구, 새 작업 재실행, 한 번의 OOM fallback도 연결했다.

S3 설계의 정상 곡 3개 완주 조건은 서로 다른 실제 곡 **1/3**이다. 같은 곡을 다른 설정으로 실행한 것은 별도 곡으로 세지 않는다. 합성 무음·역상 신호도 실제 곡을 대체하지 않는다. 따라서 S3 기능 구현은 확인했으나 단계 전체의 다양성 검증은 아직 닫지 않았다. 참조 stem과 청취 점수가 없어 분리 음질이나 악보 추출 적합성은 판정하지 않았다.

## 실제 곡 결과

입력: 사용자가 제공한 SPYAIR - サムライハート(Some Like It Hot!!).mp3

- 원본 SHA-256: 12699b68aa6ab24638df99a00e4e0ba12b223a46e5fac7c59eae4d874b39554d
- asset_id: asset_3bc078c970334e599708862126362e40
- canonical SHA-256: d1dc91c58b0917c75648105476b24f7ab86197a07799ad0570cce6207ccb6d3a
- 디코딩 길이: 191.56462585034015초, 8,448,000 frames
- 입력·출력 기준: 44.1kHz / stereo / timeline origin 0
- 보컬·드럼·베이스·other 모두 정확히 같은 frames, FLOAT WAV
- 모든 raw 파일의 기록 전후 float32 sample 일치, hash 확인
- 원본 peak가 1을 넘는 sample도 clipping 없이 보존

| 설정 | 작업 ID | 모델 추론 | worker 전체 | supervisor 전체 | GPU peak allocated / reserved |
|---|---|---:|---:|---:|---:|
| baseline | job_1442c6219eaa4c64bce8bb02515b4bc7 | 15.837초 | 20.919초 | 22.189초 | 551.47 / 840.00MiB |
| memory_safe | job_e486945163b342c2bab7e4c60dce16e4 | 49.243초 | 54.668초 | 55.842초 | 310.34 / 376.00MiB |

worker 전체는 모델 준비·입력 검사·추론·출력 저장을 포함한다. supervisor 전체는 job.json 생성부터 성공 저장까지이며, separate 명령의 최초 ingest는 제외한다. GPU 수치는 PyTorch allocator로 측정한 값이다. GPU 전체 사용량·호스트 메모리 peak와 다르다. 다른 곡·다른 PC의 성능 보장으로 사용하지 않는다.

기본 결과:
data/separation/jobs/job_1442c6219eaa4c64bce8bb02515b4bc7/result/

manifest의 reconstruction RMS는 약 0.01028이다. 이 값은 네 추정값의 합과 입력 차이를 보는 파이프라인 진단이며 악기 분리 정확도 점수가 아니다. RAW-SDR·SI-SDR는 참조 stem이 없어 null이다. other는 나머지 소리의 혼합이며 기타·피아노의 개별 분리가 아니다.

## 구현 구조와 명령

- job_service.py: 부모 supervisor, 상태 저장, 실행 잠금, worker 관리, 취소·복구·재실행, 최종 게시
- worker.py: 별도 Python 프로세스에서 모델 준비·전체 곡 추론·출력 생성
- job_contracts.py: 설정과 job/result 계약, 출력 hash·timeline 검증
- audio.py: 큰 곡의 raw WAV를 block 단위로 쓰고 다시 읽어 동일 sample 검증
- common.py: atomic JSON 교체와 Windows 읽기/교체 sharing violation 재시도
- configs/presets/demucs.json: baseline 및 실측한 memory_safe 설정
- scripts/separate.ps1: 사용자용 전체 곡 실행 명령

```powershell
cd C:\workspace\music_analyzer
.\scripts\separate.ps1 -InputAudio 'C:\audio\sample.mp3'
.\.venv\Scripts\python.exe -m music_analyzer.cli separate --asset-id 'asset_등록된32자리ID'
.\.venv\Scripts\python.exe -m music_analyzer.cli job-status 'job_출력된32자리ID'
.\.venv\Scripts\python.exe -m music_analyzer.cli cancel-job 'job_출력된32자리ID'
.\.venv\Scripts\python.exe -m music_analyzer.cli inspect-result 'job_출력된32자리ID'
.\.venv\Scripts\python.exe -m music_analyzer.cli recover-jobs
.\.venv\Scripts\python.exe -m music_analyzer.cli retry-job 'job_실패하거나중단된32자리ID'
```

출력은 jobs/<job_id>/result/stems/의 drums.wav, bass.wav, other.wav, vocals.wav다. 별도 dataset·서버·UI 설치는 필요하지 않으며, CUDA 모델 환경과 FFmpeg는 준비되어 있어야 한다.

## 추론과 저장 계약

Demucs upstream apply_model의 split/overlap-add를 그대로 사용한다. 전체 입력·출력 누적은 CPU이며 GPU는 추론 구간에 사용한다. 별도 이중 chunk 결합은 하지 않는다. CPU 전체 곡 메모리는 길이에 비례하므로 무제한 streaming 모델로 설명하지 않는다.

lazy pool에서 각 chunk 전후로 취소/부모 생존 확인을 수행하며, GPU synchronize 후 완료 chunk 수를 기록한다. 진행률 total은 실제 stride 기준 chunk 개수다. 입력 전체의 mean/std로 정규화하고 upstream 방식인 각 source의 std+mean 복원을 사용한다. 개별 stem peak 정규화·공통 정렬 변경·clipping은 하지 않는다.

정확한 무음은 네 무음 트랙으로 bypass한다. 무음도 모델 환경·등록 검사 후 처리한다. 역상 stereo로 mono reference std가 0이 되는 경우 channelwise std를 사용하고 이 변경을 manifest에 기록한다. 정규화할 수 없는 0이 아닌 상수 신호는 명시 오류로 처리한다.

출력은 attempt/result.partial에 쓰고 frame/rate/channel/FLOAT·finite·raw roundtrip·hash를 검사한다. 부모가 다시 result 계약을 확인하고 control lock 아래에서 취소를 확인한 뒤 result로 rename한다. 성공 폴더만 정상 결과다. 저장·추론 실패나 취소의 부분 결과는 정리하고 정상 결과로 게시하지 않는다.

manifest에는 입력 원본/canonical hash, 모델/checkpoint 등록, 실제 설정, 내부 segment, 실행 코드·설정 hash, 환경 lock hash, stem hash, timing과 GPU memory, 정규화와 진단을 남긴다.

## 작업 관리

정상 흐름:
CREATED → VALIDATING → PREPARING_MODEL → PREPROCESSING → SEPARATING → VALIDATING_OUTPUT → EXPORTING → SUCCEEDED

빠른 단계는 상태 polling 중 화면에 표시되지 않을 수 있다. 최종 결과 검사는 생략하지 않는다.

- supervisor.lock은 프로젝트 공통 runtime을 사용하여 data-root를 바꾸어도 정식 작업의 중복 실행을 거절한다.
- worker도 gpu-execution.lock을 유지하여 이전 worker가 남은 경우 새 GPU 실행을 거절한다.
- cancel-job은 별도 cancel.request만 기록한다. job.json은 부모가, worker.json은 worker가 단독으로 갱신한다.
- Ctrl+C 또는 cancel-job은 CANCELLING을 거쳐 CANCELLED가 된다. 기본 유예 10초 후 프로세스 트리를 종료한다.
- Windows venv python.exe의 실행기 아래 실제 Python 자식이 있을 수 있으므로 실행기만 종료하지 않고 자식도 종료한다.
- 기본 작업 시간 제한은 2시간이다. 초과는 JOB_TIMEOUT/FAILED로 기록한다.
- 복구 시 PID와 create_time으로 부모 생존을 판단한다. 남은 작업자를 종료하기 전 실행 명령의 worker marker와 request 경로를 확인한다.
- 부모 종료 후 정상 결과가 이미 게시돼 있다면 검증해 SUCCEEDED로 회복한다. 미게시 작업은 INTERRUPTED로 정리한다.
- retry-job은 FAILED/CANCELLED/INTERRUPTED만 허용하고 새 ID로 실행한다. 기존 결과와 실패 이력을 덮어쓰지 않는다.
- GPU busy는 queue에 넣지 않고 명시 오류로 반환한다. GUI queue나 일시정지·중간 chunk resume는 이번 구현에 없다.

## OOM fallback을 확정한 근거

baseline은 4초 구간, overlap 0.25, shifts 0, float32, seed 0, TF32 off, 내부 학습 segment 7.8초다.

입력 chunk만 2초로 바꿔도 모델의 내부 padding은 학습 길이를 사용할 수 있으므로 메모리 절약을 보장하지 않는다. 내부 segment를 2초로 바꾼 초기 후보도 실제 곡에서 약 2943.62MiB allocated를 사용하여 기본보다 메모리가 늘었다. 이 후보를 최종 memory_safe로 채택하지 않았다.

최종 fallback은 입력·내부 segment 2초와 **cuDNN 비활성화**를 함께 사용한다. 실제 곡 측정 allocated는 약 310.34MiB로 기본 약 551.47MiB보다 줄었고 처리 시간은 늘었다. 품질은 짧은 내부 구간 때문에 달라질 수 있어 warning을 기록한다.

PyTorch의 CUDA OutOfMemoryError만 OOM으로 분류한다. baseline의 OOM에 한해 새 worker 프로세스에서 memory_safe로 1회 재시도한다. 두 번째 OOM은 FAILED다. 임의 오류에 자동 retry하지 않고 CPU로 전환하지 않는다. 실제 GPU를 고의로 고갈시키는 시험은 하지 않았으며, OOM 분기·횟수·새 process는 주입 테스트로 검증했다.

## 검증 목록과 증거

전체 pytest: S1·S2·S3 총 86개. 최종 결과는 data/separation/test-results-s3.xml.

S3 검증 27개에는 다음을 포함한다:

- 성공한 4-stem 게시와 hash/timeline 계약
- 실패 결과 미게시와 부분 폴더 제거
- OOM 1회 retry, 신규 프로세스, 최종 설정, 횟수 제한
- non-OOM 재시도 금지, 수동 retry의 새 ID·기존 이력 보존
- 협조적 취소와 응답 없는 worker 강제 종료
- 시간 초과, supervisor lock과 별도 GPU worker lock
- 실제 supervisor 프로세스 강제 종료, orphan worker 확인·종료·INTERRUPTED 복구·재실행
- 게시 직전 취소, 게시 완료 뒤 부모 종료의 성공 상태 복구
- PID 재사용 방어와 잘못된 ID·설정 거절
- 결과 hash·timeline·source·상대 경로·gain·identity 변조 거절
- full-scale를 넘는 float32 값의 block 저장·roundtrip
- Windows JSON 읽기/교체 경합 재시도, serialization 실패 시 기존 상태 보존

추가 실제 GPU 검증(data/separation/s3-validation/results.json):

| 입력/시나리오 | 작업 | 결과 |
|---|---|---|
| 2초 정확한 무음 | job_e06f0c9ecc684bfdaeb7dbe5f4f77b65 | SUCCEEDED, 추론 bypass |
| 4초 역상 stereo | job_15b4fd4cea8149009d13d849b414006b | SUCCEEDED, 대체 정규화 기록 |
| 실제 곡 추론 중 취소 | job_6a181c1d964541cba87fea282ffbfe46 | CANCELLED, 결과 미게시, worker 종료 |
| 취소 이후 실제 곡 전체 | job_1442c6219eaa4c64bce8bb02515b4bc7 | SUCCEEDED |

구현 중 입력 manifest key 오류와 Windows 상태 파일 경합을 발견하여 수정했다. 실패한 작업 기록은 보존하며 성공 결과로 세지 않는다. 메모리 절약 설정도 실제 측정 후 조정했다.

## 남은 작업

1. 서로 다른 정상 곡 2개 추가 완주로 S3의 3곡 조건 보강.
2. 원본과 각 stem의 같은 구간을 들어 누출·artifact·target 보존 평가.
3. S4 6-stem 후보의 기타·피아노 품질·성능 비교.
4. S5 동기 재생·Solo/Mute·export UI.
5. reference 기반 품질 지표와 배포 적합성 검증.

음원 분리는 사용 가능한 상태지만, 세부 악기 분리·악보 생성까지 완성된 상태는 아니다.
