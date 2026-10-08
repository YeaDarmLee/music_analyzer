"""Compose docs/FULL_DISK_AUDIT_KO.md from data/audit/*.json (dry-run report; nothing is deleted)."""
import json, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; A = ROOT / "data/audit"
disk = json.loads((ROOT / "data/disk-audit.json").read_text(encoding="utf-8")); lib = json.loads((A / "library.json").read_text(encoding="utf-8"))
art = json.loads((A / "artifacts.json").read_text(encoding="utf-8")); cls = json.loads((A / "classified.json").read_text(encoding="utf-8"))
fmt = json.loads((A / "formats.json").read_text(encoding="utf-8"))
gb = lambda n: f"{n / 2**30:,.2f} GB"; mb = lambda n: f"{n / 2**20:,.0f} MB"
L = []; w = L.append
names_c = {"A": "PRODUCTION_REQUIRED", "B": "USER_PERSISTENT", "C": "TEST_FIXTURE_REQUIRED", "D": "REGENERABLE", "E": "DEV_TOOL", "F": "CACHE", "G": "LEGACY_BACKUP", "H": "ORPHAN", "I": "UNKNOWN"}
risk = collections.defaultdict(int)
for k, v in cls["buckets"].items():
    risk[k.split("|")[1]] += v[0]

w("# Full Project Disk Audit — DRY-RUN 보고서 (아무것도 삭제하지 않음)\n")
w("측정 도구: `scripts/disk-audit.py`, `audit-library.py`, `audit-artifacts.py`, `audit-report.py`, `audio-format-benchmark.py`, `audit-doc.py`. 이 문서의 모든 수치는 읽기 전용 측정값이며, 판단이 어려운 항목은 UNKNOWN/REVIEW로 두었다. 하드링크는 inode당 한 번만 센 **물리 용량**이다.\n")
w("## 0. 요약\n")
w(f"| 구분 | 용량 |\n|---|---:|\n| 현재 전체 프로젝트 (물리) | **{gb(cls['total'])}** (논리 {gb(disk['total_logical'])}, 차이는 하드링크) |")
w(f"| 안전하게 바로 삭제 가능 (SAFE) | {gb(risk['SAFE'])} |\n| 사용자 확인 후 삭제 (REVIEW) | {gb(risk['REVIEW'])} |\n| 유지 필수 (KEEP) | {gb(risk['KEEP'])} |\n| UNKNOWN (자동 삭제 금지) | {gb(risk['UNKNOWN'])} |\n")
w("핵심: 프로젝트의 **약 98 %가 `data/`** 이고, 그중 **43.6 GB는 `data/separation/web`의 분석 50건**(최종 stem)이다. 코드·설정·문서·라이선스 증빙·`.git`은 합쳐서 0.1 GB 미만이다. `.git`은 9.3 MB(커밋 80개, 최대 blob 0.49 MB)라 과거에 대형 파일을 커밋한 흔적이 없다.\n")

w("## 1. 용량 감사\n")
w("### 1-1. 최상위 디렉터리\n\n| Path | 물리 | 논리 | 파일 수 |\n|---|---:|---:|---:|")
for d, p, l, n in disk["top_level"]:
    w(f"| `{d}` | {gb(p)} | {gb(l)} | {n:,} |")
w(f"\n1 GB 이상 디렉터리 48개, 500 MB 이상 파일 12개.\n")
w("### 1-2. 가장 큰 디렉터리 TOP 50 (물리 / 논리)\n\n| # | Path | 물리 | 논리 | 파일 수 |\n|---:|---|---:|---:|---:|")
for i, (d, p, l, n) in enumerate(disk["directories"][:50], 1):
    w(f"| {i} | `{d}` | {gb(p)} | {gb(l)} | {n:,} |")
w("\n### 1-3. 500 MB 이상 개별 파일\n\n| Path | 물리 | 링크 수 |\n|---|---:|---:|")
for p, l, nl, path in [f for f in disk["big_files"] if f[1] >= 500 * 2**20]:
    w(f"| `{path}` | {gb(p)} | {nl} |")
w("\n### 1-4. 가장 큰 파일 TOP 100 (100 MB 이상만 존재하는 목록)\n\n| # | Path | 크기 | 링크 |\n|---:|---|---:|---:|")
for i, (p, l, nl, path) in enumerate(disk["big_files"][:100], 1):
    w(f"| {i} | `{path}` | {mb(l)} | {nl} |")
w(f"\n(100 MB 이상 파일은 총 {len(disk['big_files'])}개. 하드링크는 `data/ground-truth/cases`에만 일부 있다. 차이 0.69 GB는 `data/ground-truth/cases` 안의 하드링크(버전 폴더 사이에 이미 공유된 reference)다.)\n")

w("## 2. 분류 (A–I) × 위험도\n\n| 카테고리 | 위험도 | 용량 | 파일 수 |\n|---|---|---:|---:|")
for k, (size, n) in sorted(cls["buckets"].items(), key=lambda kv: -kv[1][0]):
    c, r = k.split("|"); w(f"| {c} {names_c[c]} | {r} | {gb(size)} | {n:,} |")
w("\n| 항목 | 카테고리 | 위험도 | 용량 | 파일 |\n|---|---|---|---:|---:|")
for x in sorted(cls["labels"], key=lambda x: -x["bytes"])[:30]:
    w(f"| {x['label']} | {x['category']} | {x['risk']} | {gb(x['bytes'])} | {x['files']:,} |")
w("\nUNKNOWN은 자동 삭제 대상이 아니다. 위험도 정의: SAFE=지금 지워도 기능·사용자 데이터 손실 없음 (삭제 직전 재검증), REVIEW=사용자 확인 필요, KEEP=유지.\n")

w("## 3. `data/separation` 분석 50건 재분류\n")
w("**중요한 한계**: `REAL_USER`로 증명할 수 있는 분석은 **0건**이다. DB에는 계정이 2개뿐이고(둘 다 2026-10-06 생성, 개발 계정), 그중 한 계정이 48건, 다른 계정이 1건을 소유하며 1건(FAILED)은 소유자가 없다. 외부 실사용자가 만든 분석이라는 근거가 없고, 대부분의 원곡이 개발자의 로컬 `song/` 폴더(상용 음원 25개)에 있는 파일이다. 그래도 이 분석들은 개발 계정의 라이브러리에 **노출되어 있으므로** 삭제 후보가 아니라 **REVIEW**(사용자 확인 후)로 둔다. NTFS의 마지막 접근 시각 갱신이 꺼져 있어(`DisableLastAccess=1`) '마지막 접근'은 알 수 없고, 아래 `수정일`(record.json) 만 제공한다.\n")
w("분류 근거: DEMO=사용자가 권리 확인한 AI 생성 샘플곡 / BENCHMARK=다른 분석에서 파생됐거나 같은 원곡을 나중에 다른 파이프라인 버전으로 다시 분석한 이전 판 / MANUAL_TEST=원본이 `song/`의 파일 / UNKNOWN=그 외.\n")
w("| id | 생성일 | preset (version) | 상태 | 소유 | 이름 | final | original | 폴더 합계(회수 가능) | 수정일 | 분류 | 근거 |\n|---|---|---|---|---|---|---:|---:|---:|---|---|---|")
for a in sorted(lib["analyses"], key=lambda x: str(x["created"])):
    ver = (a["version"] or "-").replace("staged-", "").replace("instrumental-with-brass-", "")
    w(f"| {a['id'][-8:]} | {str(a['created'])[:16]} | {a['preset']} ({ver}) | {a['state']} | {','.join(a['owners']) or '-'} | {a['name'][:34]} | {mb(a['final_bytes'])} | {mb(a['original_bytes'])} | {mb(a['folder_bytes'])} | {a['record_mtime'][:10]} | **{a['classification']}** | {a['evidence'][0][:90]} |")
tot = collections.defaultdict(lambda: [0, 0])
for a in lib["analyses"]:
    tot[a["classification"]][0] += 1; tot[a["classification"]][1] += a["folder_bytes"]
w("\n| 분류 | 건수 | 용량(= 삭제 시 회수) | 권고 |\n|---|---:|---:|---|")
rec = {"REAL_USER": "유지", "UNKNOWN": "유지", "DEMO": "REVIEW (권리 보유 샘플 - 샘플 자산은 `frontend/public/samples`에 이미 있음)", "MANUAL_TEST": "REVIEW", "BENCHMARK": "REVIEW"}
for k in ("REAL_USER", "DEMO", "MANUAL_TEST", "BENCHMARK", "UNKNOWN"):
    w(f"| {k} | {tot[k][0]} | {gb(tot[k][1])} | {rec[k]} |")
w("\n`FAILED` 1건(millsage)은 산출물이 없는 실패 기록이며 소유자도 없다 → 그 분석의 job/asset 스크래치 포함 1.6 GB는 SAFE.\n")

w("## 4. 분석에 연결되지 않은 jobs / inputs\n")
jobs = collections.defaultdict(lambda: [0, 0]); assets = collections.defaultdict(lambda: [0, 0])
for j in lib["jobs"]:
    jobs[j["class"]][0] += 1; jobs[j["class"]][1] += j["bytes"]
for a in lib["assets"]:
    assets[a["class"]][0] += 1; assets[a["class"]][1] += a["bytes"]
w("참조 그래프로 판정: 분석 레코드/파이프라인 manifest의 id, `job.json`의 `asset_id`, 소유 프로세스의 생존 여부(pid + 생성시각)를 모두 확인했다. 실행 중인 job은 0건.\n")
w("| 종류 | 분류 | 개수 | 용량 | 의미 | 위험도 |\n|---|---|---:|---:|---|---|")
meaning = {"LINKED_TO_ANALYSIS": "분석 레코드가 참조 (정리 후에는 job.json·로그 정도)", "LIBRARY_RECORD": "분석 레코드는 없지만 `WebLibrary.entries()`가 단독 결과로 라이브러리에 표시", "ORPHAN": "어떤 레코드·job·pipeline도 이름을 부르지 않음"}
rk = {"LINKED_TO_ANALYSIS": "KEEP (FAILED 분석의 것만 SAFE)", "LIBRARY_RECORD": "REVIEW", "ORPHAN": "SAFE"}
for kind, table in (("jobs", jobs), ("inputs", assets)):
    for c, (n, b) in sorted(table.items()):
        w(f"| {kind} | {c} | {n} | {gb(b)} | {meaning.get(c, c)} | {rk.get(c, '')} |")
lr = [j for j in lib["jobs"] if j["class"] == "LIBRARY_RECORD"]
w(f"\n- **단독 라이브러리 항목(LIBRARY_RECORD) {len(lr)} job**: preset {dict(collections.Counter(j['preset'] for j in lr))}, 생성 {min(j['created'] for j in lr)[:10]} ~ {max(j['created'] for j in lr)[:10]}. S2/S3 단계의 초기 실험 결과로 보이지만 라이브러리에는 보이므로 REVIEW.")
orph = sorted((a for a in lib["assets"] if a["class"] == "ORPHAN"), key=lambda a: -a["bytes"])
w(f"- **ORPHAN asset {len(orph)}개 ({gb(sum(a['bytes'] for a in orph))})**: 이름은 `vocals.wav`/`instrumental.wav` 등 단계 간 복사본이며, 이를 참조하는 job.json·레코드·pipeline이 하나도 없고 실행 중인 job도 없다. 삭제 직전에 참조를 다시 계산해서 확인한다. 이전 `delete`나 중단된 분석이 남긴 잔여물로 보인다(원인 미확정).")
w("- 이름만으로 판단하지 않았다. ORPHAN 판정은 위 참조 그래프 결과이며 목록은 `data/audit/library.json`에 있다.\n")

w("## 5. `tools/AudioSep`, `CLAPSepInference` 등 (6.6 GB)\n")
w("| 경로 | 크기 | 정체 | 코드가 쓰는가 | 테스트 | commercial preset | 판단 |\n|---|---:|---|---|---|---|---|")
w("| `tools/AudioSep` (+ `audiosep-env` 0.28 GB) | 3.46 GB + 0.28 GB | git clone `Audio-AGI/AudioSep`@`944583f1…` + 가중치 `audiosep_base_4M_steps.ckpt`(1.2 GB, SHA `f8cda01b…`) + CLAP `.pt`(2.2 GB, SHA `51c68f12…`) | `audiosep_experiment.py`(연구용 단발 실험)에서만 | 참조 없음 | 사용 안 함 (commercial preset·approval에 없음) | **REVIEW → 삭제 후보**. 프로덕션·baseline 경로가 없다. URL·SHA는 `configs/models/audiosep_base.json`에 남아 있어 재다운로드 가능 |")
w("| `tools/wesep-reference` | 0.52 GB | 연구용 참조(`avg_model.pt`, `bsrnn_ecapa_vox1.tar.gz`) | 준비 스크립트 `prepare-wesep-reference.py`뿐 | 없음 | 사용 안 함 | **REVIEW → 삭제 후보** (스크립트로 재생성 가능) |")
w("| `tools/CLAPSep` (git, 12 MB) + `CLAPSepInference` (2.41 GB, LAION-CLAP `.pt` 2.2 GB SHA `fae3e9c0…` + `best_model.ckpt` 170 MB SHA `6fcc8dbc…`) + `clapsep-env` (115 MB) | 2.5 GB | CLAPSep 추론 스택 | `synth_recovery.py`(final_11의 심벌 이동), `substem_pipeline.py`, `part_study.py`, `clapsep_experiment.py` | `test_release.py`는 commercial에서 **호출되지 않음**을 검사할 뿐 실행하지 않음 | **commercial 경로에서 사용하지 않음** (테스트가 보장) | **REVIEW — 삭제하면 final_11 BASELINE을 다시 돌릴 수 없다.** baseline 보존이 요구사항이었으므로 사용자 결정 필요 |")
w("\n- 로컬 clone과 가중치를 지우고 문서에 URL·SHA만 남기는 방안: AudioSep과 wesep은 가능. CLAPSep은 baseline 재현 포기를 뜻한다.\n- `AudioSep`의 `.pt`(CLAP)와 `CLAPSepInference`의 `.pt`는 **SHA가 달라서 중복이 아니다**(서로 다른 체크포인트 파일: `esc_89.98` vs `esc_90.14`).\n")

w("## 6. `reset-backups` (2.27 GB)\n")
for name, b in lib["reset_backups"].items():
    w(f"- `{name}`: 분석 {b['analysis_ids']}건 / job {b['jobs']} / input {b['inputs']} / substems {b['substems']}. **현재 라이브러리에 있는 id는 {b['ids_also_in_current_library']}건**, DB(analysis_owners)에도 없다. 내용은 `Orange` 곡의 기타·other·신스 비교 연구 분석 {b['analysis_ids']}건(이름 {len(b['names_missing_from_current'])}종, 예: `{b['names_missing_from_current'][0]}`)이며, 이 연구는 part-study 문서/보고서로 남아 있다. 복구에 필요한 사용자 분석은 확인되지 않았다 → **LEGACY_BACKUP, REVIEW (권고: 최종 단계에서 삭제 가능)**. 사용자가 전에 '마지막 단계에서 재판단'하기로 한 항목.")
w("")

b = art["benchmark_duplicates"]
w("## 7. 벤치마크 source / references 최소화\n")
w(f"`data/ground-truth`, `data/pad-eval`에서 1 MB 이상 오디오/배열 파일을 크기→SHA256으로 비교했다. **내용이 같은 파일 그룹 {b['groups']:,}개 (파일 {b['files_in_groups']:,}개), 중복 제거 시 약 {gb(b['dedup_saving_bytes'])}**.\n")
w("| 영역 | 절감 가능 | 중복 파일 수 |\n|---|---:|---:|")
for k, v in b["by_area"].items():
    w(f"| `{k}` | {gb(v['saving'])} | {v['files']:,} |")
w("\n예: 같은 믹스에서 만들어진 케이스 6개가 `acoustic_guitar.wav`, `bass.wav`, `brass.wav` 등 동일한 5 MB reference를 각자 복사해 갖고 있다 (`percussion-cowbell`, `percussion-bell_tree`, `real-timpani`, `controls-v16/vocal-violin` …).")
w("\n- 제안(미실행): 한 곳의 canonical fixture(`data/fixtures/<sha256>.wav`)를 두고 케이스는 `prepared.json`의 sha256으로 참조 → 약 11 GB 절감. 단 케이스 폴더가 파일 경로를 직접 읽는 코드(`ground_truth.evaluate`, `reevaluate-*`)가 있어 먼저 해석 계층이 필요하다.")
w("- 하드링크/심볼릭 링크 도입 검토: (1) Windows에서 심볼릭 링크는 권한이 필요하고 복사/백업 도구가 링크를 따라가 용량을 부풀리기 쉽다. (2) 하드링크는 같은 볼륨에서만 가능하고 한 이름을 지워도 다른 이름이 남아 삭제 수명주기 보고서(`storage-inventory`가 이미 `st_nlink`를 구분)와 충돌하지 않지만, 편집 시 모든 이름이 같이 바뀐다 → 읽기 전용 fixture라면 허용 가능. (3) 결정: 실행하지 않음. 효과가 11 GB이고 `stability-v11~v16`·`controls-v11~v16`처럼 **오래된 버전 폴더 자체를 줄이는 쪽이 더 단순**하다(REVIEW 항목).\n")

w("## 8. 체크포인트 감사 (`*.ckpt *.pth *.pt *.bin *.safetensors *.th *.onnx`, 1 MB 이상)\n")
w("프로젝트 안(`.venv` 제외) 25개. **동일 SHA256 중복은 0건**이다. `.venv`에는 1 MB 이상 가중치 파일이 없다.\n")
w("| 경로 (`data/separation/` 기준) | 크기 | SHA256 | model id | 레지스트리 | production preset | 승인 | 비고 |\n|---|---:|---|---|---|---|---|---|")
note = {"melband_karaoke": "UNKNOWN 라이선스, 개발용 vocal_detail", "bs_roformer_6s": "UNKNOWN, final_11 BASELINE 필요", "bs_karaoke": "UNKNOWN, final_11 BASELINE 필요",
        "bs_roformer_mega6": "레지스트리 승인 기록 없음 (실험용)", "bs_roformer_mega4": "승인 기록 없음 (실험용)"}
for c in sorted(art["checkpoints"], key=lambda c: -c["bytes"]):
    short = c["path"].replace("data/separation/", "")
    extra = note.get(c["model_id"], "")
    if not c["registered"]:
        extra = extra or ("official Mega53 원본: core4/vocal2/mega5/mega7 파생의 출처 (재다운로드 가능, 파생 재현에 필요)" if "official-53" in short else "레지스트리 미등록 (연구/실험)")
    w(f"| `{short}` | {mb(c['bytes'])} | `{(c['sha256'] or '')[:12]}…` | {c['model_id'] or '-'} | {'예' if c['registered'] else '아니오'} | {', '.join(c['production_presets']) or '-'} | {c['approval'] or '-'} | {extra} |")
w("\n- production에서 쓰는 체크포인트는 5개(KJ, mega7, mega5, core4, vocal2)로 1.46 GB.\n- 나머지 20개(약 11.6 GB)는 개발/실험/baseline용이다. 이 중 UNKNOWN·미승인 가중치(melband_karaoke 1.6 GB, bs_6stem 0.67 GB, bs_karaoke 0.19 GB)를 지우면 final_11 baseline과 vocal_detail 기능이 동작하지 않는다 (REVIEW). `licenses`/approval 증빙 파일(`commercial_approval.json`, 모델 JSON)은 어떤 경우에도 삭제 대상이 아니다.\n")

g = art["git"]
w("## 9. `.git`\n")
w(f"- 전체 {g['dir_bytes'] / 2**20:.1f} MB, 커밋 {g['commits']}개, pack 없음(loose objects 1,641개, 9.29 MiB), LFS 없음.\n- 가장 큰 blob {g['largest_blobs'][0]['bytes'] / 2**20:.2f} MB (`{g['largest_blobs'][0]['path']}`). 과거 대형 WAV/모델을 커밋한 흔적 없음 → 히스토리 재작성으로 회수할 용량은 사실상 0. (`.gitignore`가 `*.wav`, `*.mp3`, `*.ckpt` 등을 막고 있다.)\n")

w("## 10. 프로젝트 내부 개발 cache\n")
w("| 위치 | 종류 | 크기 | 비고 |\n|---|---|---:|---|")
for k, v in sorted(art["caches"].items(), key=lambda kv: -kv[1]["bytes"]):
    where, kind = k.split(":"); w(f"| {where} | {kind} | {v['bytes'] / 2**20:.1f} MB ({v['dirs']} dirs) | 재생성 가능 |")
w(f"| 전체 | `*.log` | {art['logs']['bytes'] / 2**20:.1f} MB ({art['logs']['count']} files) | 재생성 불필요 |")
w("\n프로젝트 안에 pip/HuggingFace/torch 다운로드 cache 디렉터리는 없다. 시스템 전역 cache(`%LOCALAPPDATA%\\pip`, `~/.cache/huggingface`, `~/.cache/torch` 등)는 프로젝트 정리 범위가 아니므로 측정·삭제하지 않았다. `.venv`(4.67 GB)는 실행에 필요한 런타임이며 requirements에서 재생성 가능하므로 KEEP.\n")

w("## 11. 최종 WAV 저장 비용 (포맷 변경 없음, 수치만)\n")
w("실제 최종 stem으로 측정(`scripts/audio-format-benchmark.py`): 2트랙=`bed`(basic_2, 150 s), 6트랙·13트랙=같은 곡 `오늘을 채워 가`(173 s).\n")
w("| 세트 | 포맷 | 크기 | float32 대비 | 인코딩 | 디코딩 | 전 stem WAV(PCM24)로 내려받기 | 최대 오차 | 합계 오차 (원본 대비) |\n|---|---|---:|---:|---:|---:|---:|---:|---:|")
for label in ("2-track", "6-track", "13-track"):
    e = fmt[label]; base = e["formats"]["float32_wav"]["bytes"]
    for f, v in e["formats"].items():
        w(f"| {label} ({e['stems']} stems) | {f} | {v['mb']} MB | {100 * v['bytes'] / base:.0f}% | {v['encode_s']} s (CPU {v['encode_cpu_s']} s) | {v['decode_s']} s (CPU {v['decode_cpu_s']} s) | {v['wav_download_s']} s | {v['max_abs_error_vs_float32']:.1e} | {v['partition_error_vs_original_after']:.1e} |")
w("\n- **무손실이 아니다**: PCM24와 FLAC24는 float32를 24 bit로 양자화한다(최대 오차 6e-8~1.2e-7, 약 -138~-144 dBFS). 현재 계약의 합계 오차 허용(2e-6) 안에는 들어오지만, **13 stem을 PCM24로 저장하면 합계 오차가 1.33e-6**으로 여유가 크게 줄어든다(FLAC24 6.0e-7). 샘플 절댓값이 1.0을 넘는 stem은 이 곡들에서 0개였다(다른 곡은 미측정, 클리핑 위험).\n- 크기: PCM24는 float32의 75 %, FLAC24는 이 곡들에서 **25~32 %**. 조용한 stem이 많은 곡일수록 FLAC 이득이 크다(곡마다 다름).\n- 인코딩/디코딩 비용: FLAC24 인코딩은 13 stem에 12.4 s(CPU 2.9 s), 디코딩 3.7 s(CPU 0.4 s) — 분석 1건당 1회 인코딩이므로 233 s 처리 시간에 비해 작다. 재생 미리듣기는 이미 PCM16/FLAC이라 영향 없음.\n- 재생·다운로드: 브라우저(Web Audio/HTMLAudio)는 FLAC 재생 가능, 서버는 이미 `audio/flac` MIME과 Range 응답을 지원한다. WAV로 내려받으려면 변환이 필요하다(13 stem 전체 8.4 s, stem 하나는 약 0.65 s). 변환을 요청 시점에 하면 임시 파일이 필요하다(방금 정리한 ZIP 정책과 같은 방식).\n- RAM: 측정 방식은 stem 전체를 한 번에 메모리에 올린 값이라 파일 합계(13트랙 758 MB)와 같다. 스트리밍 변환 시 stem 하나 분량으로 줄일 수 있다(미구현·미측정).")
proj = {"float32": 43.24, "pcm24": 32.43, "flac24": 11.27}
w(f"\n**`data/separation/web`(최종 stem + original 43.24 GB)의 예상**: PCM24 약 {proj['pcm24']} GB (−10.8 GB), FLAC24 약 {proj['flac24']} GB (−32.0 GB). 같은 비율을 적용한 추정이며 곡 내용에 따라 달라진다. `data/separation` 전체 66.1 GB 기준으로는 PCM24 약 55 GB, FLAC24 약 34 GB. 포맷 변경은 하지 않았고, 도입한다면 합계 보존 계약(2e-6)과 `manifest.json` 해시 정의를 먼저 바꿔야 한다.\n")

w("## 12. 삭제 계획 (dry-run — 승인 전 어떤 것도 삭제하지 않음)\n")
w(f"현재 전체 프로젝트: **{gb(cls['total'])}**\n")
w("| 위험도 | 용량 | 내용 |\n|---|---:|---|")
safe_items = [x for x in cls["labels"] if x["risk"] == "SAFE"]
w(f"| **SAFE** (바로 삭제 가능) | {gb(risk['SAFE'])} | ORPHAN 입력 asset 5.33 GB, FAILED 분석의 스크래치와 기록 1.6 GB, `.venv`/프런트/데이터 `__pycache__`·빌드 cache ~0.3 GB, 오래된 smoke·로그, 이번 감사 산출물 |")
review_n = sum(1 for a in lib["analyses"] if a["classification"] in ("DEMO", "MANUAL_TEST", "BENCHMARK") and a["state"] == "SUCCEEDED")
review_gb = sum(a["folder_bytes"] for a in lib["analyses"] if a["classification"] in ("DEMO", "MANUAL_TEST", "BENCHMARK") and a["state"] == "SUCCEEDED") / 2**30
mb_n = sum(1 for a in lib["analyses"] if a["classification"] in ("MANUAL_TEST", "BENCHMARK") and a["state"] == "SUCCEEDED")
mb_gb = sum(a["folder_bytes"] for a in lib["analyses"] if a["classification"] in ("MANUAL_TEST", "BENCHMARK") and a["state"] == "SUCCEEDED") / 2**30
w(f"| **REVIEW** (사용자 확인 후) | {gb(risk['REVIEW'])} | 분석 {review_n}건(약 {review_gb:.1f} GB; DEMO 1.2 / MANUAL_TEST 24.4 / BENCHMARK 17.5 중 FAILED 1건 제외), 케이스 references·reports 27.1 GB(중복 제거 시 −11.2 GB), AudioSep·wesep 4.1 GB, CLAPSep 스택 2.5 GB(baseline 재현 포기), 비production 가중치 3.5 GB, official-53 1.4 GB, 단독 job 항목 1.3 GB, reset-backups 2.3 GB, medleydb·philharmonia 1.0 GB, `song/` 0.13 GB |")
w(f"| **KEEP** | {gb(risk['KEEP'])} | `.venv` 4.7 GB, production 체크포인트 1.5 GB, 소스·설정·문서·라이선스 증빙, 청정 벤치마크 source(BabySlakh, FreePats, pad-eval stems), 데모곡 mix·stems, report·metrics, `.git` |")
w(f"| **UNKNOWN** | {gb(risk['UNKNOWN'])} | 분석 `bed`(basic_2, 150 s, 소스 불명) |")
w(f"\n### 권고 순서\n1. SAFE 7.2 GB: 승인되면 삭제 직전에 참조 그래프를 다시 계산해서(그 사이 새 분석이 생길 수 있음) 실행.\n2. REVIEW 중 가장 큰 효과: (a) 분석 50건 처리 방침(전부 보관 / MANUAL_TEST·BENCHMARK {mb_n}건 삭제 시 약 {mb_gb:.1f} GB 회수 / DEMO는 별도), (b) `ground-truth/cases`·`pad-eval/cases`의 이전 버전 폴더 정리 또는 sha256 dedup(약 11 GB), (c) AudioSep·wesep 삭제(4.1 GB), (d) reset-backups(2.3 GB).\n3. 포맷 최적화(FLAC24, −32 GB 예상)는 삭제가 아니라 별도 결정 사항이며, 합계 보존 계약·manifest 변경이 선행된다.\n")
w("사용자 데이터로 의심되는 파일(`B USER_PERSISTENT`, `I UNKNOWN`)은 이 보고서에서 삭제 대상으로 확정하지 않았다.")
Path(ROOT / "docs/FULL_DISK_AUDIT_KO.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("written", len(L), "lines")
