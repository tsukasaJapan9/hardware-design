"""An assembly is the design. The parts are just its consequences.

This wraps build123d's joints with the bookkeeping that turns a pile of solids
into something a human can build: which way up each part prints, what hardware to
buy, what order it goes together in, and proof that the pieces do not collide.

Two frames matter, and confusing them is the easy mistake:

  design frame    where you authored the part, before any joint moved it.
                  Printability and STL export live here, rotated by
                  `print_orientation` to put the part on the plate.

  assembly frame  where the part ends up once its joints are connected.
                  Interference and running clearance live here.

`add()` snapshots the design frame, so `mate()` is free to move the live part
around without dragging the print orientation with it.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

from build123d import Compound, Location, Part, Rotation, Vector, export_step, export_stl

from .components import Component
from .profile import DEFAULT, PrinterProfile
from .validate import (
    Report,
    check_clearance,
    check_insertion,
    check_interference,
    check_part,
)


@dataclass
class PrintedPart:
    name: str
    part: Part  # live: moves as joints are connected
    design: Part  # snapshot: the frame the part was authored in
    print_orientation: Rotation = field(default_factory=lambda: Rotation(0, 0, 0))
    qty: int = 1
    support: str = "auto"  # auto | none | required
    note: str = ""
    printed: bool = True  # False for bought parts, modelled only so checks see them

    def on_plate(self) -> Part:
        """The part as it will be sliced: rotated for printing, sat on Z=0."""
        oriented = self.design.moved(self.print_orientation)
        bb = oriented.bounding_box()
        return oriented.moved(
            Location((-bb.center().X, -bb.center().Y, -bb.min.Z))
        )


@dataclass
class Hardware:
    item: str
    qty: int
    note: str = ""


class Assembly:
    """Parts, hardware, and how they go together."""

    def __init__(self, name: str, profile: PrinterProfile = DEFAULT):
        self.name = name
        self.profile = profile
        self.parts: dict[str, PrintedPart] = {}
        self.components: dict[str, Component] = {}
        self.hardware: list[Hardware] = []
        self.steps: list[str] = []
        self.moving: list[tuple[str, str, float]] = []
        self.insertions: list[tuple] = []

    # ---- authoring -------------------------------------------------------

    def add(
        self,
        name: str,
        part: Part,
        *,
        print_orientation: Rotation | None = None,
        qty: int = 1,
        support: str = "auto",
        note: str = "",
        printed: bool = True,
    ) -> Part:
        self.parts[name] = PrintedPart(
            name=name,
            part=part,
            design=copy.deepcopy(part),
            print_orientation=print_orientation or Rotation(0, 0, 0),
            qty=qty,
            support=support,
            note=note,
            printed=printed,
        )
        return part

    def bought(self, name: str, thing: Part | Component, **kw) -> Part:
        """A part you buy, modelled so the checks can see it. Never exported.

        Pass a `Component` and you get its envelope — body *plus* keepouts — so
        the interference check sees the connector you have to plug in and the arc
        the servo horn sweeps, not just the case. Passing a bare `Part` is for
        raw stock: a length of rod, a sheet of ply.

        A component nobody has verified stops the design here, on purpose.
        """
        if isinstance(thing, Component):
            thing.check()  # raises MissingComponentData if the numbers are guesses
            self.components[name] = thing
            part = thing.envelope()
            kw.setdefault("note", f"{thing.name} — {thing.source}")
        else:
            part = thing
        return self.add(name, part, printed=False, qty=0, **kw)

    def buy(self, item: str, qty: int, note: str = "") -> None:
        self.hardware.append(Hardware(item, qty, note))

    def step(self, text: str) -> None:
        self.steps.append(text)

    def must_move(self, a: str, b: str, min_gap: float) -> None:
        """Two parts move relative to each other, and need this much room."""
        self.moving.append((a, b, min_gap))

    def goes_in(
        self,
        moving: str,
        into: str,
        *,
        direction: tuple[float, float, float] = (0, 0, 1),
        distance: float | None = None,
        clearance: float | None = None,
    ) -> None:
        """Declare that a part is put into place by moving it, and check it can be.

        `direction` is the way it travels to come OUT; `distance` how far until it
        is clear (defaults to the part's own height along that axis, doubled).

        This is a different question from interference, and a more useful one. A
        lid cut to exactly the size of its cavity overlaps nothing, passes every
        interference check, and will not go in — because room is not the absence
        of overlap, it is being able to move and still not touch. Declare this for
        anything that has to be *got into* somewhere: a lid, a bearing, a nut in a
        pocket, a board between standoffs.
        """
        self.insertions.append((moving, into, direction, distance, clearance))

    def mate(self, joint_a, joint_b, **kwargs) -> None:
        """Connect two build123d joints, placing b relative to a."""
        joint_a.connect_to(joint_b, **kwargs)

    # ---- checks ----------------------------------------------------------

    def placed(self) -> dict[str, Part]:
        """Every part where it sits in the assembled machine."""
        return {n: p.part for n, p in self.parts.items()}

    def compound(self) -> Compound:
        return Compound(children=[p.part for p in self.parts.values()])

    def validate(self, *, samples: int = 2000) -> list[Report]:
        placed = self.placed()
        reports = [
            check_part(p.on_plate(), p.name, profile=self.profile, samples=samples)
            for p in self.parts.values()
            if p.printed
        ]
        reports.append(check_interference(placed))
        if self.moving:
            reports.append(check_clearance(placed, self.moving))

        for moving, into, direction, distance, clearance in self.insertions:
            part = placed[moving]
            if distance is None:
                # Far enough to be completely clear of whatever it came out of.
                bb = part.bounding_box()
                span = abs(Vector(*direction).normalized().dot(bb.size))
                distance = max(span * 2, 10.0)
            if clearance is None:
                clearance = self.profile.gap("slide")
            reports.append(
                check_insertion(
                    part,
                    placed[into],
                    direction,
                    distance,
                    clearance=clearance,
                    names=(moving, into),
                )
            )
        return reports

    # ---- output ----------------------------------------------------------

    def export(self, outdir: str | Path = "out") -> Path:
        """Print-ready STLs, a STEP of the whole machine, and the paperwork."""
        out = Path(outdir) / self.name
        out.mkdir(parents=True, exist_ok=True)

        for p in self.parts.values():
            if p.printed:
                export_stl(p.on_plate(), str(out / f"{p.name}.stl"))

        export_step(self.compound(), str(out / f"{self.name}.step"))
        (out / "BOM.md").write_text(self.bom_md())
        (out / "ASSEMBLY.md").write_text(self.assembly_md())
        return out

    def bom_md(self) -> str:
        cal = (
            "calibrated"
            if self.profile.calibrated
            else "**UNCALIBRATED — print the tolerance coupon before you trust any fit**"
        )
        lines = [
            f"# {self.name} — bill of materials",
            "",
            "## Print",
            "",
            "| file | qty | support | notes |",
            "|---|---|---|---|",
        ]
        for p in self.parts.values():
            if p.printed:
                lines.append(f"| `{p.name}.stl` | {p.qty} | {p.support} | {p.note} |")

        if self.hardware:
            lines += ["", "## Buy", "", "| item | qty | notes |", "|---|---|---|"]
            for h in self.hardware:
                lines.append(f"| {h.item} | {h.qty} | {h.note} |")

        if self.components:
            lines += [
                "",
                "## Components this design was cut around",
                "",
                "If a part does not fit, start here: the mount is a negative of these "
                "numbers, so a wrong number is a wrong bracket.",
                "",
                "| component | dimensions from | mass |",
                "|---|---|---|",
            ]
            for c in self.components.values():
                mass = f"{c.mass_g}g" if c.mass_g else "—"
                lines.append(f"| {c.name} | {c.source} | {mass} |")
            reasons = [
                (c.name, why)
                for c in self.components.values()
                for why in c.keepout_reasons()
            ]
            if reasons:
                lines += ["", "**Kept clear on purpose** — do not fill these in later:", ""]
                for name, why in reasons:
                    lines.append(f"- {name}: {why}")

        lines += [
            "",
            "## Slicer",
            "",
            f"- profile **{self.profile.name}** — {cal}",
            f"- {self.profile.nozzle}mm nozzle, {self.profile.layer_height}mm layers",
            "- 3 perimeters minimum; 40% infill in anything that takes a screw",
            "- STLs are already oriented and sat on the plate: do not rotate them",
            "",
        ]
        return "\n".join(lines)

    def assembly_md(self) -> str:
        lines = [f"# {self.name} — assembly", ""]
        if not self.steps:
            return "\n".join(lines + ["_No steps recorded. Call `asm.step(...)`._", ""])
        for i, s in enumerate(self.steps, 1):
            lines.append(f"{i}. {s}")
        if self.insertions:
            lines += ["", "## Goes in by moving", ""]
            for moving, into, direction, _dist, _clr in self.insertions:
                lines.append(
                    f"- **{moving}** into **{into}**, along {direction}. Checked that it "
                    f"can actually get there, and that it has room once it has."
                )
        if self.moving:
            lines += ["", "## Must move freely", ""]
            for a, b, gap in self.moving:
                lines.append(f"- **{a}** against **{b}** — {gap}mm of clearance by design")
        lines.append("")
        return "\n".join(lines)
