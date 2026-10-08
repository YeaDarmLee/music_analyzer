# Open Source & Model Audit

- 감사일: 2026-10-08
- 대상: `C:\workspace\music_analyzer` (branch `main`, 커밋 `846a58b` 기준 + 미추적 스크립트 4개)
- 방법: 소스 코드·설정·스크립트를 직접 읽고, 설치된 `.venv`의 패키지 메타데이터, `frontend/package-lock.json`, 로컬 체크포인트 파일, 로컬에 내려받은 업스트림 저장소(`data/separation/tools/*`)의 LICENSE를 확인했다. 일부 HuggingFace/GitHub 페이지는 WebFetch로 확인했다.
- 한계: 이 문서는 **법률 자문이 아니다.** 확인하지 못한 항목은 `UNKNOWN` / `NEEDS MANUAL VERIFICATION`으로 표시했다. 코드·모델·의존성은 변경하지 않았다.
- 등급 정의: **GREEN** = 허용형 라이선스(MIT/BSD/ISC/Apache/CC0)이며 표준 고지 유지 외 조건 없음. **YELLOW** = 추가 고지·LGPL/MPL·재배포 조건·학습데이터 불확실성 등 별도 조건 필요. **RED** = 현재 사업 모델에서 사용·재배포 제한 가능성이 큼. **UNKNOWN** = 라이선스 확인 실패(권리자 허락이 확인되지 않았으므로 **출시 전 차단 항목으로 취급**).

---

## 1. Executive Summary

1. 실제 사용 파이프라인의 **코드 라이선스는 대부분 MIT/BSD로 양호**하다. Copyleft(GPL/AGPL)는 프로젝트 코드·의존성에서 발견되지 않았다. 다만 LGPL 3개(`libsndfile`, `lameenc`, `soxr`), MPL 1개(`tqdm`), 그리고 개발 PC의 **FFmpeg가 `--enable-gpl --enable-version3` 빌드**라는 점이 Windows 배포(시나리오 B)에서 문제가 된다.
2. 진짜 위험은 **모델 가중치**다. 운영 경로(`final_11`)가 로드하는 체크포인트 7개 중
   - 라이선스가 확인된 것은 2계열(KimberleyJSN MelBandRoformer = HF 헤더 MIT, MVSep Mega53 = 작성자가 MIT 선언했다고 저장소가 기록)뿐이고,
   - `bs_6stem_fixed.ckpt`(피아노/베이스/드럼/기타 담당 — **파이프라인의 중추**), `bs_roformer_karaoke_frazer_becruily.ckpt`(리드/코러스), CLAPSep `best_model.ckpt`, LAION-CLAP `music_audioset_epoch_15_esc_90.14.pt`는 **라이선스 UNKNOWN**이다. HF 페이지에 모델 카드가 없다(WebFetch 확인).
   - 모든 모델의 **학습 데이터 저작권/동의 상태가 불명**(`training_data_risk: UNKNOWN`)이다. MIT 선언이 있어도 학습 음원의 권리 보증은 아니다.
3. 저장소는 이미 위험을 인지하고 모든 모델을 `commercial_release_status: DEV_ONLY`, `redistribution: BLOCKED`로 표시한다(`separation/configs/models/*.json`), 그리고 `registry.require_dev_only()`가 DEV_ONLY가 아니면 **실행을 거부**한다(`registry.py:43-45`). **상용 출시 전에 이 게이트를 의도적으로 바꿔야 하며, 그 전에 가중치 라이선스 해결이 선행**되어야 한다.
4. 검증 데이터에 **MedleyDB 샘플(CC BY-NC-SA 4.0, 비상업)** 이 쓰였다(`scripts/prepare-medleydb-ground-truth.py:48`). 결과 수치를 마케팅/상용 벤치마크에 쓰는 것은 금지 위험. 저장소 루트의 `song/`에는 상업 음원 MP3가 있다(git 제외, `.gitignore`의 `*.mp3`).
5. 자체 Engineering IP는 **다중 모델 오케스트레이션과 STFT 기반 '합계 보존' 재배분(routing/leakage repair) 후처리**에서 발생한다. 개별 모델과 아키텍처는 모두 외부 것이다. 이 계층이 경쟁력의 핵심이고, 공개 시 모방이 가장 쉬운 부분이기도 하다.

**한 줄 결론:** 현재 상태로 SaaS/Windows 상용 출시는 **불가(P0 미해결)**. 가중치 4종 UNKNOWN과 Windows용 FFmpeg/LGPL 정리, 샘플/벤치마크 데이터 정리가 끝나야 한다. 코드의 일부 공개는 가능하지만 오케스트레이션·후처리는 비공개를 권장한다.

---

## 2. 전체 Architecture

```
frontend/ (Vue 3 + Vite, MIT 계열)            ← 업로드/DAW형 플레이어/다운로드
   │  POST /api/analyses?preset=...
separation/src/music_analyzer/web_server.py   ← 표준 라이브러리 http.server 기반 자체 서버 + 세션/쿠키 인증
   ├─ auth.py (PBKDF2-SHA256 600k, PyMySQL → MySQL)          [자체 작성]
   ├─ job_service.py / worker.py (GPU당 1작업, 별도 프로세스, OOM 재시도)  [자체 작성]
   │     worker.py → roformer_runner.py (MSST vendored 모델 로드/청크 추론)
   │              → Demucs 경로 (htdemucs 계열, 현재 운영 단계에서는 미사용)
   ├─ ingest.py (ffprobe/ffmpeg subprocess → 44.1kHz float32 stereo canonical.wav)
   ├─ 후처리 모듈: instrumental_restoration / context_routing / string_routing /
   │               percussion_refinement / piano_drum_refinement / synth_recovery / leakage_rule
   └─ 별도 가상환경 data/separation/tools/clapsep-env (CLAPSep + laion-clap) — subprocess로 호출
```

- 서버: `ThreadingHTTPServer` 류 표준 라이브러리(외부 웹 프레임워크 없음). 의존: `numpy, soundfile, psutil, filelock, PyMySQL[rsa]` (`separation/pyproject.toml`).
- 모델 레지스트리: `separation/configs/models/*.json` + `registry.py`(SHA-256 pinning, 다운로드 URL allowlist).
- 로컬 전용 현황: 모든 모델은 사용자 PC(RTX 3060 12GiB)에서 실행. 클라우드/Docker 파일 없음(`Dockerfile`, `docker-compose*` **없음**).

### 외부 의존성 탐색 결과 요약 (요청 1항 체크)

| 항목 | 결과 |
|---|---|
| requirements*/pyproject/setup | `separation/pyproject.toml`, `separation/requirements/windows-py312-cu121.lock.txt`(버전 스냅샷, 해시 없음) |
| poetry/uv/conda | 없음 |
| JS | `frontend/package.json`, `package-lock.json` (pnpm/yarn lock 없음) |
| Docker | 없음 |
| Shell/PS | `scripts/bootstrap.ps1`(torch cu121 설치), `separate.ps1`, `smoke.ps1`, `start-web.ps1` |
| Git submodule | 없음 (`.gitmodules` 없음) |
| vendor/third_party | `separation/src/music_analyzer/vendor/msst/` 1곳 |
| 자동 다운로드 | `registry.py`(Meta CDN, HuggingFace 3곳), `mega53_experiment.py`(GitHub release), `scripts/prepare-clapsep.py`(HF Space), `scripts/prepare-audiosep.py`(pip + 저장소), 데이터셋 준비 스크립트(수동 다운로드 후 처리) |
| ONNX | 코드에서 사용하지 않음(HF `noblebarkrr/mvsepless_resources`가 ONNX 저장소라는 점만 확인) |
| Git 이력 | 체크포인트/오디오 바이너리가 커밋된 이력 **없음** (`git log --all` 확인) |

---

## 3. 실제 Audio Processing Pipeline

UI에 노출되는 버전은 `basic_2`, `basic_6`, `final_11`(13트랙) 3종(`frontend/src/App.vue:75-78`). API 기본값은 `final_10`(`web_server.py:662`, 레거시)이지만 UI는 이 값을 보내지 않는다. 실행 경로는 `web_server.py: Library.analyze()`(197-392행).

### 3.1 `final_11` (13트랙, 주력)

| # | 단계 | 파일/함수 | 외부 프로젝트 | 모델/체크포인트 | 담당 | 입력 → 출력 | 후처리 |
|---|---|---|---|---|---|---|---|
| 0 | 업로드·디코드 | `ingest.py: ingest_file/stream_decode` (139행) | **FFmpeg/ffprobe** (subprocess) | - | - | mp3/wav/flac → 44.1kHz stereo f32 `canonical.wav` | `aresample`(필요 시), 길이/해시 검증 |
| 1 | 보컬/반주 분리 | `worker.py` → `roformer_runner.run_roformer` (`vocal_roformer`) | MSST(vendored `MelBandRoformer`) | `melband_roformer_kj` / `MelBandRoformer.ckpt` | 보컬 | canonical → `vocals`, `instrumental = 입력 − vocals` | fp16, 8s 청크, overlap 0.4 |
| 2 | 원곡 악기 근거 | `instrument_mega7` | MSST `BSRoformer` | `bs_roformer_mega7` / `mega7.ckpt` (Mega53에서 7개 head 추출) | acoustic-gtr, electric-gtr, synth, bowed_strings, brass, percussion, timpani **(근거용 추정치)** | **원곡** → 7 stem | 최종 stem으로 직접 쓰지 않고 이후 라우팅의 "증거"로 사용 |
| 3 | 보컬→반주 복원 | `instrumental_restoration.apply` | scipy.signal STFT | - | 보컬 쪽에 샌 strings/brass/synth를 반주로 반환 | vocals+instrumental+증거 → 새 vocals/instrumental | 합계 보존 검증(`2e-7`) |
| 4 | 리드/코러스 분리 | `bs_karaoke` | MSST `BSRoformer` | `bs_karaoke` / `bs_roformer_karaoke_frazer_becruily.ckpt` | lead, backing | vocals → `lead`, `backing` | 이후 7·10단계에서 backing 일부를 타악기/현악으로 재배분 |
| 5 | 기본 악기 4종 | `instrument_roformer_6s` | MSST `BSRoformer` | `bs_roformer_6s` / `bs_6stem_fixed.ckpt` | piano, guitar, bass, drums (other/vocals는 버림) | instrumental → 6 stem 중 4개 채택 | 청크 13.35s |
| 6 | 잔여 계산 | `with_remaining` (web_server.py:429) | - | - | residual1 | `instrumental − (piano+guitar+bass+drums)` | 산술 |
| 7 | 기타 재분리 | `instrument_mega5` on **guitar** | MSST | `bs_roformer_mega5` / `mega5.ckpt` | acoustic-guitar, electric-guitar | guitar → 2 stem; `guitar_residual = guitar − (ac+el)` | |
| 8 | 신디/현악/브라스 | `instrument_mega5` on **residual1** | MSST | 동일 | synth, bowed_strings, brass | residual1 → 3 stem | |
| 9 | 피아노 내 심벌 이동 | `synth_recovery.run_for_library('cymbal')` → `piano_drum_refinement.apply/cymbal_extract` | **CLAPSep** + **laion-clap** (별도 venv subprocess) | `best_model.ckpt` + `music_audioset_epoch_15_esc_90.14.pt` | 텍스트 질의 "ride cymbal…" 로 심벌 추정 | piano stem → 심벌 성분 | 하모닉 보호(median filter) + 3kHz 이상 + 의미 마스크로 piano→drums 이동 |
| 10 | 기타 타악기 | `percussion_refinement.prepare_source` → `instrument_mega7` 재실행 → `transfer` | MSST, scipy | mega7 | percussion/timpani | `drums+other` 합 → 추정, 원곡 증거와 결합 | STFT 마스크로 drums/other → `percussion` 신규 stem |
| 11 | 스트링 라우팅 | `string_routing.apply` | scipy | (mega7 증거) | synth/other/backing → strings | 마스크 이동, backing에서 가져온 분량은 instrumental에도 가산 | |
| 12 | 백킹 타악기 | `percussion_refinement.apply_backing` | scipy | (mega7 증거) | backing → percussion | | |
| 13 | 패밀리 라우팅 | `context_routing.apply` (RULES) | scipy | (mega7 증거) | brass←{guitar,other}, guitar←{other,synth}, synth←other | | |
| 14 | 최종 정리 | `with_remaining(..."flat_v4")`, `validate_partition` | - | - | `other` = 원곡 − 나머지 합 | 13 stem | 합계 ≤ 2e-6 검증 |

최종 13트랙: **lead, backing, piano, synth, strings, brass, acoustic_guitar, guitar(일렉), bass, drums, other(추가 반주), guitar_residual(기타 보조), percussion(기타 타악기)** (`web_server.py:417-427`, `App.vue:78`).

### 3.2 `basic_2` / `basic_6` / `final_10`(레거시)

- `basic_2`: 1단계만 → vocals, instrumental.
- `basic_6`: 1 → `instrument_roformer_6s` → vocals, piano, guitar, bass, drums, other(잔여).
- `final_10`(레거시): 1 → 6s(piano/bass/drums) → `instrument_mega5`를 **반주 전체**에 실행(acoustic/electric/synth/strings/brass) → `bs_karaoke` → CLAPSep로 synth/strings 보완(`synth_recovery.run_for_library`, 프롬프트는 `synth_recovery.py:10-16`) → `leakage_rule` 에너지 게이트.

### 3.3 코드에 있으나 운영 경로가 아닌 것
Demucs(htdemucs/6s/ft), `melband_karaoke`, `mega4`, AudioSep(`audiosep_experiment.py`), WeSpeaker 참조(`scripts/run-target-voice-experiment.py`), `pipeline.py`(CLI 2단계), `pair_refinement.py`, `scripts/study-*` 다수 — 실험/비교용.
**주의:** `worker.py:50-56`은 모든 작업에서 `demucs.apply`/`demucs.pretrained`를 무조건 import하고 `demucs==4.0.1`을 검사한다. 따라서 Demucs 코드는 RoFormer 전용 실행에서도 **런타임 필수 의존성**이다.

---

## 4. Stem별 모델 구성

| 최종 Stem | 1차 모델 | 추가 모델/증거 | 후처리 | 실제 코드 |
|---|---|---|---|---|
| Vocal(lead) | MelBandRoformer(Kim) → BS-RoFormer karaoke | mega7(strings/brass/synth 증거로 보컬 내 샌 악기 반환) | `instrumental_restoration` (confidence³·위상 코히런스²) | `web_server.py:241-258`, `instrumental_restoration.py` |
| Chorus(backing) | 동일 karaoke | mega7 percussion/timpani, bowed_strings | 백킹→타악기·스트링 이동 | `percussion_refinement.apply_backing`, `string_routing.py` |
| Piano | BS-RoFormer 6s | CLAPSep 심벌 질의 | 심벌 성분을 drums로 이동 | `piano_drum_refinement.py` |
| Synth | mega5 (잔여 반주에 적용) | mega7 증거 | `context_routing` RULES synth←other(.3), string_routing | `context_routing.py:13-15` |
| Strings | mega5 `bowed_strings` | mega7 증거 | synth/other/backing→strings 이동 | `string_routing.py:10` |
| Brass | mega5 | mega7 증거 | guitar·other→brass 이동 | `context_routing.py:13` |
| Acoustic Guitar | 6s guitar → mega5 | - | - | `web_server.py:290-296` |
| Electric Guitar | 6s guitar → mega5 | mega7 증거 | other·synth→guitar 이동 | `context_routing.py:13` |
| Bass | BS-RoFormer 6s | - | 없음 | |
| Drums | BS-RoFormer 6s | CLAPSep(심벌 수취) | percussion 분리 시 일부 차감 | `percussion_refinement.transfer` |
| Percussion(기타 타악기) | (신규 stem) mega7 percussion+timpani 2회 평가 | 6s drums/other | 증거 기반 STFT 마스크 | `percussion_refinement.py:6-26` |
| Guitar residual | 6s guitar − (ac+el) | - | 산술 | `web_server.py:296` |
| Other | **산술 잔차** (원곡 − 모든 stem 합) | - | 합계 검증 | `with_remaining` |

**구조적 특징:** 한 모델의 출력을 그대로 쓰는 stem은 bass뿐이다. 나머지는 (a) 다른 모델로 재분리, (b) 원곡에 돌린 증거 모델(mega7)로 STFT 마스크 재배분, (c) 텍스트 질의 모델(CLAPSep) 재추출, (d) 잔차 산술로 만들어진다. 모든 재배분은 `이동량을 한쪽에서 빼서 다른 쪽에 더하는` 방식이라 **합계가 보존**된다.

---

## 5. OSS Dependency Inventory

"사용 중" 판정 기준: 실제 import/호출 확인. 선언만 있고 호출이 없는 것은 별도 표기.

### 5.1 운영 경로 (Python)
| 컴포넌트 | 버전 | 사용 위치(근거) |
|---|---|---|
| PyTorch (+CUDA 12.1 번들) | 2.5.1+cu121 | `roformer_runner.py`, `worker.py` |
| torchaudio | 2.5.1+cu121 | 설치·버전 기록만(`environment.py:32`). 운영 경로 호출 없음 |
| Demucs | 4.0.1 | `worker.py:50-56` 무조건 import |
| MSST(ZFTurbo) vendored | rev `84b1eac…` | `vendor/msst/*`, `roformer_runner.py:66,68` |
| rotary-embedding-torch | 0.9.1 | `vendor/msst/bs_roformer.py` import |
| einops / beartype | 0.8.2 / 0.22.9 | vendor import |
| PyYAML | 6.0.3 | `roformer_runner.py` config |
| NumPy / SciPy | 1.26.4 / 1.14.1 | 전반, STFT는 `scipy.signal` |
| python-soundfile (+libsndfile) | 0.13.1 | 전반 |
| filelock / psutil | 3.32.3 / 7.1.0 | GPU 락, 프로세스 관리 |
| PyMySQL[rsa] + cryptography | 1.1.2 / 50.0.2 | `auth.py` |
| FFmpeg/ffprobe | gyan.dev `2026-03-01-git-862338fe31-full_build` (PATH) | `ingest.py:81,139` |
| CLAPSep | rev `e3c7365…` | `clapsep_experiment.py`, `part_study.py` (별도 venv) |
| laion-clap | 1.1.7 | `prepare-clapsep.py:15` (+ HTS-AT/Swin/open_clip 파생 코드 내장) |
| Python 런타임 | 3.12 | README: "venv 기반 interpreter는 Codex 제공 runtime" → 배포용 Python 별도 필요 |

### 5.2 Frontend (`package-lock.json`, 전부 직접 확인)
`vue 3.5.43`(MIT), `@lucide/vue 1.52.0`(ISC), `@mdi/js 7.4.47`(Apache-2.0), `vite 6.4.3`·`@vitejs/plugin-vue 5.2.4`(MIT, 빌드 전용). 전이 의존성 전체 라이선스 분포: MIT 81, ISC 2, Apache-2.0 1, BSD-2 1, BSD-3 1 — 비허용형 없음.

### 5.3 설치만 되어 있고 우리 코드가 호출하지 않는 것
`librosa 0.11.0`(선언만, import 없음), `lameenc 1.8.4`(demucs 의존, LGPL-3.0), `soxr 1.1.0`(librosa 의존, LGPL-2.1), `openunmix 1.3.0`, `julius`, `dora_search`, `omegaconf`, `submitit`, `numba/llvmlite`(CLAPSep venv), `scikit-learn`, `tqdm(MPL-2.0 AND MIT)`, `pooch`, `requests` 등.

### 5.4 실험 전용 (운영 미사용)
AudioSep(+lightning, transformers, timm, torchlibrosa, torchvision, webdataset 등 `prepare-audiosep.py:14`), WeSpeaker 참조(Apache-2.0), `torchaudio.compliance.kaldi`(`scripts/run-target-voice-experiment.py`).

---

## 6. Model / Weight Inventory

로컬 체크포인트 총 **23개 파일**(`data/separation/models` 18 + `tools` 5). 운영(`final_11`) 로드 7개 + 파생 원본 1개.

### 6.1 운영 경로
| 파일(경로) | 크기 | 모델/구조 | 출처 URL | 원 개발자 | 로드 코드 | 용도 |
|---|---|---|---|---|---|---|
| `data/separation/models/melband_roformer_kj/MelBandRoformer.ckpt` | 871 MiB | Mel-Band RoFormer (`vendor/msst/mel_band_roformer.py`) | `huggingface.co/KimberleyJSN/melbandroformer` @`ac9b061…` | Kimberley Jensen | `roformer_runner.py:75-83` | 보컬/반주 |
| `…/bs_roformer_6s/bs_6stem_fixed.ckpt` | 667 MiB | BS-RoFormer 6stem | `huggingface.co/noblebarkrr/mvsepless_resources` @`030a01a…` | **원 학습자 불명** (재호스팅 저장소) | 동일 | piano/guitar/bass/drums |
| `…/bs_karaoke/bs_roformer_karaoke_frazer_becruily.ckpt` | 195 MiB | BS-RoFormer | `huggingface.co/becruily/bs-roformer-karaoke` @`f7849ae…` | becruily(+frazer 표기) | 동일 | lead/backing |
| `…/bs_roformer_mega5/mega5.ckpt` | 169 MiB | BS-RoFormer(Mega53에서 head 5개만 추출) | 파생: `official-53.ckpt` | MVSep / ZFTurbo (release v1.0.21) | 동일 | 기타·신디·현악·브라스 |
| `…/bs_roformer_mega7/mega7.ckpt` | 216 MiB | 동일(head 7개) | 파생 | 동일 | 동일 | 증거 모델 |
| `data/separation/tools/CLAPSepInference/model/best_model.ckpt` | 170 MiB | CLAPSep (HTS-AT decoder 파생) | HF Space `AisakaMikoto/CLAPSep` @`e3c7365…` | Hao Ma | `clapsep_experiment.py:~35`, `part_study.py:143-163` | 심벌 질의 추출 |
| `…/music_audioset_epoch_15_esc_90.14.pt` | 2.2 GiB | LAION-CLAP 오디오-텍스트 인코더 | 동일 Space | LAION | 동일 | CLAPSep 텍스트 임베딩 |
| (파생 원본) `…/mega53_3head/official-53.ckpt` | 1.3 GiB | BS-RoFormer 53-stem | `github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.21/mvsep_mega_model_bs_roformer_53_stems_v1.ckpt` | MVSep(ZFTurbo) | `mega53_experiment.py:26`, `scripts/prepare-final-instruments.py` | mega4/5/7 생성 |

mega5/mega7은 공식 53-stem 체크포인트의 **head 선택(pruning)만** 수행한 파생 가중치다(`bs_roformer_mega5.json: derivation.transform = "head-pruning-only"`). 즉 **원본 가중치의 수정물(derivative)** 이다.

### 6.2 레지스트리에는 있으나 운영 미사용(dev/legacy)
Demucs: `955717e8-8726e21a.th`(htdemucs), `5c90dfd2-34c22ccb.th`(6s), ft bag 4개(`f7e0c4bc`, `d12395a8`, `92cfc3b6`, `04573f0d`) — 출처 `dl.fbaipublicfiles.com/demucs/hybrid_transformer/`(Meta). `melband_karaoke`(becruily, 1.6 GiB). `mega4`, `mega6`(디스크에만 존재, 레지스트리 미등록), `mega53_{3head,5head,5head_bowed}`. AudioSep 체크포인트 2개, WeSpeaker `avg_model.pt`.

---

## 7. License Matrix

### 7.1 체크포인트별 (코드/가중치 분리)

| 체크포인트 | Code License | Weight License | 상업 사용 | 재배포 | 수정 | Attribution | SaaS 추론 | Desktop 번들 | 근거 |
|---|---|---|---|---|---|---|---|---|---|
| Kim MelBandRoformer | MIT(MSST, 아키텍처 구현) | **MIT 선언**(HF 헤더, README 비어 있음) | 가능 추정(학습데이터 불명) | 가능 추정 | 가능 | MIT 고지 | YELLOW | YELLOW | `melband_roformer_kj.json`, WebFetch |
| BS-RoFormer 6stem | MIT | **UNKNOWN** — HF에 모델 카드·라이선스 없음 | UNKNOWN | UNKNOWN(레지스트리는 BLOCKED) | UNKNOWN | UNKNOWN | **차단** | **차단** | `bs_roformer_6s.json`, WebFetch |
| BS-RoFormer karaoke (becruily) | MIT | **UNKNOWN** — "No model card" | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | **차단** | **차단** | `bs_karaoke.json`, WebFetch |
| Mega53 official / mega5 / mega7 | MIT | **MIT(작성자 선언)** — 저장소는 MSST issue #245를 근거로 기록. 같은 답변이 학습음원 권리·법적 보증을 부인한다고 `docs/audio-separation/04_MODEL_EVIDENCE_KO.md §3`에 기록. **본 감사의 WebFetch로는 해당 선언을 재확인하지 못함** → NEEDS MANUAL VERIFICATION | 선언상 가능 | 선언상 가능 | 가능(head-pruning) | MIT 고지 | YELLOW | YELLOW | `bs_roformer_mega*.json` |
| CLAPSep `best_model.ckpt` | MIT(로컬 `CLAPSep/LICENSE`, Hao Ma) | **UNKNOWN** (`clapsep.json: weight_license`) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | **차단** | **차단** | `clapsep.json` |
| LAION-CLAP `music_audioset_epoch_15_esc_90.14.pt` | CC0-1.0(laion-clap 패키지, `CLAPSep/THIRD_PARTY_NOTICES.md`) | **NEEDS MANUAL VERIFICATION** (코드 CC0 ≠ 체크포인트) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | 차단 | 차단 | 〃 |
| Demucs `.th` 6종(dev) | MIT | **UNKNOWN**(issue #327 무응답; WebFetch 확인) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | 차단 | 차단 | `demucs_*.json` |
| becruily MelBand karaoke(dev) | MIT | UNKNOWN | UNKNOWN | - | - | - | 차단 | 차단 | `melband_karaoke.json` |
| AudioSep 2종(experiment) | MIT(로컬 LICENSE) | "MIT declared on official Space card; individual checkpoint permission not separately verified" | UNKNOWN | - | - | - | 차단 | 차단 | `audiosep_base.json` |
| WeSpeaker `avg_model.pt`(experiment) | Apache-2.0 | UNKNOWN | UNKNOWN | - | - | - | 차단 | 차단 | `tools/wesep-reference` |

### 7.2 전체 컴포넌트 표 (43행)

위험도 합계: **GREEN 22 · YELLOW 11 · RED 2 · UNKNOWN 8**

| # | Component | 실제 사용 위치 | Version | Upstream | License | 상업 | SaaS | 바이너리 배포 | 소스 공개 의무 | Attribution | 위험도 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | PyTorch | roformer_runner | 2.5.1+cu121 | pytorch.org | BSD-3 | O | O | O | 없음 | 고지 | GREEN |
| 2 | NVIDIA CUDA/cuDNN 런타임(torch wheel 번들) | GPU 추론 | cu121 | NVIDIA | NVIDIA EULA(독점) | O | O | 조건부(EULA 재배포 목록) | 없음 | 고지 | YELLOW |
| 3 | torchaudio | 설치(버전기록) | 2.5.1 | pytorch | BSD-2/3 | O | O | O | 없음 | 고지 | GREEN |
| 4 | Demucs(코드) | worker.py import | 4.0.1 | facebookresearch | MIT | O | O | O | 없음 | 고지 | GREEN |
| 5 | MSST vendored(ZFTurbo) | vendor/msst | rev 84b1eac | GitHub | MIT(수정 2건) | O | O | O | 없음 | **저작권·MIT 고지 필수**(LICENSE 동봉) | YELLOW |
| 6 | rotary-embedding-torch | vendor import | 0.9.1 | lucidrains | MIT | O | O | O | 없음 | 고지 | GREEN |
| 7 | einops | vendor import | 0.8.2 | arogozhnikov | MIT | O | O | O | 없음 | 고지 | GREEN |
| 8 | beartype | vendor import | 0.22.9 | beartype | MIT | O | O | O | 없음 | 고지 | GREEN |
| 9 | PyYAML | config | 6.0.3 | yaml | MIT | O | O | O | 없음 | 고지 | GREEN |
| 10 | NumPy | 전반 | 1.26.4 | numpy | BSD-3(+번들 OpenBLAS 등 고지) | O | O | O | 없음 | 고지 | GREEN |
| 11 | SciPy | STFT 후처리 | 1.14.1 | scipy | BSD-3 | O | O | O | 없음 | 고지 | GREEN |
| 12 | python-soundfile | 입출력 | 0.13.1 | bastibe | BSD-3 | O | O | O | 없음 | 고지 | GREEN |
| 13 | libsndfile(soundfile wheel 내장) | 입출력 | wheel 내장(버전 UNKNOWN) | libsndfile | **LGPL-2.1** | O | O | 동적 링크·교체 가능성 유지 시 O | LGPL 조건 | 고지+LGPL 텍스트 | YELLOW |
| 14 | filelock | GPU 락 | 3.32.3 | tox-dev | MIT(패키지 메타) | O | O | O | 없음 | 고지 | GREEN |
| 15 | psutil | 프로세스 관리 | 7.1.0 | giampaolo | BSD-3 | O | O | O | 없음 | 고지 | GREEN |
| 16 | PyMySQL | auth | 1.1.2 | PyMySQL | MIT | O | O | O | 없음 | 고지 | GREEN |
| 17 | cryptography | PyMySQL RSA | 50.0.2 | pyca | Apache-2.0 OR BSD-3 | O | O | O | 없음 | 고지 | GREEN |
| 18 | FFmpeg/ffprobe | ingest.py subprocess | gyan `full_build` 2026-03-01 | ffmpeg.org | 이 빌드 = **GPLv3**(`--enable-gpl --enable-version3`, x264/x265 포함) | O | O(서버에서 호출만) | **GPL 빌드 동봉 시 소스 제공 의무** | 동봉 시 GPL | 고지 | YELLOW (B 시 RED) |
| 19 | CLAPSep(코드) | 별도 venv | rev e3c7365 | AisakaMikoto HF Space / Hao Ma | MIT | O | O | O | 없음 | 고지 | GREEN |
| 20 | laion-clap(+HTS-AT/Swin/open_clip 파생) | CLAPSep venv | 1.1.7 | LAION | CC0-1.0(PyPI classifier는 Apache로 불일치) | O | O | O | 없음 | 권장 | GREEN |
| 21 | Vue | frontend | 3.5.43 | vuejs | MIT | O | O | O | 없음 | 고지 | GREEN |
| 22 | Vite + plugin-vue | 빌드 | 6.4.3 / 5.2.4 | vitejs | MIT | O | O | 번들 산출물만 | 없음 | 고지 | GREEN |
| 23 | @lucide/vue | frontend | 1.52.0 | lucide | ISC | O | O | O | 없음 | 고지 | GREEN |
| 24 | @mdi/js | frontend | 7.4.47 | Templarian | Apache-2.0 | O | O | O | 없음 | 고지+NOTICE | GREEN |
| 25 | lameenc(설치만) | demucs 의존, 미호출 | 1.8.4 | - | **LGPL-3.0+** | O | O | 동봉 시 LGPLv3 조건(교체 가능성) | LGPL | 고지 | YELLOW |
| 26 | soxr(설치만) | librosa 의존, 미호출 | 1.1.0 | - | **LGPL-2.1+** | O | O | 〃 | LGPL | 고지 | YELLOW |
| 27 | tqdm | 전이 | 4.70.1 | tqdm | **MPL-2.0 AND MIT** | O | O | 파일 단위 소스 공개(수정 시) | MPL(수정분) | 고지 | YELLOW |
| 28 | dora_search/julius/openunmix/omegaconf/submitit(그룹) | demucs 전이 | 각각 | - | MIT/BSD | O | O | O | 없음 | 고지 | GREEN |
| 29 | Kim MelBandRoformer 가중치 | 보컬 | - | HF KimberleyJSN | MIT 선언, 학습데이터 UNKNOWN | 조건부 | 조건부 | 조건부 | 없음 | 고지 | YELLOW |
| 30 | bs_6stem_fixed 가중치 | piano/gtr/bass/drums | - | HF noblebarkrr(재호스팅) | **UNKNOWN** | UNKNOWN | UNKNOWN | UNKNOWN | - | - | UNKNOWN |
| 31 | BS karaoke(becruily) 가중치 | lead/backing | - | HF becruily | **UNKNOWN** | UNKNOWN | UNKNOWN | UNKNOWN | - | - | UNKNOWN |
| 32 | Mega53 → mega5/mega7 가중치 | 기타·신디·증거 | - | ZFTurbo/MVSep | MIT 선언(재확인 필요), 학습데이터 UNKNOWN | 조건부 | 조건부 | 조건부 | 없음 | 고지 | YELLOW |
| 33 | CLAPSep best_model 가중치 | 심벌 질의 | - | HF Space | **UNKNOWN** | UNKNOWN | UNKNOWN | UNKNOWN | - | - | UNKNOWN |
| 34 | LAION-CLAP 오디오 체크포인트 | CLAPSep | - | LAION | **UNKNOWN** | UNKNOWN | UNKNOWN | UNKNOWN | - | - | UNKNOWN |
| 35 | Demucs 가중치(dev) | 미사용(레지스트리) | - | Meta CDN | **UNKNOWN** | UNKNOWN | UNKNOWN | UNKNOWN | - | - | UNKNOWN |
| 36 | becruily MelBand karaoke(dev) | 미사용 | - | HF | **UNKNOWN** | UNKNOWN | UNKNOWN | UNKNOWN | - | - | UNKNOWN |
| 37 | AudioSep 가중치(exp) | 실험 | - | HF Space | 선언 MIT, 개별 미검증 | UNKNOWN | UNKNOWN | UNKNOWN | - | - | UNKNOWN |
| 38 | WeSpeaker avg_model(exp) | 실험 | - | - | **UNKNOWN** | UNKNOWN | UNKNOWN | UNKNOWN | - | - | UNKNOWN |
| 39 | MedleyDB 샘플(검증 데이터) | `prepare-medleydb-ground-truth.py` | - | MedleyDB | **CC BY-NC-SA 4.0**(스크립트가 기록) | **X(비상업)** | X | 재배포 시 SA | SA | BY | RED |
| 40 | BabySlakh/Slakh | 검증 데이터 | - | Zenodo 4603870 | CC BY 4.0 | O | O | O | 없음 | **BY 표기** | YELLOW |
| 41 | Philharmonia 샘플 | 검증 데이터 | - | philharmonia.co.uk | "Free use; do not redistribute unmodified samples" (스크립트 기록, 원문 미확인) | 조건부 | 조건부 | **재배포 금지** | - | - | YELLOW |
| 42 | FreePats 팀파니 | 검증 데이터 | - | freepats | CC0-1.0 | O | O | O | 없음 | 없음 | GREEN |
| 43 | `song/` 상업 음원 MP3(일반 가요·애니송 등) | 수동 테스트 입력 | - | 각 권리자 | **저작권 있음, 허락 없음** | X | X | X | - | - | RED |

> 표 아래 카운트는 위 43행의 직접 집계: GREEN 22(1,3,4,6–12,14–17,19–24,28,42), YELLOW 11(2,5,13,18,25–27,29,32,40,41), RED 2(39,43), UNKNOWN 8(30,31,33–38).

---

## 8. SaaS Commercial Use Risk (시나리오 A)

- **GPL/LGPL 의무는 SaaS에서 사실상 발동하지 않는다.** 서버에서 FFmpeg(GPL 빌드 포함)를 subprocess로 호출하고 사용자에게 바이너리를 배포하지 않으면 소스 공개 의무가 없다. AGPL/SSPL 의존성은 **발견되지 않았다**.
- **가장 큰 문제는 가중치.** SaaS는 "추론 결과 제공"이므로 가중치 파일의 재배포는 없지만, **UNKNOWN 라이선스 가중치를 상업 서비스에 쓰는 것 자체의 허락이 없다.** 6s·karaoke·CLAPSep·LAION-CLAP 4종은 해결 전 상용 투입 불가.
- 학습 데이터: 모든 모델 `training_data_risk: UNKNOWN`. 출력(stem) 자체의 저작권은 사용자 음원에 귀속되며, 사용자가 업로드한 곡에 대한 권리 책임·약관·DMCA 대응이 별도 필요(코드 범위 밖).
- 사용자 업로드 음원 보관/삭제 정책, 서버 쿠키(`AUTH_COOKIE_SECURE`) 등은 제품 법무 범위.
- 샘플 음원: 대화에서 Sono(AI) 생성 곡을 샘플로 쓰려는 계획이 언급됨. 해당 서비스의 약관(플랜별 상업권)은 **NEEDS MANUAL VERIFICATION**. `song/`의 상업 음원은 샘플·홍보에 사용 금지.

## 9. Windows Distribution Risk (시나리오 B)

1. **FFmpeg**: 현재 PATH의 빌드는 GPLv3 full build. 설치 프로그램에 동봉하면 GPLv3 의무(대응 소스 제공, 고지). 상용 폐쇄 제품이면 **LGPL 전용 빌드(`--enable-gpl` 없음)** 를 쓰거나 FFmpeg를 번들하지 말고 직접 디코딩(libsndfile mp3 지원 등)으로 대체 검토. 동봉 여부와 무관하게 사용자 PC 설치를 요구하는 방식도 가능.
2. **LGPL 라이브러리**: `libsndfile`(soundfile wheel에 DLL 내장), `lameenc`, `soxr`. PyInstaller 등 단일 바이너리로 정적 결합하면 사용자가 라이브러리를 교체할 수 없어 LGPL 위반 소지. 폴더형(onedir) 배포로 DLL 분리 유지, LGPL 텍스트·소스 위치 고지. 우리 코드가 호출하지 않는 `lameenc`/`soxr`는 **배포물에서 제외**하는 편이 가장 안전.
3. **CUDA/cuDNN**: torch cu121 wheel에 포함된 NVIDIA 런타임은 NVIDIA 라이선스(재배포 허용 목록·조건). 최종 사용자 PC 드라이버 요구 사항 별도.
4. **가중치 번들**: UNKNOWN 가중치는 **인스톨러에 포함 금지**. 레지스트리가 `redistribution: BLOCKED`. 사용자가 직접 내려받게 하는 방식도 권리 문제 해결 전에는 위험.
5. Python 런타임: README가 "Codex 제공 runtime" 기반 venv라고 밝힘 → 배포용 Python(PSF) 별도 패키징.
6. 로컬 추론이라 가중치가 사용자 PC에 놓임 → 가중치 추출/재배포 위험. 업스트림 가중치가 허용하더라도 모델 보호 수단 없음.

## 10. Open Source Publication Risk (시나리오 C)

- 우리 저장소에 **MSST vendored MIT 코드가 이미 포함**: LICENSE 동봉 + `PROVENANCE.json`으로 출처·수정 기록(좋은 상태). 공개 시 NOTICE에 ZFTurbo, lucidrains(원 구현 계보), Meta Demucs 고지 추가.
- 가중치·오디오·데이터셋은 `.gitignore`로 제외되어 있고 Git 이력에도 없음 → 이 상태를 유지하면 **실수로 가중치를 공개할 위험은 낮음.** 다만 `docs/*.json`, `docs/*.md`에 실험 결과·곡 제목(저작물 제목)·로컬 경로가 들어 있어 공개 전 정리 필요.
- `.env`(로컬 비밀)가 작업 디렉터리에 있음 — 추적되지 않지만(.gitignore) 공개 전 `git ls-files`로 재확인. 이력에 없음은 확인.
- 코드를 MIT/Apache로 공개하면 **오케스트레이션 노하우가 그대로 노출**된다(11장). 공개 범위는 14·15장 참조.
- CC BY-NC-SA(MedleyDB) 데이터에서 파생한 `docs/*GROUND_TRUTH*` 결과 문서를 상업 마케팅에 쓰면 NC 위반 가능.

## 11. Copyleft / Native Dependency Review

| 라이선스 | 발견 | 영향 A(SaaS) | 영향 B(Windows) | 영향 C(OSS 공개) |
|---|---|---|---|---|
| GPL-3 | FFmpeg gyan full build(외부 바이너리) | 영향 없음(배포 안 함) | **동봉 시 의무 발생** | 저장소에 FFmpeg 미포함 → 없음(스크립트가 PATH 호출만) |
| AGPL / SSPL / BUSL / Commons Clause / PolyForm | 없음 | - | - | - |
| LGPL-2.1/3.0 | libsndfile, soxr, lameenc | 영향 없음 | 동적 링크·교체 가능·고지 필요; 미사용 둘은 제외 | 저장소에 포함 안 됨 → 없음 |
| MPL-2.0 | tqdm(전이) | 없음 | 수정 없이 번들하면 고지만 | 없음 |
| CC BY-NC-SA 4.0 | MedleyDB 샘플(데이터) | 벤치마크 상업 사용 불가 | 동일 | 결과 공개 시 SA/NC 조건 |
| CC BY 4.0 | Slakh | 표기 | 표기 | 표기 |
| OpenRAIL / Research-only / Academic-only | 가중치 중 **확인된 것 없음**, 단 UNKNOWN 다수 | 모델 카드 부재 | - | - |
| NVIDIA EULA | CUDA/cuDNN | 영향 없음 | 재배포 조건 | - |

네이티브 확인 항목: **libsndfile**(soundfile wheel 내장, LGPL-2.1), **CUDA/cuDNN**(torch wheel 내장), **NumPy/SciPy**(OpenBLAS 등 BSD 계열 번들 + gfortran 런타임 예외 고지), **ffmpeg**(위). SaaS에서 LGPL은 문제 없음. Windows exe와 함께 배포하면 위 표 대로 동적 링크 유지.

## 12. Third-Party Code Provenance

| 현재 파일 | 원본 | 원본 라이선스 | 수정 |
|---|---|---|---|
| `separation/src/music_analyzer/vendor/msst/bs_roformer.py` | ZFTurbo/Music-Source-Separation-Training `models/bs_roformer/bs_roformer.py` @`84b1eac` | MIT(Roman Solovyev) | PROVENANCE: attend import 변경 (sha 불일치로 수정 확인) |
| `…/mel_band_roformer.py` | 동일 저장소 `mel_band_roformer.py` | MIT | 〃 |
| `…/attend.py` | 동일 `attend.py` | MIT | torch 2.5 호환을 위해 `set_priority` 제거 |
| `…/vendor/msst/LICENSE` | 동일 LICENSE(해시 동일) | MIT | 없음 |
| `separation/configs/models/*.upstream.yaml` | 각 모델 배포처 config | 모델별 UNKNOWN~MIT | `.gitattributes`로 바이트 보존 |
| `CLAPSepInference/model/CLAPSep*.py` | HF Space / GitHub (로컬 `tools/`, **git 미포함**) | MIT | 없음(해시 고정, `clapsep.json`) |

원 계보: MSST의 RoFormer 구현은 lucidrains/BS-RoFormer 계열(MIT)에서 파생된 것으로 보이나, 이 판단은 vendor 파일 헤더에서 직접 확인되지 않았다(헤더에 라이선스 문구 없음) → NEEDS MANUAL VERIFICATION. 저장소 내 다른 복사 코드는 발견하지 못했다. `scripts/tonal_refinement_candidate.py` 등은 자체 작성으로 판단.

## 13. Proprietary Components

**A. 완전 자체 코드:** `auth.py`, `job_service.py`, `job_contracts.py`, `worker.py` 틀, `ingest.py`(ffmpeg 호출 래핑), `web_server.py`, `common.py`, `registry.py`, `audio.py`, `evaluation.py`, `ground_truth.py`, `comparison.py/.html`, `separation/sql/001_accounts.sql`, 테스트 24개.
**B. 외부 OSS 단순 호출:** `demucs_adapter.py`(Demucs 호출/청크 수 계산), `roformer_runner.py` 중 모델 로드·추론 틀(MSST 모델 사용, 오버랩 어드 합성은 자체), CLAPSep 호출 부분.
**C. 수정한 외부 코드:** `vendor/msst/*` (최소 수정 2건).
**D. 외부 모델 구조:** MelBandRoformer, BSRoformer, CLAPSep(HTS-AT 기반), HTDemucs.
**E. 외부 가중치:** 6장 전체. (mega5/mega7은 우리가 head를 잘라 만든 파생물이나 지식은 외부 학습의 것)
**F. 자체 orchestration/routing/heuristic:** `web_server.analyze()` 단계 순서 설계, 증거 모델(mega7) 이중 실행, 라우팅 규칙(`context_routing.RULES`), 단계별 합계 보존 구조.
**G. 자체 후처리:** `instrumental_restoration`, `context_routing`, `string_routing`, `percussion_refinement`, `piano_drum_refinement`, `leakage_rule`, `synth_recovery`(프롬프트·적용 로직), `with_remaining`.
**H. UI/Backend:** `frontend/src/*`(Vue 스튜디오, `bufferPlayer.js`, `trackGroups.js`, `clarity.js`, `analysisEstimate.js`), 서버·인증.

### F/G 구현 상세 (핵심)

1. **증거 모델 재사용:** Mega53 head 7개를 **원곡**에 한 번 돌려 `context` 증거를 만든다(strings/brass/synth/타악기 등). 정규 파이프라인이 반주에서 얻은 stem 은 연쇄 오류가 있어, 원곡에서의 판단이 더 정확하다는 가정(`context_routing.py` 독스트링).
2. **STFT 마스크 이동 공식 (공통):** `nperseg=2048, noverlap=1536`. 목표 악기 증거 `T`의 에너지 점유율 `share[target] = |T|² / (Σ|증거|² + |X−Σ증거|²)`. 이동량 = `S_source × clip(share[target] − share[source], 0, 1)^p × clip(cos(위상 차이), 0, 1)²`. `p`는 규칙별 보수성 지수. 이 값을 source에서 빼서 target에 더한다 → **합계 정확 보존**, 위반 시 예외(`> 2e-6`).
3. **규칙 표(튜닝값):** `RULES = brass←{guitar:1, other:2}, guitar←{other:2, synth:1}, synth←{other:0.3}` (32개 참조 케이스 v15, 64개 합성 pad 케이스 v16으로 튜닝했다고 주석). `string_routing.STRENGTH = {synth:1, other:3, backing:2}` (v13).
4. **보컬 경계 복원(`instrumental_restoration`):** 증거 3개 중 bin별 최대 크기 추정을 선택, `confidence = ownership³ × min(vocal_power/evidence_power,1) × cos²` 로 보컬 → 반주 이동.
5. **타악기 신설:** drums+other 합을 mega7 percussion/timpani(원곡 + 합산 입력 2회)와 비교해 `confidence²` 마스크로 `percussion` stem 생성, drums가 가진 비율(`drum_share`)만큼은 drums에서 차감하고 나머지는 other에서 차감.
6. **피아노 내 심벌 이동:** CLAPSep에 텍스트 "ride cymbal being struck with drumsticks" 질의 → median filter(하모닉 vs 퍼커시브)로 **피아노 하모닉 보호 마스크** × 의미 마스크 × 3–5kHz 램프 → piano→drums 이동.
7. **leakage_rule(final_10):** 100ms RMS 상대 레벨 히스테리시스(-38/-44 dB), attack 50ms/release 300ms 게이트, 잘린 샘플은 other로 반환.
8. **합계 검증:** 최종 `validate_partition`이 13 stem 합과 원곡을 샘플 단위로 비교(≤2e-6). 시스템 전체 설계 원칙이 "무손실 재배분".

## 14. 공개 가능한 영역

**PUBLIC_SAFE**
- `frontend/src/bufferPlayer.js`, `trackGroups.js`, `motion.js`, `style.css`, `clarity.js`(UI/플레이어 일반 로직), `frontend/*.test.*`
- `separation/src/music_analyzer/audio.py`, `common.py`, `evaluation.py`, `job_contracts.py`, `job_service.py`, `ingest.py`, `environment.py`
- `separation/src/music_analyzer/auth.py`, `separation/sql/001_accounts.sql` (비밀 값 없음 확인 후)
- `separation/tests/*` (경쟁 기술 노출이 큰 `test_*routing*`, `test_leakage*`, `test_context*`, `test_piano_drum*`는 제외)
- `docs/ACCOUNTS_MYSQL_KO.md`, `docs/WEB_STUDIO_GUIDE_KO.md`

**PUBLIC_WITH_NOTICE**
- `separation/src/music_analyzer/vendor/msst/*` (LICENSE·PROVENANCE 동봉 필수)
- `separation/src/music_analyzer/roformer_runner.py`, `demucs_adapter.py`, `registry.py`, `worker.py` (모델 로더, 출처 URL 노출 포함)
- `separation/configs/models/*.json|yaml`, `presets/demucs.json` (**`weight_license: UNKNOWN` 사실이 공개됨** — 공개해도 되지만 문장 정리 필요)
- `scripts/bootstrap.ps1`, `separate.ps1`, `start-web.ps1`
- `README.md` (제품 설명)

## 15. 비공개 권장 영역

**PRIVATE_RECOMMENDED**
- `separation/src/music_analyzer/web_server.py` 의 `analyze()` 단계 순서(분리해서 비공개로)
- `context_routing.py`, `string_routing.py`, `percussion_refinement.py`, `piano_drum_refinement.py`, `instrumental_restoration.py`, `leakage_rule.py`, `synth_recovery.py`(프롬프트 포함), `pair_refinement.py`, `substem_*.py`
- `separation/configs/instrument_taxonomy.v1.1.json`, `configs/pipeline.json`
- 튜닝 근거: `docs/*STABILITY*`, `docs/THIRTEEN_TRACK_*`, `docs/TWELVE_TRACK_*`, `docs/PAD_EVAL_*`, `docs/SYNTH_*`, `docs/FINAL_*TRACKS*`, `docs/*_RESULTS.json`
- `scripts/study-*.py`, `verify-*.py`, `run-*.py`, `build-*.py`, `reanalyze-*.py`, `score-*.py`, `prepare-*.py` (벤치마크·라우팅 연구 이력)
- `frontend/src/App.vue` 내 "분석 단계 문구" (과정 노출)

## 16. 재배포 금지 또는 별도 확인 영역

**DO_NOT_REDISTRIBUTE** (GitHub·설치 파일·CDN 모두)
- `data/separation/models/**` 전체 체크포인트 (특히 `bs_roformer_6s/bs_6stem_fixed.ckpt`, `bs_karaoke/*.ckpt`, `melband_karaoke/*.ckpt`, Demucs `.th`)
- `data/separation/tools/CLAPSepInference/model/*.ckpt|*.pt`, `tools/AudioSep/checkpoint/*`, `tools/wesep-reference/checkpoint/*`
- `data/ground-truth/medleydb/**` (NC-SA), `data/ground-truth/philharmonia/**`(재배포 금지 문구)
- `song/*.mp3` (상업 음원), `data/**/*.wav|mp3` 전부
- `data/**/library/models/**/*.ckpt` (하드링크된 케이스별 복사본 다수; 공개 폴더에 생길 위험)
- FFmpeg GPL 빌드 바이너리(`C:\ffmpeg\bin`)를 설치 파일에 동봉 금지(대응 소스 제공 체계 없이는)
- `.env`, `data/separation/web/**`의 사용자 업로드·세션 데이터

**NEEDS MANUAL VERIFICATION 우선순위:** ① `bs_6stem_fixed.ckpt` 원 학습자와 허락 ② becruily karaoke 라이선스 ③ CLAPSep/LAION-CLAP 체크포인트 라이선스 ④ Mega53 MIT 선언 원문(issue #245) 재확인과 학습 데이터 권리 서면 ⑤ Kim MelBandRoformer 학습데이터.

## 17. Patent Review Candidates (확정 아님, 코드 관찰 기준)

단순 OSS 연결(특허 후보 아님): 분리 모델 직렬 연결(vocal→instrument), 청크 오버랩 추론, 잔차(원곡−stem) 산출, 파일 해시 검증.

`PATENT_REVIEW_CANDIDATE`
1. **원곡 증거 모델 + 하위 단계 stem 간 합계보존 재배분**(`context_routing.transfer`): 원곡에서 얻은 다중 악기 증거로, 이후 단계의 오분류 stem들 사이에서 time-frequency bin 단위로 소유권 점유율×위상 일관성으로 이동. (공개 전 검토 1순위)
2. **보컬/반주 경계 복원**(`instrumental_restoration`): 악기 증거로 보컬 stem 내 반주 누출을 반주로 되돌림.
3. **기타 타악기 신규 stem 생성**(`percussion_refinement.transfer`): drums와 잔여 반주의 합을 증거와 점유율로 재분할.
4. **하모닉 보호형 심벌 이전**(`piano_drum_refinement.cymbal_extract`): 텍스트-질의 분리 모델 + HPSS median 마스크 + 고역 램프를 결합해 피아노→드럼 이동.
5. **텍스트-질의 모델 + 반주 잔차 stem에 대한 악기 보완**(`synth_recovery` 프롬프트 설계).
6. 전체 "무손실 단계 파티션 + 단계별 검증(`validate_partition`) + 롤백 기록(record-before-*.json)" 파이프라인 구조.

## 18. P0 / P1 / P2 Legal Actions

**P0 (SaaS/Windows 출시 전 필수)**
1. `bs_6stem_fixed.ckpt`, `bs_roformer_karaoke_frazer_becruily.ckpt`, CLAPSep `best_model.ckpt`, LAION-CLAP 체크포인트의 라이선스를 권리자에게서 서면 확인하거나, **라이선스가 명확한 대체 모델/자체 학습으로 교체.**
2. Mega53 MIT 선언 원문 보관(스크린샷·아카이브) + 학습 데이터 권리에 대한 보증이 없다는 점을 리스크로 승인할 의사결정.
3. 모든 모델의 `training_data_risk` 처리 방침(법무 검토). `commercial_release_status` 게이트(`registry.py:43`)는 법무 승인 후에만 변경.
4. MedleyDB 결과를 상업 벤치마크에서 제외, `song/` 상업 음원 샘플·홍보·저장소 사용 금지 확인.
5. (B) FFmpeg: GPL 빌드 동봉 금지 → LGPL 빌드 또는 비동봉 설계 확정.

**P1**
6. LGPL(libsndfile 등) 동적 링크 유지 가능한 패키징 설계, `lameenc`/`soxr`/`librosa` 배포물 제외.
7. 배포용 Python 런타임(Codex 제공 runtime 의존 제거), CUDA/cuDNN 재배포 조건 확인.
8. `THIRD_PARTY_NOTICES` 작성(MSST, Demucs, CLAPSep, laion-clap, HTS-AT/Swin/open_clip, Vue, lucide, mdi 등).
9. 이용약관·개인정보·업로드 음원 권리 보증/DMCA 정책(SaaS).
10. Sono 등 AI 음악 생성 서비스로 만든 샘플의 상업 이용 약관 확인.

**P2**
11. 공개 전 문서에서 곡 제목·로컬 경로 제거, 오픈소스 공개용 저장소 분리(`opensource-pipeline`).
12. 특허 후보(17장) 선출원 검토 후 공개.
13. 의존성 hash-lock(현재 lock 파일은 버전 스냅샷만).

## 19. Final Recommendation

- **지금 상업 출시는 보류.** 코드는 문제가 적지만, 운영 경로 가중치 4종이 UNKNOWN이고 학습데이터 위험이 모든 모델에 있다.
- 가장 빠른 해법: (1) 라이선스가 명시적으로 확인되는 모델(MIT 선언을 서면으로 받은 Mega53 계열, Kim MelBand)을 중심으로 재구성할 수 있는지 평가, (2) 6s·karaoke는 권리자 확인 또는 대체/자체 학습. Mega53의 53개 head 중 bass/drums/piano/vocals 역시 있으므로(`official-53.ckpt`) 6s를 Mega53 head로 대체할 수 있는지 품질 비교 가치가 있다(품질은 이번 감사 범위 밖).
- 공개 전략: UI·서버·모델 로더·vendor(고지 포함)는 공개 가능. **오케스트레이션과 라우팅 후처리는 비공개**.

### "남의 기술 조립"과 "자체 Engineering IP" 평가

| 구분 | 내용 | 평가 |
|---|---|---|
| 조립 | 보컬/악기 분리, karaoke, Mega53 head, CLAPSep, Demucs, FFmpeg, 프론트 라이브러리 | 전부 외부. 모델 선택 자체의 차별성은 낮음(같은 체크포인트를 누구나 받을 수 있음) |
| 자체 IP (강) | 원곡 증거 기반 합계보존 재배분 계열(`context_routing`/`string_routing`/`percussion_refinement`/`instrumental_restoration`), 하모닉 보호 심벌 이전, 튜닝된 규칙·지수, 13트랙 정의, 증거 이중 실행 | 실제 엔지니어링 가치가 있는 부분 |
| 자체 IP (중) | 단계별 무손실 파티션 검증·롤백, 작업/OOM 복구, 모델 레지스트리 hash 고정 | 품질/운영 신뢰성 |
| 자체 IP (약) | 웹 UI, 인증, 일반 서버 | 모방 쉬움 |
| 검증 자산 | 13트랙·32/64 케이스 벤치마크와 튜닝 이력 | 데이터 일부가 NC-SA라 활용 제한 |

> 경쟁사 복제 경계선: **모델 목록 + 실행 순서 + RULES/STRENGTH 수치 + 합계보존 STFT 마스크 수식**을 공개하면 거의 같은 품질을 재현할 수 있다. 모델 로더·UI·서버를 공개하는 것은 경쟁력을 거의 해치지 않는다. 벤치마크 데이터와 튜닝 근거 문서는 비공개가 안전하다.
