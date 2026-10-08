# Dataset Provenance

등급: **GREEN** 상업 학습 사용 후보 / **YELLOW** 연구·benchmark 전용 / **RED** 학습 금지 / `NEEDS_RESEARCH` 미조사.
GREEN만 학습 manifest에 들어간다. 곡/트랙별 라이선스가 다른 데이터셋은 개별 manifest 수준에서 검증한다.
외부 판정은 Research Packet 05가 전달한 것만 반영한다.

## 1. 실제 데이터셋 (Packet 04/05 판정)

| 데이터셋 | 등급 | 근거 | 비고 |
|---|---|---|---|
| VocalSet | **GREEN_CONDITIONAL** | CC BY 4.0 (Zenodo `1203819`, v1.1, 파일 `VocalSet11.zip` 2.08 GB 조회) | attribution 필수. scales/arpeggios/long_tones만, **excerpts 제외**(139 clip). singer-disjoint split: 아카이브의 `test_singers_technique.txt`를 test로 사용, val은 성별별 최고 번호 잔여 가수. 2026-10-08 ingest 완료 (3474 clip). 인용 문구 형식: NEEDS_RESEARCH |
| MUSDB18 / MUSDB18-HQ | RED | educational only, 상업 금지, NC 구성요소 포함 | Production 학습 금지 |
| MedleyDB | RED | non-commercial | |
| MoisesDB | RED | CC BY-NC-SA 4.0 | |
| Mixing Secrets | RED | educational only; AI 학습은 기여자별 별도 계약 | |
| MDB-stem-synth | RED | CC BY-NC 4.0 | |
| Slakh2100 | YELLOW | CC BY 4.0이나 upstream Lakh MIDI 저자 불명 | research/reference only |
| Lakh MIDI | YELLOW | CC BY 4.0, 곡별 attribution 불가 | symbolic seed로 쓰지 않음 |
| DnR v3 | YELLOW | CC BY-SA 4.0 (ShareAlike) | |
| Common Voice | v0 미사용 | CC0 기여, 발화 데이터 | |
| `song/*.mp3` (사용자 보관 상용곡) | RED | 권리 없음 | 정성 청취 전용 |

**현재 결론 [P45]**: 상업 ML 학습이 명확하고 NC/SA/upstream 문제가 없는 대규모 실제 multitrack 데이터셋은 GREEN 추천 후보가 없다. 전략: CC0 악기 asset + procedural composition + 라이선스된 isolated vocal + 향후 직접 확보 multitrack.

## 2. 합성 데이터 소스

| 소스 | 등급 | 근거 |
|---|---|---|
| 자체 DSP synth / 드럼 synth / FX / composition 출력 | GREEN | 자체 생성 (asset id `project-procedural-dsp`, 레코드는 코드에서 생성, 생성기 버전이 sha256) |
| VCSL(드럼), VCSL Keys, Big Little Bass, Sneakybass | **GREEN, ingest 완료** (해시·스냅샷: `ASSET_DOWNLOADS.md`) | LICENSE_MATRIX 2.2 |
| VSCO 2 CE | GREEN (미다운로드, version/sha256 null → production 거부) | 보류: Strings/Brass 단계 |
| Stargate Sample Pack | **GREEN, ingest 완료** (repo LICENSE = CC0 1.0 Universal) | `freesound/` 하위 38개는 kit에서 제외 (Freesound 업로더 권리 이슈) |
| Freesound CC0 자동 수집 | YELLOW | |

## 3. Asset 기록 스키마 (구현 대상)

```json
{
  "asset_id": "", "source": "", "source_url": "", "license": "", "license_url": "", "version": "", "sha256": "",
  "grade": "GREEN | GREEN_CONDITIONAL | YELLOW | RED",
  "commercial_allowed": null, "training_allowed": null, "derivative_allowed": null, "redistribution_allowed": null,
  "attribution_required": null, "attribution_text": "", "notice_required": null, "downloaded_at": ""
}
```
`sha256`은 asset 디렉터리 트리의 결정적 해시(정렬된 상대경로+파일해시). 라이선스 원문은 `artifacts/licenses/<asset_id>/LICENSE.txt`에 스냅샷하고 해시를 기록한다.

`null`/누락/`"UNKNOWN"`은 모두 UNKNOWN이다. 어떤 flag가 필수인지는 **용도(usage class)** 가 정한다 (`src/engine/data/manifest.py`, 테스트로 강제):

| usage | 허용 grade | 필수 조건 |
|---|---|---|
| `RESEARCH`, `BENCHMARK` | GREEN, GREEN_CONDITIONAL, YELLOW | 없음 (RED는 항상 거부) |
| `PRODUCTION_TRAINING` | GREEN, GREEN_CONDITIONAL | commercial / training / derivative = True, sha256, source/license/license_url/version, attribution_required·notice_required 명시(bool), attribution_required면 attribution_text 필수 |
| `DATASET_REDISTRIBUTION` | GREEN, GREEN_CONDITIONAL | 위 + redistribution = True |

`redistribution_allowed=false`여도 내부 렌더링 학습(`PRODUCTION_TRAINING`)은 막지 않는다. 재배포 가능 여부와 학습 가능 여부는 별개 판정이다.

## 4. Checkpoint lineage 추적 (구현 대상)

```
Checkpoint(sha256) → Training Run → Model Config → Training Config → Git Commit
→ Dataset Manifest(sha256) → Source Assets(asset_id) → License
```

각 체크포인트는 위 필드를 sidecar JSON으로 가진다. 구현은 Phase 2의 provenance 모듈에서 한다.
