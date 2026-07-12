"""Idler roller on a bracket — the reference design for this toolkit.

A roller spins on two 623 bearings around a fixed 3mm shaft. The bracket that
carries the shaft bolts to a base plate with M3 screws into heat-set inserts.

It is deliberately small, but it exercises every joint this toolkit knows how to
make: a press fit (bearing into roller), a snug locating fit (shaft into
bracket), a screw joint (bracket to base), and a running clearance (roller to
bracket) that has to survive the tolerance stack or the roller binds.

    uv run python -m designs.roller_bracket          # validate
    uv run python -m designs.roller_bracket --export # write out/roller-bracket/

Section view for eyeballing the fits:

         bracket upright            roller             bracket upright
              |####|      ______________________       |####|
              |####|=====[__623__|      |__623__]======|####|
    shaft ----|-o--|-----[        bore          ]------|--o-|----
              |####|=====[_______|      |_______]======|####|
              |####|                                   |####|
         =====================  base  =========================
                     ^ M3 x 12 into heat-set insert
"""

from __future__ import annotations

import sys

from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    Cylinder,
    Location,
    Locations,
    Mode,
    Part,
    Plane,
    Rotation,
    RevoluteJoint,
    RigidJoint,
    chamfer,
    fillet,
)

from hwkit import (
    BEARINGS,
    M3,
    Assembly,
    BearingPocket,
    ClearanceHole,
    CounterBore,
    InsertBoss,
    ShaftBore,
    load_profile,
)

P = load_profile()
BEARING = BEARINGS["623"]  # 3 x 10 x 4

SHAFT_DIA = 3.0
SHAFT_LEN = 40.0
ROLLER_OD = 20.0
ROLLER_LEN = 20.0

GAP = 1.0  # running clearance, roller end face to bracket upright, each side
WALL = 5.0  # bracket upright thickness
SPAN = ROLLER_LEN + 2 * GAP  # clear width between the uprights
UPRIGHT_H = 26.0
SHAFT_Z = 18.0  # shaft axis height above the bracket flange
FLANGE_T = 5.0

GUSSET = 2.0  # fillet radius where the uprights meet the flange

# Both of these numbers were set by the checks, not by eye.
#
# The bolts have to clear the TOE of the gusset, not the upright wall — a
# counterbore that bites into the fillet leaves a 1mm2 overhanging lip you would
# never see in a render, and the overhang check found four of them. And the
# flange has to be wide enough to hold a whole head pocket, or it breaks out of
# the side and the wall check reads 0.04mm.
_UPRIGHT_OUTER = SPAN / 2 + WALL  # 16.0
_HEAD_R = 3.1
_GUSSET_TOE = _UPRIGHT_OUTER + GUSSET  # 18.0
BOLT_X = _GUSSET_TOE + 1.0 + _HEAD_R
BOLT_Y = 10.0
FLANGE = (2 * (BOLT_X + _HEAD_R + 2.0), 30.0, FLANGE_T)
BOLTS = tuple((sx * BOLT_X, sy * BOLT_Y) for sx in (-1, 1) for sy in (-1, 1))

BASE = (80.0, 50.0, 8.0)


def roller() -> Part:
    """A tube with a bearing pressed into each end.

    Prints standing on one end. The step from the bearing pocket down to the
    centre bore is an annular ceiling — a short bridge, which is why the pocket
    is only as deep as the bearing and no deeper.
    """
    with BuildPart() as p:
        Cylinder(ROLLER_OD / 2, ROLLER_LEN)
        for face in (p.faces().sort_by(Axis.Z)[-1], p.faces().sort_by(Axis.Z)[0]):
            with Locations(Plane(face)):
                BearingPocket(BEARING, fit="press", lip=0, depth=BEARING.width, profile=P)
        # Centre bore clears the shaft and the rotating inner races entirely.
        Cylinder(
            (SHAFT_DIA + 3.0) / 2, ROLLER_LEN, mode=Mode.SUBTRACT
        )
        chamfer(p.edges().filter_by(Axis.Z, reverse=True).group_by(Axis.Z)[0], 0.6)
        chamfer(p.edges().filter_by(Axis.Z, reverse=True).group_by(Axis.Z)[-1], 0.6)

    RevoluteJoint("spin", p.part, axis=Axis.Z)
    return p.part


def bracket() -> Part:
    """A U that holds the shaft and bolts down to the base."""
    fw, fd, ft = FLANGE
    with BuildPart() as p:
        Box(fw, fd, ft, align=(Align.CENTER, Align.CENTER, Align.MIN))

        for x in (-(SPAN + WALL) / 2, (SPAN + WALL) / 2):
            with Locations((x, 0, ft)):
                Box(WALL, fd, UPRIGHT_H, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Gusset where the uprights meet the flange. This is the joint that
        # snaps, because the layers there are loaded in peel.
        roots = [
            e
            for e in p.edges().filter_by(Axis.Y).group_by(Axis.Z)[1]
            if abs(e.center().X) <= _UPRIGHT_OUTER + 0.01
        ]
        fillet(roots, GUSSET)

        # Shaft bores, straight through both uprights, drilled along -X from a
        # plane sitting on the +X outer face.
        with Locations(Plane.YZ.offset(fw / 2)):
            with Locations((0, ft + SHAFT_Z)):
                ShaftBore(SHAFT_DIA, fw, fit="snug", profile=P)

        # Bolt-down holes in the exposed flange, heads sunk flush.
        with Locations(Plane.XY.offset(ft)):
            with Locations(*BOLTS):
                CounterBore(M3, depth=ft, profile=P)

    RigidJoint("foot", p.part, Location((0, 0, 0)))
    RigidJoint("shaft_axis", p.part, Location((0, 0, ft + SHAFT_Z), (0, 90, 0)))
    return p.part


def base() -> Part:
    """A plate with four heat-set inserts. The relief under each insert runs out
    of the bottom on purpose: molten plastic and a long screw both need an exit."""
    w, d, t = BASE
    with BuildPart() as p:
        Box(w, d, t, align=(Align.CENTER, Align.CENTER, Align.MAX))
        with Locations(Plane.XY):
            with Locations(*BOLTS):
                InsertBoss(M3, profile=P)
        chamfer(p.edges().filter_by(Axis.Z), 2.0)
        # Take the elephant foot off the bottom edge so the plate sits flat.
        chamfer(p.faces().sort_by(Axis.Z)[0].edges(), P.elephant_foot)

    RigidJoint("top", p.part, Location((0, 0, 0)))
    return p.part


def shaft() -> Part:
    """The bought 3mm rod, modelled only so the checks can see it."""
    p = Cylinder(SHAFT_DIA / 2, SHAFT_LEN, rotation=(0, 90, 0))
    RigidJoint("centre", p, Location((0, 0, 0), (0, 90, 0)))
    return p


def build() -> Assembly:
    asm = Assembly("roller-bracket", P)

    b = asm.add("base", base(), qty=1, support="none",
                note="Inserts go in from the top. Iron at 220C, straight down.")
    br = asm.add("bracket", bracket(), qty=1, support="none",
                 note="Prints as modelled. The 3mm shaft bores bridge at the apex.")
    ro = asm.add("roller", roller(), qty=1, support="none",
                 print_orientation=Rotation(0, 0, 0),
                 note="Stands on one end. Do not scale to fit — the bearing seat is the point.")
    sh = asm.bought("shaft", shaft())

    # Place everything. The bracket sits on the base, the shaft runs through the
    # bracket, and the roller spins about that shaft.
    asm.mate(b.joints["top"], br.joints["foot"])
    asm.mate(br.joints["shaft_axis"], sh.joints["centre"])
    asm.mate(br.joints["shaft_axis"], ro.joints["spin"], angle=0)

    # The whole reason the design has a GAP.
    asm.must_move("roller", "bracket", GAP * 0.5)

    asm.buy("623 bearing (3 x 10 x 4)", 2, "press fit into the roller")
    asm.buy(f"3mm ground steel rod, {SHAFT_LEN:.0f}mm", 1, "cut from stock, deburr the ends")
    asm.buy("M3 heat-set insert (M3 x 5.7)", 4, "into the base")
    asm.buy("M3 x 12 socket cap screw", 4, "bracket down to base")

    asm.step("Press a 623 into each end of the **roller**. Push on the OUTER race only — "
             "a socket or the flat of a vice, never the inner race. It should need real "
             "force; if it drops in, your `fit_press` is too loose.")
    asm.step("Heat-set the four M3 inserts into the **base** from the top. Let them cool "
             "before you touch them, or they lift back out.")
    asm.step("Slide the 3mm shaft through one **bracket** upright, through the roller, and "
             "out the far upright. The shaft is snug in the bracket and free in the bearings.")
    asm.step("Sit the bracket on the base and drive the four M3 x 12 screws down into the "
             "inserts. Snug, not gorilla — the heads are pulling against printed plastic.")
    asm.step("Spin the roller. It should coast. If it drags, the uprights are pinching the "
             "bearing outer races: check the shaft length and that the roller is centred.")
    return asm


def main() -> None:
    asm = build()
    reports = asm.validate()
    for r in reports:
        print(r)
        print()

    failed = [r for r in reports if not r.ok]
    if "--export" in sys.argv:
        if failed:
            print("refusing to export: fix the errors above")
            raise SystemExit(1)
        out = asm.export()
        print(f"exported to {out}/")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
