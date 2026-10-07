"""Prepare seven unchanged official heads and pin derived checkpoint/config provenance."""
import copy
import torch
import yaml
from music_analyzer.common import project_root,read_json,write_json,sha256_file
from music_analyzer.mega53_experiment import configuration,prune_heads,CHECKPOINT_SHA,folder,ConfigDumper
from music_analyzer.vendor.msst.bs_roformer import BSRoformer

base=project_root();source=folder()/'official-53.ckpt'
assert sha256_file(source)==CHECKPOINT_SHA
selected=[1,16,38,7,8,32,40];config=configuration();labels=config['training']['instruments']
weights=torch.load(source,map_location='cpu',weights_only=True)
reduced=prune_heads(weights,selected);del weights
config=copy.deepcopy(config);config['model']['num_stems']=len(selected)
config['training']['instruments']=[labels[i] for i in selected]
model=BSRoformer(**config['model']);model.load_state_dict(reduced,strict=True);del model
directory=base/'data/separation/models/bs_roformer_mega7';directory.mkdir(exist_ok=True)
checkpoint=directory/'mega7.ckpt'
if not checkpoint.exists():torch.save(reduced,checkpoint)
configuration_path=base/'separation/configs/models/bs_roformer_mega7.upstream.yaml'
if not configuration_path.exists():configuration_path.write_text(yaml.dump(config,Dumper=ConfigDumper,sort_keys=False),encoding='utf-8')
entry=read_json(base/'separation/configs/models/bs_roformer_mega5.json')
entry.update(model_id='bs_roformer_mega7',checkpoint_filename='mega7.ckpt',checkpoint_signature='mega7',
             upstream_sha256_prefix=sha256_file(checkpoint),source_labels=config['training']['instruments'],
             upstream_config_file=configuration_path.name,upstream_config_sha256=sha256_file(configuration_path))
entry['source_mapping']['percussion']='instrument.percussion'
entry['source_mapping']['timpani']='instrument.percussion.timpani'
entry['derivation']['selected_heads']={str(i):labels[i] for i in selected}
entry['quality_notes']=['Seven independent unchanged official heads; contextual evidence is filtered before routing.']
path=base/'separation/configs/models/bs_roformer_mega7.json'
if path.exists():
    existing=read_json(path)
    assert existing['upstream_sha256_prefix']==entry['upstream_sha256_prefix']
    assert existing['upstream_config_sha256']==entry['upstream_config_sha256']
else:write_json(path,entry)
write_json(directory/'registration.json',{**entry,'checkpoint_sha256':sha256_file(checkpoint),
           'artifact_hashes':{checkpoint.name:sha256_file(checkpoint)},'config_sha256':sha256_file(path),
           'verification':{'source_sha256':CHECKPOINT_SHA,'strict_load':True,'transform':'head-pruning-only'}})
print('SEVEN OFFICIAL HEADS PREPARED',checkpoint.stat().st_size,flush=True)
