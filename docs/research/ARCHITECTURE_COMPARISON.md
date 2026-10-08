# Architecture Comparison (Skeleton)

상태: Research Packet 01 대기. `NEEDS_RESEARCH` 셀은 외부 조사 결과로만 채운다. 이 문서의 어떤 셀도 추론으로 채우지 않는다.

## 0. 하드 제약 (개발 기준)

| 항목 | 값 |
|---|---|
| Dev GPU | RTX 3060 12 GiB |
| 학습 | 한 장에서 반드시 동작. AMP 필수, gradient accumulation 허용, gradient checkpointing 필요 시 |
| 추론 | 12 GiB보다 훨씬 낮게 |
| 규모 | 수 M ~ 수십 M params 우선 |
| chunk | 3~8 s부터 |
| 탈락 기준 | 24 GB+ / 다중 GPU를 전제로 해야 성능이 나오는 설계 |

## 1. 기존 모델 비교 (Research Packet 01 대상)

| 모델 | 입력 표현 | Band 전략 | 시간 모델링 | 주파수 모델링 | Decoder/출력 | Phase 처리 | Loss | Params | 계산량 | 장점 | 약점 | CODE | WEIGHT | TRAIN DATA | 가져올 것 | 안 가져올 것 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| KJ Mel-Band RoFormer | complex STFT (코드 확인: LEGACY_IMPLEMENTATION_NOTES §1) | mel 60 겹침 (코드 확인) | time transformer + RoPE (코드 확인) | freq transformer (코드 확인) | complex mask, stem별 head (코드 확인) | complex mask 곱 | L1 + multi-STFT (코드 확인) | NEEDS_MEASUREMENT | NEEDS_MEASUREMENT | NEEDS_RESEARCH | NEEDS_RESEARCH | MIT | MIT | UNKNOWN | NEEDS_RESEARCH | NEEDS_RESEARCH |
| BS-RoFormer | complex STFT (코드 확인) | 고정 62 비겹침 (core4 yaml) | 동일 구조 (코드 확인) | 동일 | complex mask | complex mask 곱 | NEEDS_RESEARCH | NEEDS_MEASUREMENT | NEEDS_MEASUREMENT | NEEDS_RESEARCH | NEEDS_RESEARCH | MIT(MSST 구현) | N/A | N/A | NEEDS_RESEARCH | NEEDS_RESEARCH |
| SCNet | NEEDS_RESEARCH | | | | | | | | | | | MIT | UNKNOWN | MUSDB | | |
| Demucs / HTDemucs | NEEDS_RESEARCH | | | | | | | | | | | MIT | 제외 | NEEDS_RESEARCH | | |
| BandIt | NEEDS_RESEARCH | | | | | | | | | | | NEEDS_RESEARCH | NEEDS_RESEARCH | NEEDS_RESEARCH | | |
| Banquet | NEEDS_RESEARCH | | | | query decoder | | | | | | | MIT | UNKNOWN | NEEDS_RESEARCH | | |
| Open-Unmix | NEEDS_RESEARCH | | | | | | | | | | | NEEDS_RESEARCH | NEEDS_RESEARCH | NEEDS_RESEARCH | | |
| 2025~2026 신규 MSS | NEEDS_RESEARCH | | | | | | | | | | | | | | | |

## 2. OUR MODEL 후보 (Research Packet 02에서 확정)

| 후보 | 개요 | params | FLOPs | VRAM (3060) | 안정성 | 추론 속도 | 2-stem | 6-stem | 13-stem | 구현 난이도 |
|---|---|---|---|---|---|---|---|---|---|---|
| A | STFT → learnable band projection → T/F transformer → shared backbone → multi stem heads | NEEDS_MEASUREMENT | | | | | | | | |
| B | multi-res STFT + waveform branch → shared latent → query-conditioned decoder | NEEDS_MEASUREMENT | | | | | | | | |
| C | band-split encoder → efficient conformer/transformer → hierarchical stem decoder | NEEDS_MEASUREMENT | | | | | | | | |

측정 셀은 구현 후 실제 값으로만 채운다.

## 3. 열린 설계 결정 (미확정, 동결 금지)

### 3.1 2-stem 출력 방식

| 방식 | 정의 | 비고 |
|---|---|---|
| A | Vocal 예측, `Inst = Mix − Vocal` | 레거시(KJ) 방식. Vocal 오차가 Inst에 그대로 전이 |
| B | Vocal/Inst 독립 예측 + mixture consistency loss | 자유도·파라미터 증가 가능 |
| C | 독립 예측 후 `V + I = Mix`가 되도록 투영 | |

결정은 Packet 01/02 근거와 구현 후 ablation으로 한다. 현재 기록: `candidate = independent heads` (B/C 실험을 위한 코드 경로만 준비, 기본값 미확정).

### 3.2 6-stem 방식 (Packet 03 대기)

6 고정 head / Shared decoder + query / Hierarchical. 근거 없이 선택하지 않는다.
