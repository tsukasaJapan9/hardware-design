"""Metric fasteners: dimension tables and the pockets that receive them.

Printed threads strip. Everything here assumes real metal hardware held by one
of three joints, in descending order of preference:

  1. heat-set insert  - reusable, strongest in a printed boss, needs a soldering iron
  2. captive hex nut  - free, strong, needs a pocket the nut cannot rotate in
  3. self-tapping into a plain hole - light loads only, one assembly cycle

Every pocket here is a `BasePartObject`, so it behaves like build123d's own
`Hole`: it cuts itself at the active `Locations` and honours `Mode`. All of them
drill DOWN (-Z) from the location, so the idiom is

    with Locations(Plane(top_face)):
        with Locations((-10, 0), (10, 0)):
            CounterBore(M3, depth=6)

Screw head and nut dimensions are ISO/DIN nominal and safe to trust. Heat-set
insert lengths vary by brand; check yours against `Screw.insert_len`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Align, BuildPart, Face, Mode, Plane, Solid, Vector, Wire
from build123d.objects_part import BasePartObject

from .profile import DEFAULT, PrinterProfile


@dataclass(frozen=True)
class Screw:
    """A metric machine screw. All dims in mm."""

    name: str
    dia: float  # thread nominal diameter
    pitch: float
    head_dia: float  # socket cap head (ISO 4762 / DIN 912)
    head_h: float
    cs_head_dia: float  # countersunk head (ISO 10642), 90 degrees included
    nut_af: float  # hex nut across-flats (ISO 4032 / DIN 934)
    nut_h: float
    washer_dia: float
    insert_hole: float  # heat-set insert: boss hole diameter
    insert_len: float  # heat-set insert: body length

    @property
    def nut_ac(self) -> float:
        """Hex nut across-corners (the circumscribed circle)."""
        return self.nut_af / math.cos(math.radians(30))


# Insert values follow the common brass "standard" series (CNC Kitchen /
# McMaster 94459A): M3 = 4.0 x 5.7, M4 = 5.6 x 8.1.
M2 = Screw("M2", 2.0, 0.40, 3.8, 2.0, 4.0, 4.0, 1.6, 5.0, 3.2, 4.0)
M2_5 = Screw("M2.5", 2.5, 0.45, 4.5, 2.5, 5.0, 5.0, 2.0, 6.0, 3.6, 4.0)
M3 = Screw("M3", 3.0, 0.50, 5.5, 3.0, 6.0, 5.5, 2.4, 7.0, 4.0, 5.7)
M4 = Screw("M4", 4.0, 0.70, 7.0, 4.0, 8.0, 7.0, 3.2, 9.0, 5.6, 8.1)
M5 = Screw("M5", 5.0, 0.80, 8.5, 5.0, 10.0, 8.0, 4.0, 10.0, 6.4, 9.5)
M6 = Screw("M6", 6.0, 1.00, 10.0, 6.0, 12.0, 10.0, 5.0, 12.0, 8.0, 12.7)

SCREWS = {s.name: s for s in (M2, M2_5, M3, M4, M5, M6)}

_DOWN = Plane(origin=(0, 0, 0), z_dir=(0, 0, -1))


def _drill(radius: float, depth: float, z_top: float = 0.0) -> Solid:
    """A cylinder hanging DOWN from z_top."""
    return Solid.make_cylinder(
        radius, depth, Plane(origin=(0, 0, z_top), z_dir=(0, 0, -1))
    )


def _hex_prism(across_flats: float, depth: float, z_top: float = 0.0) -> Solid:
    """A hex prism hanging DOWN from z_top, sized across the flats."""
    cr = across_flats / math.cos(math.radians(30)) / 2
    pts = [
        Vector(cr * math.cos(math.radians(60 * i)), cr * math.sin(math.radians(60 * i)), z_top)
        for i in range(6)
    ]
    return Solid.extrude(Face(Wire.make_polygon(pts, close=True)), (0, 0, -depth))


class ClearanceHole(BasePartObject):
    """A hole the screw shank passes through without touching.

    `fit` picks how much room: "free" for a plate the screw passes through,
    "snug" when the hole also has to locate the part.
    """

    _applies_to = [BuildPart._tag]

    def __init__(
        self,
        screw: Screw,
        depth: float,
        *,
        fit: str = "free",
        profile: PrinterProfile = DEFAULT,
        mode: Mode = Mode.SUBTRACT,
    ):
        self.screw = screw
        self.hole_dia = profile.hole(screw.dia, fit)
        super().__init__(part=_drill(self.hole_dia / 2, depth), align=None, mode=mode)


class CounterBore(BasePartObject):
    """Clearance hole plus a flat pocket that swallows a socket cap head.

    `head_depth` defaults to the head height plus a layer, so the head lands
    flush or a hair below. The pocket ceiling is a small horizontal overhang
    that bridges fine at these diameters.
    """

    _applies_to = [BuildPart._tag]

    def __init__(
        self,
        screw: Screw,
        depth: float,
        *,
        head_depth: float | None = None,
        fit: str = "free",
        profile: PrinterProfile = DEFAULT,
        mode: Mode = Mode.SUBTRACT,
    ):
        head_depth = (
            head_depth if head_depth is not None else screw.head_h + profile.layer_height
        )
        self.screw = screw
        shank = _drill(profile.hole(screw.dia, fit) / 2, depth)
        head = _drill(profile.hole(screw.head_dia, "free") / 2, head_depth)
        super().__init__(part=shank.fuse(head).clean(), align=None, mode=mode)


class CounterSink(BasePartObject):
    """Clearance hole with a 90 degree cone for a flat-head screw.

    The cone is self-supporting when it opens upward, so a countersink on a TOP
    face prints without support. On a bottom face it is a 45 degree overhang
    ring and will need one.
    """

    _applies_to = [BuildPart._tag]

    def __init__(
        self,
        screw: Screw,
        depth: float,
        *,
        fit: str = "free",
        profile: PrinterProfile = DEFAULT,
        mode: Mode = Mode.SUBTRACT,
    ):
        self.screw = screw
        head_d = profile.hole(screw.cs_head_dia, fit)
        cone_h = head_d / 2  # 90 degrees included angle
        shank = _drill(profile.hole(screw.dia, fit) / 2, depth)
        cone = Solid.make_cone(head_d / 2, 0, cone_h, Plane(origin=(0, 0, 0), z_dir=(0, 0, -1)))
        super().__init__(part=shank.fuse(cone).clean(), align=None, mode=mode)


class InsertBoss(BasePartObject):
    """Blind hole for a brass heat-set insert.

    The hole is deliberately NOT compensated: the insert is melted in, so the
    printed hole wants to be at nominal and the brass makes its own room.

    Below the insert sits a relief pocket, which gives the displaced plastic and
    the screw tip somewhere to go. Without it the insert floats on a plug of
    molten PLA and sits proud.

    Leave at least one insert diameter of material all the way around the boss,
    or it splits when the insert goes in.
    """

    _applies_to = [BuildPart._tag]

    def __init__(
        self,
        screw: Screw,
        *,
        depth: float | None = None,
        relief: float = 0.6,
        profile: PrinterProfile = DEFAULT,
        mode: Mode = Mode.SUBTRACT,
    ):
        depth = depth if depth is not None else screw.insert_len + 0.5
        self.screw = screw
        self.boss_depth = depth
        bore = _drill(screw.insert_hole / 2, depth)
        relief_h = relief + screw.dia
        pocket = _drill((screw.dia + 0.6) / 2, relief_h, z_top=-depth)
        super().__init__(part=bore.fuse(pocket).clean(), align=None, mode=mode)


class NutPocket(BasePartObject):
    """Hex pocket that traps a nut so it cannot spin.

    Cuts DOWN from the location. `slot` extends the pocket along +Y so the nut
    slides in from the side after printing; leave it 0 for a pocket the nut drops
    into from above.

    Pair it with a `ClearanceHole` continuing through, or the screw has nothing
    to pass through.
    """

    _applies_to = [BuildPart._tag]

    def __init__(
        self,
        screw: Screw,
        *,
        depth: float | None = None,
        slot: float = 0.0,
        profile: PrinterProfile = DEFAULT,
        mode: Mode = Mode.SUBTRACT,
    ):
        depth = depth if depth is not None else screw.nut_h + 0.2
        af = screw.nut_af + profile.hole_compensation + profile.fit_snug
        self.screw = screw
        self.across_flats = af
        solid = _hex_prism(af, depth)
        if slot > 0:
            channel = Solid.make_box(
                af, slot, depth, Plane(origin=(-af / 2, 0, -depth))
            )
            solid = solid.fuse(channel).clean()
        super().__init__(part=solid, align=None, mode=mode)
