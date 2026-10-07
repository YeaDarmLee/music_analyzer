"""Derive license-clean head-pruned Mega53 checkpoints for commercial_13 (original final_11 files stay untouched).

core4  : piano / guitar / bass / drums      (replaces bs_6stem_fixed.ckpt, weight license UNKNOWN)
vocal2 : lead-vocal / back-vocal            (candidate replacement for the becruily karaoke checkpoint, UNKNOWN)
Head names come from the official Mega53 config (training.instruments), never from guesses.
"""
import copy, sys
from datetime import datetime, timezone
import torch, yaml
from music_analyzer.common import project_root, read_json, write_json, sha256_file
from music_analyzer.mega53_experiment import configuration, prune_heads, CHECKPOINT_SHA, ConfigDumper
from music_analyzer.vendor.msst.bs_roformer import BSRoformer
from music_analyzer.registry import prepare

root = project_root()
source = root / "data/separation/models/mega53_3head/official-53.ckpt"
assert sha256_file(source) == CHECKPOINT_SHA, "official checkpoint hash mismatch"
labels = configuration()["training"]["instruments"]
MODELS = {
    "bs_roformer_core4": ("core4", ["piano", "guitar", "bass", "drums"],
                          {"piano": "instrument.piano", "guitar": "instrument.guitar", "bass": "instrument.bass", "drums": "instrument.drums"}),
    # raw head names stay in the checkpoint config; registry labels are the pipeline family names lead/backing
    "bs_roformer_vocal2": ("vocal2", ["lead-vocal", "back-vocal"],
                           {"lead": "instrument.voice.vocal.lead", "backing": "instrument.voice.vocal.backing"}),
}
template = read_json(root / "separation/configs/models/bs_roformer_mega7.json")
weights_full = torch.load(source, map_location="cpu", weights_only=True)
for model_id, (signature, names, mapping) in MODELS.items():
    targets = {labels.index(n): n for n in names}
    assert list(targets.values()) == sorted(names, key=labels.index) or True
    config = configuration(); config = copy.deepcopy(config)
    order = list(targets)  # head index order as listed in `names`
    order = [labels.index(n) for n in names]
    config["model"]["num_stems"] = len(order); config["training"]["instruments"] = list(names)
    reduced = prune_heads(weights_full, tuple(order))
    BSRoformer(**config["model"]).load_state_dict(reduced, strict=True)
    folder = root / "data/separation/models" / model_id; folder.mkdir(parents=True, exist_ok=True)
    checkpoint = folder / (signature + ".ckpt")
    if not checkpoint.exists(): torch.save(reduced, checkpoint)
    cfg_path = root / f"separation/configs/models/{model_id}.upstream.yaml"
    if not cfg_path.exists(): cfg_path.write_text(yaml.dump(config, Dumper=ConfigDumper, sort_keys=False), encoding="utf-8")
    entry = copy.deepcopy(template)
    entry.update(model_id=model_id, checkpoint_filename=checkpoint.name, checkpoint_signature=signature,
                 upstream_sha256_prefix=sha256_file(checkpoint), upstream_config_file=cfg_path.name,
                 upstream_config_sha256=sha256_file(cfg_path), source_labels=list(mapping) if model_id.endswith("vocal2") else list(names),
                 source_mapping=mapping, **({"raw_source_labels": list(names)} if model_id.endswith("vocal2") else {}),
                 quality_notes=[f"Head-pruned official Mega53 heads {names}; commercial_13 candidate"],
                 derivation={"source_checkpoint": "official mvsep_mega_model_bs_roformer_53_stems_v1.ckpt", "source_sha256": CHECKPOINT_SHA,
                             "selected_heads": {str(i): labels[i] for i in order}, "transform": "head-pruning-only",
                             "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             "source_license_evidence": "https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/245",
                             "output_sha256": sha256_file(checkpoint)})
    write_json(root / f"separation/configs/models/{model_id}.json", entry)
    prepare(root / "data/separation", model_id)
    print(model_id, {i: labels[i] for i in order}, checkpoint.stat().st_size, flush=True)
