# Full Project Disk Audit — dry-run 보고서 + 적용 결과 (13절)

측정 도구: `scripts/disk-audit.py`, `audit-library.py`, `audit-artifacts.py`, `audit-report.py`, `audio-format-benchmark.py`, `audit-doc.py`. 이 문서의 모든 수치는 읽기 전용 측정값이며, 판단이 어려운 항목은 UNKNOWN/REVIEW로 두었다. 하드링크는 inode당 한 번만 센 **물리 용량**이다.

## 0. 요약

| 구분 | 용량 |
|---|---:|
| 현재 전체 프로젝트 (물리) | **102.56 GB** (논리 103.25 GB, 차이는 하드링크) |
| 안전하게 바로 삭제 가능 (SAFE) | 7.24 GB |
| 사용자 확인 후 삭제 (REVIEW) | 85.18 GB |
| 유지 필수 (KEEP) | 8.73 GB |
| UNKNOWN (자동 삭제 금지) | 1.42 GB |

핵심: 프로젝트의 **약 98 %가 `data/`** 이고, 그중 **43.6 GB는 `data/separation/web`의 분석 50건**(최종 stem)이다. 코드·설정·문서·라이선스 증빙·`.git`은 합쳐서 0.1 GB 미만이다. `.git`은 9.3 MB(커밋 80개, 최대 blob 0.49 MB)라 과거에 대형 파일을 커밋한 흔적이 없다.

## 1. 용량 감사

### 1-1. 최상위 디렉터리

| Path | 물리 | 논리 | 파일 수 |
|---|---:|---:|---:|
| `data` | 97.47 GB | 98.17 GB | 28,260 |
| `.venv` | 4.85 GB | 4.85 GB | 30,552 |
| `song` | 0.13 GB | 0.13 GB | 25 |
| `frontend` | 0.09 GB | 0.09 GB | 4,871 |
| `.git` | 0.01 GB | 0.01 GB | 1,674 |
| `docs` | 0.00 GB | 0.00 GB | 105 |
| `separation` | 0.00 GB | 0.00 GB | 183 |
| `scripts` | 0.00 GB | 0.00 GB | 102 |

1 GB 이상 디렉터리 48개, 500 MB 이상 파일 12개.

### 1-2. 가장 큰 디렉터리 TOP 50 (물리 / 논리)

| # | Path | 물리 | 논리 | 파일 수 |
|---:|---|---:|---:|---:|
| 1 | `data` | 97.47 GB | 98.17 GB | 28,260 |
| 2 | `data/separation` | 64.52 GB | 64.52 GB | 19,310 |
| 3 | `data/separation/web` | 43.57 GB | 43.57 GB | 673 |
| 4 | `data/ground-truth` | 17.57 GB | 18.27 GB | 4,106 |
| 5 | `data/ground-truth/cases` | 15.53 GB | 16.22 GB | 4,038 |
| 6 | `data/pad-eval` | 12.71 GB | 12.71 GB | 3,180 |
| 7 | `data/pad-eval/cases` | 6.95 GB | 6.95 GB | 1,696 |
| 8 | `data/separation/tools` | 6.61 GB | 6.61 GB | 16,424 |
| 9 | `data/separation/models` | 6.40 GB | 6.40 GB | 40 |
| 10 | `data/separation/inputs` | 6.04 GB | 6.04 GB | 254 |
| 11 | `.venv` | 4.85 GB | 4.85 GB | 30,552 |
| 12 | `.venv/Lib` | 4.84 GB | 4.84 GB | 30,518 |
| 13 | `.venv/Lib/site-packages` | 4.84 GB | 4.84 GB | 30,518 |
| 14 | `data/pad-eval/cases-v16` | 4.62 GB | 4.62 GB | 1,224 |
| 15 | `.venv/Lib/site-packages/torch` | 4.27 GB | 4.27 GB | 12,515 |
| 16 | `data/separation/tools/AudioSep` | 3.38 GB | 3.38 GB | 145 |
| 17 | `data/separation/tools/CLAPSepInference` | 2.36 GB | 2.36 GB | 6 |
| 18 | `data/reset-backups` | 2.27 GB | 2.27 GB | 131 |
| 19 | `data/reset-backups/reset-20261006-193853` | 2.27 GB | 2.27 GB | 131 |
| 20 | `data/separation/jobs` | 1.87 GB | 1.87 GB | 1,860 |
| 21 | `data/separation/web/analysis_b7ad3591dc08445094818de0b4793dce` | 1.78 GB | 1.78 GB | 14 |
| 22 | `data/ground-truth/cases/stability-v15` | 1.60 GB | 1.73 GB | 408 |
| 23 | `data/ground-truth/cases/stability-v14` | 1.60 GB | 1.73 GB | 408 |
| 24 | `data/ground-truth/cases/stability-v13` | 1.60 GB | 1.73 GB | 408 |
| 25 | `data/ground-truth/cases/stability-v16` | 1.60 GB | 1.60 GB | 384 |
| 26 | `data/ground-truth/cases/stability-v12` | 1.60 GB | 1.73 GB | 408 |
| 27 | `data/ground-truth/cases/stability-v11` | 1.60 GB | 1.65 GB | 393 |
| 28 | `data/separation/models/melband_karaoke` | 1.60 GB | 1.60 GB | 2 |
| 29 | `data/separation/models/mega53_3head` | 1.39 GB | 1.39 GB | 4 |
| 30 | `data/separation/web/analysis_69470974ce0e4663bae0a48cf7111f85` | 1.37 GB | 1.37 GB | 14 |
| 31 | `data/separation/web/analysis_58e0372b18d54484b84bf73177516f19` | 1.37 GB | 1.37 GB | 14 |
| 32 | `data/separation/web/analysis_421fdbb03b294f71985f99a147871328` | 1.31 GB | 1.31 GB | 16 |
| 33 | `data/separation/web/analysis_4ca5fbde53e14386a2c5553a30a84202` | 1.29 GB | 1.29 GB | 15 |
| 34 | `data/separation/web/analysis_acf0815867e1498a81e1bc1080f4d173` | 1.28 GB | 1.28 GB | 16 |
| 35 | `data/separation/web/analysis_f7f0f15fc44e407da078177fc14adb81` | 1.27 GB | 1.27 GB | 16 |
| 36 | `data/separation/web/analysis_b1497af0ae2745e8adf5241a94701dbc` | 1.17 GB | 1.17 GB | 16 |
| 37 | `data/separation/web/analysis_4ca7b1f748a5482e838c9b516ea8d66a` | 1.14 GB | 1.14 GB | 16 |
| 38 | `data/separation/web/analysis_9effd64575e942cfb7221da7f58c3199` | 1.13 GB | 1.13 GB | 16 |
| 39 | `data/pad-eval/stems` | 1.10 GB | 1.10 GB | 224 |
| 40 | `data/separation/web/analysis_1054745c84ca432e8596e532011aae99` | 1.09 GB | 1.09 GB | 15 |
| 41 | `data/separation/web/analysis_931fab9c2aaf4842b1b238898343b5b6` | 1.09 GB | 1.09 GB | 15 |
| 42 | `data/separation/web/analysis_780b3ad1d085465bbe267b0829c78273` | 1.07 GB | 1.07 GB | 16 |
| 43 | `data/separation/web/analysis_35a9bb080dd846f891f9905e7cdf607e` | 1.03 GB | 1.03 GB | 15 |
| 44 | `data/separation/web/analysis_76a3c91976a0496eb1e83cb1e3863250` | 1.02 GB | 1.02 GB | 16 |
| 45 | `data/ground-truth/slakh` | 1.00 GB | 1.00 GB | 30 |
| 46 | `data/separation/web/analysis_91f2b6fcb80547bb87e00078ecbb16fc` | 1.00 GB | 1.00 GB | 15 |
| 47 | `data/separation/web/analysis_7bbb8cda67fc49fcb1f2745c4224d3f3` | 1.00 GB | 1.00 GB | 14 |
| 48 | `data/separation/web/analysis_b7b5346eb91e42d3a52bbf5a18f1c73b` | 1.00 GB | 1.00 GB | 14 |
| 49 | `data/separation/web/analysis_c0c5c30c97e8439fa71d996ed05ca307` | 1.00 GB | 1.00 GB | 15 |
| 50 | `data/separation/web/analysis_4e1526b69dce46a3a39fd21b28a7a785` | 1.00 GB | 1.00 GB | 15 |

### 1-3. 500 MB 이상 개별 파일

| Path | 물리 | 링크 수 |
|---|---:|---:|
| `data/separation/tools/AudioSep/checkpoint/music_speech_audioset_epoch_15_esc_89.98.pt` | 2.19 GB | 1 |
| `data/separation/tools/CLAPSepInference/model/music_audioset_epoch_15_esc_90.14.pt` | 2.19 GB | 1 |
| `data/separation/models/melband_karaoke/mel_band_roformer_karaoke_becruily.ckpt` | 1.60 GB | 1 |
| `data/separation/models/mega53_3head/official-53.ckpt` | 1.27 GB | 1 |
| `data/separation/tools/AudioSep/checkpoint/audiosep_base_4M_steps.ckpt` | 1.18 GB | 1 |
| `.venv/Lib/site-packages/torch/lib/torch_cuda.dll` | 0.86 GB | 1 |
| `data/separation/models/melband_roformer_kj/MelBandRoformer.ckpt` | 0.85 GB | 1 |
| `data/ground-truth/slakh/babyslakh_16k.tar.gz` | 0.82 GB | 1 |
| `data/separation/models/bs_roformer_6s/bs_6stem_fixed.ckpt` | 0.65 GB | 1 |
| `.venv/Lib/site-packages/torch/lib/dnnl.lib` | 0.61 GB | 1 |
| `.venv/Lib/site-packages/torch/lib/cudnn_engines_precompiled64_9.dll` | 0.55 GB | 1 |
| `.venv/Lib/site-packages/torch/lib/cublasLt64_12.dll` | 0.50 GB | 1 |

### 1-4. 가장 큰 파일 TOP 100 (100 MB 이상만 존재하는 목록)

| # | Path | 크기 | 링크 |
|---:|---|---:|---:|
| 1 | `data/separation/tools/AudioSep/checkpoint/music_speech_audioset_epoch_15_esc_89.98.pt` | 2,243 MB | 1 |
| 2 | `data/separation/tools/CLAPSepInference/model/music_audioset_epoch_15_esc_90.14.pt` | 2,243 MB | 1 |
| 3 | `data/separation/models/melband_karaoke/mel_band_roformer_karaoke_becruily.ckpt` | 1,639 MB | 1 |
| 4 | `data/separation/models/mega53_3head/official-53.ckpt` | 1,306 MB | 1 |
| 5 | `data/separation/tools/AudioSep/checkpoint/audiosep_base_4M_steps.ckpt` | 1,206 MB | 1 |
| 6 | `.venv/Lib/site-packages/torch/lib/torch_cuda.dll` | 885 MB | 1 |
| 7 | `data/separation/models/melband_roformer_kj/MelBandRoformer.ckpt` | 871 MB | 1 |
| 8 | `data/ground-truth/slakh/babyslakh_16k.tar.gz` | 842 MB | 1 |
| 9 | `data/separation/models/bs_roformer_6s/bs_6stem_fixed.ckpt` | 667 MB | 1 |
| 10 | `.venv/Lib/site-packages/torch/lib/dnnl.lib` | 623 MB | 1 |
| 11 | `.venv/Lib/site-packages/torch/lib/cudnn_engines_precompiled64_9.dll` | 562 MB | 1 |
| 12 | `.venv/Lib/site-packages/torch/lib/cublasLt64_12.dll` | 514 MB | 1 |
| 13 | `data/ground-truth/medleydb/MedleyDB_Sample.tar.gz` | 396 MB | 1 |
| 14 | `data/separation/tools/wesep-reference/checkpoint/avg_model.pt` | 270 MB | 1 |
| 15 | `.venv/Lib/site-packages/torch/lib/cusparse64_12.dll` | 250 MB | 1 |
| 16 | `data/separation/tools/wesep-reference/bsrnn_ecapa_vox1.tar.gz` | 249 MB | 1 |
| 17 | `data/ground-truth/philharmonia/all-samples.zip` | 249 MB | 1 |
| 18 | `.venv/Lib/site-packages/torch/lib/torch_cpu.dll` | 238 MB | 1 |
| 19 | `.venv/Lib/site-packages/torch/lib/cudnn_adv64_9.dll` | 230 MB | 1 |
| 20 | `data/separation/models/bs_roformer_mega7/mega7.ckpt` | 216 MB | 1 |
| 21 | `data/separation/models/bs_karaoke/bs_roformer_karaoke_frazer_becruily.ckpt` | 195 MB | 1 |
| 22 | `data/separation/models/bs_roformer_mega6/mega6.ckpt` | 192 MB | 1 |
| 23 | `.venv/Lib/site-packages/torch/lib/cufft64_11.dll` | 182 MB | 1 |
| 24 | `data/separation/tools/CLAPSepInference/model/best_model.ckpt` | 170 MB | 1 |
| 25 | `data/separation/models/mega53_5head/mega53-5head.ckpt` | 169 MB | 1 |
| 26 | `data/separation/models/mega53_5head_bowed/mega53-5head.ckpt` | 169 MB | 1 |
| 27 | `data/separation/models/bs_roformer_mega5/mega5.ckpt` | 169 MB | 1 |
| 28 | `data/separation/web/analysis_b7ad3591dc08445094818de0b4793dce/original.wav` | 152 MB | 1 |
| 29 | `data/separation/web/analysis_b7ad3591dc08445094818de0b4793dce/final/acoustic_guitar.wav` | 152 MB | 1 |
| 30 | `data/separation/web/analysis_b7ad3591dc08445094818de0b4793dce/final/backing.wav` | 152 MB | 1 |
| 31 | `data/separation/web/analysis_b7ad3591dc08445094818de0b4793dce/final/bass.wav` | 152 MB | 1 |
| 32 | `data/separation/web/analysis_b7ad3591dc08445094818de0b4793dce/final/brass.wav` | 152 MB | 1 |
| 33 | `data/separation/web/analysis_b7ad3591dc08445094818de0b4793dce/final/drums.wav` | 152 MB | 1 |
| 34 | `data/separation/web/analysis_b7ad3591dc08445094818de0b4793dce/final/guitar.wav` | 152 MB | 1 |
| 35 | `data/separation/web/analysis_b7ad3591dc08445094818de0b4793dce/final/lead.wav` | 152 MB | 1 |
| 36 | `data/separation/web/analysis_b7ad3591dc08445094818de0b4793dce/final/other.wav` | 152 MB | 1 |
| 37 | `data/separation/web/analysis_b7ad3591dc08445094818de0b4793dce/final/piano.wav` | 152 MB | 1 |
| 38 | `data/separation/web/analysis_b7ad3591dc08445094818de0b4793dce/final/strings.wav` | 152 MB | 1 |
| 39 | `data/separation/web/analysis_b7ad3591dc08445094818de0b4793dce/final/synth.wav` | 152 MB | 1 |
| 40 | `data/separation/models/bs_roformer_core4/core4.ckpt` | 145 MB | 1 |
| 41 | `data/separation/models/bs_roformer_mega4/mega4.ckpt` | 145 MB | 1 |
| 42 | `data/separation/inputs/asset_1cc4954efa6c4ba6bdc39a2043141a38/canonical.wav` | 126 MB | 1 |
| 43 | `data/separation/inputs/asset_1cc4954efa6c4ba6bdc39a2043141a38/original.wav` | 126 MB | 1 |
| 44 | `data/separation/inputs/asset_4aa1a40e7f3f4d3ca7138bd68a262634/canonical.wav` | 126 MB | 1 |
| 45 | `data/separation/inputs/asset_4aa1a40e7f3f4d3ca7138bd68a262634/original.wav` | 126 MB | 1 |
| 46 | `data/separation/models/mega53_3head/mega53-3head.ckpt` | 121 MB | 1 |
| 47 | `data/separation/inputs/asset_1df7223c929c4c5dbe8860cfa131cb4e/canonical.wav` | 117 MB | 1 |
| 48 | `data/separation/inputs/asset_5dec38a4477d4512978da4833e925ddf/canonical.wav` | 117 MB | 1 |
| 49 | `data/separation/inputs/asset_5dec38a4477d4512978da4833e925ddf/original.wav` | 117 MB | 1 |
| 50 | `data/separation/inputs/asset_c1e29e785dd347b395301babe5dba6f5/canonical.wav` | 117 MB | 1 |
| 51 | `data/separation/inputs/asset_c1e29e785dd347b395301babe5dba6f5/original.wav` | 117 MB | 1 |
| 52 | `data/separation/web/analysis_69470974ce0e4663bae0a48cf7111f85/original.wav` | 117 MB | 1 |
| 53 | `data/separation/web/analysis_69470974ce0e4663bae0a48cf7111f85/final/acoustic_guitar.wav` | 117 MB | 1 |
| 54 | `data/separation/web/analysis_69470974ce0e4663bae0a48cf7111f85/final/backing.wav` | 117 MB | 1 |
| 55 | `data/separation/web/analysis_69470974ce0e4663bae0a48cf7111f85/final/bass.wav` | 117 MB | 1 |
| 56 | `data/separation/web/analysis_69470974ce0e4663bae0a48cf7111f85/final/brass.wav` | 117 MB | 1 |
| 57 | `data/separation/web/analysis_69470974ce0e4663bae0a48cf7111f85/final/drums.wav` | 117 MB | 1 |
| 58 | `data/separation/web/analysis_69470974ce0e4663bae0a48cf7111f85/final/guitar.wav` | 117 MB | 1 |
| 59 | `data/separation/web/analysis_69470974ce0e4663bae0a48cf7111f85/final/lead.wav` | 117 MB | 1 |
| 60 | `data/separation/web/analysis_69470974ce0e4663bae0a48cf7111f85/final/other.wav` | 117 MB | 1 |
| 61 | `data/separation/web/analysis_69470974ce0e4663bae0a48cf7111f85/final/piano.wav` | 117 MB | 1 |
| 62 | `data/separation/web/analysis_69470974ce0e4663bae0a48cf7111f85/final/strings.wav` | 117 MB | 1 |
| 63 | `data/separation/web/analysis_69470974ce0e4663bae0a48cf7111f85/final/synth.wav` | 117 MB | 1 |
| 64 | `data/separation/inputs/asset_2460ccf484e64a89910c240741e896cb/canonical.wav` | 117 MB | 1 |
| 65 | `data/separation/inputs/asset_87ae48f1dbcb4530b06befa201634842/canonical.wav` | 117 MB | 1 |
| 66 | `data/separation/inputs/asset_87ae48f1dbcb4530b06befa201634842/original.wav` | 117 MB | 1 |
| 67 | `data/separation/inputs/asset_aa52294bdcea440f98cfdc69986dbb6d/canonical.wav` | 117 MB | 1 |
| 68 | `data/separation/inputs/asset_aa52294bdcea440f98cfdc69986dbb6d/original.wav` | 117 MB | 1 |
| 69 | `data/separation/web/analysis_58e0372b18d54484b84bf73177516f19/original.wav` | 117 MB | 1 |
| 70 | `data/separation/web/analysis_58e0372b18d54484b84bf73177516f19/final/acoustic_guitar.wav` | 117 MB | 1 |
| 71 | `data/separation/web/analysis_58e0372b18d54484b84bf73177516f19/final/backing.wav` | 117 MB | 1 |
| 72 | `data/separation/web/analysis_58e0372b18d54484b84bf73177516f19/final/bass.wav` | 117 MB | 1 |
| 73 | `data/separation/web/analysis_58e0372b18d54484b84bf73177516f19/final/brass.wav` | 117 MB | 1 |
| 74 | `data/separation/web/analysis_58e0372b18d54484b84bf73177516f19/final/drums.wav` | 117 MB | 1 |
| 75 | `data/separation/web/analysis_58e0372b18d54484b84bf73177516f19/final/guitar.wav` | 117 MB | 1 |
| 76 | `data/separation/web/analysis_58e0372b18d54484b84bf73177516f19/final/lead.wav` | 117 MB | 1 |
| 77 | `data/separation/web/analysis_58e0372b18d54484b84bf73177516f19/final/other.wav` | 117 MB | 1 |
| 78 | `data/separation/web/analysis_58e0372b18d54484b84bf73177516f19/final/piano.wav` | 117 MB | 1 |
| 79 | `data/separation/web/analysis_58e0372b18d54484b84bf73177516f19/final/strings.wav` | 117 MB | 1 |
| 80 | `data/separation/web/analysis_58e0372b18d54484b84bf73177516f19/final/synth.wav` | 117 MB | 1 |
| 81 | `.venv/Lib/site-packages/llvmlite/binding/llvmlite.dll` | 115 MB | 1 |
| 82 | `data/separation/inputs/asset_18ac394ddd8f4c0e9d7aef097b26b9ef/canonical.wav` | 110 MB | 1 |
| 83 | `data/separation/inputs/asset_18ac394ddd8f4c0e9d7aef097b26b9ef/original.wav` | 110 MB | 1 |
| 84 | `data/separation/inputs/asset_1923eb56670a4e47aa08e802886b59e3/canonical.wav` | 110 MB | 1 |
| 85 | `data/separation/inputs/asset_bea61bcddeaf4d89a2f425a9a013c608/canonical.wav` | 110 MB | 1 |
| 86 | `data/separation/inputs/asset_bea61bcddeaf4d89a2f425a9a013c608/original.wav` | 110 MB | 1 |
| 87 | `.venv/Lib/site-packages/torch/lib/cusolver64_11.dll` | 105 MB | 1 |
| 88 | `.venv/Lib/site-packages/torch/lib/cudnn_ops64_9.dll` | 103 MB | 1 |
| 89 | `data/separation/web/analysis_4ca5fbde53e14386a2c5553a30a84202/original.wav` | 101 MB | 1 |
| 90 | `data/separation/web/analysis_4ca5fbde53e14386a2c5553a30a84202/final/acoustic_guitar.wav` | 101 MB | 1 |
| 91 | `data/separation/web/analysis_4ca5fbde53e14386a2c5553a30a84202/final/backing.wav` | 101 MB | 1 |
| 92 | `data/separation/web/analysis_4ca5fbde53e14386a2c5553a30a84202/final/bass.wav` | 101 MB | 1 |
| 93 | `data/separation/web/analysis_4ca5fbde53e14386a2c5553a30a84202/final/brass.wav` | 101 MB | 1 |
| 94 | `data/separation/web/analysis_4ca5fbde53e14386a2c5553a30a84202/final/drums.wav` | 101 MB | 1 |
| 95 | `data/separation/web/analysis_4ca5fbde53e14386a2c5553a30a84202/final/guitar.wav` | 101 MB | 1 |
| 96 | `data/separation/web/analysis_4ca5fbde53e14386a2c5553a30a84202/final/guitar_residual.wav` | 101 MB | 1 |
| 97 | `data/separation/web/analysis_4ca5fbde53e14386a2c5553a30a84202/final/lead.wav` | 101 MB | 1 |
| 98 | `data/separation/web/analysis_4ca5fbde53e14386a2c5553a30a84202/final/other.wav` | 101 MB | 1 |
| 99 | `data/separation/web/analysis_4ca5fbde53e14386a2c5553a30a84202/final/piano.wav` | 101 MB | 1 |
| 100 | `data/separation/web/analysis_4ca5fbde53e14386a2c5553a30a84202/final/strings.wav` | 101 MB | 1 |

(100 MB 이상 파일은 총 101개. 하드링크는 `data/ground-truth/cases`에만 일부 있다. 차이 0.69 GB는 `data/ground-truth/cases` 안의 하드링크(버전 폴더 사이에 이미 공유된 reference)다.)

## 2. 분류 (A–I) × 위험도

| 카테고리 | 위험도 | 용량 | 파일 수 |
|---|---|---:|---:|
| B USER_PERSISTENT | REVIEW | 43.12 GB | 1,200 |
| D REGENERABLE | REVIEW | 27.09 GB | 6,827 |
| E DEV_TOOL | REVIEW | 12.70 GB | 16,512 |
| H ORPHAN | SAFE | 6.94 GB | 203 |
| A PRODUCTION_REQUIRED | KEEP | 6.16 GB | 24,451 |
| C TEST_FIXTURE_REQUIRED | KEEP | 2.57 GB | 1,790 |
| G LEGACY_BACKUP | REVIEW | 2.27 GB | 131 |
| I UNKNOWN | UNKNOWN | 1.42 GB | 30 |
| F CACHE | SAFE | 0.30 GB | 14,519 |

| 항목 | 카테고리 | 위험도 | 용량 | 파일 |
|---|---|---|---:|---:|
| library analysis - MANUAL_TEST (visible in the dev accounts' library) | B | REVIEW | 23.10 GB | 330 |
| library analysis - BENCHMARK (visible in the dev accounts' library) | B | REVIEW | 17.52 GB | 282 |
| case mixtures/references (regenerable from the sources above) | D | REVIEW | 15.53 GB | 3,901 |
| case references / reports of the synthetic benchmark | D | REVIEW | 11.57 GB | 2,920 |
| orphan input asset (no job, record or pipeline names it) | H | SAFE | 5.33 GB | 137 |
| .venv (runtime; rebuildable from requirements but required to run) | A | KEEP | 4.67 GB | 20,873 |
| AudioSep / wesep research tools (no production or baseline path) | E | REVIEW | 4.13 GB | 12,913 |
| non-production weights (UNKNOWN license / experiments / baseline final_11) | E | REVIEW | 3.54 GB | 26 |
| CLAPSep stack (needed only by the final_11 BASELINE cymbal path) | E | REVIEW | 2.47 GB | 3,511 |
| reset-20261006 backup (5 study analyses, none in the DB) | G | REVIEW | 2.27 GB | 131 |
| production checkpoints (APPROVED) | A | KEEP | 1.46 GB | 10 |
| library analysis - UNKNOWN | I | UNKNOWN | 1.42 GB | 21 |
| official-53 source checkpoint + 3-head experiment (provenance for pruned heads) | E | REVIEW | 1.39 GB | 4 |
| scratch of the FAILED analysis | H | SAFE | 1.29 GB | 52 |
| library analysis - DEMO (visible in the dev accounts' library) | B | REVIEW | 1.20 GB | 25 |
| rendered synthetic GT stems + tools (clean benchmark source) | C | KEEP | 1.14 GB | 254 |
| license-clean benchmark sources (BabySlakh CC BY, FreePats CC0) | C | KEEP | 1.03 GB | 35 |
| license-excluded datasets (only the final_11 baseline reports used them) | E | REVIEW | 1.02 GB | 33 |
| stand-alone job result shown in the library | B | REVIEW | 0.91 GB | 455 |
| input of a stand-alone job result shown in the library | B | REVIEW | 0.39 GB | 108 |
| demo song mix + stems | C | KEEP | 0.34 GB | 28 |
| FAILED analysis record (no deliverable) | H | SAFE | 0.32 GB | 14 |
| .venv __pycache__ | F | SAFE | 0.18 GB | 9,679 |
| song/ (developer's local commercial mp3 collection, not tracked) | E | REVIEW | 0.13 GB | 25 |
| build / dependency caches | F | SAFE | 0.08 GB | 4,750 |
| benchmark reports / metrics (commercial_13/6) | C | KEEP | 0.06 GB | 474 |
| old smoke output / logs / runtime markers | F | SAFE | 0.03 GB | 51 |
| playback / download caches | F | SAFE | 0.01 GB | 1 |
| source, config, docs, license evidence, frontend | A | KEEP | 0.01 GB | 521 |
| .git | A | KEEP | 0.01 GB | 1,685 |

UNKNOWN은 자동 삭제 대상이 아니다. 위험도 정의: SAFE=지금 지워도 기능·사용자 데이터 손실 없음 (삭제 직전 재검증), REVIEW=사용자 확인 필요, KEEP=유지.

## 3. `data/separation` 분석 50건 재분류

**중요한 한계**: `REAL_USER`로 증명할 수 있는 분석은 **0건**이다. DB에는 계정이 2개뿐이고(둘 다 2026-10-06 생성, 개발 계정), 그중 한 계정이 48건, 다른 계정이 1건을 소유하며 1건(FAILED)은 소유자가 없다. 외부 실사용자가 만든 분석이라는 근거가 없고, 대부분의 원곡이 개발자의 로컬 `song/` 폴더(상용 음원 25개)에 있는 파일이다. 그래도 이 분석들은 개발 계정의 라이브러리에 **노출되어 있으므로** 삭제 후보가 아니라 **REVIEW**(사용자 확인 후)로 둔다. NTFS의 마지막 접근 시각 갱신이 꺼져 있어(`DisableLastAccess=1`) '마지막 접근'은 알 수 없고, 아래 `수정일`(record.json) 만 제공한다.

분류 근거: DEMO=사용자가 권리 확인한 AI 생성 샘플곡 / BENCHMARK=다른 분석에서 파생됐거나 같은 원곡을 나중에 다른 파이프라인 버전으로 다시 분석한 이전 판 / MANUAL_TEST=원본이 `song/`의 파일 / UNKNOWN=그 외.

| id | 생성일 | preset (version) | 상태 | 소유 | 이름 | final | original | 폴더 합계(회수 가능) | 수정일 | 분류 | 근거 |
|---|---|---|---|---|---|---:|---:|---:|---|---|---|
| 18f1c73b | 2026-10-06T15:54 | final_10 (v5) | SUCCEEDED | 6ff80a | 아이유(IU) - 분홍신 [가사 Lyrics] | 941 MB | 86 MB | 1,027 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source '아이유(IU) - 분홍신 [가사 Lyrics].mp3' was analysed again later  |
| 911d1dca | 2026-10-06T16:03 | final_10 (v5) | SUCCEEDED | 6ff80a | MyGO!!!!!-壱雫空 | 702 MB | 64 MB | 766 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source 'MyGO!!!!!-壱雫空.mp3' was analysed again later with another |
| f60c7cfe | 2026-10-06T16:10 | final_10 (v5) | FAILED | - | millsage - 기사개전 (起死開戦) | 0 MB | 0 MB | 332 MB | 2026-10-06 | **BENCHMARK** | older iteration: the same source 'millsage-(起死開戦.mp3' was analysed again later with anothe |
| fc67d335 | 2026-10-06T16:15 | final_10 (v5) | SUCCEEDED | 6ff80a | millsage - 기사개전 (起死開戦) | 723 MB | 66 MB | 789 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source 'millsage-(起死開戦.mp3' was analysed again later with anothe |
| b4793dce | 2026-10-06T16:23 | final_10 (v5) | SUCCEEDED | 6ff80a | 주님의 선하심 Goodness of God albastian  | 1,667 MB | 152 MB | 1,818 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/주님의 선하심 Goodness of God albastian live worship vol.3.mp3 (developer's  |
| 729b4ed1 | 2026-10-06T16:37 | final_10 (v5) | SUCCEEDED | 6ff80a | My Name is Malguem (내 이름 맑음) | 697 MB | 63 MB | 760 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/My Name is Malguem (내 이름 맑음).mp3 (developer's local collection of comm |
| f7111f85 | 2026-10-06T16:47 | final_10 (v5) | SUCCEEDED | 6ff80a | 아름다운 나라 Kingdom Beautiful [WELOVE] | 1,289 MB | 117 MB | 1,406 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/아름다운 나라 Kingdom Beautiful [WELOVE].mp3 (developer's local collection o |
| 8c140611 | 2026-10-06T17:11 | final_10 (v5) | SUCCEEDED | 6ff80a | MyGO!!!!!-壱雫空 | 702 MB | 64 MB | 766 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source 'MyGO!!!!!-壱雫空.mp3' was analysed again later with another |
| 4224d3f3 | 2026-10-06T17:19 | final_10 (v5) | SUCCEEDED | 6ff80a | 아이유(IU) - 분홍신 [가사 Lyrics] | 941 MB | 86 MB | 1,027 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source '아이유(IU) - 분홍신 [가사 Lyrics].mp3' was analysed again later  |
| 261d02cb | 2026-10-06T17:27 | final_10 (v5) | SUCCEEDED | 6ff80a | 알바스천-미라클 제너레이션 | 892 MB | 81 MB | 973 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source '알바스천-미라클 제너레이션.mp3' was analysed again later with anothe |
| 6e2f464d | 2026-10-06T18:56 | final_10 (v5) | SUCCEEDED | 6ff80a | 알바스천-미라클 제너레이션 | 892 MB | 81 MB | 973 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source '알바스천-미라클 제너레이션.mp3' was analysed again later with anothe |
| 77516f19 | 2026-10-06T19:10 | final_10 (v5) | SUCCEEDED | 6ff80a | WELOVE - 시간을 뚫고 (The Time, Penetra | 1,288 MB | 117 MB | 1,405 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/WELOVE - 시간을 뚫고 (The Time, Penetrated Eng, CHN Sub).mp3 (developer's l |
| 71e1efc0 | 2026-10-06T19:49 | basic_2 (-) | SUCCEEDED | 6ff80a | SPYAIR - サムライハート(Some Like It Hot! | 129 MB | 64 MB | 193 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/SPYAIR - サムライハート(Some Like It Hot!!).mp3 (developer's local collection |
| 662b89d2 | 2026-10-06T19:51 | bs_karaoke (-) | SUCCEEDED | 6ff80a | SPYAIR - サムライハート(Some Like It Hot! | 129 MB | 64 MB | 193 MB | 2026-10-08 | **BENCHMARK** | derived from another analysis (parent_analysis_id / '보완' / '리드/코러스' in the name) |
| a382cc37 | 2026-10-06T19:53 | basic_6 (-) | SUCCEEDED | 6ff80a | 아이유(IU) - 분홍신 [가사 Lyrics] | 513 MB | 86 MB | 599 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source '아이유(IU) - 분홍신 [가사 Lyrics].mp3' was analysed again later  |
| 145ff851 | 2026-10-06T20:01 | basic_6 (-) | SUCCEEDED | 6ff80a | 아이유(IU) - Blueming(블루밍) | 439 MB | 73 MB | 512 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source '아이유(IU) - Blueming(블루밍).mp3' was analysed again later wi |
| f8f1ca6e | 2026-10-06T20:07 | final_11 (recovery-v7) | SUCCEEDED | 6ff80a | 아이유(IU) - Blueming(블루밍) | 804 MB | 73 MB | 877 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source '아이유(IU) - Blueming(블루밍).mp3' was analysed again later wi |
| e5c3a195 | 2026-10-06T20:25 | final_11 (guitar-residual-v8) | SUCCEEDED | 6ff80a | 아이유(IU) - Blueming(블루밍) | 877 MB | 73 MB | 950 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source '아이유(IU) - Blueming(블루밍).mp3' was analysed again later wi |
| 011aae99 | 2026-10-06T20:35 | final_11 (guitar-residual-v8) | SUCCEEDED | 6ff80a | 아이유(IU) - 분홍신 [가사 Lyrics] | 1,027 MB | 86 MB | 1,112 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source '아이유(IU) - 분홍신 [가사 Lyrics].mp3' was analysed again later  |
| 7cdf607e | 2026-10-06T20:48 | final_11 (guitar-residual-v8) | SUCCEEDED | 6ff80a | 알바스천-미라클 제너레이션 | 973 MB | 81 MB | 1,054 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/알바스천-미라클 제너레이션.mp3 (developer's local collection of commercial tracks) |
| ecbb16fc | 2026-10-06T20:58 | final_11 (guitar-residual-v8) | SUCCEEDED | 6ff80a | 스파이에어(SPYAIR) - Orange | 948 MB | 79 MB | 1,027 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/스파이에어(SPYAIR) - Orange.mp3 (developer's local collection of commercial |
| d05ca307 | 2026-10-06T21:08 | final_11 (guitar-residual-v8) | SUCCEEDED | 6ff80a | sumika - 픽션(フィクション) | 942 MB | 79 MB | 1,021 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source 'sumika - 픽션(フィクション).mp3' was analysed again later with a |
| 30a84202 | 2026-10-06T21:28 | final_11 (guitar-residual-v8) | SUCCEEDED | 6ff80a | 윤하(YOUNHA) - 사건의 지평선 | 1,216 MB | 101 MB | 1,317 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/윤하(YOUNHA) - 사건의 지평선.mp3 (developer's local collection of commercial t |
| 4a0eaa6b | 2026-10-06T21:42 | final_11 (guitar-residual-v8) | SUCCEEDED | 6ff80a | 아이유(IU) - strawberry moon | 829 MB | 69 MB | 898 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source '아이유(IU) - strawberry moon.mp3' was analysed again later  |
| 0d991426 | 2026-10-06T22:39 | final_11 (guitar-residual-v9) | SUCCEEDED | 6ff80a | millsage - 기사개전 (起死開戦) | 789 MB | 66 MB | 855 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/millsage-(起死開戦.mp3 (developer's local collection of commercial tracks) |
| 28a7a785 | 2026-10-06T22:46 | final_11 (guitar-residual-v9) | SUCCEEDED | 6ff80a | sumika - 픽션(フィクション) | 942 MB | 79 MB | 1,021 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source 'sumika - 픽션(フィクション).mp3' was analysed again later with a |
| 8343b5b6 | 2026-10-06T23:03 | final_11 (guitar-residual-v9) | SUCCEEDED | 6ff80a | 아이유(IU) - 분홍신 [가사 Lyrics] | 1,027 MB | 86 MB | 1,112 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source '아이유(IU) - 분홍신 [가사 Lyrics].mp3' was analysed again later  |
| aa198a47 | 2026-10-06T23:11 | basic_2 (-) | SUCCEEDED | 6ff80a | 아이유(IU) - Blueming(블루밍) | 146 MB | 73 MB | 219 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source '아이유(IU) - Blueming(블루밍).mp3' was analysed again later wi |
| 555eb610 | 2026-10-06T23:13 | basic_6 (-) | SUCCEEDED | 6ff80a | 아이유(IU) - Blueming(블루밍) | 439 MB | 73 MB | 512 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/아이유(IU) - Blueming(블루밍).mp3 (developer's local collection of commercia |
| 072b74b5 | 2026-10-06T23:16 | basic_2 (-) | SUCCEEDED | 6ff80a | 너의 이름은 OST - Sparkle | 187 MB | 93 MB | 280 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source '너의 이름은 OST - Sparkle.mp3' was analysed again later with  |
| 03e2ccd7 | 2026-10-06T23:19 | final_11 (guitar-residual-v9) | SUCCEEDED | 6ff80a | imase - Fiction | 778 MB | 65 MB | 843 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/imase - Fiction.mp3 (developer's local collection of commercial tracks |
| f5a5b045 | 2026-10-06T23:29 | final_11 (guitar-residual-v9) | SUCCEEDED | 6ff80a | (한글자막) 코미 양은 커뮤증입니다 OP Full - 신데렐라 | 913 MB | 76 MB | 989 MB | 2026-10-08 | **BENCHMARK** | older iteration: the same source '(한글자막) 코미 양은 커뮤증입니다 OP Full - 신데렐라 사이다 걸.mp3' was analys |
| 22c70f29 | 2026-10-06T23:47 | basic_6 (-) | SUCCEEDED | 6ff80a | (한글자막) 코미 양은 커뮤증입니다 OP Full - 신데렐라 | 456 MB | 76 MB | 533 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/(한글자막) 코미 양은 커뮤증입니다 OP Full - 신데렐라 사이다 걸.mp3 (developer's local collec |
| a8c56e42 | 2026-10-07T00:27 | final_11 (context-percussion-v11) | SUCCEEDED | 6ff80a | millsage - 기사개전 (起死開戦) · 13트랙 보완 | 855 MB | 66 MB | 921 MB | 2026-10-08 | **BENCHMARK** | derived from another analysis (parent_analysis_id / '보완' / '리드/코러스' in the name) |
| c95296bf | 2026-10-07T01:06 | final_11 (context-percussion-v12) | SUCCEEDED | 6ff80a | millsage - 기사개전 (起死開戦) · 13트랙 보완 v | 855 MB | 66 MB | 921 MB | 2026-10-08 | **BENCHMARK** | derived from another analysis (parent_analysis_id / '보완' / '리드/코러스' in the name) |
| f62cb50c | 2026-10-07T01:40 | final_11 (context-percussion-v12) | SUCCEEDED | 6ff80a | 아이유(IU) - strawberry moon | 898 MB | 69 MB | 967 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/아이유(IU) - strawberry moon.mp3 (developer's local collection of commerc |
| 6ea8d66a | 2026-10-07T02:09 | final_11 (context-percussion-v12) | SUCCEEDED | 6ff80a | 엔플라잉 - Flashback | 1,084 MB | 83 MB | 1,167 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/엔플라잉 - Flashback.mp3 (developer's local collection of commercial track |
| 6385da45 | 2026-10-07T02:48 | final_11 (context-percussion-v12) | SUCCEEDED | 6ff80a | METEOR | 862 MB | 66 MB | 928 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/METEOR.mp3 (developer's local collection of commercial tracks) |
| 94701dbc | 2026-10-07T03:03 | final_11 (context-percussion-v12) | SUCCEEDED | 6ff80a | 아이유(IU) - 분홍신 [가사 Lyrics] | 1,112 MB | 86 MB | 1,198 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/아이유(IU) - 분홍신 [가사 Lyrics].mp3 (developer's local collection of commerc |
| f58c3199 | 2026-10-07T03:26 | final_11 (context-percussion-v12) | SUCCEEDED | 6ff80a | 브로큰발렌타인 Broken Valentine - 화석의노래 | 1,072 MB | 82 MB | 1,154 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/브로큰발렌타인 Broken Valentine - 화석의노래.mp3 (developer's local collection of  |
| 8e8e0083 | 2026-10-07T03:36 | final_11 (context-percussion-v12) | SUCCEEDED | 6ff80a | MyGO!!!!!-壱雫空 | 829 MB | 64 MB | 893 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/MyGO!!!!!-壱雫空.mp3 (developer's local collection of commercial tracks) |
| 29c78273 | 2026-10-07T03:44 | final_11 (context-percussion-v12) | SUCCEEDED | 6ff80a | sumika - 픽션(フィクション) | 1,021 MB | 79 MB | 1,099 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/sumika - 픽션(フィクション).mp3 (developer's local collection of commercial tr |
| 80f4d173 | 2026-10-07T03:53 | final_11 (context-percussion-v12) | SUCCEEDED | 6ff80a | 너의 이름은 OST - Sparkle | 1,215 MB | 93 MB | 1,309 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/너의 이름은 OST - Sparkle.mp3 (developer's local collection of commercial t |
| 58643cc3 | 2026-10-07T04:07 | final_11 (context-percussion-v12) | SUCCEEDED | 6ff80a | QWER - 고민중독 [가사 Lyrics] | 770 MB | 59 MB | 829 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/QWER - 고민중독.mp3 (developer's local collection of commercial tracks) |
| 47871328 | 2026-10-07T04:39 | final_11 (context-families-v15) | SUCCEEDED | 6ff80a | R | 1,248 MB | 96 MB | 1,344 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/R.mp3 (developer's local collection of commercial tracks) |
| e3863250 | 2026-10-07T04:54 | final_11 (context-families-v15) | SUCCEEDED | 6ff80a | 掌心正銘 | 969 MB | 75 MB | 1,043 MB | 2026-10-08 | **MANUAL_TEST** | source matches song/MyGO!!!!!-掌心正銘.mp3 (developer's local collection of commercial tracks) |
| c14adb81 | 2026-10-07T05:21 | final_11 (context-families-v15) | SUCCEEDED | 6ff80a | millsage「everscape」【Official Music | 1,206 MB | 93 MB | 1,298 MB | 2026-10-08 | **UNKNOWN** | source is not in song/ and not the demo track |
| b7d2dc8c | 2026-10-07T16:14 | basic_2 (-) | SUCCEEDED | 7418fa | bed | 101 MB | 50 MB | 151 MB | 2026-10-08 | **UNKNOWN** | source is not in song/ and not the demo track |
| ec355a2e | 2026-10-07T17:39 | final_11 (context-families-v15) | SUCCEEDED | 6ff80a | 오늘을 채워 가 | 758 MB | 58 MB | 816 MB | 2026-10-08 | **DEMO** | title is the AI-generated sample song (rights confirmed by the user) |
| 365a7bf5 | 2026-10-07T17:49 | basic_6 (-) | SUCCEEDED | 6ff80a | 오늘을 채워 가 | 350 MB | 58 MB | 408 MB | 2026-10-08 | **DEMO** | title is the AI-generated sample song (rights confirmed by the user) |

| 분류 | 건수 | 용량(= 삭제 시 회수) | 권고 |
|---|---:|---:|---|
| REAL_USER | 0 | 0.00 GB | 유지 |
| DEMO | 2 | 1.20 GB | REVIEW (권리 보유 샘플 - 샘플 자산은 `frontend/public/samples`에 이미 있음) |
| MANUAL_TEST | 23 | 23.10 GB | REVIEW |
| BENCHMARK | 23 | 17.85 GB | REVIEW |
| UNKNOWN | 2 | 1.42 GB | 유지 |

`FAILED` 1건(millsage)은 산출물이 없는 실패 기록이며 소유자도 없다 → 그 분석의 job/asset 스크래치 포함 1.6 GB는 SAFE.

## 4. 분석에 연결되지 않은 jobs / inputs

참조 그래프로 판정: 분석 레코드/파이프라인 manifest의 id, `job.json`의 `asset_id`, 소유 프로세스의 생존 여부(pid + 생성시각)를 모두 확인했다. 실행 중인 job은 0건.

| 종류 | 분류 | 개수 | 용량 | 의미 | 위험도 |
|---|---|---:|---:|---|---|
| jobs | LIBRARY_RECORD | 41 | 0.91 GB | 분석 레코드는 없지만 `WebLibrary.entries()`가 단독 결과로 라이브러리에 표시 | REVIEW |
| jobs | LINKED_TO_ANALYSIS | 231 | 0.96 GB | 분석 레코드가 참조 (정리 후에는 job.json·로그 정도) | KEEP (FAILED 분석의 것만 SAFE) |
| inputs | LIBRARY_RECORD | 36 | 0.39 GB | 분석 레코드는 없지만 `WebLibrary.entries()`가 단독 결과로 라이브러리에 표시 | REVIEW |
| inputs | LINKED_TO_ANALYSIS | 3 | 0.32 GB | 분석 레코드가 참조 (정리 후에는 job.json·로그 정도) | KEEP (FAILED 분석의 것만 SAFE) |
| inputs | ORPHAN | 49 | 5.33 GB | 어떤 레코드·job·pipeline도 이름을 부르지 않음 | SAFE |

- **단독 라이브러리 항목(LIBRARY_RECORD) 41 job**: preset {'baseline': 22, 'instrument_mega5': 14, 'vocal_roformer': 5}, 생성 2026-10-06 ~ 2026-10-07. S2/S3 단계의 초기 실험 결과로 보이지만 라이브러리에는 보이므로 REVIEW.
- **ORPHAN asset 49개 (5.33 GB)**: 이름은 `vocals.wav`/`instrumental.wav` 등 단계 간 복사본이며, 이를 참조하는 job.json·레코드·pipeline이 하나도 없고 실행 중인 job도 없다. 삭제 직전에 참조를 다시 계산해서 확인한다. 이전 `delete`나 중단된 분석이 남긴 잔여물로 보인다(원인 미확정).
- 이름만으로 판단하지 않았다. ORPHAN 판정은 위 참조 그래프 결과이며 목록은 `data/audit/library.json`에 있다.

## 5. `tools/AudioSep`, `CLAPSepInference` 등 (6.6 GB)

| 경로 | 크기 | 정체 | 코드가 쓰는가 | 테스트 | commercial preset | 판단 |
|---|---:|---|---|---|---|---|
| `tools/AudioSep` (+ `audiosep-env` 0.28 GB) | 3.46 GB + 0.28 GB | git clone `Audio-AGI/AudioSep`@`944583f1…` + 가중치 `audiosep_base_4M_steps.ckpt`(1.2 GB, SHA `f8cda01b…`) + CLAP `.pt`(2.2 GB, SHA `51c68f12…`) | `audiosep_experiment.py`(연구용 단발 실험)에서만 | 참조 없음 | 사용 안 함 (commercial preset·approval에 없음) | **REVIEW → 삭제 후보**. 프로덕션·baseline 경로가 없다. URL·SHA는 `configs/models/audiosep_base.json`에 남아 있어 재다운로드 가능 |
| `tools/wesep-reference` | 0.52 GB | 연구용 참조(`avg_model.pt`, `bsrnn_ecapa_vox1.tar.gz`) | 준비 스크립트 `prepare-wesep-reference.py`뿐 | 없음 | 사용 안 함 | **REVIEW → 삭제 후보** (스크립트로 재생성 가능) |
| `tools/CLAPSep` (git, 12 MB) + `CLAPSepInference` (2.41 GB, LAION-CLAP `.pt` 2.2 GB SHA `fae3e9c0…` + `best_model.ckpt` 170 MB SHA `6fcc8dbc…`) + `clapsep-env` (115 MB) | 2.5 GB | CLAPSep 추론 스택 | `synth_recovery.py`(final_11의 심벌 이동), `substem_pipeline.py`, `part_study.py`, `clapsep_experiment.py` | `test_release.py`는 commercial에서 **호출되지 않음**을 검사할 뿐 실행하지 않음 | **commercial 경로에서 사용하지 않음** (테스트가 보장) | **REVIEW — 삭제하면 final_11 BASELINE을 다시 돌릴 수 없다.** baseline 보존이 요구사항이었으므로 사용자 결정 필요 |

- 로컬 clone과 가중치를 지우고 문서에 URL·SHA만 남기는 방안: AudioSep과 wesep은 가능. CLAPSep은 baseline 재현 포기를 뜻한다.
- `AudioSep`의 `.pt`(CLAP)와 `CLAPSepInference`의 `.pt`는 **SHA가 달라서 중복이 아니다**(서로 다른 체크포인트 파일: `esc_89.98` vs `esc_90.14`).

## 6. `reset-backups` (2.27 GB)

- `reset-20261006-193853`: 분석 5건 / job 3 / input 3 / substems 2. **현재 라이브러리에 있는 id는 0건**, DB(analysis_owners)에도 없다. 내용은 `Orange` 곡의 기타·other·신스 비교 연구 분석 5건(이름 4종, 예: `Orange · other·신스 비교 · 0:40–1:00`)이며, 이 연구는 part-study 문서/보고서로 남아 있다. 복구에 필요한 사용자 분석은 확인되지 않았다 → **LEGACY_BACKUP, REVIEW (권고: 최종 단계에서 삭제 가능)**. 사용자가 전에 '마지막 단계에서 재판단'하기로 한 항목.

## 7. 벤치마크 source / references 최소화

`data/ground-truth`, `data/pad-eval`에서 1 MB 이상 오디오/배열 파일을 크기→SHA256으로 비교했다. **내용이 같은 파일 그룹 1,134개 (파일 3,362개), 중복 제거 시 약 11.18 GB**.

| 영역 | 절감 가능 | 중복 파일 수 |
|---|---:|---:|
| `data/ground-truth/cases` | 7.51 GB | 2,135 |
| `data/pad-eval/cases` | 2.10 GB | 704 |
| `data/pad-eval/cases-v16` | 1.58 GB | 523 |

예: 같은 믹스에서 만들어진 케이스 6개가 `acoustic_guitar.wav`, `bass.wav`, `brass.wav` 등 동일한 5 MB reference를 각자 복사해 갖고 있다 (`percussion-cowbell`, `percussion-bell_tree`, `real-timpani`, `controls-v16/vocal-violin` …).

- 제안(미실행): 한 곳의 canonical fixture(`data/fixtures/<sha256>.wav`)를 두고 케이스는 `prepared.json`의 sha256으로 참조 → 약 11 GB 절감. 단 케이스 폴더가 파일 경로를 직접 읽는 코드(`ground_truth.evaluate`, `reevaluate-*`)가 있어 먼저 해석 계층이 필요하다.
- 하드링크/심볼릭 링크 도입 검토: (1) Windows에서 심볼릭 링크는 권한이 필요하고 복사/백업 도구가 링크를 따라가 용량을 부풀리기 쉽다. (2) 하드링크는 같은 볼륨에서만 가능하고 한 이름을 지워도 다른 이름이 남아 삭제 수명주기 보고서(`storage-inventory`가 이미 `st_nlink`를 구분)와 충돌하지 않지만, 편집 시 모든 이름이 같이 바뀐다 → 읽기 전용 fixture라면 허용 가능. (3) 결정: 실행하지 않음. 효과가 11 GB이고 `stability-v11~v16`·`controls-v11~v16`처럼 **오래된 버전 폴더 자체를 줄이는 쪽이 더 단순**하다(REVIEW 항목).

## 8. 체크포인트 감사 (`*.ckpt *.pth *.pt *.bin *.safetensors *.th *.onnx`, 1 MB 이상)

프로젝트 안(`.venv` 제외) 25개. **동일 SHA256 중복은 0건**이다. `.venv`에는 1 MB 이상 가중치 파일이 없다.

| 경로 (`data/separation/` 기준) | 크기 | SHA256 | model id | 레지스트리 | production preset | 승인 | 비고 |
|---|---:|---|---|---|---|---|---|
| `tools/AudioSep/checkpoint/music_speech_audioset_epoch_15_esc_89.98.pt` | 2,243 MB | `51c68f12f9d7…` | - | 아니오 | - | - | 레지스트리 미등록 (연구/실험) |
| `tools/CLAPSepInference/model/music_audioset_epoch_15_esc_90.14.pt` | 2,243 MB | `fae3e9c087f2…` | - | 아니오 | - | - | 레지스트리 미등록 (연구/실험) |
| `models/melband_karaoke/mel_band_roformer_karaoke_becruily.ckpt` | 1,639 MB | `d3aa262ac01d…` | melband_karaoke | 예 | - | UNKNOWN | UNKNOWN 라이선스, 개발용 vocal_detail |
| `models/mega53_3head/official-53.ckpt` | 1,306 MB | `c62820893bbf…` | - | 아니오 | - | - | official Mega53 원본: core4/vocal2/mega5/mega7 파생의 출처 (재다운로드 가능, 파생 재현에 필요) |
| `tools/AudioSep/checkpoint/audiosep_base_4M_steps.ckpt` | 1,206 MB | `f8cda01bfd0e…` | - | 아니오 | - | - | 레지스트리 미등록 (연구/실험) |
| `models/melband_roformer_kj/MelBandRoformer.ckpt` | 871 MB | `87201f4d31af…` | melband_roformer_kj | 예 | commercial_2, commercial_6, commercial_13 | APPROVED |  |
| `models/bs_roformer_6s/bs_6stem_fixed.ckpt` | 667 MB | `24e7d35ee9c6…` | bs_roformer_6s | 예 | - | UNKNOWN | UNKNOWN, final_11 BASELINE 필요 |
| `tools/wesep-reference/checkpoint/avg_model.pt` | 270 MB | `3d0502171eab…` | - | 아니오 | - | - | 레지스트리 미등록 (연구/실험) |
| `models/bs_roformer_mega7/mega7.ckpt` | 216 MB | `46e2e801cccb…` | bs_roformer_mega7 | 예 | commercial_13 | APPROVED |  |
| `models/bs_karaoke/bs_roformer_karaoke_frazer_becruily.ckpt` | 195 MB | `eb90ee24c115…` | bs_karaoke | 예 | - | UNKNOWN | UNKNOWN, final_11 BASELINE 필요 |
| `models/bs_roformer_mega6/mega6.ckpt` | 192 MB | `d33b5a08e026…` | bs_roformer_mega6 | 예 | - | - | 레지스트리 승인 기록 없음 (실험용) |
| `tools/CLAPSepInference/model/best_model.ckpt` | 170 MB | `6fcc8dbcd717…` | - | 아니오 | - | - | 레지스트리 미등록 (연구/실험) |
| `models/mega53_5head/mega53-5head.ckpt` | 169 MB | `05eb7b0334b5…` | - | 아니오 | - | - | 레지스트리 미등록 (연구/실험) |
| `models/mega53_5head_bowed/mega53-5head.ckpt` | 169 MB | `6c959b4d988e…` | - | 아니오 | - | - | 레지스트리 미등록 (연구/실험) |
| `models/bs_roformer_mega5/mega5.ckpt` | 169 MB | `8a73fb568f5a…` | bs_roformer_mega5 | 예 | commercial_13 | APPROVED |  |
| `models/bs_roformer_core4/core4.ckpt` | 145 MB | `24b900e2cc5b…` | bs_roformer_core4 | 예 | commercial_6, commercial_13 | APPROVED |  |
| `models/bs_roformer_mega4/mega4.ckpt` | 145 MB | `c9e368742e5e…` | bs_roformer_mega4 | 예 | - | - | 승인 기록 없음 (실험용) |
| `models/mega53_3head/mega53-3head.ckpt` | 121 MB | `9d97108e4f95…` | - | 아니오 | - | - | 레지스트리 미등록 (연구/실험) |
| `models/bs_roformer_vocal2/vocal2.ckpt` | 98 MB | `fb4d0d09c900…` | bs_roformer_vocal2 | 예 | commercial_13 | APPROVED |  |
| `models/demucs_htdemucs/955717e8-8726e21a.th` | 80 MB | `8726e21a9939…` | demucs_htdemucs | 예 | - | - |  |
| `models/demucs_htdemucs_ft/04573f0d-f3cf25b2.th` | 80 MB | `f3cf25b222c4…` | - | 아니오 | - | - | 레지스트리 미등록 (연구/실험) |
| `models/demucs_htdemucs_ft/92cfc3b6-ef3bcb9c.th` | 80 MB | `ef3bcb9c8b40…` | - | 아니오 | - | - | 레지스트리 미등록 (연구/실험) |
| `models/demucs_htdemucs_ft/d12395a8-e57c48e6.th` | 80 MB | `e57c48e6b0e3…` | - | 아니오 | - | - | 레지스트리 미등록 (연구/실험) |
| `models/demucs_htdemucs_ft/f7e0c4bc-ba3fe64a.th` | 80 MB | `ba3fe64ae8ef…` | demucs_htdemucs_ft | 예 | - | - |  |
| `models/demucs_htdemucs_6s/5c90dfd2-34c22ccb.th` | 52 MB | `34c22ccb381c…` | demucs_htdemucs_6s | 예 | - | - |  |

- production에서 쓰는 체크포인트는 5개(KJ, mega7, mega5, core4, vocal2)로 1.46 GB.
- 나머지 20개(약 11.6 GB)는 개발/실험/baseline용이다. 이 중 UNKNOWN·미승인 가중치(melband_karaoke 1.6 GB, bs_6stem 0.67 GB, bs_karaoke 0.19 GB)를 지우면 final_11 baseline과 vocal_detail 기능이 동작하지 않는다 (REVIEW). `licenses`/approval 증빙 파일(`commercial_approval.json`, 모델 JSON)은 어떤 경우에도 삭제 대상이 아니다.

## 9. `.git`

- 전체 9.4 MB, 커밋 80개, pack 없음(loose objects 1,641개, 9.29 MiB), LFS 없음.
- 가장 큰 blob 0.49 MB (`frontend/public/licenses/texts/pytorch.txt`). 과거 대형 WAV/모델을 커밋한 흔적 없음 → 히스토리 재작성으로 회수할 용량은 사실상 0. (`.gitignore`가 `*.wav`, `*.mp3`, `*.ckpt` 등을 막고 있다.)

## 10. 프로젝트 내부 개발 cache

| 위치 | 종류 | 크기 | 비고 |
|---|---|---:|---|
| venv | __pycache__ | 179.4 MB (1214 dirs) | 재생성 가능 |
| data | __pycache__ | 115.2 MB (985 dirs) | 재생성 가능 |
| frontend | node_modules | 77.3 MB (1 dirs) | 재생성 가능 |
| frontend | dist | 7.5 MB (1 dirs) | 재생성 가능 |
| separation | __pycache__ | 0.9 MB (4 dirs) | 재생성 가능 |
| data | build | 0.1 MB (2 dirs) | 재생성 가능 |
| scripts | __pycache__ | 0.0 MB (1 dirs) | 재생성 가능 |
| venv | build | 0.0 MB (1 dirs) | 재생성 가능 |
| separation | .pytest_cache | 0.0 MB (1 dirs) | 재생성 가능 |
| 전체 | `*.log` | 0.5 MB (329 files) | 재생성 불필요 |

프로젝트 안에 pip/HuggingFace/torch 다운로드 cache 디렉터리는 없다. 시스템 전역 cache(`%LOCALAPPDATA%\pip`, `~/.cache/huggingface`, `~/.cache/torch` 등)는 프로젝트 정리 범위가 아니므로 측정·삭제하지 않았다. `.venv`(4.67 GB)는 실행에 필요한 런타임이며 requirements에서 재생성 가능하므로 KEEP.

## 11. 최종 WAV 저장 비용 (포맷 변경 없음, 수치만)

실제 최종 stem으로 측정(`scripts/audio-format-benchmark.py`): 2트랙=`bed`(basic_2, 150 s), 6트랙·13트랙=같은 곡 `오늘을 채워 가`(173 s).

| 세트 | 포맷 | 크기 | float32 대비 | 인코딩 | 디코딩 | 전 stem WAV(PCM24)로 내려받기 | 최대 오차 | 합계 오차 (원본 대비) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2-track (2 stems) | float32_wav | 100.8 MB | 100% | 0.54 s (CPU 0.0 s) | 0.03 s (CPU 0.02 s) | 0.91 s | 0.0e+00 | 3.0e-08 |
| 2-track (2 stems) | pcm24_wav | 75.6 MB | 75% | 0.95 s (CPU 0.0 s) | 0.11 s (CPU 0.0 s) | 1.01 s | 1.2e-07 | 2.4e-07 |
| 2-track (2 stems) | flac24 | 25.2 MB | 25% | 1.71 s (CPU 0.34 s) | 0.35 s (CPU 0.03 s) | 1.22 s | 6.0e-08 | 1.2e-07 |
| 6-track (6 stems) | float32_wav | 349.7 MB | 100% | 1.95 s (CPU 0.06 s) | 0.11 s (CPU 0.03 s) | 2.92 s | 0.0e+00 | 7.3e-08 |
| 6-track (6 stems) | pcm24_wav | 262.3 MB | 75% | 2.26 s (CPU 0.12 s) | 0.38 s (CPU 0.06 s) | 2.84 s | 1.2e-07 | 7.0e-07 |
| 6-track (6 stems) | flac24 | 111.8 MB | 32% | 5.99 s (CPU 0.56 s) | 1.48 s (CPU 0.16 s) | 4.91 s | 6.0e-08 | 3.4e-07 |
| 13-track (13 stems) | float32_wav | 757.7 MB | 100% | 3.91 s (CPU 0.05 s) | 0.24 s (CPU 0.02 s) | 5.87 s | 0.0e+00 | 1.0e-07 |
| 13-track (13 stems) | pcm24_wav | 568.3 MB | 75% | 4.58 s (CPU 0.36 s) | 0.64 s (CPU 0.11 s) | 13.16 s | 1.2e-07 | 1.3e-06 |
| 13-track (13 stems) | flac24 | 195.0 MB | 26% | 12.43 s (CPU 2.89 s) | 3.71 s (CPU 0.39 s) | 8.42 s | 6.0e-08 | 6.0e-07 |

- **무손실이 아니다**: PCM24와 FLAC24는 float32를 24 bit로 양자화한다(최대 오차 6e-8~1.2e-7, 약 -138~-144 dBFS). 현재 계약의 합계 오차 허용(2e-6) 안에는 들어오지만, **13 stem을 PCM24로 저장하면 합계 오차가 1.33e-6**으로 여유가 크게 줄어든다(FLAC24 6.0e-7). 샘플 절댓값이 1.0을 넘는 stem은 이 곡들에서 0개였다(다른 곡은 미측정, 클리핑 위험).
- 크기: PCM24는 float32의 75 %, FLAC24는 이 곡들에서 **25~32 %**. 조용한 stem이 많은 곡일수록 FLAC 이득이 크다(곡마다 다름).
- 인코딩/디코딩 비용: FLAC24 인코딩은 13 stem에 12.4 s(CPU 2.9 s), 디코딩 3.7 s(CPU 0.4 s) — 분석 1건당 1회 인코딩이므로 233 s 처리 시간에 비해 작다. 재생 미리듣기는 이미 PCM16/FLAC이라 영향 없음.
- 재생·다운로드: 브라우저(Web Audio/HTMLAudio)는 FLAC 재생 가능, 서버는 이미 `audio/flac` MIME과 Range 응답을 지원한다. WAV로 내려받으려면 변환이 필요하다(13 stem 전체 8.4 s, stem 하나는 약 0.65 s). 변환을 요청 시점에 하면 임시 파일이 필요하다(방금 정리한 ZIP 정책과 같은 방식).
- RAM: 측정 방식은 stem 전체를 한 번에 메모리에 올린 값이라 파일 합계(13트랙 758 MB)와 같다. 스트리밍 변환 시 stem 하나 분량으로 줄일 수 있다(미구현·미측정).

**`data/separation/web`(최종 stem + original 43.24 GB)의 예상**: PCM24 약 32.43 GB (−10.8 GB), FLAC24 약 11.27 GB (−32.0 GB). 같은 비율을 적용한 추정이며 곡 내용에 따라 달라진다. `data/separation` 전체 66.1 GB 기준으로는 PCM24 약 55 GB, FLAC24 약 34 GB. 포맷 변경은 하지 않았고, 도입한다면 합계 보존 계약(2e-6)과 `manifest.json` 해시 정의를 먼저 바꿔야 한다.

## 12. 삭제 계획 (dry-run — 승인 전 어떤 것도 삭제하지 않음)

현재 전체 프로젝트: **102.56 GB**

| 위험도 | 용량 | 내용 |
|---|---:|---|
| **SAFE** (바로 삭제 가능) | 7.24 GB | ORPHAN 입력 asset 5.33 GB, FAILED 분석의 스크래치와 기록 1.6 GB, `.venv`/프런트/데이터 `__pycache__`·빌드 cache ~0.3 GB, 오래된 smoke·로그, 이번 감사 산출물 |
| **REVIEW** (사용자 확인 후) | 85.18 GB | 분석 47건(약 41.8 GB; DEMO·MANUAL_TEST·BENCHMARK, 세부는 3절 표, FAILED 1건 제외), 케이스 references·reports 27.1 GB(중복 제거 시 −11.2 GB), AudioSep·wesep 4.1 GB, CLAPSep 스택 2.5 GB(baseline 재현 포기), 비production 가중치 3.5 GB, official-53 1.4 GB, 단독 job 항목 1.3 GB, reset-backups 2.3 GB, medleydb·philharmonia 1.0 GB, `song/` 0.13 GB |
| **KEEP** | 8.73 GB | `.venv` 4.7 GB, production 체크포인트 1.5 GB, 소스·설정·문서·라이선스 증빙, 청정 벤치마크 source(BabySlakh, FreePats, pad-eval stems), 데모곡 mix·stems, report·metrics, `.git` |
| **UNKNOWN** | 1.42 GB | 분석 2건: `bed`, `millsage「everscape」【Official M` (원곡이 `song/`에도 샘플곡에도 없음) |

### 권고 순서
1. SAFE 7.2 GB: 승인되면 삭제 직전에 참조 그래프를 다시 계산해서(그 사이 새 분석이 생길 수 있음) 실행.
2. REVIEW 중 가장 큰 효과: (a) 분석 50건 처리 방침(전부 보관 / MANUAL_TEST·BENCHMARK 45건 삭제 시 약 40.6 GB 회수 / DEMO는 별도), (b) `ground-truth/cases`·`pad-eval/cases`의 이전 버전 폴더 정리 또는 sha256 dedup(약 11 GB), (c) AudioSep·wesep 삭제(4.1 GB), (d) reset-backups(2.3 GB).
3. 포맷 최적화(FLAC24, −32 GB 예상)는 삭제가 아니라 별도 결정 사항이며, 합계 보존 계약·manifest 변경이 선행된다.

사용자 데이터로 의심되는 파일(`B USER_PERSISTENT`, `I UNKNOWN`)은 이 보고서에서 삭제 대상으로 확정하지 않았다.


## 13. 삭제 적용 결과 (사용자 확정 방침에 따라 실행)

확정 방침: SAFE 삭제 / MANUAL_TEST 23 + BENCHMARK 23 분석 삭제 / DEMO 2 + UNKNOWN 2 유지 / AudioSep + wesep 삭제 / reset-backups 삭제(메타데이터 선보존) / CLAPSep 스택, UNKNOWN 체크포인트 3종, 단독 job 41건은 유지. 스크립트 `scripts/apply-disk-cleanup.py`(기본 plan, `--apply`로 실행).

### 13-1. 실행 전 검증 (실제 ID 기준)
- 레코드 50건 = MANUAL_TEST 23 + BENCHMARK 23(SUCCEEDED 22 + FAILED 1) + DEMO 2 + UNKNOWN 2. DB `analysis_owners` 49행(= FAILED 1건을 뺀 전부), 소유자 없는 레코드는 FAILED 1건뿐임을 assert로 확인.
- **"REVIEW 47건" 설명**: 47 = DEMO 2 + MANUAL_TEST 23 + SUCCEEDED BENCHMARK 22. FAILED BENCHMARK 1건은 보고서에서 SAFE(스크래치) 쪽으로 따로 셌다. 삭제 대상은 46건(45 SUCCEEDED + 1 FAILED), 유지 4건. 합계는 일치한다.
- 삭제 직전 참조 그래프 재계산: 고아 asset 49개 중 새로 참조가 생긴 것 0개, 실행 중인 job/분석 0건, `prepared.json`/`case.json`/`run.json` source 의존성 없음.

### 13-2. 실행 내용
| 단계 | 내용 | 결과 |
|---|---|---|
| 1 safe | 고아 입력 asset 49개, `__pycache__`/`.pytest_cache`, 오래된 smoke 출력 | 5.33 GB + 0.29 GB + 0.03 GB. `data/separation/runtime`(JobService 런타임), 로그, `frontend/dist`·`node_modules`는 **건드리지 않음** (SAFE 분류에 `runtime`이 섞여 있었으나 실행 전에 제외) |
| 2 analyses | 46건을 `WebLibrary.delete()` + `AuthStore.release()`로 삭제 | 파일만 지우지 않았고 각 건마다 폴더 부재와 DB 소유 행 부재를 assert. 이후 레코드 4건 = 유지 목록과 동일, DB 소유 행 4건 |
| 3 tools | `tools/AudioSep` 3.46 GB + `tools/wesep-reference` 0.52 GB | 아래 주의 참고. 출처·SHA는 `docs/RETIRED_TOOLS_PROVENANCE.json`에 보존 |
| 4 reset-backups | 2.27 GB 삭제, 작은 JSON 메타데이터 25개(59 KB)를 `docs/legacy-backups/reset-20261006-193853/`에 먼저 복사 | mp3 2개와 로그·freeze 파일은 보존하지 않음 |

**방침 대비 변경 1건 (audiosep-env 유지)**: 지시는 "AudioSep + wesep 삭제"였고 초안에는 `tools/audiosep-env`(0.28 GB)도 있었다. 삭제 전 의존성 확인에서 `clapsep-env`가 `.pth` 파일로 `audiosep-env`의 site-packages를 읽는다는 것을 발견했다. 이를 지우면 **유지하기로 한 CLAPSep 스택(= final_11 baseline의 심벌 이동)이 깨진다**. 그래서 `audiosep-env`는 남겼고, 삭제 전후에 `clapsep-env`에서 `import torch, laion_clap, music_analyzer.clapsep_experiment`가 성공함을 확인했다. 또 `audiosep_experiment.py`는 CLAPSep이 쓰는 공용 헬퍼(`restore_channel` 등)라서 코드 모듈은 그대로 둔다. 남은 경로 참조는 그 모듈의 CLI 기본값 1곳(`--repo`)과 재생성 스크립트(`prepare-audiosep.py`, `run-target-voice-experiment.py`)뿐이다.

**실행 중 사고 2건 (기록)**
1. plan 모드 실행이 순수하지 않았다: `WebLibrary` 생성자가 시작 시 정리를 수행해서 FAILED 분석(삭제 대상)의 스크래치 1.73 GB가 plan 단계에서 먼저 지워졌다. 승인 범위 안의 항목이라 피해는 없었고, 이후 plan 모드에서는 `WebLibrary`를 만들지 않도록 고쳤다.
2. `tools/AudioSep`의 git pack 파일이 읽기 전용이라 첫 삭제 시도가 `PermissionError`로 중단됐다(해당 단계 이전의 1·2단계는 이미 완료). 읽기 전용 해제 후 재시도해서 완료했다. 그 뒤 PC가 강제 재부팅되었으나, 재부팅 후 상태를 확인했을 때 라이브러리·DB·`.venv`는 모두 정상이었다.

### 13-3. 전후 측정 (물리 용량, 하드링크 1회 계산)
| 항목 | 이전 | 이후 | 감소 |
|---|---:|---:|---:|
| **프로젝트 전체** | **102.56 GB** | **48.52 GB** | **−54.04 GB** |
| `data/` | 97.47 GB | 43.62 GB | −53.85 GB |
| `data/separation` | 64.52 GB | 12.93 GB | −51.59 GB |
| `data/separation/tools` | 6.61 GB | 2.61 GB | −4.00 GB |
| `data/separation/web` (분석 결과) | 43.57 GB | 2.62 GB | −40.95 GB |
| `data/separation/jobs` / `inputs` | 1.87 / 6.04 GB | 0.91 / 0.39 GB | −0.96 / −5.65 GB |
| `data/reset-backups` | 2.27 GB | 삭제 (메타데이터 59 KB → `docs/legacy-backups/`) | −2.27 GB |
| `.venv` | 4.85 GB | 4.67 GB | −0.18 GB (`__pycache__`) |
| 파일 수 | 65,777 | 46,146 | −19,631 (신규 `docs/legacy-backups` 25개 포함) |
| C: 여유 공간 | - | 757.9 GB | 볼륨을 다른 데이터가 공유해서 프로젝트 크기만 신뢰할 수 있는 수치로 본다 (이 정리 실행 시작 시점 662.5 GB → 종료 757.9 GB) |

스크립트가 세어서 삭제한 바이트: 3·4단계 6.6 GB(738개 파일) + 1·2단계는 위 폴더 크기 차이로 계산. 목표 예상 "약 47 GB 전후"에 대해 실제는 **48.5 GB**다 (audiosep-env 0.28 GB 유지, 감사 산출물 `data/audit` 등 약 0.1 GB, 실행 중 새로 생긴 로그가 남음).

### 13-4. 남은 가장 큰 디렉터리 TOP 20 (물리)
`data/ground-truth` 17.57 · `data/ground-truth/cases` 15.53 · `data/separation` 12.93 · `data/pad-eval` 12.71 · `pad-eval/cases` 6.95 · `separation/models` 6.40 · `.venv` 4.67 (torch 4.23) · `pad-eval/cases-v16` 4.62 · `separation/web` 2.62 · `separation/tools` 2.61 · `tools/CLAPSepInference` 2.36 · `ground-truth/cases/stability-v11…v16` 각 1.60 · `models/melband_karaoke` 1.60 · `models/mega53_3head` 1.39 · 분석 `analysis_f7f0…`(DEMO) 1.27.

남은 것은 모두 유지 결정된 항목이다: 벤치마크 source/references(약 29 GB, 중복 제거 시 −11 GB 가능), 모델 체크포인트 6.4 GB, `.venv`, CLAPSep 스택, 분석 4건(2.6 GB).

### 13-5. 삭제 후 무결성
| 점검 | 결과 |
|---|---|
| 백엔드 단위 테스트 | **323 passed, 1 skipped, 0 failed** (재부팅 후 재실행) |
| 프런트엔드 | `vite build` 성공. 프런트엔드 테스트는 `analysisEstimate.test.js` 1개뿐이며 `node --test`로 통과 (`npm test` 스크립트는 없음) |
| release gate | `validate_production` 통과, commercial_2/6/13 problems 없음, 승인(APPROVED)된 preset 0개(VALIDATING 유지) |
| 모델 레지스트리 | `commercial_gate`로 2/6/13의 고정 SHA256 일치, 승인·baseline 체크포인트 8개 모두 존재 |
| 라이선스 | `build-license-notices.py --check` 일치 |
| 애플리케이션 기동 | `python -m music_analyzer.web_server --help` 정상, 라이브러리 로드 정상 |
| 라이브러리 | 분석 4건 모두 `contract_violations == []`, 목록 40건(분석 4 + 단독 job 항목 36), 13트랙 분석의 미리듣기와 758 MB ZIP 생성 확인 |
| DB 일관성 | `analysis_owners` 4행 ⊆ 레코드 4건 |
| CLAPSep 환경 | `clapsep-env`에서 torch, laion_clap, `clapsep_experiment` import 성공 (삭제 전·후) |
| 전체 lifecycle (commercial_6, 5 s) | 분석 → 정리 → 재생 → 개별 WAV → 전체 ZIP → ZIP 임시 파일 삭제 → 분석 삭제 → 남은 파일 0개, `LIFECYCLE E2E OK` |

### 13-6. 아직 남은 결정/위험
- 단독 job 항목: 라이브러리 목록 40건 중 36건이 분석에 연결되지 않은 단독 job 결과(이번에는 유지, 별도 inventory로 재판단).
- `final_11 baseline`의 `bs_6stem`·`bs_karaoke`·`melband_karaoke`(UNKNOWN 라이선스)와 CLAPSep 스택: commercial_13 동결 후 baseline 폐기 시점에 재검토.
- `audiosep-env`(0.28 GB)는 `clapsep-env`가 쓰는 동안 삭제할 수 없다.
- AudioSep/wesep 재생성: `prepare-audiosep.py` 등으로 재다운로드 가능하며 URL·commit·체크포인트 SHA256은 `docs/RETIRED_TOOLS_PROVENANCE.json`에 있다.
