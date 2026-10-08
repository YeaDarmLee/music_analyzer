# License Matrix

규칙: 각 구성요소는 아래 열을 **따로** 판정한다. 한 열의 값이 다른 열로 번지지 않는다.
값: `MIT`/`BSD-*`/`Apache-2.0`/`CC0` 등 SPDX, `UNKNOWN`(확인했으나 명시 없음), `NEEDS_RESEARCH`(아직 외부 조사 안 함), `N/A`.
외부 근거는 Research Packet이 전달한 것만 적는다. 근거 없는 셀은 `NEEDS_RESEARCH`로 둔다.

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

## 2. Data Factory 구성요소 (Research Packet 04 대기)

각 항목은 CODE / ASSET / SAMPLE / PRESET / GENERATED AUDIO RIGHTS / TRAINING RIGHTS 여섯 열로 쪼갠다.

| 구성요소 | CODE | ASSET | SAMPLE | PRESET | GENERATED AUDIO | TRAINING | 판정 |
|---|---|---|---|---|---|---|---|
| FluidSynth | NEEDS_RESEARCH | N/A | N/A | N/A | NEEDS_RESEARCH | NEEDS_RESEARCH | NEEDS_RESEARCH |
| GeneralUser GS (SF2) | N/A | NEEDS_RESEARCH | NEEDS_RESEARCH | N/A | NEEDS_RESEARCH | NEEDS_RESEARCH | NEEDS_RESEARCH. 레거시 `DATASET_LICENSES_COMMERCIAL_KO.md`는 소유자 제공 요약만 근거 |
| sfizz | NEEDS_RESEARCH | N/A | N/A | N/A | N/A | N/A | NEEDS_RESEARCH |
| Surge XT / Dexed / OB-Xf | NEEDS_RESEARCH | | | | | | NEEDS_RESEARCH (GPL 계열은 프로세스 분리 여부 포함) |
| FreePats Timpani | N/A | CC0 1.0 (레거시 LICENSE.txt) | CC0 1.0 | N/A | NEEDS_RESEARCH | NEEDS_RESEARCH | 부분 확인 |
| 자체 DSP synth (신규 구현) | 자체 | 없음 | 없음 | 자체 생성 | 자체 | 자체 | OK (구현 후 기록) |

## 3. 의존성 (Python 패키지)

정확한 버전·라이선스는 의존성이 확정되는 Phase 2 이후 `pip-licenses` 출력으로 채운다. 현재 후보: torch, numpy, soundfile, einops, PyYAML, pytest. 라이선스 값은 `NEEDS_RESEARCH`.
