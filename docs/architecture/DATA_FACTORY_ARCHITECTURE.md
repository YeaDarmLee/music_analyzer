# Data Factory v0 Architecture

근거: Research Packet 04/05 (사용자 전달, 2026-10-08) **[P45]**. 구현: `src/data_factory/` (엔진과 독립 패키지). 공유 계약은 파형 shape `(channels, samples)`, target dict `{stem: array}`, dataset/asset manifest 정책(`engine.data.manifest`)뿐이다. `engine`을 import하는 모듈은 `assets.py`(정책 호출)와 `adapter.py`(DATASETS 등록) 두 개다.

## 1. 데이터 흐름

```
Composition (procedural, seed)  →  Performance (NoteEvent)  →  SceneSpec (JSON, 소스 오브 트루스)
 SceneSpec → Renderers: Piano/Bass/Drums = OUR sampler (CC0 raw asset) | OUR DSP synth | procedural drum synth
                        Synth = OUR DSP synth       Vocal = VocalSet non-excerpt clip
 → stem-local FX (own DSP) → stem gains → common level scale → common peak scale
 → atomic final stems (vocal, drums, bass, piano, synth, [guitar, strings, brass, organ])
 → mix = float64 sum of final stems
 → target builder (atomic_v1 | 2stem_v1 | 6stem_v1) → QC → manifest/hash → engine DATASETS
```

## 2. 모듈

| 모듈 | 역할 |
|---|---|
| `schema.py` | `NoteEvent`, `SceneSpec` (seeds, composition, note events, renderers, fx, mix, vocal, assets, generator_version). `SceneSpec.hash()` = 내용 해시(git_commit 제외) |
| `util.py` | 시드 파생(`SeedSequence`), `RandomState`(NumPy가 stream을 고정하는 legacy RNG), WAV I/O(scipy), tree/file/array SHA-256 |
| `assets.py` | Packet 판정 catalog → `ingest_asset`(버전 고정, tree sha256, license snapshot) → production gate |
| `sfz.py` | SFZ 입력 메타데이터 파서 (지원 opcode subset; 영역 선택을 바꾸는 critical opcode는 ingest 거부) |
| `sampler.py` | 자체 sampler: zone 선택(key/vel/round-robin/random), playback-rate 리피치, loop, 엔벨로프, pan |
| `synth.py` | 자체 DSP synth(PolyBLEP osc, unison, 2-op FM, ADSR, biquad filter+envelope/LFO, glide, vibrato/tremolo/PWM), patch randomizer + 규칙 기반 label, procedural drum synth |
| `composition.py` / `performance.py` | procedural 화성 문법 / 악기별 연주 패턴(휴머나이즈 포함) |
| `fx.py` | gain, balance pan, RBJ EQ, block compressor, saturation, delay, algorithmic reverb(합성 IR), chorus, width. stem-local |
| `vocal.py` | VocalSet index(excerpt 제외), singer-disjoint split, vocal stem render |
| `mixer.py` / `targets.py` / `qc.py` | exact-sum 믹서 / 계층 target / QC |
| `scenes.py` | `Factory`: `make_spec`(family 분할 rejection sampling) + `render`(전체 또는 window+pre-roll) |
| `fixed.py` | val/test 고정 pre-render (scene별 디렉터리, metadata/provenance/spec) |
| `adapter.py` | engine `DATASETS["datafactory_scenes"]`: lazy window render 또는 fixed 디렉터리, 선택적 LRU 디스크 캐시 |
| `cli.py` | `catalog`, `ingest-asset`, `ingest-sfz`, `ingest-drumkit`, `index-vocalset`, `manifest`, `render-fixed` |

## 3. 재현성
- Scene 시드 5종(composition/performance/instrument/fx/mix)은 `(master_seed, split#attempt, index)`에서 파생. 모든 랜덤은 `RandomState`(stream 고정).
- 같은 `SceneSpec` + 같은 asset → 같은 오디오. 같은 환경(NumPy/SciPy 버전)에서 **별도 프로세스에서도 spec hash·오디오 hash 일치**를 확인함 (`docs/benchmark/data_factory_v0_bench_fixture.json`). fixed 렌더의 `metadata.json`은 numpy/scipy/python 버전을 기록한다. 다른 SciPy 버전/CPU에서 비트 단위 동일성은 보장하지 않는다 (미검증).
- 서로 다른 scene index → 서로 다른 spec/오디오 (테스트).

## 4. 정책 (Packet §2, §18~19, §23)
- **Exact sum**: FX는 stem-local. master 비선형 처리 없음. 공통 level scale(목표 RMS)과 공통 peak scale만 적용. `mix = Σ final stems` (오차 ≤ 2e-6, QC 강제). 비활성 stem은 **정확히 0**.
- **Split**: 파일/클립 random split 금지. `composition_family_id`(모드·키·차수열·박자 구조의 해시)가 train/val/test를 결정하며, 요청 split과 다른 family가 나오면 seed attempt를 올려 재샘플. VocalSet은 singer-disjoint. OOD split은 holdout 악기(`holdout_instruments`)만 쓰고 그 악기는 다른 split에 나오지 않는다.
- **Scene 분포(초기 가설, config)**: vocal+instruments 55% / instrumental only 20% / vocal only 10% / sparse 10% / near-silence 5%; 활성 악기 수 1~4 모두 존재 (400개 샘플 확인: 230/80/45/30/15).
- **Production gate**: scene이 쓰는 모든 asset은 usage 정책을 통과해야 한다 (`render-fixed`가 매 scene에서 검사, 실패 scene은 기록되지 않음). 미-ingest asset(version/sha256 null), RED, YELLOW, 권한 UNKNOWN, 의무(attribution) 누락은 거부.
- **Fallback은 명시**: piano 샘플 asset이 없으면 FM "keys" 합성 patch를 쓰고 `renderers[stem].fallback_for`로 기록한다. 이 fallback으로 만든 piano는 Packet의 "VCSL Keys piano"가 아니다.
- **Lazy vs fixed**: train은 spec+seed만 저장하고 **scene 전체를 렌더한 뒤(모든 FX, scene-level gain 포함) 3 s crop**을 반환한다. 따라서 `full_render(scene)[start:end] == training_crop(scene, start, end)` (property test, 캐시 on/off). val/test는 고정 WAV. 전체 렌더 RTF ≈ 0.084 (대리 데이터 기준)라 연구 초기에는 충분하다. 독립 window 렌더(`render(spec, window)`, 어댑터 `render_path: window`)는 실험적 최적화 경로로만 남기며 전체 렌더와 **같지 않다** (scene-level level scale이 window 기준, pre-roll 밖에서 시작한 지속음 누락, FX tail 차이). 필요해지면 context-aware renderer(pre-roll + active note carry + FX state + post-roll + 전역 정규화)로 대체한다.
- **Activity metadata**: 어댑터는 crop된 target 자체에서 stem별 `active`(peak > `activity_threshold`, 기본 1e-4)를 계산해 `batch["active"]`로 넘기고, 엔진 trainer가 loss에 전달한다. scene에서는 활성이지만 crop 구간이 조용한 stem도 inactive로 취급된다.

## 5. 의존성
추가: **SciPy** (BSD-3-Clause, Packet §4.2 승인) — WAV I/O, biquad/IIR, FFT convolution, resampling. 추가하지 않은 것: FluidSynth, sfizz runtime, Sforzando, VST host, Pedalboard, Surge, Dexed, OB-Xf, librosa, audiomentations, music21, MusPy, pretty_midi, Mido(debug MIDI export 미구현).

## 6. Dataset format (fixed)
```
val_0000001/ mix.wav, <active stem>.wav ..., metadata.json, provenance.json, spec.json
```
`metadata.json`: spec_hash, active/all stems, QC 통계, stem sha256, generator/환경 버전. `provenance.json`: 사용 asset 레코드, usage 검사 결과, `license_manifest_hash`.

## 7. 한계 / 미구현
- guitar / strings / brass / organ stem 없음 (6stem 타깃은 guitar=0으로만 구성 가능). Packet 03 이전 6-stem 본학습 불가.
- 보컬: VocalSet 연습 음원(scale/arpeggio/long tone)만, 반주와 조성 매칭 없음 (Packet §17 v0 범위).
- sampler: SFZ 전체 호환 아님. 외부 SFZ의 필터/엔벨로프 opcode는 무시(보고됨). 샘플 리피치는 선형 보간.
- `ingest-drumkit`의 파일명 키워드 규칙은 실제 Stargate/VCSL 구조 확인 전 가정이다 (NEEDS_VERIFICATION after download).
- 정성 청취: 에이전트는 오디오를 들을 수 없다. 청취용 procedural 샘플 12개를 `data/factory/listening_procedural/`에 생성해 두었다 (사람이 확인해야 함).

## 8. DF-0 결과 반영 (2026-10-08)
- **실제 asset ingest 완료**: VCSL(드럼), VCSL Keys(피아노 4종), Big Little Bass, Sneakybass, Stargate(드럼), VocalSet. 판정·해시·크기·reject/warning 수는 `docs/legal/ASSET_DOWNLOADS.md`. 모든 scene은 `PRODUCTION_TRAINING` gate를 통과한다 (240 scene manifest: `artifacts/manifests/df_v0_smoke.manifest.json`, 7개 asset id).
- **Instrument manifest**는 `artifacts/instruments/`에 커밋된다. 피아노는 FLAC 원본에서 ingest 시점에 디코딩한 float32 WAV 사본(`data/derived/vcsl_keys_wav`, manifest의 `sample_root`/`conversion`에 기록)을 읽는다.
- **스템 레벨**: 믹서가 먼저 모든 스템을 active-RMS(가장 큰 frame 대비 -40 dB 이내 frame의 RMS) -20 dBFS로 맞춘 뒤 랜덤 gain(`stem_gain_db`, 보컬 `vocal_gain_db`)을 적용한다. 이 단계 전에는 보컬이 반주보다 22~26 dB 작게 렌더되었다 (listening pack 진단으로 발견).
- **Activity**: 어댑터가 crop된 target의 peak로 stem별 `active`를 계산하고 trainer가 loss와 metric에 전달한다. 학습 metric(`sdr`, `si_sdr`)은 inactive 항목을 건너뛰고, `inactive_rms_ratio_db`가 비활성 stem 환각을 감시한다.
- **측정(실제 asset, `docs/benchmark/data_factory_v0_bench_real_assets.json`)**: spec 생성 2.3 ms; scene 전체 렌더 0.66 s / 평균 8.4 s scene (RTF 0.079), QC 40/40 통과; full-scene 렌더 dataloader 1.6 / 5.1 / 11.0 item/s (worker 0/4/8, batch 4); 디스크 캐시 hit 0.01 s/item (scene당 약 9 MB — 대량 데이터에서는 LRU 상한 필수); 별도 프로세스 결정성 spec·audio hash 일치.
- **알려진 한계**: 피아노는 서스테인 페달 down 영역만 쓰고 key-release 샘플은 쓰지 않는다. Stargate의 `freesound/` 하위(38개)는 제외했다. 드럼 kit은 폴더/파일명 규칙 기반이고 청취 검증 전이다.

## DF-0 follow-up: piano pedal / veltrack, Long Listening Pack (2026-10-08)

- **Piano**: SFZ `amp_veltrack`/`global_volume` supported; instrument manifest keeps `zones` (CC64=127) and `zones_pedal_up` (CC64=0, only Steinway B has a separate set); `perf_rules_v2` chooses pedal mode per scene (`up` 30 % / `mixed` 30 % / `down` 40 %) and tags piano events with `meta.cc64`. Release samples (`trigger=release`), pedal noise and `rt_decay` stay excluded and are recorded in each manifest's `ingest_report`. Details: `docs/legal/ASSET_DOWNLOADS.md`.
- **Long Listening Pack** (`scripts/df_long_listening.py` → `data/factory/listening_long/`, git-ignored): 8 section-structured songs (45–60 s) for human QA only. `dataset_usage = LISTENING_EVALUATION`, never used for training; training scenes keep the 5–15 s lazy-render format. Songs are assembled from the existing Composition/Performance generators (one chord progression per section letter, repeated sections share harmony and pattern; per-section pattern/groove/stem sets), real PRODUCTION-gated assets (gate + QC checked per song, `mix == sum(stems)` max err 3e-8), and VocalSet **val** singers only (female9 / male11). The vocal stem is a sequence of truncated VocalSet phrases (`vocal.segments`, `len_s` with 40 ms fade). Known limitations: VocalSet phrases are not pitch-aligned to the song key; one synth role/patch per song; no tempo/dynamic automation inside a song.
- **Short Listening Pack** (`scripts/df_listening_pack.py` → `data/factory/listening_real/`): 17 scenes (piano 3, bass 3, drums 3, synth 3, vocal+band 5), `INDEX.json` carries per-stem active RMS / peak, vocal-to-instrumental ratio, instrument ids, singer, FX profile, BPM/key.
