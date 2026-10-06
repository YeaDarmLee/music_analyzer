"""Prepare three 20-second reference remixes from the official MedleyDB sample."""
import argparse
from pathlib import Path
import shutil
import tarfile

from music_analyzer.common import project_root, write_json, sha256_file
from music_analyzer.ground_truth import prepare

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('archive', type=Path)
args = parser.parse_args()
root = project_root()/'data/ground-truth'
songs = {'Phoenix_ScotchMorris': 4, 'LizNelson_Rainfall': 5}
expected = {}
for song,count in songs.items():
    for filename in [song+'_METADATA.yaml']+[f'{song}_STEMS/{song}_STEM_{n:02}.wav' for n in range(1,count+1)]:
        expected[f'MedleyDB_sample/Audio/{song}/{filename}'] = root/'medleydb'/song/filename
with tarfile.open(args.archive, 'r:gz') as archive:
    for member in archive:
        if member.name not in expected:
            continue
        if not member.isfile():
            raise ValueError('Expected regular sample file')
        destination = expected.pop(member.name)
        destination.parent.mkdir(parents=True,exist_ok=True)
        with archive.extractfile(member) as source, destination.open('wb') as target:
            shutil.copyfileobj(source,target)
if expected:
    raise ValueError('Missing sample stems: '+str(list(expected)))

def names(song, *numbers):
    return [f'../../medleydb/{song}/{song}_STEMS/{song}_STEM_{n:02}.wav' for n in numbers]

phoenix = {'acoustic_guitar': names('Phoenix_ScotchMorris',1),
           'strings': names('Phoenix_ScotchMorris',3), 'other': names('Phoenix_ScotchMorris',2)}
rainfall = {'lead': names('LizNelson_Rainfall',1), 'backing': names('LizNelson_Rainfall',2,3),
            'acoustic_guitar': names('LizNelson_Rainfall',4), 'guitar': names('LizNelson_Rainfall',5)}
for name,start,bleed,sources in [
    ('phoenix-30-50',30,True,phoenix),
    ('rainfall-40-60',40,False,rainfall),
    ('rainfall-guitars-only-40-60',40,False,{k:v for k,v in rainfall.items() if k in ('acoustic_guitar','guitar')}),
]:
    path = root/'cases'/name/'case.json'
    write_json(path, {'name':name,'start_sec':start,'duration_sec':20,'has_bleed':bleed,
                     'reference_sources':sources,'dataset_url':'https://medleydb.weebly.com/downloads.html',
                     'archive_sha256':sha256_file(args.archive),
                     'license':'CC BY-NC-SA 4.0',
                     'input_kind':'unmastered equal-gain stem remix; not the released MIX.wav'})
    prepare(path)
    print('PREPARED',path,flush=True)
