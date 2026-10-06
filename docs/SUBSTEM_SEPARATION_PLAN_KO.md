# 2차 세부 트랙 분리 계획

브랜치: feature/substem-separation / 기준 커밋: 86da3e6

## 목표와 적용 범위

기존 원곡 → 확정 보컬 → 반주 악기 5개 흐름에 선택 실행하는 2차 분리를 추가한다. 입력은 선명도 EQ 적용 전 FLOAT WAV다. 기존 결과는 덮어쓰지 않으며 별도 실험 결과로 저장한다. 원본 분리 품질과 2차 분리 품질을 구분한다.

| 분야 | 첫 목표 | 어려운 범위 | 우선순위 |
|---|---|---|---|
| 보컬 | 리드 보컬 + 잔여/코러스 후보 | 동시 가창자별 보컬 1·2·3, 더블링·리버브와 실제 코러스 구분 | 1 |
| other | 스트링 또는 신스/패드 목표 추출 + 잔여 | 비슷한 음색의 스트링 패드와 실제 현악기, 여러 프롬프트 중복 | 2 |
| 기타 | 리드 기타 또는 리듬 기타 목표 추출 + 잔여 | 같은 톤으로 겹친 기타, 같은 연주의 L/R 더블링 | 3 |

소리가 사람별/악기별로 분리된다고 보장하지 않는다. 특히 L/R 나누기, 주파수별 자르기, 기존 6-stem 재실행을 실제 연주 파트 분리로 이름 붙이지 않는다. 잔여 파일은 다른 악기만 있는 정답이 아니라 원입력에서 추정 목표를 뺀 파일이다.

## 모델 후보

- 리드/코러스: karaoke 전용 RoFormer 후보를 MSST 호환 설정과 함께 조사한다. vocals/instrumental 모델을 lead/backing 모델로 오해하지 않는다. 목표 레이블, 원본 설정, 체크포인트 해시, 가중치 라이선스를 확인한 뒤 등록한다. Mel-Band 및 BS-RoFormer Karaoke 비교 실행 완료.
- other/기타: AudioSep 공식 구현은 텍스트 질의 분리와 32kHz, chunk 추론을 제공한다. 입력·출력을 44.1kHz stereo 타임라인으로 변환하고 지연·길이·모노 출력을 명시적으로 다룬다. 같은 종류 여러 연주자를 구분하는 보장은 없다. 코드 MIT와 다운로드 가중치 허가는 따로 검토한다.
- 대안: SAM-Audio는 text/time span 프롬프트 후보다. SAM License와 접근 조건을 확인해야 하며 기존 MIT 모델로 취급하지 않는다. 기본 환경에 바로 설치하지 않는다.

자료: https://github.com/Audio-AGI/AudioSep
https://github.com/facebookresearch/sam-audio
https://github.com/facebookresearch/sam-audio/blob/main/LICENSE
https://github.com/ZFTurbo/Music-Source-Separation-Training

## 개발 단계 및 완료 기준

1. B1 실험 계약/입출력 기반: 10–30초 WAV 구간 준비, 부모 파일 해시·시작 프레임·타임라인 기록, 모델 추정 결과 검증·목표/잔여 저장. 빈 파일·NaN·길이/샘플레이트 불일치 거부. 모델 미실행을 성공으로 표시하지 않는다.
2. B2 모델 선정/격리 실행: 리드/코러스 후보 1개 및 AudioSep 후보 1개를 별도 실험 환경에 설치. 코드 revision·config hash·weight hash·코드/가중치 라이선스 기록. RTX3060 12GB에서 10초 실행으로 메모리·시간 측정 후 30초로 확장. 기존 서비스 가상환경의 torch 버전을 변경하지 않는다. GPU 작업은 기존 supervisor/GPU lock과 연계한다.
3. B3 청취 평가: 대상 소리가 실제 존재하는 구간, 다른 소리와 겹치는 구간, 대상이 없는 구간을 각각 비교. 음량 일치 A/B, 목표 누락·잔여 누출·수중음·새 잡음·경계 클릭을 기록한다. 재합산 오차는 무결성 지표이며 분리 정확도로 표시하지 않는다. 사람이 3종 구간 모두 청취 승인하기 전에는 모델을 기본 엔진으로 채택하지 않는다.
4. B4 전체 곡: overlap/crossfade 구간 합성, 전체 시작점·프레임 수·스테레오 유지, OOM 취소/재시도, 같은 입력/설정 중복 캐시. 잔여에 여러 목표를 차례로 적용해 중복을 줄이되 순서 의존성을 비교한다.
5. B5 DAW: 부모 트랙 아래 접을 수 있는 하위 트랙 그룹. 부모/자식 이중 재생 방지, 세부 분리 모달(대상·구간·모델), 진행률·취소·실패, 원본/자식 비교, 별도 ZIP. 기타 번호는 결과가 검증된 뒤 사용자 이름으로 붙인다.

## 실험 데이터 계약

실험 폴더 data/separation/substems/experiment_<uuid>/ 에 manifest.json, input.wav, target.wav, residual.wav를 저장한다. PREPARED는 입력 구간 준비만 완료된 상태다. CANDIDATE_READY는 외부 모델 결과를 가져온 상태이며 quality_improvement_verified=false다. 재학습/모델 실행 완료와 혼동하지 않는다. 결과 입력은 정확히 같은 44.1kHz stereo 프레임 수를 요구하며 임의 padding·채널 복제·자동 지연 정렬은 하지 않는다. 모델 어댑터에서 변환을 검증한 뒤 제출한다. 품질이 부족하면 원본 트랙을 그대로 유지한다.

## 이번 작업의 범위

B1 기반 및 리드/코러스 B2–B4 연결을 구현했다. other/기타는 AudioSep 20초 실험 추론과 기존 DAW 결과 표시까지 검증한다. 전체 곡 자동 처리와 선택 모달은 청취 평가 후 진행한다. 모델 접근 동의가 필요한 후보는 사용자가 약관 동의를 직접 완료한 뒤 진행한다.

## 실행 예시

```powershell
.\.venv\Scripts\python.exe -m music_analyzer.substem_experiment prepare --input 'C:\audio\vocals.wav' --task vocals --start 20 --duration 20
.\.venv\Scripts\python.exe -m music_analyzer.substem_experiment publish --experiment-id experiment_출력ID --estimate 'C:\audio\lead_estimate.wav' --model-id 후보명 --prompt 'lead singing voice'
```

publish는 이미 실행한 모델의 추정 WAV를 가져오는 명령이며 자체적으로 AI 추론을 하지 않는다. target/residual을 새 결과로 저장할 뿐이며 보컬·기타·스트링이라는 의미를 자동으로 검증하지 않는다.

## 리드/코러스 구현 진행

2026-10-05: becruily/mel-band-roformer-karaoke를 별도 DEV_ONLY 후보로 등록했다. 가중치 허가는 UNKNOWN이며 공개 배포·상용 채택 승인을 의미하지 않는다. revision 0c149975cfaa261c7d87baf54330a9da85bcf888, SHA256 d3aa262ac01df870b9fc033e9c7b6cad33fe04fc9c148b6c40841326a515a0e0 고정. 원본 설정의 Vocals/Instrumental 출력을 보컬 입력에서 lead/backing 후보로 표시한다. 실제 보컬 20초 구간 CUDA 실행과 FLOAT stereo 길이/해시 검증 성공. 기타·other와 다중 가창자 분리는 아직 구현하지 않았다.

웹 상세의 보컬 세부분리 버튼은 이미 확정한 보컬 RAW만 읽어 새 리드/코러스 분석을 만든다. 원래 6개 결과를 덮어쓰지 않는다. 큐·진행률·기존 GPU 잠금·OOM fallback을 재사용한다. 새 분석은 라이브러리에 별도 항목으로 표시되며 원본 REF는 전체 원곡이 아니라 분리 전 보컬이다. 리드/코러스에는 잔향과 누출이 남을 수 있다.

CLI: python -m music_analyzer.cli separate --input vocals.wav --preset karaoke_roformer

실곡 전체 웹 검증: 주님의 선하심 450.30458초 입력에서 analysis_bfd62bcc15c74c1cae8527cb856c7f25 생성 성공. 상세 사전 로딩, 리드/코러스 재생, 개별 WAV 및 ZIP Range 다운로드 확인. 음질 청취 평가는 사용자 확인 전이며 다른 곡에서도 동일한 품질을 보장하지 않는다.


## 리드·코러스 누출 피드백 및 BS-RoFormer 비교

- 사용자가 Mel-Band Karaoke 결과에서 리드와 코러스의 양방향 누출을 확인했다. EQ로 배정 오류를 해결하지 않는다.
- BS-RoFormer Karaoke frazer/becruily를 추가했다. 기존 Mel-Band 결과를 보존하며, 웹의 새 보컬 세부분리는 BS 후보를 사용한다.
- BS 후보는 단일 리드 추정 + 입력 보컬에서 리드를 뺀 코러스 후보다. 재합산 일치는 품질 개선의 증거가 아니다. 잔향 및 리드 누출이 코러스 후보에 남을 수 있다.
- 기본 10초 / 75% 겹침, GPU 메모리 부족 시 5초로 재시도한다. 기존 20초 보컬 구간 GPU 추론 완료. 동일 전체 곡 비교는 별도 라이브러리 항목으로 실행한다.
- 공식 HF revision: f7849ae934209184dc288d1018cd8a76a7fc8b3c. 체크포인트 SHA256: eb90ee24c1154d83fbcfd27e96182f19e061557cc6e4746953125e08c29389f9. 가중치 변경/재학습 없음. 가중치 라이선스는 미확인 상태를 유지한다.
- 개선 여부는 청취로 확인해야 하며, 품질 검증 플래그는 false로 유지한다. 기타/스트링/가창자별 상세 분리는 아직 완료되지 않았다.


## 다음 단계: other / 기타 AudioSep 실험

사용자는 BS-RoFormer 리드·코러스 결과가 얼추 괜찮다고 평가하고 다음 단계 진행을 요청했다. 현재 곡의 잠정 기준으로 유지하되, 모든 곡에서 가창자별 분리가 검증됐다고 표시하지 않는다.

AudioSep 공식 코드 revision 944583f18b84589dc965de3ad77525c945334252 및 공식 Space revision 0807a713283035d8b0d0628f1b8e3d6580459f7b를 고정한다. 체크포인트 2개는 공개 SHA256 검증을 통과했다. 별도 실험 환경에 추가 의존성을 설치하며, 서비스 .venv 패키지는 읽기만 공유한다.

공식 모델은 32kHz 모노다. 새 어댑터는 좌우를 각각 추론하고 polyphase resampling으로 44.1kHz 정확한 부모 프레임 수를 복원한다. 출력 끝의 리샘플링 초과 프레임만 절단한다. 좌우 일관성은 청취 평가가 필요하다. FLOAT WAV로 저장해 공식 예시의 int16 변환을 피한다. supervisor/GPU execution lock을 공유한다.

Transformers 4.44에서 사라진 비학습 position_ids 버퍼만 로딩 시 제외하는 호환 처리가 있다. 학습 파라미터 및 원본 가중치 파일은 수정하지 않는다. 이 처리는 격리 실험 프로세스에서만 적용하고 복원한다.

패드 프롬프트: `A sustained synthesizer pad playing in the background`
기타 프롬프트: `An electric lead guitar playing a melodic solo`

기존 20–40초 구간에서 목표 + 입력에서 목표를 뺀 잔여를 비교한다. 기타 잔여를 기타 2 또는 리듬 기타 정답으로 이름 붙이지 않는다. 현재 전체 곡 자동 분리, 기타 1/2/3 및 스트링 분리 완료를 의미하지 않는다.

준비: `.\.venv\Scripts\python.exe scripts/prepare-audiosep.py`
실행: `.\data\separation\tools\audiosep-env\Scripts\python.exe -m music_analyzer.audiosep_experiment --experiment-id experiment_새ID --prompt "An electric lead guitar playing a melodic solo" --publish-library`
실험 입력 준비는 위 substem_experiment prepare 명령을 재사용한다. 동일 실험 결과를 덮어쓰지 않도록 매 추론마다 새 PREPARED 입력을 사용한다.

실행 결과: 신스 패드 analysis_66ab9a174be0414c89b7beaad01d91ec 및 리드 기타 analysis_81b40703c3cc443f9dc2200d6a182acd를 라이브러리에 추가했다. 각 20초 양 채널 추론 약 16초, PyTorch peak allocated 3,741,275,648 bytes(약 3.48 GiB). 프레임 수/finite 검증, 원본·후보·잔여 Range 재생 응답 및 ZIP 다운로드 검증 완료. 프론트 빌드 및 전체 144 테스트 통과. 실제 브라우저에서 상세 사전 로딩과 재생 확인. 사용자 청취 품질 승인 전이다.


### 다른 곡 재시험

사용자가 첫 AudioSep 결과가 아직 분리되지 않은 것 같다고 평가하여 기본 엔진 채택을 보류한다. 새로 완료한 01 Head Like A Hole의 기타/other에서 220–240초를 동일하게 추출해 후보를 만들었다. 구간은 두 부모 트랙의 상대 RMS 곱이 높은 구간으로 선택했으며, 특정 연주 파트 존재 여부를 자동 검증한 것은 아니다. This D.J. 기타는 거의 무음이라 기타 비교에서 제외했다.

라이브러리: analysis_a8e30c6db2fd49c9b1c65f80aa4eec47(패드), analysis_d6a77188bc19490ab7c6b40fd9661435(기타). 각 882000 프레임 stereo finite 출력과 원본/후보/잔여 재생·ZIP 응답 확인. 기타 목표/입력 RMS 비율 0.921, 잔여/입력 0.191; 패드 0.723 / 0.549. 이 비율은 음량 진단이며 분리 정확도 점수가 아니다. 기타 목표가 입력 대부분을 포함할 수 있으므로 리드·리듬 구분 성능은 계속 미검증이다. 사용자 청취 확인 전.


### 주님의 선하심 패드 재시험

사용자가 Head Like A Hole의 other 잔여는 지직거리는 노이즈라고 평가했다. 이 결과를 성공한 악기 분리로 채택하지 않는다. 사용자 요청대로 주님의 선하심 analysis_d148642d640f45c3a4b390a308865f56의 실제 other(job_d445e46445234bfd834cef450b2676f8/result/stems/other.wav)를 사용해 패드만 20–40초 및 370–390초 비교한다. 첫 패드 실험의 부모 job_8c0eb67a61a44dbaa800e879b77f14fc와 구분한다. 입력 차감 잔여는 모델 오차가 포함될 수 있고, 생성 성공만으로 분리 품질을 주장하지 않는다. 20–40초 결과 analysis_7f92a40aecea47a399092f2e93889bac는 실제 CUDA 추론 및 WAV/ZIP 응답 검증 완료. 뒤 구간은 다른 GPU 분석 후 직렬 실행한다.

370–390초 결과 analysis_68eec1f8b80d4e4e9418dc935c3dbd05도 CUDA 추론 및 원본/후보/잔여 WAV·ZIP 응답 검증 완료. 두 후보 모두 사용자 청취 검증 전이다.


### AudioSep 청취 실패 이후 CLAPSep 모델 비교

사용자가 주님의 선하심 패드 결과가 분리되지만 너무 이상하다고 평가하여 다른 모델을 요청했다. AudioSep는 현재 패드 기본 엔진으로 채택하지 않는다. CLAPSep 공식 Space e3c73653fa9aadcddbcc3b5e967182a573589e81의 추론 코드와 별도 학습된 decoder/LoRA 체크포인트를 고정하고 공개 파일 SHA256을 검증했다. 코드/가중치 식별은 separation/configs/models/clapsep.json에 기록한다. GitHub 코드 MIT와 개별 가중치 사용 허가는 구분하며 가중치 허가는 UNKNOWN/DEV_ONLY 유지.

별도 clapsep-env에서 laion-clap 1.1.7, loralib 0.1.2를 추가했다. 기존 서비스 환경은 수정하지 않는다. 공식 checkpoint가 학습된 LoRA·decoder 파라미터를 모두 제공하는지 검증하며, frozen CLAP/고정 STFT/resampler는 공식 사전학습 모델 및 초기화 값을 사용한다. 원본 가중치 수정이나 재학습은 수행하지 않았다.

32kHz 10초 / 50% 겹침, 좌우 독립 추론, 입력 볼륨 변경 없음, FLOAT 44.1kHz 원래 길이 복원. positive: A sustained synthesizer pad playing in the background / negative: Electric guitar, piano, drums and singing. 서로 같은 parent other 입력의 20–40초와 370–390초를 AudioSep와 비교한다.

라이브러리: analysis_2ac21eba1a3544229494984a159f3e7a 및 analysis_a84ea86f9ecd4ba0adb2de054f9c8cdc. 각각 실제 CUDA 추론 약 12초, PyTorch peak allocated 약 1.27 GiB. 각 882000 frame stereo finite 출력과 원본/패드 후보/잔여 WAV 및 ZIP HTTP Range 응답 검증. 프론트 빌드 및 144 테스트 통과. 결과 품질은 사용자 청취 전이며 개선을 주장하지 않는다.

준비: `.\.venv\Scripts\python.exe scripts/prepare-clapsep.py` (prepare-audiosep.py로 만든 기반 실험 환경 필요)
실행: `.\data\separation\tools\clapsep-env\Scripts\python.exe -m music_analyzer.clapsep_experiment --experiment-id experiment_새ID --name "주님의 선하심"`


## 자동 전체 세부분리 및 그룹 DAW

사용자가 CLAPSep 패드 결과를 합격으로 평가하고 한 번의 분석에서 모든 세부 트랙을 요청했다. 새 업로드는 확정 보컬 → 반주 5종 → BS Karaoke 리드/코러스 → CLAPSep 기타 목표/잔여 → CLAPSep 패드/잔여 순서로 실행한다. 원곡/6개 부모/6개 자식을 같은 분석에 보존한다. 15분까지 원래 타임라인을 유지하며 10초/50% overlap 추론으로 전체 길이를 처리한다. worker는 별도 환경에서 기존 GPU/supervisor lock을 공유하고 stdout 청크 수를 진행률에 반영한다.

DAW는 보컬/일렉기타/신스 그룹을 접고 펼친다. 접힌 상태는 부모, 펼친 상태는 자식만 재생해 이중 합산을 피한다. 모든 오디오를 상세 진입 시 사전 로딩하고 개별 및 전체 ZIP 다운로드를 유지한다. 기타 자식은 일렉1 리드 후보/일렉2 잔여, 신스는 신스1 패드/신스2 잔여로 명시한다. 잔여를 독립 기타 또는 두 번째 신스 정답으로 주장하지 않는다.

실제 주님의 선하심 원곡 370–380초(10초)를 신규 업로드한 analysis_40759119f539403a9a7c612ff6470f7d가 모든 단계 SUCCEEDED, 부모6+자식6=12 결과. 부모/자식 API 경로·재생 파일 및 ZIP 검증. 전체 기존 144 테스트 및 전체 입력 타임라인 검증2개 통과, 프론트 빌드 통과. 기존 분석 결과는 유지하며 새 분석부터 통합 실행한다.

그룹 mute/solo/volume을 자식에 전달하고 접힌 자식 solo가 다른 트랙을 묵음으로 만들지 않도록 추가 검증했다. Node 그룹 재생 테스트4개 통과. 실제 브라우저에서 세 그룹 펼치기 및 부모 바로 아래 자식6개 표시 확인. 기존 실험과 달리 기타도 CLAPSep로 처리하되 리드 후보와 잔여를 명시한다. 신스2 잔여에는 신스 이외의 소리가 포함될 수 있다.

2026-10-06: 사용자 요청으로 주님의 선하심 전체 450.30458초를 새 분석 analysis_4635993d92ce4c629371cf6d6f98a442(주님의 선하심 - 전체 통합분리)로 실행해 SUCCEEDED. 12개 결과 전부 원본과 프레임 수/44.1kHz/stereo 일치 및 finite 확인. 원본·12개 결과 재생과 ZIP Range 응답 검증 완료. 기존 결과 보존. 기타/신스의 두 번째 트랙은 잔여이며 독립 연주 파트로 검증된 것이 아니다.

## 2026-10-06 전체 곡 상세 진입 지연 개선
- 7분 30초 통합 결과의 원본+12개 분리 트랙을 AudioBuffer로 모두 디코딩할 때 약 2 GiB 이상의 샘플 메모리가 필요하고 상세 준비가 지연되는 현상을 재현했다. 브라우저 OOM 자체를 확정한 것은 아니다.
- 120초 초과 곡은 HTMLAudioElement와 MediaElementAudioSourceNode로 스트리밍한다. 상세 진입 시 각 트랙 canplay 준비를 진행률로 표시하며, 짧은 비교 음원은 기존 AudioBuffer 방식을 유지한다.
- 긴 곡의 재생 캐시는 PCM16 FLAC으로 무손실 압축한다. 기존 재생용 공통 gain과 샘플 길이를 유지하며 FLOAT WAV 개별/ZIP 다운로드는 변경하지 않는다. 첫 진입에는 재생 캐시 생성 시간이 필요하다.
- 원본 파형은 서버에서 계산한다. 화면을 벗어날 때 미디어/오디오 노드를 정리하며, 재생 실패 시 이미 시작된 트랙도 멈춘다.
- 긴 곡 미디어 재생은 샘플 단위 동시 시작을 보장하지 않으며 80 ms 초과 드리프트를 보정한다. 정밀 위상 비교에는 다운로드 WAV를 DAW에서 사용한다.
- 검증: 웹 API 테스트 13개 통과, 프론트 production build 성공. 주님의 선하심 전체 통합분리의 상세 진입, 13개 트랙 준비, 시간 진행, 일시정지, 보컬/일렉/신스 그룹 펼침 및 위치 조절을 실제 브라우저에서 확인했다.

### 재생 파일 호환성 보완 (2026-10-06)
- 새 전체 분석 analysis_b9a1d04282dc468ab26459798395413a는 SUCCEEDED이며 12개 결과 파일이 존재한다. FLAC 범위 응답도 정상(206)이어서 분리 실패/파일 누락은 확인되지 않았다. 사용자 기기에서의 정확한 미디어 오류 코드는 아직 확보하지 못했다.
- 긴 곡의 브라우저 재생은 호환성과 외부 접속 전송량을 위해 320 kbps MP3 캐시를 사용하도록 변경했다. 이는 손실 압축 미리듣기이며 원본 FLOAT WAV 다운로드·ZIP·선명도 출력은 유지한다. FLAC은 중간 캐시로 남는다.
- /audio/{family}?format=mp3 제공, 미디어 MIME을 명시하고 최초 캐시 생성/느린 전송의 로딩 제한을 120초로 확대했다. 오류 메시지에 트랙 이름과 미디어 오류 코드를 표시한다.
- 연결 종료 예외를 OSError 처리보다 먼저 처리하여 이미 끊어진 연결에 JSON 오류 응답을 다시 쓰는 문제를 방지했다.
- API 테스트 14개(실제 MP3 인코딩/캐시/원음 보존 포함)와 frontend production build 통과.

### HTML 미디어 재생 제거 및 AudioBuffer 구간 재생 (2026-10-06)
- 사용자 환경에서 play() 준비 중 pause() 호출로 중단되는 오류가 발생했다. 앞선 FLAC/MP3 HTMLAudioElement 재생 경로를 제거하고 모든 곡을 Web Audio AudioBufferSourceNode 재생으로 복원했다. 긴 곡은 전체 버퍼를 모두 보관하는 대신 30초 현재/다음 구간만 유지한다.
- WAV 구간 API는 start_frame/num_frames를 받아 SoundFile.seek로 정확한 프레임을 읽고 기존 공통 재생 gain/PCM16을 적용한다. MP3 재인코딩은 사용하지 않는다. FLOAT WAV 다운로드/분리 결과는 유지한다.
- 모든 트랙의 현재/다음 구간을 AudioContext의 동일한 시각에 예약한다. 종료한 노드는 연결을 해제하고 지난 구간 캐시를 제거한다. 빠른 위치 이동은 불필요한 구간 요청을 취소한다.
- 재생 준비 중 재클릭/정지/화면 이동에는 세대 번호로 이전 시작 요청을 무효화한다. 아직 준비되지 않은 위치로 이동하면 '재생 구간 준비 중'을 표시한다. 네트워크가 다음 구간 준비를 따라가지 못하면 오류를 표시하고 정지하므로 모든 접속 환경에서 무중단을 보장하는 것은 아니다.
- 검증: 서버 테스트 14개, 프론트 테스트 7개(동시 시작/구간 경계 예약/준비 중 정지/캐시 제거/그룹 믹싱), production build 성공. 실제 서버 30–60초 구간은 1,323,000 frames/44.1kHz/stereo로 확인했다.
- 실제 브라우저 추가 검증: 새 전체 곡 상세 로딩 성공, 재생·정지 빠른 반복, 보컬 그룹 펼치기, 30초 경계 통과, 재생 중 PageUp 3회로 3분대 위치 이동 후 재생 지속, 일시정지 성공. 확인 중 브라우저 error 로그는 없었다. 사용자 모바일/외부 네트워크에서의 동일 검증은 아직 하지 않았다.

## 2026-10-06 리드/코러스 2:25 이후 양방향 누출 재검토
- 대상: analysis_b9a1d04282dc468ab26459798395413a, 주님의 선하심 - 전체 통합분리 새 분석. 사용자가 145초 이후 리드가 코러스 후보에 남고 코러스가 리드에 들어가는 현상을 보고했다. BS 기본 결과는 리드 단일 추정 + 입력 보컬 잔여이며, 모든 잔여를 코러스 정답으로 해석할 수 없다.
- 기존 결과를 보존했다. 145–175초를 비교 구간으로 정하고 130–190초(앞뒤 15초 문맥)를 두 모델에 입력한 뒤 동일한 30초를 잘라 새 라이브러리 항목으로 등록했다. 비교 파일의 0초는 원곡 2:25다. 각 비교의 원본 REF는 분리 전 보컬 구간이다.
- scripts/compare-vocal-detail.py: 부모 분석 ID/시작/길이를 받아 기존 BS 구간, BS 고겹침 후보, Mel-Band 대체 후보를 생성한다. 기본 파이프라인/기존 가중치/기존 전곡 결과는 변경하지 않는다.
- bs_karaoke_refined 실험 프리셋: 기존 BS 가중치/10초 추론 문맥/float16 유지, overlap 0.75 → 0.875. OOM 시 기존 5초 메모리 절약 프리셋으로 fallback한다. 이번 실험은 refined 프리셋으로 성공했다. 이는 새 학습 모델이 아니다.
- 비교 항목:
  - 기존 BS: analysis_d7660d2f119e4d0b89954fa4ca9383e3
  - BS 고겹침: analysis_4591b6141ebc4681a07079581300d35f, job_84d74a385f8e46d98d86bee10fa6e528
  - Mel-Band 대체: analysis_0069464a69ba485cb425a43defcd19d2, job_759cc20d1b1a43c1a25fe6f6f4e713b8
- 모든 트랙 1,323,000 frames/44.1kHz/stereo/FLOAT 및 finite 검증. BS는 리드+잔여 합산 오차 peak 5.96e-8, Mel-Band는 두 독립 추정 출력이므로 합산 오차가 남는다(구간 peak 0.09338). 재합산 수치는 목소리 배정 정확도의 점수가 아니다.
- 두 후보의 리드 출력은 기존과 다르지만 개선을 청취 검증하지 않았다. quality_improvement_verified=false 유지. 공식 모델 제공자 페이지에는 상세 model card가 없으므로 이 곡에서의 완벽한 가창자 구분 능력을 주장하지 않는다.
- 모델 제공자: https://huggingface.co/becruily/bs-roformer-karaoke 및 https://huggingface.co/becruily/mel-band-roformer-karaoke
- 테스트: RoFormer 기존 테스트 22개 통과. 비교 GPU 추론 모두 성공, 라이브러리 표시 검증 완료.
