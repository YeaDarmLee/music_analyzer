# Commercial-Clean Baseline (final_11 고정 기록)

- 기록일: 2026-10-08
- git commit: `1cf6bd8da7d606e18fd5b97ab4f2a0e216368a99` (작업 시작 시점. 이후 변경은 추가 파일과 `registry.py`/`worker.py`의 가산 변경뿐이며 `final_11` 코드 경로는 수정하지 않는다.)
- 목적: commercial_13 작업 전 `final_11`을 BASELINE으로 고정한다. 이 문서의 수치는 코드에서 직접 읽거나 직접 실행한 것이다.

## 1. 모델 레지스트리 (final_11이 로드하는 체크포인트와 SHA-256)

| model_id | checkpoint | SHA-256 | weight license | release status |
|---|---|---|---|---|
| `melband_roformer_kj` | `MelBandRoformer.ckpt` | `87201f4d31afb5bc79993230fc49446918425574db48c01c405e44f365c7559e` | MIT (PUBLISHER_DECLARED) | DEV_ONLY |
| `bs_roformer_6s` | `bs_6stem_fixed.ckpt` | `24e7d35ee9c64415673d3fd33e06a67cac2c103c5df6267ba1576459c775916e` | UNKNOWN (UNRESOLVED) | DEV_ONLY |
| `bs_karaoke` | `bs_roformer_karaoke_frazer_becruily.ckpt` | `eb90ee24c1154d83fbcfd27e96182f19e061557cc6e4746953125e08c29389f9` | UNKNOWN (UNRESOLVED) | DEV_ONLY |
| `bs_roformer_mega5` | `mega5.ckpt` | `8a73fb568f5a4cc28e464dbf7ec3ac2b961a7fe6c010fc97215468582e3d32d3` | MIT (VERIFIED_DECLARATION) | DEV_ONLY |
| `bs_roformer_mega7` | `mega7.ckpt` | `46e2e801cccb08a318947ef596683170603cd6f66717cc7e613242919c877a27` | MIT (VERIFIED_DECLARATION) | DEV_ONLY |
| `melband_karaoke` | `mel_band_roformer_karaoke_becruily.ckpt` | `d3aa262ac01df870b9fc033e9c7b6cad33fe04fc9c148b6c40841326a515a0e0` | UNKNOWN (UNRESOLVED) | DEV_ONLY |
| `bs_roformer_mega4` | `mega4.ckpt` | `c9e368742e5e935e7288f525a93219821eccc7dc285fcdaab91177a17f49567e` | MIT (VERIFIED_DECLARATION) | DEV_ONLY |

CLAPSep `best_model.ckpt`와 LAION-CLAP `music_audioset_epoch_15_esc_90.14.pt`는 별도 venv(`data/separation/tools/clapsep-env`)에서 실행하며 레지스트리 항목은 `clapsep.json`(weight license UNKNOWN)이다.
모든 모델은 `commercial_release_status = DEV_ONLY`이고 `registry.require_dev_only()`가 그 외 상태의 실행을 거부한다.

## 2. final_11 단계 (`web_server.py: Library.analyze`)

1. `vocal_roformer` (melband_roformer_kj, 8 s, overlap 0.4): vocals / instrumental
2. `instrument_mega7` on 원곡: 7개 head 증거 (acoustic-guitar, electric-guitar, synth, bowed_strings, brass, percussion, timpani), 10 s
3. `instrumental_restoration`: vocals에 샌 strings/brass/synth를 instrumental로 복원 (confidence^3, 위상 일치^2)
4. `bs_karaoke` (10 s): vocals → lead / backing
5. `instrument_roformer_6s` (bs_6stem_fixed, 13.35 s): piano / guitar / bass / drums 채택
6. residual1 = instrumental − (piano+guitar+bass+drums)
7. `instrument_mega5` on guitar → acoustic/electric, guitar_residual
8. `instrument_mega5` on residual1 → synth / bowed_strings / brass
9. CLAPSep 심벌 질의 (`synth_recovery.run_for_library('cymbal')`) → `piano_drum_refinement`로 piano→drums 이동
10. `percussion_refinement` (mega7 percussion+timpani 재실행) → percussion 신규 stem
11. `string_routing`, 12. `percussion_refinement.apply_backing`, 13. `context_routing`
14. `with_remaining(flat_v4)` + `validate_partition`

최종 13 stem: lead, backing, piano, synth, strings, brass, acoustic_guitar, guitar, bass, drums, other, guitar_residual, percussion.

## 3. 라우팅 파라미터

- `context_routing.RULES = (('brass', {'guitar': 1, 'other': 2}), ('guitar', {'other': 2, 'synth': 1}), ('synth', {'other': .3}))` (staged-context-pads-v16)
- `string_routing.STRENGTH = {'synth': 1, 'other': 3, 'backing': 2}`
- `instrumental_restoration`: confidence 지수 3, 위상 일치 지수 2, `min(vocal/evidence, 1)` 호환 게이트
- `percussion_refinement.transfer`: confidence 지수 2; `from_backing`: share × coherence^2
- `piano_drum_refinement.cymbal_extract`: 고역 3 kHz→5 kHz 램프, harmonic median 31, percussive mask², CLAP semantic mask²
- STFT: nperseg 2048, noverlap 1536, 블록 512×2048 샘플

## 4. 검증 허용오차

| 대상 | 허용 |
|---|---|
| 최종 stem 합계 vs 원곡 (`validate_partition`) | 최대 절대오차 ≤ 2e-6 |
| 쌍 이동 (restoration, cymbal, synth recovery) | ≤ 2e-7 |
| 라우팅 재구성 (context/string/percussion) | ≤ 2e-6 |

## 5. 테스트 baseline

`separation/tests` 전체: **227 passed, 1 skipped** (61 s, `.venv`, torch 2.5.1+cu121). 실행 전 코드 변경 없음.

## 6. 기존 benchmark 산출물 (덮어쓰지 않음)

`docs/THIRTEEN_TRACK_V16_VERIFICATION.json`, `docs/PAD_EVAL_V15.json`, `docs/PAD_EVAL_BASELINE_KO.md`, `docs/THIRTEEN_TRACK_V15_*`, `docs/STABILITY_V15_KO.md`, `docs/MEGA53_*_KO.md`. 이들 중 MedleyDB/상업곡을 포함한 결과는 commercial_13 근거로 쓰지 않는다 (COMMERCIAL_CLEAN_MIGRATION_KO.md 7장).
