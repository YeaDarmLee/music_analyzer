"""Build and register the accepted four Mega53 heads for local ten-track analysis."""
import copy
from pathlib import Path
import torch
import yaml
from music_analyzer.common import project_root, read_json, write_json, sha256_file
from music_analyzer.mega53_experiment import configuration, prune_heads, CHECKPOINT_SHA, ConfigDumper
from music_analyzer.vendor.msst.bs_roformer import BSRoformer
from music_analyzer.registry import prepare

root = project_root()
original = root / "data/separation/models/mega53_3head/official-53.ckpt"
if sha256_file(original) != CHECKPOINT_SHA:
    raise ValueError("Official checkpoint hash mismatch")
targets = {1: "acoustic-guitar", 16: "electric-guitar", 38: "synth", 7: "bowed_strings"}
config = configuration(targets)
config["model"]["num_stems"] = 4
config["training"]["instruments"] = list(targets.values())
weights = prune_heads(torch.load(original, map_location="cpu", weights_only=True), tuple(targets))
model = BSRoformer(**config["model"])
model.load_state_dict(weights, strict=True)
model_id = "bs_roformer_mega4"
folder = root / "data/separation/models" / model_id
folder.mkdir(parents=True, exist_ok=True)
checkpoint = folder / "mega4.ckpt"
temporary = checkpoint.with_suffix(".partial")
torch.save(weights, temporary)
temporary.replace(checkpoint)
config_path = root / "separation/configs/models/bs_roformer_mega4.upstream.yaml"
config_path.write_text(yaml.dump(config, Dumper=ConfigDumper, sort_keys=False), encoding="utf-8")
entry = copy.deepcopy(read_json(root / "separation/configs/models/bs_roformer_6s.json"))
entry.update(model_id=model_id, checkpoint_filename="mega4.ckpt", checkpoint_signature="mega4",
             checkpoint_index_evidence="https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.21",
             checkpoint_url="local-derived:official-mega53", upstream_sha256_prefix=sha256_file(checkpoint),
             upstream_config_file=config_path.name, upstream_config_sha256=sha256_file(config_path),
             source_labels=list(targets.values()), source_mapping={
                 "acoustic-guitar": "instrument.guitar.acoustic", "electric-guitar": "instrument.guitar.electric",
                 "synth": "instrument.synth", "bowed_strings": "instrument.strings"},
             weight_license={"value": "MIT", "status": "VERIFIED_DECLARATION", "evidence_url": "https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/245"},
             quality_notes=["Accepted local instrument heads; independent estimates may overlap"],
             derivation={"source_sha256": CHECKPOINT_SHA, "selected_heads": targets, "transform": "head-pruning-only"})
write_json(root / "separation/configs/models/bs_roformer_mega4.json", entry)
prepare(root / "data/separation", model_id)
print("Final four-head model registered", flush=True)
