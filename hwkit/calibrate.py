"""The tolerance coupon: one small print that tells you what your machine does.

Every clearance in this toolkit is a guess until you print this. It is a 60 x 40
plate carrying:

  - holes in a range of nominal diameters, to measure how much your printer
    shrinks a hole  -> hole_compensation
  - pegs in the same range, to measure how much it grows a peg -> peg_compensation
  - pin/socket pairs at a spread of clearances, so you can feel which one is a
    press fit and which one is a slide fit -> fit_press / fit_snug / fit_slide

Print it in the material you will build in, with the settings you will build
with, and measure it with calipers. Twenty minutes here buys back every failed
fit later.

    uv run python -m hwkit.calibrate            # writes out/calibration.stl
"""

from __future__ import annotations

from pathlib import Path

from build123d import (
    Align,
    Axis,
    BuildPart,
    BuildSketch,
    Box,
    Cylinder,
    Locations,
    Mode,
    Plane,
    Text,
    export_stl,
    extrude,
)

PLATE = (70.0, 46.0, 3.0)
NOMINALS = (3.0, 4.0, 5.0, 6.0, 8.0)  # matches the common shaft/screw sizes
CLEARANCES = (0.0, 0.10, 0.20, 0.30, 0.40)  # diametral, on a 6mm nominal pin


def coupon() -> BuildPart:
    w, d, t = PLATE
    with BuildPart() as p:
        Box(w, d, t, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Row 1: through holes at nominal. Measure each with a pin gauge or the
        # depth blade of your calipers; the shortfall is hole_compensation.
        y = d / 2 - 9
        xs = [-w / 2 + 10 + i * 12 for i in range(len(NOMINALS))]
        for x, dia in zip(xs, NOMINALS):
            with Locations((x, y)):
                Cylinder(dia / 2, t * 3, mode=Mode.SUBTRACT)

        # Row 2: pegs at the same nominals. The excess is peg_compensation.
        y2 = 0.0
        for x, dia in zip(xs, NOMINALS):
            with Locations((x, y2, t)):
                Cylinder(
                    dia / 2, 6, align=(Align.CENTER, Align.CENTER, Align.MIN)
                )

        # Row 3: sockets for a 6mm pin at a spread of clearances. Print a 6mm
        # peg (or use a 6mm rod) and find the first one that slides.
        y3 = -d / 2 + 9
        for x, clr in zip(xs, CLEARANCES):
            with Locations((x, y3)):
                Cylinder((6.0 + clr) / 2, t * 3, mode=Mode.SUBTRACT)

        # Engrave what each row is, because in a week you will not remember.
        for x, dia in zip(xs, NOMINALS):
            _label(f"{dia:g}", x, y - 6.0, t)
        for x, dia in zip(xs, NOMINALS):
            _label(f"{dia:g}", x, y2 - 6.0, t)
        for x, clr in zip(xs, CLEARANCES):
            _label(f"{clr:.2f}"[1:], x, y3 - 6.0, t)
    return p


def _label(text: str, x: float, y: float, t: float) -> None:
    """Engrave into the top of the plate. Cuts into the ambient BuildPart."""
    with BuildSketch(Plane.XY.offset(t)) as s:
        with Locations((x, y)):
            Text(text, font_size=3.5)
    extrude(s.sketch, amount=-0.6, mode=Mode.SUBTRACT)


def main() -> None:
    out = Path("out")
    out.mkdir(exist_ok=True)
    p = coupon()
    path = out / "calibration.stl"
    export_stl(p.part, str(path))
    print(f"wrote {path}")
    print(
        "\nPrint it, then measure:\n"
        "  row 1 (holes)   measured - nominal  -> hole_compensation = -that (a positive number)\n"
        "  row 2 (pegs)    measured - nominal  -> peg_compensation  = that\n"
        "  row 3 (sockets) the tightest one a 6mm pin enters by hand -> fit_snug\n"
        "                  the one that needs a press               -> fit_press\n"
        "                  the one that slides freely               -> fit_slide\n"
        "\nWrite them into printer_profile.json and set calibrated: true."
    )


if __name__ == "__main__":
    main()
