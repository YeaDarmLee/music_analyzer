"""Name -> object registries. Model builders, losses, metrics and datasets are all plug-ins."""
from __future__ import annotations

from typing import Callable


class Registry:
    def __init__(self, kind: str):
        self.kind = kind
        self._items: dict[str, Callable] = {}

    def register(self, name: str):
        def deco(obj):
            if name in self._items:
                raise KeyError(f"{self.kind} '{name}' already registered")
            self._items[name] = obj
            return obj
        return deco

    def get(self, name: str):
        if name not in self._items:
            raise KeyError(f"unknown {self.kind} '{name}'; registered: {sorted(self._items)}")
        return self._items[name]

    def names(self) -> list[str]:
        return sorted(self._items)


MODELS = Registry("model")      # builder(model_cfg) -> SeparatorModel
LOSSES = Registry("loss")       # fn(out, target, mix, **kwargs) -> scalar tensor
METRICS = Registry("metric")    # fn(out, target, mix, **kwargs) -> float
DATASETS = Registry("dataset")  # builder(dataset_cfg, model_cfg, split, seed) -> torch Dataset


def build_model(model_cfg: dict):
    import engine.models  # noqa: F401  (registers built-ins)
    return MODELS.get(model_cfg["model_id"])(model_cfg)
