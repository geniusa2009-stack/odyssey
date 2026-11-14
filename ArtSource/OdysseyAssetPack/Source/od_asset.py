"""ODYSSEY Asset Pack - asset description shared by every asset script."""
from __future__ import annotations

from dataclasses import dataclass, field

from od_core import Node


@dataclass
class Asset:
    name: str                      # OD_* asset name (= root node name, = GLB file name)
    title: str
    reference: str                 # approved reference image(s) - visual only
    envelope: tuple                # (W along Y, H along Z, D along X) in cm
    pivot: str                     # floor | wall_base | wall | ceiling
    pivot_text: str
    root: Node
    description: str = ""
    collision: str = ""
    nanite: str = ""
    interaction: list = field(default_factory=list)   # (name, socket node, text)
    mounting: list = field(default_factory=list)      # (name, socket node, text)
    notes: list = field(default_factory=list)
    allow_pairs: tuple = ()        # intentional interpenetrations (none expected)
