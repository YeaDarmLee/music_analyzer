# Engine Rebuild Roadmap

## 역할 분담 (2026-10-08 확정)

| 담당 | 책임 |
|---|---|
| 사용자 + 외부 Research Lead | 웹/논문/Repo/HF/Zenodo 검증, 라이선스 판정, Architecture 후보 비교, Data Factory 기술 조사 → **Research Packet** 작성 |
| Claude (Implementation Lead) | Git repo 분석, Packet을 실제 코드와 대조, 문서 반영, 구현, 학습·추론 실행, benchmark, 테스트, commit |

규칙: Claude는 광범위한 웹 검색을 하지 않는다. 외부 정보가 필요한데 Packet에 없으면 추론하지 않고 `NEEDS_RESEARCH`로 표시한다. 브랜치 `engine/rebuild`는 엔진 연구 전용(웹서비스 코드 없음). Legacy는 태그 `legacy-baseline-2026-10-08`.

## Research Packet 일정

| # | 주제 | 상태 | 반영 문서 |
|---|---|---|---|
| 01 | Separation Architecture + License (KJ, Mel/BS-RoFormer, SCNet, Demucs, BandIt, Banquet, Open-Unmix, BSMamba2, TS-BSmamba2, MuS3D) | v1 수령·반영 완료 (개별 URL 미수령: NEEDS_URL) | ARCHITECTURE_COMPARISON, LICENSE_MATRIX |
| 02 | OUR v0.1 Architecture (3060 12GB 기준 n_fft/hop/band/dim/depth/chunk/batch/accum/AMP/loss/optimizer) | 수령·구현 완료 (`OUR_SEPARATOR_ARCHITECTURE.md`) | OUR_SEPARATOR_ARCHITECTURE |
| 03 | 6-stem. 비교 대상: stem별 output projection / factorized projection / shared projection + stem embedding / lightweight shared decoder / query-conditioned decoder / hierarchical decoder (output projection 36.9% 병목 때문) | 실제 데이터 baseline 이후 | OUR_SEPARATOR_ARCHITECTURE §10.1 |
| 04+05 (통합) | Commercial-Clean Data Factory & Dataset. 7열 판정(Code/Asset/Sample/Preset/Generated Audio/AI Training/판정; commercial use와 AI training은 별도 조사), GREEN/YELLOW/RED/UNKNOWN(UNKNOWN은 사용 금지). Data Factory v0 대상: Drums, Bass, Piano, Synth(자체 DSP 우선) → 이후 Electric/Acoustic Guitar, Strings, Brass | 수령·구현 완료 (DF-1~DF-7, `DATA_FACTORY_ARCHITECTURE.md`). DF-0 실제 asset 다운로드는 사용자 승인 대기 | DATA_FACTORY_ARCHITECTURE, LICENSE_MATRIX §2, DATASET_PROVENANCE |

## Phase 상태

| Phase | 내용 | 상태 |
|---|---|---|
| 0 | Repository audit, benchmark freeze | 완료 (`LEGACY_BASELINE.md`) |
| 1 | 아키텍처·라이선스 | Packet 01 반영 완료. 남은 NEEDS_RESEARCH는 매트릭스 참조 |
| 2 | Engine foundation (config, registry, checkpoint/provenance, trainer, 테스트) | 완료 (`TRAINING_SYSTEM.md`) |
| 3 | OUR MODEL v0.1 구현 + profiling + synthetic overfit | 완료·승인. v0.1 아키텍처 개발 일시 정지 (실제 데이터 전까지 개선 판단 불가) |
| 4 | Data Factory v0 | DF-0~7 완료: 실제 asset ingest, 15-scene listening pack, 20-step 학습 smoke(CUDA). **정성 청취는 사람 확인 대기** |
| 5~7 | 생성 음원 청취 검증 → our_separator_v01 본학습 → 2-stem ablation → 6-stem(Packet 03) → 13+ | 후속 |

## 확정 제약
- Dev GPU RTX 3060 12 GiB, 학습 1장 동작, AMP 필수, 수 M~수십 M params, chunk 3~8 s.
- 2-stem 출력 방식은 미확정 (ARCHITECTURE_COMPARISON §3.1).
