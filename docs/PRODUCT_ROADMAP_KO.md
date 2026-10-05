# music_analyzer 제품 로드맵

최종 제품은 음원 입력부터 악기별 오디오·채보·악보와 사용자 수정까지 이어지는 하나의 프로그램이다. 각 Phase는 모듈과 검증 단위이며 별도 제품이나 저장소를 뜻하지 않는다.

| Phase | 모듈 | 주요 결과 | 착수 기준 |
|---|---|---|---|
| A | Audio Separation Engine | stem WAV, 타임라인, provenance, 로컬 비교 청취 | 현재 개발 범위: [S1–S7](audio-separation/03_DELIVERY_AND_VALIDATION_KO.md) |
| B | Music Analysis Engine | Beat/BPM/Downbeat, Key/Chord, 분석 JSON | Phase A 시간축 계약 확보 후 별도 상세 설계 |
| C | Transcription Engine | Guitar/Bass/Piano/Drums note·event와 raw MIDI | 참조 오디오·MIDI 확보, 악기별 Note/Onset/Offset F1 검증 |
| D | Score Engine | MIDI/MusicXML/TAB/드럼 악보/PDF | C 결과와 B 음악 시각 연결, 악보 수용 기준 확정 |
| E | Integrated Workstation | Waveform, stem, piano roll, score, correction 이력 | 모듈 간 재생·편집·재생성 계약 확보 |
| F | Service | Upload, GPU worker, 계정, 결제 | 로컬 품질·자원 실측과 운영·이용조건 검토 |

B–F의 라이브러리·모델·기간은 아직 확정하지 않았다. A를 먼저 구현하고 필요한 인터페이스만 준비한다. 로컬 프로그램만으로 최종 목표를 충족할 수 있다면 F는 선택 단계다.

Phase C가 가능해지면 separator의 최종 선택 근거에 downstream transcription 성능을 추가한다. 청각 순도, RAW-SDR, SI-SDR과 Note/Onset/Offset F1을 나란히 비교하며 하나의 종합 정확도 백분율로 합치지 않는다. 깨끗하게 들리는 stem이 채보에 가장 좋은 stem이라고 미리 가정하지 않는다.

평가곡 확대 계획은 초기 20곡 → 개발 확대 50–100곡 → 서비스 전 300–500곡 이상을 목표 후보로 삼되, 단계별 용도·권리·장르·holdout 설계가 먼저다. correction 데이터의 학습 활용은 사용자의 별도 동의와 데이터 권한이 확보되어야 한다.
