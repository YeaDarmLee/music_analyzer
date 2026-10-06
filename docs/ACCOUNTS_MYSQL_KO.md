# 회원가입과 회원별 분석 격리

## 이 PC에서 실행

2026-10-06 로컬 MySQL의 `music_analyzer` DB에 DDL을 적용했습니다. 접속 설정은 Git에서 제외되는 프로젝트 루트 `.env`에 있습니다. DB 비밀번호는 소스와 문서에 기록하지 않습니다.

```powershell
cd C:\workspace\music_analyzer
.\scripts\start-web.ps1
```

<http://127.0.0.1:8780>에서는 로그인 없이 메인 화면을 볼 수 있습니다. 상단 로그인 버튼을 누르면 메인 위에 로그인 모달이 열리며 회원가입도 같은 모달에서 진행합니다. URL과 메인 화면은 유지됩니다. 비로그인 상태에서 새 분석을 누르면 로그인 모달이 열립니다. 회원가입 또는 로그인에 성공하면 모달이 닫히고 본인 라이브러리가 표시됩니다. 닫기 버튼·배경 클릭·Esc로 닫을 수 있으며, 키보드 포커스는 모달 안에서 순환하고 닫은 뒤 원래 버튼으로 돌아갑니다. 처리 중에는 중복 제출과 닫기를 막고 진행 표시를 제공합니다. 이미 실행 중이던 서버는 종료한 후 다시 실행해야 합니다. 이메일·이름·10~128자 비밀번호로 가입합니다. 로그인 후 본인이 생성한 분석만 보이며, 로그아웃 시 재생과 화면 상태를 정리합니다.

현재는 이메일 인증, 비밀번호 재설정, 회원 탈퇴, 관리자 화면이 없는 첫 번째 회원 기능입니다. 이메일은 로그인 식별자로만 사용하며 실제 이메일 소유권은 검증하지 않습니다.

## DB 초기화 / 다른 PC 설정

1. `.env.example`을 `.env`로 복사하고 MySQL 접속 정보를 입력합니다. 환경변수가 있으면 `.env`보다 우선합니다.
2. 기존 환경을 업데이트할 때 아래 드라이버 설치를 실행합니다. 신규 환경의 `bootstrap.ps1`에도 의존성을 반영했습니다.
3. 제공 DDL을 MySQL에서 실행하거나 초기화 명령을 사용합니다. 기존 테이블을 삭제하는 명령은 없습니다.

```powershell
.\.venv\Scripts\python.exe -m pip install "PyMySQL[rsa]==1.1.2"
.\.venv\Scripts\python.exe -m music_analyzer.auth --init-db
```

DDL: [separation/sql/001_accounts.sql](../separation/sql/001_accounts.sql)

| 테이블 | 역할 |
| --- | --- |
| `users` | 회원 ID, 정규화한 이메일, 이름, salt를 포함한 비밀번호 해시 |
| `sessions` | 세션 토큰의 SHA-256 해시, 회원 ID, 만료 시각 |
| `analysis_owners` | 분석 ID와 회원 ID의 소유권 관계 |
| `auth_attempts` | IP별 로그인·가입 요청 횟수 제한 |

현재 제공된 root 접속을 사용합니다. 외부 서비스 운영 시에는 초기화용 DB 계정과 런타임 계정을 분리하고, 런타임에는 이 네 테이블에 필요한 SELECT/INSERT/UPDATE/DELETE 권한만 부여합니다.

## 격리 범위

- 회원가입/로그인/로그아웃 외 분석 API는 서버 세션 인증을 요구합니다.
- 목록은 DB가 반환한 본인 소유 ID만 읽습니다. 업로드 본문이나 쿼리의 회원 ID는 사용하지 않습니다.
- 상세, 파형, 원본·분리음 재생, 구간 재생, Range 요청, WAV, ZIP, 선명도 결과와 세부분리 모두 소유권을 검사합니다. 다른 회원의 ID와 존재하지 않는 ID는 동일하게 404로 응답합니다.
- 새 업로드와 보컬 세부분리는 소유권이 DB에 저장된 뒤에만 작업 큐에 들어갑니다. DB 오류 시 분석을 시작하지 않습니다.
- 오디오 파일·진행 상태·결과 manifest는 기존 디스크 구조를 유지합니다. DB는 회원·세션·소유권을 관리합니다. 현재 격리는 애플리케이션 접근 권한에 의한 격리이며 회원별 OS 계정, 암호화 키 또는 GPU 프로세스 격리는 아닙니다.
- 작업 큐와 GPU는 회원들이 공유합니다. 회원별 사용량 제한·과금·공정 큐는 아직 없습니다.

기존 분석과 CLI 분석은 자동으로 누구에게도 배정하지 않습니다. 파일은 그대로 남지만 웹에서는 보이지 않습니다. 첫 가입자에게 기존 자료를 자동 공개하지 않습니다. 기존 결과 이전이 필요하면 소유자를 확인한 후 정확한 분석 ID만 `analysis_owners`에 추가해야 합니다. 여러 회원에게 같은 분석을 공유하는 기능은 없습니다.

## 세션과 네트워크

비밀번호는 PBKDF2-SHA256 600,000회와 무작위 salt로 저장합니다. 세션은 7일 후 만료되며 로그아웃하면 서버에서 삭제됩니다. 쿠키는 `HttpOnly; SameSite=Strict`이고, 브라우저의 localStorage에는 토큰을 저장하지 않습니다. 변경 요청에는 동일 출처 검사와 `X-Requested-With: MusicAnalyzer` 헤더를 요구합니다. 분석 응답·다운로드는 `Cache-Control: private, no-store` 또는 `no-store`를 사용합니다.

가입·로그인은 IP당 15분 동안 합계 30회까지 가능합니다. 프록시의 전달 헤더는 신뢰하지 않으므로 프록시 운영 시에는 앞단의 요청 제한 구성도 필요합니다.

`start-web.ps1`의 기본값은 로컬 전용으로 변경했습니다. `-LocalOnly`도 계속 사용할 수 있습니다. 외부 공개는 HTTPS 프록시를 준비하고 `.env`에 `AUTH_COOKIE_SECURE=1`을 설정한 뒤 명시적으로 `-PublicAccess`를 사용합니다. 이 Python 서버 자체는 TLS를 제공하지 않으므로 로그인 비밀번호를 공인 IP의 HTTP 주소로 전송하지 않습니다. 백엔드 포트는 프록시에서만 접근하도록 제한해야 합니다.

## API

| 메서드와 경로 | 동작 |
| --- | --- |
| `POST /api/auth/register` | `email`, `display_name`, `password`로 가입 및 세션 발급 |
| `POST /api/auth/login` | `email`, `password`로 세션 발급 |
| `GET /api/auth/me` | 현재 회원 조회, 미인증은 401 |
| `POST /api/auth/logout` | 현재 세션 폐기 |
| `GET /api/analyses` | 본인 분석 목록 |
| `POST /api/analyses` | 본인 소유로 업로드 및 분석 |

기존 분석 하위 API 경로는 유지하고 인증·소유권 검사만 추가했습니다. DB 오류는 503으로 처리하며 시작 시 DB와 테이블 연결을 검사합니다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m pytest -q separation/tests
# 로컬 실제 DB 통합 테스트. UUID 기반 임시 계정만 생성하고 테스트 후 정리합니다.
$env:MUSIC_TEST_MYSQL='1'
.\.venv\Scripts\python.exe -m pytest -q separation/tests/test_auth_mysql.py
```

실제 MySQL 테스트에서 회원가입, 중복 이메일, 잘못된 비밀번호, 로그인/로그아웃, 세션 만료, 재연결 후 소유권 유지, 두 회원의 목록·상세 분리를 검증합니다. 별도 HTTP 테스트는 원본·재생·구간 재생·Range·WAV·ZIP·후처리·세부분리의 소유권과 소유자 없는 기존 분석의 비공개를 검사합니다. GPU 추론 자체를 새로 실행하는 테스트는 아닙니다.
