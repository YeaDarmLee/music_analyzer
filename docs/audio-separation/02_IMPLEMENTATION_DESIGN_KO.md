# 02. 구현 설계

## 1. 실행 구조

첫 구현은 Python CLI 프로세스 하나와 모델별 격리 환경으로 구성한다. Python 3.11/3.12를 지원 후보로 두고 S1은 제공된 Python 3.12 전용 환경에서 시작하되, 실제 모델 의존성 검증 후 정확한 Python/PyTorch/CUDA/FFmpeg 버전을 잠근다. Windows 직접 실행을 먼저 검증하며 호환성 문제가 확인되면 WSL2를 별도 결정 기록으로 채택한다. S1에서는 PyTorch 2.5.1+cu121 및 torchaudio 2.5.1+cu121로 CUDA 실행과 모델 추론을 검증한다. 결과는 별도 S1 보고서에 기록한다.

```text
CLI / 후속 localhost UI
       ↓ JobService
검증 → 디코딩 → 기준 오디오 생성
       ↓ ModelAdapter (격리 subprocess)
모델 고유 전처리 → chunk 추론 → 결합
       ↓ 기준 시간축 복원
정합성 검사 → 원시 WAV / preview / manifest
       ↓ atomic publish
완성 결과 → 청취 / export / 후속 채보
```

| 구성 | 책임 | 경계 |
|---|---|---|
| AudioIO | probe, decode, resample, write | 모델 이름을 모름 |
| JobService | 상태, 취소, lock, 복구, 결과 게시 | 신호처리 구현을 모름 |
| ModelRegistry | 모델·config·hash·라이선스·입출력 정보 | 신뢰되지 않은 임의 checkpoint 로딩 금지 |
| ModelAdapter | 모델 환경 실행, chunk, tensor → stem | 제품 상태/UI에 의존하지 않음 |
| Validator | 길이, 채널, NaN, peak, 누락 출력 | 청각 품질의 자동 합격 판정은 하지 않음 |
| Evaluator | 참조 평가, 청취 기록, 실행 성능 | 원시 결과를 변경하지 않음 |
| Exporter | 공통 gain, PCM24, 안전한 파일명 | 원시 결과 보존 |

DB, Redis, Celery, S3는 초기 필요 요소가 아니다. Job 상태는 JSON으로 atomic 갱신하고 단일 GPU 작업만 허용한다. 후속 서버화에서 JobService의 저장소와 executor를 바꿀 수 있게 인터페이스를 분리한다.

## 2. 제안 디렉터리

아래는 목표 구조다. S1에서 CLI, 환경 검사, registry, raw writer, 지표 함수와 smoke runner를 먼저 작성하고 나머지는 후속 단계에서 추가한다.

```text
separation/
  pyproject.toml
  src/music_analyzer/
    cli.py, job_service.py, contracts.py
    audio/{probe,decode,resample,export}.py
    models/{registry,base,demucs,msst}.py
    evaluation/{metrics,benchmark,report}.py
    playback/                 # UI 단계에서 추가
  configs/{presets,models}/
  tests/{unit,integration,fixtures}/
  benchmarks/{catalog,reports}/
data/separation/               # Git 제외; 사용자 설정 가능
  models/<model_id>/<revision>/
  inputs/<asset_id>/
  jobs/<job_id>/
    job.json
    attempts/<attempt_id>/
    result/{manifest.json,stems,previews,metrics.json}
```

Python 기반 분리 엔진부터 새로 구성하고, 로컬 웹 UI는 후속 단계에서 추가한다. 모델 가중치, 음원, 로그의 사용자 경로를 저장소에 커밋하지 않는다.

## 3. 오디오 처리 순서

1. 파일 확장자와 실제 decoder 결과를 함께 검사한다. FFprobe/FFmpeg 호출에는 shell 문자열 조합 대신 인자 배열을 사용한다.
2. 원본을 로컬 managed input으로 복사하며 SHA-256을 구한다. 복사·검증 완료 후에만 실행 대상으로 등록한다.
3. duration, 채널, rate, 추정 PCM 크기를 검사한다. decoder 실행 제한 5분, 전체 작업 제한 2시간을 초기 설정값으로 두고 실험 후 조정한다.
4. 기준 PCM을 만든다. stereo 유지, mono는 양 채널 복제 및 `mono_duplicated=true` 기록. silence trim, denoise, loudness normalization은 하지 않는다.
5. 정확한 `reference_num_frames`를 기록한다. 원본 sample rate와 기준 sample rate를 별도로 보존한다.
6. adapter가 모델 요구 형식으로 바꾼다. 모델 내부 정규화가 필요하면 scale/mean과 역변환 여부를 기록한다.
7. 모델이 지원하는 chunk/overlap 구현을 우선 이용한다. wrapper에서 다시 chunking하지 않는다. chunk 길이·overlap·precision·seed·shifts는 preset에 고정한다.
8. 직접 overlap-add가 필요하면 weight 합으로 정규화하고 경계에서 0으로 나누지 않는다. 첫·마지막 패딩을 제거한다. chunk별 gain 정규화는 금지한다.
9. 모델 출력 순서는 registry의 명시적 label mapping으로 변환한다. 파일명 가나다순이나 tensor index 추측에 의존하지 않는다.
10. 기준 rate로 돌아온 결과는 기준 frame 수에 맞춘다. 문서화된 resample 반올림 오차 1 frame까지만 보정한다. 그 이상의 길이 차이 또는 알려지지 않은 latency는 실패 처리하고 원인을 확인한다.
11. 검증 후 임시 result 디렉터리를 같은 볼륨에서 최종 경로로 rename한다. 결과 게시와 SUCCEEDED 상태 사이의 중단은 복구 시 manifest를 검사해 일관되게 정리한다.

초기 GPU 설정은 batch 1, 동시 모델 1이다. fp32를 비교 기준으로 두고 혼합 정밀도는 차이·메모리·속도를 측정한 별도 preset만 허용한다. CPU 모드는 입출력 smoke test 및 모델이 지원하는 짧은 구간 확인용이며 실시간 처리를 약속하지 않는다.

## 4. 모델 adapter 계약

```text
describe() -> ModelCapabilities
prepare(registry_entry) -> PreparedModel
run(canonical_audio, preset, output_dir, progress, cancel) -> SeparationResult
release() -> None
```

`ModelCapabilities`는 native rate/channels, 정확한 출력 labels, taxonomy version, 최대 segment 제약, 지원 precision/device를 포함한다. `SeparationResult`는 각 stem path, label, rate, frame 수, normalization 역변환 정보, 측정 timing, warnings를 반환한다. 모델 고유 confidence가 없으면 생성하지 않는다.

런타임은 job JSON 요청과 result JSON 응답을 사용하는 subprocess 방식으로 시작한다. GPU tensor를 API나 UI로 전달하지 않는다. 모델마다 충돌하는 의존성은 별도 가상환경으로 격리한다. 필요할 때만 공용 in-process 최적화를 검토한다.

## 5. registry와 재현성

각 모델은 `training_data_risk`(LOW/MEDIUM/HIGH/UNKNOWN), `commercial_release_status`(DEV_ONLY/INTERNAL_APPROVED/LEGAL_REVIEW/PRODUCTION_APPROVED), `model_id`, `architecture`, `repository_url`, `commit`, `checkpoint_url`, `checkpoint_sha256`, `config_sha256`, `environment_lock_hash`, `native_sample_rate`, `source_labels`, `code_license`, `weight_license`, `license_evidence_url`, `review_status`를 갖는다.

미확정 hash·revision은 실행 가능한 registry에 들어갈 수 없다. 다운로드는 `.partial`로 쓰고 hash 검증 후 승격한다. 초기 다운로드는 공식 파일 목록의 SHA-256 prefix를 확인한 뒤 전체 hash를 등록하는 별도 prepare 작업이다. 이는 독립적으로 제공된 전체 hash를 검증한 것과 다르며 verification에 구분한다. 등록 후 추론 직전 전체 hash와 config hash를 다시 검증한다. 오프라인에서 모델이 없으면 `MODEL_NOT_AVAILABLE`로 종료한다. 학습 파일 포맷은 실행 코드가 포함될 수 있으므로 임의 사용자 checkpoint 업로드를 지원하지 않고, 신뢰한 배포 경로만 등록한다.

cache key = 입력 원본 hash + decoder/resampler 버전 + canonical 변환 설정 + 모델/config/environment hash + 실제 preset + pipeline version. 캐시 재사용 전 manifest와 출력 hash를 검사한다. 다른 모델·설정·fallback으로 나온 결과는 같은 캐시로 취급하지 않는다.

## 6. 출력 manifest 계약

아래 JSON은 필드 형식 예시다. placeholder 값은 실행 결과가 아니다. 실제 발행 manifest에는 모든 stem, 실제 hash와 revision이 필요하다.

```json
{
  "schema_version": "1.0",
  "job_id": "job_example",
  "asset_id": "asset_example",
  "status": "succeeded",
  "input": {"sha256": "<sha256>", "original_sample_rate": 48000},
  "timeline": {"sample_rate": 44100, "channels": 2, "num_frames": 10584000, "origin_sec": 0},
  "pipeline_version": "<version>",
  "model": {"id": "<registered-id>", "revision": "<commit>", "checkpoint_sha256": "<sha256>", "config_sha256": "<sha256>"},
  "preset": {"requested": "baseline", "resolved": "<resolved-preset>", "seed": 0},
  "stems": [{"id": "stem_bass", "family": "bass", "parent_stem_id": null, "path": "stems/bass.wav", "sha256": "<sha256>", "presence": "unknown", "quality_score": null}],
  "mix_group": {"id": "main", "kind": "estimated_partition", "reconstruction_guaranteed": false},
  "timing": {"wall_sec": null, "inference_sec": null, "peak_vram_bytes": null},
  "warnings": []
}
```

frame을 시간 기준으로 삼고 `time_sec = frame / sample_rate`로 초를 계산한다. duration과 frame 수를 독립적으로 갱신하지 않는다. 알 수 없는 schema major version은 거절하고 minor 추가 필드는 무시할 수 있게 한다. 내부 경로는 result 아래의 상대 경로이며 `..`와 절대 경로를 금지한다.

## 7. 분류 중복과 재합성

6-stem은 서로 겹치지 않는 분할을 목표로 하지만 추정 오차 때문에 합계가 원곡과 완전히 일치하지 않을 수 있다. `residual = reference - sum(stems)`는 진단용이며 독립 악기의 정답이나 순수한 other가 아니다.

53-stem 등의 분류에는 부모와 자식 범주가 포함될 수 있다. guitar와 electric-guitar, drums와 kick을 모두 동시에 더하지 않는다. registry에 `parent`와 `mix_group`을 기록하고 같은 계층의 분할만 재생 대상으로 선택한다. 배타성이 확인되지 않았으면 `overlapping_targets`로 취급한다.

전문 모델로 일부만 교체하면 새 result revision을 만든다. 기존 other를 포함한 합계의 정합성을 다시 검사하며, 기존 6-stem과 같은 재합성 특성을 보장하지 않는다. 자동 잔차 배분은 초기 비활성이다. 계층 분리는 앞 단계의 결손이 전파되므로 full mix에서 직접 추출한 결과와도 비교한다.

## 8. 상태·실패·복구

상태: `CREATED → VALIDATING → PREPARING_MODEL → PREPROCESSING → SEPARATING → VALIDATING_OUTPUT → EXPORTING → SUCCEEDED`. 실행 중에는 `CANCELLING → CANCELLED` 또는 `FAILED`로 전이할 수 있다. 정상 종료 상태는 변경하지 않는다. 재시도는 새 attempt ID를 사용한다. 프로세스 중단은 복구 시 해당 attempt에 `INTERRUPTED`로 기록한다.

| 사건 | 처리 |
|---|---|
| 잘못된 형식·허용 범위 밖 입력 | 검증 실패, GPU 처리하지 않음 |
| GPU OOM | subprocess 해제 후 작은 segment의 등록된 fallback을 최대 1회 시도. 변경을 manifest에 기록 |
| fallback도 OOM | FAILED. 무제한 재시도·무통보 CPU 전환 없음 |
| GPU/드라이버 오류 | 진단 저장, 수동 재시도 가능 |
| NaN/Inf·stem 누락·큰 길이 차이 | 전체 실패, 완성 result를 발행하지 않음 |
| 디스크 부족 | 시작 전 검사와 쓰기 오류 모두 처리. 성공으로 표시하지 않음 |
| 사용자 취소 | chunk 경계에서 정지 요청, 10초 응답 없으면 자식 프로세스 종료, temp 정리 |
| 앱 중단 | 다음 실행 시 attempt를 INTERRUPTED로 기록. 새 attempt에서 처음부터 재실행 |
| UI만 닫음 | worker 계속 실행 가능. 재접속 시 상태 복원. 명시적 앱 종료는 취소로 처리 |

lock에는 PID와 시작 정보를 저장하고 오래된 lock을 무조건 실행 중으로 취급하지 않는다. GPU job은 1개만 실행하며 두 번째 요청은 busy를 반환한다. 삭제 대상은 managed data root 아래로 제한하고 사용자 원본 파일은 삭제하지 않는다.

## 9. 로컬 UI 구현 단계

FastAPI를 127.0.0.1에 bind하고 작은 독립 웹 화면을 제공한다. 실행별 session token, Origin 검사, 허용된 result ID를 통한 접근을 사용한다. 임의 파일 경로를 URL로 전달해 읽게 하지 않는다. UI framework는 S5에서 새 로컬 화면을 구현할 때 선택한다.

API안: `POST /assets` 파일 등록, `POST /jobs` preset 지정 실행, `GET /jobs/{id}` 상태 조회, `POST /jobs/{id}/cancel` 취소, `GET /jobs/{id}/manifest` 결과, `GET /jobs/{id}/stems/{stem_id}` 음성, `POST /jobs/{id}/exports` 내보내기. 초기에는 1초 poll을 사용하고 필요하면 이벤트 전송을 추가한다. 없는 ID는 404, 충돌은 409, 입력 오류는 422다.

재생은 공통 AudioContext 시각에서 모든 stem을 schedule한다. pause/seek 시 모든 source를 정지하고 같은 offset으로 다시 만든다. 개별 audio 태그의 play를 동시에 호출하는 방식으로 동기화하지 않는다. UI 커서는 audio clock에서 계산한다.

15분·6stem을 float32로 전부 decode하면 약1.9GB이므로 브라우저에 전체 곡의 모든 stem을 상주시켜서는 안 된다. 초기에는 최대 60초의 동일 frame 범위를 모든 stem에서 읽어 약0.13GB를 오디오 버퍼 예산의 기준으로 삼는다. 원본 비교 버퍼·복사·브라우저 overhead는 별도로 측정한다. 긴 곡은 구간을 선택해 듣는다. 전체 곡 연속 믹서는 ring buffer와 AudioWorklet을 이용하는 별도 확장이다.

재생 측에는 headroom을 두고 gain 변경에 따른 clip을 감지한다. 모니터링용 limiter를 사용하면 표시하고 비교 테스트에서는 끈다. 원본과 stem 비교에는 전체에 공통 gain만 적용한다.

## 10. 저장 용량과 export

PCM 예상 bytes = 초 × sample rate × channels × bytes/sample × 파일 수. 4분, 44.1kHz, stereo, float32 파일 하나는 약84.7MB다. 기준 PCM+6stem은 약593MB이며 입력 복사·temp·preview·export는 별도다. 시작 전 추정 작업 크기의 2배+1GiB 여유를 확보하는 안을 제안한다.

PCM24 export에서 peak가 상한을 넘으면 선택 stem 전체에 같은 gain을 적용한다. 개별 peak normalization은 하지 않는다. float32 raw의 1 초과 값은 저장할 수 있지만 clip 경고를 기록하고 integer export는 반드시 범위 안에 들어오게 한다. 양자화의 dither 방식도 고정·기록한다. ZIP에는 결과물만 포함하고 개인용 절대 경로나 환경변수는 넣지 않는다.

모델 캐시와 성공 결과는 명시 삭제 전까지 보관한다. 실패 temp는 다음 시작 시 대상 job을 표시해 정리할 수 있게 한다. 로그는 로컬에 저장하며 외부 전송이나 자동 학습에 사용하지 않는다.


## 11. P0 불변조건과 S1 구현 범위

DEM-RAW-01: Demucs CLI 기본 저장 경로를 사용하지 않는다. float32 WAV, clip=none 의미, per-stem normalization 없음, gain=1로 저장한다. 1을 넘는 샘플과 파트 사이 볼륨 관계를 보존하며 저장 후 원시 tensor와 동일한 float32 sample인지 검사한다. PCM24 공통 gain export는 별도 단계다.

PREPARING_MODEL은 명시적 모델 다운로드, hash 확인, 환경 검사, load와 warm-up의 진행을 설명하는 상태다. S1에서는 prepare-model 명령으로 다운로드를 분리하고 smoke 명령은 준비된 모델만 읽는다. 첫 추론은 cold run이며 모델 warm-up을 제외한 수치라고 표시하지 않는다.

taxonomy 1.0의 family ID와 명시적 Demucs label mapping을 configs에 둔다. unknown 모델 label은 임의 변환하지 않고 거절한다. S7 전에 53개 label의 parent/child, overlap, 역할 분류를 검증한다.

S1 runner는 별도 Python 프로세스의 단일 smoke 실험이다. 완성 JobService의 lock/복구/자동 OOM fallback/사용자 원본 관리 기능은 S2–S3에서 구현한다. S1 완료를 서비스 전체 구현 완료로 해석하지 않는다.

## 12. S2 실제 입력 계약

S2는 ingest.py와 ingest/inspect-asset CLI로 AudioIO를 제공한다. inputs/<asset_id>/에 original.*, canonical.wav, manifest.json을 발행한다. 완성 job과 입력 asset의 manifest는 서로 다른 kind다. Audio asset은 kind=audio_asset/status=ready이며 source label이나 모델 결과를 포함하지 않는다.

원본 복사·hash 검증 후 FFprobe로 실제 형식과 mono/stereo를 확인한다. native rate로 bounded pipe decode하고 native PCM frame 수로 실제 길이를 판정한다. resample 후 rational half-up frame 수와 1 frame 이내 차이만 끝부분 보정한다. mono는 변환 후 sample을 그대로 두 채널에 복제한다.

입력 최대1GiB, native decoded PCM 최대2GiB, 실제 길이 1–900초다. FFprobe는30초, native decode/resample은 각각300초 timeout이다. 각 단계의 timeout과 전체 job timeout은 구분한다. 실제 생성한 15분 48kHz mono 파일을 검증했다.

값과 파일을 변경하지 않는 inspect-asset은 hash·상대 경로·frame/rate/channel/subtype·duration을 확인한다. 부분 directory는 발행 전까지 asset으로 취급하지 않는다. S3가 검증된 asset을 받아 모델 작업을 수행한다. [S2 검증 결과](07_S2_VERIFICATION_KO.md)


## 14. S3 구현 반영 (2026-10-05)

등록된 asset을 받는 JobService와 별도 GPU worker를 연결했다. separate --input은 S2 ingest 이후 정식 전체 곡 작업을 실행한다. 상태·취소·재실행·복구·결과 검사를 각각 CLI 명령으로 제공한다.

worker는 upstream apply_model의 split/overlap-add를 사용하며 CPU에 전체 결과를 누적한다. 각 chunk 전후로 취소를 확인한다. 출력은 float32 raw WAV로 block 저장·roundtrip 확인 후 부모가 결과 hash·timeline을 다시 검증하여 게시한다.

정식 작업은 공통 supervisor lock과 worker 실행 lock으로 중복 GPU 사용을 거절한다. Windows venv 실행기와 실제 Python 자식 모두 취소 시 종료한다. PID/create_time·worker 명령·request 경로를 확인해 강제 종료 작업을 복구한다. 재실행은 새 job_id와 retry_of를 남긴다.

OOM은 baseline에서 memory_safe로 새 프로세스 1회 재시도한다. 최종 memory_safe는 입력·내부 segment 2초와 cuDNN 비활성화를 함께 사용한다. 짧은 segment만 바꾸는 초기 후보는 실측에서 오히려 메모리 사용이 늘어 제외했다. 품질 변화 경고와 실제 설정·코드·환경 hash를 manifest에 기록한다.

실제 곡 1개와 무음·역상·취소 검증을 실행했다. 3곡 완주 조건과 청취 품질 평가는 남아 있다. 상세 증거와 현재 명령은 [S3 검증 보고서](08_S3_VERIFICATION_KO.md)를 기준으로 확인한다.

## S4 구현 반영 (2026-10-05)

사용자 음질 피드백에 따라 7.8초 문맥·50% overlap·두 시간 이동 평균, 악기별 fine-tuned 및 6-stem을 구현했다. 같은 곡을 세 후보로 완주하고 고정 gain 청취 비교 페이지를 만들었다. 다곡/reference/blind 청취 gate는 남아 있다. [S4 구현·측정·청취 안내](09_S4_QUALITY_AND_6STEM_KO.md)를 참고한다.
