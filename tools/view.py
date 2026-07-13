"""Show the designs in the OCP CAD viewer — the real OCC geometry, not a picture of it.

    uv run python -m ocp_vscode --port 3939     # 1. start the viewer server
    #                                             2. OPEN http://127.0.0.1:3939/viewer
    uv run python -m tools.view box             # 3. then send a design to it

**Open the viewer before you send.** `show()` pushes over a websocket and the
server keeps nothing: anything sent while no viewer is attached is silently
dropped, and the page goes on showing its default model as if you had never run
anything. The `++` it prints means "handed to the server", not "somebody saw it".

    uv run python -m tools.view box       # parts box, lid lifted so you can see in
    uv run python -m tools.view motor     # NEMA 17 mount + the motor's envelope
    uv run python -m tools.view roller    # roller bracket, fully assembled
    uv run python -m tools.view coupon    # the tolerance coupon

Re-run any of these after editing a design and the viewer updates in place.
"""

from __future__ import annotations

import sys

from build123d import Location
from ocp_vscode import Camera, set_defaults, set_port, show

BLUE, ORANGE, GREEN, GREY = "#5b8fc9", "#e8913c", "#7fc47f", "#9a9a9a"


def parts_box():
    from examples.parts_box import build

    a = build()
    return dict(
        objs=[a.parts["box"].part, a.parts["lid"].part.moved(Location((0, 0, 26)))],
        names=["box", "lid (lifted 26mm so you can see in)"],
        colors=[BLUE, ORANGE],
        alphas=[1.0, 1.0],
    )


def motor_mount():
    from examples.motor_mount import build

    a = build()
    return dict(
        objs=[a.parts["mount"].part, a.parts["motor"].part],
        names=["mount (printed)", "NEMA 17 envelope: body + shaft + cable keepout"],
        colors=[ORANGE, BLUE],
        alphas=[1.0, 0.45],
    )


def roller_bracket():
    from examples.roller_bracket import build

    a = build()
    p = a.parts
    return dict(
        objs=[p["base"].part, p["bracket"].part, p["roller"].part, p["shaft"].part],
        names=["base", "bracket", "roller", "shaft (bought)"],
        colors=[BLUE, ORANGE, GREEN, GREY],
        alphas=[1.0, 1.0, 1.0, 1.0],
    )


def coupon():
    from hwkit.calibrate import coupon as make

    return dict(objs=[make().part], names=["tolerance coupon"], colors=[BLUE], alphas=[1.0])


SCENES = {
    "box": parts_box,
    "motor": motor_mount,
    "roller": roller_bracket,
    "coupon": coupon,
}


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "box"
    if which not in SCENES:
        raise SystemExit(f"pick one of: {', '.join(SCENES)}")

    set_port(3939)
    # reset_camera wants the enum, not the string it is named after. Passing
    # "reset" gets you AttributeError: 'str' object has no attribute 'value',
    # thrown from deep inside the tessellator where it means nothing.
    set_defaults(reset_camera=Camera.RESET, axes=True, axes0=True, black_edges=False)

    scene = SCENES[which]()
    show(
        *scene["objs"],
        names=scene["names"],
        colors=scene["colors"],
        alphas=scene["alphas"],
    )
    print(f"sent {which!r} -> http://127.0.0.1:3939/viewer")


if __name__ == "__main__":
    main()
