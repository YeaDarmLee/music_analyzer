# Mega53 세 출력 첫 실행 결과

실행일: 2026-10-06. 공식 가중치에서 어쿠스틱 기타(index 1), 일렉기타(16), 신스(38)를 추출했다. 웹 기본 모델을 변경하지 않은 연구 실행이다.

## 구현과 확인

- 실행 모듈: `separation/src/music_analyzer/mega53_experiment.py`.
- 공식 checkpoint/config SHA256 확인 후 `weights_only=True`로 로드했다.
- 53개 head 존재를 확인하고 shared tensor를 유지한 채 선택한 head를 0/1/2로 재배치했다.
- 축소 checkpoint 크기: 127,223,818 bytes (121.33 MiB).
- 파생 SHA256: `9d97108e4f9516d67ddd5ee053a46df20aff34d4f83607c1ec79f06e8a560e26`.
- 축소 모델 strict load 성공. YAML의 tuple 형식도 보존했다.
- 검사한 1초 probe에서 공식 selected-head와 축소 모델의 FP32 최대/평균 오차 0. AMP FP16 비교에서도 오차 0. 이는 해당 probe의 검사 결과이며 전체 곡의 수치 동일성을 검사한 것은 아니다.
- 관련 자동 테스트 35개 통과. head 대응, 누락/중복 거부, 설정 round-trip, 기존 overlap/timeline 검증을 포함한다.

## RTX3060 12GB 실측

환경: PyTorch 2.5.1+cu121, batch 1, AMP FP16, 50% overlap, TF32 OFF, 기존 정규화 overlap-add 사용.

| 입력 | 음원 길이 | chunk | 추론 시간 | RTF | peak allocated |
| --- | ---: | ---: | ---: | ---: | ---: |
| SPYAIR 원곡 40–60초 | 20초 | 10초 | 3.662초 | 0.183 | 0.904 GiB |
| 같은 구간의 기존 보컬 제거 반주 | 20초 | 10초 | 3.855초 | 0.193 | 0.904 GiB |
| SPYAIR 원곡 40–60초 | 20초 | 20초 | 4.797초 | 0.240 | 1.509 GiB |
| SPYAIR 원곡 전체 | 234.777초 | 10초 | 35.035초 | 0.149 | 0.904 GiB |

각 조건 1회 실측이다. 이번 짧은 비교에서는 10초 chunk가 유리했다. GPU 메모리는 PyTorch allocator 기준이며 전체 장치 메모리가 아니다. 전체 곡 peak reserved는 1.100 GiB, 축소 모델 로드 시간은 0.914초였다. 추론 시간에는 CPU 누적과 GPU 출력 전송이 포함되며, 원본 검증 모델 로드·동등성 검사·파일 export·다운로드를 포함한 CLI 전체 실행 시간이 아니다. 기존 보컬/코러스/베이스/드럼/피아노 분석 시간을 대체하는 숫자도 아니다.

## 청취 자료

`data/part-studies/mega53-first/comparison.html`에서 40–60초의 원곡 직접 추출, 반주 입력 추출, 기존 출력을 비교할 수 있다.

- `mix/`, `instrumental/`: 세 악기의 20초 raw WAV와 benchmark JSON.
- `mix-20s-chunk/`: 20초 chunk 비교 결과.
- `full-song/`: 전체 곡의 세 악기 raw WAV, 정확히 10,353,664 frames.
- `preview/`: 청취용 RMS 조정본과 적용 gain 기록. 원본 raw는 수정하지 않았다. RMS 맞춤은 정확한 LUFS 일치를 뜻하지 않는다.

기존 일반 기타 출력은 두 기타 각각의 정답이 아니며, 기존 other 출력도 신스 정답이 아니다. 실제 곡의 ground truth가 없으므로 추출률이나 SI-SDR 품질 개선을 주장하지 않는다.

## 실행 명령

프로젝트 루트에서:

```powershell
.\.venv\Scripts\python.exe -m music_analyzer.mega53_experiment prepare
.\.venv\Scripts\python.exe -m music_analyzer.mega53_experiment benchmark data/reset-backups/reset-20261006-193853/inputs/asset_d8b1327923bd43c98a4cca041db58c25/canonical.wav --output data/part-studies/mega53-first/full-song --start 0 --duration 235 --chunk 10
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider separation/tests/test_mega53_experiment.py separation/tests/test_roformer.py
```

모델 준비와 GPU 실행은 각각 file lock을 사용한다. GPU lock은 웹 worker와 같은 `data/separation/runtime/gpu-execution.lock`이며 동시 GPU 작업을 피한다. GPU 작업 중이면 실패하고 기존 작업을 중단하지 않는다.

## 다음 품질 검증

실행 가능성과 공식 출력 보존을 확인했다. 다음은 정답 악기 트랙을 포함한 혼합/대상 부재 대조군 평가와 실제 곡 청취다. 특히 신스 출력의 기타·피아노·보컬 누출, clean/distorted 기타의 교차 누출, 정상 FX/sustain 보존을 확인한다. 통과한 클래스만 웹 경로에 연결한다. 후처리로 소리를 바꾸기 전에 raw 분리 결과부터 평가한다.

이번 작업은 DB, 회원 라이브러리, 웹 기본 분석을 변경하거나 초기화 백업을 회원 라이브러리로 복원하지 않았다.
