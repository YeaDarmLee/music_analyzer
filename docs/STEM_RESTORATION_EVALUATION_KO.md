# Stem Restoration 평가 계획 (설계, 미구현)

**아직 구현하지 않았다.** Separation 베이스라인(commercial_6 결정)이 확정된 뒤에만 시작한다. 분리 튜닝과 섞지 않는다.

## 구조
Separation → Routing → RAW stem → RAW validation(13/13 계약, 합계 보존, NaN/Inf, 클리핑) → Restoration → FINAL stem → Final QC.
FINAL은 합계 보존을 요구하지 않는다. 중간 산출물 정리는 Restoration까지 끝난 뒤.

## R1 DSP (외부 AI 없음)
DC/subsonic 정리, 약한 spectral denoise, temporal smoothing, harmonic/transient 보호, 약한 tone correction. hard gate 금지, 감쇠는 −3/−6/−8 dB 후보부터. stem별 프로필을 분리(lead, backing, piano, guitar, acoustic_guitar, bass, drums, percussion, synth, strings, brass, other, guitar_residual).
- drums: 일반 spectral gate 금지. 어택 검출로 kick/snare/hi-hat/cymbal 어택과 cymbal tail 보호, 무음·sustain 구간의 artifact만 감쇠.
- strings/synth/pad: 매우 보수적(spectral smoothing 위주), 강한 gate/dereverb 금지.
- 기존 clarity(EQ) 중 유효한 부분은 이 단계의 tone correction으로 이동. clarity UI(ON/OFF, 강도 노브, 선명도 다운로드, 그냥/둘 다 받기)는 제거 예정.

## R2 보컬 AI restoration (R1 이후)
Lead/Backing 전용, 음성(speech) 모델을 악기에 적용 금지. 후보마다 RAW / 25 / 50 / 75 / 100 % wet 비교, vibrato·breath·falsetto·growl·distortion·reverb tail 손상 확인. exact checkpoint, SHA256, weight license 검증 전에는 후보로도 올리지 않는다.

## R3 Dereverb (필요할 때만)
Lead/Backing 중심. drums/strings/synth 기본 적용 금지. 분리 artifact와 원곡의 의도된 리버브를 구분하지 못하면 적용하지 않는다.

## 평가 방법
- GT 있는 합성 케이스: restoration 전/후 SDR, SI-SDR, leakage, 노이즈 floor, 어택 보존(onset 위치/에너지), 크레스트 팩터. 개선이 없으면 채택하지 않는다.
- 청취: 권리 보유 곡에서 instrument presence, bleed, missing notes, volume pumping, musical noise, metallic artifact, transient damage, reverb, tone, continuity.
- 회귀: restoration on/off에서 RAW는 바뀌지 않아야 한다.
