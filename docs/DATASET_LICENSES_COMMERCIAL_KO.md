# Commercial-Clean Benchmark Dataset Licenses

법률 자문이 아니다. 근거는 저장소에 있는 라이선스 파일/메타데이터와 프로젝트 소유자가 제공한 문서다.

## 사용하는 데이터 (commercial_13 benchmark / 튜닝 후보)

| 데이터 | 위치 | 라이선스 / 근거 | 비고 |
|---|---|---|---|
| 합성 pad-eval (piano/bass/drums/guitar/brass/strings/pad 32 timbre) | `data/pad-eval/stems` | FluidSynth + GeneralUser GS License v2.0 (S. Christian Collins; 프로젝트 소유자가 제공한 라이선스 요약: permissive, 상업 사용 제한 없음). pad 8~31번은 numpy 파라메트릭 생성물(자체 생성) | 15 s, 44.1 kHz stereo, 정확한 GT. 합성음이므로 실제 녹음 일반화는 주장하지 않는다 |
| 합성 piano + cymbal GT | `data/commercial-eval/cymbal-gt` (`scripts/build-cymbal-eval.py`) | 위와 동일 (GeneralUser GS 렌더링) | 12 case, GT stem 3종 (piano / cymbals / body) |
| FreePats Timpani (CC0 1.0) | `data/ground-truth/freepats/Timpani SFZ+WAV-20240810/LICENSE.txt` | CC0 1.0 (Versilian Community Sample Library 기반) | 팀파니 대조군 |
| BabySlakh | `data/ground-truth/slakh/zenodo-record.json` | Zenodo 10.5281/zenodo.4603870, `license: cc-by-4.0` | 16 kHz 원본. **원곡 작곡(Lakh MIDI)의 권리는 확인하지 못했다.** 보조 검증으로만 쓰고 수치를 광고에 쓰지 않는다 |
| Mureka AI 곡 "오늘을 채워 가" | 프로젝트 소유자 보관 (`Commercial_license.pdf`, 저장소 미포함) | Mureka(SKYWORK AI) 소유권 증명서 2026-10-07: 권리는 사용자에게 귀속("if any") | GT 없음. 리드/코러스 정성 비교와 청취용으로만 사용 |

## 제외하는 데이터

| 데이터 | 이유 |
|---|---|
| MedleyDB (`data/ground-truth/medleydb`) | CC BY-NC-SA 4.0, 비상업 |
| `song/*.mp3`, millsage 계열 | 상업 음원, 권리 없음 |
| Philharmonia 샘플 (`data/ground-truth/philharmonia`) | 상업적 튜닝 사용 가능 여부 미확인 |
| 위 데이터에서 파생된 모든 case (`rainfall-*`, `phoenix-*`, `vocal-*violin`, `real-*`, `percussion-*`, `piano-cymbal-text-study` 등) | 원천이 위 목록 |

## 결과 해석 한계
- 모델 학습 데이터의 저작권/동의 상태는 모든 모델에서 UNKNOWN이다 (`training_data_risk`). 가중치 MIT 선언이 학습 데이터 권리를 보증하지 않는다.
- commercial benchmark의 모든 수치는 합성 GT 기준이며 실제 상업 음원에서의 품질을 대표하지 않는다.
