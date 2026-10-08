# Legacy Baseline (Frozen)

- 기록일: 2026-10-08
- 기준: git tag `legacy-baseline-2026-10-08` → commit `992f058ad225a64dc28860b0530e87329b95e78b` (branch `main`)
- 이 브랜치(`engine/rebuild`)는 웹서비스·프론트엔드·분리 파이프라인 코드를 모두 제거했다. 기존 코드는 `git show legacy-baseline-2026-10-08:<path>` 또는 별도 worktree로 읽는다.
- 용도: 새 엔진(OUR MODEL)과 비교하는 **Legacy Benchmark**. 새 아키텍처는 이 구조에 제한받지 않는다.
- 이 문서의 수치는 태그 안의 문서/설정/체크포인트에서 직접 읽은 것이다. 새로 측정한 성능 수치는 없다.

## 1. 실행 환경 (측정 기준)

| 항목 | 값 |
|---|---|
| GPU | NVIDIA GeForce RTX 3060, 12 GiB (드라이버 560.94) |
| Host RAM | 약 64 GiB |
| Python / torch | 3.12.14 / 2.5.1+cu121 (루트 `.venv`) |
| OS | Windows 11 |
| 디스크 | C: 1.9 TB 중 약 948 GB 여유 |

**제약**: 학습 가능한 모델 크기와 배치는 12 GiB VRAM이 상한이다. Architecture 후보 평가 시 이 수치를 기준으로 삼는다.

## 2. 체크포인트 목록 (로컬 SHA-256 직접 계산)

위치: `data/separation/models/<model_id>/` (gitignore, 저장소 미포함)

| model_id | 파일 | SHA-256 | 용도 | 가중치 라이선스 | 학습 데이터 권리 |
|---|---|---|---|---|---|
| `melband_roformer_kj` | MelBandRoformer.ckpt | `87201f4d…c7559e` | **KJ** vocal/instrumental | MIT (publisher declared) | UNKNOWN |
| `bs_roformer_vocal2` | vocal2.ckpt | `fb4d0d09…8952f6` | Mega53 파생, vocal | MIT (issue #245 선언) | UNKNOWN |
| `bs_roformer_core4` | core4.ckpt | `24b900e2…9393ed` | Mega53 파생 head-pruning, piano/guitar/bass/drums | MIT (issue #245 선언) | UNKNOWN |
| `bs_roformer_mega4/5/6/7` | mega{4,5,6,7}.ckpt | mega4 `c9e36874…`, mega5 `8a73fb56…`, mega6 `d33b5a08…`, mega7 `46e2e801…` | Mega53 파생 head 묶음 | MIT (issue #245 선언) | UNKNOWN |
| `mega53_*` | official-53.ckpt `c6282089…`, 3head `9d97108e…`, 5head `05eb7b03…`, 5head_bowed `6c959b4d…` | | 53-stem 원본 및 head 실험본 | 위와 동일 | UNKNOWN |
| `bs_roformer_6s` | bs_6stem_fixed.ckpt | `24e7d35e…75916e` | 6 stem | **UNKNOWN** | UNKNOWN |
| `bs_karaoke` | bs_roformer_karaoke_frazer_becruily.ckpt | `eb90ee24…389f9` | lead/backing | **UNKNOWN** | UNKNOWN |
| `melband_karaoke` | mel_band_roformer_karaoke_becruily.ckpt | `d3aa262a…a0e0` | lead/backing | **UNKNOWN** | UNKNOWN |
| `demucs_htdemucs`, `_6s`, `_ft` | `.th` 6개 | 전체 해시는 `sha256sum`으로 재계산 | Demucs 비교 | 코드 MIT, 가중치 별도 권리 미확인 (issue #327) → OUR MODEL lineage 제외 | UNKNOWN |
| CLAPSep, LAION-CLAP | 별도 venv `data/separation/tools/clapsep-env` | | cymbal 질의 | UNKNOWN | UNKNOWN |

KJ 가중치는 2026-04-22 원 저자가 GPL-3.0에서 MIT로 변경한 기록이 외부 검증으로 확인됨(Research Packet). Mega53은 저자가 가중치를 MIT로 공개했으나 학습 오디오 전체의 저작권을 보유하지 않는다고 명시 → 가중치 라이선스와 학습 데이터 권리는 **별개 열**로 기록한다.

전체 해시 원문은 Phase 0 실행 로그(`sha256sum`)에서 얻었다. 새 레지스트리 구현 시 이 표를 `configs/legacy/checkpoints.json`으로 옮긴다.

## 3. Legacy 추론 파이프라인

### 3.1 코드 계층 (태그 기준 `separation/src/music_analyzer/`)

- `vendor/msst/` : ZFTurbo MSST commit `84b1eac0887756b4f1a9d7a1ff49105939749ed2`의 `bs_roformer.py`, `mel_band_roformer.py`, `attend.py` (MIT) 수정 복사본. 수정: 로컬 Attend import, torch 2.5 sdpa_kernel 호환을 위해 `set_priority` 제거. 해시는 태그 안 `PROVENANCE.json`.
- `roformer_runner.py` : chunk 단위 추론. `pipeline.py`, `commercial_pipeline.py` : 단계 오케스트레이션.
- `web_server.py` / `worker.py` / `job_service.py` / `auth.py` : 웹·큐·계정 (엔진과 무관, 이 브랜치에서 제거).

### 3.2 final_11 / commercial_13 단계 (`web_server.py: Library.analyze`)

1. KJ (8 s, overlap 0.4): vocals / instrumental
2. mega7 on 원곡: 7개 head 증거 (acoustic-guitar, electric-guitar, synth, bowed_strings, brass, percussion, timpani), 10 s
3. instrumental_restoration: vocals에 샌 strings/brass/synth를 instrumental로 복원
4. bs_karaoke (10 s): vocals → lead / backing
5. bs_roformer_6s (13.35 s): piano / guitar / bass / drums
6. residual1 = instrumental − (piano+guitar+bass+drums)
7. mega5 on guitar → acoustic/electric; mega5 on residual1 → synth / bowed_strings / brass
8. CLAPSep cymbal 질의 → piano_drum_refinement
9. percussion_refinement, string_routing, context_routing
10. `validate_partition` (stem 합 vs 원곡 최대 절대오차 ≤ 2e-6)

최종 13 stem: lead, backing, piano, synth, strings, brass, acoustic_guitar, guitar, bass, drums, other, guitar_residual, percussion.

### 3.3 Production preset (`release_presets.json`, 소유자 결정 APPROVED)

| preset | 단계 | 모델 수 |
|---|---|---|
| `commercial_2` | KJ | 1 |
| `commercial_6` | KJ → core4 (+ residual = rest) | 2 |
| `commercial_13` | KJ, mega7, mega5, core4, vocal2 | 5 |

core4 설정: segment 10 s, overlap 0.4, fp16, batch 1. OOM 시 segment 5 s `memory_safe`로 폴백.

## 4. 모델 하이퍼파라미터 (태그 안 upstream yaml)

| | KJ (MelBandRoformer) | core4 (BSRoformer, Mega53 4-head) |
|---|---|---|
| chunk | 352800 (8 s) | 441000 (10 s) |
| n_fft / hop | 2048 / 441 | 2048 / 512 |
| dim / depth | 384 / 6 | 256 / 12 |
| heads × dim_head | 8 × 64 | 8 × 64 |
| 밴드 | mel 60 | 고정 band 62개 (2×24, 4×12, 12×8, 24×8, 48×8, 128, 129) |
| stems | 1 (vocals; instrumental = mix − vocals) | 4 |
| time/freq transformer depth | 1 / 1 | 1 / 1 |
| mask estimator depth | 2 | (기본) |
| loss | multi-STFT (4096…256) w=1.0 | (upstream 기본) |
| 학습 설정 | lr 1e-5, Adam, AMP, batch 4 | - |

**핵심 관찰**: KJ의 "instrumental"은 `mix − vocals`이다. 따라서 보컬 잔향/잔여가 instrumental로 직접 전이되는 구조다. 새 모델의 2-stem 출력 방식(A: Inst = Mix − Vocal / B: 독립 head + mixture consistency / C: 독립 예측 후 Mix 투영)은 **미확정**이며 Research Packet 01/02 이후 실험으로 결정한다. 현재 기록은 `candidate = independent heads` 뿐이다.

## 5. 기존 측정 수치 (태그 안 `docs/COMMERCIAL_CLEAN_CORE4_SUMMARY.md`, 합성 GT 기준)

core4 vs baseline_6s, 합성 pad-eval 2400 s 오디오:

| 지표 | baseline 6s | core4 |
|---|---|---|
| RTF (RTX 3060) | 0.20 | 0.19 |
| 피크 VRAM | 1879 MiB | 1646 MiB |
| 평균 SDR piano / guitar / bass / drums | 4.99 / 1.51 / 4.79 / 9.83 dB | 3.90 / 1.47 / 6.84 / 8.20 dB |
| 잔차(mix − 4 stems) | −22.5 dB | −22.6 dB |

한계: 합성음(FluidSynth + GeneralUser GS)이므로 실제 녹음 일반화를 주장하지 못한다. KJ 단독 SDR 수치는 이번 감사에서 확인하지 못했다(확정 수치 없음). **새 Benchmark(Phase 5)에서 KJ를 포함해 재측정한다.**

## 6. 재현 방법

```bash
git worktree add ../music_analyzer_legacy legacy-baseline-2026-10-08
# 체크포인트는 data/separation/models 에 있다. venv는 루트 .venv (torch 2.5.1+cu121).
```

## 7. 새 엔진에 넘기는 교훈

1. 직렬 5개 모델 체인은 오류가 누적된다. 단일 공유 backbone의 다중 head 구조로 대체한다.
2. 12 GiB VRAM에서 inference는 충분하지만 학습은 소형 모델(수 M~수십 M 파라미터), 짧은 chunk, AMP, gradient checkpointing이 필수다.
3. 모든 체크포인트의 학습 데이터 권리는 UNKNOWN이다. OUR MODEL은 합성 + 라이선스 확인 데이터로 처음부터 학습해 이 위험을 없앤다.
4. 이전 테스트 데이터(MedleyDB, `song/*.mp3`)는 상업 학습/평가 근거로 쓰지 않는다. `song/`은 정성 청취 전용.
