# Legacy 구현 분석 (KJ / BS-RoFormer / Mel-Band RoFormer)

출처: 태그 `legacy-baseline-2026-10-08`의 `separation/src/music_analyzer/vendor/msst/` (ZFTurbo MSST commit `84b1eac…`, MIT). 코드를 직접 읽은 사실만 적는다. 논문 주장·성능 비교는 Research Packet 01 대기 (`NEEDS_RESEARCH`).
OUR MODEL은 이 코드를 복사하지 않고 아래 모듈 경계를 명세로 삼아 자체 구현한다(clean-room). 재사용 시 `docs/legal`에 source/file/license/modification을 기록한다.

## 1. 공통 데이터 흐름 (`mel_band_roformer.py` MelBandRoformer.forward)

1. 입력 `(b, 2, t)` → `torch.stft(n_fft=2048, hop, win=2048, hann)` → complex.
2. 스테레오를 주파수 축에 병합 `b (f s) t c`.
3. **Band split**: 밴드별 주파수 인덱스를 한 번에 gather → `(f c)` 특징 → 밴드마다 `RMSNorm + Linear(dim_in → dim)`. 출력 `(b, t, bands, dim)`.
4. **Axial transformer × depth**: 각 층 = (선택: linear attention) → **time transformer**(시간축 attention, 밴드별 독립 시퀀스) → **freq transformer**(밴드축 attention, 프레임별 독립 시퀀스). time/freq 각각 RoPE(rotary) 사용. 옵션: skip_connection(이전 층 합), PoPE, gradient checkpoint.
5. **Mask estimator**: stem마다 별도 head. 밴드마다 `MLP(dim→4·dim→2·dim_in, tanh) → GLU`. 출력은 complex mask.
6. **Mel 전용**: 밴드가 서로 겹침(mel filterbank > 0). 겹치는 주파수의 mask를 `scatter_add` 후 `num_bands_per_freq`로 평균. BS-RoFormer는 겹치지 않는 고정 `freqs_per_bands`.
7. `stft × mask` → `istft` (zero_dc 옵션) → 파형. mask는 복소수 곱(위상 포함 수정).
8. 손실(코드 내장): 파형 L1 + multi-resolution STFT L1 (창 4096/2048/1024/512/256, hop 147). **mixture consistency, SI-SDR, leakage 항 없음.**

## 2. 모듈 경계 (OUR MODEL 명세 입력)

| 모듈 | 입출력 | 비고 |
|---|---|---|
| STFT frontend | wave → complex `(b,f,t)` | 고정. 학습 가능 대역 투영은 후보 A에서 실험 |
| BandSplit | `(b,t,Σ2fs)` → `(b,t,B,d)` | 밴드별 독립 Linear. 파라미터 지배항 중 하나 |
| TimeBlock / FreqBlock | `(b,t,B,d)` 양방향 | attention 비용: time `O(B·T²)`, freq `O(T·B²)` |
| MaskEstimator (stem head) | `(b,t,B,d)` → complex mask | stem마다 독립 head → 확장 시 head 수에 선형 증가 |
| Overlap-average (mel) | mask → 주파수별 평균 | BS에는 없음 |
| Loss | wave, multi-STFT | 외부에서 교체 가능하게 분리 필요 |

## 3. 하이퍼파라미터 비교 (레거시 yaml)

| | KJ Mel | core4 (BS, 4-head) |
|---|---|---|
| dim / depth | 384 / 6 | 256 / 12 |
| bands | mel 60 (겹침) | 62 (고정, 비겹침) |
| n_fft / hop | 2048 / 441 | 2048 / 512 |
| chunk | 352800 (8 s) | 441000 (10 s) |
| time/freq depth | 1 / 1 | 1 / 1 |
| mask_est depth | 2 | 레거시 yaml 참조 |
| flash_attn | true | true |
| 학습 설정 | batch 4, lr 1e-5, AMP, EMA 0.999 | - |

파라미터 수·FLOPs·VRAM은 **측정하지 않았다**. Phase 2에서 `torchinfo`/프로파일러로 측정한다 (현재: NEEDS_MEASUREMENT).

## 4. 12 GiB 제약에서 읽히는 위험 지점 (코드 근거, 수치는 미측정)

- time attention 시퀀스 길이 = 프레임 수. 8 s, hop 441 → 약 800 프레임. hop을 키우거나 chunk를 3~6 s로 줄이면 선형~제곱으로 감소.
- freq attention 길이 = 밴드 수(60~62). 작아서 비용 낮음.
- BandSplit/MaskEstimator는 밴드마다 Linear → 밴드 수·dim에 비례한 파라미터. stem head당 MaskEstimator 1개 → 6-stem에서 head 파라미터가 6배.
- `use_torch_checkpoint`가 이미 구현되어 있어 gradient checkpointing 선례가 있음.

## 5. KJ 학습 설정에서 읽은 사실

- `num_stems: 1` (vocals만). instrumental은 추론 코드에서 `mix − vocals`.
- 학습 loss는 위 §1-8과 동일(L1 + multi-STFT). `other_fix: true` 설정은 "other가 실제로 instrumental인지" 확인용.

## 6. 미해결 (`NEEDS_RESEARCH`)

- Mel vs 고정 band 중 어느 쪽이 2-stem에서 유리한가 (논문/ablation 근거)
- SCNet/Demucs/Banquet의 입력 표현·디코더 상세
- 학습 가능한 band projection의 선행 연구
- 2-stem 출력 방식 A/B/C 비교 근거
