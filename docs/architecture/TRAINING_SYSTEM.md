# Training System (Phase 2 Foundation)

아키텍처 중립 인프라. OUR MODEL 구조는 아직 없다. 유일한 모델은 테스트 fixture `TinyTestSeparator`(`dummy_split` 포함)이며 아키텍처 후보가 아니다.

## 패키지 (`src/engine/`)

| 모듈 | 역할 |
|---|---|
| `interfaces.py` | `SeparatorModel`, `SeparationOutput(stems{name→(B,C,T)}, sample_rate, metadata, aux)`. 파형/STFT/hybrid/query/계층 모델 모두 같은 계약 |
| `registry.py` | `MODELS / LOSSES / METRICS / DATASETS` 레지스트리. 현재 모델은 fixture 2개만 등록. Legacy(KJ 등)는 등록하지 않음 |
| `config.py` | experiment/model/training/dataset 4분리 YAML. 필수 키 검증만 하고 값 default 없음 |
| `hashing.py` | canonical JSON(정렬 키, 무공백, UTF-8, NaN 거부) → SHA-256 |
| `provenance.py` | `<ckpt>.provenance.json` 기록·검증, git/환경 정보, parent lineage |
| `checkpoint.py` | 저장(원자적) / 로드(sidecar sha256 검증 후에만 unpickle) / RNG 상태 |
| `experiment.py` | `runs/<id>/` 로컬 추적 (experiment.json, config 스냅샷, checkpoints, metrics.jsonl) |
| `training/trainer.py` | optimizer·scheduler·AMP·accumulation·clip·checkpointing 모두 config 주입. resume은 optimizer step 경계에서 bit-exact. OOM은 `TrainingOOMError`로 맥락과 함께 보고 |
| `training/losses.py` | loss 레지스트리 + 가중합. 현재 `waveform_l1`, `waveform_l2`(배관 검증용)만 |
| `training/metrics.py` | `sdr`, `si_sdr`, `reconstruction_error_db`(테스트로 정의 검증), `measure_inference`(latency/RTF/peak VRAM) |
| `data/manifest.py` | asset 권한 정책 엔진 (usage별). `DATASET_PROVENANCE.md` 참조 |
| `data/synthetic.py` | 인프라 테스트용 sine-sum 데이터셋 (학습 데이터 아님) |
| `inference.py` | 아키텍처 무관 chunk + overlap-add 추론 (chunk/overlap은 호출자가 지정) |
| `runner.py`, `cli.py` | manifest 검사 → 학습 → ckpt+provenance → 재로딩 → 추론 → metric |

## Config 구조 (`configs/`)
`model/`, `training/`, `dataset/`, `experiment/`. experiment 파일이 나머지 세 파일을 configs 루트 기준 상대경로로 가리킨다. 현재 파일은 `*tiny_test*`, `test_smoke`, `synthetic_tiny`, `phase2_smoke` 뿐이며 값은 테스트용이지 권장값이 아니다.

## Provenance sidecar 필드
`checkpoint_sha256, model_id, model_config_hash, training_config_hash, dataset_manifest_sha256, training_run_id, git_commit, created_at, parent_checkpoint(null=from scratch), dataset_usage, format_version`.

## 아직 정하지 않은 것 (Packet 01/02 이후)
STFT 규격, band 표현, backbone, decoder/head 방식, 2-stem A/B/C, loss 조합, 모델 dim/depth, chunk 길이, 실제 optimizer/scheduler 선택, leakage·stem-preservation metric 정의.

## 실행
```bash
.venv/Scripts/python.exe -m pytest -q
PYTHONPATH=src .venv/Scripts/python.exe -m engine.cli run configs/experiment/phase2_smoke.yaml
```

## Phase 4 additions (Data Factory integration)
- Dataset configs may set `plugin: <module>`; the runner imports it before building datasets (used by `data_factory.adapter`, kind `datafactory_scenes`). The engine does not import `data_factory`.
- `multires_stft` is activity-aware (Research Lead decision, 2026-10-08). The batch may carry `active: {stem: bool (B,)}`; the trainer forwards it to every loss as `active=`. Active items: spectral convergence + log magnitude (+ optional `linear_weight` * linear magnitude). Inactive (silent-target) items: `inactive_linear_weight` * linear magnitude L1 only; spectral convergence and the log term are not computed (relative error to a silent target is undefined), and masked rows use a safe denominator so gradients stay finite. Waveform L1 still applies to all items. Without `active` (external datasets), the Packet-02 form is used; it explodes (~1e10 measured) on silent targets unless `sc_floor_rel` is set, which stays as a numerical-safety fallback (`max(|T|, r*|mixture|)` per item) and is not the main fix. `inactive_stem_penalty` (RMS(est)/RMS(mix)) is not implemented; it stays an ablation to add only if inactive-stem hallucination is observed in real training.
- Manifest policy: `GREEN_CONDITIONAL` grade and explicit obligations (`attribution_required`, `notice_required`, `attribution_text`, `license_url`); see `DATASET_PROVENANCE.md`.
