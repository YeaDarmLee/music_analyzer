from engine.registry import MODELS

from .model import OurSeparatorV01, build

MODELS.register("our_separator_v01")(build)

__all__ = ["OurSeparatorV01", "build"]
