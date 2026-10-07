# Stem Continuity / Cross-Stem Leakage QC (설계, 미구현)

내부 QC(benchmark·regression·운영 진단). 사용자 UI에는 노출하지 않는다. **아직 코드가 없다.**

## 입력
RAW 단계의 모든 stem(합계 보존 상태), 원곡 mix, 단계별 중간 stem(모델 원출력, routing 후, restoration 후), 청크/세그먼트 경계 목록(`segment_sec`, `overlap`, stride에서 계산).

## 지표 (100 ms / 250 ms / 500 ms / 1 s 윈도우)
RMS, short-term loudness, peak, spectral energy, spectral flux, harmonicity, pitch/harmonic continuity.

## 급감(Unexpected drop) 탐지와 원인 분류
직전 윈도우 대비 임계(예: −8 dB) 이상 감소한 구간을 후보로 잡고 다음으로 분류한다.

| 코드 | 판정 조건 |
|---|---|
| A REAL_DYNAMICS | 원곡 mix에서 해당 악기 evidence(다른 head/보조 증거)도 같이 감소 |
| B CROSS_STEM_LEAKAGE | 이 stem ↓ 와 동시에 다른 stem ↑, 두 구간의 STFT/하모닉 패턴 상관이 높음 |
| C MODEL_DROPOUT | 원곡에는 evidence가 있으나 어느 stem에서도 찾지 못함 |
| D ROUTING_ATTENUATION | 모델 raw에는 있으나 routing 이후 감소 |
| E RESTORATION_ATTENUATION | RAW에는 있으나 FINAL(restoration)에서 감소 |
| F CHUNK_BOUNDARY | 급감 시점이 세그먼트 경계와 일치 |
| G UNKNOWN | 위에 해당 없음 |

## Cross-stem energy transfer
RAW는 합계 보존이므로 한 stem에서 사라진 에너지는 다른 stem의 증가분으로 보존된다는 성질을 이용한다. 급감 구간에서 모든 다른 stem의 증가분을 구하고, 에너지 변화만이 아니라 STFT 유사도, 스펙트럼 상관, 하모닉 유사도, 피치 연속성을 함께 비교한다. 예: guitar −8 dB, other +7 dB, 스펙트럼 상관 0.9+ → guitar→other 누출 의심(신뢰도 포함).

## 보고서 스키마 (예)
```json
{"guitar": {"suspicious_drops": 2,
  "cross_stem_candidates": [{"time": 42.2, "target": "other", "confidence": 0.87}]}}
```

## 검증 계획
합성 GT(GeneralUser GS)에서 의도적으로 한 stem의 구간을 다른 stem으로 옮긴 케이스(주입 시험)로 분류 정확도를 먼저 측정한다. 실제곡은 청취 확인이 있어야만 "정답"으로 인정한다. 임계값은 주입 시험 결과로 정하고 현재는 미정.

## 선행 조건
Separation 베이스라인 확정(commercial_6 결정) 이후 구현. Restoration과 섞지 않는다.
