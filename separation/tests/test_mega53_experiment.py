import pytest
import torch
import yaml
from music_analyzer.mega53_experiment import TARGETS, EXTENDED_TARGETS, BOWED_TARGETS, ConfigDumper, configuration, prune_heads
from music_analyzer.roformer_runner import ConfigLoader


@pytest.mark.parametrize("targets", [TARGETS, EXTENDED_TARGETS, BOWED_TARGETS])
def test_official_config_and_head_pruning_preserve_exact_tensors(targets):
    config = configuration(targets)
    assert yaml.load(yaml.dump(config, Dumper=ConfigDumper), Loader=ConfigLoader) == config
    assert [config["training"]["instruments"][i] for i in targets] == list(targets.values())
    weights = {"shared": torch.tensor([3.])}
    weights.update({f"mask_estimators.{i}.weight": torch.tensor([float(i)]) for i in range(53)})
    result = prune_heads({"state_dict": {"module." + k: v for k, v in weights.items()}}, tuple(targets))
    assert set(result) == {"shared", *(f"mask_estimators.{i}.weight" for i in range(len(targets)))}
    assert result["shared"] is weights["shared"]
    for new, old in enumerate(targets):
        assert result[f"mask_estimators.{new}.weight"] is weights[f"mask_estimators.{old}.weight"]
    with pytest.raises(ValueError, match="53 official heads"):
        prune_heads({k: v for k, v in weights.items() if k != "mask_estimators.38.weight"})
    with pytest.raises(ValueError, match="Invalid selected heads"):
        prune_heads(weights, (1, 1))
