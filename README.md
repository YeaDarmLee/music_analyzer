# music_analyzer

음원을 악기별로 분리하고 음악 분석·채보·악보 생성으로 확장하는 로컬 프로그램입니다.

현재 **WAV/FLAC/MP3를 입력해 곡 전체를 보컬·드럼·베이스·other의 4개 WAV로 분리하는 CLI**를 사용할 수 있습니다. RTX 3060에서 사용자가 제공한 약 3분 12초 MP3의 실제 분리와 파일 무결성을 확인했습니다. 기타·피아노를 추가하는 실험적 6-stem, 고품질 비교 설정과 로컬 청취 비교 페이지도 추가했습니다. Vue 웹 스튜디오를 추가했으며 MIDI·악보 생성은 후속 단계입니다.

S1 환경 검증·S2 오디오 입력을 마쳤고, S3 전체 곡 작업 실행·취소·복구·OOM 재시도 기능을 구현했습니다. 설계의 정상 곡 3개 완주 기준은 현재 **서로 다른 실제 곡 1/3**입니다. 분리 음질 청취 평가는 아직 수행하지 않았습니다.

## 회원가입과 회원별 분석

MySQL 기반 회원가입·로그인과 회원별 분석 접근 제어를 사용할 수 있습니다. 로컬 `music_analyzer` DB에 초기 스키마를 적용했으며 접속 설정은 Git 제외 파일 `.env`에서 관리합니다. 기존 분석은 소유자를 지정하기 전까지 웹 목록에 표시되지 않습니다.

[회원 기능·MySQL 설정 가이드](docs/ACCOUNTS_MYSQL_KO.md) · [DDL](separation/sql/001_accounts.sql)

## 웹 스튜디오

새 분석의 기본 출력은 **보컬·코러스·피아노·신디사이저·스트링·어쿠스틱기타·일렉기타·베이스·드럼·나머지** 10트랙입니다. 신디사이저·두 기타·현악은 공식 Mega53에서 선택한 4-head 모델로 원곡에서 추출합니다. 스트링은 검증한 `bowed_strings` 출력을 사용합니다. 기존 분석은 기존 결과를 유지하며 새 구성은 새 분석에 적용됩니다. 상세 실행/검증은 [최종 10트랙](docs/FINAL_TEN_TRACKS_KO.md)에 정리했습니다.

로그인 후 Vue 화면에서 파일 선택 → 자동 보컬/악기 분리 → 진행률 → DAW 형태 재생과 WAV/ZIP 다운로드를 사용할 수 있습니다. 최종 결과는 확정 RoFormer 보컬과 반주에서 분리한 악기 5개이며, 악기 모델이 추출한 보컬은 제외합니다.

```powershell
.\scripts\start-web.ps1
```

[웹 스튜디오 사용 가이드](docs/WEB_STUDIO_GUIDE_KO.md) · [로컬 화면](http://127.0.0.1:8780)

## 바로 분리하기

프로젝트 환경과 개발용 모델은 준비되어 있습니다. PowerShell에서:

```powershell
cd C:\workspace\music_analyzer
.\scripts\separate.ps1 -InputAudio 'C:\audio\sample.mp3'
```

또는:

```powershell
.\.venv\Scripts\python.exe -m music_analyzer.cli separate --input 'C:\audio\sample.mp3'
```

입력 범위는 WAV/FLAC/MP3, mono/stereo, 8–192kHz, 1초–15분, 최대 1GiB입니다. 원본을 보존하고 44.1kHz stereo 기준 오디오로 변환한 후 GPU로 분리합니다.

진행 상태와 job_id가 표시됩니다. 성공 결과 위치:

```text
data/separation/jobs/<job_id>/result/
  manifest.json
  stems/
    vocals.wav
    drums.wav
    bass.wav
    other.wav
```

other는 기타·피아노 등 나머지 소리가 섞인 결과입니다. 개별 기타 트랙으로 해석하지 않습니다. 출력은 원본과 같은 길이·시작점의 float32 WAV이며, clipping·개별 음량 정규화를 적용하지 않습니다.

## 품질 개선 후보와 기타·피아노 분리

이 PC에는 추가 모델도 준비되어 있습니다:

```powershell
.\scripts\separate.ps1 -InputAudio 'C:\audio\sample.mp3' -Preset quality_ft
.\scripts\separate.ps1 -InputAudio 'C:\audio\sample.mp3' -Preset quality_6s
```

quality_ft는 악기별 추가 학습 모델로 기존 4개 파트를 비교합니다. quality_6s는 원곡에서 기타·피아노를 포함한 6개 파트를 직접 추출합니다. quality는 같은 기본 모델에 구간 설정만 개선한 비교 후보입니다. 세 설정은 7.8초 구간·50% overlap·두 시간 이동 추론 평균을 사용합니다.

약한 연주를 유지하기 위해 noise gate나 구간별 음량 보정은 적용하지 않습니다. 모델 변경이 모든 누출·음량 흔들림을 해결했다고 판단하지 않으며 같은 구간을 들어 실제 개선을 확인합니다. 피아노는 실험적이며 6-stem의 other는 기타·피아노를 제외한 잔여 소리입니다.

[현재 곡의 비교 페이지](data/separation/comparisons/compare_5e132bd5f7c8403f84ef085fec7a5a06/comparison.html)를 브라우저에서 열면 기존·구간 개선·추가 학습·6-stem·원곡을 같은 위치로 바꿔 들을 수 있습니다. 실행 중인 [localhost 비교](http://127.0.0.1:8768/comparison.html)도 사용할 수 있습니다. 모든 청취 사본은 같은 고정 gain을 사용합니다.

다른 같은 곡의 결과를 비교하려면:

```powershell
.\.venv\Scripts\python.exe -m music_analyzer.cli compare-results --job-id 'job_기존ID' 'job_개선ID' --window '45:20'
```

새 PC에서는 prepare-model --model demucs_htdemucs_ft 또는 demucs_htdemucs_6s를 먼저 실행합니다. [S4 구현과 실측 결과](docs/audio-separation/09_S4_QUALITY_AND_6STEM_KO.md)를 참고하세요.

## 작업 상태·중단·재실행

다른 터미널에서 출력된 작업 ID를 사용합니다:

```powershell
.\.venv\Scripts\python.exe -m music_analyzer.cli job-status 'job_출력된32자리ID'
.\.venv\Scripts\python.exe -m music_analyzer.cli cancel-job 'job_출력된32자리ID'
.\.venv\Scripts\python.exe -m music_analyzer.cli inspect-result 'job_출력된32자리ID'
```

실행 터미널의 Ctrl+C도 취소를 요청합니다. 두 번째 Ctrl+C 또는 취소 유예 10초 초과 시 작업자와 자식 프로세스를 종료합니다. 프로젝트 내 정식 작업은 GPU당 하나만 실행하며, 추가 요청은 GPU_BUSY로 거절합니다.

강제 종료 이후:

```powershell
.\.venv\Scripts\python.exe -m music_analyzer.cli recover-jobs
.\.venv\Scripts\python.exe -m music_analyzer.cli retry-job 'job_실패하거나중단된32자리ID'
```

복구는 중단 상태를 정리합니다. 재실행은 기존 이력을 보존하고 새 job_id를 만듭니다. 작업 시작 시에도 복구를 시도합니다.

기본 설정에서 GPU OOM이 발생하면 기존 작업자를 종료한 뒤 등록된 memory_safe 설정으로 새 프로세스에서 한 번만 재시도합니다. 작은 내부 구간·cuDNN 비활성화를 실제 결과에 기록합니다. 변경된 구간 때문에 음질이 달라질 수 있습니다. 실패한 부분 출력은 정상 결과로 게시하지 않습니다.

## 입력만 등록하기

```powershell
.\.venv\Scripts\python.exe -m music_analyzer.cli ingest 'C:\audio\sample.mp3'
.\.venv\Scripts\python.exe -m music_analyzer.cli inspect-asset 'asset_출력된32자리ID'
.\.venv\Scripts\python.exe -m music_analyzer.cli separate --asset-id 'asset_출력된32자리ID'
```

등록 폴더는 data/separation/inputs/<asset_id>/이며 원본·canonical.wav·manifest.json을 저장합니다. ingest는 모델을 실행하지 않습니다. 재실행에서 등록 음원을 사용할 수 있습니다.

## 환경 확인과 테스트

```powershell
.\.venv\Scripts\python.exe -m music_analyzer.cli check-environment
.\.venv\Scripts\python.exe -m music_analyzer.cli smoke
.\.venv\Scripts\python.exe -m pytest -q separation/tests
```

smoke는 10초 합성 신호의 GPU 검사 도구입니다. 실제 파일을 넣을 경우 44.1kHz mono/stereo WAV, 1–60초, 최대 32MiB로 제한됩니다. 일반 전체 곡은 separate를 사용합니다.

새 PC에서는 Python 3.11/3.12와 FFmpeg/FFprobe를 준비한 후:

```powershell
.\scripts\bootstrap.ps1 -PythonExecutable 'C:\Python312\python.exe'
.\.venv\Scripts\python.exe -m music_analyzer.cli prepare-model
```

[현재 Windows/Python 3.12 의존성 목록](separation/requirements/windows-py312-cu121.lock.txt)은 버전 snapshot입니다. artifact hash를 포함하는 배포 lock은 아닙니다. 현재 venv 기반 interpreter는 Codex 제공 runtime이며 다른 PC에서는 별도 Python 설치가 필요합니다.

## 문서와 다음 단계

- [전체 제품 로드맵](docs/PRODUCT_ROADMAP_KO.md)
- [분리 설계 문서](docs/audio-separation/README.md)
- [피드백 검토](docs/audio-separation/05_FEEDBACK_REVIEW_KO.md)
- [S1 환경·모델 실행 검증](docs/audio-separation/06_S1_VERIFICATION_KO.md)
- [S2 입력·변환 검증](docs/audio-separation/07_S2_VERIFICATION_KO.md)
- [S3 전체 곡 분리·작업 검증](docs/audio-separation/08_S3_VERIFICATION_KO.md)
- [S4 품질 개선 후보·6-stem 비교](docs/audio-separation/09_S4_QUALITY_AND_6STEM_KO.md)

현재 같은 곡에서 품질 개선·6-stem 실행 비교를 완료했고, 다음은 사용자 청취와 실제 곡 다양성 검증으로 채택 후보를 확정하는 단계입니다. 모델 weights는 DEV_ONLY/UNRESOLVED이며 프로젝트 코드에 포함하거나 재배포하지 않습니다.

[S5 RoFormer 보컬·반주 후보 실행 및 비교](docs/audio-separation/10_S5_ROFORMER_VERIFICATION_KO.md) — 실제 두 곡 실행 완료. 청취 품질 채택과 개별 악기 모델 개선은 후속 검증.

[S6 확정 보컬 → 반주 악기 분리 실행](docs/audio-separation/11_S6_CASCADE_KO.md) — 기본 실행에 단계 연결 반영. 보컬 채택 확정, 악기 모델은 검증 중.

[S7 BS-RoFormer 악기 후보 비교](docs/audio-separation/12_S7_INSTRUMENT_ROFORMER_KO.md) — 같은 반주로 전체 곡 실행 완료. 슬랩 13–14초와 피아노 20–40초 청취 평가 대기.

[다른 음원 테스트 명령어 가이드](docs/audio-separation/13_TESTING_GUIDE_KO.md)

[S8 기타/other 재분리 실험](docs/audio-separation/14_S8_GUITAR_OTHER_REFINEMENT_KO.md) — 두 트랙만 재배분하는 후보, 최초 20초 비교. 청취 채택 대기.

[2026-10-05 종합 결과·채택 결정·남은 문제](docs/audio-separation/15_2026-10-05_DAILY_RESULTS_KO.md)
