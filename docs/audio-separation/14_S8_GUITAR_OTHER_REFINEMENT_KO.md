# S8 기타와 other 혼입에 대한 재분리 실험

2026-10-05. 대상 job_570b38bffcb643db978641cc1a289919. 사용자는 나머지 악기는 괜찮지만 **처음부터 20초**에서 기타와 other가 겹쳐 들린다고 평가했다. 해당 작업은 BS-RoFormer 6트랙 결과이며 입력 반주는 348.206초다.

## 변경 범위

기존 guitar + other를 합쳐 같은 BS-RoFormer에 다시 입력하는 집중 분리 실험을 구현했다. 경쟁 악기 성분을 줄인 입력이지만 여전히 같은 모델의 분류 한계가 남을 수 있다. 이번에는 모델 자체를 교체하지 않았다.

- 새 기타 = 집중 입력에서 모델이 추정한 guitar.
- 새 other = 기존 guitar + 기존 other - 새 기타.
- bass, drums, piano, vocals는 기존 WAV 경로 및 해시를 그대로 참조.
- 원본 작업과 파일을 덮어쓰지 않는다.
- 진폭 정규화, hard gate, clipping으로 겹친 부분을 지우지 않는다.
- secondary 모델의 다른 출력은 진단용 작업에 보관하며 최종 기타/other에 혼합하지 않는다.

두 출력의 합은 기존 기타+other와 float32 오차 범위로 일치한다. 이는 소리 보존 검사이며 **기타를 정확하게 판별했다는 의미는 아니다**. 원래 두 출력에 중복 추정이나 누락이 있었다면 그 문제도 합에 포함된다. 같은 연주가 양쪽에 조금씩 있다는 청취 의견만으로 위상까지 동일한 중복 복제라고 판단하지 않는다.

## 실제 실행

- refinement: refine_14809c3105a84e1e9e1396c67483e50f
- secondary GPU 작업: job_a0a855472be942babeb37a5f7649d4b4
- 상태: SUCCEEDED. 전체 길이 FLOAT WAV 출력 및 모든 참조 파일 해시 확인.
- 기타+other 합 오차 최대: 1.4901161193847656e-08.
- 전체 회귀 테스트 122개 통과(30.10초). 별도 테스트에서 잔차가 음수여도 유지하고 clipping하지 않는 것, 잘못된 shape 및 nonfinite 추정치 거부를 검사.

새 파일은 data/separation/refinements/refine_14809c3105a84e1e9e1396c67483e50f/stems/guitar.wav 및 other.wav에 있다. manifest의 나머지 트랙 경로는 원래 job을 참조한다.

[청취 비교 파일](../../data/separation/refinements/refine_14809c3105a84e1e9e1396c67483e50f/comparison/comparison.html)

0~20초를 우선 비교하고, 70~90초와 135~155초도 추가했다. 모든 파일은 동일한 fixed gain을 사용한다. 기타와 other의 혼입이 줄어도 synth/strings 등 다른 소리가 기타로 잘못 이동하면 채택하지 않는다. 개선 여부는 아직 청취 검증 전이며 기본 pipeline은 변경하지 않았다.

## 재실행

프로젝트 루트 PowerShell:
```powershell
.\.venv\Scripts\python.exe -m music_analyzer.cli refine-guitar-other --job-id job_570b38bffcb643db978641cc1a289919 --window 0:20
```

새 refinement와 비교 파일 경로가 출력된다. 기존 successful instrument job에 guitar와 other가 있어야 한다. 추가 --window 시작초:길이초 옵션으로 다른 구간도 지정할 수 있다. 실행 중 모델 job 관리 및 CUDA lock은 기존 JobService를 사용한다. refinement 자동 재개는 없고 실패 시 원본 job으로 다시 실행한다.
