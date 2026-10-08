# 서비스 적용·초기화 상태 — 2026-10-08

## 실행
```
scripts\start-web.ps1 -SkipBuild -LocalOnly     # 기본이 MUSIC_RELEASE_PROFILE=commercial (-Development 로만 개발 프로필)
```
commercial 프로필에서는 `release_presets.json`에 APPROVED로 올라간 preset(2/6/13)만 열린다. 허용되지 않은 preset은 generic 오류로 거절되고(fail-closed), 개발용 preset으로 대체되지 않는다.
UI id → runtime id 매핑은 `frontend/src/versions.js`의 `commercial` 필드(2트랙→commercial_2, 6트랙→commercial_6, 13트랙→commercial_13)이며, 서버가 `/api/release`로 알려 준 허용 목록만 업로드 화면에 나온다.

## 이번 변경
- `commercial_2/6/13` APPROVED(소유자 결정). 법적 근거는 `docs/COMMERCIAL_LICENSE_STATUS_KO.md`의 blocker 참조.
- 선명도(clarity) 기능 제거: UI 토글·노브·다운로드 선택 창, 서버 `/enhanced`·`/bundle` 경로, `clarity.js`. 다운로드는 분리 pipeline의 final WAV 그대로.
- 보컬 세부분리 버튼 제거(commercial 프로필에서는 서버가 거절하는 개발용 기능).
- 사용자 화면·API 응답에서 내부 모델명/라우팅 필드 제거(`vocal_source`, `cymbal_recovery`, `string_routing` 등). 번들 JS에도 모델명 문자열이 없다.
- 13트랙은 BETA·연구 중 표기 유지(`versions.js`의 `BETA_MODELS`, 업로드·결과 화면 문구).
- 테스트 격리: MySQL 통합 테스트는 임시 DB(`music_analyzer_test_<id>`)를 만들고 지운다. `conftest.py`가 서비스 data root(`data/separation/{web,jobs,inputs}`)에 쓰는 테스트를 실패시킨다. smoke/E2E 스크립트는 `KEEP_TEST_OUTPUT=1`이 아니면 결과를 지운다. 입력은 `separation/tests/fixtures/synthetic-mix-15s.wav`(합성, 2.6 MB).

## 초기화 (`scripts/reset-service-data.py`, 사용자 지시에 따라 적용)
- 삭제: `data/` 아래 생성물 전부(ground-truth, pad-eval, listening, commercial-eval, sample*, part-studies, 로그/JSON), `data/separation`의 web·jobs·inputs·로그·테스트 결과·runtime 내용, `__pycache__`, `.pytest_cache`.
- 유지: 소스·docs·git, `data/separation/models`(체크포인트와 registration), `tools`, `environment`, `runtime`(빈 디렉터리), 승인/라이선스 기록, 프런트 자산, `song/`.
- DB(`music_analyzer`): `analysis_owners`, `sessions`, `auth_attempts`, `user_consents` 비움. `users` 2명 유지. 스키마·인덱스·제약·`separation/sql` 그대로.
- 용량: 프로젝트 51.7 GiB → 14.0 GiB (`data` 9.0 GiB 남음: models 6.4, tools 2.6).
- 초기화 후 로그인한 사용자는 현재 약관·개인정보·만 14세 동의를 다시 요구받았고(동의 없이는 업로드 403), 재동의 후 정상 진행된다.

## 검증 요약
- smoke (`scripts/smoke-commercial.py`, 5케이스): commercial_2 2/2, commercial_6 6/6, commercial_13 13/13 stem, missing·unexpected 0, NaN/Inf 0, clipping 0, 합 보존 오차 ≤ 1e-7. 0.5초 입력은 의도대로 거절.
- 서비스 E2E (`scripts/service-e2e.py`, 실행 중인 commercial 서버 대상): 임시 계정 가입 → 동의 없이 업로드 403 → 권리 확인 없이 400 → 개발 preset 400 → 분석 → 미리듣기 → 개별 WAV → ZIP → ZIP 임시파일 0 → 분석 삭제 → 계정 삭제. commercial_2/6/13 모두 통과, 종료 후 users 수·분석 행·파일 수 원상복구.
- 성공 후 남는 것: `web/<id>/{final/,original.wav,manifest.json,record.json}` + job 기록(job.json, 로그, request/environment json, 6~12개 · 약 9 KB). 분석 삭제 시 모두 제거.
