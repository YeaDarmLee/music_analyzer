# 악기 모델 2차 조사

조사일: 2026-10-06. 기본 분석 모델 변경, 가중치 다운로드, GPU 추론은 수행하지 않았습니다. 작은 설정 파일과 공개 API 메타데이터를 읽고 저장하여 검증했습니다.

추가 검토: 네 외부 리서치 보고서를 현재 코드와 대조한 실행안은 [리서치 종합 실행안](RESEARCH_REPORTS_IMPLEMENTATION_PLAN_KO.md)에 정리했습니다. Mega53 가중치에 대해서는 제작자의 2026-09-25 [공식 MIT 공개 답변](https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/245)을 확인했습니다. 아래의 가중치 사용조건 미확정 문구는 이 추가 근거와 함께 읽어야 하며, 다른 모델의 가중치 조건까지 확정한 것은 아닙니다.

## 1차 조사 정정

1차 조사에서 공식 MVSep Mega 53 Stems 릴리스를 놓쳤습니다. 신스·어쿠스틱 기타·일렉기타를 명시적인 출력 클래스로 갖는 공개 가중치가 존재하므로, 이번에는 Mega53을 직접적인 로컬 검증 1순위로 올립니다. Banquet는 참고 오디오 방식의 비교 후보로 유지합니다. MVSEP 서비스의 최신 독립 전용 모델과 Mega53 공개 모델은 동일 모델이라고 단정하지 않습니다.

## 공식 모델 확인

- 배포: ZFTurbo/Music-Source-Separation-Training release `v1.0.21`, 2026-04-20.
- 이름: MVSep Mega 53 Stems, BS-Roformer.
- 출력에 `acoustic-guitar`, `electric-guitar`, `synth`가 포함됩니다. 기타·키·신스 등 일부 출력은 서로 겹칠 수 있으며 53개 전체 합이 원곡과 일치하는 분할은 아닙니다.
- 공식 가중치: `mvsep_mega_model_bs_roformer_53_stems_v1.ckpt`, 1,368,919,887 bytes. 공식 SHA256: `c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f`.
- 공식 설정 파일 SHA256 `7e198062a251587088adb91215a4f44ab59e67bd62fcc805cf54d6e7dfc51103`을 실제 다운로드 후 검증했습니다.
- 개발자는 배치 1에서도 메모리 소모가 크며 16GB 이상 VRAM을 권장합니다. 현재 RTX3060 12GB에서 원본 전체 53출력의 기본 실행을 보장하지 않습니다.
- 개발자는 일부 소스 품질이 MVSEP 서비스의 독립 전용 모델보다 낮을 수 있다고 설명합니다. 출력 종류의 증가가 품질 향상의 증거는 아닙니다.

## 소스별 파생 모델 확인

Hugging Face `noblebarkrr/BS-Roformer-MVSep-Mega-53-stems`는 원본을 소스별 단일 출력으로 나눴다고 설명합니다. 공식 제작자의 원본 릴리스와 제3자 파생 배포를 구분합니다.

확인한 revision: `0677941f9cdfd891a6bc3336229244e197035327`.

| 대상 | 파일 | 크기(bytes) | 공식 클래스 index (0부터) |
| --- | --- | ---: | ---: |
| 신스 | `v1/bs_mega_53stem_synth_mvsep.ckpt` | 77,616,988 | 38 |
| 어쿠스틱 기타 | `v1/bs_mega_53stem_acoustic-guitar_mvsep.ckpt` | 77,624,038 | 1 |
| 일렉기타 | `v1/bs_mega_53stem_electric-guitar_mvsep.ckpt` | 77,624,038 | 16 |

세 YAML의 training.target_instrument는 각 대상이며 model.num_stems=1입니다. 공식 모델 설정과 실제 비교한 결과 model 섹션의 차이는 num_stems=53→1뿐이었습니다. 44.1kHz stereo, dim256/depth12, batch1입니다. 배포 inference.chunk_size는 882000 frames(20초), num_overlap=2입니다. 이 설정은 우리가 검증하여 채택한 실행 프리셋이 아닙니다.

크기가 작다는 것만으로 GPU 실행 성공이나 품질을 보장하지 않습니다. 가중치를 실제로 받지 않았으므로 encoder 동일성, 출력 head 대응, tensor shape, 정확한 원본 출력과의 일치를 아직 확인하지 않았습니다. 새로운 악기 전용 데이터로 별도 학습한 모델이라고도 주장하지 않습니다.

## 현재 프로젝트와 호환성

현재 로컬 BS-Roformer 구현은 output head가 별도 ModuleList이며 forward의 active_stem_ids 인자로 일부 head만 선택할 수 있습니다. 이를 활용해 원본에서 목표 3개만 추론하는 경로가 가능할 것으로 판단합니다. 다만 원본 가중치 strict load, 해당 클래스 순서, 설정 호환성을 실제 검증해야 합니다.

두 실행 경로를 비교할 수 있습니다.

1. 공식 원본을 로드해 필요한 3개 head만 사용: encoder를 공유할 수 있어 3개 단일 모델을 따로 실행하는 것보다 계산량을 줄일 가능성이 있습니다. 전체 가중치 메모리 문제는 별도이며 아직 실측하지 않았습니다.
2. 소스별 파생 모델을 순차 실행: 초기 다운로드와 메모리 부담이 작을 가능성이 있습니다. encoder 계산을 반복하며 출력의 공식 원본 일치 여부를 검증해야 합니다.

실제 통합 전에는 공식 원본에서 직접 head를 뽑아 만든 소형 모델과 파생 파일을 비교하는 것이 가장 명확합니다. 이는 가중치 학습을 추가하는 방식이 아니라 불필요한 출력 head를 제외하는 방식입니다. 코드·가중치 사용조건도 별도 확인합니다.

## 추천 검증 순서

1. 세 소스별 모델의 안전한 가중치 로드와 체크섬·키·shape 검증. torch.load(weights_only=True), strict load를 우선합니다.
2. 10초 청크/batch1부터 GPU peak memory와 wall time 측정. 짧은 전체 음원만 선택하고 청크가 20초로 고정되어 있다면 순간 VRAM이 줄지 않으므로 모델에 들어가는 청크도 함께 관리합니다.
3. 정답 트랙이 있는 혼합으로 각 대상의 보존/누출을 평가하고, 목표가 없는 대조군을 반드시 포함합니다.
4. 실제 곡에서는 원곡/반주 직접 추출과 기존 other/guitar 재분리를 비교합니다. 신스는 other 안에만 있다고 가정하지 않습니다.
5. 원본 가중치의 동일한 3개 head 결과와 비교하여 파생 모델 출력을 검증합니다.
6. 품질이 확인되기 전에는 현재 기본 분석을 교체하지 않습니다. 신스·기타 후보는 겹칠 수 있으므로 기존 기타 부모와 두 기타 자식을 함께 최종 믹스에 넣지 않습니다.

## 후보 우선순위

| 우선순위 | 후보 | 목적 |
| --- | --- | --- |
| 1 | Mega53 공식 모델의 대상 head / 소스별 파생 모델 | 명시적 신스·어쿠스틱·일렉 추출의 직접 검증 |
| 2 | Banquet 기타 세부 클래스 모델 | 참고 음원 조건에서 기타 분리 비교 |
| 3 | SAM Audio | 시간 구간을 지정한 어려운 대상 재추출 비교 |
| 서비스 비교 | MVSEP 최신 전용 모델 | 공개 Mega 모델과 서비스 품질을 구분한 외부 대조군 |

Banquet의 체크포인트별 정확한 학습 설정 대응은 이번에 새로 입증하지 않았습니다. 이전의 기타 관련 학습 클래스와 가중치 배포 확인을 그대로 유지합니다. SIREN과 ACMID의 우선순위도 변경하지 않습니다.

## 저장한 증거와 출처

`docs/model-research-round2/`에 공식 YAML, 3개 파생 YAML, revision·LFS 크기·SHA256 메타데이터를 저장했습니다. 가중치는 없습니다.

- [공식 릴리스](https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.21)
- [공식 파일 및 SHA256](https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/expanded_assets/v1.0.21)
- [소스별 파생 배포 설명](https://huggingface.co/noblebarkrr/BS-Roformer-MVSep-Mega-53-stems)
- [파생 파일 목록](https://huggingface.co/noblebarkrr/BS-Roformer-MVSep-Mega-53-stems/tree/main/v1)
- [공식 MSST 코드](https://github.com/ZFTurbo/Music-Source-Separation-Training)
