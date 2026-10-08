# Output / Storage Resource Optimization — 구현 결과

모든 수치는 이 저장소에서 직접 측정했다. 측정하지 않은 항목은 "미측정"으로 표시했다. 분리 모델·라우팅·RULES·STRENGTH·추론 파라미터·저장 포맷(float32 WAV)은 바꾸지 않았다.

## 1. 한 줄 요약

| 항목 | 이전 | 이후 |
|---|---|---|
| 90 s 13트랙 1건의 영구 용량 | 2,105 MB (127 파일) | **424 MB (58 파일, 그중 사용자 결과 394 MB + 원본 30 MB)** |
| 90 s 6트랙 / 2트랙 | 318 / 106 MB | 212 / 91 MB |
| 전체 ZIP | 분석마다 영구 캐시 | 요청마다 임시 파일, 응답 후 삭제 |
| `data/` 전체 (du) | 393,249 MB | **99,895 MB (−293.4 GB)** |
| 디스크 여유 (C:) | 101.7 GB | **426.5 GB** |

## 2. 영구 저장 계약 (분석 1건)

```
<data-root>/web/<analysis_id>/
├── record.json        UI/API 레코드
├── manifest.json      영구 자산의 단일 진실 공급원: 자산별 family, 경로, sha256, bytes
├── original.wav       canonical 원본 (재생·검증용)
└── final/<family>.wav 사용자에게 제공하는 최종 stem
```

- 정리 로직은 파일 이름을 추측하지 않는다. 최종 stem과 원본을 `final/`·`original.wav`로 **옮기고** `manifest.json`에 등록한 뒤, 그 외의 모든 파일(모델 원출력, evidence, routing 중간, 중간 asset, 업로드 복사본)을 지운다.
- `jobs/<job>/job.json`과 `attempts/*` 로그(수 KB)는 남는다. 실패 추적과 `WebLibrary.delete`의 참조 탐색에 쓰인다.
- 경로 이름은 `storage/`로 바꾸지 않았다. 지금 구조는 데이터 루트 한 곳 아래 `web/`(영구 결과), `jobs/`·`inputs/`(스크래치), `models/`다. `job_service`·`ingest`가 `jobs/`·`inputs/`를 직접 쓰고 기존 레코드·테스트·다른 작업이 그 경로에 의존해서, 이름 변경은 위험 대비 이득이 작다고 판단했다. 대신 영구/임시의 경계를 코드(`lifecycle.py`)와 테스트(`contract_violations`)로 고정했다. `.gitignore`에는 `storage/`, `scratch/`, `generated/`, `benchmark-runs/`를 추가했다.
- 스크래치를 `scratch/<run_id>/` 한 곳으로 모으는 작업은 **미구현**이다. 현재 스크래치는 `jobs/`·`inputs/`이고, 성공/실패 직후 `finalize`가, 서버 기동 시 `reap`이 정리한다.

## 3. 설정

| 이름 | 기본 | 의미 |
|---|---|---|
| `MUSIC_KEEP_INTERMEDIATES` | 꺼짐 | 켜면 중간 산출물을 지우지 않는다 (개발/벤치마크). 평가 스크립트와 `conftest.py`가 켠다. |
| `MUSIC_KEEP_BENCHMARK_AUDIO` | 꺼짐 | 켜면 벤치마크의 비교 WAV와 라이브러리를 남긴다. 기본은 report/metrics만 남김. |
| `MUSIC_CACHE_TTL_HOURS` | 24 | 재생 미리듣기 등 재생성 가능한 캐시의 보관 시간. |

`MUSIC_RELEASE_PROFILE`과 같은 곳(`.env` + 환경 변수, `auth.load_settings`)에서 읽는다.

## 4. 파일 수명표 (실제 코드 기준)

| Path/Pattern | Creator | Consumer | 처리 중 필요 | 성공 후 필요 | 실패 후 필요 | Persistent? |
|---|---|---|---|---|---|---|
| 업로드 임시 파일 | `create` | `analyze` | 예 | 아니오 (`upload.unlink`) | 아니오 | 아니오 |
| `inputs/<upload asset>/{canonical,original,manifest}` | `ingest_file` | 모든 단계 | 예 | canonical만 → `web/<id>/original.wav`로 이동, 나머지 삭제 | 아니오 (삭제) | 아니오 (원본은 이동) |
| `inputs/<중간 asset>/` (stem 재투입용 복사본) | `ingest_file` | 다음 단계 | 예 | 아니오 | 아니오 | 아니오 |
| `jobs/<job>/result/stems/*.wav`, `manifest.json` | worker | 다음 단계, `web/`로 복사 | 예 | 최종 stem만 `final/`로 이동, 나머지 삭제 | 아니오 | 아니오 |
| evidence stem (mega7 등) | worker | routing | 예 | 아니오 | 아니오 | 아니오 |
| routing 중간 (`*-routed*`, `remaining-*`, `guitar-residual`) | `web_server` + routing 모듈 | 다음 routing | 예 | 아니오 | 아니오 | 아니오 |
| `*-before-*.json` 롤백 백업 | recovery 단계 | 개발 | 아니오 | 아니오 | 아니오 | 아니오 |
| 최종 stem | 마지막 단계 | 재생·다운로드·ZIP | 예 | **예** | 아니오 | **예** (`final/`) |
| `record.json` | `save` | UI | 예 | 예 | 예 (실패 사유) | 예 |
| `manifest.json` | `lifecycle.promote` | 계약 검사 | - | **예** | - | **예** |
| `jobs/<job>/job.json`, `attempts/*/worker.log` | `JobService` | 삭제 시 참조 탐색, 진단 | 예 | 작은 추적용 | 예 | 예 (KB) |
| `web/previews/<id>/…` | 재생 요청 | 재생 | - | 캐시 | - | TTL 24h 후 삭제 |
| `web/enhanced`, `web/bundles` (clarity) | clarity 기능 | 다운로드 | - | 캐시 | - | 분석 삭제 시 삭제 (clarity 제거 예정) |
| `web/archives/dl-<uuid>.zip` | `archive()` | 한 번의 다운로드 | - | 아니오 | - | **아니오** (응답 후 삭제, 1시간 넘으면 sweep) |
| `*.partial`, `inputs/.partial_*`, `result.partial` | 각 쓰기 | rename | 예 | 아니오 | 아니오 | 아니오 (sweep) |
| 벤치마크 `library/`, `evaluation-*`, `without-recovery`, `comparison.html` | 평가 스크립트 | 비교 청취 | 예 | 아니오 | 아니오 | 아니오 (옵션 시 유지) |
| 벤치마크 report/metrics/prepared | 평가 스크립트 | 문서·재채점 | - | **예** | 예 | 예 (KB~MB) |

## 5. 라이프사이클

1. 성공: `save(SUCCEEDED)` 직후 `finish_outputs` → `lifecycle.finalize(success=True)`.
   `promote`(최종 stem·원본을 `final/`·`original.wav`로 이동, `manifest.json` 기록, 레코드 경로 갱신) → (선택) `after_promote` 검증 → 나머지 삭제. 2트랙/6트랙의 조기 return 경로도 같은 호출을 한다(테스트가 `SUCCEEDED` 저장 횟수와 `finish_outputs` 호출 횟수를 비교).
2. 실패: `finalize(success=False)` — 사용자에게 전달된 것이 없으므로 `record.json`과 job 추적 파일만 남기고 전부 삭제.
3. 서버 기동: 실행 중으로 남은 레코드를 FAILED로 표시 → `cleanup_unfinalized`로 정리 → `reap`(오래된 `.partial`, 옛 영구 ZIP, TTL 지난 캐시). 실행 중인 job(종료 상태가 아닌 것)과 활성 분석 폴더는 건드리지 않는다.
4. 참조 안전: 다른 분석 레코드나 pipeline manifest가 이름을 부르는 job/asset(그 job이 쓰는 asset 포함)은 삭제하지 않는다 (`WebLibrary.delete`와 같은 규칙).
5. 모든 삭제는 best effort + 멱등: 실패는 결과의 `errors`에 남고 분석을 실패시키지 않는다. `promote`는 중간에 실패하면 이동을 되돌린다.
6. 사용자 삭제: 정리 이후에도 `delete`가 정상 동작함을 테스트로 확인 (남은 job.json으로 asset을 찾아 지움).

## 6. 저장소 벤치마크 (90 s 클립, `MUSIC_KEEP_INTERMEDIATES` 1 → 0)

`scripts/storage-benchmark.py`, 원자료 `OUTPUT_STORAGE_BENCHMARK.json`. 스크래치는 0.5 s 간격 샘플링.

| preset | 구분 | 처리 시간 | peak scratch | 완료 후 영구 | 영구 파일 수 | 사용자 결과(최종 stem) | 정리 시간 | 회수 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| commercial_2 | 이전 | 21 s | 106 MB | 106 MB | 13 | 61 MB | - | - |
| commercial_2 | 이후 | 21 s | 106 MB | **91 MB** | 11 | 61 MB | 0.05 s | 15 MB |
| commercial_6 | 이전 | 41 s | 318 MB | 318 MB | 28 | 182 MB | - | - |
| commercial_6 | 이후 | 42 s | 318 MB | **212 MB** | 21 | 182 MB | 0.08 s | 106 MB |
| commercial_13 | 이전 | 225 s | 2,105 MB | 2,105 MB | 127 | 394 MB | - | - |
| commercial_13 | 이후 | 238 s | 2,105 MB | **424 MB** | 58 | 394 MB | 0.67 s | 1,681 MB |

- 이전 13트랙 영구 용량 내역: web 803 + jobs 969 + inputs 348 MB. 이후에는 사용자 결과 394 MB + 원본 30 MB.
- 모든 경우 합계 오차 ≤ 8.8e-8, 재생 미리듣기·전체 ZIP 생성 정상. ZIP 임시 파일 크기는 최종 stem 합계와 같다(13트랙 약 394 MB 규모, 2트랙 61 MB 측정) 그리고 다운로드 후 0개가 남는다.
- **peak scratch는 줄지 않았다.** 정리는 분석이 끝난 뒤 한 번 하므로 처리 도중 최대 사용량은 그대로다 (13트랙 90 s에서 약 2.1 GB, 곡 길이에 비례). 단계별 즉시 삭제는 미구현이며 필요하면 별도 작업.
- 영구 파일 58개 = 최종 13 + 원본 + manifest + record + 7개 job의 추적 파일(job.json, 로그 등).

## 7. 반복 실행 누수 점검 (같은 프로세스, commercial_6, 5 s 클립, 30회, 절반은 삭제)

`scripts/resource-leak-check.py`, 원자료 `OUTPUT_LEAK_CHECK_COMMERCIAL_6.json`. 추론은 job마다 별도 worker 프로세스에서 일어나고 끝나면 종료되므로 서버 프로세스의 GPU allocated/reserved는 측정 대상이 아니다(서버 프로세스는 CUDA를 쓰지 않음). 대신 장치 전체 사용량(nvidia-smi)을 기록했다.

| 지표 | 초기(0회) | 1~3회 (초기화 구간) | 6~30회 (정상 상태) | 6~30회 추세 |
|---|---|---|---|---|
| RSS | 372.4 MB | 374.2~374.3 | 374.3~374.4 | **+0.003 MB/회 (사실상 0)** |
| 핸들 | 356 | 361 → 358 | 350 (고정) | 0 |
| 스레드 | 18 | 19 → 16 | 13~14 | -0.01 |
| 자식 프로세스 | 0 | 0 | 0 | 0 |
| 장치 GPU 사용량 | 1,562 MB | 1,497~1,543 | 1,489~1,804 | 변동 ±150 MB, 추세 없음(-2.5 MB/회) |
| 영구 디스크 | 0 | 11.8 MB | 분석 1건당 11.8 MB, 21 파일 (생존 분석 수에 비례) | 삭제한 분석은 정확히 0으로 복귀 |
| `.partial`/ZIP 임시 | 0 | 0 | 0 | 0 |

- 처음 1~5회에 핸들이 361에서 350으로, 스레드가 19에서 13으로 **줄었다** (지연 초기화 후 안정화). 5회 이후 지속적으로 증가하는 값은 없다.
- 디스크 증가는 누수가 아니라 살아남은 분석의 최종 결과다(15건 × 11.8 MB = 177 MB, 측정값 176.9 MB).
- 한계: 5 s 클립·단일 프로세스. 장시간 서버, 동시 다운로드, 90 s 곡 반복은 미측정.

## 8. 기존 라이브러리(legacy) 압축 — `data/separation`의 분석 50건

분석은 삭제하지 않고 중간 산출물만 정리했다 (`scripts/compact-legacy-library.py`). 분석별로 먼저 검증하고, 하나라도 불확실하면 SKIP.

검증 항목: 성공 상태 / (model, separation_version)별 stem 계약과 일치 / 원본 존재 / 모든 WAV가 열림·44.1 kHz 스테레오·원본과 같은 프레임 수 / 길이가 레코드와 일치 / NaN·Inf 없음 / 레코드의 sha256과 일치 / 합계 오차 ≤ 2e-6 (보장되는 버전) / 다른 분석과 파일·job·asset 공유 없음 / 실행 중인 분석 없음. 적용 시에는 이동 후 파일 크기를 다시 확인하고 어긋나면 삭제하지 않는다.

| 결과 | 건수 |
|---|---|
| 압축 | **49** |
| SKIP | 1 (FAILED 상태인 millsage 분석, 건드리지 않음) |
| 검증 실패(이동 후 불일치) | 0 |

- `data/separation`: 158,724 MB → 66,119 MB (du 기준 −92.6 GB; 스크립트가 센 삭제 바이트는 100.1 GB). 분석 레코드와 최종 stem은 그대로이며 `web/`은 42.9 → 44.6 GB(최종 stem이 `final/`로 이동해 들어옴), `jobs/` 78 → 1.9 GB, `inputs/` 34 → 6.2 GB.
- 압축 후 49건 모두 `contract_violations == []`, 모든 stem이 열림, 라이브러리 목록 86건(분석 50 + 기존 단독 job 항목 36) 정상, 13트랙 분석의 미리듣기와 758 MB ZIP 생성 확인.
- 남은 `jobs/`(272개 폴더, 1.9 GB)와 `inputs/`(88개, 6.2 GB)는 분석에 연결되지 않은 기존 단독 job 항목(라이브러리 목록에 보이는 것)과 FAILED 분석의 자산이다. 사용자에게 보이는 항목일 수 있어서 건드리지 않았다.
- 서버 프로세스가 이미 떠 있다면 **재시작해야** 새 코드(정리·ZIP)가 적용된다. 기존 코드도 새 경로(`final/`)를 레코드대로 읽으므로 재생은 문제없다.

## 9. 테스트/벤치마크 산출물 정리

`scripts/storage-inventory.py` (기본 dry-run, `--apply`로 삭제). 규칙: git 추적 파일 삭제 금지, 체크포인트/설정 확장자 삭제 금지(단, `data/separation/models`와 같은 inode를 공유하는 하드링크 별칭은 이름만 제거), 규칙에 안 맞는 파일은 유지, 삭제 후에도 남는 `prepared.json`의 source가 사라지면 삭제 거부.

분류 (삭제 전에 `prepared.json`의 source 1,509건이 모두 존재함을 확인):

| 종류 | 처리 | 내용 |
|---|---|---|
| canonical source / fixture | 유지 | `data/separation/{models,tools}`, 외부 데이터셋(slakh, medleydb, philharmonia, freepats), `pad-eval/stems`·`tools`, 데모 mix·stems |
| regenerable generated input | 유지 | 케이스의 `mix.wav`, `references/`, `evaluation-references/` (다른 케이스가 의존: 48개 케이스가 `rainfall-40-60`, `slakh20-pad-15-30`의 references를 source로 씀) |
| generated model output | **삭제** | 벤치마크 `library/`, `evaluation-candidates/`, `evaluation-outputs/`, `without-recovery/`, `comparison.html`, 단계별 before/after WAV, part-studies, test-runs, test-tmp-*, 무효화된 12-stem 결과, 스모크/청취/탐침 산출물, head 연구 캐시 |
| report / provenance | 유지 | `report.json`, `prepared.json`, `case.json`, `run.json`, 기타 json/md/txt/csv |
| user library / backup | 유지 | `data/separation/{web,jobs,inputs}`(압축만), `data/reset-backups` |

- 삭제: **53,092개 파일, 191.6 GB 회수**(하드링크 제외 바이트). 삭제 후 source 의존성 검사 0건 깨짐.
- 무효화된 12-stem 결과(`pad-invalid-12stem`, `smoke-invalid-12stem`)의 근거는 문서(`COMMERCIAL_CLEAN_MIGRATION_KO.md` 17-1절)와 커밋 `59bd810`에 남아 있다. 대용량 오디오는 삭제.
- 지금도 `data/ground-truth/cases` 15.9 GB, `data/pad-eval/cases` 7.1 GB, `cases-v16` 4.7 GB가 남아 있는데, 전부 위의 "재생성 가능한 입력"(references·mix)이다.

### 삭제 전후 (du, MB)

| 위치 | 이전 | 이후 |
|---|---:|---:|
| `data/separation` | 158,724 | 66,119 |
| `data/ground-truth` | 111,092 | 18,009 |
| `data/pad-eval` | 78,269 | 13,028 |
| `data/commercial-eval` | 27,405 | 66 |
| `data/part-studies` | 9,514 | 9 |
| `data/reset-backups` | 2,322 | 2,322 (유지) |
| `data/test-runs`, `test-tmp-*`, `sample`, `sample-b` | 약 6,100 | 약 340 (소스 stem/mix만) |
| **`data/` 합계** | **393,249** | **99,895 (−293.4 GB)** |
| C: 여유 공간 | 101,661 | 426,479 |

### 남은 가장 큰 디렉터리 (du)

`separation/tools/AudioSep` 3.5 GB · `tools/CLAPSepInference` 2.4 GB · 분석 `analysis_b7ad…` 1.8 GB · `ground-truth/cases/stability-v11…v16` 각 1.6 GB(references/mix) · `models/melband_karaoke` 1.6 GB · `models/mega53_3head` 1.4 GB · 라이브러리 분석 폴더들(각 1.1~1.4 GB, 사용자 결과). `reset-backups`는 2.3 GB.

## 10. 무결성 점검 (정리 후)

| 점검 | 결과 |
|---|---|
| 단위 테스트 (`.venv`) | **323 passed, 1 skipped, 0 failed** (정리 테스트 16개 포함) |
| 프런트엔드 빌드 | 성공 (`vite build`) |
| 서버 기동 | `python -m music_analyzer.web_server --help` 정상, `WebLibrary` 기동·sweep 정상 |
| release gate | `validate_production` 통과; commercial_2/6/13 모두 problems 없음, `commercial_gate`가 `data/separation`의 체크포인트 SHA256 고정값과 일치 |
| 모델 레지스트리/체크포인트 | 7개 모델의 체크포인트·registration 존재 |
| 라이선스 빌드/체크 | 기존 매니페스트가 commercial_2/6 등록 때문에 stale이었음 → 재생성 후 `--check` 통과 |
| 신규 분석 end-to-end | 아래 |

### 신규 분석 1건의 전체 라이프사이클 (`scripts/lifecycle-e2e.py`, commercial_6, 5 s)

분석(6 stem, 정리 `removed`, 5.9 MB 회수) → 계약 위반 0, 분석 폴더에는 `final/{bass,drums,guitar,other,piano,vocals}.wav`, `manifest.json`, `original.wav`, `record.json`만 존재 → 미리듣기(5.0 s, 유한값) → 개별 WAV(1,764,088 bytes, 프레임 수 원본과 일치) → 전체 ZIP(7개 항목, `testzip` 통과) → ZIP 임시 파일 삭제 확인 → 분석 삭제 후 `web/jobs/inputs`에 남은 파일 0개.

## 11. 실패/복구 시나리오

| 시나리오 | 결과 | 검증 |
|---|---|---|
| 단계 중간 실패 | 레코드 FAILED, 중간·업로드 asset 삭제, 추적 파일만 남음 | `test_failure_cleanup…` |
| 프로세스 종료 / 서버 재시작 | 실행 중 레코드를 FAILED로 표시 → 시작 시 정리; 두 번째 재시작은 변화 없음 | `test_server_restart…` |
| 분석 삭제 | 정리 이후에도 정상 삭제 | `test_analysis_delete_still_works…` |
| 같은 파일 재분석 | asset/job id는 매번 새로 생성되어 서로 공유하지 않음 (코드 확인) | 공유 참조 보호 테스트 |
| 정리 중 실패 | `errors`에 기록, 분석은 유지, 재실행하면 이어서 정리 | `test_cleanup_is_idempotent`, `test_unverified_promotion…` |
| 다른 분석이 쓰는 job/asset | 삭제하지 않음 | `test_shared_job_and_asset…`, `test_asset_of_a_job_owned_by_someone_else…` |
| 활성 job / 활성 분석 | sweep이 건드리지 않음 | `test_active_job_and_active_analysis_survive_reap` |
| 동시 다운로드 | ZIP마다 고유 이름이라 서로 지우지 않음 | `test_download_zip_is_a_unique_temporary_file…` |
| 중간 산출물이 새로 생겨 정리 누락 | `contract_violations`가 이름과 무관하게 큰 잔여 파일을 잡음 | `test_contract_holds_after_success…` |

## 12. 남은 위험 / 미구현

- peak scratch 미감소(분석 중 최대 사용량은 곡 길이에 비례, 13트랙 90 s에서 약 2.1 GB). 단계별 즉시 삭제가 필요하면 별도 작업.
- `scratch/<run_id>` 단일 스크래치 루트와 `storage/` 이름 통일은 미구현(2절 이유).
- 재생 미리듣기(PCM16)는 TTL 24시간 동안 영구 용량에 더해진다 (벤치마크에서 15~45 MB). clarity 번들/enhanced 캐시는 분석 삭제 때만 지워진다(clarity는 제거 예정).
- 라이브러리에 연결되지 않은 단독 job 항목 36건(jobs 1.9 GB + inputs 6.2 GB)은 유지했다.
- 서버 프로세스를 재시작하기 전까지 실행 중인 서버는 옛 코드(영구 ZIP, 정리 없음)로 동작한다.
- `data/reset-backups`(2.3 GB, 이전 라이브러리 초기화 시 백업)는 사용자 데이터라서 유지. 디스크 여유가 426 GB라서 급하지 않다. 삭제 여부는 사용자가 최종 결정.
- `data/separation/tools/{AudioSep,CLAPSepInference}`(5.9 GB)는 개발용 UNKNOWN 라이선스 경로의 도구라서 이번 범위에서 건드리지 않았다.
- 한 번에 한 서버가 같은 데이터 루트를 쓴다고 가정한다. 두 프로세스가 같은 라이브러리를 동시에 정리하는 경우는 미검증.
