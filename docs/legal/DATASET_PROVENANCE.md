# Dataset Provenance

등급: **GREEN** 상업 학습 사용 후보 / **YELLOW** 연구·benchmark 전용 / **RED** 학습 금지 / `NEEDS_RESEARCH` 미조사.
GREEN만 학습 manifest에 들어간다. 곡/트랙별 라이선스가 다른 데이터셋은 개별 manifest 수준에서 검증한다.
외부 판정은 Research Packet 05가 전달한 것만 반영한다.

## 1. 실제 데이터셋

| 데이터셋 | 등급 | 라이선스 근거 | 트랙 단위 검증 | 비고 |
|---|---|---|---|---|
| MUSDB18 / MUSDB18-HQ | NEEDS_RESEARCH | | | 레거시 문서는 "연구용"으로 기록했으나 외부 검증 전 |
| MedleyDB | NEEDS_RESEARCH | 레거시 기록: CC BY-NC-SA 4.0 | | 외부 재검증 필요. 그 전까지 학습 사용 금지 |
| Slakh / BabySlakh | NEEDS_RESEARCH | 레거시 기록: Zenodo CC-BY-4.0, 원곡(Lakh MIDI) 권리 미확인 | | |
| MoisesDB | NEEDS_RESEARCH | | | |
| FMA, MTG-Jamendo | NEEDS_RESEARCH | | | stem 없음. 용도 재검토 |
| Mixing Secrets, Cambridge MT, Open Multitrack | NEEDS_RESEARCH | | | |
| `song/*.mp3` (사용자 보관 상용곡) | RED | 권리 없음 | N/A | 정성 청취 전용. 학습/지표 근거 금지 |

## 2. 합성 데이터 소스

| 소스 | 등급 | 근거 | 비고 |
|---|---|---|---|
| 자체 DSP synth 출력 | GREEN 예정 | 자체 생성 | 구현 후 asset manifest로 증명 |
| SoundFont/SFZ 렌더링 | NEEDS_RESEARCH | LICENSE_MATRIX §2 | UNKNOWN asset은 production dataset 불가 |

## 3. Asset 기록 스키마 (구현 대상)

```json
{
  "asset_id": "", "source": "", "license": "", "version": "",
  "commercial_allowed": null, "training_allowed": null,
  "derivative_allowed": null, "redistribution_allowed": null,
  "sha256": ""
}
```

`null`은 UNKNOWN과 같다. `null`이 하나라도 있는 asset은 production dataset 생성에서 거부한다(코드로 강제).

## 4. Checkpoint lineage 추적 (구현 대상)

```
Checkpoint(sha256) → Training Run → Model Config → Training Config → Git Commit
→ Dataset Manifest(sha256) → Source Assets(asset_id) → License
```

각 체크포인트는 위 필드를 sidecar JSON으로 가진다. 구현은 Phase 2의 provenance 모듈에서 한다.
