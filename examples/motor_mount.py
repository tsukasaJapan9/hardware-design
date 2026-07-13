"""NEMA 17 motor mount — the reference for designing around a bought component.

The point of this design is the order it is done in. The motor is modelled first,
with its pilot boss, its shaft, the circle a coupler sweeps, and the room its
cable needs to leave the back. Only then does a bracket get cut around it, and
the interference check is what proves the bracket did not land on any of it.

Try deleting the cable keepout from NEMA17 and re-running: the design still
passes, and the motor still does not fit, because you cannot check what you did
not model.

    uv run python -m examples.motor_mount
    uv run python -m examples.motor_mount --export
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
    Rotation,
    chamfer,
    fillet,
)

from hwkit import (
    M4,
    NEMA17,
    Assembly,
    CounterBore,
    MountHoles,
    load_profile,
)

P = load_profile()
MOTOR = NEMA17

PLATE_T = 6.0  # the face the motor bolts to
PLATE = (56.0, 56.0)
WEB_T = 6.0  # the upright that carries the plate
FOOT = (56.0, 40.0, 6.0)
HEIGHT = 62.0  # from the foot to the motor axis: clears the 48mm body


def mount() -> Part:
    """An L: a vertical face the motor hangs off, a foot that bolts down.

    The motor bolts through the plate from the front, into heat-set inserts, so
    you can pull the motor without taking the mount apart.
    """
    pw, ph = PLATE
    fw, fd, ft = FOOT

    with BuildPart() as p:
        # Foot, lying on the bed.
        Box(fw, fd, ft, align=(Align.CENTER, Align.MIN, Align.MIN))

        # Vertical plate. Printed flat on its back would be stronger, but then
        # the foot is an overhang; this way the layers run up the plate and the
        # load on the motor bolts is in shear across them, not in peel.
        with Locations((0, 0, 0)):
            Box(pw, WEB_T, HEIGHT + ph / 2,
                align=(Align.CENTER, Align.MIN, Align.MIN))

        # The gusset that stops the plate folding back under the motor's weight.
        fillet(
            [e for e in p.edges().filter_by(Axis.X).group_by(Axis.Z)[1]
             if abs(e.center().Y - WEB_T) < 0.01],
            8.0,
        )

        # The motor's bolt pattern and its pilot bore, cut into the plate from
        # the FRONT face (-Y), which is the face the motor sits against.
        motor_face = Plane(
            origin=(0, 0, HEIGHT), x_dir=(1, 0, 0), z_dir=(0, -1, 0)
        )
        with Locations(motor_face):
            MountHoles(MOTOR, kind="insert", profile=P)
            # Clear the pilot boss and the shaft. The boss is what actually
            # locates the motor; the bolts only hold it there.
            Cylinder(P.hole(22.0, "snug") / 2, WEB_T * 3, mode=Mode.SUBTRACT)

        # Bolt the foot down.
        with Locations(Plane.XY.offset(ft)):
            with Locations((-20.0, 28.0), (20.0, 28.0)):
                CounterBore(M4, depth=ft, profile=P)

        chamfer(p.faces().sort_by(Axis.Z)[0].edges(), P.elephant_foot)

    RigidJoint("foot", p.part, Location((0, 0, 0)))
    # Where the motor goes. The component's +Z is the side the motor is ON, so
    # it has to point OUT of the plate (-Y) into free space. Rotating +90 about
    # X sends +Z to -Y; -90 would bury the motor in the plate, and the
    # interference check would say so in about a second.
    RigidJoint("motor_face", p.part, Location((0, 0, HEIGHT), (90, 0, 0)))
    return p.part


def build() -> Assembly:
    asm = Assembly("motor-mount", P)

    m = asm.add(
        "mount", mount(), qty=1, support="none",
        note="Prints standing on the foot. No support: the gusset is the overhang, "
             "and at 8mm radius it is under 50 degrees the whole way round.",
    )
    # The motor, with its keepouts. If this component were unverified the design
    # would stop right here rather than cut a bracket around a guess.
    motor = asm.bought("motor", MOTOR)

    asm.mate(m.joints["motor_face"], motor.joints["origin"])

    asm.buy("NEMA 17 stepper, 48mm body", 1, "5mm shaft, 31mm bolt pattern")
    asm.buy("M3 heat-set insert (M3 x 5.7)", 4, "into the mount plate, from the front")
    asm.buy("M3 x 8 socket cap screw", 4, "motor to mount")
    asm.buy("M4 x 12 socket cap screw", 2, "foot down to whatever it sits on")

    asm.step("Heat-set four M3 inserts into the FRONT face of the mount plate — the "
             "flat face the motor will sit against. Straight in, and let them cool.")
    asm.step("Drop the motor's 22mm pilot boss into the plate's bore. That boss is "
             "what centres the motor; if it does not drop in, do not force the bolts "
             "in to pull it — open the bore out.")
    asm.step("Four M3 x 8 through the motor flange into the inserts. Cross-tighten.")
    asm.step("Check the cable has somewhere to go before you bolt the foot down. "
             "The mount was cut to leave 20 x 20 x 15mm behind the motor for it.")
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
        print(f"exported to {asm.export()}/")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
