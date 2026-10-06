# 분홍신 브라스 24–60초 비교

실행일 2026-10-07. 최신 완료 분석 `analysis_d02be493cd3444e8ad3d2c5a87f55659`를 읽어 반주·신디·스트링·나머지를 비교했다. 회원 기록과 서비스 모델은 변경하지 않았다.

실행: `scripts/study-brass.py`의 prepare → mega → clap → build. 결과: `data/part-studies/brass-red-shoes/comparison.html`.

## 실제 추론

- 공식 Mega53 원본 SHA 검증, brass index 8 확인, 헤드 보존 후 strict load. 반주와 현재 나머지 각각에서 전용 brass를 추론했다.
- CLAPSep 일반 brass/trumpets/trombones/French horns, 짧은 brass hits, 지속음의 세 조건을 반주·현재 나머지·Mega53 나머지 추출 후의 잔여·오렌지 반주에 적용했다.
- 제외 조건은 piano, electronic synthesizer, bowed strings, acoustic guitar, electric guitar, bass, drums and singing이다. 추가 다운로드나 외부 음원 전송 없이 핀된 로컬 모델과 캐시를 사용했다.
- 나머지 입력 Mega53 추출분+그 이후 잔여의 CLAPSep 추출분으로 결합 후보를 만들었다. 결합분과 보완 후 나머지의 합계 검증 최대 오차는 세 후보 모두 7.45e-9이다. 이는 악기 품질 검증이 아니다.
- 현재 신디·스트링 보완 단계에서 브라스가 이미 다른 트랙으로 옮겨졌을 수 있어, 현재 나머지만 처리하는 결합 후보는 전체 브라스 복원을 보장하지 않는다. 서비스 기본 추출 단계의 brass 추가는 아직 하지 않았다.

## 성능 및 부재 대조군

Mega53 36초 반주 5.88초, 나머지 5.58초, 모델 최대 할당 0.81GiB. CLAPSep는 각 조건 0.77–1.95초이며 모델 로딩은 별도다.

오렌지 9–29초는 사용자가 브라스가 없다고 특정한 대조군이다. 전용 brass RMS 0.000101, CLAPSep RMS 약 0.197–0.208이었다. 오렌지 반주 RMS는 0.324다. 음량은 악기 정체성의 증거가 아니지만, 부재 구간에서 큰 출력이 나오는 CLAPSep 후보는 오검출 가능성이 높아 단독 서비스 적용을 보류한다. 전용 출력도 부재 구간 출력이 작다는 사실만으로 분홍신 브라스 품질이 입증되지는 않는다.

청취 우선 대상은 `Mega53 브라스 · 반주 입력`이다. 실제 브라스 유지, 신디·스트링과의 중복, 기타·드럼·보컬 유입을 확인한 뒤 기본 brass 헤드를 현재 반주 모델에 추가할지 결정한다. 청취 게인은 최대 4배이며 원시 출력은 보존했다.
