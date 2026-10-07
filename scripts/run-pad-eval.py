"""Run the production pipeline on every pad-eval case; resumable."""
import sys
from pathlib import Path
from music_analyzer.common import project_root
from music_analyzer.ground_truth import run

base = project_root() / 'data/pad-eval/cases'
only = sys.argv[1:]
for case in sorted(base.iterdir()):
    if only and not any(case.name.startswith(o) for o in only): continue
    if (case / 'report.json').exists(): continue
    try: run(case)
    except Exception as error: print('FAILED', case.name, error, flush=True)
print('PAD EVAL RUN DONE', flush=True)
