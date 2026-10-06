# 브라스·스트링 추가 및 미라클 제너레이션 검증

2026-10-06. 사용자의 청취 결과에 따라 원곡 직접 입력을 채택했다. 새 모델은 기존 세 출력에 brass(index 8), strings(index 37)를 추가한 5-head 모델이다. 신스에서 두 악기를 단순 차감하지 않는다. 각 출력은 독립적인 추정이므로 서로 완전히 배타적인 트랙이라고 보장하지 않는다.

## 구현

- 기존 `mega53_experiment`에 `--extended` 옵션을 추가했다. 기존 3-head 실행 명령과 모델 파일은 유지했다.
- 공식 원본 checkpoint를 재사용했다. 가중치 재다운로드와 encoder의 악기별 반복 실행을 피했다.
- 출력 순서: acoustic-guitar, electric-guitar, synth, brass, strings.
- 5-head 모델은 168.65 MiB이며 strict load와 공식 설정의 클래스 순서 검증을 통과했다.
- 두 곡에서 검사한 1초 probe의 공식 selected-head 대비 FP32/AMP 최대 오차는 모두 0이다.
- 관련 자동 테스트 36개 통과. 3/5-head 각각의 tensor 대응과 YAML round-trip을 확인했다.

## 실행 결과

batch 1, 10초 chunk, 50% overlap, RTX3060, CUDA AMP FP16. 각 조건 1회 실측이며 추론 시간은 모델 준비·동등성 검사·export까지 포함한 전체 CLI 시간이 아니다.

| 곡 | 원곡 길이 | 5개 출력 추론 | peak allocated |
| --- | ---: | ---: | ---: |
| 알바스천 미라클 제너레이션 | 240.953초 | 38.724초 | 0.996 GiB |
| SPYAIR Orange | 234.777초 | 37.387초 | 0.996 GiB |

GPU 메모리는 PyTorch allocator 기준이다. 10개 전체 곡 출력이 원곡의 sample rate/stereo/frame 수를 유지하는지 확인했다. 실제 곡의 정답 트랙이 없으므로 분리 품질 수치를 산출하지 않았다. 미라클 제너레이션으로 두 기타의 구분을, Orange로 신스·브라스·스트링을 청취 평가한다.

## 비교 페이지

`data/part-studies/mega53-extended/comparison.html`

- 곡과 0–20초 / 40–60초 / 100–120초 구간을 선택한다.
- 다섯 전용 출력과 기존 출력, 원곡을 재생한다.
- 기존 기타는 두 기타 각각의 정답이 아니다. 기존 신스 표시 출력도 브라스/스트링 각각의 정답이 아니다.
- 청취용 RMS를 조정하되 증폭은 최대 4배로 제한했다. raw는 보존했다. 처리 gain은 `preview/levels.json`에 기록했다.
- 66개 preview WAV의 존재와 44.1kHz/stereo/20초 길이를 검사했다.
- 기존 비교 페이지에도 새 페이지 링크를 추가했다.

전체 곡 원본 추출 결과와 benchmark JSON은 각각 `miracle/`, `orange/`에 있다. 이 자료는 연구용이며 회원 라이브러리의 트랙을 덮어쓰지 않는다.

## 재실행

```powershell
.\.venv\Scripts\python.exe -m music_analyzer.mega53_experiment prepare --extended
.\.venv\Scripts\python.exe -m music_analyzer.mega53_experiment benchmark data/separation/inputs/asset_e4b493593b934b12a58670f5a31deb14/canonical.wav --output data/part-studies/mega53-extended/miracle --start 0 --duration 241 --chunk 10 --extended
.\.venv\Scripts\python.exe -m music_analyzer.mega53_experiment benchmark data/reset-backups/reset-20261006-193853/inputs/asset_d8b1327923bd43c98a4cca041db58c25/canonical.wav --output data/part-studies/mega53-extended/orange --start 0 --duration 235 --chunk 10 --extended
.\.venv\Scripts\python.exe scripts/build-mega53-comparison.py
```

원곡/반주 입력 선택은 사용자의 청취 판단과 첫 실행 결과를 반영했다. 기존 악기 분석에도 반주가 필요하므로 원곡 직접 입력 선택이 전체 파이프라인의 보컬 분리 단계를 제거한다는 뜻은 아니다. 웹 기본 분석 연결은 새 악기 출력의 누출·음색 보존을 평가한 후 진행한다.
