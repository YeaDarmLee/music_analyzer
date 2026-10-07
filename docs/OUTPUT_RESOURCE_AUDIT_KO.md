# Output / Resource Audit (1차: 코드 읽기 + 실측 1건, 나머지는 계획)

**구현된 변경 없음.** 이 문서는 현재 상태 기록과 계획이다. 법률/성능 주장은 아래 "실측"으로 표시한 것만 측정값이다.

## 1. 실측 (commercial_13, 90 s 스테레오 44.1 kHz, `data/commercial-eval/smoke`)

| 위치 | 크기 | 내용 |
|---|---|---|
| `web/<analysis>/` | **787 MB** | 28개 WAV(float32): 최종 13 트랙 + 중간 15개(`*-routed`, `*-restored`, `remaining-*`, `guitar-residual` 등)와 record |
| 그중 최종 트랙이 아닌 WAV | 454 MB (15개) | 성공 후에도 남음 |
| `jobs/<job>/` (7개 job) | **969 MB** | 단계별 모델 원출력 stem(float32) — 같은 오디오가 `web/`에 다시 복사/가공됨 |
| `original` (canonical WAV) | 30 MB | 필수 |
| 최종 13 트랙 합계 | 394 MB | 사용자에게 실제로 필요한 것 |

분석 1건이 영구 보관하는 총량 ≈ 787 + 969 + 30 ≈ **1.8 GB**, 사용자에게 필요한 최종 트랙은 그 **약 22 %**(394 MB). 곡 길이에 선형(약 20 MB/초 → 4분 곡 약 4.7 GB 추정, 미측정). 따라서 중간 산출물 정리가 가장 큰 절감 항목이다.

## 2. 파일 수명표 (코드 기준, 1차)

| File | Created by | Consumer | Needed after success | Persistent? |
|---|---|---|---|---|
| 업로드 원본 | `create` | `analyze` (ingest) | 아니오 — `upload.unlink`로 삭제됨 | 아니오 |
| canonical WAV (`inputs/<asset>`) | `ingest_file` | 모든 단계, 재생 | 예(재생/검증) | 예 |
| 모델 원출력 (`jobs/<id>/result/stems`) | `worker`/`roformer_runner` | 다음 단계, `web/` 복사 | 아니오 (최종 생성 후) | **예 (현재)** |
| evidence stem(mega7), 복원 중간 | 각 단계 | routing | 아니오 | **예 (현재)** |
| routing 중간 (`*-routed-v1.wav`, `remaining-*`) | `web_server`/routing 모듈 | 다음 routing | 아니오 | **예 (현재)** |
| 최종 13 트랙 (`web/<id>/…`) | 마지막 단계 | 재생·다운로드 | **예** | 예 |
| record.json | `save` | UI | 예 | 예 |
| previews / enhanced / bundles (`web/previews|enhanced|bundles/<id>`) | 재생 캐시, clarity | UI | 캐시 | 예, 분석 삭제 때만 정리 |
| 전체 ZIP (`web/archives/<id>_<fp>.zip`) | `archive` | 다운로드 | 아니오(요청 시 재생성 가능) | **예 (현재: 영구 캐시)** |
| `.partial` 파일 | 각 쓰기 | 완료 시 rename | 아니오 | 실패/kill 시 남을 수 있음 (reaper 미확인) |
| 로그/벤치마크 산출물 | 평가 스크립트 | 개발 | 아니오 | 개발용 (`data/commercial-eval`, git 제외) |

삭제 경로: `delete`는 해당 분석의 job, asset, previews/enhanced/bundles/archives를 지우고 다른 분석이 쓰는 job/asset은 보존한다(코드 확인). 성공 직후 중간 WAV를 지우는 로직은 **없다**.

## 3. 계획 (미구현)

1. `KEEP_INTERMEDIATES` (개발 true / production 기본 false). 성공 시 RAW validation·restoration이 끝난 뒤에만 중간 산출물(`jobs/*/result`의 모델 출력, routing 중간, RAW stem)을 삭제. 실패 시 진단용 짧은 TTL을 명시 설정으로만 허용.
2. 전체 ZIP: 영구 캐시 대신 요청 시 스트리밍 생성 후 임시 파일 삭제(또는 짧은 TTL). 라이브러리의 영속 자산이 되면 안 된다.
3. 시작 시 reaper: `*.partial`, `.partial_*`, 소유자 없는 `result.partial`, 레코드가 없는 job/asset 정리. 삭제는 멱등.
4. 저장 포맷 비교 벤치마크(float32 WAV / PCM24 WAV / FLAC24 + 요청 시 WAV): 크기, 인코딩/디코딩 CPU, Web Audio 재생, 다운로드 지연, 오디오 차이. 측정 전 변경 금지. 현재 float32가 크기의 2/3 이상을 차지하므로 가장 큰 후보.
5. 반복 분석(1/10/30회) 후 RSS, GPU allocated/reserved, 핸들, temp 디렉터리 수, 디스크, 스레드 수가 기준선으로 돌아오는지 측정. 시나리오: 정상, 단계 중간 실패, 프로세스 kill, 서버 재시작, 사용자 삭제, 동일 음원 재분석, 실패 재시도.
6. 곡 길이 1/3/5/10/15분 × preset 2/6/13: scratch 피크, 완료 후 영구 용량, 임시/영구 파일 수, 정리 시간, ZIP 피크, RAM, VRAM.

## 4. 현재 알려진 위험 (확인됨 / 미확인)

- 확인: 위 1절의 중간 산출물 영구 보관, ZIP 영구 캐시.
- 미확인: 실패/kill 후 남는 파일, 모델 중복 로드, 핸들/메모리 누수. 측정 전에는 "문제 없음"으로 간주하지 않는다.
