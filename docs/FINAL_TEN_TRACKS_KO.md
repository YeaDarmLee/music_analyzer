# 최종 10트랙 분석

적용일: 2026-10-06. 사용자가 승인한 어쿠스틱/신디사이저와 Orange 현악 후보를 기본 웹 분석에 연결했다.

## 최종 순서

보컬 → 코러스 → 피아노 → 신디사이저 → 스트링 → 어쿠스틱기타 → 일렉기타 → 베이스 → 드럼 → 나머지.

원본 음원은 비교용 reference로 별도 유지한다. 브라스 전용 트랙은 구성에서 제외했으며 나머지 신호에 남는다. 브라스를 신디사이저에서 단순 차감하지 않는다.

## 실제 추출 경로

1. 기존 확정 보컬 RoFormer로 원곡의 보컬과 반주를 추출한다.
2. 반주를 기존 6-source BS-RoFormer에 넣고 피아노·베이스·드럼만 최종 트랙으로 선택한다.
3. 분리된 반주를 `bs_roformer_mega4`에 넣어 acoustic-guitar(index 1), electric-guitar(16), synth(38), bowed_strings(7)를 함께 추출한다. encoder는 네 출력이 공유한다.
4. 보컬을 기존 BS karaoke 모델에 넣어 보컬·코러스로 구분한다.
5. 악기 7개 raw 트랙의 합을 분리된 반주에서 빼 나머지를 만든다. 보컬·코러스는 이 계산에서 제외한다. 모든 출력의 sample rate/stereo/frame 수를 검사한다.
6. 나머지에 CLAPSep의 승인된 지속 화음 신디 조건을 적용한다. 피아노·어쿠스틱기타·일렉기타·베이스·드럼을 텍스트 제외 조건으로 지정한다. 추출분을 신디에 더하고 나머지에서 빼며, 합계 보존을 검증한다. 보완 실패 시 분석을 실패로 표시해 미완료 결과를 완료로 제공하지 않는다.
7. 신디 보완 이후 나머지에서 지속음을 연주하는 bowed orchestral strings를 추가 추출한다. 피아노·신디사이저·어쿠스틱기타·일렉기타·베이스·드럼을 제외 조건으로 지정한다. 추출분은 스트링에 더하고 나머지에서 빼며 신디 트랙은 변경하지 않는다.
8. 악기 7개와 최종 나머지의 합계가 분리된 반주와 일치하는지 검증하고 무음 트랙 표시를 판정한 뒤 저장한다.

학습을 새로 수행한 모델이 아니라 공식 Mega53의 네 head를 보존한 파생 모델이다. 기존 broad strings head는 사용하지 않는다. 출력 클래스가 서로 완전히 배타적이라는 보장은 없으며 사용자의 현재 청취 승인을 기준으로 채택했다.

## 화면과 파일

- 웹/업로드 API의 기본 분석 값은 `final_10`이다.
- 모델 선택 드롭다운을 제거했다. 업로드 후 같은 구성으로 분석한다.
- 새 트랙도 볼륨·mute·solo·파형·선명도·개별 WAV·전체 ZIP 기능을 사용한다.
- 내부 family는 `lead`, `backing`, `piano`, `synth`, `strings`, `acoustic_guitar`, `guitar`, `bass`, `drums`, `other` 순서다.
- `strings`는 `bowed_strings`, `guitar`는 `electric-guitar` 원본 파일을 참조한다.
- 기존 `other → synth` 재분류는 새 분석에서 제거했다.
- 새 결과는 `flat_v3`이며 나머지 파일은 `remaining-v3.wav`다. 이전 결과의 나머지 캐시를 재사용하지 않는다.
- 보완 이후 신디/나머지는 `synth-recovered-v2.wav`, `other-recovered-v2.wav`를 사용한다. 변경된 SHA를 기준으로 재생·선명도·ZIP 캐시를 갱신한다. 기존 파일과 `record-before-synth-recovery-v2.json`은 복구용으로 보존한다.
- 회원 소유권 검사와 기존 분석은 유지한다. 이미 분석한 곡에 새 구성을 적용하려면 새 분석을 실행한다.
- 기존 `final_10` 미라클·사무라이 하트 결과에는 승인된 신디 보완을 적용했다. 이전 6트랙 분석은 그대로 유지한다. 회원 DB와 소유권은 변경하지 않는다.

## 모델 준비와 실행

최초에 공식 Mega53 원본이 없다면 연구 모듈의 prepare를 실행한 뒤 최종 모델을 준비한다.

```powershell
.\.venv\Scripts\python.exe -m music_analyzer.mega53_experiment prepare
.\.venv\Scripts\python.exe scripts/prepare-final-instruments.py
.\scripts\start-web.ps1
```

기존 로컬에는 최종 모델과 registration을 생성해 실제 적용했다. 가중치의 전체 hash, 설정 hash, 코드 revision 및 vendored 파일 hash를 검증하는 기존 runner를 사용한다. 10초 chunk / 50% overlap / batch 1 / AMP FP16이며 OOM 시 5초 chunk로 재시도한다.

## 검증

- Python 관련 테스트 68개 통과: 새 10트랙 순서·raw 연결·나머지 재합성·신규 트랙 후처리, 웹 파일/다운로드, 회원 접근 검사, RoFormer 계약 검증을 포함한다.
- 프런트 재생/믹싱 테스트 7개 통과, Vite production build 성공.
- 실제 GPU로 Orange 8–28초를 새 네 단계 경로 전체에 넣어 10개 WAV를 생성했다. 882,000 frames / 44.1kHz stereo / finite 값 유지, ZIP에 10개 WAV 포함을 확인했다.
- 원곡 대비 10트랙 재합성의 최대 절대 오차는 `2.947165966826759e-08`이다. 재합성 일치는 개별 트랙의 완벽 분리 증거가 아니다.
- 실측 smoke 결과는 `data/part-studies/final10-smoke/verification.json`에 있다. 테스트 라이브러리는 회원 DB를 변경하지 않는다.
- 웹 서버를 재시작하고 `http://127.0.0.1:8780/`의 HTTP 200 응답 및 빌드의 새 기본 분석 값을 확인했다.

2026-10-07 변경: 새 분석의 모든 악기는 반주를 입력으로 사용한다. 악기 7개+나머지의 합계가 분리된 반주와 일치하는지 검증한다. 기존 완료 결과는 이전 버전으로 보존하며 새 방식 적용은 재분석으로 수행한다. 보컬·코러스까지 합친 결과가 원곡과 정확히 일치한다는 보장은 하지 않는다.

스트링 보완 추가: `instrumental-with-strings-v4`. 같은 설치된 CLAPSep 환경을 사용하며 신디 → 스트링 순차 실행이다. 스트링 보완은 별도 manifest와 백업에 기록한다. 신디 보완 파일은 `synth-synth-recovered-v2.wav`, 이후 스트링과 나머지는 `strings-strings-recovered-v1.wav`, `other-strings-recovered-v1.wav`이다. 이전 완료 결과는 자동 변경하지 않는다. 텍스트 제외 조건은 유입의 완전 차단을 보장하지 않으며 실제 곡에서의 품질은 청취로 확인해야 한다.
