# 09. S4 품질 개선 후보와 기타·피아노 분리

작성: 2026-10-05 · 로컬 개발 검증 · RTX 3060 12GiB

## 사용자 피드백과 이번 변경

사용자는 기존 4-stem 결과에서 중간 음량 변화, 다른 악기의 약한 누출, 원곡보다 약하게 남거나 빠진 듯한 연주를 들었다고 보고했다. 이번 작업에서는 이 문제를 품질 평가의 기준으로 삼고 다음 비교 결과를 생성했다.

1. **quality**: 같은 htdemucs 모델에서 입력 구간을 4초에서 학습 문맥 길이인 7.8초로 확대했다. overlap은 25%에서 50%로 올리고, 서로 다른 두 시간 이동 위치의 추론을 정렬한 후 평균했다.
2. **quality_ft**: 공식 악기별 fine-tuned 모델을 동일한 고품질 구간 설정으로 적용했다. 네 checkpoint는 source별 공식 가중치로 순차 실행하며 GPU에 한 모델씩 올린다.
3. **quality_6s**: 공식 6-stem 모델로 원곡에서 drums/bass/vocals/guitar/piano/other를 직접 추출했다. 기존 other WAV를 다시 분리하지 않으므로 앞 단계의 손실을 재분리 입력으로 물려받지 않는다.
4. 기존 결과와 후보를 같은 시작점·같은 고정 gain으로 들어볼 수 있는 로컬 비교 페이지를 추가했다.

**이번 검증은 개선 후보의 실제 실행과 오디오 계약을 확인한 것이다. 모든 누출·손실·음량 흔들림이 해결됐다는 판정은 아직 하지 않는다.** 사용자 청취 피드백이나 reference stems 없이 개선된 정확도 수치를 붙이지 않는다. 기본 baseline 설정은 비교 근거 없이 자동 교체하지 않았다.

## 원인을 어떻게 다루었는가

기존 raw writer는 sample을 그대로 저장하며 개별 stem이나 chunk의 loudness/peak 정규화를 하지 않았다. 따라서 저장기의 임의 음량 보정이 흔들림 원인이라는 증거는 없다. 신호가 약해지는 현상은 모델의 분리 오차, 악기 누출, nonlinear chunk 예측 차이 등과 구별하여 평가해야 한다.

기존 4초 입력 chunk는 HTDemucs 내부에서 학습 길이 7.8초까지 padding될 수 있다. 새 품질 설정은 입력도 7.8초를 사용해 구간마다 실제 문맥을 더 제공한다. 다만 마지막 구간·시간 이동 평균 경계에는 여전히 padding이 필요하므로 모든 경계 문제를 없앴다고 설명하지 않는다.

정상 구간의 overlap을 늘리고 두 시간 이동 추론을 평균하는 것은 분리 결과의 구간 의존성·시간 이동 민감성을 줄이려는 후보 조정이다. 처리 시간이 늘며 모든 악기에서 개선을 보장하지 않는다. 추가 fine-tuning은 모델 후보 자체를 비교하기 위한 변경이다.

소리가 빠지는 문제를 감추려고 dynamic compressor, automatic gain correction, hard noise gate, 약한 sample 제거, 원곡 잔여분의 임의 재분배를 적용하지 않았다. 이러한 처리는 희미한 목표 연주를 더 없애거나 다른 악기를 다시 섞을 수 있다. raw 결과는 기존과 동일하게 float32 WAV, gain 1, clipping 없음이다.

## 모델 근거

Demucs 공식 문서는 htdemucs_ft와 실험적인 6-source 모델을 제공한다. 6-source 모델은 guitar와 piano를 추가하며 piano에 bleeding/artifact 한계가 있음을 명시한다.

- [공식 모델 설명과 한계](https://github.com/facebookresearch/demucs)
- [공식 fine-tuned ensemble 구성](https://github.com/facebookresearch/demucs/blob/v4.0.1/demucs/remote/htdemucs_ft.yaml)
- [공식 6-source signature](https://github.com/facebookresearch/demucs/blob/v4.0.1/demucs/remote/htdemucs_6s.yaml)
- [공식 checkpoint/hash prefix 목록](https://github.com/facebookresearch/demucs/blob/v4.0.1/demucs/remote/files.txt)

설치된 demucs 4.0.1의 해당 파일과 upstream apply.py도 확인했다. downloads는 공식 allowlist에 한정하며 각각의 공개 SHA-256 prefix를 검증하고 관측된 전체 hash를 registration에 고정한다. full hash 최초 독립 검증과는 구별한다. 모델 weights의 기존 DEV_ONLY/UNRESOLVED 상태는 유지한다.

## 실행 결과

동일한 사용자 제공 SPYAIR MP3와 동일 canonical hash를 사용했다. 음원 길이는 191.56462585034015초다.

| 후보 | source 수 | 입력 구간 / overlap / shifts | 추론 시간 | PyTorch peak allocated |
|---|---:|---|---:|---:|
| 기존 baseline | 4 | 4초 / 0.25 / 0 | 15.837초 | 551.47MiB |
| quality | 4 | 7.8초 / 0.5 / 2 | 22.408초 | 550.92MiB |
| quality_ft | 4 | 7.8초 / 0.5 / 2 | 89.412초 | 551.42MiB |
| quality_6s | 6 | 7.8초 / 0.5 / 2 | 23.172초 | 619.54MiB |

모두 44.1kHz stereo FLOAT WAV, 8,448,000 frames, origin 0이다. 저장 전후 float32 sample 일치·finite·hash·출력 source 계약을 확인했다. source 개수는 등록 모델의 명시적인 label 계약으로 결정한다. 모델이 내놓은 label을 임의로 다른 악기로 변환하지 않는다.

| 후보 | 작업 ID |
|---|---|
| baseline | job_1442c6219eaa4c64bce8bb02515b4bc7 |
| quality | job_5ddc2dd39e7049e09a4af11a683cea30 |
| quality_ft | job_f82922c65b704403b7e697bb19e88d56 |
| quality_6s | job_ff87860b8aa5453b948c345f0849f050 |

결과 폴더는 data/separation/jobs/<job_id>/result/stems/다. 6-stem 결과의 other는 기타·피아노를 제외한 잔여 소리이므로 기존 4-stem other와 같은 파트가 아니다. 기타 track도 리드/리듬 기타별 또는 연주자별 분리를 뜻하지 않는다. 악기 검출이 검증되지 않았으므로 피아노 출력이 있다는 사실로 원곡에 피아노가 존재한다고 단정하지 않는다.

실측 상세 JSON: data/separation/s4-validation/results.json. 지표·환경·코드·preset·checkpoint hash는 각 result/manifest.json에 기록되어 있다. reconstruction RMS는 모델 품질 순위가 아니며 RAW-SDR/SI-SDR는 reference가 없어서 null이다.

## 현재 곡 청취 비교

페이지:
data/separation/comparisons/compare_5e132bd5f7c8403f84ef085fec7a5a06/comparison.html

현재 PC에서 열어 둔 로컬 페이지:
http://127.0.0.1:8768/comparison.html

서버가 종료된 경우 comparison.html을 브라우저에서 직접 열어 사용할 수 있다. clips 폴더를 같은 위치에 유지한다. 서버는 이 비교 폴더만 127.0.0.1로 제공하며 외부 전송 기능이 없다.

비교 구간: **0:20–0:40 / 1:10–1:30 / 2:15–2:35**. 사용자가 특정 문제 시점을 아직 지정하지 않아 동일한 고정 구간을 먼저 준비했다. 구간은 품질 우위를 선택하기 위한 근거로 선별한 것이 아니다.

원곡과 4개 결과의 총 19개 소리, 3개 구간의 57개 PCM16 WAV를 생성했다. 모든 source·구간에 동일 gain 0.6937643110910255를 적용했다. 최대 peak에 대한 공통 headroom 확보이며 source별·구간별 gain 보정이나 dynamic normalization이 아니다. 원본 raw WAV는 변경하지 않았다. 각 preview는 동일 frame 구간과 PCM16 quantization 오차를 검증했다.

모델·악기·원곡을 전환할 때 재생 위치를 유지하고, 구간 변경은 처음으로 이동한다. 재생·일시중지·seek·반복 재생을 제공한다. 직접 들은 연주 보존/누출 억제/소리 안정성 점수와 문제 시점을 기록할 수 있다. 기록은 브라우저 로컬 저장과 JSON 다운로드이며 자동 품질 점수나 외부 공유가 아니다.

브라우저에서 실제 WAV 재생, 기타 선택, 원곡 전환, 20초 길이, 구간 변경을 확인했다. 모델과 악기를 빠르게 연속 전환할 때 위치가 초기화되는 문제를 발견하여 pending 위치·재생 의도를 보존하도록 수정했다. 수정 후 7.2365초 → 7.4767초, 원곡에서 분리 결과 복귀 시 17.0645초 → 17.3253초로 전환 위치 유지와 오류 없음·재생 연속성을 확인했다. 이는 사용자 체감 음질 평가를 대신하지 않는다.

## 앞으로 같은 설정으로 실행

처음 사용하는 PC에서는 필요한 등록 모델을 명시적으로 준비한다:

```powershell
cd C:\workspace\music_analyzer
.\.venv\Scripts\python.exe -m music_analyzer.cli prepare-model --model demucs_htdemucs_ft
.\.venv\Scripts\python.exe -m music_analyzer.cli prepare-model --model demucs_htdemucs_6s
```

이 PC에는 이미 준비되어 있다. 음원 파일을 지정한다:

```powershell
.\scripts\separate.ps1 -InputAudio 'C:\audio\sample.mp3' -Preset quality_ft
.\scripts\separate.ps1 -InputAudio 'C:\audio\sample.mp3' -Preset quality_6s
```

동일한 등록 입력을 재사용하려면:

```powershell
.\.venv\Scripts\python.exe -m music_analyzer.cli separate --asset-id 'asset_등록된32자리ID' --preset quality
.\.venv\Scripts\python.exe -m music_analyzer.cli separate --asset-id 'asset_등록된32자리ID' --preset quality_ft
.\.venv\Scripts\python.exe -m music_analyzer.cli separate --asset-id 'asset_등록된32자리ID' --preset quality_6s
.\.venv\Scripts\python.exe -m music_analyzer.cli compare-results --job-id 'job_기존ID' 'job_개선ID' --window '45:20' --window '110:20'
```

compare-results는 동일한 canonical 입력·timeline의 성공 결과만 받으며 지정 구간이 곡 범위를 벗어나면 오류로 거절한다. 짧은 곡에서는 --window로 유효 구간을 지정한다.

quality/quality_ft/quality_6s에도 기존 잠금·취소·복구와 한 번의 GPU OOM fallback을 적용한다. fallback은 원래 모델을 유지하고 메모리 절약 설정으로 바꾸며 shifts 0과 짧아진 segment를 manifest에 기록한다. 6-stem OOM을 4-stem으로 숨겨 전환하지 않는다. 실제 OOM 고갈 시험은 하지 않았으며 mapping은 unit test로 검증했다.

## 테스트와 판정

총 **96개 pytest 통과**. 결과: data/separation/test-results-s4.xml.

신규 검증에는 다음을 포함한다:

- upstream split/overlap-add와 shifts가 입력 timing·sample amplitude를 보존하는 CPU identity-model 시험
- 실제 upstream 실행 횟수와 단일/ensemble·시간 이동의 진행률 count 일치
- 6-source 결과 수·label·모델 identity 검증
- ensemble의 첫 artifact뿐 아니라 모든 checkpoint의 pinned hash 검증
- fallback 모델 유지와 명시적 taxonomy mapping
- 서로 다른 source 음량을 그대로 유지하는 공통 gain preview와 지정 구간 길이·PCM16 오차
- 비교 구간 초과 거절, 품질 개선 판정이 자동 true로 바뀌지 않음

기존 S1–S3의 입력·raw 저장·모델 변조·취소·복구 테스트도 통과했다. node --check로 생성된 비교 페이지 JavaScript 문법을 검사했고 브라우저에서 실제 재생·전환을 확인했다.

## 채택 조건과 남은 검증

사용자가 동일 구간에서 다음을 평가한다:

1. 원곡의 약한 연주·잔향이 더 잘 보존되는가.
2. 다른 악기 누출이 줄었는가.
3. 구간 중간의 음량·질감 변화가 줄었는가.
4. guitar/piano 결과가 실제 연주를 따라갈 수 있는가.
5. 특정 악기 개선이 다른 악기 악화로 바뀌지 않았는가.

더 큰 음량, 더 작은 reconstruction RMS, 더 많은 stem 수, 더 긴 처리 시간만으로 품질 향상을 판정하지 않는다. 특정 문제 구간과 악기를 받으면 이 비교기에 추가하고 필요하면 전문 모델의 직접 추출과 비교한다.

설계의 다곡·장르별 reference/blind 청취 gate는 아직 완료하지 않았다. 이번에는 같은 한 곡에 대한 실행 비교다. 사용자 청취 후 채택 후보를 확정하고, 누출이 여전히 큰 악기는 더 적합한 전문 모델을 별도 후보로 등록하는 것이 다음 작업이다.
