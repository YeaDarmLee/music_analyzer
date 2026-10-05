# 다른 음원 테스트 가이드

이 문서는 현재 PC에 설치된 환경을 기준으로 한다. **확정 보컬은 Mel-Band RoFormer**, **새 악기 후보는 BS-RoFormer 6트랙**이다. 기본 pipeline은 아직 기존 Demucs 악기 모델을 사용한다. 아래 순서는 새 곡에서 보컬을 한 번 분리하고 같은 반주로 기존/새 악기 모델을 비교한다.

## 1. PowerShell에서 프로젝트 폴더 열기

Windows 터미널 또는 PowerShell을 열고 아래를 입력한다. 명령어를 위에서 아래로 같은 창에서 실행한다.

```powershell
Set-Location "C:\workspace\music_analyzer"
```

별도로 가상환경을 활성화할 필요는 없다. 모든 명령은 프로젝트의 Python을 직접 사용한다.

테스트 파일 경로를 지정한다. 아래 경로만 실제 파일로 바꾼다. 파일이 프로젝트 밖에 있어도 된다.

```powershell
$songPath = "C:\workspace\music_analyzer\테스트할 노래.mp3"
Test-Path -LiteralPath $songPath
```

True이면 파일을 찾은 것이다. False이면 경로를 수정한다. 지원 형식은 MP3/WAV/FLAC, 길이는 1초~15분이다. 경로의 공백·한글·괄호를 유지하려면 따옴표를 사용한다.

## 2. 보컬 + 기존 악기 모델 실행

```powershell
$run = & .\.venv\Scripts\python.exe -m music_analyzer.cli separate-pipeline --input $songPath | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "분리가 실패했습니다. 위 오류를 확인하세요." }
$run
```

화면에 진행 상태가 나오며 완료되면 pipeline_dir, manifest 경로가 나온다. 이 단계는 **RoFormer 보컬 → 반주 → 기존 Demucs 악기 분리**까지 실행한다. 한 번에 한 곡씩 실행한다.

생성된 기록을 읽는다.

```powershell
$pipeline = Get-Content -LiteralPath $run.manifest -Raw -Encoding UTF8 | ConvertFrom-Json
$pipeline.state
```

SUCCEEDED이면 완료다.

## 3. 동일 반주를 새 BS-RoFormer 악기 모델로 실행

```powershell
$newJob = & .\.venv\Scripts\python.exe -m music_analyzer.cli separate --asset-id $pipeline.instrumental_asset_id --preset instrument_roformer_6s | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "새 악기 모델 실행이 실패했습니다." }
$newJob.state
$newJob.job_id
```

SUCCEEDED이면 새 악기 결과가 만들어졌다. **이 단계는 원곡을 다시 넣지 않고, 2번에서 만든 반주를 사용한다.** 보컬은 다시 분리할 필요가 없다.

## 4. 전체 길이 결과 듣기

확정 보컬과 새 악기 파일은 서로 다른 작업 폴더에 있다. 아래 명령으로 연다.

```powershell
# 확정 보컬 vocals.wav와 전체 반주 instrumental.wav
Invoke-Item ("C:\workspace\music_analyzer\data\separation\jobs\" + $pipeline.vocal_job_id + "\result\stems")

# 새 모델의 악기 파일
Invoke-Item ("C:\workspace\music_analyzer\data\separation\jobs\" + $newJob.job_id + "\result\stems")
```

새 모델 결과의 bass.wav, drums.wav, guitar.wav, piano.wav, other.wav를 확인한다. 여기의 vocals.wav는 **반주에 남은 보컬의 진단용 추정치**다. 최종 보컬에는 첫 번째 폴더의 vocals.wav를 사용한다. other는 나머지 소리이며 특정 악기 하나가 아니다.

raw WAV는 원래 크기를 유지한 FLOAT 형식이다. 일부 재생기의 변환 방식에 따라 피크가 왜곡될 수 있으므로 모델 간 비교에는 아래 같은 gain의 청취 사본을 권장한다.

## 5. 기존/새 모델 비교 화면 만들기

비교 구간은 시작초:길이초로 지정한다. 아래는 10~18초, 20~40초다. **곡이 최소 40초 이상일 때** 그대로 사용한다.

```powershell
$comparison = & .\.venv\Scripts\python.exe -m music_analyzer.cli compare-results --job-id $pipeline.instrument_job_id $newJob.job_id --window 10:8 --window 20:20 | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "비교 화면 생성이 실패했습니다." }
Invoke-Item $comparison.page
```

기본 브라우저에서 comparison.html이 열린다. ‘분리 결과’를 기존 6트랙 / BS-RoFormer 악기 후보로 바꾸고 베이스·기타·피아노를 번갈아 듣는다. 같은 구간에서 모든 모델/트랙에 같은 고정 gain을 적용한다.

다른 구간 예:
- 13~18초: --window 13:5
- 1분10초~1분30초: --window 70:20
- 짧은 10초 음원: --window 0:10

--window를 반복해 추가할 수 있다. 끝 지점은 곡 길이를 넘으면 안 된다. 구간은 최대 10개, 각 길이는 최대 60초다. --window를 생략하면 20~40초, 70~90초, 135~155초가 적용되므로 짧은 곡에는 직접 지정한다.

### 파일로 열린 페이지에서 재생이 안 될 때

같은 PowerShell에서 아래 명령을 실행하고 브라우저 주소창에 http://127.0.0.1:8772/comparison.html 을 입력한다.

```powershell
& .\.venv\Scripts\python.exe -m http.server 8772 --bind 127.0.0.1 --directory $comparison.comparison_dir
```

서버를 쓰는 동안 터미널은 실행 중인 상태로 둔다. Ctrl+C로 서버를 종료한다. 포트가 사용 중이면 8773 등 다른 번호로 바꾸고 브라우저 주소도 같은 번호를 사용한다. 이전 8771 페이지는 기사개전 결과이며 새 곡으로 자동 교체되지 않는다.

## 보컬만 실행하거나, 새 악기만 실행하고 싶을 때

보컬만:
```powershell
& .\.venv\Scripts\python.exe -m music_analyzer.cli separate --input $songPath --preset vocal_roformer
```

출력의 job_id에 해당하는 result/stems/instrumental.wav 경로를 다음 명령의 입력으로 사용한다:
```powershell
& .\.venv\Scripts\python.exe -m music_analyzer.cli separate --input "C:\workspace\music_analyzer\data\separation\jobs\job_여기에실제ID\result\stems\instrumental.wav" --preset instrument_roformer_6s
```

이 방법은 새 모델만 빠르게 들어볼 때 사용한다. 비교까지 하려면 위 1~5번을 권장한다.

## 중단·실패·재시도

실행 중 Ctrl+C로 취소한다. 작업이 완료되어 파일이 게시된 뒤에는 취소로 결과를 지우지 않는다.

작업 ID를 알고 있을 때:
```powershell
& .\.venv\Scripts\python.exe -m music_analyzer.cli job-status "job_실제ID"
& .\.venv\Scripts\python.exe -m music_analyzer.cli retry-job "job_실제ID"
```

retry-job은 새로운 작업 ID를 만든다. 비교할 때 새 ID를 사용한다. 작업별 로그는 data/separation/jobs/job_ID/attempts/a_ID/worker.log에 있다.

MODEL_NOT_AVAILABLE 오류가 나면 필요한 모델을 한 번 준비한다:
```powershell
& .\.venv\Scripts\python.exe -m music_analyzer.cli prepare-model --model melband_roformer_kj
& .\.venv\Scripts\python.exe -m music_analyzer.cli prepare-model --model demucs_htdemucs_6s
& .\.venv\Scripts\python.exe -m music_analyzer.cli prepare-model --model bs_roformer_6s
```

현재 PC에는 세 모델이 준비되어 있으므로 매 곡마다 준비 명령을 실행할 필요는 없다. 결과 파일은 누적 저장된다.

## 청취할 때 기록할 것

곡 이름, 구간, 모델, 악기를 함께 적는다. 예: “새 모델 / 13~14초 / 베이스 — 슬랩은 돌아왔지만 기타가 조금 섞임”. 누출이 줄어도 원래 연주가 사라지면 개선으로 판단하지 않는다. 새 악기 후보의 채택은 여러 곡 청취 결과를 본 뒤 결정한다.
