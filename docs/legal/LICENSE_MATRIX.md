# License Matrix

규칙: 각 구성요소는 아래 열을 **따로** 판정한다. 한 열의 값이 다른 열로 번지지 않는다.
값: `MIT`/`BSD-*`/`Apache-2.0`/`CC0` 등 SPDX, `UNKNOWN`(확인했으나 명시 없음), `NEEDS_RESEARCH`(아직 외부 조사 안 함), `N/A`.
외부 근거는 Research Packet이 전달한 것만 적는다. 근거 없는 셀은 `NEEDS_RESEARCH`로 둔다.

Lineage 판정: `OK`(OUR MODEL lineage 사용 가능) / `REFERENCE_ONLY`(아키텍처 연구만) / `EXCLUDED`.

## 1. 분리 모델

| 구성요소 | CODE | WEIGHT | TRAINING DATA | 근거 | Lineage 판정 |
|---|---|---|---|---|---|
| KJ MelBandRoformer | MIT (MSST repo 84b1eac) | MIT (2026-04-22 GPL-3.0→MIT 변경 기록, 원 저자) | UNKNOWN | Research Packet(사용자 전달), HF commit ac9b061 | 실험/fine-tuning/reference OK. 최종 OUR MODEL의 clean lineage에는 포함하지 않음 |
| ZFTurbo Mega53 (53-stem) 및 파생(core4, mega4-7, vocal2) | MIT | MIT (저자 답변, MSST issue #245, 2026-09) | UNKNOWN — 저자가 모든 학습 오디오의 저작권을 보유하지 않는다고 명시 | issue #245 | 실험/benchmark만. clean lineage 제외 |
| Demucs / HTDemucs 코드 | MIT | 별도. 상업 배포 권리 미확인 (issue #327) | NEEDS_RESEARCH | Research Packet | 코드: REFERENCE_ONLY. 가중치: EXCLUDED |
| Banquet / query-bandit | MIT | UNKNOWN (`WEIGHT_LICENSE_UNKNOWN`; Zenodo 13694558에 명시 license 없음. NC로 확정된 것은 아님) | NEEDS_RESEARCH | Research Packet | 코드: REFERENCE_ONLY. 공식 weight: EXCLUDED |
| SCNet | MIT | UNKNOWN (issue #35 문의에 공식 답변 없음) | MUSDB (README 명시). 데이터 라이선스는 DATASET_PROVENANCE 참조 | Research Packet | 코드: REFERENCE_ONLY. 공식 weight: EXCLUDED |
| BS-RoFormer (논문/lucidrains 구현) | NEEDS_RESEARCH | NEEDS_RESEARCH | NEEDS_RESEARCH | | NEEDS_RESEARCH |
| Mel-Band RoFormer (논문/구현) | NEEDS_RESEARCH | NEEDS_RESEARCH | NEEDS_RESEARCH | | NEEDS_RESEARCH |
| MSST (ZFTurbo) 코드 | MIT (LICENSE sha256 `3282dc05…0207`, 레거시 vendor에 보존) | N/A | N/A | 레거시 `vendor/msst/PROVENANCE.json` | REFERENCE_ONLY(clean-room 재구현 대상) |
| Open-Unmix | NEEDS_RESEARCH | NEEDS_RESEARCH | NEEDS_RESEARCH | | NEEDS_RESEARCH |
| BandIt | NEEDS_RESEARCH | NEEDS_RESEARCH | NEEDS_RESEARCH | | NEEDS_RESEARCH |
| bs_roformer_6s, karaoke 계열 (becruily/frazer) | NEEDS_RESEARCH | UNKNOWN | UNKNOWN | 레거시 registry | EXCLUDED |
| CLAPSep / LAION-CLAP | NEEDS_RESEARCH | UNKNOWN | UNKNOWN | 레거시 registry | EXCLUDED |

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
