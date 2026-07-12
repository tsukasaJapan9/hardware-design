"""Bought components: servos, sensors, boards, batteries, motors.

**You cannot design the bracket before you have modelled the thing it holds.**
A mount is a negative of a component, and a negative of a guess is scrap.

So a component is not a footprint. A hole pattern tells you where the screws go
and nothing about why the part will not fit, because the part does not usually
collide on its screws. It collides on the connector nobody left room to plug in,
on the servo cable exiting the case where the wall is, on the horn sweeping
through a bracket arm, on the battery that swelled 1mm. Those are `keepout`
volumes, and they are checked exactly like solid material is.

Three things every component carries:

  solids    what it physically occupies
  keepouts  what must stay empty even though nothing is there yet
  source    where the numbers came from, and whether anyone has verified them

## The datum

**z = 0 is the mounting plane** — the surface of the component that touches the
bracket. The origin sits at the centre of the mounting hole pattern in that
plane, so mount holes are 2D (x, y) at z = 0.

**+Z is the side the component is on.** Its body, its connectors, its horn.

**−Z is through the bracket.** Anything a component puts at negative Z — a motor's
pilot boss, its output shaft, a servo case that hangs through a cutout, the
solder tails under a PCB — is telling you the bracket needs a hole there. That is
not a modelling accident, it is the most useful thing the model says.

Do not assume the body is always +Z. A NEMA 17 mounts on its face and hangs its
shaft *through* the plate; an SG90 rests on its tabs and hangs its *case* through
the plate. Both are correct, and both are only expressible because the sign means
something.

## When the data does not exist

Ask. `require()` raises with the list of measurements needed. Do not estimate a
servo from a photograph; a bracket that is 1mm out is a bracket you print twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from build123d import (
    Align,
    Box,
    BuildPart,
    Cylinder,
    Location,
    Locations,
    Mode,
    Part,
    Plane,
    RigidJoint,
    Rotation,
    Solid,
)
from build123d.objects_part import BasePartObject

from .fasteners import SCREWS, ClearanceHole, InsertBoss, Screw
from .profile import DEFAULT, PrinterProfile


class MissingComponentData(Exception):
    """Raised when a design needs a component nobody has measured yet.

    This is not a bug to work around. It is the design telling you it does not
    have enough information to be correct, which is the only honest thing it can
    say. Take the message to the user and ask.
    """


CHECKLIST = {
    "servo": [
        "body length x width x height (the case, not the tabs)",
        "mounting tab thickness, and how far the tabs sit below the top of the case",
        "hole spacing between tab hole centres, both axes, and the hole diameter",
        "output shaft centre: how far from the hole pattern centre, along which axis",
        "how far the horn sticks out past the case, and its swept diameter",
        "which face the cable leaves from, and how much room the bend needs",
    ],
    "board": [
        "board length x width, and thickness",
        "mounting hole diameter and the (x, y) of each hole from a named corner",
        "the tallest component on the top face, and on the bottom face",
        "every connector: which edge, how far along, and how much room to plug in",
        "anything that must stay clear for airflow or an antenna",
    ],
    "battery": [
        "cell or pack length x width x height, at its FATTEST (packs swell; add 1mm)",
        "which face the wires leave from, and their bend radius",
        "for cylindrical cells: diameter, length, and whether it is a protected cell",
        "for a holder or BMS: its own footprint and mounting holes",
    ],
    "sensor": [
        "board or body length x width x height",
        "mounting hole diameter and positions",
        "the sensing element: where it is, which way it faces, and what it needs to see",
        "connector position and insertion clearance",
    ],
    "motor": [
        "body diameter or square, and length",
        "mounting hole pattern and thread size",
        "pilot boss diameter and how far it protrudes",
        "shaft diameter, length, and any flat or keyway",
    ],
}


def require(name: str, kind: str = "board") -> None:
    """Refuse to design against a component nobody has measured.

    Call this the moment a design reaches for a component that is not in the
    library. Relay the message to the user verbatim and ask for the numbers.
    """
    wanted = CHECKLIST.get(kind, CHECKLIST["board"])
    lines = "\n".join(f"  - {w}" for w in wanted)
    raise MissingComponentData(
        f"No verified model for {name!r}.\n\n"
        f"A mount is a negative of the component, so this design cannot be correct "
        f"until the component is. Ask the user for the datasheet, or for these "
        f"measurements taken with calipers:\n\n{lines}\n\n"
        f"Then add a Component to hwkit/components.py and set "
        f"source= where the numbers came from."
    )


@dataclass(frozen=True)
class Mount:
    """One mounting hole, in the component's mounting plane (z = 0)."""

    x: float
    y: float
    dia: float  # the hole in the COMPONENT, not the hole you will print
    screw: str = "M3"  # what goes through it


@dataclass(frozen=True)
class Vol:
    """A box or a cylinder, placed in component coordinates.

    role="body"    the component physically occupies this. Interference here is
                   a part that does not fit.
    role="keepout" nothing may occupy this either, even though the component
                   does not. Interference here is a cable you cannot route, a
                   connector you cannot plug in, or a horn that will not turn.
    """

    kind: str  # "box" | "cyl"
    size: tuple[float, ...]  # box: (dx, dy, dz) | cyl: (dia, h)
    at: tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis: str = "z"  # cylinder axis: "x" | "y" | "z"
    role: str = "body"
    why: str = ""

    def solid(self) -> Part:
        if self.kind == "box":
            dx, dy, dz = self.size
            s = Box(dx, dy, dz, align=(Align.CENTER, Align.CENTER, Align.MIN))
        elif self.kind == "cyl":
            dia, h = self.size
            s = Cylinder(dia / 2, h, align=(Align.CENTER, Align.CENTER, Align.MIN))
        else:
            raise ValueError(f"unknown Vol kind {self.kind!r}")
        spin = {"z": (0, 0, 0), "x": (0, 90, 0), "y": (-90, 0, 0)}[self.axis]
        return s.moved(Location(self.at, spin))


@dataclass(frozen=True)
class Component:
    """A thing you buy. Modelled before the bracket that holds it exists."""

    name: str
    kind: str  # servo | board | battery | sensor | motor
    vols: tuple[Vol, ...]
    mounts: tuple[Mount, ...] = ()
    source: str = ""  # datasheet name/URL, or "measured, calipers, <date>"
    verified: bool = False  # has a human confirmed these against the real part?
    mass_g: float | None = None
    notes: str = ""

    # ---- geometry --------------------------------------------------------

    def body(self) -> Part:
        """What the component physically is."""
        return self._fuse("body")

    def keepout(self) -> Part | None:
        """What must stay empty around it. None if nothing was declared."""
        return self._fuse("keepout")

    def envelope(self) -> Part:
        """Body plus keepouts: what a bracket must not intrude on.

        This is what you hand to `Assembly.bought()`, because the interference
        check can only see what has been modelled, and the thing that actually
        stops an assembly is usually the connector, not the case.
        """
        body, keep = self.body(), self.keepout()
        env = body if keep is None else body + keep
        for i, m in enumerate(self.mounts):
            RigidJoint(f"mount_{i}", env, Location((m.x, m.y, 0)))
        RigidJoint("origin", env, Location((0, 0, 0)))
        return env

    def _fuse(self, role: str) -> Part | None:
        parts = [v.solid() for v in self.vols if v.role == role]
        if not parts:
            return None
        out = parts[0]
        for p in parts[1:]:
            out = out + p
        return out

    # ---- what the bracket needs ------------------------------------------

    def screw(self) -> Screw:
        names = {m.screw for m in self.mounts}
        if len(names) != 1:
            raise ValueError(f"{self.name} mixes screw sizes {names}; cut them by hand")
        return SCREWS[names.pop()]

    def keepout_reasons(self) -> list[str]:
        return [f"{v.why}" for v in self.vols if v.role == "keepout" and v.why]

    def check(self) -> None:
        if not self.verified:
            raise MissingComponentData(
                f"{self.name!r} is in the library but NOT verified: {self.notes or 'no note'}\n"
                f"source: {self.source or 'unknown'}\n\n"
                f"These numbers are nominal. Ask the user to confirm them against the "
                f"part in their hand before anything gets printed. If they confirm, set "
                f"verified=True with how they checked. If they cannot, get the "
                f"measurements in components.CHECKLIST[{self.kind!r}]."
            )


class MountHoles(BasePartObject):
    """Cut a component's mounting pattern into the plate under it.

    Placed at the component's origin, on the face it bolts to. `kind` picks how
    the plate holds the screw:

        through  a clearance hole; the nut or a captive nut lives on the far side
        insert   a heat-set insert boss; the screw comes from the component side
    """

    _applies_to = [BuildPart._tag]

    def __init__(
        self,
        component: Component,
        *,
        kind: str = "insert",
        depth: float = 10.0,
        profile: PrinterProfile = DEFAULT,
        mode: Mode = Mode.SUBTRACT,
    ):
        component.check()
        if kind not in ("insert", "through"):
            raise ValueError(f"kind must be insert|through, not {kind!r}")
        if not component.mounts:
            raise ValueError(f"{component.name} has no mounting holes to cut")

        screw = component.screw()
        # Build the cutters positively in a scratch context, then hand the fused
        # solid up to BasePartObject, which applies OUR mode at the active
        # Locations. Calling the pockets with their default SUBTRACT here would
        # try to subtract from an empty builder.
        with BuildPart(mode=Mode.PRIVATE) as cutters:
            with Locations(*[(m.x, m.y, 0) for m in component.mounts]):
                if kind == "insert":
                    InsertBoss(screw, profile=profile, mode=Mode.ADD)
                else:
                    ClearanceHole(screw, depth, profile=profile, mode=Mode.ADD)

        self.component = component
        super().__init__(part=cutters.part, align=None, mode=mode)


# ---------------------------------------------------------------------------
# The library.
#
# `verified=True` means the pattern is a published standard and I am confident
# in it. Everything else is nominal: a starting point that the code will not let
# you print without a human confirming it, because hobby parts vary between
# batches and a bracket that is 1mm out is a bracket you print twice.
# ---------------------------------------------------------------------------

NEMA17 = Component(
    name="NEMA 17 stepper",
    kind="motor",
    source="NEMA ICS 16-2001 frame standard",
    verified=True,
    vols=(
        # The motor sits on the plate (+Z) and puts its boss and shaft THROUGH it.
        Vol("box", (42.3, 42.3, 48.0), at=(0, 0, 0), why="body, 48mm variant"),
        Vol("cyl", (22.0, 2.0), at=(0, 0, -2.0), why="pilot boss — bore the plate for it"),
        Vol("cyl", (5.0, 24.0), at=(0, 0, -24.0), why="output shaft, through the plate"),
        Vol(
            "box", (20.0, 20.0, 15.0), at=(0, 0, 48.0), role="keepout",
            why="cable leaves the back of the motor and needs a bend radius",
        ),
    ),
    mounts=tuple(
        Mount(x, y, 3.0, "M3") for x in (-15.5, 15.5) for y in (-15.5, 15.5)
    ),
    mass_g=350,
    notes="31mm square bolt pattern. Body length varies by model (34/40/48mm) — "
    "this is the 48mm; shorten the body Vol if yours is shorter. The 22mm boss is "
    "what centres the motor, not the bolts: bore the plate for it. Whatever you put "
    "on the 24mm shaft (pulley, coupler) needs its own room past the plate — that "
    "is your transmission's keepout to declare, not the motor's.",
)

RPI5 = Component(
    name="Raspberry Pi 4B / 5",
    kind="board",
    source="Raspberry Pi mechanical drawing (85 x 56, 58 x 49 pattern)",
    verified=True,
    vols=(
        Vol("box", (85.0, 56.0, 1.6), at=(0, 0, 0), why="the PCB itself"),
        Vol("box", (85.0, 56.0, 16.0), at=(0, 0, 1.6), why="components on the top face"),
        Vol(
            "box", (85.0, 56.0, 3.0), at=(0, 0, -3.0), role="keepout",
            why="solder tails on the underside; standoffs must be at least 3mm",
        ),
        Vol(
            "box", (30.0, 30.0, 16.0), at=(56.0, 0, 1.6), role="keepout",
            why="USB and ethernet: room to insert the plugs",
        ),
        Vol(
            "box", (20.0, 20.0, 12.0), at=(0, -38.0, 1.6), role="keepout",
            why="USB-C power and HDMI on the near edge",
        ),
    ),
    mounts=tuple(
        Mount(x, y, 2.7, "M2.5") for x in (-29.0, 29.0) for y in (-24.5, 24.5)
    ),
    mass_g=46,
    notes="Holes are 3.5mm in from the board edges. The origin is the centre of "
    "the hole pattern, which is also the centre of the board.",
)

# --- nominal, NOT verified: the code will stop before these reach a printer ---

SG90 = Component(
    name="SG90 micro servo",
    kind="servo",
    source="nominal hobby-servo dimensions; NOT taken from a datasheet",
    verified=False,
    vols=(
        # Rests on its tabs, hangs its case THROUGH the bracket. The bracket
        # needs a 23 x 13 cutout, and the negative-Z case is what says so.
        Vol("box", (32.2, 12.2, 2.5), at=(0, 0, 0), why="mounting tabs, resting on the bracket"),
        Vol("box", (22.8, 12.2, 22.7), at=(0, 0, -16.0), why="case, hanging through the bracket"),
        Vol("cyl", (11.8, 4.0), at=(-5.9, 0, 6.7), why="output boss"),
        Vol(
            "cyl", (34.0, 8.0), at=(-5.9, 0, 10.7), role="keepout",
            why="the horn sweeps this circle — a bracket in it is a stalled servo",
        ),
        Vol(
            "box", (10.0, 12.0, 10.0), at=(16.0, 0, -16.0), role="keepout",
            why="cable leaves the end of the case and needs a bend radius",
        ),
    ),
    mounts=(
        Mount(-14.0, 0.0, 2.2, "M2"),
        Mount(14.0, 0.0, 2.2, "M2"),
    ),
    mass_g=9,
    notes="SG90 clones vary between batches — the tab hole spacing, the case height "
    "above and below the tabs, and how far the output shaft sits off centre all move. "
    "MEASURE THE ONE IN YOUR HAND before this cuts a bracket.",
)

CELL_18650 = Component(
    name="18650 cell",
    kind="battery",
    source="nominal cell size; protected cells are longer",
    verified=False,
    vols=(
        Vol("cyl", (18.6, 65.2), at=(0, 0, 0), axis="x", why="the cell, at its fattest"),
        Vol(
            "cyl", (20.6, 69.0), at=(0, 0, 0), axis="x", role="keepout",
            why="1mm all round: cells swell, and a trapped cell is a fire",
        ),
    ),
    mounts=(),
    mass_g=47,
    notes="Bare cells are 18.4 x 65. PROTECTED cells carry a PCB on the end and "
    "run 69-70mm. Button-top adds another 1mm. Measure yours, and never design a "
    "pocket a swollen cell cannot leave.",
)

COMPONENTS = {c.name: c for c in (NEMA17, RPI5, SG90, CELL_18650)}


TEMPLATE = '''
MY_PART = Component(
    name="...",
    kind="servo",              # servo | board | battery | sensor | motor
    source="measured with calipers, <date>",   # or the datasheet
    verified=True,             # only once a human has checked the real part
    vols=(
        Vol("box", (L, W, H), at=(0, 0, 0), why="body"),
        Vol("box", (L, W, H), at=(0, 0, 0), role="keepout",
            why="connector needs room to plug in"),
    ),
    mounts=(Mount(x, y, hole_dia, "M3"), ...),
    notes="",
)
'''
