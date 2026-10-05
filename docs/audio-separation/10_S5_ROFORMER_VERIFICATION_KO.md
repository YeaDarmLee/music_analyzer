# S5 보컬·반주 모델 교체 후보 검증

2026-10-05. 기존 Demucs 6트랙에서 연주 누락·먹먹함·누출이 있다는 청취 피드백에 따라, 다른 모델 계열인 Mel-Band RoFormer를 추가했다. 기존 파일은 유지했다. **실행 검증은 완료했지만 청취 품질 개선 및 최종 모델 채택은 미확정이다.**

## 구현

- KimberleyJSN/melbandroformer 게시 모델의 고정 리비전 ac9b0614ab3cd7f77219e18ba494dfd93956c348 사용. 공개 전체 SHA-256 87201f4d31afb5bc79993230fc49446918425574db48c01c405e44f365c7559e와 다운로드 파일 일치.
- MSST 코드 리비전 84b1eac0887756b4f1a9d7a1ff49105939749ed2와 설정 YAML 고정. 안전한 YAML 로더, weights_only 체크포인트 로딩 및 strict state_dict 검증.
- upstream MIT 코드와 LICENSE, 변경 내역 및 해시를 vendor/msst에 보관. 패키지 내부 import와 torch 2.5 SDPA 호환 변경만 적용했다.
- 44.1kHz 스테레오, 8초 구간, 75% 겹침, 반사 문맥 패딩, 양의 선형 crossfade, batch 1, CUDA float16. 모델 ISTFT 길이를 입력과 일치시킨다.
- 전체 입력과 합산 출력은 CPU에 두고 GPU에는 한 구간씩 전달한다. 구간별 취소 확인과 진행 기록.
- 추가 gate·노이즈 억제·구간별 음량 정규화 없이 FLOAT WAV 저장. 원본의 샘플 수와 타임라인, gain=1을 유지한다.
- 보컬은 모델 추정치이고 **instrumental은 원본에서 추정 보컬을 뺀 전체 반주**다. 독립적으로 추론한 악기 트랙이 아니다.
- CUDA OOM이면 같은 모델의 4초 프리셋으로 새 worker에서 한 번 재시도한다. 이번 두 실행에서는 fallback이 발생하지 않았다. 4초 실행의 실제 모델 품질은 별도 검증 대상이다.

## 실제 실행 결과

RTX 3060 12GiB, 기존 CUDA 12.1 / torch 2.5.1 환경 유지.

| 곡 | 길이 | 추론 시간 | GPU 최대 할당 | 결과 |
|---|---:|---:|---:|---|
| millsage - 기사개전 | 195.419초 | 43.234초 | 1.554GiB | 보컬·반주 2개, SUCCEEDED |
| SPYAIR - サムライハート | 191.565초 | 41.858초 | 1.554GiB | 보컬·반주 2개, SUCCEEDED |

GPU 수치는 PyTorch allocator 측정이며 전체 장치 사용량은 아니다. 첫 곡은 104구간, 두 번째는 102구간 처리했다. 출력 해시, 정확한 프레임 수, 유한 값 및 FLOAT WAV readback 검증을 통과했다. 보컬+반주 합이 원본과 맞는 것은 잔차 구성의 결과이며 음질 점수가 아니다.

작업:
- 기사개전: job_a5b0e6a61f45478c902b72754700dba7
- SPYAIR: job_2d72bbda153f467fbfa13661414a69e8

## 청취 비교

기사개전: [새 비교 페이지](../../data/separation/comparisons/compare_a367a1fdde764b2885ef871cc398cc4d/comparison.html)
SPYAIR: [새 비교 페이지](../../data/separation/comparisons/compare_ee178b824bf6465aa130a2e9f2137ea9/comparison.html)

각 페이지에서 추가 학습 4트랙·기타/피아노 6트랙·RoFormer를 선택할 수 있다. 전체 반주는 모든 모델에서 원본 minus 보컬로 맞췄다. 20–40초, 70–90초, 135–155초의 동일 구간과 같은 고정 gain으로 비교한다. 잔차의 피크 상한까지 포함해 재생 사본의 clipping을 예방한다. 모델을 바꾸면서 보컬 질감·반주에 남는 목소리·원래 연주의 보존을 평가한다. 브라우저에서 모델/보컬/반주 전환과 20초 WAV 정상 로딩을 확인했다.

드럼·베이스·기타·피아노 버튼은 기존 Demucs 결과이며, 새 모델로 바뀐 악기 결과가 아니다. 이번 후보가 모든 6트랙 문제를 해결했다고 간주하지 않는다.

## 재실행

프로젝트 루트 PowerShell:
```powershell
.\.venv\Scripts\python.exe -m music_analyzer.cli prepare-model --model melband_roformer_kj
.\.venv\Scripts\python.exe -m music_analyzer.cli separate --input "millsage - 기사개전 (起死開戦).mp3" --preset vocal_roformer
```

bootstrap에 RoFormer 의존성과 현재 검증 환경 lock을 반영했다. 게시 모델의 MIT 표시는 publisher declaration으로 기록했고 개발 실험 모델로 유지한다.

## 다음 개발 단계

1. 이 비교로 보컬 누락, 물속 같은 질감, 반주 잔류 목소리가 줄었는지 청취 판단.
2. 개선 후보를 채택한 후 반주 전용 악기 분리 모델을 별도로 비교. 원본 직접 분리도 함께 남겨, 보컬 제거 단계의 손상이 악기 분리에 누적되는지 확인.
3. 기타/드럼/베이스 각각의 보존과 누출을 구간별 평가. 여러 모델의 출력을 단순히 합쳐 동일한 6개 partition이라고 표시하지 않는다.
4. 전문 악기 모델의 채택 여부를 정한 뒤 악보 변환 단계로 진행.

자동 테스트는 구간 연결에서 1샘플/짧은 파일/긴 파일 및 다양한 overlap의 타임라인·진폭 보존, nonfinite 출력 거부, 취소, 안전 YAML 및 고정 코드/설정을 검증한다. 청취 정확도와 실제 악기 정답 검증은 포함하지 않는다.

출처: [모델 게시 저장소](https://huggingface.co/KimberleyJSN/melbandroformer/tree/ac9b0614ab3cd7f77219e18ba494dfd93956c348), [고정 MSST 코드](https://github.com/ZFTurbo/Music-Source-Separation-Training/tree/84b1eac0887756b4f1a9d7a1ff49105939749ed2).

최종 회귀 검증: 112개 테스트 통과(31.01초), pip check 통과.
