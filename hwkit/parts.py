"""Off-the-shelf parts: bearings, shafts, and module footprints.

The bearing and shaft tables are industry-standard sizes and safe to trust.
The footprints are the ones worth hard-coding; for anything else you buy, put a
caliper on it before you commit to a print. A footprint that is 0.5mm off is a
part that does not fit, and a spool you have already spent.
"""

from __future__ import annotations

from dataclasses import dataclass

from build123d import BuildPart, Mode, Plane, Solid
from build123d.objects_part import BasePartObject

from .profile import DEFAULT, PrinterProfile


@dataclass(frozen=True)
class Bearing:
    name: str
    bore: float  # inner diameter (takes the shaft)
    od: float  # outer diameter (goes in the pocket)
    width: float


# Deep-groove ball bearings, in the sizes hobby hardware actually ships in.
BEARINGS = {
    b.name: b
    for b in (
        Bearing("623", 3.0, 10.0, 4.0),
        Bearing("624", 4.0, 13.0, 5.0),
        Bearing("625", 5.0, 16.0, 5.0),
        Bearing("626", 6.0, 19.0, 6.0),
        Bearing("608", 8.0, 22.0, 7.0),  # the skateboard bearing
        Bearing("688", 8.0, 16.0, 5.0),
        Bearing("6800", 10.0, 19.0, 5.0),
        Bearing("6801", 12.0, 21.0, 5.0),
        Bearing("MR105", 5.0, 10.0, 4.0),
        Bearing("MR115", 5.0, 11.0, 4.0),
    )
}

# Ground steel rod, the common linear-motion diameters (mm).
SHAFTS = (3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0)


@dataclass(frozen=True)
class Footprint:
    """A mounting pattern for a bought module. Hole centres are module-local,
    origin at the module centre."""

    name: str
    size: tuple[float, float]
    holes: tuple[tuple[float, float], ...]
    hole_dia: float
    note: str = ""


NEMA17 = Footprint(
    name="NEMA 17 stepper",
    size=(42.3, 42.3),
    holes=((-15.5, -15.5), (15.5, -15.5), (-15.5, 15.5), (15.5, 15.5)),
    hole_dia=3.0,  # M3
    note="31mm square pattern. 22mm pilot boss, 2mm proud. 5mm output shaft. "
    "Body length varies by model (34 / 40 / 48mm) — check yours.",
)

RPI4 = Footprint(
    name="Raspberry Pi 4B / 5",
    size=(85.0, 56.0),
    holes=((-29.0, -24.5), (29.0, -24.5), (-29.0, 24.5), (29.0, 24.5)),
    hole_dia=2.75,  # M2.5
    note="58 x 49mm pattern, 3.5mm in from the board edges.",
)

FOOTPRINTS = {f.name: f for f in (NEMA17, RPI4)}


def _drill(radius: float, depth: float, z_top: float = 0.0) -> Solid:
    return Solid.make_cylinder(
        radius, depth, Plane(origin=(0, 0, z_top), z_dir=(0, 0, -1))
    )


class BearingPocket(BasePartObject):
    """Pocket for a bearing's outer race, cut DOWN from the location.

    `lip` is the shoulder left under the bearing for it to seat against. The
    bore through that lip clears the INNER race, so the lip can only ever touch
    the outer race — load a bearing through its inner race and you have
    destroyed it.

    A press fit is the one dimension you should not take on trust. Print the
    calibration coupon and set `fit_press` from what you measure.
    """

    _applies_to = [BuildPart._tag]

    def __init__(
        self,
        bearing: Bearing,
        *,
        fit: str = "press",
        lip: float = 1.0,
        depth: float | None = None,
        profile: PrinterProfile = DEFAULT,
        mode: Mode = Mode.SUBTRACT,
    ):
        depth = depth if depth is not None else bearing.width
        self.bearing = bearing
        self.pocket_dia = profile.bore(bearing.od, fit)
        # Clear the inner race and shaft; leave the outer race fully supported.
        inner_clear = bearing.bore + (bearing.od - bearing.bore) * 0.35

        solid = _drill(self.pocket_dia / 2, depth)
        if lip > 0:
            solid = solid.fuse(
                _drill(inner_clear / 2, lip + 1, z_top=-depth)
            ).clean()
        super().__init__(part=solid, align=None, mode=mode)


class ShaftBore(BasePartObject):
    """Plain bore for a rod, cut DOWN from the location."""

    _applies_to = [BuildPart._tag]

    def __init__(
        self,
        dia: float,
        depth: float,
        *,
        fit: str = "slide",
        profile: PrinterProfile = DEFAULT,
        mode: Mode = Mode.SUBTRACT,
    ):
        self.bore_dia = profile.hole(dia, fit)
        super().__init__(part=_drill(self.bore_dia / 2, depth), align=None, mode=mode)
