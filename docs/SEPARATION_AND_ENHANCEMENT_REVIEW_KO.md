# 현재 분리 구조와 음질 개선 검토

검토일: 2026-10-06. 현재 저장소 코드와 모델 등록 파일 기준입니다. 청취상 약 90%라는 평가는 정답 트랙을 기준으로 측정한 정확도가 아닙니다.

## 현재 실행 흐름

1. MP3/WAV/FLAC 업로드 → FFprobe 검증 → FFmpeg 디코딩 → 44.1kHz 스테레오 float32 canonical WAV. 모노는 양쪽 채널에 복제합니다. 입력 샘플레이트가 다르면 리샘플링합니다.
2. MelBandRoformer / KimberleyJSN `MelBandRoformer.ckpt`: 원곡에서 보컬 추정. 반주는 원곡−보컬로 계산합니다.
3. 기본 BS-Roformer `bs_6stem_fixed.ckpt`: 반주에서 bass/drums/other/vocals/guitar/piano를 동시에 추정. 이 단계의 vocals 출력은 최종 트랙 목록에서 제외합니다. 선택 가능한 대안은 Demucs htdemucs_6s입니다.
4. BS-Roformer karaoke / `bs_roformer_karaoke_frazer_becruily.ckpt`: 2번의 보컬에서 lead를 추정. backing은 보컬−lead로 계산합니다. 가창자 신원 분리가 아니므로 잔향과 리드 누출이 코러스에 남을 수 있습니다.
5. 최종 표시: 보컬(lead), 코러스(backing), 피아노, 신스(3번 other), 일렉기타(guitar), 베이스, 드럼, 나머지. 기타는 전용 일렉기타 클래스가 아니라 guitar 클래스입니다. 신스 역시 전용 synth 클래스가 아니라 other의 표시 이름입니다.
6. 나머지=원곡−위 7개 출력 합계. 모델의 독립 악기 추출 결과가 아니라 부호가 있는 차이 신호입니다. 모델 간 오차와 제외된 신호가 포함될 수 있습니다. 이를 포함하여 재합성이 잘 된다는 사실은 분리 품질을 뜻하지 않습니다.

## 추론 방식

Roformer는 STFT로 변환한 주파수 영역에서 밴드별 특징과 시간·주파수 관계를 처리하고, 복소 마스크를 추정하여 iSTFT로 복원합니다. 실제 로컬 BS-Roformer 코드가 복소 마스크 곱셈을 사용하므로, 기존 CLAPSep 실험의 magnitude-mask 설명과 구분해야 합니다.

| 단계 | 청크 | 오버랩 | 연속 청크 간격 |
| --- | ---: | ---: | ---: |
| 보컬 MelBandRoformer | 8초 | 75% | 2초 |
| 악기 BS-Roformer 6stem | 약 13.35초 | 50% | 약 6.68초 |
| 보컬·코러스 BS karaoke | 10초 | 75% | 2.5초 |

배치 1, CUDA, float16 autocast, inference_mode, 고정 seed, TF32 비활성화입니다. 좌우 스테레오를 모델 입력으로 함께 처리합니다. 청크 경계는 패딩과 crossfade 가중 평균으로 연결합니다. 최종 출력 범위 밖의 끝 청크는 생략합니다. OOM 시 별도 memory_safe 프리셋으로 재시도합니다. 작업마다 별도 worker 프로세스를 실행하고 모델을 다시 로드합니다. GPU 잠금으로 동시 추론을 제한합니다.

WAV 출력은 32bit float이며 원본 출력에 클램핑이나 개별 정규화를 하지 않습니다. 긴 곡 재생은 30초 단위로 가져오고, 미리보기에는 공통 gain을 적용하여 클리핑을 피합니다. 재생과 RAW 다운로드를 구분합니다.

## 현재 사용 라이브러리

| 구성 | 라이브러리/도구 | 역할 |
| --- | --- | --- |
| 추론 | Python 3.12 환경, PyTorch 2.5.1+cu121, torchaudio 2.5.1+cu121 | NVIDIA CUDA GPU 추론 |
| 모델 구현 | Music-Source-Separation-Training 고정 revision 84b1eac0887756b4f1a9d7a1ff49105939749ed2 | MelBand/BS Roformer 코드 |
| 대안 모델 | Demucs 4.0.1 | 선택 가능한 6stem 분리 및 Demucs 프리셋 |
| 신호 처리 | NumPy 1.26.4, SciPy 1.14.1, librosa 0.11.0 | 배열, 필터, 모델 특징 처리 |
| 오디오 IO | soundfile 0.13.1 / libsndfile, FFmpeg/FFprobe | WAV/FLAC 읽기·쓰기, 검증, 디코딩 |
| 모델 보조 | einops 0.8.2, rotary-embedding-torch 0.9.1, beartype 0.22.9, PyYAML 6.0.3 | 텐서 변형, 모델 구성 |
| 작업 제어 | filelock 3.32.3, psutil 7.1.0, subprocess | GPU 직렬화, 프로세스 감시, 취소·복구 |
| 회원 데이터 | MySQL, PyMySQL 1.1.2, cryptography | 계정·세션·분석 소유권 |
| 웹 UI | Vue 3.5.43, Vite 6.4.3, Web Audio API | 재생·믹서·EQ·다운로드 |

정확한 전체 의존성은 `separation/requirements/windows-py312-cu121.lock.txt`에 있습니다. openunmix 등 간접 의존성이 설치되어 있다고 기본 추출에서 직접 실행되는 것은 아닙니다.

CLAPSep, AudioSep와 대체 karaoke Roformer는 이전 실험/등록 대상으로 남아 있지만 현재 기본 분석의 기타·신스 세부분리에는 사용하지 않습니다. SAM Audio와 아래 향상 모델은 현재 설치·통합한 기능이 아닙니다.

## 현재 선명도 기능

브라우저 Web Audio peaking EQ와 다운로드 SciPy SOS 필터입니다. 예를 들어 보컬은 300Hz를 약하게 줄이고 3.2kHz를 약하게 올립니다. 강도에 따라 gain이 변하며 0%는 bypass입니다. AI 잡음 제거, 잔향 제거, 누출 악기 제거, 생성 복원, de-esser 또는 compressor는 아직 없습니다. 다른 악기와 주파수가 겹치면 EQ만으로 누출을 분리할 수 없습니다.

## 남은 품질 문제를 분류하는 방법

- 누출: 목표 트랙에 다른 악기의 음표·박자·가사가 들림 → 분리 모델/전용 체크포인트/구간별 재추출을 검토합니다.
- 목표 손실: 기타 배음, 피아노 어택, 보컬 자음이 사라짐 → 다른 모델 후보를 비교하고 제거 강도를 낮춥니다.
- 분리 아티팩트: 물결치는 금속성 소리, 불연속, 위상 문제 → 마스크 안정성, 청크 연결, 다른 모델 결과를 검토합니다.
- 녹음 잡음: hiss/hum → 조심스러운 잡음 제거를 검토합니다. 악기 누출과 구별합니다.
- 음색·다이내믹: 탁함, 날카로움, 음량 불균형 → dynamic EQ, de-esser, compressor 등을 적용합니다.
- 잔향: 원곡의 음악적 reverb와 불필요한 공간 잔향을 구별합니다. 코러스·패드·심벌의 긴 꼬리를 무조건 제거하지 않습니다.

정답 stem이 있는 테스트에서는 SI-SDR와 누출·목표 보존 지표를 평가하고, 정답이 없는 실제 곡에서는 같은 시간/청감 음량으로 블라인드 A/B 청취를 합니다. 각 구간의 모델·체크포인트·속도·GPU 메모리·처리 강도를 기록합니다. 전체 합계가 원곡과 일치하거나 A/B 상관도가 낮다는 것만으로 정확도를 주장하지 않습니다.

## Enhance Speech와 구현 방향

Adobe 공식 설명의 Enhance Speech는 말소리의 배경 잡음 제거와 명료도 개선을 대상으로 합니다. 공개된 제품 설명만으로 내부 모델이나 우리 노래 stem에서 동일한 성능을 보장할 수 없습니다.

Resemble Enhance는 denoiser와 enhancer로 구성되며 44.1kHz speech 데이터로 학습했다고 명시합니다. DeepFilterNet은 48kHz speech enhancement용입니다. 둘 모두 노래·코러스·악기에 대한 적용은 별도 실험이 필요합니다. 이 도메인 차이 때문에 비브라토·숨·화음·악기 배음을 손상할 가능성을 검증해야 합니다.

AudioSR은 오디오 대역 확장 후보이며 독립 악기 분리나 누출 제거 기능이 아닙니다. 생성한 고역이 원래 음원의 정답 고역이라는 보장도 없습니다. SAM Audio는 텍스트·시간 구간을 지정하는 재추출 후보입니다. 설치 환경, GPU 요구량, 모델 접근 및 라이선스를 따로 검토해야 합니다.

추천 구성: 원곡 → 기본 분리 → 선택 소스의 누출 정리 → 소스별 음질 처리 → 지연 보정·길이/스테레오 유지 → RAW/향상 A/B 및 강도 조절. 처리 결과는 원본을 덮어쓰지 않고 캐시하며 선택 트랙만 추가 처리합니다. 모델명·버전·파라미터·원본 해시를 캐시 키에 포함합니다.

| 소스 | 우선 처리 | 주요 보존 대상 |
| --- | --- | --- |
| 보컬 | 누출 제거, 약한 denoise, de-esser, dynamic EQ, 압축 | 발음, 비브라토, 숨, 음색 |
| 코러스 | 리드 누출 제거, 약한 EQ/잡음 정리 | 화음, 여러 목소리, stereo width, 자연스러운 잔향 |
| 피아노 | 전용 추출 후보, 저중역 dynamic EQ | 해머 어택, 공명, 페달 꼬리 |
| 신스 | 전용 synth 분리 후보/프롬프트 재추출 | sustained pad, modulation, delay/reverb |
| 일렉기타 | 기타 전용 후보와 원곡/반주 입력 비교 | distortion, 배음, 피킹, amp noise |
| 베이스 | 킥 누출 정리, 저역 dynamic EQ/압축 | 저역 fundamental, 배음, 연주 어택 |
| 드럼 | 보컬·선율 누출 정리, 약한 transient 처리 | 킥/스네어 어택, 심벌 고역, decay |
| 나머지 | 진단·청취 중심 | 여러 종류의 신호가 섞여 있으므로 자동 강한 향상은 피함 |

추천 진행 순서는 문제 구간 선정 → 분리 후보 비교(원곡 직접 6stem 포함) → 보컬용 보존 중심 DSP → speech AI 후보의 노래 적합성 비교 → 악기별 처리 확장입니다. 앙상블은 평균을 내면 반드시 개선되는 것이 아니며 시간·위상 정렬과 후보 선정이 필요합니다.

## 출처

- [Music-Source-Separation-Training](https://github.com/ZFTurbo/Music-Source-Separation-Training)
- [KimberleyJSN MelBandRoformer](https://huggingface.co/KimberleyJSN/melbandroformer)
- [현재 6stem 가중치](https://huggingface.co/noblebarkrr/mvsepless_resources)
- [현재 karaoke 가중치](https://huggingface.co/becruily/bs-roformer-karaoke)
- [Demucs](https://github.com/facebookresearch/demucs)
- [CLAPSep](https://github.com/Aisaka0v0/CLAPSep), [AudioSep](https://github.com/Audio-AGI/AudioSep)
- [Adobe Enhance Speech 설명](https://podcast.adobe.com/en/guides/how-enhance-speech-can-improve-your-recording-sound-quality)
- [Resemble Enhance](https://github.com/resemble-ai/resemble-enhance)
- [DeepFilterNet](https://github.com/Rikorose/DeepFilterNet)
- [AudioSR](https://github.com/haoheliu/versatile_audio_super_resolution)
- [SAM Audio](https://github.com/facebookresearch/sam-audio)

코드와 가중치의 라이선스는 별개입니다. 현재 프로젝트 등록 파일에서는 MSST 코드 MIT를 확인했지만 6stem·karaoke 가중치는 UNKNOWN/UNRESOLVED로 기록되어 있습니다. 외부 서비스 제공 단계에서는 해당 체크포인트 조건을 확인해야 합니다.
