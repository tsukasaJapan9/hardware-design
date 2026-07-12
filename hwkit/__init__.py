"""hwkit — printable, assemblable hardware with build123d.

    from build123d import *
    from hwkit import *

    P = load_profile()
    asm = Assembly("gizmo", P)

Two rules the rest of this follows from:

  Every clearance derives from a measured `PrinterProfile`, never a literal, so
  one calibration propagates to every fit in every design.

  Every bought part is a `Component` — modelled, with its keepouts, before the
  bracket that holds it exists. A mount is a negative of a component, and a
  negative of a guess is scrap.
"""

from .assembly import Assembly, Hardware, PrintedPart
from .components import (
    CELL_18650,
    CHECKLIST,
    COMPONENTS,
    NEMA17,
    RPI5,
    SG90,
    Component,
    MissingComponentData,
    Mount,
    MountHoles,
    Vol,
    require,
)
from .fasteners import (
    M2,
    M2_5,
    M3,
    M4,
    M5,
    M6,
    SCREWS,
    ClearanceHole,
    CounterBore,
    CounterSink,
    InsertBoss,
    NutPocket,
    Screw,
)
from .parts import (
    BEARINGS,
    SHAFTS,
    Bearing,
    BearingPocket,
    ShaftBore,
)
from .profile import DEFAULT, PrinterProfile
from .profile import load as load_profile
from .validate import (
    Issue,
    Report,
    check_clearance,
    check_interference,
    check_part,
)

__all__ = [
    # assembly
    "Assembly",
    "Hardware",
    "PrintedPart",
    # profile
    "PrinterProfile",
    "DEFAULT",
    "load_profile",
    # bought components: model these FIRST
    "Component",
    "Mount",
    "Vol",
    "MountHoles",
    "COMPONENTS",
    "CHECKLIST",
    "MissingComponentData",
    "require",
    "NEMA17",
    "RPI5",
    "SG90",
    "CELL_18650",
    # fasteners
    "Screw",
    "SCREWS",
    "M2",
    "M2_5",
    "M3",
    "M4",
    "M5",
    "M6",
    "ClearanceHole",
    "CounterBore",
    "CounterSink",
    "InsertBoss",
    "NutPocket",
    # mechanical
    "Bearing",
    "BEARINGS",
    "BearingPocket",
    "ShaftBore",
    "SHAFTS",
    # validation
    "Issue",
    "Report",
    "check_part",
    "check_interference",
    "check_clearance",
]
