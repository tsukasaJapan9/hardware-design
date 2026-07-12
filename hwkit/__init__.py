"""hwkit — printable, assemblable hardware with build123d.

    from build123d import *
    from hwkit import *

    P = load_profile()
    asm = Assembly("gizmo", P)

Every clearance is derived from a PrinterProfile, so one calibration measurement
propagates to every fit in the design.
"""

from .assembly import Assembly, Hardware, PrintedPart
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
    FOOTPRINTS,
    NEMA17,
    RPI4,
    SHAFTS,
    Bearing,
    BearingPocket,
    Footprint,
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
    # bought parts
    "Bearing",
    "BEARINGS",
    "BearingPocket",
    "ShaftBore",
    "Footprint",
    "FOOTPRINTS",
    "NEMA17",
    "RPI4",
    "SHAFTS",
    # validation
    "Issue",
    "Report",
    "check_part",
    "check_interference",
    "check_clearance",
]
