"""Synthetic Music Data Factory. Independent of the separator engine: the only shared contracts are the waveform
layout (channels, samples), the target dictionary {stem: array}, and the dataset/asset manifest policy
(`engine.data.manifest`, imported only by `assets.py` and `adapter.py`)."""
GENERATOR_VERSION = "df0.1"
SAMPLE_RATE = 44100
