# OUR Separator v0.1 — 2-Stem Architecture

- 모델 ID `our_separator_v01`, class `OurSeparatorV01`, 코드 `src/engine/models/our_separator_v01/`, config `configs/model/our_separator_v01.yaml`
- 근거: Research Packet 02 (사용자 전달, 2026-10-08). **[P02]** 표기는 Packet이 준 결정/예상값, **MEASURED**는 이 repo에서 RTX 3060으로 직접 잰 값, **ENGINEERING_ESTIMATE**는 측정 전 추정.
- from scratch (`parent_checkpoint = null`). KJ/Mega53/기타 가중치, distillation, 앙상블, 후처리 없음. v0.1은 최종 아키텍처가 아니며 §9의 ablation 대상이 열려 있다.
- 외부 근거 ID [P02]: BS-RoFormer arXiv:2309.02612, Mel-Band RoFormer arXiv:2310.01809, SCNet arXiv:2401.13276, Mixture Consistency arXiv:1811.08521 (ICASSP 2019), MSST `ZFTurbo/Music-Source-Separation-Training`, `lucidrains/BS-RoFormer`, BandIt `kwatcharasupat/bandit`. 이 repo는 이 ID들을 재검증하지 않았다. 논문/공개 구현은 설계 근거일 뿐이며 코드 복사나 pretrained weight 사용이 없다.

## 1. 데이터 흐름

```
mix (B,2,T) 44.1 kHz
 → chunk RMS 정규화 (mixture/target 공통 scale)
 → STFT n_fft 2048 / hop 512 / win 2048 / Hann / complex 유지 (L,R × real,imag)
 → 60 overlapping Mel-like band slice → band별 RMSNorm+Linear → (B, Frames, 60, 192)
 → 6 × AxialBlock [time attn+RoPE → FFN → band attn+RoPE → FFN]  (block 단위 gradient checkpointing)
 → shared decoder trunk (RMSNorm → Linear 192→384 → SiLU → Linear 384→192)
 → band별 출력층 (192 → num_pred × 2ch × bins × 2), zero-init
 → 겹친 band 평균 → bounded complex mask (2·tanh(x/2))
 → mixture STFT × mask → iSTFT (length = T)
 → output consistency (project | soft | residual)
 → scale 복원 → SeparationOutput(stems{vocals, instrumental}, aux{input_scale, raw_*})
```

## 2. 결정표

| 항목 | 값 | 출처 / 이유 |
|---|---|---|
| chunk | 131584 samples (≈2.9838 s, 257×hop, 258 frames) | [P02] 3초대 chunk가 단일 GPU 반복 학습에 현실적. 6초(263168)는 v0.2 후보 |
| STFT | 2048 / 512 / 2048, Hann, onesided, normalized=false, 1025 bins | [P02] |
| 입력 | complex 전부 보존, magnitude-only 금지 | [P02] |
| band | 60개 overlapping, Mel(HTK) 기반 contiguous slice, 자체 구현(librosa 없음), 전체 bin 커버(DC/Nyquist 포함), 결정적, 매핑은 체크포인트 buffer `band_slices_buf`에 기록되고 불일치 시 load 거부 | [P02] |
| band projector | band별 RMSNorm → Linear(4·width, 192) | [P02] |
| dim / depth / heads / dim_head | 192 / 6 / 6 / 32 | [P02] |
| attention | `F.scaled_dot_product_attention` + RoPE, dropout 0, 외부 flash-attn 의존 없음 | [P02] |
| FFN | expansion 2, SiLU | [P02]: 3060용 의도적 축소 |
| decoder | shared trunk + band별 출력층. stem 수가 늘어도 출력층만 선형 증가 | [P02] |
| mask | complex, `bound·tanh(raw/bound)` (bound 2.0), 독립 module, `unconstrained`로 교체 가능 | [P02] |
| 2-stem 방식 | 기본 `project`(C): `s_i' = s_i + (mix − Σs)/N`. `soft`(B), `residual`(A)도 같은 backbone에서 선택 가능 | [P02] 동결 아님. A/B/C benchmark 후 결정 |
| loss | waveform L1 (w=1) + multi-res STFT (w=1; 2048/512/2048, 1024/256/1024, 512/128/512; spectral convergence + log-mag L1) | [P02] |
| 기본 OFF loss | `si_sdr`, `mixture_l1`(soft 모드 전용) 구현·등록됨. leakage/hierarchy/confusion은 미구현 (정의 미동결) | [P02] |
| optimizer | Adam lr 5e-5, betas (0.9,0.999), eps 1e-8, wd 0, grad clip 1.0 | [P02] |
| scheduler | ReduceLROnPlateau mode=max, factor 0.5, patience 3, min_lr 1e-6, monitor `val_si_sdr` (POC; 실제 primary metric은 benchmark 데이터 준비 후) | [P02] |
| batch | 1 × accumulation 8 (effective 8), AMP fp16 + GradScaler, gradient checkpointing ON | [P02] |
| inference | chunk 131584, overlap 0.5 (65792), batch 1, 기존 `engine.inference.separate` | [P02] |

## 3. Packet에 없어서 구현 중에 내린 결정 (모두 config/module 경계로 교체 가능)

| 결정 | 내용 |
|---|---|
| band 경계 알고리즘 | Mel 끝점 62개 → band b의 지원 = Mel 끝점 b … b+2 사이 bin. 빈 band는 1 bin로 확장, 틈은 앞 band가 흡수 |
| 겹친 bin의 mask | band별 raw 출력을 bin마다 평균한 **뒤** activation 적용 (activation 후 평균과 다름) |
| 정밀도 | STFT/iSTFT, 출력층, mask 곱, projection은 autocast 밖에서 fp32. backbone과 band projector만 fp16 |
| loss 정규화 | 모델이 `aux["input_scale"]`을 내면 loss가 pred/target을 같은 scale로 나눠 계산(Packet의 "target도 동일 scale로 나눈다"). 끄려면 loss kwargs `use_input_scale: false`. 모델 출력과 metric은 원래 scale |
| zero-init 효과 | 출력층 zero-init + bounded mask → 초기 mask 0 → `project` 모드 초기 출력은 `mix/2`씩 (테스트됨) |
| RoPE | half-split 회전, base 10000, attention마다 인스턴스(파라미터 없음) |
| RMSNorm eps | 1e-6, fp32 계산 |
| 학습 config | `deterministic: false` (속도). bit-exact resume은 CPU tiny 모델 테스트로 보장 |

## 4. 측정 결과 (MEASURED, RTX 3060 12 GiB, torch 2.5.1+cu121)

원본: `docs/benchmark/our_separator_v01_profile.json`. 입력은 무작위 파형, AMP fp16, loss는 §2 baseline.

| 항목 | 값 | Packet 기준 |
|---|---|---|
| 파라미터 (총/학습) | 8,316,732 / 8,316,732 | 목표 8~12M, hard gate 15M → **PASS** (Packet 추정 8~10M과 일치) |
| fp32 체크포인트 | 31.7 MiB | |
| 학습 peak VRAM, batch 1, checkpointing ON | **373 MiB** | 목표 ≤ 9.5 GiB → **PASS** (약 4%) |
| 학습 peak VRAM, batch 1, checkpointing OFF | 1,701 MiB | 속도 비교용 |
| 학습 peak VRAM, batch 2 / 4 (ON) | 664 / 1,275 MiB | |
| fwd+bwd (batch 1) | 227 ms (ON) / 189 ms (OFF) | checkpointing 비용 약 +20% |
| forward only | 70 ms | backward ≈ fwd+bwd − fwd ≈ 157 ms (ON) |
| 추론 (batch 1, 3 s chunk, fp16) | 64 ms, peak 181 MiB, **RTF ≈ 0.021** | |
| forward FLOPs (3 s chunk, `FlopCounterMode`) | 1.39e11 | 카운터가 지원하는 연산 기준 |
| frames | 258 | |

### 파라미터 breakdown (MEASURED)

| 모듈 | params | 비중 |
|---|---|---|
| band projector | 1,547,028 | 18.6% |
| backbone (6 blocks) | 3,550,464 | 42.7% |
| decoder trunk | 148,224 | 1.8% |
| 출력 projection (band별) | 3,071,016 | 36.9% |
| 합계 | 8,316,732 | |

decoder 전체(trunk + 출력층)는 38.7%. 출력층은 stem 수에 선형 비례하므로 6-stem이면 약 9.2M이 되어 총합이 약 14.5M (**ENGINEERING_ESTIMATE**: 출력층만 3배, 나머지 동일 가정; 6-stem 구현 전까지 미측정)이며, 15M gate에 근접한다는 점이 Packet 03의 설계 제약이다.

**해석 주의**: peak VRAM이 예상보다 훨씬 낮다. 따라서 dim 192 / 3초는 VRAM 한계가 아니라 Packet이 정한 보수적 출발점이다. Packet 지시대로 batch/크기를 바로 키우지 않았고, AB-04~06(depth, dim, context) 실험에서 headroom을 쓴다.

## 5. Overfit (learnability) 결과

원본: `docs/benchmark/our_separator_v01_overfit.json`, run `20261008T063321-our_v01_overfit-ef84ffdc` (150 optimizer step ≈ 1200 chunk, 약 5분).
데이터: 결정적 procedural sine-sum 16 scene (validation = training scene). **분리 품질/제품 성능이 아니다.**

| 조건 | 결과 |
|---|---|
| loss 지속 감소 | train loss step 1: 1.80 → step 150: 0.59 (val_loss 1.76 → 0.62) |
| 초기 대비 SDR/SI-SDR 개선 | val SI-SDR step 10: 0.71 dB → step 150: 26.9 dB (SDR 3.0 → 26.5 dB) |
| stem swap | 없음 (각 stem이 자기 target과의 SDR > 다른 stem target과의 SDR: vocals 26.1 vs −3.0, instrumental 26.9 vs −3.8 dB) |
| collapse | 없음 (출력/target 에너지비 1.004, 0.998) |
| NaN/Inf | 없음 |
| mixture 합 오차 | val 재구성 오차 −125.8 dB (fp16 AMP 추론 포함) |
| scheduler | plateau가 step 120 이후 lr 5e-5 → 2.5e-5 로 1회 감소 |
| 체크포인트 | step 50/100/150 + sidecar, 재로드 후 추론·metric 정상 |

한계: 이 scene은 stem마다 주파수 대역이 분리된 sine이라 주파수 mask만으로 풀린다. 이 테스트가 증명하는 것은 "backbone·mask·iSTFT·projection·loss·trainer가 끝까지 학습 가능하게 연결됨"이며 음악 분리 능력이 아니다. 실제 성능은 Data Factory/GREEN 데이터 이후 측정한다. 이 run의 `experiment.json`은 `git_dirty: true`다 (코드 commit 전에 실행). 재현 가능한 기록이 필요하면 commit된 코드로 같은 config를 다시 실행한다.

## 6. 테스트
`tests/test_our_separator_v01.py` (25 collected) — 사양값, 파라미터 예산, band 커버리지, odd/even 길이 shape, 합=mix(project/residual), soft는 합 미보장, N-stem 일반화, 초기 상태, scale 등변성, 모든 모듈 gradient 도달(checkpointing on/off, 동일 grad), loss 유한성, band layout 불일치 거부, ckpt 왕복, chunked 추론, CUDA fp16 AMP full-spec 학습 스텝. 전체 57개 통과 (CPU 단위 + CUDA 2개).

## 7. 구현하지 않은 것 (Packet §25)
waveform branch, Demucs식 hybrid, Mamba, Conformer, query decoder, source discovery, learnable band boundary, SCNet 압축, 13-stem, lead/backing, KJ distillation/초기 weight, pretrained weight, ensemble, 후처리.

## 8. 6-stem 확장 대비 상태
stem 이름/개수는 config(`stems`)에서만 온다 (6-stem 구성으로 forward·합=mix 테스트 통과). backbone은 stem 독립. projection은 equal weight이며 `MixtureProjection`에 격리되어 있어 energy-weighted / learned 변형으로 교체 가능.

## 9. 다음 ablation 순서 [P02]
AB-01 C vs B, AB-02 C vs A, AB-03 60 overlapping Mel vs fixed BS band, AB-04 depth 6 vs 8, AB-05 dim 192 vs 256, AB-06 3 s vs 6 s context, AB-07 FF expansion 2 vs 4. 평가 지표: vocal/instrumental SDR·SI-SDR, mixture 재구성 오차(평균·최대 절대), 향후 instrumental 내부 보존(drums/bass/guitar/piano). 단일 sine-sum 데이터로는 ablation을 수행하지 않는다 (실제 분리 데이터 필요).
