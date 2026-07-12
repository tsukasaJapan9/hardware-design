---
name: build123d-hardware
description: Design 3D-printable hardware in build123d that actually assembles — parametric parts, metal fasteners, bearings, joint-based assemblies, geometric validation (wall thickness, overhang, interference, running clearance), and print-ready STL/STEP/BOM export. Use when the user wants to design a bracket, mount, enclosure, mechanism, jig, or any printed part that has to mate with other parts or with bought hardware.
---

# Printable, assemblable hardware with build123d

A part that renders beautifully and cannot be assembled is a failure. The whole
point of this toolkit is to close the gap between "the CAD looks right" and "the
printed parts go together", and that gap is made of exactly four things:

1. **Tolerance.** A hole modelled at 3.0mm prints at about 2.85mm. Every fit in
   the design comes from a measured `PrinterProfile`, never from a literal.
2. **Fastening.** Printed threads strip. Real hardware — heat-set inserts,
   captive nuts, machine screws — or the thing falls apart.
3. **Manufacturability.** Overhangs droop, thin walls vanish, small holes close.
4. **Interference.** Two parts cannot occupy the same space, and a part that has
   to rotate needs somewhere to rotate into.

The first is a measurement, and the other three are checkable. `hwkit` checks
them, so you find these problems in seconds instead of after a four-hour print.

## Run it

```bash
uv run python -m designs.<name>            # validate, print the report
uv run python -m designs.<name> --export   # validate, then write out/<name>/
uv run python -m hwkit.calibrate           # the tolerance coupon
```

## The workflow

### 0. Model the bought parts before you design anything

**A mount is a negative of a component. A negative of a guess is scrap.**

Servos, sensors, PCBs, batteries, motors — before a single bracket exists, each
one is a `Component` in `hwkit/components.py` carrying its real dimensions, its
mounting holes, and its **keepouts**. Nothing else in this workflow is allowed to
start until that is done.

A hole pattern is not enough, because parts do not collide on their screws. They
collide on the USB plug nobody left room to insert, on the servo cable exiting
where the wall is, on the horn sweeping through a bracket arm, on the battery
that swelled a millimetre. Those are `keepout` volumes and the interference check
treats them exactly like solid material.

```python
SOME_SENSOR = Component(
    name="...", kind="sensor",
    source="measured with calipers, 2026-07-13",   # or the datasheet
    verified=True,                                  # only after a human checked
    vols=(
        Vol("box", (25.0, 11.0, 1.6), at=(0, 0, 0), why="the PCB"),
        Vol("box", (8.0, 6.0, 12.0), at=(-8, 0, 1.6), role="keepout",
            why="JST plug needs room to insert"),
    ),
    mounts=(Mount(-9.0, 0.0, 2.2, "M2"), Mount(9.0, 0.0, 2.2, "M2")),
)
```

**The datum.** z = 0 is the mounting plane, origin at the centre of the hole
pattern. **+Z is the side the component is on. −Z is through the bracket** — a
motor's pilot boss and shaft, a servo case hanging through a cutout, the solder
tails under a PCB. That sign is how the bracket learns it needs a bore.

Then `asm.bought("motor", NEMA17)` hands the checks the component's *envelope* —
body plus keepouts — and `MountHoles(NEMA17, kind="insert")` cuts its pattern
into whatever face you place it on.

#### When you do not have the data: **ask the user. Do not estimate.**

This is not optional and there is no fallback. If a component is not in the
library, or is in it with `verified=False`, the design **stops**:

```
MissingComponentData: 'SG90 micro servo' is in the library but NOT verified.
These numbers are nominal. Ask the user to confirm them against the part in
their hand before anything gets printed.
```

When that fires, or when the user names a part you have no model for, **stop and
ask them**, quoting the checklist (`hwkit.components.CHECKLIST[kind]`) for what
to measure:

> To design this bracket I need the SG90's actual dimensions — clones vary
> between batches. Could you measure yours, or send me the datasheet?
> - body length x width x height (the case, not the tabs)
> - hole spacing between tab hole centres, and the hole diameter
> - output shaft: how far from the hole pattern centre, along which axis
> - how far the horn sticks out, and its swept diameter
> - which face the cable leaves from, and how much room the bend needs

Do not measure a part from a photograph, do not average what the internet says,
and do not proceed with a placeholder "to be refined later" — there is no later,
there is a printed bracket that does not fit. Once the user answers, add the
`Component` with `source=` recording where the numbers came from, set
`verified=True`, and only then design.

The library ships `NEMA17` and `RPI5` as verified (published standards), and
`SG90` and `CELL_18650` as nominal-but-unverified, which is to say: as a
conversation starter with the user, not as a licence to print.

### 1. Calibrate first, once per printer + material

Do this before trusting any fit. It is the difference between a press fit and a
cracked part.

```bash
uv run python -m hwkit.calibrate    # -> out/calibration.stl
```

Print it, measure it with calipers, write the numbers into `printer_profile.json`,
set `"calibrated": true`. Until then every design carries an UNCALIBRATED warning
on its BOM, which is honest — the numbers in `PrinterProfile()` are reasonable
FDM/PLA defaults, not *your* printer.

If the user has not calibrated, say so once and carry on. Do not pretend the
default clearances are measured.

### 2. Design the assembly, not the parts

Parts are what falls out of an assembly. Start from `Assembly`, declare what
mates to what with build123d joints, and declare what has to *move*:

```python
from build123d import *
from hwkit import *

P = load_profile()

def bracket() -> Part:
    with BuildPart() as p:
        Box(40, 30, 5, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations(Plane.XY.offset(5)):          # cut from the top face
            with Locations((-14, 0), (14, 0)):
                CounterBore(M3, depth=5, profile=P)  # screw head sits flush
    RigidJoint("foot", p.part, Location((0, 0, 0)))
    return p.part

asm = Assembly("gizmo", P)
b = asm.add("base", base(), support="none", note="inserts go in from the top")
r = asm.add("bracket", bracket(), print_orientation=Rotation(0, 0, 0))
asm.mate(b.joints["top"], r.joints["foot"])
asm.must_move("roller", "bracket", 0.5)   # this is a promise the checks enforce
asm.buy("M3 x 12 socket cap screw", 4, "bracket down to base")
asm.step("Heat-set the four inserts into the base. Let them cool before you touch them.")
```

Two frames, and confusing them is the easy mistake. `add()` snapshots the
**design frame**, which is where printability and STL export live. `mate()` moves
the part into the **assembly frame**, which is where interference and clearance
live. That is why `print_orientation` still means something after the part has
been rotated into place by a joint.

### 3. Validate before you export

```python
for r in asm.validate():
    print(r)
```

Errors block the print. Warnings are a decision you make on purpose:

| check | catches | severity |
|---|---|---|
| `manifold` | broken solids, or one "part" that is secretly two loose pieces | error |
| `bounds` | does not fit on the plate | error |
| `wall` | thin walls, and the **web left between a hole and an edge** | error under 2x nozzle |
| `hole` | holes too small to survive printing | warn |
| `overhang` | downward surface past the support angle; flags flat ceilings as bridges | warn |
| `interference` | two parts in the same space — the assembly is impossible | error |
| `clearance` | a part that must move has nowhere to move | error |

Take the warnings seriously. On the reference design the overhang check found
four 1mm² undercut lips where a counterbore had bitten into a fillet — invisible
in a render, and each one a support scar on a mating face.

### 4. Export

`asm.export()` writes, per part, an STL already rotated to its print orientation
and sat on Z=0 (so *do not rotate it in the slicer*), plus a STEP of the whole
assembly in its assembled positions, plus `BOM.md` and `ASSEMBLY.md`.

Refuse to export a design with errors. `designs/roller_bracket.py` shows the
pattern.

## Doctrine

**Never design around a component you have not modelled.** And never model one
from a guess — ask. See step 0; it is the one that costs the most when skipped,
because a bracket cut around wrong numbers looks perfect until it is in your hand.

**Never model a printed thread.** Use `InsertBoss` (heat-set, reusable, strong),
or `NutPocket` (captive nut, free), in that order. Self-tapping into a plain hole
is for light loads and one assembly cycle.

**Never write a clearance as a literal.** `P.hole(3.0, "free")`, `P.bore(10.0,
"press")`, `P.peg(6.0, "snug")`, `P.gap("slide")`. When the user recalibrates,
every fit in every design updates. A `3.4` in the source does not.

**Orient for strength, then for surface.** Layers peel apart under tension across
the print direction; a bracket loaded in bending wants its layers running along
the load, not across it. This is usually the real reason to pick an orientation,
and support is a distant second.

**Fillet the roots.** Where a rib or upright meets a plate is where printed parts
snap, because the layers there are loaded in peel.

**Model bought parts** — bearings, shafts, motors — with `asm.bought()`. They are
never exported, but the interference and clearance checks can only see what has
been modelled, and the parts that collide in practice are usually the bought ones.

**Design out the support.** A chamfer under an overhang, a teardrop instead of a
round hole, a part split in two and screwed together — all better than support on
a surface that has to mate with something.

## Where things are

- `hwkit/components.py` — **start here.** `Component` `Vol` `Mount` `MountHoles`,
  the datum convention, the measurement checklists, and the gate that stops a
  design built on guessed dimensions.
- `hwkit/profile.py` — the `PrinterProfile` and the fit model.
- `hwkit/fasteners.py` — `ClearanceHole` `CounterBore` `CounterSink` `InsertBoss`
  `NutPocket`, and the M2–M6 dimension table.
- `hwkit/parts.py` — `BearingPocket` `ShaftBore`, bearing and shaft tables.
- `hwkit/validate.py` — the checks, and why each one is written the way it is.
- `hwkit/assembly.py` — `Assembly`, the two frames, BOM and export.
- `designs/motor_mount.py` — designing around a bought component. Copy this when
  the design holds something you bought.
- `designs/roller_bracket.py` — fits, bearings, and a running clearance.
- `references/components.md` — how to measure a part, and what to ask the user for.
- `references/design-rules.md` — the numbers, and why they are what they are.
- `references/build123d-api.md` — **read this before writing build123d code.** It
  is the list of things that will otherwise cost you an hour each.
