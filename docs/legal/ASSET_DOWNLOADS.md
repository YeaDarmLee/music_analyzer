# DF-0 Asset Downloads and Ingest Report

기준일 2026-10-08. 승인: Research Lead(사용자) — VocalSet, Big Little Bass, Sneakybass, Stargate, VCSL(sparse), VCSL Keys. VSCO 2 CE는 보류(Strings/Brass 단계). 기계가 읽는 사본: `df0_asset_report.json`. 레코드: `artifacts/assets/<id>.json`, 라이선스 스냅샷: `artifacts/licenses/<id>/LICENSE.txt`.
로컬 경로(`data/assets/…`, `data/derived/…`)는 gitignore 대상이며 저장소에는 해시·레코드·manifest만 남는다.

## 1. 자산별 결과

| asset | exact source | resolved version | 다운로드 크기 | LICENSE 원문 해시 (sha256) | asset 해시 (tree sha256) | 파일 수 | 최종 분류 | Production gate |
|---|---|---|---|---|---|---|---|---|
| `karoryfer_big_little_bass` | https://github.com/sfzinstruments/karoryfer.big-little-bass (`git clone --depth 1`) | commit `4e92bdf54dcd2d6cfad968cc90542d5461c9b9fc` (2024-12-05) | 체크아웃 318.2 MB + .git 263.6 MB | `f4e7f373b9b996950337e8d41a4a2939c2d90b7725e9baf3d5084a22717ad328` (repo `LICENSE`, CC0 1.0 Universal) | `fa0a0af3f216ed1b819786d13b97dc05fdcc0bc0853ee84a5452a8561995db6c` | 481 | **GREEN** CC0-1.0 | 통과 |
| `karoryfer_sneakybass` | https://github.com/sfzinstruments/karoryfer.sneakybass (`--depth 1`) | commit `cc1a67e5c913678b85eaad1a3b5cb180d3be3e2d` (2022-12-05) | 418.7 MB + .git 340.5 MB | `f4e7f373…ad328` (동일 CC0 텍스트) | `ba7bf9bf5546028477d402452d44601f673a2f4bb0725b99612d4b0715f92d84` | 715 | **GREEN** CC0-1.0 | 통과 |
| `stargate_sample_pack` | https://github.com/stargatedaw/stargate-sample-pack (`--depth 1`) | commit `dbfd6ec52d4ed53b60bdbea5fc6adf295127c027` (2022-12-24) | 270.7 MB + .git 197.3 MB | `50b0537fd5f8a4d4899b90d2e1e233a1bca53e56897b84785edd094b3a3d72b6` (repo `LICENSE`, CC0 1.0 Universal; GitHub SPDX 자동인식 NOASSERTION은 사용하지 않음) | `653338fc08cfd14c33452c9ff65f9270e3537b9317ae0706d61ec62a20ad3402` | 358 | **GREEN** CC0-1.0 (Research Lead 정정 승인) | 통과 |
| `vcsl` (sparse: 드럼/타악 11개 폴더만) | https://github.com/sgossner/VCSL (`--depth 1 --filter=blob:none --sparse`, 이후 sparse-checkout) | commit `c1ea7bcc3c7309650ab0da9d15c9cd1fbc4a4c7e` (2026-01-14) | 체크아웃 176.8 MB (+ 부분 clone .git 1.82 GB; 피아노 폴더 2.4 GB를 한 번 받았다가 sparse에서 제외 — VCSL Keys로 대체) | `f4e7f373…ad328` (repo `LICENSE`, CC0 1.0 Universal) | `a36d56fec3c10aafb6585a9416ce688775ed6a546e19521670d967c048dc8cc8` | 196 | **GREEN** CC0-1.0 | 통과 |
| `vcsl_keys` (별도 배포) | https://versilian-studios.com/Distro/VCSL_Keys.zip (공식 페이지 https://versilian-studios.com/vcsl-keys/) | archive sha256 `2e91c9aa7b16d936f035963149df1fe4cbd65911116fb3e3ea6daca52e92024b` (version = 앞 16자) | 655,370,475 B (Content-Length와 일치, `zip testzip` 통과) | `0dae6bfdfc9b9f227b798d6a4a04409804230d23f2ba78e2943cfc4fe7b5cfa6` (아카이브에 LICENSE 파일 없음 → 공식 페이지 문구 verbatim + VCSL CC0 법적 텍스트로 만든 증빙 스냅샷) | `27b9d75738b7ad7b2c3a6d671e6b93971fdd8882e72e9033d572b1577c6bcf04` (md5 `42b5c583e5945898f71ec93112f92f2d`) | 1481 | **GREEN** CC0-1.0 | 통과 |
| `vocalset` | https://zenodo.org/api/records/1203819/files/VocalSet11.zip/content (DOI 10.5281/zenodo.1203819, v1.1, 2018-03-08) | archive sha256 `df3dbe37b3dd840dce4bf7a4d2545d36daf38abc63a368f0e2003764aa7fa124` | 2,077,243,579 B, **md5 `0c09396242f946e7111ad7d8fc649b81` = Zenodo 기재값** | `4b3ea01d43cbfbb1adb214831cbf2ad0e842303c2929130d76863b644e306801` (Zenodo 레코드 메타 + CC BY 4.0 legalcode.txt) | `ab1b20927a78f65f2e6fe29b41a49eaddbeda1493b881feec5cea1ae797347f3` | 4225 | **GREEN_CONDITIONAL** CC-BY-4.0, attribution 필수 | 통과 (attribution_text 포함) |

총 다운로드: 아카이브 2.73 GB(VCSL Keys 0.66 + VocalSet 2.08) + git 저장소 5개(체크아웃 1.19 GB, .git 메타 2.62 GB) + 디코딩 사본 2.6 GB(`data/derived/vcsl_keys_wav`). 사전 안내(0.26/0.33/0.19 GB, VCSL 전체 4 GB)보다 큰 이유: GitHub API의 `size`는 압축된 저장소 값이고 체크아웃 + `.git` 객체가 이중으로 남는다.

## 2. Instrument manifest (`artifacts/instruments/*.json`)

| instrument | asset | zones | 방식 |
|---|---|---|---|
| `vcsl_keys_grand_k`, `vcsl_keys_steinway_b`, `vcsl_keys_upright_knight`, `vcsl_keys_upright_y` | `vcsl_keys` | 138 / 126 / 90 / 70 | 공식 SFZ, `--cc 64=127`(서스테인 페달 down 상태의 영역 선택). FLAC → float32 WAV 디코딩 사본 사용 |
| `blb_pluck_center` | `karoryfer_big_little_bass` | 440 | `Programs/maps/p_map.sfz`(+`hivel=63,seq_length=5`) + `f_map.sfz`(+`lovel=64,seq_length=5`), base-dir `Programs` |
| `sneakybass_pluck` | `karoryfer_sneakybass` | 160 | `Programs/modules/maps/sneakybass_pluck_map.sfz` 그대로 (seq_length=4 포함) |
| `vcsl_drums` | `vcsl` | 84 (kick 16, snare 24, tom 24, hat 11+2, crash 7) | 폴더/파일명 규칙, `hit|close`만, roll/cresc/tap/rim/bow/bell/legacy/loose/**HitNS(스네어 off)** 제외, 속도층은 `_v<k>_` |
| `stargate_drums` | `stargate_sample_pack` | 69 (kick 13, snare 11, tom 19, hat 9+6, crash 11) | `fugue-state-audio/drums`, `karoryfer/`, `microlag/One-Shots/Drums`만. **`freesound/` 하위 트리는 제외** |

## 3. SFZ critical opcode 호환성 / reject·warning 수

| 파일군 | 결과 |
|---|---|
| Karoryfer **프로그램** `.sfz` (BLB 18개, Sneakybass 27개) | 직접 ingest는 **reject**: `#include`, CC 게이트(`locc/hicc105`, `locc100`), `amplitude_cc`, `pan_cc`, `fil_type/cutoff` 등. → 프로그램 대신 순수 region 맵 파일(`*_map.sfz`)을 ingest하고 프로그램이 부여하던 `hivel/lovel/seq_length`를 명시 override로 기록(`ingest_overrides`) |
| Karoryfer 맵 (BLB p/f 440 region, Sneakybass 160 region) | reject 0, warning 0, 누락 샘플 0 |
| VCSL Keys 공식 SFZ 4개 (region 222/225/135/138) | critical opcode: `locc64/hicc64`(→ `cc_state` 64=127로 영역 선택, Steinway 126개 NoSus region 제외), `on_locc/on_hicc`(8개 제외). `trigger=release` 84/99/45/68개 skip(키-오프 노이즈 샘플 미사용). 비치명 미지원(경고만): `global_volume`, `amp_veltrack`, `ampeg_decay/sustain`, `rt_decay`. 누락 샘플 0 |
| VCSL / Stargate 드럼 | SFZ 없음 → 파일명 키워드 규칙. unmatched: VCSL 0, Stargate 30(claps/percussion 등 역할 없는 소리) |

알려진 영향: `global_volume`/`amp_veltrack` 무시로 피아노 레벨·다이내믹 곡선이 원 SFZ와 다르다(스템 레벨은 믹서가 active-RMS로 정규화). 페달-up(NoSus) 샘플과 키-오프 노이즈는 v0에서 사용하지 않는다.

## 4. 발견된 사항 (Research Lead 확인 필요)

1. **Stargate는 Freesound 사용자 업로드를 포함**(`freesound/` 하위 38개 파일)한다. Packet §6.7이 Freesound를 YELLOW(업로더 권리 검증 불가)로 둔 이유가 그대로 적용될 수 있어 kit에서 제외했다(`exclude` 목록이 manifest에 기록됨). 포함 여부는 결정 사항.
2. Stargate는 VCSL 사본(`sgossner/VCSL`)과 Karoryfer 샘플도 포함한다(중복). `karoryfer/` 하위는 사용 중이다.
3. VCSL 저장소의 피아노 폴더에는 SFZ가 없고(파일명 인코딩), SFZ는 VCSL Keys 배포본에 있다. 그래서 VCSL에서는 드럼 폴더만 사용한다.
4. VocalSet 아카이브에 **게시자 제공 singer split**(`train/test_singers_technique.txt`, 기술 분류기용)이 들어 있다. test 5명(female2, female8, male3, male5, male10)을 그대로 쓰고, 남은 가수 중 성별별 번호가 가장 높은 2명(female9, male11)을 val로 분리했다 (train 13명).
5. VocalSet: excerpts 139개 제외, `__MACOSX` 리소스 포크 2개 제외, 읽기 불가 0. 사용 가능 3474 clip (44.1 kHz 전부), 평균 8.2 s.
6. FLAC 디코딩에 **python-soundfile 0.13.1 / libsndfile 1.2.2(LGPL)** 를 ingest 시점에만 사용했다(런타임은 SciPy로 WAV만 읽음). 산출 오디오는 도구 라이선스의 영향을 받지 않지만 permissive-only 정책과의 관계는 결정 사항이다.
7. 정확한 VocalSet 인용 문구는 Zenodo 레코드가 제공한 생성자 목록(Wilkins, Julia; Prem Seetharaman; Alison Wahl; Bryan Pardo)을 그대로 썼다. 게시자가 요구하는 별도 인용문은 `NEEDS_RESEARCH`.

## 5. 다운로드 재현 명령

```
git clone --depth 1 https://github.com/sfzinstruments/karoryfer.big-little-bass data/assets/karoryfer_big_little_bass
git clone --depth 1 https://github.com/sfzinstruments/karoryfer.sneakybass data/assets/karoryfer_sneakybass
git clone --depth 1 https://github.com/stargatedaw/stargate-sample-pack data/assets/stargate_sample_pack
git clone --depth 1 --filter=blob:none --sparse https://github.com/sgossner/VCSL data/assets/VCSL   # + sparse-checkout (드럼 폴더)
curl -L -o data/assets/_downloads/VCSL_Keys.zip https://versilian-studios.com/Distro/VCSL_Keys.zip
curl -L -C - -o data/assets/_downloads/VocalSet11.zip https://zenodo.org/api/records/1203819/files/VocalSet11.zip/content
python scripts/df0_ingest.py git|zip …        # 해시·버전·라이선스 스냅샷 고정
python -m data_factory.cli ingest-sfz|ingest-drumkit|convert-flac|index-vocalset …
```
