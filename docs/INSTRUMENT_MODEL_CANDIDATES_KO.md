# 신디사이저·어쿠스틱·일렉기타 모델 후보 조사

조사일: 2026-10-06. 1차 문헌/공개 저장소 조사입니다. 다운로드·설치·실제 음원 추론은 수행하지 않았으며 기본 분석은 변경하지 않았습니다. 확인하지 못한 공개 가중치를 없다고 단정하지 않습니다.

**2차 조사로 결론 갱신:** 공식 MVSep Mega 53 Stems 공개 릴리스와 synth/acoustic-guitar/electric-guitar 출력, 소스별 파생 가중치를 확인했습니다. 아래 1차 결론은 조사 당시의 기록이며 현재 후보 우선순위는 `INSTRUMENT_MODEL_CANDIDATES_ROUND2_KO.md`를 참고합니다.

## 결론

세 가지 소스를 모두 고정 출력으로 제공하며, 공개 추론 코드·가중치·재현 가능한 성능까지 확인된 로컬 모델은 이번 조사에서 확보하지 못했습니다. Banquet는 기타 종류별 학습과 공개 가중치가 확인되어 로컬 기타 실험의 우선 후보입니다. 신스는 Banquet 논문 자체에서 성능 한계를 보고하므로 기본 신스 모델로 선정하지 않습니다. MVSEP는 목표에 맞는 전용 추출 기능이 있지만 공개 로컬 체크포인트 접근 여부는 미확인입니다.

## 후보 비교

| 후보 | 방식/대상 | 접근 확인 | 판단 |
| --- | --- | --- | --- |
| Banquet/query-bandit | 참고 오디오 기반. acoustic, clean electric, distorted electric 기타 세부 클래스 학습 | GitHub 코드, Zenodo 가중치 공개 | 기타 로컬 비교 1순위. 정확도와 RTX3060 실행은 미검증 |
| Banquet q:all | synth pad, synth lead, bass synth 등까지 확장 | 공개 ev 계열 가중치 존재. 파일과 설정의 정확한 대응은 설치 전 확인 필요 | 신스 연구 대조군. 논문이 약한 성능/불안정성을 보고하므로 기본 적용 보류 |
| MVSEP Synth/Acoustic/Electric | 서비스가 명시한 전용 대상+other 출력 | 공식 API 목록 확인. 해당 전용 모델의 공개 가중치 링크 미확인 | 서비스 결과 비교 후보, 로컬 모델 확보와 구분 |
| SAM Audio | 텍스트·시간 구간 기반 범용 대상 추출 | 공식 코드 및 모델 배포 페이지 있음. 접근 조건과 별도 환경 검토 필요 | 고정된 3개 악기 전용 모델이 아닌 재추출 후보 |
| SIREN-SEPARATE | other에서 query 오디오 기반 세부 추출. synth/guitar 지원 주장 | 모델 카드 있음. 연락처 공유 동의 필요. 카드 예제는 체크포인트 로드 수준 | 학습 클래스·완전한 추론 구현·성능 근거 부족으로 우선순위 낮음 |
| ACMID | acoustic/electric을 포함한 7개 악기 데이터 정제·분류 연구 | 공개 가중치는 Dasheng 기반 instrument cleaner의 MLP로 설명됨 | 바로 교체할 분리 모델이 아님. 학습 데이터 구축 후보 |

## Banquet 확인 사항

- 논문 q:vdbgp에는 acoustic guitar, clean electric guitar, distorted electric guitar가 명시됩니다. 일렉은 clean/distorted라는 세부 음색을 사용하므로 두 독립 출력의 단순 합이 일렉 전체와 정확히 같다고 보장하지 않습니다. 중복과 누락을 평가해야 합니다.
- q:all에는 synth pad/lead 및 bass synth 등이 포함됩니다. 논문은 새 long-tail 클래스의 SNR이 약하고, 해당 실험에서 5dB를 넘는 샘플이 없으며 일부 설정의 출력 붕괴도 보고합니다. 기타 추출 가능성을 신스 품질 증거로 일반화하지 않습니다.
- 공식 README는 `ev-pre-aug.ckpt`를 기본 추천합니다. Zenodo 크기는 645.5MB이며, 기타 중심의 `vdbgp-*` 변형도 존재합니다. 실제 설치 시 학습 설정과 체크포인트 구조를 대조해야 합니다.
- 입력은 원곡과 참고 오디오 파일입니다. 세 악기가 버튼 하나로 동시에 나오는 고정 3stem 모델이 아닙니다. 자동화하려면 버전이 고정된 참고 오디오 세트가 필요합니다.
- README의 batch=12 사례는 RTX4090 기준입니다. 현재 RTX3060 12GB에서는 batch=1과 짧은 구간으로 먼저 VRAM/시간을 측정해야 하며 실행 성공을 아직 보장하지 않습니다.
- 코드 MIT 표시와 가중치/훈련 데이터의 조건은 구분합니다. Zenodo 페이지의 가중치 권리 표기가 명확하지 않아 별도 확인 대상으로 둡니다.

## MVSEP 확인 사항

공식 API 목록에는 Synth(synth, other), Acoustic Guitar(acoustic-guitar, other), Electric Guitar(electric-guitar, other)가 있습니다. API상 sep_type은 각각 88/66/81입니다. 알고리즘 상세 페이지의 숫자와 API sep_type을 혼동하지 않습니다.

신스는 원곡 또는 반주에서 추출, 기타는 원곡 또는 기타 부모 트랙에서 추출하는 옵션이 있습니다. Synth 정의는 synth bass, synth percussion, synth FX 등까지 포함하므로 현재 베이스·드럼 분류와 중복될 수 있습니다. API 기능이 존재한다는 사실은 공개 가중치나 학습 데이터·로컬 실행을 입증하지 않습니다. 이번에는 파일을 업로드하거나 API 작업을 생성하지 않았습니다.

## 검증 대상으로 선정할 범위

1. 기타: Banquet acoustic/clean electric/distorted electric 참고 오디오 조건 비교. 원곡/반주 직접 추출과 기타 부모 재분리를 비교합니다.
2. 신스: 공개 고정 출력 가중치는 아직 선정하지 않음. Banquet q:all을 대조군으로 두고 SAM Audio의 시간 구간 조건 추출을 비교 후보로 둡니다. 서비스 이용을 선택한다면 MVSEP 전용 신스도 비교할 수 있습니다.
3. 평가 음원: 어쿠스틱만 존재, 일렉만 존재, 두 기타 동시 존재, 신스만 존재, 신스+기타, 목표 악기가 없는 구간. 정답 stem이 있는 자료와 실제 음악을 구분합니다.
4. 평가: 목표 보존, 다른 소스 누출, 아티팩트, 스테레오 보존, 목표가 없을 때의 잘못된 추출, 추론 시간/VRAM. 현재 모델보다 개선되기 전에는 기본 분석에 넣지 않습니다.

UI 분류를 위해 신스 베이스는 베이스에, 신스 드럼은 드럼에 우선 포함하고 신스는 선율·패드 중심으로 정의하는 방안을 제안합니다. 이는 모델이 자동으로 보장하는 구분이 아니며 학습/평가 정의가 필요합니다.

## 1차 출처

- [Banquet 공식 코드](https://github.com/kwatcharasupat/query-bandit)
- [Banquet 논문: 기타 세부 클래스와 신스 성능 한계](https://arxiv.org/html/2406.18747v2)
- [Banquet 공식 가중치](https://zenodo.org/records/13694558)
- [MVSEP 공식 알고리즘 설명](https://mvsep.com/en/algorithms)
- [MVSEP 공식 API 대상·옵션](https://mvsep.com/en/full_api)
- [SAM Audio 공식 코드](https://github.com/facebookresearch/sam-audio)
- [SIREN-SEPARATE 모델 카드](https://huggingface.co/hilarl/siren-separate)
- [ACMID 공식 코드/가중치 설명](https://github.com/scottishfold0621/ACMID)
