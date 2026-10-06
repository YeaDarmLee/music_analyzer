# 12트랙 존재·약음·부재 통제 실험

2026-10-07. `codex/12-track-ground-truth-evaluation`에서 초기 MedleyDB 3구간에 이어 6개 구간을 추가했다. 서비스의 모델·보완 정책·회원 데이터는 변경하지 않는다.

Cambridge의 공식 목록/다운로드 페이지가 HTTP 403을 반환해 이번 추가 세트는 공개 [BabySlakh](https://zenodo.org/records/4603870)를 사용한다. 공식 MD5 `311096dc2bde7d61c97e930edbfc7f78`과 파일 크기 882,818,115 bytes가 일치함을 확인했다. Zenodo API의 라이선스는 CC BY 4.0이다.

BabySlakh는 가상악기로 렌더링한 16kHz mono 오디오다. polyphase resampling으로 44.1kHz로 변환하고 두 채널에 동일 신호를 복제한다. 변환 후 독립 stem을 합성하므로 입력은 정답의 합계와 일치한다. 샘플레이트 변환이 8kHz 이상의 정보를 복원하지는 않는다. Slakh 처음 20개 곡에서 가져온 샘플이므로 학습 데이터 중복을 배제할 수 없으며, 실녹음·홀드아웃 성능 벤치마크로 취급하지 않는다.

| 곡 | 구간 | 정답 구성 | 비교 조건 |
|---|---|---|---|
| Track00020 | 15–30초 | 신디 패드, grand piano, clean 일렉기타, 스트링, 베이스, 드럼 | 신디 gain 1 / 0.1 / 0 |
| Track00016 | 60–75초 | brass section, 피아노 2개, 기타 3개, 스트링 2개, 베이스, 드럼, 나머지 | 브라스 gain 1 / 0.1 / 0 |

gain 0.1은 해당 정답만 20dB 낮추고, gain 0은 해당 stem만 제거한다. 다른 참조 stem은 그대로 유지한다. Track00016의 플루트·오보에·하프는 other로 매핑하고 brass나 bowed strings로 합치지 않는다. 60–75초에서는 이 other 원본들의 대부분이 무음이므로 other에 실제 연주가 존재한다고 단정하지 않는다. 출처 metadata의 program_num을 확인하고 선택한 실제 WAV의 길이·채널·샘플레이트·활성 RMS를 검사한다. metadata의 audio_rendered=false만으로 존재하는 WAV를 제외하지 않는다.

Track00016의 피아노 참조에는 metadata의 Electric Piano 2(program 5)가 포함되지만 실제 plugin은 scarbee_clavinet_full.nkm다. 따라서 이 곡의 piano 점수는 해당 keyboard 매핑에 대한 파형 비교이며, 순수 피아노 음색 성능으로 해석하면 안 된다. Track00020은 grand_piano.nkm만 피아노 정답으로 사용한다. 원본 메타데이터와 플러그인 음색이 서비스 악기 분류와 완벽히 일치하지 않는 한계도 함께 기록한다.

목표 파형 gain은 정답 파형에 투영한 선형 계수이며, 단순 출력 RMS보다 목표 성분을 구분하는 데 도움이 된다. 누출·변형이 있는 출력에서 정확히 보존된 음악의 백분율을 의미하지는 않는다. quiet target도 SDR과 오차 RMS를 함께 평가한다.

## 재현

공식 아카이브를 `data/ground-truth/slakh/babyslakh_16k.tar.gz`로 저장하고 위 체크섬을 먼저 확인한다. 선택한 두 디렉터리만 추출한다.

```powershell
tar.exe -xzf data/ground-truth/slakh/babyslakh_16k.tar.gz -C data/ground-truth/slakh --strip-components 1 babyslakh_16k/Track00016 babyslakh_16k/Track00020
.\.venv\Scripts\python.exe scripts/prepare-slakh-ground-truth.py --track 20
.\.venv\Scripts\python.exe scripts/prepare-slakh-ground-truth.py --track 16
.\.venv\Scripts\python.exe -m music_analyzer.ground_truth run data/ground-truth/cases/slakh20-pad-15-30
.\.venv\Scripts\python.exe -m music_analyzer.ground_truth run data/ground-truth/cases/slakh20-quiet-pad-15-30
.\.venv\Scripts\python.exe -m music_analyzer.ground_truth run data/ground-truth/cases/slakh20-no-pad-15-30
.\.venv\Scripts\python.exe -m music_analyzer.ground_truth run data/ground-truth/cases/slakh16-brass-60-75
.\.venv\Scripts\python.exe -m music_analyzer.ground_truth run data/ground-truth/cases/slakh16-quiet-brass-60-75
.\.venv\Scripts\python.exe -m music_analyzer.ground_truth run data/ground-truth/cases/slakh16-no-brass-60-75
```

각 케이스의 report.json과 comparison.html은 기존 평가 세트와 같은 형식이다. 기타가 사라지는 문제를 추적하기 위해 base_guitar와 버려진 잔여 입력 Mega5 기타 출력의 정답 비교도 guitar_stage_scores에 기록한다. 초기 분리 모델 자체의 손실과 기타 세부분리에서 생긴 손실을 구분한다. 보완 제거 후보는 같은 실행의 모델 출력을 사용해 synth/strings/brass 보완분을 other로 반환한 ablation이다.

수치 요약은 `TWELVE_TRACK_CONTROLLED_RESULTS.json`, 전체 창별 수치는 `data/ground-truth/cases/<case>/report.json`에 저장한다. 원본·참조·현재·후보 WAV를 모두 보존하고 오디오는 Git에 포함하지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts/summarize-controlled-ground-truth.py
```

요약 명령은 세 조건에서 목표를 제외한 참조가 샘플 단위로 동일하고, 약음 목표가 정상 목표의 정확한 0.1배이며 부재 목표가 정확히 0인지 검증한다. 평가 명령도 현재 준비한 믹스가 해당 실행의 실제 분석 입력과 샘플 단위로 동일한지 검사한다. WAV 재저장 시 헤더가 달라질 수 있으므로 파일 해시만으로 기존 분석 입력과의 일치를 판단하지 않는다. 청취 목록은 `data/ground-truth/cases/index.html`에 생성한다.

## 판단

정상 신디 패드는 보완 전 SDR 0.01dB에서 보완 후 0.63dB로 조금 개선됐지만, 목표 파형 gain은 0.0049→0.0979에 머물렀다. 신디 출력이 충분히 회복됐다고 볼 수 없다. 스트링은 이 믹스에서 SDR 약 0.49dB로 혼입이 크고, 없는 브라스도 원곡 대비 -23.15dB의 출력을 냈다.

약한 신디는 보완 전 SDR -4.01dB에서 보완 후 -7.73dB로 악화됐다. 목표 파형 gain 0.0116→0.2405만 보면 개선처럼 보이지만 오차가 더 커졌다. 단순 에너지 증가나 투영 계수 하나로 보완 성공을 판정하면 안 된다.

정상 브라스는 보완 전 SDR 5.69dB, 보완 후 5.57dB로 이득이 없었다. 기본 모델 출력의 목표 gain은 약 0.66이다. 이 곡에서도 없는 신디가 원곡 대비 -14.04dB의 출력을 내므로 브라스 추출만 보고 전체 트랙을 승인할 수 없다.

Track00020의 베이스·드럼 SDR은 15.88/17.99dB인 반면 가상 clean 기타는 거의 0dB이며 기타 합계에도 실제 목표가 남지 않는다. 기본 6-source 단계의 기타가 이미 거의 무음이다. 실제 목표 기타가 포함된 other가 다음 잔여 입력으로 이동한다. 마지막 잔여 Mega5의 버려진 기타 head도 목표를 충분히 추출하지 못해, 이 샘플은 기타 라우팅 변경 하나만으로 해결되지 않는다. Rainfall 실제 기타의 좋은 결과를 모든 기타 음색으로 일반화하지 않는다.

| 목표/조건 | 보완 전 SDR | 현재 SDR | 부재 출력: 보완 전 → 현재(원곡 대비 dB) |
|---|---:|---:|---|
| 신디 정상 | 0.01 | 0.63 | 해당 없음 |
| 신디 20dB 감쇠 | -4.01 | -7.73 | 해당 없음 |
| 신디 제거 | 해당 없음 | 해당 없음 | -23.75 → -18.58 |
| 브라스 정상 | 5.69 | 5.57 | 해당 없음 |
| 브라스 20dB 감쇠 | -0.66 | -4.96 | 해당 없음 |
| 브라스 제거 | 해당 없음 | 해당 없음 | -34.65 → -23.80 |

약한 브라스도 목표 gain이 0.049→0.148로 증가했지만 SDR은 약 4.30dB 악화됐다. 부재 신디와 브라스는 보완 후 각각 약 5.17/10.85dB 더 큰 출력을 냈다. 비교 후보의 전체 출력 합계 보존 최대 오차는 1.20e-7 미만이다. 새 실험 6개와 기존 실녹음 3개 모두 재생 페이지를 보존했다. 관련 자동 테스트 10개와 실제 6개 분석이 통과했고 각 비교 페이지의 오디오 링크도 확인했다.

부재와 약음 조건의 최종 판단은 6개 케이스 전체 요약과 함께 읽어야 한다. 이번 통제 세트가 보완의 조건부 실행·모델 자체의 악기 구분을 추가로 검증할 근거이며, 서비스에 일반적인 음량 gate를 바로 도입하는 근거는 아니다.
