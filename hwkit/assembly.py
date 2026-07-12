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

from build123d import Compound, Location, Part, Rotation, export_step, export_stl

from .profile import DEFAULT, PrinterProfile
from .validate import Report, check_clearance, check_interference, check_part


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
        self.hardware: list[Hardware] = []
        self.steps: list[str] = []
        self.moving: list[tuple[str, str, float]] = []

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

    def bought(self, name: str, part: Part, **kw) -> Part:
        """A part you buy, modelled so the checks can see it. Never exported."""
        return self.add(name, part, printed=False, qty=0, **kw)

    def buy(self, item: str, qty: int, note: str = "") -> None:
        self.hardware.append(Hardware(item, qty, note))

    def step(self, text: str) -> None:
        self.steps.append(text)

    def must_move(self, a: str, b: str, min_gap: float) -> None:
        """Two parts move relative to each other, and need this much room."""
        self.moving.append((a, b, min_gap))

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
        reports = [
            check_part(p.on_plate(), p.name, profile=self.profile, samples=samples)
            for p in self.parts.values()
            if p.printed
        ]
        reports.append(check_interference(self.placed()))
        if self.moving:
            reports.append(check_clearance(self.placed(), self.moving))
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
        if self.moving:
            lines += ["", "## Must move freely", ""]
            for a, b, gap in self.moving:
                lines.append(f"- **{a}** against **{b}** — {gap}mm of clearance by design")
        lines.append("")
        return "\n".join(lines)
