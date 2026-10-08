# Architecture Comparison

출처 표기: **[P01]** = Research Packet 01 v1 (외부 Research Lead 작성, 사용자가 2026-10-08에 전달). Packet은 사이트명(arXiv/GitHub/Hugging Face)만 주고 개별 URL을 주지 않았다. URL을 이 repo가 지어내지 않는다 → `URL: NEEDS_URL`. **[CODE]** = 레거시 코드를 직접 읽음 (`LEGACY_IMPLEMENTATION_NOTES.md`). **[PHASE0]** = 레거시 문서/설정/해시 계산.
[P01] 수치는 보고값이며 이 repo에서 재현·검증하지 않았다. 확인 날짜: 2026-10-08 (전달일). 외부 사실을 추론으로 채우지 않는다: 근거 없는 칸은 `NEEDS_RESEARCH`.

## 0. 하드 제약 (개발 기준)

| 항목 | 값 |
|---|---|
| Dev GPU | RTX 3060 12 GiB (Windows) |
| 학습 | 한 장에서 반드시 동작. AMP 필수, gradient accumulation 허용, checkpointing 필요 시 |
| 추론 | 12 GiB보다 훨씬 낮게 |
| 규모 | 수 M ~ 수십 M params 우선 |
| chunk | 3~8 s부터 |
| 탈락 기준 | 24 GB+ / 다중 GPU 전제 설계 |

## 1. 기존 모델 비교

| 모델 | 핵심 구조 | 우리가 가져올 것 | 가져오지 않을 것 | CODE | WEIGHT | TRAIN DATA | Lineage |
|---|---|---|---|---|---|---|---|
| KJ Mel-Band RoFormer | overlapping mel 60 band, T/F axial transformer, stem별 complex mask head [CODE] | overlapping perceptual band, T/F 분리 모델링, complex mask | stem별 독립 대형 head, `Inst = Mix − Vocal` 추론 | MIT [PHASE0] | MIT. HF checkpoint 2026-04-22 GPL-3.0→MIT 변경 기록, 파일 SHA-256이 Phase 0 계산값(`87201f4d…c7559e`)과 HF 값 일치 [P01] | UNKNOWN | experiment/reference/teacher/fine-tuning 가능. 최종 clean lineage 제외 |
| BS-RoFormer | complex spectrogram → band split(비겹침) → inner/inter-band hierarchical transformer + RoPE → multi-band mask. 작은 버전 MUSDB18HQ 단독 평균 SDR 9.80 dB 보고 [P01] | complex STFT, T/F 분리 모델링, band-level latent, RoPE, mask estimation | stem마다 큰 MaskEstimator를 키우는 구조 (6/13 stem에서 head 파라미터 선형 증가 [CODE]) | MIT (lucidrains 구현) [P01] | 별도 확인 필요 [P01] | 논문: MUSDB18HQ + 추가곡 [P01] | 핵심 연구대상 |
| Mel-RoFormer | BS-RoFormer의 비겹침 경험적 band를 overlapping Mel band로 교체. MUSDB18HQ에서 BS-RoFormer 대비 vocals/drums/other 향상 보고 [P01] | overlapping perceptual band (v0 첫 frontend 기본 후보) | - | permissive 구현 존재 [P01] | checkpoint별 별도 [P01] | 논문: MUSDB18HQ [P01] | 핵심 연구대상 |
| SCNet | spectrogram을 subband로 나눠 정보량 적은 대역을 더 강하게 압축(주파수별 다른 압축률). CPU 추론이 HT-Demucs의 48% 보고 [P01] | unequal band compression 아이디어 (RoFormer-style T/F 앞단에 A/B 실험) | official checkpoint | MIT [P01] | **UNKNOWN**. 2026 license 문의 issue(#35) 열려 있고 공식 답변 없음 [P01] | MUSDB 계열 (README 명시) [P01] | 코드/논문 REFERENCE_ONLY, weight EXCLUDED |
| Demucs / HTDemucs | Hybrid Demucs: waveform+spectrogram 병행. HT-Demucs: 두 domain bottleneck에서 self/cross attention 교환 [P01] | 아이디어(cross-domain)만 → waveform branch는 v1 이후 ablation | pretrained weights | MIT [P01] | 상업 라이선스 공식 미해결 → 제외 (issue #327) [P01] | MUSDB + 추가 [P01] | 코드/논문 REFERENCE_ONLY, weight EXCLUDED |
| BandIt | common encoder + stem별 decoder. 계산 공유. ERB48 BandIt 32.6M params, 6 s chunk 벤치마크 peak 약 519.5 MB 보고 [P01] | **Shared Encoder** (6-stem 핵심 원칙) | - | Apache-2.0 [P01] | 별도 [P01] | DnR/MUSDB 등 [P01] | 중요 연구대상 |
| Banquet | shared encoder → audio query → FiLM conditioning → single decoder. 24.9M params로 MoisesDB에서 6-stem HT-Demucs에 근접, guitar/piano 우세 보고 [P01] | query conditioning 아이디어 (13+ 단계용) | official checkpoint, 2/6 stem 단계 도입 | MIT [P01] | **UNKNOWN** (`WEIGHT_LICENSE_UNKNOWN`) | MoisesDB [P01] | 코드 REFERENCE_ONLY, weight EXCLUDED |
| Open-Unmix | 단순 baseline, residual/Wiener [P01] | baseline 참고 | UMXL weights | MIT [P01] | umxl: CC BY-NC-SA 4.0 (README) → RED. 그 외 "일부 제한" [P01] (정확한 모델별 값은 NEEDS_RESEARCH) | MUSDB/private [P01] | 코드 reference, umxl EXCLUDED |
| BSMamba2 (2025) | Mamba2 + band split + dual-path. vocal 분리 cSDR 11.03 dB 보고. 간헐적 vocal 구간의 장기 context 강조 [P01] | time attention `O(T²)` 대체 가능성(별도 실험 branch) | 공식 checkpoint | MIT [P01] | 별도, license 불명 (제3자 감사 프로젝트도 NOASSERTION) [P01] | MUSDB18-HQ [P01] | 실험 후보. 기본 backbone 아님 (아래 §3) |
| TS-BSmamba2 | 2-stage residual refinement [P01] | refinement 단계 아이디어 | - | Apache-2.0 [P01] | 별도 확인 [P01] → NEEDS_RESEARCH | 별도 확인 [P01] → NEEDS_RESEARCH | 연구 후보 |
| MuS3D (2026-09) | mixture 안의 active source를 자동 발견해 query 형태로 분리 [P01] | 장기 13+ 설계 시 재조사 | - | 실사용 라이선스 검증 필요 [P01] → NEEDS_RESEARCH | NEEDS_RESEARCH | NEEDS_RESEARCH | 장기 연구 (v0 무관) |
| 2025~2026 기타 MSS | Packet 01에 포함되지 않음 | | | NEEDS_RESEARCH | NEEDS_RESEARCH | NEEDS_RESEARCH | NEEDS_RESEARCH |

수치 비교용 열(params / FLOPs / 학습 VRAM)은 우리 구현으로 직접 측정한다 (`NEEDS_MEASUREMENT`). [P01]의 BandIt 수치만 외부 보고값이다.

## 2. OUR Separator Base Architecture Family — 1순위 가설 [P01 §13], **Frozen 아님**

```
Stereo waveform → Complex STFT → Band Projector → Shared Band Encoder
→ Efficient T/F blocks (time modeling + frequency modeling) → Shared Latent
→ lightweight stem heads → complex masks → (optional) mixture projection → iSTFT
```

초기에는 waveform branch를 넣지 않는다 ([P01] 권고: 3060 12 GiB에서 강한 frequency-domain baseline 먼저, 성능 향상이 확인되면 추가). KJ 복사본이 아니다: 아래 항목을 우리가 따로 정한다.

### 2.1 채택 수준 (Packet 01 추천)

| 기술 | 수준 |
|---|---|
| Complex STFT | 채택 |
| Overlapping perceptual bands | v0 강한 후보 |
| RoPE | 채택 후보 |
| Time/Frequency 분리 modeling | 채택 |
| SCNet-style unequal band compression | A/B 실험 |
| Shared encoder | 강하게 채택 |
| Stem별 거대한 decoder | 지양 |
| Complex mask | 채택 |
| Mixture consistency / projection | 실험 |
| Waveform branch | v1 이후 |
| Query decoder | 13+ 이후 |
| Mamba2 temporal block | 별도 실험 |
| 여러 대형 모델 cascade | 최종 구조에서 제거 |

### 2.2 Ablation 대상 (동결 금지)

1. fixed BS band vs overlapping perceptual band (장기: fixed Mel → learnable band projection)
2. uniform band vs SCNet-style unequal compression
3. Transformer time block vs 향후 Mamba/SSM
4. 2-stem 출력 방식 A / B / C (§4)
5. stem head 파라미터 공유 정도
6. mixture projection 유무
7. loss 조합

### 2.3 스테이지별 순서 [P01]

2 stem: fixed heads → 6 stem: fixed heads vs lightweight shared decoder 비교 → 13+: query decoder 연구.

## 3. 환경 위험 메모

- 레거시 time attention이 가장 비싼 구간 (시퀀스 길이 = 프레임 수) [CODE]. Mamba/SSM 대체가 동기.
- [P01]: upstream Mamba accelerator가 Linux/CUDA 환경을 전제로 한다. 개발 환경은 Windows → 기본 backbone으로 채택하지 않음. 이 repo에서 설치 가능 여부는 미검증 (`NEEDS_MEASUREMENT`).

## 4. 열린 설계 결정 — 2-stem 출력 방식

| 방식 | 정의 |
|---|---|
| A | V 추정, `Inst = Mix − V` (레거시 방식) |
| B | V, I 독립 추정 + mixture consistency loss |
| C | V, I 독립 추정 + 출력 투영으로 `V + I = Mix` 강제 |

[P01] 실험 가치 예상 순서: C → B → A. **예상일 뿐이며 동결하지 않는다.** 동일 backbone에서 세 방식을 비교 가능하게 구현한 뒤 ablation으로 결정한다.

## 5. 후보 구현 표 (Packet 02 이후)

| 후보 | params | FLOPs | 3060 학습 VRAM | 안정성 | 추론 속도 | 2-stem | 6-stem | 13-stem |
|---|---|---|---|---|---|---|---|---|
| Family 가설(§2) 첫 변형 | NEEDS_MEASUREMENT | NEEDS_MEASUREMENT | NEEDS_MEASUREMENT | | | | | |

n_fft / hop / band 수 / dim / depth / chunk / batch / accumulation / loss / optimizer는 Research Packet 02에서 확정. 그 전에는 코드·문서 어디에도 고정하지 않는다.

## 6. 6-stem 방식 (Packet 03 대기)
6 고정 head / shared decoder + query / hierarchical. [P01]은 BandIt의 shared encoder 원칙을 6-stem 설계 원칙으로 채택할 가치가 있다고 평가했다. 선택은 실험 후.
