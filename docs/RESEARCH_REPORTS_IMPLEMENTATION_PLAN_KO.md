# 네 리서치 보고서 검토와 개선 실행안

검토일: 2026-10-06. 제공된 네 Markdown 보고서를 현재 코드와 대조했다. 이 문서는 채택할 제안과 수정할 제안을 구분한 개발 기준이며, 모델 교체나 품질 향상을 이미 완료했다는 의미는 아니다. 보고서 안의 Q1/Q2/Q3, 설치 명령, 예제 코드는 참고 자료로 취급했다.

실행 업데이트: 공식 가중치 검증, 3-head 변환, probe 출력 동등성, RTX3060 추론과 SPYAIR 전체 곡 추출을 수행했다. 수치와 품질 검증의 남은 범위는 [첫 실행 결과](MEGA53_FIRST_BENCHMARK_KO.md)에 기록했다.

## 결론

첫 개선은 **공식 Mega53에서 신스·어쿠스틱 기타·일렉기타 세 출력만 사용하는 로컬 실험**이다. 현재 `other`를 신스로 표시하거나 일반 `guitar`를 일렉기타로 표시하는 구조를 먼저 해결한다. 이후 같은 결과를 기준으로 후처리를 한 종류씩 비교한다. 후처리 여러 개를 동시에 넣으면 모델 개선과 음색 변경의 효과를 구분할 수 없다.

기본 분석을 바꾸기 전에 공식 체크포인트 무결성, 세 head의 정확한 대응, 원본과 축소 모델의 출력 동일성, RTX3060 12GB 실행 가능성, 실제 분리 품질을 각각 검증한다. 신스 전용 **출력 클래스**를 확보하는 것이 모든 곡에서 신스만 완벽하게 분리한다는 보장은 아니다.

## 보고서별 역할

| 제공 파일 | 핵심 내용 | 프로젝트에 반영할 판단 |
| --- | --- | --- |
| `deep-research-report.md` | 공식 Mega53 → 자체 3-head, 기타/신스 품질 차이, 입력 경로 비교 | 첫 모델 검증의 기준으로 채택 |
| `deep-research-report (1).md` | 악기별 복원, raw 보존, 음성 전용 모델의 한계 | 원본 보존과 선택 처리 채택. 노래 보컬에도 speech AI는 기본 OFF |
| `deep-research-report (2).md` | WOLA, mixture consistency, Wiener, 후처리 단계 | 기존 구현을 먼저 확인. 잔여 재주입·Wiener는 실험군으로 제한 |
| `deep-research-report (3).md` | 구간 진단, 후보 비교, MISI, DiCoSe/SR 장기 연구 | 최소 측정부터 시작. 자동 결함 판정·후보 선택·학습 시스템은 후순위 |

보고서 내부의 `turn...` 인용 식별자는 출처 URL이 아니므로 재사용하지 않는다. `sandbox:/mnt/data/...`에 있는 그림·WAV도 로컬 제공 파일이 아니며 실제 프로젝트 음원 측정 증거로 취급하지 않는다.

## 현재 코드에서 확인한 사실

1. `separation/src/music_analyzer/web_server.py`의 `analyze()`는 원곡 보컬 분리 → 반주 악기 분리 → 보컬의 리드/코러스 분리를 수행한다.
2. `flatten_session()`은 악기 모델의 `other`를 `synth`로 바꿔 표시한다. 현재 신스 전용 추출이 아니다. `guitar`도 어쿠스틱/일렉 전용 분리가 아니다.
3. 나머지는 `original - sum(displayed_tracks)`로 생성한다. 모든 표시 트랙을 더하면 float32 저장 오차 범위에서 원곡이 된다. 이 합 일치는 개별 트랙이 정확하다는 증거가 아니다. 겹친 추정치를 빼면 나머지에 상쇄 성분이 들어갈 수 있다.
4. `roformer_runner.overlap_infer()`에는 문맥 패딩, 양수 선형 페이드, 가중치 누적 후 정규화, 출력 길이/유한값 검증이 이미 있다. 단순 청크 이어 붙이기가 아니다.
5. vendored `bs_roformer.py`는 `active_stem_ids`를 지원한다. 현재 runner는 `model(piece)`를 호출하므로 기본적으로 등록된 모든 head를 실행한다.
6. 모델은 복소 마스크를 입력 STFT에 곱한다. magnitude만 예측하고 mixture phase를 무조건 재사용하는 모델로 설명하면 부정확하다.
7. runner는 이미 `torch.load(weights_only=True)`와 `strict=True`를 사용하며 추론 시간 및 PyTorch GPU peak allocated/reserved를 기록한다.
8. 기존 선명도 기능은 EQ다. 분리 오류를 복원하는 AI 기능으로 보아서는 안 된다.

## 그대로 적용하지 않을 권고

| 보고서 제안 | 수정 이유 | 결정 |
| --- | --- | --- |
| WOLA/crossfade부터 새로 구현 | 이미 정규화된 overlap-add가 있음 | 기존 코드 재사용. 실제 경계 결함이 확인될 때만 창/overlap 비교 |
| equal-power crossfade 기본 적용 | 같은 신호를 단순 equal-power로 합치면 중앙 레벨이 올라갈 수 있음 | 기존 정규화 유지. 추가 페이드 중복 적용 금지 |
| residual의 50–80%를 Other, 나머지를 각 stem으로 분배 | Other가 이미 전체 잔여를 받으므로 최종 residual은 거의 0. 다른 조건에서는 누출을 재주입할 수 있음 | 기본 OFF. 합 일치 측정과 품질 개선을 구분 |
| synth에서 bass/drums를 빼서 신스 정책 보장 | 서로 다른 추정치가 중복되고 위상이 다를 수 있음 | 금지. 실제 오분류 사례를 먼저 수집 |
| Wiener/MISI가 반드시 먹먹함·warble 개선 | 소스 가정과 추정 품질에 의존. 기존 복소 출력의 정보를 바꿀 수 있음 | 후처리 OFF와 비교하는 별도 실험 |
| stem/mix 고역 에너지 비율로 고역 손실 자동 판정 | 원곡에는 다른 악기의 고역도 포함됨 | 진단 참고값. 정답 없는 파일에서는 손실/품질 점수로 표시하지 않음 |
| stem 간 상관으로 bleed 자동 판정 | 정상적인 유니즌, 공통 리듬도 상관이 큼 | 후보 구간 표시만. 정답 또는 청취로 확인 |
| 에너지 threshold로 악기 자동 숨김 | 작은 정상 연주를 제거할 수 있고 큰 누출을 통과시킬 수 있음 | 부재 대조군에서 검증 전 자동 숨김 금지 |
| 자동 metric gate로 raw보다 좋은 결과 선택 | 정답 없는 실제 곡에서는 fidelity를 확정할 수 없음 | 신호 무결성은 자동 검사, 품질 승격은 정답 평가와 청취 |
| Adobe/DeepFilterNet 등을 보컬 기본 경로로 추가 | 말소리와 노래·다성 코러스는 다른 적용 범위 | 노래/코러스/악기 기본 OFF |
| DiCoSe stem ID만 8종으로 변경 | 학습된 조건과 backbone/데이터가 다름 | 장기 재학습 연구. Mega53에 바로 연결하지 않음 |

## 1차 구현 범위: 세 악기 추출 검증

### 모델 준비

- 원본: [공식 Mega53 v1.0.21](https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.21).
- checkpoint SHA256: `c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f`.
- 설정 SHA256: `7e198062a251587088adb91215a4f44ab59e67bd62fcc805cf54d6e7dfc51103`.
- 기존 `docs/model-research-round2/official-mega53.yaml`을 기준으로 클래스 순서를 확인한다: acoustic index 1, electric index 16, synth index 38.
- shared tensor는 유지하고 `mask_estimators.1/16/38`을 `0/1/2`로 옮긴다. `num_stems=3`, 출력 순서는 acoustic/electric/synth로 고정한다.
- 공식 설정의 나머지 model 옵션을 변경하지 않는다. 잘못된 key, 누락 head, shape 오류는 변환 실패로 처리한다.
- 원본 hash, 설정 hash, 변환 규칙, 파생 hash를 함께 보존한다. 약 127MB라는 보고서 수치는 추정이며 실제 변환 전 보장하지 않는다.

제작자는 2026-09-25 공식 이슈에서 Mega53 가중치의 MIT 공개와 상업적 사용·재배포·변환 허용을 명시했다. 이 선언은 해당 모델에 관한 것이며 모든 커뮤니티 가중치의 조건으로 확대하지 않는다. [제작자 답변](https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/245).

### 동등성 및 자원 검증

공식 모델 selected-head 출력과 축소 3-head 출력에 동일한 입력·설정·precision을 사용한다. FP32에서 최대/평균 절대 오차를 기록하고, CUDA AMP는 별도 비교한다. FP32에서 head batch의 연산 순서 차이까지 고려해 허용 오차를 명시한다. 가중치 tensor 동일성만으로 전체 waveform 검증을 대체하지 않는다.

12GB GPU는 batch 1, 10초 chunk, 50% overlap부터 실측한다. 필요하면 5–6초로 줄이고, 안정적일 때 15–20초를 비교한다. 전체 53-head를 FP32로 GPU에 올릴 필요는 없다. 원본 선택 head 비교는 필요한 head만 유지하는 검증 인스턴스 또는 CPU 짧은 입력도 가능하되 어떤 경로로 비교했는지 기록한다.

기록: load/inference/전체 wall time, audio duration, RTF, chunk/overlap, precision, GPU, allocator peak allocated/reserved, 파일 크기. 짧은 음원은 전체 작업량을 줄이고 chunk는 순간 VRAM을 좌우한다. 파일 크기나 head 수만으로 속도를 주장하지 않는다.

### 입력과 품질 비교

먼저 원곡 입력과 보컬 제거 반주 입력을 비교한다. 기타 부모를 통한 재분리는 직접 추출이 실패한 구간의 비교군으로 추가한다. 이미 부모 단계에서 없어진 성분은 자식 분리기가 그대로 회복한다고 보장할 수 없다.

정답이 있는 비교군:

- 어쿠스틱만, clean/distorted 일렉만, 신스 pad/lead만.
- 두 기타 동시 연주, 피아노+신스, 일렉+신스, cymbal+distorted guitar.
- 대상 악기가 없는 음원, synth bass와 전자 드럼만 있는 음원.
- 스테레오·잔향·약한 연주·긴 sustain이 포함된 구간.

정답이 있는 파일에서는 target fidelity(SI-SDR, 다중 해상도 STFT 오차), 정답 기반 누출, 스테레오 변화를 측정한다. 대상이 없는 경우 SI-SDR 평균에 넣지 않고 출력 RMS와 입력 대비 에너지 비율을 별도 기록한다. MIDI 합성 자료의 성적은 실제 녹음의 성적으로 일반화하지 않는다.

실제 곡에서는 같은 구간, 같은 청취 레벨로 블라인드 A/B한다. 보존/누출/warble/attack/공간/전체 선호를 따로 기록한다. 정답 트랙이 없으면 추출률 90% 같은 수치를 산출하지 않는다. 예전 SPYAIR 실험 자료는 초기화 백업에 있으며 활성 회원 라이브러리로 자동 복원하지 않는다.

### 통합 조건

기타와 신스는 각각 평가한다. 한 클래스의 성공을 다른 클래스의 통과로 취급하지 않는다. 기본 모델 변경은 실제 검증 이후 진행한다.

- generic guitar 부모는 내부 비교용으로 남길 수 있지만 두 전용 기타와 함께 최종 합산하지 않는다.
- `other → synth` 이름 변경은 새 경로에서 제거하고 신스 모델 출력을 연결한다.
- 최종 나머지는 최종 표시 raw 트랙이 확정된 후 다시 생성한다. 이전 `remaining-v1.wav`를 새 결과에 재사용하지 않는다.
- 새 경로는 결과 layout/version을 구분하여 기존 `flatten_session()`의 재분류를 피한다.
- 보컬·코러스의 기존 단일 트랙 구조, 드롭다운 제거, 회원 소유권과 파일 접근 검사를 유지한다.
- 어쿠스틱 기타를 추가할 때 제안 순서는 보컬 → 코러스 → 피아노 → 신스 → 어쿠스틱 기타 → 일렉기타 → 베이스 → 드럼 → 나머지다. 이는 기존 8트랙에 새 클래스를 넣는 배치 제안이며, 이번 문서 작성에서 화면을 변경한 것은 아니다.
- 사용자가 삭제를 요청한 설명 알림을 다시 노출하지 않는다. 모델의 정확한 의미와 버전은 내부 metadata에 기록한다.

## 2차: 선택 후처리

새 모델의 raw 결과를 고정한 뒤 한 구간·한 기법씩 비교한다. 대형 processor 인터페이스나 여러 ONNX adapter를 먼저 만들지 않는다.

1. 공통 무결성: sample rate, stereo, frame 수, finite 값, peak, chunk 경계. 기존 검사를 재사용한다. sample peak와 true peak는 서로 구분한다.
2. 최소 진단: 구간별 RMS/crest, L/R 상관, M/S 비율, 고역 대역 에너지. 원본 비교 proxy는 실제 결함 판정이 아님을 metadata에서 구분한다.
3. Wiener: [Open-Unmix 공개 구현](https://github.com/sigsep/open-unmix-pytorch/blob/master/openunmix/filtering.py) 또는 Norbert 중 하나만 사용해 iterations 0/1/2를 비교한다. 서로 겹칠 수 있는 53출력 전체를 partition으로 가정하지 않는다. TF tensor layout, magnitude/power, residual 출력 개수는 실제 API에 맞춰 확인한다.
4. click/hum/잡음이 확인된 구간에만 기존 FFmpeg 등의 처리를 A/B한다. 드럼·기타의 정상 attack을 click로 지우지 않는다.
5. EQ는 남은 정보의 음색 조정으로 유지한다. 신스 denoise/dereverb, 코러스 mono화/강한 공간 제거, 나머지 일괄 cleanup은 기본 OFF다.

raw는 보존하고 처리본은 별도 저장한다. 파일 무결성 실패 시 raw로 돌아간다. 품질이 개선됐다는 자동 판정은 정답 기반 검증 없이 하지 않는다. 개별 raw stem에 limiter/정규화를 일괄 적용하면 gain과 재합성 관계가 바뀌므로 피한다. 재생·A/B용 gain은 export 원본과 구분한다.

## 3차 연구와 보류

- [DiCoSe 공식 구현](https://github.com/Russell-Izadi-Bose/DiCoSe)은 BS-RoFormer/MUSDB18와 U-Net/Slakh 실험을 제공한다. 유망한 refinement 연구지만 Mega53 세 악기와 리드/코러스에 바로 맞는 checkpoint라는 근거는 없다. 학습 데이터와 backbone 조건 확인 후 별도 환경에서 다룬다.
- [AudioSR](https://github.com/haoheliu/versatile_audio_super_resolution)은 고역 생성 비교 후보다. 생성된 음색이 원래 연주라는 보장은 없으며 현재 분리 artifact가 단순 low-pass 손상과 같지도 않다. 기본 OFF.
- Banquet 기타 query와 SAM Audio는 난해 구간 재추출 비교로 남긴다. 후보 라우터와 Judge를 항상 실행하는 시스템은 아직 만들지 않는다.
- Adobe/Auphonic/RX는 선택적인 외부 비교 도구다. 서비스 연동·유료 제품 도입·외부 음원 업로드는 이번 검토에 포함되지 않는다.
- 보고서의 GPU/RAM 추정치, A6000 속도, 일부 서비스 SDR 수치는 RTX3060 실측으로 사용하지 않는다. Mega53 서비스 표의 정확한 최신 값은 이번 웹 조회에서 다시 확보하지 못했으므로 배포 기준 숫자로 확정하지 않는다.

## 완료 기준 및 이번 검토 상태

첫 개발 묶음의 완료 기준은 **공식 원본 검증 → 3-head 변환 → 출력 동등성 확인 → 12GB 자원 측정 → 정답/부재/실제 곡 평가**다. 이후 통과한 클래스만 웹 기본 경로로 연결한다. 향상률이나 처리시간 목표는 baseline 실측 후 정한다.

이번 작업에서는 네 보고서 검토, 핵심 신규 라이선스 주장 확인, 기존 코드 대조, 실행 범위 정리를 완료했다. 새 가중치 다운로드·GPU 추론·기본 분석 모델 변경·DB 변경은 수행하지 않았다.
