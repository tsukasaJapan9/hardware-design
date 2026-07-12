# Design rules for FDM parts that have to fit

Numbers for a 0.4mm nozzle, 0.2mm layers, PLA or PETG. They are defaults in
`PrinterProfile`, and the ones marked **measure** are the ones the calibration
coupon exists to replace.

## Tolerance

An FDM printer does not print what you model. The nozzle traces the inside of a
hole with finite width and the plastic shrinks as it cools, so **holes come out
undersized and pegs come out oversized**, both by roughly 0.1–0.2mm.

This is why nothing in a design is a literal dimension:

| you want | you call | default result |
|---|---|---|
| a hole a 3mm screw passes freely | `P.hole(3.0, "free")` | 3.60mm |
| a hole that also locates the part | `P.hole(3.0, "snug")` | 3.25mm |
| a pocket a 10mm bearing presses into | `P.bore(10.0, "press")` | 10.15mm |
| a bore a 5mm shaft turns in | `P.hole(5.0, "slide")` | 5.40mm |
| a peg that enters a 6mm hole | `P.peg(6.0, "snug")` | 5.80mm |
| a lid that slides into a groove | `P.gap("slide")` | 0.20mm per side |

The fit classes, diametral, on top of the compensation:

| fit | clearance | for |
|---|---|---|
| `press` | 0.00 | bearing outer race, dowel. Needs real force. **measure** |
| `snug` | 0.10 | located, removable by hand |
| `slide` | 0.25 | shaft in a plain bore, a lid in a groove |
| `free` | 0.45 | a screw shank through a plate |

**A press fit is the one you cannot guess.** Too loose and the bearing spins in
its pocket and eats it. Too tight and the boss splits, usually a day later. Print
the coupon.

## Walls, holes, and everything thin

| rule | value | why |
|---|---|---|
| minimum wall | **1.2mm** (3 perimeters) | 2 perimeters have no infill between them and split |
| absolute floor | 0.8mm (2 x nozzle) | below this the slicer silently drops the wall |
| minimum hole | 2.0mm | smaller and it closes up; plan to drill it |
| web between a hole and an edge | ≥ 1.2mm | this is where parts break, and nobody checks it by eye |
| boss around a heat-set insert | ≥ 1 insert diameter of material all round | otherwise it splits when the insert goes in |

The wall check finds all of these, including the web, which is the one that gets
missed. A 4mm hole 2mm from the edge of a plate leaves a 0.0mm web and looks
perfectly fine in a render.

## Overhang and bridging

Overhang is measured **from vertical**: a vertical wall is 0°, a flat ceiling is
90°.

| angle | what happens |
|---|---|
| 0–45° | prints cleanly |
| 45–55° | usually fine; the default threshold is 50° |
| 55–80° | droops. Support, or redesign |
| 80–90° | a bridge if it spans between two walls; spaghetti if it does not |

A bridge up to ~25mm prints acceptably between two anchors. An unanchored
horizontal ceiling — the roof of a blind pocket — is not a bridge, it is a
ceiling, and it needs support or a redesign.

**Design the support out instead of adding it.** In descending order of elegance:

- **Chamfer under the overhang.** A 45° chamfer under a boss or a lip is free.
- **Teardrop a horizontal hole.** A round hole in a vertical wall has a 90°
  overhang at its apex. Small ones (≤ 5mm) bridge fine and are not worth the
  ugliness; large ones want a teardrop.
- **Split the part** and screw it together. Two parts each printing flat, with
  no support and better layer orientation, beat one heroic part every time.
- **Reorient.** Free, and usually the right answer — but check what it does to
  the layer direction before you accept it.

## Strength and orientation

Layers peel. A printed part is roughly **half as strong across the layers as
along them**, and the failure is sudden.

- Orient so the load runs **along** the layers, not across them.
- A bracket loaded in bending: the layers want to run along the arm.
- Fillet where a rib or upright meets a plate. That corner is loaded in peel and
  it is where printed parts snap. 2mm is enough to change the outcome.
- Anything that takes a screw wants **40%+ infill** locally and 3+ perimeters.
- A thin flat part printed flat is a hinge. Printed on edge it is a beam.

## Fastening

In descending order of preference:

| method | strength | reusable | notes |
|---|---|---|---|
| **heat-set insert** | best | yes | `InsertBoss`. Iron at ~220°C, push straight down, let it cool before touching it |
| **captive hex nut** | very good | yes | `NutPocket`. Free. The pocket ceiling is a short bridge and prints fine |
| **self-tap into a plain hole** | fair | no, once | hole ≈ 0.85 × screw dia. Light loads, one assembly cycle |
| **printed thread** | worthless | no | do not |

Sink screw heads with `CounterBore` (socket cap) or `CounterSink` (flat head).
Countersinks are self-supporting when they open upward.

## The elephant foot

The first layer is squashed and spreads by 0.2–0.4mm. A part that has to sit flat
against another part, or drop into a pocket, will not — it is fatter at the
bottom than the model says.

Chamfer the bottom edge by `P.elephant_foot` (0.3mm default). It is one line and
it is the difference between a part that seats and a part that rocks.

## Bearings

- The pocket takes the **outer** race. `BearingPocket` bores through the lip
  under it to clear the **inner** race, so the lip can never touch the part that
  spins.
- Press only on the outer race when you fit it. A socket, or the flat of a vice.
  Pressing on the inner race brinells the balls and the bearing is finished —
  it will feel notchy and it will not get better.
- Give the bearing a shoulder to seat against (`lip=1.0`), or it wanders in.
- The seat is 4–7mm of engagement on a small bearing. Deeper is not better; the
  pocket floor is where the print goes wrong.

## Before you commit to a long print

1. `asm.validate()` clean of errors.
2. Warnings understood and accepted on purpose, not ignored.
3. The profile is calibrated, or you know it is not and the fits are guesses.
4. For anything with a press fit or a running clearance: **print the one small
   part first**, or a 10mm test coupon of just the pocket. A four-hour print that
   ends in a bearing that will not go in is a four-hour print you did twice.
