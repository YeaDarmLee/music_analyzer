"""Symbolic scene representation. The scene spec (seeds + chosen parameters + note events) is the source of truth;
MIDI is only a debug export."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .util import hash_obj

ATOMIC_STEMS = ("vocal", "drums", "bass", "piano", "synth")  # v0; guitar/strings/brass/organ are added later


@dataclass
class NoteEvent:
    instrument: str          # atomic stem name
    pitch: int               # MIDI note number (drums: role key, see drum_roles)
    velocity: int            # 1..127
    start: float             # seconds
    end: float               # seconds (note-off; release tail continues after it)
    articulation: str = ""
    channel: int = 0
    meta: dict = field(default_factory=dict)

    def to_list(self):
        return [self.instrument, self.pitch, self.velocity, round(self.start, 6), round(self.end, 6),
                self.articulation, self.channel, self.meta]

    @classmethod
    def from_list(cls, v):
        return cls(v[0], int(v[1]), int(v[2]), float(v[3]), float(v[4]), v[5], int(v[6]), dict(v[7]))


@dataclass
class SceneSpec:
    scene_id: str
    split: str
    composition_family_id: str
    duration_samples: int
    sample_rate: int
    seeds: dict
    scene_type: str
    profile: str
    composition: dict                 # bpm, key, mode, chords, section_type, rule version
    active_stems: list
    note_events: list                 # NoteEvent.to_list() rows
    renderers: dict                   # stem -> {kind, instrument_id | patch | kit}
    fx: dict                          # stem -> chain (list of effect dicts)
    mix: dict                         # gains in dB, peak limit
    vocal: dict | None                # {clip_id, crop_start_s, ...}
    assets: list                      # asset_ids used (for the license manifest)
    target_schema: str = "atomic_v1"
    generator_version: str = ""
    git_commit: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SceneSpec":
        return cls(**d)

    def hash(self) -> str:
        d = self.to_dict()
        d.pop("git_commit", None)  # provenance-only, must not change the identity of the scene content
        return hash_obj(d)

    def events(self) -> list[NoteEvent]:
        return [NoteEvent.from_list(r) for r in self.note_events]
