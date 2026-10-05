# 07. S2 오디오 입력·변환 검증 결과

검증일: 2026-10-05 (한국 시간). 상태: S2 수용 기준 통과.

## 구현 결과

모델과 GPU 없이 WAV·FLAC·MP3를 검증하고 원본 사본과 canonical float32 WAV, asset manifest를 생성한다. CLI는 ingest와 inspect-asset을 제공한다.

오디오 하나는 inputs/asset ID 디렉터리 하나로 저장된다. 원본은 바이트 그대로 복사하고 SHA-256을 기록·재검증한다. 확장자와 probe 결과를 대조하고 mono/stereo만 받는다. 먼저 원래 rate로 디코딩해 frame 수를 얻은 뒤 필요할 때만 44.1kHz로 resample한다. mono는 채널마다 같은 샘플을 복제하며 downmix·loudness normalization·silence trim을 하지 않는다.

canonical은 44.1kHz stereo FLOAT WAV다. 시간 0은 처음 디코딩된 샘플이며 duration=frames/44100으로 계산한다. MP3의 헤더 duration과 실제 decoded duration은 별개로 보존한다.

## 실행 예제

실제로 생성한 10초 합성 파일을 CLI로 각각 등록하고, 생성된 asset을 다시 hash·타임라인 검사했다. 아래 시간은 subprocess 시작/검증/복사/변환/결과 조회가 포함된 단일 로컬 실행 관측치다.

| 입력 | canonical frame 수 | native decoded 길이 | 채널 처리 | CLI wall |
|---|---|---|---|---|
| 한글 스테레오 48k.wav | 441,000 | 10.000000초 | 스테레오 유지 | 0.559초 |
| 한글 모노 48k.wav | 441,000 | 10.000000초 | 양 채널 복제 | 0.561초 |
| 검증용 48k.flac | 441,000 | 10.000000초 | 스테레오 유지 | 0.560초 |
| 검증용 48k.mp3 | 441,000 | 10.000000초 | 스테레오 유지 | 0.566초 |

모든 예제의 canonical frame 수는 441,000이고 원본은 그대로 보존됐다. 이 결과는 음악 분리 품질 평가가 아니다.

- [한글 스테레오 48k.wav manifest](../../data/separation/inputs/asset_8d5d01f70bbd4332aa9dc6aced724310/manifest.json)
- [한글 모노 48k.wav manifest](../../data/separation/inputs/asset_7838375875de486984cd8f4222ba4e59/manifest.json)
- [검증용 48k.flac manifest](../../data/separation/inputs/asset_480342c5a3f6409aa2a10935728a03b7/manifest.json)
- [검증용 48k.mp3 manifest](../../data/separation/inputs/asset_04eba0183ba443148833413db0020e66/manifest.json)
- [전체 예제 결과 JSON](../../data/separation/s2-validation/results.json)
- [테스트 결과 XML](../../data/separation/test-results-s2.xml)

## 검증 항목

총 59개 테스트가 통과했다. S1 회귀 16개와 S2 검증 43개를 포함한다.

- WAV·FLAC·MP3, 8/44.1/48/192kHz, mono/stereo, 한글·공백·기호 경로.
- 원본 바이트·hash 보존, 저장 전후 gain 유지, 1.0 초과 float32 샘플 보존.
- 48kHz 임펄스의 44.1kHz 변환에서 위치 오차 1 sample 이내, stereo 상대 볼륨 유지.
- fractional frame 반올림, 마지막 1 frame trim/zero padding, 더 큰 차이는 실패.
- 15분짜리 실제 48kHz mono WAV 입력: canonical 39,690,000frame, 정확히 900초.
- 정상 무음과 역위상 stereo를 그대로 보존하며 모델은 호출하지 않음.
- 손상 파일, 빈 파일, 다른 형식으로 위장한 확장자, 6채널, 짧은 음원, 지원 범위 밖 rate, NaN 거절.
- 파일 크기·decoded PCM·길이·디스크 여유 제한과 decoder timeout 후 subprocess 종료.
- manifest 쓰기 오류 시 부분 결과 미게시, 재실행·실패가 이전 성공 asset을 변경하지 않음.
- 손상된 manifest·원본·hash·타임라인 및 경로/ID 변조 거절.
- CLI의 JSON 오류·exit code 2와 GPU 라이브러리 미사용 확인.

15분 검증은 무음의 입력·변환 시험이다. 긴 실제 곡의 분리 성능이나 청각 품질을 입증하는 시험은 아니다.

## 구현 결정과 제한

native PCM 기준 최대 2GiB, 원본 최대1GiB, 실제 decoded 길이 1–900초를 제한한다. FFprobe는 최대30초, 각 decode/resample subprocess는 최대300초다. 두 단계를 순서대로 실행하므로 입력 처리 전체가 300초로 제한되는 것은 아니다. stderr는 임시 파일로 받고 출력 PCM은 작은 block으로 읽어 길이·byte·finite 제한을 실행 중 적용한다.

FFprobe duration은 preflight 힌트이며 1초 허용 여유를 둔다. 실제 decoded frame 수가 최종 길이 판정 기준이다. 헤더 길이로 결과를 강제로 자르지 않는다. resampler 출력은 native_frames×44100/native_rate를 가장 가까운 정수(half-up)로 바꾼 값과 비교하고, 최대1 frame의 끝부분만 trim 또는 zero pad한다. 보정량을 manifest에 기록한다.

처리 중 디렉터리는 .partial로 관리한다. 원본/canonical/manifest 검증 후 같은 볼륨에서 directory rename으로 발행한다. 실패·KeyboardInterrupt는 이 실행이 만든 임시 디렉터리만 정리한다. OS 강제 종료로 남은 임시 디렉터리는 자동으로 성공 결과가 되지 않으며 S3에서 복구/정리 정책을 연결한다.

manifest에 원본 이름과 결과 내 상대 경로는 포함하지만 개인용 절대 경로는 넣지 않는다. CLI 응답에는 현재 사용자가 접근할 실제 경로를 별도로 제공한다.

FFmpeg/FFprobe는 PATH의 외부 도구로 호출하며 프로그램에 포함하지 않는다. 설정과 버전을 provenance에 기록한다. [FFmpeg 공식 문서](https://ffmpeg.org/ffmpeg.html), [SoundFile 문서](https://python-soundfile.readthedocs.io/en/0.13.1/)

## 다음 단계

S3에서는 이 asset ID와 검증된 canonical을 모델 adapter의 입력으로 사용한다. JobService, GPU 단일 실행 lock, 작업 상태·취소·복구, 정식 4-stem 출력과 OOM fallback을 연결한다. 이번 단계에는 실제 음악의 분리 품질, 6-stem, PCM24 사용자 export, GUI가 포함되지 않는다.
