# Music Analyzer Legal & Trust Implementation

작성: 2026-10-08. 이 문서는 법률 자문이 아니며, 사이트 문구가 **현재 구현과 일치하도록** 만든 작업 기록이다. 분리 파이프라인·모델은 변경하지 않았다.

## 1. 변경 개요

| 영역 | 내용 | 주요 파일 |
|---|---|---|
| 정책 버전 | `TERMS_VERSION` / `PRIVACY_VERSION` / `COPYRIGHT_POLICY_VERSION` / `RIGHTS_CONFIRMATION_VERSION`을 한 곳에서 관리, `GET /api/legal`로 프런트에 제공 | `separation/src/music_analyzer/legal.py` |
| 법적 페이지 | `/terms` `/privacy` `/copyright` `/licenses` (공통 `LegalPage`, 목차·앵커·모바일) | `frontend/src/LegalPage.vue`, `legalDocs.js` |
| 가입 동의 | 서버 검증 + `user_consents` 기록, 인증수단과 분리 | `auth.py`, `sql/002_consents.sql`, `AccountGate.vue` |
| 업로드 권리 확인 | 체크박스 + 서버 검증 + 분석 record 기록 | `web_server.py`, `App.vue` |
| 13트랙 BETA | 선택 카드·상세 패널·홈·라이브러리·결과 화면·FAQ | `versions.js`, `App.vue` |
| 문구 정리 | 마케팅 문구, 5단계 진행 설명, FAQ, 샘플 문구, Footer | `versions.js`, `App.vue`, `SamplePlayer.vue`, `SiteFooter.vue` |
| 삭제 | 분석 삭제(reference-safe), 회원 탈퇴, 업로드 원본 임시 파일 제거 | `web_server.py`, `auth.py` |
| OSS 고지 | 설치된 패키지·승인 파일에서 생성 | `scripts/build-license-notices.py`, `frontend/public/licenses/` |

변경하지 않은 것: 모델, 분리 알고리즘, 라우팅, 후처리, 이메일/비밀번호 로그인, HTTPS/도메인/결제/SNS 로그인.

## 2. 이용약관 (`/terms`)

(2026-10-08.2: 제3조의2 이용연령 추가 — 만 14세 미만은 가입할 수 없음.)

요청서의 제1~15조를 그대로 반영했다. `[운영자명]`, 시행일 `[YYYY-MM-DD]`는 placeholder다. 제8조에 13트랙 BETA 조항이 있다. 정책 버전(`2026-10-08`)은 페이지 상단에 표시되며 시행일과는 별개다.

## 3. 개인정보처리방침 (`/privacy`)

실제 코드·DB를 확인해 다음만 적었다.

| 항목 | 근거 |
|---|---|
| 이메일, 닉네임(`display_name`), 비밀번호 PBKDF2-SHA256 해시 | `users` 테이블, `auth.password_hash` |
| 세션 토큰의 SHA-256 해시, 7일 만료 | `sessions`, `SESSION_SECONDS=7일`. 만료 행은 다음 `new_session` 때 삭제 |
| 로그인 시도 제한: **접속 IP의 SHA-256 해시**와 시도 횟수, 15분 | `auth_attempts`, `throttle()`. 만료 행은 다음 인증 요청 때 삭제. 30회 초과 시 차단 |
| 동의 기록(항목·버전·시각) | `user_consents` |
| 업로드 오디오·파일명·길이·파일 해시·선택 구성·상태·생성일·소유 관계 | `web/analysis_*/record.json`, `inputs/*/manifest.json`, `analysis_owners` |
| 권리 확인 기록 | `record.json`의 `rights_confirmation_version`, `rights_confirmed_at` |
| 쿠키 `music_session`: HttpOnly, SameSite=Strict, Max-Age 7일, Secure는 `AUTH_COOKIE_SECURE` 설정에 따라 | `web_server.cookie()` |

문서에 쓰지 않은 것 / 일부러 한정한 것:
- "암호화 저장": at-rest 암호화가 없어 쓰지 않음.
- "복구 불가능한 파기/안전한 삭제": 구현은 일반 파일·레코드 삭제이므로 "서비스 저장소에서 삭제", "서비스에서 복구할 수 없음"으로 표현.
- 제3자 제공·위탁·국외 이전: 없음으로 기재. 웹 폰트는 자체 호스팅한다(`frontend/public/fonts/`, `src/fonts.css`; `@fontsource-variable` 5.3.0의 woff2와 OFL 라이선스 원문). 외부 폰트 서버 요청이 없으므로 방침 6항의 폰트 문장은 삭제했고, `frontend/legal.test.mjs`가 외부 폰트 호스트 참조를 막는다.
- 처리 위탁 업체 이름은 사용자 페이지에 넣지 않았다. 위탁 TODO는 아래 14절에만 둔다.

## 4. 저작권 정책 (`/copyright`)

요청서 1~8항 반영. 신고 연락처는 `[저작권 신고 이메일]`, `[저작권 담당자]` placeholder. 공개 게시물 URL을 요구하지 않고 분석 ID·파일명으로 대상을 특정하도록 했다. strike 횟수는 고정하지 않았다. "저작권법 제102조 면책" 류 문구는 없다(테스트가 확인).

## 5. OSS Notices (`/licenses`)

`/licenses`는 손으로 쓴 목록이 아니라 **상용 프리셋의 실제 실행 의존성**에서 만든다(15절). 산출물은 `frontend/public/licenses/`(`components.json`, `models.json`, `texts/*.txt`)이고 `scripts/build-license-notices.py`가 만든다.

- Python 구성요소: 상용 런타임 모듈(`release_presets.json`의 `runtime_modules`)을 AST로 읽어 import한 서드파티 패키지를 설치된 배포 패키지로 환산한다. 그 결과가 `license_notices.PYTHON`의 고지 항목과 정확히 일치해야 한다(누락·잉여 모두 실패). 저작권 문구는 LICENSE 파일의 `Copyright` 줄 또는 패키지 메타데이터를 그대로 쓴다.
- 이전에 "미사용"으로 분류했던 `librosa`는 vendored Mel-Band RoFormer가 import하므로 실제 의존성이다. `packaging`, `demucs`(워커가 import)도 포함된다. 하위 의존성(`soxr`, `lameenc`(LGPL) 등)은 내부 매니페스트에는 기록하되 공개 표에는 "직접 사용하는 구성요소만 실었다"는 문구를 둔다(TODO).
- 웹: `frontend/package.json`의 dependencies가 `WEB` 표와 일치해야 하며, 자체 호스팅 웹 폰트(Manrope, Noto Sans KR, OFL-1.1)를 포함한다.
- 모델 가중치: **APPROVED로 승격된 상용 프리셋이 실행하는 모델만** 나온다. 현재 승격된 프리셋이 없으므로 모델 목록은 비어 있고 페이지는 그렇게 안내한다. 역할·해시·파생 방식은 공개하지 않는다.

## 6. 회원가입 동의

```
Auth Provider (현재: 이메일/비밀번호)  →  legal.require_consents()  →  AuthStore.consent_statements()  →  Account
```

- UI: 닉네임(라벨만 변경, DB 필드 `display_name` 유지), [필수] 이용약관, [필수] 개인정보 수집·이용 체크박스와 "내용 보기"(새 탭), 개인정보 요약(목적·항목·보유기간·동의 거부).
- 서버: `register`가 `consents={"TERMS": <현재 버전>, "PRIVACY": <현재 버전>}`를 검증한다. 누락·구버전·`true` 같은 값이면 400이며 계정을 만들지 않는다. 계정과 동의 행은 **한 트랜잭션**으로 저장된다.
- **만 14세 이상 확인**: 가입 화면의 [필수] "만 14세 이상입니다" 체크박스를 `AGE14` 동의 항목으로 같은 `user_consents`에 기록한다(서버가 없으면 거부, 생년월일은 받지 않음). 법정대리인 동의 절차는 만들지 않고 14세 미만 가입을 제한한다. 정책 버전을 `2026-10-08.2`로 올렸으므로 기존 회원은 동의 게이트에서 새 약관·방침과 연령 확인을 다시 받는다.
- DB: `user_consents(user_id, consent_type, policy_version, accepted_at)`, PK `(user_id, consent_type, policy_version)`, `users` 삭제 시 CASCADE.
- SNS 로그인으로 바꿀 때: 새 Provider가 사용자 id만 확보하면 `require_consents` + `consent_statements`를 그대로 재사용한다. 이메일/비밀번호에 종속된 코드는 `register`뿐이다.
- **현재 정책 동의 게이트**: `/api/auth/me`·로그인 응답에 `consent_required`(현재 TERMS/PRIVACY 버전 둘 다 없으면 true)가 실린다. true면 화면이 동의 대화상자(`ConsentFields` 재사용)로 막고, 서버도 `/api/analyses*` 조회·생성을 403으로 거부한다. 동의는 `POST /api/auth/consent`로 `user_consents`에 기록한다. 분석 삭제·회원 탈퇴는 동의 없이도 가능하다. 정책 버전을 올리면 모든 회원에게 같은 게이트가 다시 적용된다.

## 7. 업로드 권리 확인

- 버전 선택 단계의 "분석 시작하기" 바로 위 체크박스 + 안내 문구 + `/copyright` 링크. 미체크 시 버튼 비활성, 제출 함수도 한 번 더 차단한다.
- 서버: `POST /api/analyses?preset=..&rights=<RIGHTS_CONFIRMATION_VERSION>`. 값이 없거나 현재 버전과 다르면 400(`업로드한 음원의 이용 권한을 확인해 주세요.`), 파일·레코드·소유권을 만들지 않는다.
- 기록: `record.json`에 `rights_confirmation_version`, `rights_confirmed_at`(UTC). 이는 사용자가 확인했다는 사실만 저장하며 음원의 권리를 판단하지 않는다. 리드/코러스 세부분리(자식 분석)는 부모의 기록을 복사한다.

## 8. 데이터 보관/삭제

| 데이터 | 보관 | 삭제 |
|---|---|---|
| 업로드 임시 파일 `web/analysis_*/source.*` | 분석 준비(ingest) 직후까지 | **ingest 성공 직후 또는 실패 시 삭제(이번에 추가)** |
| 검증용 원본 사본·canonical.wav (`inputs/asset_*`) | 분석 삭제 전까지 | 분석 삭제·회원 탈퇴 |
| 단계별 job 결과·중간 asset (`jobs/job_*`, `inputs/asset_*`) | 분석 삭제 전까지 | 분석 삭제·회원 탈퇴 |
| 분석 record, 잔여 트랙, previews/enhanced/bundles/archives 캐시 | 분석 삭제 전까지 | 분석 삭제·회원 탈퇴 |

`inputs/asset_*/original.*`는 `load_asset`의 무결성 검증이 요구하므로 분석 삭제 전에는 지울 수 없다. 방침에는 "임시 파일은 삭제, 분석용 오디오 사본(검증용 원본 사본·변환 오디오)과 결과는 분석 삭제·탈퇴까지 보관"으로 구분해 적었다.

**분석 삭제**(`DELETE /api/analyses/<id>`, 라이브러리 행의 "삭제"와 트랙 스튜디오의 "분석 삭제"):
1. 소유자 검증(다른 사용자·비로그인은 404/401, CSRF 헤더 필수).
2. `QUEUED`/`RUNNING`이면 거부(진행 중 삭제로 인한 고아 파일 방지).
3. 이 분석 record 전체에서 `job_*`/`asset_*` ID를 모으고, 각 job의 `job.json`이 가리키는 중간 asset을 더한다.
4. **다른 분석 record, pipeline manifest, 삭제 대상이 아닌 job**이 참조하는 job/asset은 지우지 않는다.
5. 남은 job·asset 폴더, previews/enhanced/bundles/archives 캐시, 분석 폴더를 삭제한 뒤 `analysis_owners` 행을 제거한다. MySQL과 파일시스템은 하나의 트랜잭션이 아니므로 순서는 파일 → DB이고, 파일 삭제가 중간에 실패하면 record와 소유 행이 남아 같은 요청을 다시 보내면 이어서 정리된다. record가 이미 없으면 소유 행만 해제해 200을 돌려준다(멱등). 테스트: `test_delete_is_retryable_after_a_file_failure_and_repeat_safe`.

## 9. 계정 삭제

`DELETE /api/auth/account`(상단 "회원 탈퇴" → 확인 대화상자): 진행 중 분석이 있으면 전체 거부 → 모든 소유 분석 삭제(8절 로직) → 한 트랜잭션으로 `analysis_owners`, `user_consents`, `sessions`, `users` 삭제 → 쿠키 만료. `auth_attempts`는 사용자와 연결되지 않은 IP 해시이므로 15분 만료에 맡긴다. 결제 기능이 없어 거래 기록 보존 로직은 만들지 않았다.

## 10. 13-track Beta Policy

기준: `versions.js`의 `BETA_MODELS = ['final_11', 'commercial_13']`. 2/6트랙에는 표시되지 않는다.

| 위치 | 표시 |
|---|---|
| 새 분석 선택 카드 | `13트랙` + `BETA` + `실험 기능` 배지, 요청서의 설명·보조 문구 |
| 선택 시 상세 패널 | BETA 배지 + 경고 박스(연구 및 개선 중인 기능…) |
| 홈 | 히어로 문구, `2 / 6 / 13 tracks · 13 BETA`, 트랙 플랜 13트랙 카드 BETA |
| 라이브러리 행 | 분석 구성 옆 `BETA` |
| 결과 화면 | 제목 옆 `BETA · 연구 중`(툴팁), 아래 안내 문구 |
| FAQ | "13트랙은 2트랙이나 6트랙보다 더 정확한가요?" 등 |
| 약관 | 제8조 |

## 11. Marketing Copy Changes

| 이전 | 이후 |
|---|---|
| DAW와 동일하게 트랙을 다뤄요 | 분리된 트랙을 스튜디오처럼 다뤄 보세요 |
| 용도에 따라 다른게 분리할 수 있어요 | 용도에 따라 다르게 분리할 수 있어요 |
| 풀밴드와 오케스트라 까지 | 풀밴드부터 오케스트라까지 |
| 노래방 MR · 보컬 연습 · 커버 작업 | 보컬 연습 · 반주 청취 · 곡 구조 파악 |
| 밴드 연습 · 파트 카피 · 파트별 커버 | 밴드 연습 · 파트 카피 · 악기별 청취 |
| 편곡 분석 · 악기별 학습 · 정밀 분석 | 편곡 분석 · 세부 악기 청취 · 실험적 분석 |
| 엉뚱한 트랙에 섞인 소리를 바로잡아요(원곡을 함께 살펴서) | 여러 단계의 분석으로 트랙 간 혼입을 줄여요 |
| 샘플: "저작권 문제가 없는 샘플" | 서비스 내 데모 사용 권한을 확인한 샘플 음원입니다. |
| Footer: Local workspace | 삭제, 정책 링크 5개 + © |

FAQ에 요청서의 신규 질문(13트랙 정확도, 스튜디오 멀티트랙 여부, 품질 편차, 업로드 가능 음원, 영상·공연·리믹스, AI 학습)과 "분석이나 계정을 삭제할 수 있나요?"를 추가했고, 기존 "올리는 음원은 누구 것이어야 하나요?"는 새 "어떤 음원을 올릴 수 있나요?"로 대체했다. 쓰이지 않던 `features/chipTracks/howTo` 배열(“내 PC에서 처리” 등 현재 사실과 다른 문구 포함)은 삭제했다.

## 12. Proprietary Technology Disclosure Boundary

UI·법적 페이지·OSS 고지에서 제거/비공개:
- 진행 단계 이름·설명: "원곡 악기 근거 확인", "피아노 내 심벌 보완/혼입을 드럼으로 이동", "기타 타악기 분류(원곡 근거 이용)", "어쿠스틱·일렉기타 분리", "반주에서 네 악기를 뺍니다" 등 → 5단계(음원 준비 / 기본 파트 분리 / 세부 악기 분석 / 품질 보정 / 결과 검증)로 대체. `versions.js`의 진행률 경계값만 실제 워커 진행과 연결된다.
- 모델 실행 순서·역할, Mega53 역할, evidence routing, STFT mask, phase coherence, threshold, RULES, STRENGTH, source→target 규칙, cymbal transfer, residual 계산, 튜닝값은 어디에도 쓰지 않았다.
- `/licenses`는 "무엇을 사용하는지"(이름·버전·저작권·라이선스·링크·전문)만 담고 "어떤 순서로 무엇을 실행하는지"는 담지 않는다. 모델 가중치 항목에도 역할·해시·파생 방식을 넣지 않았다.

처리 화면 제목은 서버의 `stage` 문자열 대신 진행률로 정한 5단계 라벨("세부 악기 분석 중" 등)을 쓰고, 실패 시 서버의 `error` 원문 대신 일반 안내를 보여 준다(`stageTitle`).

한계: `GET /api/analyses`와 `record.json`은 여전히 서버가 정한 `stage`/`error` 문자열을 그대로 내려보낸다. 화면에는 보이지 않지만 개발자 도구의 응답에서는 볼 수 있다. 파이프라인 파일(commercial-clean 작업 영역)의 `save(stage=...)` 문구를 일반화하면 해소된다. **14절 TODO.**

## 13. Tests

```powershell
.\.venv\Scripts\python.exe -m pytest separation\tests -q                       # 전체
$env:MUSIC_TEST_MYSQL='1'; .\.venv\Scripts\python.exe -m pytest separation\tests\test_auth_mysql.py -q   # 실제 MySQL
cd frontend; node --test legal.test.mjs trackGroups.test.mjs bufferPlayer.test.mjs; node src\analysisEstimate.test.js
```

신규 테스트(`separation/tests/test_legal_trust.py`, `test_auth.py`, `test_auth_mysql.py`, `frontend/legal.test.mjs`):

| 요구 | 테스트 |
|---|---|
| 동의 없이 가입 실패 | `test_signup_without_required_consent_creates_no_account` |
| 약관/개인정보 버전 저장 | `test_signup_records_terms_and_privacy_versions`, MySQL 통합 테스트 |
| 권리 확인 없이 분석 실패 | `test_analysis_requires_current_rights_confirmation` |
| 확인 시각·버전 기록 | `test_rights_confirmation_version_and_time_are_recorded` |
| 타인 분석 삭제 불가 / 본인 삭제 / 삭제 후 접근 불가 | `test_member_cannot_delete_...`, `test_member_deletes_own_analysis_...` |
| 공유 파일 보호 | `test_delete_keeps_files_still_referenced_by_another_analysis` |
| 진행 중 삭제 거부 | `test_running_analysis_cannot_be_deleted`, `test_withdrawal_is_refused_...` |
| 탈퇴 후 세션 무효·분석 접근 불가 | `test_withdrawal_invalidates_session_...`, MySQL `delete_account` |
| 업로드 원본 임시 파일 제거 | `test_upload_copy_is_removed_...` |
| `/terms` `/privacy` `/copyright` `/licenses` 접근 | `test_legal_pages_are_served_without_login` |
| 13트랙만 BETA | `legal.test.mjs` (1·2번) |
| 내부 알고리즘 문구 미노출, 마케팅 문구, placeholder, 방침 사실 | `legal.test.mjs` (3~6번) |

기존 테스트는 업로드에 `rights`가 필요해져 `test_auth.py`(업로드 요청 URL), `test_web_server.py::test_truncated_upload_is_not_enqueued`, `test_auth_mysql.py`(가입 payload)를 최소한으로 수정했다. UI는 브라우저에서 직접 확인했다(가입 → DB 동의 행 확인, 권리 확인 후 업로드, 실패 분석 삭제, 회원 탈퇴 후 DB 행 제거).

## 14. 외부 공개 전 점검표 (2026-10-08 외부 검토 반영)

반영함(코드): 만 14세 이상 확인, 방침 10항에 처리정지·동의 철회·이의제기, 동의 요약의 비밀번호/IP 표현·처리 근거 구분, UI preset ID ↔ commercial preset ID 매핑(`versions.js`의 `commercial`, 상용 모드에서 `/api/release` 목록과 매칭하고 그 id를 서버로 전송), 결과 화면의 "보컬 RoFormer + 악기"와 라이브러리의 모델명(RoFormer/Demucs/CLAPSep/AudioSep) 제거, "원본 FLOAT WAV" → "44.1kHz FLOAT WAV", `/licenses` 문구 정정, API 응답에서 `stage`/`error` 제거(`error_code: ANALYSIS_FAILED`만 제공, 원문은 `record.json`과 서버 stderr).

공개 전 반드시 사람이 처리(코드로 해결 불가):
- placeholder 실제값: `[운영자명]`, `[개인정보 보호 담당자]`, `[문의 이메일]`, `[저작권 신고 이메일]`, `[저작권 담당자]`, 시행일. 가능하면 개인정보 문의 전화번호도.
- **복구 불가능한 파기**: 현재 삭제는 `unlink`/`rmtree`/`DELETE`이다(방침은 이를 과장하지 않음). 운영 스토리지가 정해지면 영구 삭제 방식(암호화 저장 + 키 삭제 등)을 결정하고 방침 9항을 갱신한다. SSD에서는 덮어쓰기 삭제가 신뢰할 수 없다.
- HTTPS + `AUTH_COOKIE_SECURE=1`.
- commercial preset 승격 후 `build-license-notices.py` 재생성과 `--check`.

## 14-1. Remaining TODO

운영 전 필수:
- **HTTPS / Secure Cookie**: `.env`의 `AUTH_COOKIE_SECURE=1` 설정과 HTTPS 종단. 방침 8항은 Secure를 단정하지 않으므로 적용 후 문구 재확인.
- **정식 도메인**.
- **실제 문의 이메일 확정**: `[문의 이메일]`, `[개인정보 보호 담당자]`, `[저작권 신고 이메일]`, `[저작권 담당자]`.
- **운영자/사업자 정보 확정**: `[운영자명]`, 약관·방침 시행일 `[YYYY-MM-DD]`(`legalDocs.js`의 `EFFECTIVE`). 사업자 등록·통신판매업 표시는 결제 도입 전까지 넣지 않음.
- **SNS Login 도입 시 Privacy 업데이트**: 수집 항목(제공자 식별자 등), 제3자 제공/국외 이전 재검토. 동의 로직은 `legal.py`를 재사용.
- **Hosting provider 도입 시 개인정보 위탁 업데이트**: 서버 호스팅, 이메일 발송, SNS 로그인, 클라우드 스토리지 등을 쓰기 시작하면 방침 4~6항에 **실제 수탁자 이름·위탁 업무·보유기간·국외 이전 여부**를 확인해 기재. (현재 사용자 페이지에는 가상의 업체를 넣지 않았다.)
- **Payment 도입 시**: 전자상거래·환불·사업자 표시 정책, 법정 보존 거래 기록, 방침 개정.

권고(이번 범위 밖에서 발견):
- 정책 이전 버전 아카이브(`/privacy/<버전>`)는 없다. 방침 13항은 "시행일과 변경사항 안내"만 약속한다. 아카이브를 만들 때 문구를 추가한다.
- API는 `stage`/`error`를 내려주지 않는다. 내부 값은 `record.json`과 서버 로그에만 남는다. 로그 보관 정책은 운영 환경에서 정한다.
- **CLAPSep**(UNKNOWN 가중치)을 쓰는 심벌 단계가 `commercial_13` 경로에서 `commercial_gate`의 검사 대상(`MODELS`)에 없다. commercial-clean 작업에서 확인하고, 결론에 따라 `/licenses` 목록을 재생성해야 한다. `bs_roformer_vocal2`는 승인 대기(`UNKNOWN`)이므로 현재 `/licenses`에 없다.
- Mega53 가중치의 MIT 근거는 승인 파일에 "assumed per project owner"로 기록되어 있다. 출시 전 원문 선언 재확인 필요(감사 문서 NEEDS MANUAL VERIFICATION).
- 진단 스크립트(`scripts/diagnose-instrument-leakage.py`, `apply-synth-recovery.py`)는 `web/analysis_*` 기록을 읽을 수 있다. 운영 데이터 디렉터리에서 실행하지 말 것. 학습 코드는 저장소에 없으며 사용자 음원을 데이터셋으로 복사하는 경로는 확인되지 않았다.

## 15. Production Preset Isolation (release profile)

개발 동작은 그대로이고, 상용 모드는 **기본 비활성**이다. commercial_2/6/13의 최종 확정 전이므로 UI 프리셋 id(`basic_2`, `basic_6`, `final_11`)는 바꾸지 않았다.

**release profile**: `MUSIC_RELEASE_PROFILE = development | commercial`(`.env` 또는 환경변수, 기본 `development`). 알 수 없는 값(오타 포함)은 development로 취급하지 않고 모든 분석 요청을 거부한다(`release.profile`). `development`에서는 `release.py`가 아무것도 막지 않는다.

**allowlist**: `separation/configs/release_presets.json`의 `commercial.presets`. 항목마다 `status`(`VALIDATING` / `APPROVED`)를 두며, 상용 모드는 `APPROVED`만 실행한다. 현재 `commercial_13`은 `VALIDATING`이라 상용 모드를 켜도 어떤 분석도 허용되지 않는다. 프리셋 추가 절차: ① 파이프라인 작성 ② `release.STAGE_RESOLVERS`에 stage 목록 등록 ③ 설정에 `VALIDATING`으로 추가 ④ 검증 후 `APPROVED`로 승격. 설정에는 있는데 매핑이 없으면 오류다.

**서버 강제**(`web_server.py`):
- `WebLibrary.create`가 파일을 만들기 전에 `release.require_allowed(preset, data_root)`를 호출한다. `basic_2/6`, `final_10/11`, `instrument_roformer_6s`, `quality_6s`, 기본값 `final_10`을 API로 직접 보내도 400이다. 응답은 항상 같은 일반 문구이고 내부 사유는 서버 stderr에만 남는다.
- 리드/코러스 세부분리(`bs_karaoke`, UNKNOWN 가중치)는 상용 모드에서 거부한다.
- `run_stage`가 모든 단계 job의 stage preset이 승인된 프리셋의 stage 목록에 속하는지 다시 검사한다.
- 서버 시작 시 `release.startup_check`가 상용 모드의 설정·승인 프리셋을 검증하고 실패하면 시작하지 않는다.
- `GET /api/release`가 UI에 제공 가능한 프리셋을 알려 주고, 선택 화면은 그 목록만 보여 준다.

**fail closed**: 아래 중 하나라도 있으면 `ReleaseError`이며 development 프리셋으로 내려가지 않는다 — allowlist 설정 누락/손상, stage 매핑 누락·불일치(존재하지 않는 stage preset), 승인 상태가 `APPROVED`가 아닌 모델, 가중치 라이선스 UNKNOWN/BLOCKED, 승인 파일의 sha256과 레지스트리 sha256 불일치, 승인 sha256과 설치된 체크포인트 등록(`registration.json`) 불일치, 등록 파일 없음(`registry.commercial_gate`).

**commercial_13 CLAPSep 추적 결과**: `web_server.analyze`의 `commercial_13`(`is11` and `commercial`) 경로를 끝까지 따라갔다.
- 심벌 단계는 `commercial_cymbal.apply`(core4 drums 증거 + `piano_drum_refinement.cymbal_extract`, CLAP 마스크 없음)를 쓴다. `cymbal_extract`는 numpy/scipy만 쓴다.
- 이후 `percussion_refinement`, `string_routing`, `context_routing`, `apply_backing`은 mega7 증거와 STFT 마스크뿐이고 CLAP을 import하지 않는다.
- 결함 아님, 위험 요소 1건: 이전 코드는 `from .synth_recovery import run_for_library`를 `commercial` 분기 **앞에서** 무조건 import했다(호출은 안 됨, synth_recovery는 `part_study`를 함수 안에서 늦게 import). 이 import를 비상용(`else`) 분기 안으로 옮겼다. `final_11` 동작은 같다.
- 테스트: web_server의 `run_for_library` 호출 지점이 AST상 `commercial` 분기에서 도달 불가임을 확인, CLAPSep 진입점(`run_for_library`, `infer`, `part_study`, `clapsep_experiment`)을 함정으로 바꾼 채 실제 `commercial_cymbal.apply`를 실행, commercial_13 stage/model 목록에 CLAP 계열이 없음을 확인. 전체 GPU 파이프라인 실행으로는 검증하지 않았다.

**Production Dependency Manifest**: `docs/PRODUCTION_DEPENDENCY_MANIFEST.json`(내부용, 공개 금지: stage 목록·해시 포함)을 `release.manifest()`가 만든다. 프리셋 → stage preset → 모델(승인 상태, 승인/레지스트리 sha256, 가중치 라이선스, 코드 리비전·라이선스, blocker) + 런타임 패키지(import 스캔한 직접 의존성, 메타데이터로 계산한 하위 의존성, 선택적 미설치 import, 외부 도구)를 담는다. 직접 입력한 값은 `release_presets.json`의 모듈 목록과 `cryptography`(PyMySQL RSA 용) 한 줄뿐이다.

**/licenses 검증 구조**:
```
release_presets.json (APPROVED) → stage preset → 모델 → commercial_approval.json + 모델 레지스트리 교차 검증
runtime_modules → import 스캔 → 설치된 배포 패키지 → license_notices.PYTHON 대조
→ license_notices.build() → frontend/public/licenses/
```
빌드·테스트가 실패하는 경우: APPROVED 프리셋이 UNKNOWN/BLOCKED 모델을 참조, 모델에 `model_notices.json` 항목 없음, 런타임 패키지에 고지 없음, 고지가 쓰지 않는 패키지를 설명, `/licenses`에 production이 쓰지 않는 모델 표시, production 모델이 `/licenses`에서 누락, 승인 sha256 ≠ 레지스트리 sha256, 라이선스 원문 누락/변경. `scripts/build-license-notices.py --check`가 커밋된 산출물이 계획과 같은지 검사한다.

현재 상태: `commercial_13`은 `VALIDATING`(승인 파일상 모델은 모두 APPROVED로 보이나 프리셋 승격은 commercial-clean 검증 결과를 기다린다). 승격하면 위 검증이 즉시 적용되고 `/licenses`에 해당 모델이 나타난다. **commercial_2/6/13이 최종 확정된 것은 아니다.**
