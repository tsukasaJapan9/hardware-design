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

- `hwkit/profile.py` — the `PrinterProfile` and the fit model. Read this first.
- `hwkit/fasteners.py` — `ClearanceHole` `CounterBore` `CounterSink` `InsertBoss`
  `NutPocket`, and the M2–M6 dimension table.
- `hwkit/parts.py` — `BearingPocket` `ShaftBore`, bearing/shaft/footprint tables.
- `hwkit/validate.py` — the checks, and why each one is written the way it is.
- `hwkit/assembly.py` — `Assembly`, the two frames, BOM and export.
- `designs/roller_bracket.py` — the reference design. Copy its shape.
- `references/design-rules.md` — the numbers, and why they are what they are.
- `references/build123d-api.md` — **read this before writing build123d code.** It
  is the list of things that will otherwise cost you an hour each.
