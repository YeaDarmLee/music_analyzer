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
- 제3자 제공·위탁·국외 이전: 없음으로 기재. 단, **웹 폰트(Google Fonts)를 브라우저가 직접 불러온다**는 사실은 6항에 명시했다(`frontend/src/style.css` 첫 줄의 `@import`). 폰트를 자체 호스팅하면 이 문장을 삭제할 수 있다.
- 처리 위탁 업체 이름은 사용자 페이지에 넣지 않았다. 위탁 TODO는 아래 14절에만 둔다.

## 4. 저작권 정책 (`/copyright`)

요청서 1~8항 반영. 신고 연락처는 `[저작권 신고 이메일]`, `[저작권 담당자]` placeholder. 공개 게시물 URL을 요구하지 않고 분석 ID·파일명으로 대상을 특정하도록 했다. strike 횟수는 고정하지 않았다. "저작권법 제102조 면책" 류 문구는 없다(테스트가 확인).

## 5. OSS Notices (`/licenses`)

- `scripts/build-license-notices.py`가 설치된 패키지 메타데이터·LICENSE 파일과 `frontend/node_modules`, vendored MSST LICENSE에서 `frontend/public/licenses/components.json`, `texts/*.txt`를 생성한다. 저작권 문구는 LICENSE 파일의 `Copyright` 줄(없으면 패키지 메타데이터)을 그대로 쓴다. 추측으로 채운 값은 없다.
- 목록은 **실제 사용 구성요소만**: 웹 3개(Vue, @lucide/vue, @mdi/js), 서버 16개. `librosa`(import 없음), `lameenc`/`soxr`/`tqdm`(전이·미호출), CLAPSep/laion-clap, AudioSep, Demucs 가중치 등은 제외했다.
- FFmpeg는 서버 환경에 따라 LGPL/GPL 빌드가 다르므로 라이선스를 "빌드 구성에 따라 다름"으로 표기하고 공식 법적 고지 링크를 걸었다.
- **모델 가중치**는 `separation/configs/commercial_approval.json`에서 `APPROVED`인 것만 `models.json`에 들어간다. UNKNOWN 가중치는 나오지 않는다. 현재 2개 항목(Mel-Band RoFormer 가중치, MVSep Mega53 계열 가중치), 라이선스는 "MIT (저작자 선언)"으로 쓰고 "승인/상업 사용 가능"이라는 표현은 쓰지 않았다. 승인 파일이 바뀌면 스크립트를 다시 실행한다.

```powershell
.\.venv\Scripts\python.exe scripts\build-license-notices.py
```

## 6. 회원가입 동의

```
Auth Provider (현재: 이메일/비밀번호)  →  legal.require_consents()  →  AuthStore.consent_statements()  →  Account
```

- UI: 닉네임(라벨만 변경, DB 필드 `display_name` 유지), [필수] 이용약관, [필수] 개인정보 수집·이용 체크박스와 "내용 보기"(새 탭), 개인정보 요약(목적·항목·보유기간·동의 거부).
- 서버: `register`가 `consents={"TERMS": <현재 버전>, "PRIVACY": <현재 버전>}`를 검증한다. 누락·구버전·`true` 같은 값이면 400이며 계정을 만들지 않는다. 계정과 동의 행은 **한 트랜잭션**으로 저장된다.
- DB: `user_consents(user_id, consent_type, policy_version, accepted_at)`, PK `(user_id, consent_type, policy_version)`, `users` 삭제 시 CASCADE.
- SNS 로그인으로 바꿀 때: 새 Provider가 사용자 id만 확보하면 `require_consents` + `consent_statements`를 그대로 재사용한다. 이메일/비밀번호에 종속된 코드는 `register`뿐이다.
- 알려진 한계: 이 작업 이전에 가입한 계정은 동의 기록이 없다. 정책 개정 시 재동의 화면은 아직 없다(14절).

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

`inputs/asset_*/original.*`는 `load_asset`의 무결성 검증이 요구하므로 분석 삭제 전에는 지울 수 없다. 방침에는 "검증용 원본 사본을 분석 삭제 전까지 보관"으로 적었다.

**분석 삭제**(`DELETE /api/analyses/<id>`, 라이브러리 행의 "삭제"와 트랙 스튜디오의 "분석 삭제"):
1. 소유자 검증(다른 사용자·비로그인은 404/401, CSRF 헤더 필수).
2. `QUEUED`/`RUNNING`이면 거부(진행 중 삭제로 인한 고아 파일 방지).
3. 이 분석 record 전체에서 `job_*`/`asset_*` ID를 모으고, 각 job의 `job.json`이 가리키는 중간 asset을 더한다.
4. **다른 분석 record, pipeline manifest, 삭제 대상이 아닌 job**이 참조하는 job/asset은 지우지 않는다.
5. 남은 job·asset 폴더, previews/enhanced/bundles/archives 캐시, 분석 폴더를 삭제한 뒤 `analysis_owners` 행을 제거한다.

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

## 14. Remaining TODO

운영 전 필수:
- **HTTPS / Secure Cookie**: `.env`의 `AUTH_COOKIE_SECURE=1` 설정과 HTTPS 종단. 방침 8항은 Secure를 단정하지 않으므로 적용 후 문구 재확인.
- **정식 도메인**.
- **실제 문의 이메일 확정**: `[문의 이메일]`, `[개인정보 보호 담당자]`, `[저작권 신고 이메일]`, `[저작권 담당자]`.
- **운영자/사업자 정보 확정**: `[운영자명]`, 약관·방침 시행일 `[YYYY-MM-DD]`(`legalDocs.js`의 `EFFECTIVE`). 사업자 등록·통신판매업 표시는 결제 도입 전까지 넣지 않음.
- **SNS Login 도입 시 Privacy 업데이트**: 수집 항목(제공자 식별자 등), 제3자 제공/국외 이전 재검토. 동의 로직은 `legal.py`를 재사용.
- **Hosting provider 도입 시 개인정보 위탁 업데이트**: 서버 호스팅, 이메일 발송, SNS 로그인, 클라우드 스토리지 등을 쓰기 시작하면 방침 4~6항에 **실제 수탁자 이름·위탁 업무·보유기간·국외 이전 여부**를 확인해 기재. (현재 사용자 페이지에는 가상의 업체를 넣지 않았다.)
- **Payment 도입 시**: 전자상거래·환불·사업자 표시 정책, 법정 보존 거래 기록, 방침 개정.

권고(이번 범위 밖에서 발견):
- **Google Fonts 자체 호스팅**하면 방침 6항의 폰트 문장을 삭제할 수 있다.
- **재동의 절차**: 정책 버전이 바뀌면 기존 회원에게 새 버전 동의를 받는 화면과 `user_consents` 갱신이 필요하다. 이전 가입자는 동의 기록이 없다.
- **정책 이전 버전 보관**(`legalDocs.js`는 현재 버전만 보유). 방침 13항의 "이전 버전 제공"을 위해 개정 시 이전 본문을 별도로 보관해야 한다.
- **서버 `stage`/`error` 문자열**이 API 응답에 내부 단계명을 포함한다(12절). 파이프라인 작업이 정리된 뒤 일반화.
- 분석 실패 시 `error`에 서버 절대 경로가 들어가 사용자 화면에 표시된다(기존 동작).
- **CLAPSep**(UNKNOWN 가중치)을 쓰는 심벌 단계가 `commercial_13` 경로에서 `commercial_gate`의 검사 대상(`MODELS`)에 없다. commercial-clean 작업에서 확인하고, 결론에 따라 `/licenses` 목록을 재생성해야 한다. `bs_roformer_vocal2`는 승인 대기(`UNKNOWN`)이므로 현재 `/licenses`에 없다.
- Mega53 가중치의 MIT 근거는 승인 파일에 "assumed per project owner"로 기록되어 있다. 출시 전 원문 선언 재확인 필요(감사 문서 NEEDS MANUAL VERIFICATION).
- 진단 스크립트(`scripts/diagnose-instrument-leakage.py`, `apply-synth-recovery.py`)는 `web/analysis_*` 기록을 읽을 수 있다. 운영 데이터 디렉터리에서 실행하지 말 것. 학습 코드는 저장소에 없으며 사용자 음원을 데이터셋으로 복사하는 경로는 확인되지 않았다.
