"""A small parts box — the first thing to design with this toolkit.

Nothing is bought except four screws and four inserts, so there is no component
to measure and nothing to block on. What it does exercise is the thing every
printed assembly lives or dies on: **does the lid actually go in?**

The lid drops inside the walls and lands on four corner posts, flush with the
rim. The only dimension that decides whether that works is the gap between the
lid's edge and the inner wall, and that gap is `P.gap("slide")` — 0.20mm a side
on an uncalibrated profile. Two tenths of a millimetre, times four walls, is the
whole design.

    uv run python -m examples.parts_box
    uv run python -m examples.parts_box --export

Section, looking along X:

     |<-------------- 70 outer ------------->|
     |###|                               |###|   <- wall 2.5
     |###|===============================|###|   <- lid, 5 thick, flush with the rim
     |###| ^                           ^ |###|
     |###| |  post r6              post | |###|   <- lid lands on these; M3 into inserts
     |###| |                            | |###|
     |###|____________________________ __|###|
     |#######################################|   <- floor 2.5
      ^ 0.20mm each side. This is the design.
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
    RigidJoint,
    chamfer,
    fillet,
    offset,
)

from hwkit import M3, Assembly, CounterBore, InsertBoss, load_profile

P = load_profile()

OUTER = (70.0, 50.0, 30.0)
WALL = 2.5
FLOOR = 2.5
LID_T = 5.0
POST_R = 9.0

INNER = (OUTER[0] - 2 * WALL, OUTER[1] - 2 * WALL)  # 65 x 45
POST_TOP = OUTER[2] - LID_T  # 25.0 — the lid sits on this and ends flush

# Corner posts. Sizing one is a squeeze between three constraints, and getting it
# wrong is invisible in a render:
#
#   it must COVER the inner corner. A post that stops short leaves a narrow
#   crevice down the corner — slivers OCC will not even fillet, and a stress
#   raiser exactly where the box gets dropped.
#
#   it must not BULGE out of the outer wall. So it is cut back by intersecting
#   the whole part with the outer envelope, which lets the post be generously
#   oversized without a tangency anywhere.
#
#   the screw in it must stay clear of the LID's edge. Post centre, plus the
#   counterbore head, plus a minimum wall, has to fit inside the lid.
POST_INSET = 5.0  # post centre, in from the inner faces
POSTS = tuple(
    (sx * (INNER[0] / 2 - POST_INSET), sy * (INNER[1] / 2 - POST_INSET))
    for sx in (-1, 1)
    for sy in (-1, 1)
)
_CORNER_REACH = POST_INSET * 2**0.5  # centre to the inner corner, along the diagonal
assert POST_R > _CORNER_REACH + 0.5, (
    f"post r={POST_R} does not reach the corner at {_CORNER_REACH:.2f}mm; "
    "it will leave a crevice"
)

# The whole design, in one number. The lid is the inner cavity, less one
# slide-fit gap on each side. Do not write 0.2 here — write where 0.2 comes from,
# so that recalibrating the printer moves the lid.
GAP = P.gap("slide")
LID = (INNER[0] - 2 * GAP, INNER[1] - 2 * GAP)

# The lid has to be thick enough to swallow an M3 cap head AND still have a floor
# under it. Head is 3.0mm, plus a layer of margin = 3.2mm of counterbore, leaving
# LID_T - 3.2 = 1.8mm — just over the 1.2mm minimum wall. A 3mm lid, which is
# what you would reach for, has the screw head coming out the bottom.
_LID_FLOOR = LID_T - (M3.head_h + P.layer_height)
assert _LID_FLOOR >= P.min_wall, f"lid floor {_LID_FLOOR:.1f}mm is under the minimum wall"

# And the screw head must not eat its way out through the edge of the lid.
_HEAD_R = P.hole(M3.head_dia, "free") / 2
_LID_WEB = LID[0] / 2 - (POSTS[-1][0] + _HEAD_R)
assert _LID_WEB >= P.min_wall, (
    f"only {_LID_WEB:.2f}mm of lid left outside the counterbore; move the posts in"
)


def box() -> Part:
    """Walls, floor, and four posts to screw the lid down to.

    Prints open-side-up exactly as modelled: every overhang in it is a blind hole
    drilled downward, whose floor faces up. No support anywhere.
    """
    w, d, h = OUTER
    with BuildPart() as p:
        Box(w, d, h, align=(Align.CENTER, Align.CENTER, Align.MIN))
        offset(amount=-WALL, openings=p.faces().sort_by(Axis.Z)[-1])

        with Locations(*[(x, y, FLOOR) for x, y in POSTS]):
            Cylinder(
                POST_R,
                POST_TOP - FLOOR,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )
        # The posts are deliberately too big — big enough to swallow the corner
        # with room to spare — and then trimmed back to the outer envelope. Sizing
        # them to land exactly on the wall instead would put a tangent surface
        # there, and a tangency is a zero-thickness face that OCC chokes on.
        Box(w, d, h, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.INTERSECT)

        # Where the posts and walls meet the floor is where a dropped box breaks:
        # those layers are loaded in peel.
        fillet([e for e in p.edges() if abs(e.center().Z - FLOOR) < 1e-6], 2.0)

        with Locations(Plane.XY.offset(POST_TOP)):
            with Locations(*POSTS):
                InsertBoss(M3, profile=P)

        chamfer(p.faces().sort_by(Axis.Z)[0].edges(), P.elephant_foot)

    RigidJoint("seat", p.part, Location((0, 0, POST_TOP)))
    return p.part


def lid() -> Part:
    """A plate that drops between the walls and lands on the posts.

    Prints as modelled, counterbores facing up, so the head pockets are open
    craters rather than ceilings. Flip it and you print four bridges for no
    reason.
    """
    with BuildPart() as p:
        Box(LID[0], LID[1], LID_T, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations(Plane.XY.offset(LID_T)):
            with Locations(*POSTS):
                CounterBore(M3, depth=LID_T, profile=P)
        chamfer(p.edges().filter_by(Axis.Z), 1.0)

    RigidJoint("underside", p.part, Location((0, 0, 0)))
    return p.part


def build() -> Assembly:
    asm = Assembly("parts-box", P)

    b = asm.add(
        "box", box(), qty=1, support="none",
        note="Open side up, as exported. Nothing in it overhangs.",
    )
    l = asm.add(
        "lid", lid(), qty=1, support="none",
        note="Counterbores up, as exported. 5mm thick so the M3 head sinks flush "
             "and still leaves 1.8mm of floor.",
    )

    asm.mate(b.joints["seat"], l.joints["underside"])

    # The whole design, stated as a requirement rather than hoped for. The lid is
    # lowered straight down, so it comes out straight up; it needs GAP of side room
    # the whole way. Interference alone would happily pass a lid cut to exactly
    # 65.00mm — zero overlap, and it will never go in.
    asm.goes_in("lid", "box", direction=(0, 0, 1), distance=15.0, clearance=GAP)

    asm.buy("M3 heat-set insert (M3 x 5.7)", 4, "into the corner posts")
    asm.buy("M3 x 10 socket cap screw", 4, "lid down to the posts")

    asm.step("Heat-set four M3 inserts into the tops of the corner posts. Straight "
             "down, and let them cool before you touch them — a lifted insert takes "
             "the post with it.")
    asm.step(f"Drop the lid in. It should fall in under its own weight with about "
             f"{GAP:.2f}mm a side. If you have to push it, stop: the profile is not "
             f"calibrated and the lid is oversized, not the box undersized.")
    asm.step("Four M3 x 10 through the lid into the inserts. Snug only — the head is "
             "pulling against 1.8mm of printed plastic.")
    return asm


def main() -> None:
    asm = build()
    reports = asm.validate()
    for r in reports:
        print(r)
        print()

    print(f"designed side gap: {GAP:.3f}mm  (lid {LID[0]:.2f} x {LID[1]:.2f} "
          f"in a {INNER[0]:.1f} x {INNER[1]:.1f} cavity)")

    failed = [r for r in reports if not r.ok]
    if "--export" in sys.argv:
        if failed:
            print("refusing to export: fix the errors above")
            raise SystemExit(1)
        print(f"exported to {asm.export()}/")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
