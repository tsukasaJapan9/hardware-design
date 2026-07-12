# hardware-design

3D-printable hardware, designed in [build123d](https://build123d.readthedocs.io),
that actually goes together.

A part that renders beautifully and cannot be assembled is a failure. The gap
between "the CAD looks right" and "the printed parts fit" is made of four things,
and this repo attacks all four:

- **tolerance** — every fit comes from a measured `PrinterProfile`, never a literal
- **fastening** — heat-set inserts, captive nuts, real screws; printed threads strip
- **manufacturability** — thin walls, overhangs, and holes too small to survive
- **interference** — two parts cannot share a space, and a moving part needs room

The last three are checkable, so `hwkit` checks them. You find the problems in
seconds instead of after a four-hour print.

## Quick start

```bash
uv sync
uv run python -m hwkit.calibrate              # the tolerance coupon — print this first
uv run python -m designs.roller_bracket       # validate the reference design
uv run python -m designs.roller_bracket --export   # -> out/roller-bracket/
uv run pytest                                 # the checks are tested against known answers
```

## What comes out

`asm.export()` writes, per part, an STL already rotated to its print orientation
and sat on Z=0, a STEP of the whole assembly in its assembled positions, a
`BOM.md` listing what to print and what to buy, and an `ASSEMBLY.md` telling you
the order to put it together in.

## Calibrate before you trust a fit

`printer_profile.json` starts with sane FDM/PLA defaults and `"calibrated": false`,
and every BOM says so. Print `out/calibration.stl`, measure it with calipers,
write the numbers in. One measurement propagates to every clearance in every
design — that is the whole reason nothing is a literal dimension.

## Layout

```
hwkit/           the toolkit
  profile.py       PrinterProfile: the measured reality of one printer
  fasteners.py     M2-M6, ClearanceHole CounterBore CounterSink InsertBoss NutPocket
  parts.py         bearings, shafts, footprints, BearingPocket ShaftBore
  validate.py      the checks, and why each is written the way it is
  assembly.py      Assembly: joints, BOM, print orientation, export
  calibrate.py     the tolerance coupon
designs/         your designs. roller_bracket.py is the reference
tests/           known-answer tests for the checks
```

The [skill](.claude/skills/build123d-hardware/SKILL.md) documents the workflow;
its `references/` hold the design rules and a hard-won list of build123d's
sharp edges.
