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
| 03 | 6-stem (6 head / query / hierarchical) | 2-stem 동작 이후 | |
| 04 | Data Factory (작곡, 악기, SFZ/SF2, FX, 6열 라이선스) | 필요 시점 | DATA_FACTORY_ARCHITECTURE, LICENSE_MATRIX §2 |
| 05 | Dataset GREEN/YELLOW/RED | 필요 시점 | DATASET_PROVENANCE |

## Phase 상태

| Phase | 내용 | 상태 |
|---|---|---|
| 0 | Repository audit, benchmark freeze | 완료 (`LEGACY_BASELINE.md`) |
| 1 | 아키텍처·라이선스 | Packet 01 반영 완료. 남은 NEEDS_RESEARCH는 매트릭스 참조 |
| 2 | Engine foundation (config, registry, checkpoint/provenance, trainer, 테스트) | 완료 (`TRAINING_SYSTEM.md`) |
| 3 | OUR MODEL v0.1 구현 + profiling + synthetic overfit | 완료 (분리 품질 미측정) |
| 4~7 | Data Factory v0 (Packet 04), 2-stem 최적화/ablation, 6-stem, 13+ | 후속. 실제 분리 데이터가 먼저 필요 |

## 확정 제약
- Dev GPU RTX 3060 12 GiB, 학습 1장 동작, AMP 필수, 수 M~수십 M params, chunk 3~8 s.
- 2-stem 출력 방식은 미확정 (ARCHITECTURE_COMPARISON §3.1).
