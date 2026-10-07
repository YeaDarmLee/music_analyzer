# Commercial Separator Finalization (진행 중)

법률 자문이 아니다. 측정값은 이 저장소에서 직접 실행한 결과이며, 측정하지 않은 항목은 "미측정/추정"으로 표시했다.
상태: **commercial_6 / commercial_13은 아직 APPROVED가 아니다.** 2/6/13 모두 `release_presets.json`에서 `VALIDATING`.

## 0. 출발점 (SIX_DIAGNOSIS 결과)

core4는 공식 Mega53 head와 비트 단위로 동일하다. commercial_6의 손실(piano -1.13, bass -1.01, drums -2.21, other -0.91 dB)은 전부 모델 단계에서 생기며 후처리 손실은 0이다. 없는 악기 오탐은 basic -84~-92 dB, core4 -47~-55 dB.

## Phase A — 추론 파라미터만 변경 (weights/routing/RULES/STRENGTH 불변)

코드에서 실제로 지원하는 파라미터(`roformer_runner.run_roformer` / `overlap_infer`): `segment_sec`(청크), `overlap`(stride = 청크×(1−overlap)), fp16 autocast(코드에 고정). 크로스페이드 윈도우는 10% 선형 페이드로 고정, batch=1, RoFormer에는 shift/TTA가 없다(`shifts`는 Demucs 경로). 따라서 grid는 segment × overlap × precision. 추가로 실제 코드에 없는 **실험용** `tta_swap`(L/R 교환 평균)도 측정했다. 현재 production = core4 10 s(Mega53 학습 청크 441000), overlap 0.4. basic 6stem 프리셋은 13.35 s.

10 case GeneralUser GS, 입력은 깨끗한 mix(실제 파이프라인 instrumental과 동일한 결과를 SIX_DIAGNOSIS part 2에서 확인). SDR(dB), FP = 없는 악기 평균 오탐(mix 대비 dB, 낮을수록 좋음), 시간 = 오디오 1분당 초, VRAM = PyTorch 최대 할당.

| Config | Piano | Guitar | Bass | Drums | Other | FP | s/min | VRAM MB |
|---|---|---|---|---|---|---|---|---|
| basic 6s (13.35 s, .4) | 9.21 | 3.43 | 11.52 | 15.46 | 12.38 | -87.8 | 12.1 | 1583 |
| **core4 production (10 s, .4, fp16)** | 8.05 | 3.72 | 10.80 | 13.20 | 10.70 | -50.4 | 11.1 | 972 |
| core4 overlap .25 | 8.00 | 3.93 | 10.46 | 13.22 | 10.86 | -51.5 | 8.6 | 972 |
| core4 overlap .5 | 8.15 | 3.93 | 11.04 | 13.32 | 10.87 | -51.0 | 11.1 | 972 |
| core4 overlap .6 | 8.13 | 3.93 | 10.88 | 13.31 | 10.83 | -50.9 | 16.6 | 972 |
| core4 overlap .75 | 8.27 | 4.00 | 10.89 | 13.36 | 10.94 | -51.4 | 25.5 | 972 |
| core4 segment 7 s | 7.81 | 3.69 | 10.14 | 12.96 | 10.61 | -50.1 | 10.3 | 786 |
| core4 segment 12 s | 8.29 | 3.84 | 10.98 | 13.24 | 10.74 | -50.7 | 10.3 | 1098 |
| core4 segment 15 s | 8.26 | 3.81 | 10.62 | 13.32 | 10.83 | -51.5 | 13.1 | 1282 |
| core4 fp32 | 8.05 | 3.72 | 10.80 | 13.20 | 10.70 | -50.4 | 23.7 | 1162 |
| core4 overlap .75 + fp32 | 8.27 | 4.00 | 10.89 | 13.36 | 10.94 | -51.4 | 51.5 | 1162 |
| core4 tta_swap (실험, 코드에 없음) | 8.13 | 3.81 | 10.86 | 13.25 | 10.77 | -49.9 | 22.3 | 972 |

합계 오차는 전 설정에서 6.0e-8. 시간은 단일 측정이라 ±수 % 오차가 있다(예: overlap .25가 가장 빠르게 나온 값 포함).

**결론: 추론 파라미터로는 복구되지 않는다.** 최선(overlap .75)도 piano +0.22, bass +0.09, drums +0.16 dB뿐이고 비용은 2.3배다. basic 대비 격차(piano -0.94, bass -0.63, drums -2.10)의 90% 이상이 남는다. 오탐은 어떤 설정에서도 -50 dB 부근에서 변하지 않는다. fp32는 fp16과 SDR이 같아 정밀도는 원인이 아니다. 64-case 확대는 후보가 없어서 하지 않았다. → 채택하지 않음.

## Phase B — Mega53 나머지 head의 보조 evidence

head 이름은 공식 config에서 읽었다(53개, 예: kick, snare, toms, hh, percussion, tambourine, congas, timpani, triangle, double-bass, digital-piano, keys, harpsichord, organ, acoustic-guitar, electric-guitar, banjo, mandolin, ukulele, dobro). 실제 존재하는 이름만 후보로 썼다. 10 case, `scripts/probe-mega53-aux.py`, 원자료 `COMMERCIAL_CLEAN_AUX_RESULTS.json`.

핵심 질문은 "core4가 놓친 에너지(GT − core4)가 다른 head에 있는가"다.

| 대상 | 보조 head 합 | GT와의 상관 | **놓친 부분과의 상관** | 놓친 에너지 recall | 오탐(타 악기 설명량 대비, dB) |
|---|---|---|---|---|---|
| drums | kick+snare+toms+hh+percussion+tambourine+congas+timpani+triangle | 0.95 | **-0.03** | -31.6 dB | -26.2 |
| bass | double-bass | 0.83 | 0.19 | -18.0 dB | -18.0 |
| piano | digital-piano+keys+harpsichord+organ | 0.83 | **-0.05** | -25.0 dB | -11.7 |
| guitar | acoustic+electric+banjo+mandolin+ukulele+dobro | 0.70 | 0.23 | -12.9 dB | -9.0 |

- 보조 head는 GT와는 잘 맞지만(그 head들이 core4 head와 같은 내용을 보기 때문), **core4가 놓친 부분과는 거의 상관이 없다.** 새 정보가 아니라 같은 신호의 중복이다.
- 이동 시험(잔차 `R`에서 `min(1,|STFT(aux)|/|STFT(R)|)` 마스크로 stem에 옮김, 합계 보존 6e-8 이하)은 전부 악화: piano 8.05→1.58, guitar 3.72→2.41, bass 10.80→9.80, drums 13.20→10.61. 'other'도 같이 악화.
- 결론: **기각.** 다른 head로 core4의 부족분을 메울 수 없다.

## Phase C — Mixture-consistent Wiener refinement

Norbert 0.2.1: MIT(Inria, LICENSE가 wheel에 포함), 의존성 scipy만, wheel sha256 `409ac3f173cfb1fdaad21563b8f730d7cbe01af81349bcd96fb2b8b9d5f74339`. 프로젝트 venv에는 설치하지 않고 `data/tmp-norbert/site`에서 import해 평가했다. core4 raw 4 stem + 잔차를 소스로 사용. `scripts/eval-wiener-refine.py`, 원자료 `COMMERCIAL_CLEAN_WIENER_RESULTS.json`. 마지막 소스는 항상 mix − Σ(나머지)로 다시 계산해 합계 오차는 6e-8 이하.

| Variant | Piano | Guitar | Bass | Drums | Other | FP(mix 대비 dB) | CPU s/15 s |
|---|---|---|---|---|---|---|---|
| A core4 raw | 8.05 | 3.72 | 10.80 | 13.20 | 10.70 | -49.8 | 0.0 |
| B ratio mask (5 src) | 3.62 | 2.34 | 5.39 | 9.42 | 7.29 | -52.8 | 0.9 |
| C Wiener 1회 (5 src, 잔차 포함) | 2.29 | 0.94 | 3.99 | 7.91 | 4.58 | -94.1 | 2.0 |
| D Wiener 2회 (5 src) | 1.46 | 0.48 | 3.02 | 7.58 | 3.45 | -184.9 | 3.1 |
| C4 Wiener 1회 (4 src, 잔차 없음) | -0.01 | 0.36 | 3.43 | 7.30 | 2.47 | -42.4 | 1.7 |

- 모든 변형이 raw보다 훨씬 나쁘다(drums -3.8 ~ -5.9 dB). 오탐이 줄어든 것(-94, -185 dB)은 stem을 비워서 생긴 효과이지 분리 개선이 아니다.
- 원인 확인: GT 소스의 정확한 magnitude를 넣은 oracle 시험에서도 softmask drums 9.1 dB, Wiener 7.9 dB. 이 합성 믹스에서는 magnitude만 쓰는 마스크가 모델의 complex 마스크보다 구조적으로 불리하다(파이프라인 오류가 아님).
- spatial artifact(stereo 상관·L/R 레벨차)는 raw 대비 약간 커졌다(drums 상관 오차 0.002→0.004~0.005, L/R 0.03→0.06~0.09 dB). 의미 있는 수준은 아니다.
- RAM 증가는 최대 20 MB. 비용 문제가 아니라 품질 문제다.
- 결론: **기각.** Norbert는 라이선스상 깨끗한 후보이지만 이 용도에서는 쓰지 않는다. commercial registry에는 올리지 않았다.

## Phase D — 외부 separator 후보 (코드 / 가중치 / 학습데이터 분리)

확인한 근거만 적는다. "확인 못 함"은 근거를 찾지 못했다는 뜻이며 허용을 의미하지 않는다. 체크포인트 SHA256은 후보가 LEGAL_REVIEW 이상으로 올라간 뒤 exact 파일 기준으로 기록한다(현재 미수집).

| Candidate | Code | Weight | Training Data | Commercial | Quality | Decision |
|---|---|---|---|---|---|---|
| Spleeter 5stems | MIT (README: "The code of Spleeter is MIT-licensed") | **저장소 README에는 가중치 라이선스 문장이 없다.** 논문/프로젝트 설명에는 모델도 MIT로 배포된다는 서술이 있다고 알려져 있으나 이번에 exact 릴리스 파일 기준으로 확인하지 못함 | 비공개 (저작권 때문에 공개하지 않았다고 알려짐). 출처 추적 불가 | 저작권 곡 사용 시 권리자 허락 필요(README 경고). 가중치 근거 미확정 | 미측정. 5stem 출력은 대역이 제한된 구형 구조라 core4보다 낮을 가능성이 높음 | **LEGAL_REVIEW** (자동 승인 금지. 벤치마크는 법무 검토 통과 후 필요하면) |
| Open-Unmix umxl | MIT | **CC BY-NC-SA 4.0 (README에 비상업 명시)** | MUSDB18-HQ + 추가 데이터 | **불가** | - | **REJECTED** |
| Open-Unmix umx / umxhq | MIT | README 발췌에서 라이선스 명시 확인 못 함 | MUSDB18 / MUSDB18-HQ (교육/연구 제한 데이터셋) | 불가로 간주 | - | **REJECTED** (benchmark 참고용으로도 production 의존성 금지) |
| Demucs htdemucs / htdemucs_ft / hdemucs_mmi | MIT | README에 가중치 라이선스 문장 없음 | MUSDB + 추가 800곡(출처 미공개) | 근거 부족 | - | **DEV_ONLY** (exact 체크포인트별 근거가 나오기 전까지) |
| Demucs mdx / mdx_extra | MIT | 위와 동일 | mdx: MUSDB18-HQ만, mdx_extra: 추가 데이터(MUSDB test 포함) | 근거 부족 | - | **DEV_ONLY** |
| MDX23C DrumSep 커뮤니티 가중치 | 코드 MIT | 원 저작자 라이선스 불명, 미러 라벨은 근거 아님 | 불명 | 불명 | 미측정 | **REJECTED** |
| BS-RoFormer / MelBand RoFormer 커뮤니티 체크포인트 | 코드 라이선스는 별개 | 원 배포자 문서가 없으면 제외 | 불명 | - | - | 해당 체크포인트별 **DEV_ONLY/REJECTED** (이미 `bs_6stem_fixed`, becruily karaoke가 UNKNOWN으로 분류됨) |
| SCNet, Bandit, MDX(원본), AudioSep 등 | 조사하지 않음 | 조사하지 않음 | 조사하지 않음 | - | - | **미조사** (이번 범위에서 근거를 수집하지 못함) |
| Mega53 (현재 사용) | 저장소 MIT | MIT 허가가 이슈 #245 답변에 근거(사용자가 제공한 근거, 원 저작자 서면은 별도) | **학습 데이터 출처 미확인** | 사용자 근거에 의존 | 위 측정값 | 현 core4/vocal2/mega5/mega7의 기반. **재검증 필요 항목** |

공통 원칙: "저장소가 MIT"는 가중치나 학습데이터의 허락이 아니다. 위 표에서 `APPROVED_CANDIDATE`로 분류된 외부 후보는 없다. Mega53 자체도 학습 데이터 출처가 확인되지 않았다는 점이 release gate의 "license evidence 재검증" 항목에 남아 있다.

## Phase E — 자체 학습 Drum Separator (설계만, 구현 안 함)

외부 후보 중 commercial-clean + 품질 우수가 없으므로 fallback R&D로만 설계한다.

- 데이터 후보(확인한 사실):
  - GMD / E-GMD: CC BY 4.0.
  - **StemGMD: CC BY 4.0, 1224 시간 분량의 isolated drum 채널(풀킷 믹스 약 136 시간)**, GMD MIDI를 Logic Pro X의 드럼 샘플 라이브러리 10종(Bluebird, Brooklyn, Detroit Garage, East Bay, Heavy, Motown Revisited, Portland, Retro Rock, Roots, SoCal)으로 렌더링.
  - **blocker/주의**: 데이터셋 자체는 CC BY 4.0이지만 렌더링 소스가 Apple Logic 샘플 라이브러리다. 샘플 기반 파생 오디오의 재배포/학습 사용이 Apple 라이선스상 문제 없는지는 **확인하지 못했다.** 법적 검토 항목으로 남긴다.
  - **품질 위험**: 킷이 10종뿐이고 전부 샘플 기반 합성이다. 실제 녹음된 드럼, 룸 리버브, 믹스 처리에 대한 일반화는 보장되지 않는다. 권리를 보유한 실제 녹음 드럼 데이터 확보가 필요하다.
- 금지: 기존 비상업 pretrained weight의 fine-tuning. 무작위 초기화 또는 상업 사용이 확실한 초기화만 허용.
- 구조 후보: 저장소에 이미 vendoring된 BS-RoFormer/MelBand-RoFormer 구현(코드 MIT)의 소형 설정. 입력은 core4가 만든 drums stem(혹은 instrumental)로 하고 kick/snare/hh/기타를 부차 출력으로 두는 방식이 가장 값싸다.
- RTX 3060 12 GB 추정(미측정): fp16, 소형(dim 128~256, depth 6~8), 크롭 6~8 s, batch 2~4. 학습 시간은 수 일~수 주 규모로 추정되며 실제 측정 전에는 신뢰하지 말 것. 평가는 StemGMD 보류 split + 권리 보유 실제 녹음으로 별도 구성해야 한다.
- 결정: 지금은 구현하지 않는다. Phase F 이후 결과(손실 수용 vs 드럼만 교체)에 따라 착수 여부를 정한다.

## Phase F — commercial_2 / 6 / 13 최종 결정 (현재 상태)

| Preset | 상태 | 근거 / 남은 일 |
|---|---|---|
| commercial_2 | VALIDATING | 모델 1개(KJ), 스모크 통과. 품질 비교(GT 없는 보컬)는 lead/backing 검증과 별도 |
| commercial_6 | VALIDATING | 파라미터·보조 head·Wiener로 복구 불가 → 선택지는 (A) 손실 수용, (B) drums만 hybrid, (C) 4악기 전체 교체. 실제곡 청취와 license 재검증 전에는 APPROVED 금지 |
| commercial_13 | VALIDATING (BETA) | 6트랙 core 결정 후 regression 재실행 필요 |

### Release gate 체크리스트 (APPROVED 전 필수)

- [x] inference parameter sweep (Phase A) — 복구 불가 확인
- [x] Mega53 auxiliary evidence 검토 (Phase B) — 기각
- [x] Wiener refinement (Phase C) — 기각
- [~] external commercial candidates 검토 — 문헌/라이선스 조사만 완료, 승인 후보 없음. 모델 벤치마크는 하지 않음
- [ ] 실제 곡 청취 (권리 보유 음원)
- [~] absent-stem 오탐: 측정 완료(-47~-55 dB), 청취 영향 확인 안 됨
- [ ] lead/backing clean GT 확보 및 측정
- [x] 3개 실패 테스트: 시스템 Python으로 돌린 환경 문제로 확정, `.venv`에서 307 passed / 0 failed
- [ ] license evidence 재검증 (Mega53 학습 데이터 출처 포함)

## 이후 작업 (미구현, 계획)

1. 64-case clean benchmark: Phase A~C에서 후보가 나오지 않아 보류.
2. 드럼 hybrid(Phase E 또는 외부 후보): 라이선스 근거 확보가 선행.
3. lead/backing GT 도구, 실제곡 청취, QC Inspector, Restoration R1~R3, 저장소 최적화: 각각 `STEM_CONTINUITY_QC_KO.md`, `STEM_RESTORATION_EVALUATION_KO.md`, `OUTPUT_RESOURCE_AUDIT_KO.md` 참조. 구현 상태는 해당 문서에 따로 적었다.
