# 라이선스 위험 수용 기록

이 문서는 **법률 자문이 아니다.** 소유자가 어떤 위험을 알고 감수하는지 남기는 기록이며, 라이선스가 완전히 확인되었다는 뜻이 아니다. 서비스 화면과 문서에서 이 가중치들을 "상업 사용 승인 완료"나 "commercial-ready"로 표현하지 않는다.

- 작성일: 2026-10-08
- 결정자: 프로젝트 소유자 (대화에서 직접 결정)
- 기준 문서: `docs/SIX_TRACK_IMPROVEMENT_PLAN_KO.md` 3절, `docs/COMMERCIAL_LICENSE_STATUS_KO.md`

## 1. 소유자 정책 (2026-10-08)

> 비상업이라고 명시된 것이 아니면 사용한다. 전체 포괄 적용이 아니어도 원본 소스가 MIT이고 가중치에 별다른 내용이 없다면 MIT로 간주한다.

적용 방식:
1. 가중치 배포 페이지(README, 모델 카드, Zenodo 등)에 비상업·연구 전용·MIT 제외 문구가 **있으면** 제외한다. 이 정책이 적용되지 않는다.
2. 그런 문구가 없고 원본 소스가 MIT이면 가중치도 MIT로 간주한다. 간주한 근거(URL, 확인일, 확인한 문구)를 아래 3절에 항목으로 적는다. 항목이 없는 가중치는 production에 올리지 않는다.
3. 출처가 불명확한(UNKNOWN) 체크포인트는 이 정책으로 구제하지 않는다.
4. 학습 데이터의 권리 위험은 가중치 라이선스와 별개이며, 항목마다 따로 적는다.

## 2. 현재 서비스에 쓰는 가중치

### 2.1 Mega53 파생 (core4, mega5, mega7, vocal2)

- 근거: `ZFTurbo/Music-Source-Separation-Training` issue #245의 저장소 소유자 댓글(2026-09-25)이 53-stem 가중치를 MIT로 배포한다고 밝혔고, 상업 사용을 포함한다고 확인했다. 우리 파생 체크포인트는 그 가중치에서 출력 헤드만 골라낸 것이다(bit-exact 검증).
- 단서(같은 댓글): 저자는 훈련에 쓴 오디오의 저작권을 전부 보유하지 않는다. 가중치는 "AS IS"이며 면책이 없다. 파생본을 저자가 직접 언급한 것은 아니다.
- **감수하는 위험**: 훈련 오디오 권리자가 모델 사용에 이의를 제기할 가능성, 면책 없음.
- 대상 해시: `separation/configs/commercial_approval.json` 참조.
- 재검토 조건: 저자 문구 변경, 이의·청구 발생, 저자가 훈련 데이터 목록을 공개하는 경우.

### 2.2 KJ Mel-Band RoFormer

- 근거: HF `KimberleyJSN/melbandroformer` README의 MIT 표기. 가중치에 별도 제한 문구는 확인되지 않았다.
- 소유자 결정: MIT로 간주하고 그대로 사용한다. 저자 문의는 선택 사항이다.
- **감수하는 위험**: 학습 데이터 내용 미확인, 재라이선스 이력 미확인.
- 재검토 조건: 저자가 제한을 명시하는 경우.

## 3. 정책으로 후보가 된 외부 가중치 (확인일 2026-10-08)

아직 서비스에 쓰지 않으며, 비교 대상 후보일 뿐이다. 실제로 쓰려면 정확한 체크포인트 파일과 SHA256을 이 표에 추가한다.

| 가중치 | 확인한 배포 페이지 | 확인한 내용 | 판정 | 학습 데이터 위험 |
|---|---|---|---|---|
| Open-Unmix `umxhq` | https://zenodo.org/records/3370489 | 라이선스 필드 "MIT License", 비상업 문구 없음 | 후보 | MUSDB18-HQ 학습. MUSDB 라이선스는 연구용 |
| Open-Unmix `umx` | https://zenodo.org/records/3370486 | 라이선스 필드 "MIT License", 비상업 문구 없음 | 후보 | MUSDB18 학습. 위와 같음 |
| Spleeter (코드 MIT) | https://github.com/deezer/spleeter | "The code of Spleeter is MIT-licensed." 사전학습 모델의 라이선스는 언급 없음. 비상업 문구 없음 | 후보-별도 위험(모델 라이선스 문구 없음, 정책 적용) | Deezer 내부 데이터, 비공개 |
| SCNet (코드 MIT) | https://github.com/starrytong/SCNet | 코드 MIT. 체크포인트는 Google Drive 링크이며 제한 문구 없음. "The model checkpoint was trained on the MUSDB dataset." | 후보-별도 위험(정책 적용, 배포처가 Google Drive) | MUSDB 학습. 연구용 데이터 위험 |

## 4. 이 정책으로 제외한 가중치

| 가중치 | 근거 | 판정 |
|---|---|---|
| Banquet / Query-Bandit 체크포인트 | https://zenodo.org/records/13694558 의 라이선스 필드가 "Creative Commons Attribution Non Commercial Share Alike 4.0 International"이다. 코드는 MIT이지만 가중치에 비상업이 명시되어 있다 | **제외** |
| Open-Unmix `umxl` | README: "the weights are only licensed for non-commercial use (CC BY-NC-SA 4.0)" | **제외** |
| Demucs 계열 전체 | 개발자가 가중치는 MIT가 아니며 과학적 목적으로만 제공한다고 밝힘(issue #327). 적용 범위가 특정되지 않아 전체 제외 | **제외** |
| 출처 불명 커뮤니티 체크포인트 (BS-RoFormer 변형, 드럼 전용 모델 등) | 원 배포자·라이선스 미특정 | **제외** (정책으로 구제하지 않음) |

## 5. 알려진 한계

- 배포 페이지를 읽은 것이며 원저자에게 서면 확인을 받은 것이 아니다.
- Google Drive 같은 개인 저장소 링크는 라이선스를 명시하는 곳이 아니어서, SCNet 가중치는 "문구 없음"에 의존한다.
- 모든 후보는 학습 데이터(MUSDB 등)의 연구용 제한 위험을 안고 있다. 소유자가 이를 알고 감수한다는 것이 이 문서의 내용이다.
- 이 기록은 법적 효력의 보증이 아니다. 서비스를 외부에 상업적으로 제공하기 전에는 별도로 전문가 검토를 받는 것을 권한다.
