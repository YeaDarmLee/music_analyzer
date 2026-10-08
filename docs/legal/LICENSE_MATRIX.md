# License Matrix

규칙: 각 구성요소는 아래 열을 **따로** 판정한다. 한 열의 값이 다른 열로 번지지 않는다.
값: `MIT`/`BSD-*`/`Apache-2.0`/`CC0` 등 SPDX, `UNKNOWN`(확인했으나 명시 없음), `NEEDS_RESEARCH`(아직 외부 조사 안 함), `N/A`.
외부 근거는 Research Packet이 전달한 것만 적는다 (Packet 04/05 표기 [P45]; GitHub/Zenodo 메타데이터 확인은 2026-10-08 에이전트가 직접 조회). 근거 없는 셀은 `NEEDS_RESEARCH`로 둔다.

Lineage 판정: `OK`(OUR MODEL lineage 사용 가능) / `REFERENCE_ONLY`(아키텍처 연구만) / `EXCLUDED`.

## 1. 분리 모델

출처 약어: **[P01]** = Research Packet 01 v1 (사용자 전달, 2026-10-08; 개별 URL은 Packet에 없음 → `NEEDS_URL`). **[PHASE0]** = 레거시 설정/해시를 이 repo에서 직접 확인. **[#245]**, **[#327]**, **[#35]** = 각각 MSST issue 245, Demucs issue 327, SCNet issue 35 (이전 Research Packet/레거시 기록 기준). 확인일 2026-10-08. 근거 없는 칸은 `NEEDS_RESEARCH`, 불명확은 `UNKNOWN`. 추론으로 채우지 않는다.

| 구성요소 | CODE | WEIGHT | TRAINING DATA | 근거 | Lineage 판정 |
|---|---|---|---|---|---|
| KJ MelBandRoformer | MIT (MSST 84b1eac) [PHASE0] | MIT. 2026-04-22 GPL-3.0→MIT 변경 기록, 파일 SHA-256 `87201f4d…c7559e`가 HF 값과 일치 [P01] | UNKNOWN | [P01], HF commit ac9b061 | experiment/fine-tuning/benchmark/teacher/reference OK. 최종 clean OUR MODEL lineage 제외 |
| ZFTurbo Mega53 및 파생(core4, mega4-7, vocal2) | MIT | MIT (저자 답변 [#245], 2026-09) | UNKNOWN — 저자가 모든 학습 오디오의 저작권을 보유하지 않는다고 명시 | [#245] | experiment/benchmark만. clean lineage 제외 |
| BS-RoFormer | MIT (lucidrains 구현) [P01] | 별도 확인 필요 [P01] → UNKNOWN | 논문: MUSDB18HQ + 추가곡 [P01]. 데이터 라이선스는 DATASET_PROVENANCE | [P01] | 코드/논문 REFERENCE_ONLY. 구현은 자체(clean-room) |
| Mel-RoFormer | permissive 구현 존재 [P01] (정확한 SPDX NEEDS_RESEARCH) | checkpoint별 별도 [P01] → UNKNOWN | 논문: MUSDB18HQ [P01] | [P01] | REFERENCE_ONLY |
| SCNet | MIT [P01] | UNKNOWN (issue [#35]에 공식 답변 없음) | MUSDB 계열 [P01] | [P01] | 코드/논문 REFERENCE_ONLY. 공식 weight EXCLUDED |
| Demucs / HTDemucs | MIT [P01] | 상업 권리 미확인 [#327] → 제외 | MUSDB + 추가 [P01] (라이선스 NEEDS_RESEARCH) | [P01] | 코드/아이디어 REFERENCE_ONLY. weight EXCLUDED |
| BandIt | Apache-2.0 [P01] | 별도 [P01] → UNKNOWN | DnR/MUSDB 등 [P01] | [P01] | 코드/논문 REFERENCE_ONLY |
| Banquet / query-bandit | MIT [P01] | UNKNOWN (`WEIGHT_LICENSE_UNKNOWN`; Zenodo 13694558에 명시 license 없음. 비상업으로 확정된 것 아님) | MoisesDB [P01] (라이선스 NEEDS_RESEARCH) | [P01] | 코드 REFERENCE_ONLY. 공식 weight EXCLUDED |
| Open-Unmix | MIT [P01] | umxl: CC BY-NC-SA 4.0 (README) → RED. 그 외 모델은 "일부 제한" [P01]; 모델별 값 NEEDS_RESEARCH | MUSDB/private [P01] | [P01] | 코드 reference. umxl EXCLUDED |
| BSMamba2 | MIT [P01] | 별도, license 불명 (제3자 감사 프로젝트도 NOASSERTION) [P01] → UNKNOWN | MUSDB18-HQ [P01] | [P01] | 코드/논문 REFERENCE_ONLY 실험 후보. weight EXCLUDED |
| TS-BSmamba2 | Apache-2.0 [P01] | 별도 확인 [P01] → NEEDS_RESEARCH | NEEDS_RESEARCH | [P01] | 연구 후보 (코드/논문만) |
| MuS3D (2026-09) | NEEDS_RESEARCH ("실사용 라이선스 검증 필요" [P01]) | NEEDS_RESEARCH | NEEDS_RESEARCH | [P01] | 장기 13+ 연구. 현재 사용 불가 |
| MSST (ZFTurbo) 코드 | MIT (LICENSE sha256 `3282dc05…0207`) [PHASE0] | N/A | N/A | 레거시 `vendor/msst/PROVENANCE.json` | REFERENCE_ONLY. 직접 재사용 시 source/file/license/modification 기록 |
| bs_roformer_6s, karaoke 계열 | NEEDS_RESEARCH | UNKNOWN | UNKNOWN | 레거시 registry | EXCLUDED |
| CLAPSep / LAION-CLAP | NEEDS_RESEARCH | UNKNOWN | UNKNOWN | 레거시 registry | EXCLUDED |

### 1.1 OUR MODEL 제외 목록 (Packet 01 지시, 2026-10-08)
Demucs pretrained, Open-Unmix UMXL pretrained, Banquet pretrained, SCNet pretrained, BSMamba2 pretrained. 해당 코드/논문은 Architecture Research 용도로만 쓴다. KJ checkpoint는 MIT지만 학습 데이터 provenance UNKNOWN이므로 experiment/reference만 가능하다.

## 2. Data Factory 구성요소 (Research Packet 04/05 **[P45]**, 2026-10-08)

7열 판정: Code / Asset / Sample / Preset / Generated Audio / AI Training / 판정. commercial use와 AI training은 별도 조사 항목이다. 판정: GREEN, GREEN_CONDITIONAL(의무 기록 필요), YELLOW(연구/benchmark만), RED/UNKNOWN(사용 금지).
URL은 Packet Source Map 그대로. `—` = 해당 없음.

### 2.1 소프트웨어

| 구성요소 (URL) | Code | Asset/Sample/Preset | Generated Audio | AI Training | 판정 / v0 사용 |
|---|---|---|---|---|---|
| NumPy (https://github.com/numpy/numpy) | BSD-3-Clause | — | — | — | GREEN, **사용** |
| SciPy (https://github.com/scipy/scipy) | BSD-3-Clause | — | — | — | GREEN, **사용** (WAV I/O, filter, FFT conv, resample) |
| PyTorch | 기존 Engine 의존성 (Packet은 라이선스 값을 주지 않음) | — | — | — | NEEDS_RESEARCH (SPDX 확인) |
| Mido (https://github.com/mido/mido) | MIT | — | — | — | GREEN, 미사용 (debug MIDI export 후보) |
| pretty_midi (https://github.com/craffel/pretty-midi) | MIT | 연계 SoundFont/FluidSynth 경로는 코드 라이선스와 별개 | — | — | GREEN optional, 미사용 |
| music21 (https://github.com/cuthbertLab/music21) | BSD-3-Clause | 번들 corpus는 곡별 별도 권리 → 자동 사용 금지 | — | — | 코드 GREEN, **corpus 자동 사용 금지**, 미사용 |
| MusPy (https://github.com/salu133445/muspy) | MIT | 접근 symbolic dataset은 각각 별도 | — | — | 코드 GREEN, 미사용 |
| librosa (https://github.com/librosa/librosa) | ISC | — | — | — | GREEN, v0 미채택 |
| audiomentations (https://github.com/iver56/audiomentations) | MIT | — | — | — | GREEN optional, 미사용 |
| torch-audiomentations (https://github.com/iver56/torch-audiomentations) | MIT | — | — | — | GREEN optional, 미사용 |
| Spotify Pedalboard (https://github.com/spotify/pedalboard) | GPL-3.0 | — | — | — | **RED for Core** (permissive-only 정책) |
| FluidSynth (https://github.com/FluidSynth/fluidsynth) | LGPL-2.1-or-later | SoundFont 권리는 별개 | — | — | YELLOW, v0 제외 |
| sfizz (https://github.com/sfztools/sfizz) | BSD-2-Clause (2026-06-21 archived) | — | — | — | 코드 GREEN, runtime 제외, SFZ 동작 참고만 |
| Surge XT (https://github.com/surge-synthesizer/surge) | GPL-3.0-or-later | — | — | — | RED for Core |
| Dexed (https://github.com/asb2m10/dexed) | GPL-3.0 (내부 `msfa` FM 엔진 일부 Apache-2.0) | — | — | — | RED for Core |
| OB-Xf (https://github.com/surge-synthesizer/OB-Xf) | GPL-3.0 | — | — | — | RED for Core |
| OUR sampler / DSP synth / FX / composition (`src/data_factory`) | project-owned | 없음 (자체 생성) | project-owned | project-owned | GREEN (asset id `project-procedural-dsp`) |

### 2.2 Asset / Sample

| 구성요소 (URL) | Code | Asset | Sample | Preset | Generated Audio | AI Training | 판정 |
|---|---|---|---|---|---|---|---|
| VCSL (https://github.com/sgossner/VCSL, https://versilian-studios.com/vcsl/) | CC0 (포함된 스크립트) | CC0 | CC0 | SFZ는 CC0 범위 확인 후 사용 [P45] | unrestricted [P45] | 금지 조건 없음 [P45]; publisher: generative music/sampler 포함 | **GREEN** (GitHub API license 필드 CC0-1.0, 2026-10-08 직접 조회) |
| VCSL Keys (https://versilian-studios.com/vcsl-keys/) | — | CC0 | CC0 | SFZ | unrestricted | 금지 조건 없음 [P45] | **GREEN**, Piano 1순위. **다운로드 위치/구조: NEEDS_RESEARCH** (VCSL repo 안인지 별도 배포인지 Packet에 없음) |
| VSCO 2 CE (https://github.com/sgossner/VSCO-2-CE, https://versilian-studios.com/vsco-community/) | — | CC0 | CC0 | — | unrestricted | 금지 조건 없음 | **GREEN** (GitHub CC0-1.0 조회). strings/brass 등 후속 stem |
| Karoryfer Big Little Bass (https://github.com/sfzinstruments/karoryfer.big-little-bass) | — | CC0-1.0 | CC0-1.0 | — | README: royalty-free commercial/non-commercial | 금지 조건 없음 | **GREEN** (GitHub CC0-1.0 조회) |
| Karoryfer Sneakybass (https://github.com/sfzinstruments/karoryfer.sneakybass) | — | CC0-1.0 | CC0-1.0 | — | unrestricted | 금지 조건 없음 | **GREEN** (GitHub CC0-1.0 조회) |
| Stargate Sample Pack (https://github.com/stargatedaw/stargate-sample-pack) | — | public-domain/unrestricted 의도 [P45] | 동일 | — | unrestricted | 금지 조건 없음 [P45] | GREEN candidate. **GitHub license 필드는 NOASSERTION** → ingest 시 repo `LICENSE` 원문과 SPDX 확인 필요 (NEEDS_RESEARCH). 확인 전 production 금지 |
| VocalSet (https://doi.org/10.5281/zenodo.1203819) | — | CC BY 4.0 (Zenodo record license 필드 `cc-by-4.0`, version 1.1, 2026-10-08 조회) | 동일 | — | attribution 의무 | 금지 조건 없음 [P45] | **GREEN_CONDITIONAL** (attribution_required). excerpts 제외(프로젝트 정책). 인용문 정확한 형식: NEEDS_RESEARCH |
| Common Voice (https://commonvoice.mozilla.org/oc/terms) | — | CC0 기여분 [P45] | — | — | — | 음성(발화) 데이터, 노래 아님 | v0 미사용 |
| Freesound CC0 (https://freesound.org/help/faq/) | — | uploader 권리 검증 불가 | — | — | — | — | **YELLOW** (수동 allowlist만) |
| MUSDB18 / MUSDB18-HQ (https://zenodo.org/records/3338373) | — | educational only, 상업 금지, MedleyDB 등 NC 포함 | — | — | — | — | **RED** |
| MedleyDB | — | non-commercial (subset별) | — | — | — | — | **RED** (URL: NEEDS_RESEARCH) |
| MoisesDB (https://github.com/moises-ai/moises-db) | — | CC BY-NC-SA 4.0 | — | — | — | — | **RED** |
| Mixing Secrets (https://www.cambridge-mt.com/ms3/mtk/ , FAQ https://cambridge-mt.com/ms3/mtk-faq/) | — | educational only; AI engine training은 기여자별 별도 라이선스 필요 | — | — | — | — | **RED** |
| MDB-stem-synth | — | CC BY-NC 4.0 | — | — | — | — | **RED** (URL: NEEDS_RESEARCH) |
| Slakh2100 (https://github.com/ethman/Slakh) | — | CC BY 4.0 | — | — | — | upstream MIDI 권리 불확실 | **YELLOW** |
| Lakh MIDI (https://colinraffel.com/projects/lmd/) | — | CC BY 4.0, 곡별 저자 attribution 불가 (maintainer) | — | — | — | — | **YELLOW** |
| DnR v3 | Apache-2.0 | CC BY-SA 4.0 (ShareAlike) | — | — | — | — | **YELLOW** (URL: NEEDS_RESEARCH) |

커밋된 판정 데이터: `configs/data_factory/asset_catalog.json`. ingest 후 레코드: `artifacts/assets/<id>.json`, 라이선스 원문 스냅샷: `artifacts/licenses/<id>/LICENSE.txt`.

## 3. 의존성 (Python 패키지)

정확한 버전·라이선스는 의존성이 확정되는 Phase 2 이후 `pip-licenses` 출력으로 채운다. 현재 후보: torch, numpy, soundfile, einops, PyYAML, pytest. 라이선스 값은 `NEEDS_RESEARCH`.
