# 상용 이용 가능성 현황 (production route 기준) — 2026-10-08

이 문서는 **품질(QUALITY)과 라이선스(LICENSE)를 분리**해서 적는다. 아래 어떤 항목도 "commercial-ready"라는 뜻이 아니다.
`commercial_2/6/13`은 소유자 결정으로 `release_presets.json`에서 APPROVED 상태이며(서비스 테스트용), 독립된 법적 검토를 거친 것이 아니다.

## 1. 상태 요약

| preset | QUALITY | LICENSE |
|---|---|---|
| commercial_2 (2트랙) | 서비스 테스트 가능. 합성 smoke 통과(stem 2/2, 합 보존 오차 3e-8) | **조건부**: KJ 가중치는 게시자(README) MIT 선언뿐이고, 학습 데이터의 라이선스는 확인되지 않음 |
| commercial_6 (6트랙) | 서비스 테스트 가능. **실제곡에서 drums가 크게 약함**(known limitation) | **BLOCKED(증거 부족)**: Mega53 파생 가중치(core4) — 아래 2절 |
| commercial_13 (13트랙, BETA) | 서비스 테스트 가능. 13/13 stem. drums 한계는 6트랙과 동일, 곡에 따라 결과 편차 | **BLOCKED(증거 부족)**: Mega53 파생 가중치 4종 — 아래 2절 |

## 2. 모델 (실제 production 경로에서 실행되는 5개만)

공통 코드: Music-Source-Separation-Training (ZFTurbo), rev `84b1eac0887756b4f1a9d7a1ff49105939749ed2`, **MIT**(LICENSE 파일, VERIFIED). 코드 라이선스와 가중치 라이선스는 별개로 기록했다.

| model id | 파일 | SHA256 | 가중치 라이선스(상태) | 근거 | 사용 preset |
|---|---|---|---|---|---|
| melband_roformer_kj | MelBandRoformer.ckpt | `87201f4d31afb5bc79993230fc49446918425574db48c01c405e44f365c7559e` | MIT (PUBLISHER_DECLARED) | HF `KimberleyJSN/melbandroformer` README @ac9b0614 | 2, 6, 13 |
| bs_roformer_core4 | core4.ckpt | `24b900e2cc5b405b24cc87b898beb7c57fdcd3bc8fbde5cb514a9a4f716393ed` | MIT (VERIFIED_DECLARATION) | MSST issue #245의 저자 선언 | 6, 13 |
| bs_roformer_mega7 | mega7.ckpt | `46e2e801cccb08a318947ef596683170603cd6f66717cc7e613242919c877a27` | 동일 | 동일 | 13 |
| bs_roformer_mega5 | mega5.ckpt | `8a73fb568f5a4cc28e464dbf7ec3ac2b961a7fe6c010fc97215468582e3d32d3` | 동일 | 동일 | 13 |
| bs_roformer_vocal2 | vocal2.ckpt | `fb4d0d09c900bc40b184b6132efe6ea541c7db969e17e7a60a80ca32898952f6` | 동일 | 동일 | 13 |

(SHA256 전체값은 `separation/configs/commercial_approval.json`, 모델 구성은 `separation/configs/models/*.json`.)
core4·mega5·mega7·vocal2는 모두 공식 `mvsep_mega_model_bs_roformer_53_stems_v1.ckpt`(sha256 `c62820893bbf86d4…3519f`)에서 head만 골라 만든 파생 체크포인트다.
attribution 요구: MIT 고지문(저작권 표시)을 `/licenses`에 싣는 것으로 처리했다. 별도 attribution 문구 요구는 확인되지 않았다.

### Blocker (문서화만 하고 승인 근거를 만들어 내지 않음)
1. **Mega53 가중치의 상업 이용 근거는 저자의 댓글 한 건이다.** 저장소 소유자가 이슈 #245의 2026-09-25 댓글에서 53-stem 가중치를 상업 사용을 포함해 MIT로 배포한다고 밝혔다(2026-10-08 직접 확인). 같은 댓글의 단서: AS IS, 저자가 훈련 오디오 전체의 저작권을 보유하지 않음, 면책 없음. 체크포인트 파일 자체에는 라이선스 파일이 없고, 우리 파생본을 저자가 직접 언급한 것도 아니다.
   `commercial_approval.json`의 `basis`는 이 내용으로 정정했고, 소유자의 위험 수용은 `docs/LICENSE_RISK_ACCEPTANCE_KO.md`에 기록했다.
2. **학습 데이터 출처·라이선스가 확인되지 않았다**(Mega53과 KJ 모두). 가중치가 MIT라는 선언이 학습 데이터의 권리 문제까지 해소하는지는 이 프로젝트에서 판단할 수 없다.
3. 위 두 가지는 코드로 해결되는 문제가 아니다. 상업 서비스 전에 저작권자(ZFTurbo/MVSep, KimberleyJSN)의 서면 확인이나 법률 검토가 필요하다.
4. 품질 개선을 위해 다른 모델을 찾는 조사는 하지 않기로 했다.

## 3. 그 외 production 구성요소 (코드·네이티브·폰트)
`/licenses`(`frontend/public/licenses/`, 서버 18건 · 웹 5건 · 모델 2건 그룹)와 `docs/PRODUCTION_DEPENDENCY_MANIFEST.json`은 실제 production 경로의 import에서 자동 생성한다.
- 서버 패키지: beartype, cryptography, Demucs(MIT), einops, filelock, librosa, NumPy, packaging, psutil, PyMySQL, PyYAML, rotary-embedding-torch, SciPy, python-soundfile, PyTorch, MSST(일부 포함).
- 네이티브: libsndfile 1.2.2(LGPL-2.1, python-soundfile 동봉), FFmpeg(외부 프로세스; 빌드에 따라 LGPL-2.1+ 또는 GPL-2.0+ — **배포 시 사용하는 빌드의 구성과 고지 의무를 따로 확인해야 함**).
- 웹: Vue, @lucide/vue, @mdi/js(Apache-2.0).
- 폰트: Manrope, Noto Sans KR (OFL-1.1).
- 모델 아키텍처 코드(MSST)는 MIT. 아키텍처와 체크포인트를 혼동하지 않았다.

## 4. 검증
- `scripts/build-license-notices.py --check` → "notices and manifest are in sync"
- production route에서 쓰지 않는 모델(final_11의 UNKNOWN 가중치, CLAPSep, htdemucs, bs_6stem 등)은 승인 레지스트리·manifest·`/licenses`에 없다(테스트 `test_notices_built_from_an_approved_preset_list_exactly_its_models`).
- 각 모델의 SHA256은 승인 레지스트리와 모델 레지스트리가 일치한다(`release.model_record`, 문제 0건).
