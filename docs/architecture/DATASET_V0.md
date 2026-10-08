# Dataset v0 (pre-training report)

기준일 2026-10-08. 상태: **Data Factory v0 = FROZEN**, Dataset v0 생성 완료, 본학습 **미시작** (이 보고 검토 후 첫 학습 설정 확정).
기계 판독 사본: `docs/benchmark/dataset_v0_report.json`. 생성: `python scripts/df_dataset_v0.py`. 분포 config: `configs/data_factory/dataset_v0.yaml`. dataset config: `configs/dataset/dataset_v0_2stem.yaml`. license manifest: `artifacts/manifests/dataset_v0.manifest.json` (16,000 scene, `PRODUCTION_TRAINING` gate 통과, 7개 asset id).

## FROZEN (v0 baseline)
Asset ingest · OUR sampler · piano/bass/drum renderer · OUR DSP synth · composition engine · performance engine (`perf_rules_v2`) · stem-local FX · mixer · exact mixture consistency · QC · provenance · license policy · full-scene render → training crop · VocalSet singer split. 큰 구조 변경/리팩토링 중단. 다양성 부족은 renderer 재작성이 아니라 distribution 확장으로 푼다. 이 단계에서 허용한 코드 변경은 scene type 선택(`Factory._scene_type`, 새 category 이름만 추가; 기존 이름의 동작은 동일)과 config뿐이다.

## 1. Scene distribution (config에 기록, 15,000 train 실측)
| category | 비율 | train 실측 | 구성 |
|---|---|---|---|
| vocal_full_band | 40 % | 5,935 | vocal + 3–4 악기 |
| vocal_sparse | 10 % | 1,459 | vocal + 1–2 악기, 저밀도 |
| instrumental_only | 15 % | 2,321 | 1–4 악기, vocal 없음 |
| vocal_only | 5 % | 722 | |
| dense | 10 % | 1,529 | 4 악기 전부(+vocal 70 %), density 1.0 |
| sparse_instrument | 15 % | 2,273 | 1–2 악기 (+vocal 50 %), 저밀도 |
| near_silence (inactive/edge) | 5 % | 761 | −60~−48 dBFS 레벨 |
scene 길이 5–15 s. scene별 randomize: BPM 70–150, key, mode, chord progression, density, singer, vocal clip/placement/double, piano/bass/drum 악기와 performance pattern, synth role/patch, gain, pan, EQ, comp, saturation, reverb/delay/chorus/width (FX profile 5종).

## 2. Split
| split | scenes | 시간 | 저장 | composition family | 가수 |
|---|---|---|---|---|---|
| train | 15,000 | 41.5 h | lazy (deterministic spec) | 14,002 | 13 |
| val | 500 | 1.40 h | 고정 WAV `data/factory/dataset_v0/val_*` | 487 | female9, male11 |
| test | 500 | 1.44 h | 고정 WAV `.../test_*` | 491 | female2/8/3/5/10 |
leakage: family overlap train/val/test 모두 0, singer overlap 0, train 중복 spec hash 0. val/test 렌더 QC 500/500 + 500/500 통과(실패 0), 고정 WAV 15.4 GB. 같은 family의 scene은 같은 split 안에서만 반복된다(train 15,000 scene = 14,002 family).

## 3. VocalSet 사용 (train)
vocal 포함 10,541 scene, 13명 모두 사용(678–878 scene/명). category scales 4,105 / arpeggios 4,331 / long_tones 2,105. clip: 가용 2,249개 중 2,218개 사용, 1 clip 최대 14회. doubled vocal 4,208 scene. vocal 길이 합 ≈ 1,223 min(중복 포함), **고유 원본은 2,249 clip ≈ 5 h** → vocal domain이 데이터 다양성의 병목이다(가수 13명, 창법 3종, 가사/언어 없음, 음정은 key 비정렬).

## 4. 악기/patch 사용 (train)
- piano: steinway_b 3,246 / grand_k 3,237 / upright_knight 3,184 (upright_y는 holdout). pedal mode up 2,866 / mixed 2,934 / down 3,867. pattern 6종 균등.
- bass: Big Little Bass 2,437 / Sneakybass 2,411 / OUR synth bass 4,939. pattern 5종 균등.
- drums: vcsl 2,408 / stargate 2,463 / OUR drum synth 4,880 (고유 kit 4,880). groove 6종.
- synth: pad 2,503 / lead 2,470 / arp 2,383 / pluck 2,364, 고유 patch 9,720.
- stem 존재: vocal 10,541, piano 9,667, bass 9,787, drums 9,751, synth 9,720. BPM 평균 110. FX profile 5종 ≈ 균등.

## 5. 처리량 / 저장 (이 PC, CPU 렌더)
- spec 생성 51.7 s / 16,000 scene.
- full-scene render: category별 0.16–0.90 s/scene (full_band 0.90, dense 0.72, instrumental 0.79, sparse 0.36, vocal_only 0.16), RTF 0.02–0.10.
- DataLoader full-scene render: **workers 0/4/8 = 1.16 / 2.99 / 4.41 items/s** (batch 4).
- 모델 쪽(`our_separator_v01_profile.json`, ckpt ON, batch 1): fwd+bwd 227 ms/chunk → loss/optimizer 포함 약 0.28 s/chunk ≈ **3.5 chunk/s** (이 값은 profile 기반 추정; 학습 중 실측으로 대체). → DataLoader(4.4/s @8 workers)가 모델과 거의 같은 속도 = 경계선. GPU 학습 중에는 worker가 CPU를 나눠 쓰므로 데이터 쪽이 병목이 될 수 있다.
- 디스크 캐시(full scene, 2-stem float32): 10.3 MB/scene → train 전체 155 GB (여유 930 GB). 캐시 hit은 0.01 s/item이라 epoch 2부터 DataLoader 병목이 사라진다. 대안: 한 번 렌더한 scene에서 서로 다른 crop을 여러 개 사용(adapter 변경 필요, 미적용).
- 이 보고의 필수 항목에 대한 필요 캐시: lazy train 0 GB(권장 시작점), val/test 고정 15.4 GB(생성 완료), 선택적 train full-scene 캐시 155 GB.

## 6. epoch / step / 시간 추정
- epoch 정의(현행 어댑터): scene당 2.98 s crop 1개 = 15,000 chunk = 12.4 h의 crop 오디오(scene 원본 41.5 h). crop 위치는 `epoch_salt`를 바꾸지 않으면 epoch마다 동일.
- batch 1 × accum 8 → 1 epoch = 1,875 optimizer step.
| epochs | step | chunk | 예상 시간 (3.5 chunk/s) |
|---|---|---|---|
| 10 | 18.8 k | 150 k | 11.9 h |
| 20 | 37.5 k | 300 k | 23.8 h |
| 40 | 75 k | 600 k | 47.6 h |
추정은 GPU 실측 전이며 DataLoader가 병목이면 늘어난다(4.4/s면 40 epoch ≈ 38 h는 모델 쪽이 상한이라 사실상 동일). 첫 200 step 실측으로 확정한다.
- checkpoint 제안: 1,000 step마다(≈ 38 min), 최근 3개 + best(val_si_sdr) 유지. validation 제안: 1,000 step마다 val 500 scene(1 crop씩, 약 1–2 min, 학습 시간의 약 3 %), test는 마지막에 1회.

## 7. 알려진 한계 (Failure Analysis 대상)
vocal 다양성(가수 13, 5 h 원본, 키 비정렬, 언어 없음) · 합성 domain 편향(악기 3 piano / 2 bass / 2 drum kit 소스) · 실음원 mismatch · hard example은 학습 결과를 보고 목적성 있게 추가(reverb vocal, cymbal-heavy, 저음역 male 등) · inactive stem penalty는 첫 수천 step 후 `inactive_rms_ratio_db`가 내려가지 않을 때만 추가.

## 8. First baseline run (2026-10-08)
- **Decisions (Research Lead)**: train source = persistent full-scene cache; epoch-dependent crop (`epoch_salt` = epoch); 20 epochs × 1,875 steps = 37,500; val/test fixed and unchanged; validation + checkpoint every 1,000 steps (keep last 3 + best val_si_sdr; `best.json` tracks best overall / vocal / instrumental); test once at the end. No architecture / loss / optimizer / distribution / asset / inactive-penalty change during the run. Config: `configs/experiment/dataset_v0_baseline.yaml`.
- **Cache**: `data/cache/dataset_v0`, 15,000 scenes, 173.4 GB (above the 155 GB estimate: it stores the active atomic stems, not just the 2-stem targets, so 6-stem reuse needs no re-render). Entry = float32 `(n_active, 2, T)`; mix = float64 sum of stems (the mixer's definition); reads are memory-mapped (≈1 MB per crop). Key = spec hash + generator + render-module source hash + asset records + instrument manifests + mix config; never the crop. Fill: 62 min with 10 processes (`scripts/df_cache_fill.py`).
- **Bug found while filling the cache and fixed**: per-stem FX/gain RNG draws iterated a `set` of stem names, so multi-stem scene specs depended on `PYTHONHASHSEED` (differed between processes). Fixed with sorted iteration + regression test; val/test fixed scenes, the report and the cache were regenerated after the fix (the earlier 174 GB cache was discarded).
- **200-step gate**: 4.48 chunk/s, 1.79 s/optimizer step, data wait 0.07 % of step time, cache hit 100 %, item load 24 ms, GPU 82 %, CPU 7 %, peak VRAM 459 MiB, no NaN/Inf, loss 2.98 → 1.41 (mean of first/last 20 steps), max grad norm 22.7 (clipped at 1.0). Projected 37,500 steps ≈ 18.6 h + validations.
