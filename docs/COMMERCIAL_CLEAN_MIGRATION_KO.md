# Commercial-Clean Pipeline Migration (commercial_13)

법률 자문이 아니다. 모든 수치는 이 저장소에서 직접 실행한 결과다. GT가 없는 항목은 N/A로 표기했다.
기준선(`final_11`)과 기존 체크포인트, 기존 benchmark 산출물은 변경하지 않았다 (BASELINE: `COMMERCIAL_CLEAN_BASELINE_KO.md`).

## 1. Executive Summary

- `commercial_13`은 `final_11`과 같은 구조(원곡 mega7 증거 → 복원 → 리드/코러스 → 기본 4악기 → 기타/신디/현악/브라스 재분리 → 증거 기반 재배분 → 잔차 `other`)를 유지하면서 UNKNOWN 가중치 3종(`bs_6stem_fixed`, becruily karaoke, CLAPSep+LAION-CLAP)을 제거했다.
- 대체: 4악기 → Mega53 head 4개(`bs_roformer_core4`), 리드/코러스 → Mega53 `lead-vocal`/`back-vocal` head를 소유권 증거로 쓰는 합계 보존 분리(`vocal_split.py`), 심벌 이동 → core4 드럼 stem을 증거로 쓴 `commercial_cymbal.py`.
- 합성 GT 10 case(GeneralUser GS 렌더링) 기준 final_11 대비 stem SDR은 −2.3 ~ +0.4 dB. 합계 오차 최대 1.04e-7(허용 2e-6), NaN/Inf 0. 처리 시간은 10 case 평균 92 s(commercial_13 단독 재측정, 아래 15절 참조).
- **정정(stem 조립 버그)**: 이전 결과는 `guitar_residual`이 빠진 12 stem 상태에서 측정됐다(원인·수정은 17-1절). 그 측정은 무효 처리하고 13 stem으로 전부 재실행했다.
- **출시 후보 판정: 아직 아님** (17·19장). 가중치 라이선스는 프로젝트 소유자의 가정(Mega53 MIT 허락)에 의존하고, 라우팅 파라미터는 MedleyDB가 섞인 데이터로 튜닝된 값을 그대로 쓰고 있다.

## 2. 기존 License Blockers

| 구성요소 | 담당 | 상태 | commercial_13 |
|---|---|---|---|
| `bs_6stem_fixed.ckpt` | piano/guitar/bass/drums | weight UNKNOWN | 제거 → `bs_roformer_core4` |
| `bs_roformer_karaoke_frazer_becruily.ckpt` | lead/backing | weight UNKNOWN | 제거 → `bs_roformer_vocal2` |
| CLAPSep `best_model.ckpt` (+ LAION-CLAP) | piano 안 심벌 | checkpoint 상업 허락 불명 | 제거 → core4 드럼 증거 |
| MedleyDB 기반 튜닝 | RULES/STRENGTH 등 | CC BY-NC-SA 4.0 | 7장, 미해결 |

## 3. Replacement Candidates

- 4악기: A) Mega53 직접 4-head (채택). B) pruned 4-head는 A와 동일 가중치(head-pruning-only, strict load)라 별도 후보가 아니다. C) 다른 외부 모델은 license evidence가 없어 추가하지 않았다.
- 리드/코러스: A) Mega53 head 출력을 그대로 사용 — 레벨이 입력 대비 약 2배이고 합계가 보존되지 않아 탈락. B) head를 증거로만 쓰는 소유권 분리 — 채택. C) 보컬 단일 트랙(분리 없음) — 제품 옵션으로 보류.
- 심벌: 6개 후보 비교(6장).

## 4. BS 6stem Replacement

Mega53 공식 설정(`docs/model-research-round2/official-mega53.yaml`, `training.instruments`)에서 직접 읽은 head 번호: piano=33, guitar=20, bass=4, drums=15 (추측 없음). `scripts/prepare-commercial-heads.py`가 `official-53.ckpt`(SHA `c62820893bbf…3519f`)에서 head pruning만 수행해 `bs_roformer_core4`를 만든다. 파생 메타데이터(소스 SHA, selected_heads, transform, created_at, 라이선스 근거, 출력 SHA)는 `separation/configs/models/bs_roformer_core4.json`의 `derivation`에 있다. 기존 mega5/mega7은 건드리지 않았다.

모델 단위 비교: 합성 GT, 8 음색 × 4 stem × 레벨 {0, −6, −12, −18 dB, 부재} = 320 입력, 두 모델에 동일 입력 (`scripts/eval-commercial-core4.py`).

### SDR / SI-SDR / leak by stem and level (mean over timbres; dB)

| Stem | Level | SDR base | SDR core4 | Δ | SI-SDR base | SI-SDR core4 | Δ | Leak base | Leak core4 |
|---|---|---|---|---|---|---|---|---|---|
| piano | 0 dB | 9.64 | 8.54 | -1.10 | 9.15 | 7.88 | -1.27 | -19.50 | -17.69 |
| piano | -6 dB | 6.16 | 4.76 | -1.41 | 4.97 | 2.98 | -1.99 | -20.32 | -15.82 |
| piano | -12 dB | 3.06 | 2.00 | -1.06 | 0.09 | -2.42 | -2.51 | -21.36 | -12.99 |
| piano | -18 dB | 1.11 | 0.30 | -0.81 | -5.48 | -9.82 | -4.34 | -20.87 | -7.95 |
| guitar | 0 dB | 4.05 | 4.16 | 0.11 | 2.10 | 2.22 | 0.12 | -21.03 | -17.71 |
| guitar | -6 dB | 1.82 | 1.67 | -0.15 | -2.74 | -3.17 | -0.43 | -22.24 | -16.28 |
| guitar | -12 dB | 0.16 | 0.17 | 0.02 | -18.53 | -18.86 | -0.32 | -5.96 | 8.15 |
| guitar | -18 dB | 0.00 | -0.12 | -0.12 | -37.35 | -41.02 | -3.67 | 19.92 | 33.54 |
| bass | 0 dB | 12.30 | 11.55 | -0.75 | 12.17 | 11.34 | -0.83 | -27.93 | -25.63 |
| bass | -6 dB | 5.66 | 8.73 | 3.07 | 4.85 | 8.23 | 3.38 | -28.25 | -24.28 |
| bass | -12 dB | 1.21 | 5.50 | 4.29 | -17.10 | 4.25 | 21.35 | -5.39 | -23.26 |
| bass | -18 dB | 0.00 | 1.57 | 1.57 | -35.07 | -3.34 | 31.74 | 22.97 | -19.30 |
| drums | 0 dB | 15.42 | 13.36 | -2.06 | 15.30 | 13.17 | -2.14 | -30.70 | -29.03 |
| drums | -6 dB | 11.87 | 10.34 | -1.53 | 11.59 | 9.94 | -1.65 | -29.40 | -28.06 |
| drums | -12 dB | 8.64 | 6.79 | -1.85 | 8.04 | 5.77 | -2.27 | -28.34 | -26.04 |
| drums | -18 dB | 3.40 | 2.31 | -1.09 | 0.77 | -1.50 | -2.28 | -35.45 | -25.04 |

### Overall per stem (all levels)

| Stem | SDR base | SDR core4 | Δ | energy ratio base | energy ratio core4 |
|---|---|---|---|---|---|
| piano | 4.99 | 3.90 | -1.09 | -3.83 | -3.79 |
| guitar | 1.51 | 1.47 | -0.03 | -25.55 | -12.66 |
| bass | 4.79 | 6.84 | 2.04 | -28.81 | -3.66 |
| drums | 9.83 | 8.20 | -1.63 | -0.97 | -1.47 |

### Silence false positive (target absent; dB relative to mix, lower is better)

| Stem | base | core4 |
|---|---|---|
| piano | -84.2 | -49.1 |
| guitar | -83.5 | -46.8 |
| bass | -92.5 | -50.9 |
| drums | -90.9 | -55.0 |

### Residual (mix minus four stems; dB re full scale) and finiteness

- baseline_6s: mean residual -22.5 dB, all finite: True
- core4: mean residual -22.6 dB, all finite: True

### Runtime

- baseline_6s: 475.3 s for 2400 s audio (RTF 0.20), peak VRAM 1879 MiB
- core4: 453.1 s for 2400 s audio (RTF 0.19), peak VRAM 1646 MiB


해석: 베이스는 개선(+2.0 dB), 피아노 −1.1, 드럼 −1.6, 기타 동일. 목표 stem이 없는 곡에서의 오탐은 core4가 더 크다(믹스 대비 약 −50 dB, 기존 −85 dB). 실청취에서 문제가 되는지는 확인하지 못했다.

## 5. Karaoke Replacement

입력: 프로젝트 소유자의 Mureka AI 곡(권리 귀속 증명서 있음)의 보컬 stem 173 s. **깨끗한 보컬 GT가 없어 SDR/leakage는 N/A**이고, GT 없이 계산 가능한 값만 기록했다.

| 지표 | baseline karaoke | vocal2 (원출력) | vocal2 + 소유권 분리 |
|---|---|---|---|
| lead RMS (dB) | -21.6 | -15.7 | −21.5 |
| backing RMS (dB) | -41.1 | -47.4 | −48.6 |
| 합계 오차 vs 입력 | 0 (입력−lead) | 보존 안 됨(잔차가 입력과 −0.4 dB) | 5.96e-8 |
| baseline lead와 일치 SDR | - | 0.12 dB (레벨 불일치) | 21.0 dB |
| baseline backing과 일치 SDR | - | 2.33 dB | 1.6 dB |

- 레벨 문제: Mega53 head는 보컬 단독 입력에서 출력이 약 2배(최적 이득 0.51)다. 그래서 head를 증거로만 쓴다.
- 코러스 에너지는 baseline보다 약 7.5 dB 작다(조용한 하모니 보존이 약해질 가능성). 기준이 baseline이라 정확도 평가는 아니다. 청취 비교 파일: `data/commercial-eval/vocal_split/{baseline,commercial}/`.
- 제품 옵션 B(보컬 단일 트랙)는 분리 오차가 0이지만 리드/코러스 제어를 잃는다. 소유자의 청취 판단이 필요하다.
- 속도/VRAM은 baseline과 동일(RTF 0.12, 878 MiB).

## 6. CLAPSep Replacement

CLAPSep 제거. 증거 후보를 core4 추정과 같은 mix에서 비교했다(`scripts/eval-commercial-cymbal.py`, 12 case, GT stem 3종). 깨끗한 합성 데이터에서는 core4 피아노에 심벌 혼입이 거의 없어(−57 dB) 이동량이 0에 가까웠다. 그래서 GT 심벌을 피아노로 −12/−6 dB 섞은 가상 누출 시나리오를 추가했다(시험용 가정이며 실제 누출의 재현이 아니다).

| leak | approach | piano SDR | drums SDR | cymbal-in-piano (dB) | moved (dB) | max sum err |
|---|---|---|---|---|---|---|
| natural | C0_none | 15.54 | 22.14 | -56.8 | -240 | 3.7e-09 |
| natural | C1_dsp_only | 15.54 | 22.14 | -56.8 | -129 | 7.5e-09 |
| natural | C2_hh | 15.54 | 22.14 | -56.8 | -130 | 7.5e-09 |
| natural | C3_percussion | 15.54 | 22.14 | -56.8 | -149 | 7.5e-09 |
| natural | C4_drums | 15.54 | 22.14 | -56.8 | -128 | 7.5e-09 |
| natural | C5_hh_plus_percussion | 15.54 | 22.14 | -56.8 | -130 | 7.5e-09 |
| -12 dB | C0_none | 12.66 | 18.52 | -15.4 | -240 | 3.7e-09 |
| -12 dB | C1_dsp_only | 12.83 | 18.71 | -15.9 | -85 | 7.5e-09 |
| -12 dB | C2_hh | 12.77 | 18.65 | -15.8 | -82 | 7.5e-09 |
| -12 dB | C3_percussion | 12.66 | 18.52 | -15.4 | -136 | 7.0e-09 |
| -12 dB | C4_drums | 12.93 | 18.82 | -16.1 | -81 | 7.0e-09 |
| -12 dB | C5_hh_plus_percussion | 12.77 | 18.65 | -15.8 | -82 | 7.5e-09 |
| -6 dB | C0_none | 9.05 | 14.51 | -9.5 | -240 | 3.7e-09 |
| -6 dB | C1_dsp_only | 9.35 | 14.82 | -9.9 | -79 | 5.6e-09 |
| -6 dB | C2_hh | 9.20 | 14.67 | -9.8 | -76 | 5.6e-09 |
| -6 dB | C3_percussion | 9.05 | 14.51 | -9.5 | -141 | 5.6e-09 |
| -6 dB | C4_drums | 9.74 | 15.23 | -10.6 | -72 | 7.5e-09 |
| -6 dB | C5_hh_plus_percussion | 9.20 | 14.67 | -9.8 | -76 | 5.6e-09 |

- 모든 후보가 피아노를 해치지 않는다(자연 시나리오에서 변화 0). 개선 폭은 작다: 누출 −6 dB에서 최선(C4, 드럼 head 증거)이 피아노 SDR +0.7 dB.
- 채택: C4. 이미 계산된 core4 드럼 stem을 증거로 쓰므로 추가 모델 실행이 없다. 하모닉 보호, HPSS, 3–5 kHz 대역 게이트, 이동량만큼 drums에 가산(합계 보존)은 final_11 로직을 그대로 재사용했다.
- 한계: final_11의 CLAPSep 경로와의 직접 A/B는 실행하지 못했다. 합성 데이터에는 실제 심벌 누출이 거의 없어 후보 간 차이가 작다.

## 7. MedleyDB Provenance Cleanup

각 튜닝값의 근거 사례를 `data/ground-truth/cases/*/case.json`의 `reference_sources`로 추적했다.

| 값 | 근거 연구 세트 (구성) | 분류 |
|---|---|---|
| `context_routing.RULES` brass/guitar (v15) | stability-v15 24 case: MedleyDB 3, Philharmonia 12, Slakh 9, FreePats 3 + millsage(상업곡) 안정성 | **B** |
| `context_routing.RULES` synth `.3` (v16) | pad-eval 합성 64 case + Slakh20 | **C** |
| `string_routing.STRENGTH` (v13) | stability-v13(위와 동일 구성) + string-family-study(MedleyDB 3) | **B** |
| `instrumental_restoration` 지수 3/2 | rainfall(MedleyDB) 보컬 + 합성/실악기 제어 | **A/B** |
| 심벌 마스크 (`piano_drum_refinement`) | piano-cymbal/piano-drum study: MedleyDB 3 + millsage(상업곡) | **B** (commercial_13은 CLAP mask를 제거했지만 나머지 상수는 잔존) |
| `percussion_refinement` 지수 2, share×coherence² | Slakh + Philharmonia + FreePats + millsage | **B** (MedleyDB 직접 의존은 확인하지 못했으나 Philharmonia·상업곡 포함) |
| mega5/mega7 head 선택 | extended-head-study, string-family-study (MedleyDB 3 포함) | **B** |

commercial_13은 A/B 값을 **그대로 가져다 쓰고 있다.** 코드가 MedleyDB를 읽는 경로는 없지만 값의 출처가 오염돼 있으므로 "MedleyDB dependency = 0"이라고 주장하지 않는다. 깨끗한 데이터(합성 pad-eval 64, Slakh, FreePats)만으로 파라미터를 재튜닝하는 작업은 하지 않았다. 대신 같은 값이 깨끗한 합성 10 case에서 회귀를 만들지 않는지만 확인했다(10·11장).

## 8. Commercial Dataset Inventory

`DATASET_LICENSES_COMMERCIAL_KO.md` 참고. 사용: pad-eval 합성, 합성 piano+cymbal, FreePats Timpani(CC0), BabySlakh(CC BY 4.0, 작곡 권리 미확인이라 보조), Mureka AI 곡. 제외: MedleyDB, `song/*.mp3`, millsage, Philharmonia.

## 9. New Pipeline Architecture

```
canonical wav ─ vocal_roformer(melband_roformer_kj, APPROVED) ─ vocals / instrumental
original ─ instrument_mega7 (APPROVED) ─ 증거 7종 ─ instrumental_restoration (변경 없음)
vocals ─ vocal2_mega (bs_roformer_vocal2) ─ vocal_split(소유권 분리, 합계 보존) ─ lead / backing
instrumental ─ instrument_core4 (bs_roformer_core4) ─ piano / guitar / bass / drums
guitar ─ mega5 ─ acoustic / electric / guitar_residual ;  residual ─ mega5 ─ synth / strings / brass
piano ─ commercial_cymbal(core4 drums 증거) ─ drums
percussion / string / backing-percussion / context routing (변경 없음) ─ with_remaining(other) ─ validate_partition(2e-6)
```

- 코드: `commercial_pipeline.py`(단계→preset 매핑), `vocal_split.py`, `commercial_cymbal.py`, `commercial_eval.py`. `web_server.py`는 `is11`/`commercial` 분기만 추가했고 final_11 동작은 동일하다.
- preset: `separation/configs/presets/commercial.json`(별도 파일. `demucs.json`은 final_11 job의 provenance 해시 대상이라 미변경).
- **License Gate**: `separation/configs/commercial_approval.json`이 유일한 권위. `registry.commercial_gate()`가 (1) APPROVED가 아닌 모델(누락=UNKNOWN), (2) 체크포인트 SHA 불일치를 즉시 실패 처리한다. `Library.analyze`가 시작 전에, `worker.py`가 `profile: commercial` preset 로드 시 각각 검사한다. 기존 모델 JSON은 DEV_ONLY 그대로.

## 10. Stem-by-Stem Comparison (10 합성 case, SDR dB)

cases: 10

| Stem | final_11 SDR | commercial_13 SDR | Delta | n |
|---|---|---|---|---|
| lead | N/A | N/A | N/A | 0 |
| backing | N/A | N/A | N/A | 0 |
| piano | 9.30 | 8.11 | -1.19 | 10 |
| synth | 4.53 | 4.92 | 0.39 | 9 |
| strings | 8.26 | 6.79 | -1.47 | 8 |
| brass | 4.47 | 4.34 | -0.13 | 3 |
| acoustic_guitar | N/A | N/A | N/A | 0 |
| guitar | 4.03 | 3.73 | -0.30 | 4 |
| bass | 11.67 | 10.84 | -0.83 | 10 |
| drums | 15.48 | 13.20 | -2.28 | 10 |
| percussion | N/A | N/A | N/A | 0 |
| other | N/A | N/A | N/A | 0 |
| guitar_total | 4.05 | 3.77 | -0.28 | 4 |

| Partition (original vs sum of all stems) | value |
|---|---|
| max_abs_error (worst over cases) | 1.04e-07 |
| rms_error (worst over cases) | 5.7e-09 |
| samples_over_2e-6 (worst over cases) | 0 |
| nan (worst over cases) | 0 |
| inf (worst over cases) | 0 |
| clipping_samples (worst over cases) | 0 |
| dc_offset (worst over cases) | 0.00191 |
processing seconds (mean): 83.91550000000001


lead/backing/acoustic_guitar/percussion/other는 이 합성 세트에 정답이 없어 N/A. brass는 3 case, guitar는 4 case에서만 GT 레벨이 측정 가능했다.

## 11. Objective Benchmark

위 표가 객관 지표다. final_11 수치는 같은 case의 기존 v16 리포트, commercial_13은 이번에 새로 돌린 결과이며 둘 다 `ground_truth.evaluate`로 채점했다. 피아노 −1.19, 스트링 −1.47, 베이스 −0.83, 드럼 −2.28, 브라스 −0.13, 기타 −0.30, 신디 +0.39 dB.
`ground_truth.evaluate`는 이제 `stem_contract`(expected/actual/missing_required/unexpected)를 report.json에 기록하고, 하나라도 어긋나면 실패한다. 이전의 "있는 stem만" 완화는 제거했다(누락을 가렸다).

## 12. Synthetic Ground Truth Test

- 4악기 모델 단위: 8 음색 × {0, −6, −12, −18 dB} 1 stem 감쇠 + 부재 조건(4장).
- 심벌 후보: 6장.
- 하지 못한 것: synth+strings, guitar+brass, vocal+strings 등 전체 파이프라인 SNR 스윕(pad-eval 64 case 중 10 case만 실행). 보컬이 들어가는 케이스는 깨끗한 보컬 GT가 없어 만들지 못했다.

## 13. Listening Test

`data/commercial-eval/listening/case_00N_*/` (original.wav, baseline/, commercial/, comparison.json). 동일 샘플레이트·길이를 assert로 확인했고 gain은 정규화하지 않은 원 출력이다. 리드/코러스는 `data/commercial-eval/vocal_split/`. 청취 판정은 수행하지 않았다.

## 14. Partition Integrity

10 case 최악값: max abs error 1.04e-7, RMS 5.7e-9, 2e-6 초과 샘플 0, NaN 0, Inf 0, 클리핑 0, DC offset 최대 0.0019. 스모크에서도 9.6e-8 이하(16장 표). 실패 0건.

## 15. Runtime / VRAM

- 10 case 평균 92.4 s(commercial_13, 13 stem 재실행, 직전 측정 83.9 s와 다름 = 기기 부하 변동). final_11은 이번에 재실행하지 않았다. 이전 동일 세션 비교(109.1 s → 86.6 s, 4 case)는 12 stem 상태의 값이라 무효이며, 속도 개선 주장은 같은 세션에서 final_11과 다시 비교하기 전까지 보류한다.
- stage별 PyTorch 최대 할당: 6stem 1.66 GB → core4 1.02 GB, karaoke 0.92 GB → vocal2 0.92 GB. KJ 1.67 GB가 전체 최대이며 두 파이프라인이 같다. 전체 장치 피크와 CLAPSep venv 메모리는 측정하지 못했다.
- RTF: core4 0.20, 6stem 0.23 (job 매니페스트).

## 16. Regression Test Results

`separation/tests` 전체: **307 passed, 1 skipped, 0 failed** (프로젝트 `.venv` 인터프리터, commercial_2/6 테스트 포함). 앞서 보고한 `test_quality.py` 3 실패는 시스템 Python으로 실행해서 생긴 환경 문제였고 `.venv`에서는 발생하지 않는다. 증가분은 이번 작업의 신규 테스트 14개(`test_commercial_gate.py` 9, `test_commercial_modules.py` 5)와 다른 세션이 추가한 테스트다. 실패한 테스트를 삭제하거나 허용치를 바꾸지 않았다.

엣지 입력 스모크(commercial_13):

| case | state | seconds | stems (expected/actual) | missing | unexpected | max abs partition error |
|---|---|---|---|---|---|---|
| stereo44k_5s | SUCCEEDED | 68.7 | 13/13 | [] | [] | 9.53e-08 |
| mono48k_5s | SUCCEEDED | 66.6 | 13/13 | [] | [] | 8.23e-08 |
| short_0.5s | FAILED (Decoded duration must be between 1s and 15min) | 0.5 | - | - | - | - |
| silence_3s | SUCCEEDED | 55.1 | 13/13 | [] | [] | 0.00e+00 |
| long_90s | SUCCEEDED | 222.2 | 13/13 | [] | [] | 8.82e-08 |

44.1/48 kHz, 모노/스테레오, 무음, 90 s 장편은 통과. 0.5 s는 ingest가 1초 미만을 거부(final_11 동일). OOM 재시도 경로는 새로 검증하지 않았다(preset에 memory_safe fallback만 추가).

## 17. Remaining License Risks

1. Mega53 MIT 허락은 프로젝트 소유자의 가정(저장소 issue #245 선언)에 의존한다. 학습 데이터 권리는 모든 모델에서 UNKNOWN.
2. `melband_roformer_kj`는 HF README의 MIT 선언(PUBLISHER_DECLARED)만 근거다.
3. 라우팅 파라미터 provenance(7장): 코드는 NC 데이터를 읽지 않지만 값의 출처가 NC·상업곡을 포함한다.
4. 감사 문서가 지적한 FFmpeg GPL 빌드, LGPL 3종, Demucs 무조건 import는 이번 범위 밖이라 미해결.
5. `commercial_approval.json`은 기존 DEV_ONLY 모델 JSON과 분리돼 있어 두 곳을 같이 관리해야 한다.

## 18. Remaining Quality Risks

1. 모든 정량 평가는 합성음 기준이다. 실제 상업 음원 수준의 일반화는 검증하지 못했다.
2. 리드/코러스 품질은 정답 없이 baseline과의 일치만 봤고, 코러스 에너지가 약 7.5 dB 작다.
3. core4는 stem 부재 시 오탐이 더 크다.
4. 피아노/드럼/스트링 SDR이 1~2.3 dB 낮다.
5. 심벌 이동의 개선 폭이 작아 실제 곡에서의 효과는 미확인.
6. 프론트엔드에는 commercial_13 선택지가 없다(API `preset=commercial_13`로만 호출).

## 19. Final Recommendation

현 상태의 commercial_13은 **개발/검증용 상용 후보**다. 출시 전 필수: (a) Mega53 허락 근거의 법무 확인, (b) 깨끗한 데이터로 RULES/STRENGTH 재튜닝 또는 현재 값의 영향 평가, (c) 실제 권리 보유 음원으로 청취 검증과 코러스 품질 판단, (d) 감사 문서의 FFmpeg/LGPL 항목 정리. 합성 기준 품질 하락(−0.1 ~ −2.3 dB)은 실사용 불가 수준은 아니다.

## 17-1. Stem 조립 버그 (13 → 12) 및 재측정

- 증상: commercial_13 결과가 12 stem(`guitar_residual` 없음). 이전 스모크 표의 `stems=12`가 그 증거.
- 원인: `web_server.final_session()`이 버전 문자열 목록으로 `guitar_residual` 추가 여부를 정하는데 `commercial-13-v1`이 목록에 없었다. 평가기도 같은 방식으로 기대 개수를 12로 계산했고, `groups.pop('guitar_residual',None)` 완화가 누락을 가려서 통과했다.
- 수정: 목록에 `commercial-13-v1` 추가, 평가기에 stem 계약 검증(`stem_contract`) 추가·완화 제거.
- 재사용 검토: 중간 산출물에 `guitar-residual.wav`는 있었지만 이후 단계(`other` 재계산, 라우팅)가 이를 포함하지 않은 채 진행됐기 때문에 재조립이 안전하지 않다고 판단해 GPU로 전부 재실행했다.
- 이전 12 stem 결과는 `data/commercial-eval/pad-invalid-12stem`, `smoke-invalid-12stem`에 보존(invalidated). SDR 차이는 ≤0.01 dB, 합계 오차는 동일 범위였다.

## 17-2. commercial_2 / commercial_6

- `commercial_2` = KJ vocal (`vocal_roformer`) → vocals + instrumental. 모델 1개(`melband_roformer_kj`).
- `commercial_6` = KJ vocal + Mega53 core4 → vocals / piano / guitar / bass / drums / other(잔차). 모델 2개. `bs_roformer_6s`(UNKNOWN)는 실행되지 않는다(`instrument_roformer_6s` stage가 `instrument_core4`로 치환).
- 단계 목록은 `commercial_pipeline.PIPELINES`에 있고 `release.STAGE_RESOLVERS`가 이를 읽는다. 실행 전 `commercial_gate(models_for(preset))`가 APPROVED·SHA를 검사한다.
- `configs/release_presets.json`에는 둘 다 `VALIDATING`으로 등록(승인 전). 스모크(5 입력): 2/2, 6/6 stem 계약 일치, 합계 오차 ≤5.4e-8, 0.5초 입력은 의도대로 거부.
- 아직 안 한 것: 6트랙의 GT 품질 비교(basic_6 대비), UI 공개 preset ↔ runtime preset 매핑.

## 17-3. 6트랙 SDR 비교 (basic_6 vs commercial_6)

합성 GT 10 case(pad-eval, GeneralUser GS), 동일 입력·동일 채점(`ground_truth.score`). `other` 정답 = strings+brass+synth. vocals는 정답이 없어 N/A. 재현: `scripts/eval-six-track.py`, `scripts/summarize-six-track.py`, 원자료 `COMMERCIAL_CLEAN_SIX_RESULTS.json`.

| stem | basic_6 SDR | commercial_6 SDR | Delta | worst case delta | n |
|---|---|---|---|---|---|
| piano | 9.27 | 8.14 | -1.13 | -2.41 (pad01-mix) | 10 |
| guitar | 3.43 | 3.70 | +0.27 | -1.01 (pad03-mix) | 4 |
| bass | 11.97 | 10.96 | -1.01 | -2.55 (pad03-mix) | 10 |
| drums | 15.52 | 13.30 | -2.21 | -2.87 (pad06-mix) | 10 |
| other | 9.54 | 8.63 | -0.91 | -2.18 (pad05-mix) | 10 |

- 합계 오차 최대 5.96e-8(두 쪽 동일), 평균 처리 시간 26.5 s → 24.5 s (같은 세션 순차 실행, 단일 측정).
- 해석: 13트랙 결과와 같은 방향(드럼이 가장 큼). 합성 데이터이며 실제 곡·보컬 품질은 검증하지 못했다.

## 17-4. 6트랙 손실 원인 진단 (진단만, 튜닝·모델 변경 없음)

재현: `scripts/diagnose-six-track.py [1..5]`, 원자료 `COMMERCIAL_CLEAN_SIX_DIAGNOSIS.json`. 같은 10 case(합성 GT), raw SDR 기준.

**1) head-pruning 무결성 — 통과.** 공식 Mega53 53-head 체크포인트(SHA 일치)에서 head 33/20/4/15를 꺼낸 출력과 `bs_roformer_core4` 출력을 3개 입력, fp32·fp16 모두에서 비교했다. 4 stem 전부 **max abs error 0, RMS 0, correlation 1.0 (비트 단위 동일)**. 파생 checkpoint 문제(B)는 아니다.

**2) 어디서 잃는가 (commercial_6)**

| Stem | basic raw | core4 raw | commercial_6 final | Raw loss | Post loss | Main cause |
|---|---|---|---|---|---|---|
| piano | 9.27 | 8.14 | 8.14 | -1.13 | 0.00 | A. core4 모델 자체 |
| guitar | 3.43 | 3.70 | 3.70 | +0.27 | 0.00 | 손실 없음 (n=4) |
| bass | 11.97 | 10.96 | 10.96 | -1.01 | 0.00 | A |
| drums | 15.52 | 13.30 | 13.30 | -2.21 | 0.00 | A |
| other | 9.54 | 8.63 | 8.63 | -0.91 | 0.00 | C. 잔차(=입력−4 stem)가 A의 오차를 그대로 상속 |

- commercial_6에는 후처리 단계가 없다. final과 raw의 최대 차이는 6e-8(부동소수점 수준)이라 **후처리 손실은 0**이다.
- KJ 보컬 단계의 영향은 작고 두 파이프라인에 동일하다(깨끗한 믹스 입력 vs 실제 파이프라인 입력의 core4-basic 차이: piano -1.16/-1.13, bass -0.72/-1.01, drums -2.27/-2.21).
- 손실의 성격: core4는 basic보다 leak가 약간 크고(drums -29.0 vs -30.7 dB) 놓치는 target 에너지도 크다(drums missing -13.2 vs -15.5 dB). 한 방향 편향이 아니라 전반적으로 덜 깨끗하다.

**3) commercial_13 단계 추적 (SDR, 10 case 평균)**

| stem | raw core4 | 중간 단계 | final | 후처리 손실 |
|---|---|---|---|---|
| drums | 13.25 | cymbal 이동 13.25 → percussion routing 13.20 | 13.20 | -0.05 |
| piano | 8.11 | cymbal 이동 8.11 | 8.11 | 0.00 |
| bass | 10.84 | - | 10.84 | 0.00 |

13트랙의 drums -2.28 dB 중 core4 raw가 -2.2 dB, 후처리가 -0.05 dB다. RULES/STRENGTH/cymbal 이동은 현재 값에서 거의 영향을 주지 않으며 튜닝으로 회복할 여지가 작다.

**4) strings (-1.47 dB)와 other.** strings는 모델 교체가 아니라 **입력 잔차가 달라서** 생긴 손실이다. 같은 mega5를 서로 다른 잔차에 돌린 비교(8 case): oracle(GT로 4악기를 뺀 잔차) 12.57 → basic 잔차 8.84 → core4 잔차 7.42 (-1.42 dB, 최종 -1.47과 일치). core4가 strings 에너지 일부를 가져가 strings 출력 에너지가 -1.7 dB → -3.9 dB로 줄었다. 분류 E(복합): 원인은 A, 전달 경로는 C. strings 라우팅 단계의 손실은 0.

**5) 없는 악기 오탐 (모델 단위, 8 timbre, mix 대비 dB; 낮을수록 좋음).** commercial_6 final = raw이므로 그대로 final 값이다.

| 없는 악기 | basic | core4 |
|---|---|---|
| piano | -84.2 | -49.1 |
| guitar | -83.5 | -46.8 |
| bass | -92.5 | -50.9 |
| drums | -90.9 | -55.0 |

**결론**
- drums -2.21 dB는 전부 core4 모델 자체(A)다. piano -1.13, bass -1.01도 같다. other -0.91은 그 파생, strings -1.47은 잔차 경유 파생이다.
- core4는 공식 Mega53 head와 비트 단위로 동일하다. 즉 "상용 라이선스를 위해 Mega53 head로 바꿨더니 품질이 낮아졌다"는 말이 정확하다. 파생 과정 오류는 아니다.
- 6트랙에는 튜닝할 후처리가 없고 13트랙의 후처리 손실도 0.05 dB 이하라서 **RULES/STRENGTH 튜닝으로 복구할 수 있는 범위는 거의 없다**. 복구하려면 모델 단계 변경이 필요하다. 선택지: ① 손실 수용 ② 드럼만 별도 라이선스-클린 분리기 탐색 ③ Mega53 다른 head를 증거로 쓰는 재구성.
- 아직 확인하지 않은 값싼 레버: core4 추론 파라미터(overlap, segment 길이). 진단만 하라는 지시라 건드리지 않았다.
- 한계: 합성 데이터 10 case(기타는 4 case). 실제 곡에서는 다를 수 있다.
