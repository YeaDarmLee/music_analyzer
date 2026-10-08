# 실제곡 드럼 진단 (basic_6 · commercial_6 · commercial_13) — 2026-10-08

진단만 한 문서다. 파이프라인은 수정하지 않았고, 이후 별도 연구 루프도 시작하지 않는다. 알려진 한계(known limitation)로 남기고,
실서비스에서 직접 들어 본 뒤 개선 우선순위를 정한다.

## 입력과 방법
- 곡 6개(`song/`), 곡마다 가장 시끄러운 40초(곡의 20–80% 구간). 세 pipeline이 **같은 `clip.wav`** 를 입력으로 사용했다.
- 레벨·에너지 분석은 모두 정규화 전 raw stem(`data/listening/raw/<song>/<preset>/`)과 `bs_roformer_core4` 단계 출력(`core4raw_*`)을 읽었다.
  청취용 `blind/` 파일(RMS 보정·A/B 섞임)은 분석에 쓰지 않았다. 이전 `analyze-listening-package.py` 결과도 `raw/`를 읽었으므로
  **무효가 아니다**(INVALID 아님). 다만 이 문서의 수치는 `analyze-drum-transfer.py`로 다시 계산한 값이 기준이다.
- 기준 신호는 basic_6의 drums다. 이 곡들에는 정답(GT)이 없으므로 모든 수치는 **상대 비교**이며 SDR이 아니다.
- 이동량은 기준 drums를 각 시스템의 모든 stem에 동시에 최소제곱 회귀한 뒤 stem별 설명 에너지 비율로 계산했다(합이 1−잔차).
- 산출물: `docs/DRUM_TRANSFER_RESULTS.json`, `docs/LISTENING_PROXY_RESULTS.json`.

## 결과
drums 레벨(원곡 대비 dB) — 단계별:

| 곡 | basic drums | C6 core4 | C6 final | C13 core4 | C13 final | 주 이동처 |
|---|---:|---:|---:|---:|---:|---|
| s01 | −5.6 | −17.0 | −17.0 | −17.0 | −17.0 | other |
| s02 | −5.3 | −23.9 | −23.9 | −23.9 | −24.1 | other |
| s03 | −6.1 | −26.1 | −26.1 | −26.1 | −26.2 | other |
| s04 | −9.3 | −20.5 | −20.5 | −20.5 | −20.5 | other |
| s05 | −4.3 | −31.9 | −31.9 | −31.9 | −31.9 | other |
| s06 | −5.1 | −29.2 | −29.2 | −29.1 | −29.7 | other |

basic drums 에너지가 어디로 갔는가(%, 전대역):

| 곡 | drums→drums C6 / C13 | drums→other C6 / C13 | drums→percussion C13 | drums→기타 C6 / C13 |
|---|---:|---:|---:|---:|
| s01 | 8.5 / 8.4 | 82.4 / 87.6 | 0.1 | −0.5 / 1.5 |
| s02 | 4.0 / 3.5 | 81.6 / 89.0 | 0.3 | −0.9 / −0.8 |
| s03 | 3.4 / 2.9 | 77.8 / 85.2 | 1.7 | −0.3 / −0.4 |
| s04 | 18.6 / 16.5 | 71.1 / 75.3 | 1.4 | −0.1 / 2.9 |
| s05 | 1.0 / 1.0 | 97.9 / 97.7 | 0.0 | −0.1 / 0.0 |
| s06 | 2.2 / 2.2 | 93.1 / 93.6 | 1.4 | −0.4 / 0.0 |

- 대역별(6곡 평균, C6): 20–80 Hz drums 2.6 / other 96.7, 80–200 Hz 10.3 / 86.4, 200–2k 12.8 / 54.2, 2k–8k 7.1 / 78.1, 8k+ 2.5 / 94.7.
  C13에서 8k+ 중 percussion으로 가는 몫은 8.8%뿐이다(심벌이 percussion으로 회복되지 않는다).
- 2초 창(곡당 20개): C6에서 drums가 기준의 50%도 설명하지 못하는 창이 s04 12개, 나머지 곡은 19–20개다.
- core4 drums가 commercial_13 후처리를 지난 뒤: drums 93–100%에 남고 percussion으로 가는 몫은 최대 1.8%다.
- commercial_6의 final drums는 core4 raw drums와 비트 단위로 같다. commercial_13의 core4 drums 레벨은 commercial_6과 같지만
  비트 단위로는 같지 않다(부동소수점 비결정성으로 보이며 레벨 차이는 없다).
- 합계 보존: 세 시스템 모두 stem 합이 원본과 일치한다(`partition_err`는 JSON 참조).

## 판단: C — commercial_6/13 공통 core4 문제
- 손실은 `bs_roformer_core4` 단계 출력에서 이미 발생한다. 후처리(13트랙)가 만든 추가 손실은 레벨 기준 0.0–0.6 dB이다.
- 놓친 drums는 사라지지 않고 `other`로 들어간다(에너지 71–98%). `commercial_13`의 percussion·cymbal 경로는 이를 회복시키지 못한다.
- 합성 10-case의 drums −2.2 dB와 달리 실제곡은 −11 ~ −28 dB다. 평균적 품질 하락이 아니라 **도메인 불일치**다.
- 원인 후보(가설, 확정 아님): 6곡이 모두 라우드니스가 큰 상용 마스터(RMS −7 ~ −12 dBFS)이고, core4의 drums head가 이런 믹스에서
  약하다. 표본이 6곡이라 조건별로 원인을 분리하지는 못했다. 같은 곡에서 basic_6 drums는 정상 수준이므로 입력 문제는 아니다.
- 추정이 아닌 사실: drums 에너지가 other로 이동했고 그 합은 보존된다 → 이후 "other 안의 drum 성분을 drums로 되돌리는" 합 보존형
  복원이 가능한 구조이다. 이번 단계에서는 구현·연구하지 않는다.

## Known limitation (서비스 반영)
- 6트랙·13트랙의 drums는 실제 곡에서 크게 약하거나 비어 있을 수 있고, 그 신호는 "추가 반주(other)"에 들어 있다.
- piano·bass·guitar는 같은 비교에서 레벨 차이가 작았다(piano 심벌 대역 −6 dB, guitar −1.3 dB, bass 거의 동일, vocals 동일).
