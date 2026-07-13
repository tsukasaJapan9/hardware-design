# Modelling the things you buy

A mount is a negative of a component. A negative of a guess is scrap.

This is the step people skip, and it is the step that decides whether the print
fits. Everything downstream — the bracket, the enclosure, the interference check
— is only as true as the numbers you put in here.

## The order is not negotiable

1. Get the component's real dimensions. Datasheet, or calipers, or **ask**.
2. Model it as a `Component`: solids, keepouts, mount holes, `source`.
3. `verified=True` only once a human has confirmed it against the real part.
4. *Then* design the bracket around it.

`Assembly.bought()` refuses an unverified component, and `require()` refuses an
unknown one. Those are not obstacles to route around. They are the design saying
it does not have enough information to be correct.

## What a footprint does not tell you

Parts rarely collide on their screws. They collide on:

| what | why it bites |
|---|---|
| **connector insertion** | a USB-C plug needs ~20mm of straight run past the socket. The socket is 3mm tall; the plug is not |
| **cable bend radius** | a servo cable leaving the case needs 8–10mm before it can turn. A wall at 3mm crushes it |
| **the underside of a PCB** | solder tails stand 2–3mm proud. Stand the board off, or it sits on its own joints |
| **swept volume** | a servo horn, a pulley, a fan blade. It is empty *now* |
| **thermal / swelling** | a LiPo pouch grows. A cell that cannot leave its pocket is a fire |
| **the tool** | you need to get a screwdriver, and your hand, to every screw |

All of these go in as `role="keepout"` volumes, and the interference check treats
them exactly like solid material — because as far as your bracket is concerned,
they are.

## The datum

**z = 0 is the mounting plane.** The origin sits at the centre of the mounting
hole pattern, in that plane. Mount holes are 2D `(x, y)` at z = 0.

**+Z is the side the component is on.** Body, connectors, horn.

**−Z is through the bracket.** A motor's pilot boss and output shaft, a servo case
hanging through a cutout, the solder tails under a PCB. Anything at negative Z is
telling the bracket it needs a hole there — that is the most useful thing the
model says, so get the sign right.

Do not assume the body is +Z. A NEMA 17 bolts on its face and puts its *shaft*
through the plate. An SG90 rests on its tabs and puts its *case* through the
plate. Both are correct.

## Measuring, when there is no datasheet

Calipers, and take each number twice. The ones that matter most, in order:

1. **Hole spacing, centre to centre.** Not edge to edge. If the holes are the
   same size, measuring outer-edge to outer-edge and subtracting one diameter is
   easier and more repeatable than trying to find two centres.
2. **Hole diameter.** Then model the *printed* hole with
   `P.hole(dia, "free")` — never the raw number.
3. **Body envelope at its fattest.** Include the sticker, the shrink wrap, the
   blob of hot glue. Not the idealised part: the one you own.
4. **Where the connectors are**, measured from the same origin as the holes, and
   **how far out you have to pull the plug** to seat it.
5. **Which way the cable leaves**, and how much room it needs to turn.

Then `source="measured with calipers, <date>"`, `verified=True`, and say in
`notes` what you were unsure about.

## Asking the user

When a component is missing or unverified, **stop and ask**. Do not estimate from
a photo, do not average forum posts, do not leave a placeholder. There is no
"refine it later" — there is a printed bracket that does not fit and an evening
gone.

`hwkit.components.CHECKLIST` holds the per-category list to ask for. Quote it:

> To cut this bracket I need the servo's real dimensions — SG90 clones vary
> between batches, and the mount is a negative of these numbers. Could you
> measure yours or send the datasheet?
>
> - body length x width x height (the case, not the tabs)
> - hole spacing between the tab hole centres, and the hole diameter
> - output shaft: how far from the centre of the hole pattern, along which axis
> - how far the horn sticks out past the case, and its swept diameter
> - which face the cable leaves from, and how much room the bend needs

Ask for all of it at once. Asking for one number, designing, then discovering you
need another is worse for the user than one complete question.

## What ships verified, and what does not

| component | verified | why |
|---|---|---|
| `NEMA17` | yes | NEMA frame standard: 42.3mm, 31mm bolt pattern, 22mm boss, 5mm shaft |
| `RPI5` | yes | published mechanical drawing: 85 x 56, 58 x 49 pattern, 3.5mm from the edges |
| `SG90` | **no** | clones vary; tab spacing and shaft offset move between batches |
| `CELL_18650` | **no** | protected cells run 69–70mm, bare cells 65mm, button tops add more |

The unverified two are there to start a conversation with the user, not to
license a print. The code will not let them through.

## A worked example

`examples/motor_mount.py`. The motor is modelled first — body, pilot boss, shaft,
and the room the cable needs behind it. Only then is a bracket cut around it, and
the interference check is the proof the bracket did not land on any of it.

Delete the cable keepout from `NEMA17` and re-run: the design still passes, and
the motor still does not fit. **You cannot check what you did not model.** That is
the whole argument for doing this step first.
