# S7 악기 분리 BS-RoFormer 후보 비교

2026-10-05. 사용자 피드백: 기타에 피아노가 섞이고, 13–14초의 슬랩 베이스가 기타에 들어가며, 20–40초 피아노 트랙에 빈 구간이 있다. 보컬 모델은 확정 상태로 유지하고 **동일한 RoFormer 반주**를 입력으로 다른 악기 모델을 시험했다.

## 후보와 실행 조건

6-stem BS-RoFormer의 community-published fixed checkpoint를 연결했다. 게시 저장소는 noblebarkrr/mvsepless_resources이며 고정 리비전은 030a01aa951b3908ed6b01b2e507c17953300c2d다. 원 학습 주체, 학습 데이터 및 품질 근거가 확인되지 않아 실험 후보로만 등록했다. 새 모델이 기존보다 정확하다고 주장하지 않는다.

- 체크포인트 bs_6stem_fixed.ckpt, 공개 전체 SHA-256: 24e7d35ee9c64415673d3fd33e06a67cac2c103c5df6267ba1576459c775916e. 실제 다운로드와 일치.
- 설정 SHA-256: 4678db9430a87ee33e7fad199166928c9adcd322e2df1a812b4bf03726e2a48b.
- 모델 출력 순서: bass, drums, other, vocals, guitar, piano. 설정의 instruments와 등록 계약을 대조하고 strict state_dict 로드.
- MSST 리비전 84b1eac0887756b4f1a9d7a1ff49105939749ed2의 BSRoformer 코드. 패키지 내부 import만 변경하고 MIT LICENSE 및 원본/변경 코드 해시를 보관.
- 44.1kHz stereo, 588800샘플(약13.35초) 구간, 50% overlap, batch 1, CUDA float16. 양의 선형 crossfade 및 반사 문맥 패딩. 모델의 원래 ISTFT length 처리 사용.
- 구간 및 stem별 gain 변경, hard gate, 강한 denoise 없음. FLOAT WAV, 정확한 타임라인, hash/readback 검증.
- OOM이면 같은 모델의 6초 구간을 새 worker에서 한 번 재시도하는 preset 등록. 실제 실행에는 fallback이 없었으며 fallback의 품질은 미검증.

## 실제 결과

기사개전 전체 195.419초 반주, asset_fbfe1273f17741e5aa0f4fd4b3c643d4:
- 기존 악기 작업: job_da86237490c64ae786c577e6a0995ccd.
- 후보 작업: job_c2788a98d55c4aa091a429d40b6b007a — SUCCEEDED, 32구간, 추론 30.715초.
- PyTorch peak allocated 1658294272 bytes, reserved 2027945984 bytes. 전체 GPU 사용량 측정은 아니다.
- 동일 canonical SHA-256: 64cefd0fc6c8f8d61120d02b04afdf1f4b9aa3a82a982e40f5e1a5dc82d9f3bb.
- 첫 연결에서 Mel-Band 전용 생성자 옵션을 BS 모델에 전달하는 호환 오류가 발생했다. BS 모델 고유 ISTFT 처리로 수정하고 새 작업으로 재실행해 성공했다. 기존 실패 작업은 이력으로 보존했다.
- 보컬·반주 단계와 달리 여섯 추정치 합의 원본 재구성은 보장하지 않는다. 이 오차로 분리 정확도를 채점하지 않는다.

## 비교

[청취 비교 파일](../../data/separation/comparisons/compare_28597ec671304d54b2f34a3c5c3ad06c/comparison.html)

기존 Demucs 6트랙과 BS-RoFormer를 같은 반주 및 동일 fixed gain으로 비교한다.
1. 10–18초: 13–14초 슬랩이 베이스에 보존되고 기타에서 줄었는지.
2. 20–40초: 피아노의 빈 부분이 채워졌는지, 기타의 피아노 혼입이 줄었는지.
3. 70–90초와 135–155초: 다른 구간에서 악기 누락·먹먹함·누출이 악화되지 않았는지.

여기서 입력은 보컬을 제거한 반주다. 페이지의 보컬 트랙은 두 악기 모델이 다시 추정한 잔여 보컬 진단용이며 확정한 RoFormer 원곡 보컬을 대신하지 않는다. 전체 반주 버튼은 동일 방식으로 입력 반주 minus 잔여 보컬인 비교용 파생값이다.

기존 기본 pipeline 설정은 변경하지 않았다. 후보의 청취 평가를 받은 뒤 악기 모델 채택 여부를 결정한다.

## 검증과 재실행

전체 테스트 119개 통과(31.84초), pip check 통과. 추가 검증은 다중 stem 순서·진폭·timeline 보존 및 누락 output head 거부다. 실제 추론의 strict load, 출력 frames/hash/FLOAT readback도 통과했다. 객관적 정답 stem이 없어 SDR나 실제 악기 정확도는 산출하지 않았다.

프로젝트 루트에서:
```powershell
.\.venv\Scripts\python.exe -m music_analyzer.cli prepare-model --model bs_roformer_6s
.\.venv\Scripts\python.exe -m music_analyzer.cli separate --asset-id asset_fbfe1273f17741e5aa0f4fd4b3c643d4 --preset instrument_roformer_6s
```

출처: [게시 모델 파일](https://huggingface.co/noblebarkrr/mvsepless_resources/tree/030a01aa951b3908ed6b01b2e507c17953300c2d/bs_roformer), [추론 코드](https://github.com/ZFTurbo/Music-Source-Separation-Training/blob/84b1eac0887756b4f1a9d7a1ff49105939749ed2/models/bs_roformer/bs_roformer.py).
