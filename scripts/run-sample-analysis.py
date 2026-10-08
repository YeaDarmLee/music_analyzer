"""Run the full 13-track pipeline on the rendered demo song in an isolated library (data/sample/library)."""
import os
import time
from music_analyzer.common import project_root, read_json, write_json
from music_analyzer.registry import paths
from music_analyzer.web_server import WebLibrary

base = project_root()
source = base / 'data/separation'
sample = base / os.environ.get('SAMPLE_DIR', 'data/sample')
root = sample / 'library'
for model in ('melband_roformer_kj', 'bs_roformer_6s', 'bs_karaoke', 'bs_roformer_mega5', 'bs_roformer_mega7'):
    checkpoint, registration = paths(source, model)
    target = root / 'models' / model; target.mkdir(parents=True, exist_ok=True)
    if not (target / checkpoint.name).exists(): os.link(checkpoint, target / checkpoint.name)
    write_json(target / 'registration.json', read_json(registration))
library = WebLibrary(root)
try:
    original = sample / 'mix.wav'
    with original.open('rb') as stream:
        public = library.create('demo-song.wav', 'final_11', stream, original.stat().st_size)
    write_json(sample / 'run.json', {'id': public['id'], 'root': str(root.resolve())})
    previous = None
    while True:
        row = library.get(public['id'])
        if previous != row['stage']: print(row['stage'], flush=True); previous = row['stage']
        if row['state'] in ('SUCCEEDED', 'FAILED', 'CANCELLED'): break
        time.sleep(.5)
    if row['state'] != 'SUCCEEDED': raise RuntimeError(row.get('error', row))
    print('SAMPLE SUCCEEDED', row['id'], flush=True)
finally:
    library.executor.shutdown(wait=True)
