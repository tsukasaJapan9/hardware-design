"""Known-answer tests for the checks.

Each case has a thickness or an area you can work out on paper. If one of these
drifts, the checks are lying, and a lying check is worse than no check — it is
the thing standing between the user and a four-hour print.
"""

from __future__ import annotations

import math

import pytest
from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    Hole,
    Location,
    Locations,
    Plane,
    chamfer,
    fillet,
    offset,
)

from hwkit import (
    BEARINGS,
    M3,
    BearingPocket,
    CounterBore,
    InsertBoss,
    NutPocket,
    PrinterProfile,
    check_clearance,
    check_interference,
    check_part,
)
from hwkit.validate import _holes

P = PrinterProfile()


def wall_of(part, name="t") -> float:
    stat = check_part(part, name, profile=P).stats["min wall"]
    return float(stat.replace("mm", "").replace(">= ", ""))


# --- wall thickness ---------------------------------------------------------


@pytest.mark.parametrize(
    "thickness",
    [0.8, 1.5, 3.0, 6.0],
)
def test_plate_thickness_is_measured_exactly(thickness):
    assert wall_of(Box(30, 30, thickness)) == pytest.approx(thickness, abs=0.02)


def test_bore_does_not_read_as_a_zero_wall():
    """A mesh point on a concave face sits outside the solid. Naively stepping
    inward from it measures the chord sag, ~0.00mm, on every part with a hole."""
    with BuildPart() as p:
        Box(30, 30, 5.0)
        Hole(radius=4)
    assert wall_of(p.part) == pytest.approx(5.0, abs=0.02)


def test_chamfer_does_not_read_as_a_zero_wall():
    with BuildPart() as p:
        Box(40, 30, 10)
        chamfer(p.edges(), 1.5)
    assert wall_of(p.part) == pytest.approx(10.0, abs=0.05)


def test_hollow_box_wall():
    with BuildPart() as p:
        Box(40, 30, 20)
        offset(amount=-2, openings=p.faces().sort_by(Axis.Z)[-1])
    assert wall_of(p.part) == pytest.approx(2.0, abs=0.05)


def test_thin_web_between_a_hole_and_an_edge_is_caught():
    """The failure nobody sees in a render: a 4mm hole 2.5mm from the edge of a
    20mm plate leaves 0.5mm of material."""
    with BuildPart() as p:
        Box(20, 20, 6)
        with Locations((7.5, 0, 3)):
            Hole(radius=2.0)
    rep = check_part(p.part, "web", profile=P)
    assert not rep.ok
    assert wall_of(p.part) == pytest.approx(0.5, abs=0.03)


def test_thin_plate_is_an_error_not_a_warning():
    rep = check_part(Box(30, 30, 0.6), "thin", profile=P)  # below 2 x nozzle
    assert [i.severity for i in rep.issues if i.check == "wall"] == ["error"]


# --- overhang ---------------------------------------------------------------


def test_flat_ceiling_area_is_exact():
    """A 30x10 slab on a 6x10 leg: 300 - 60 = 240mm2 of ceiling, all at 90deg."""
    with BuildPart() as p:
        Box(30, 10, 4)
        with Locations((0, 0, -12)):
            Box(6, 10, 20)
    rep = check_part(p.part.moved(Location((0, 0, 22))), "T", profile=P)
    overhang = [i for i in rep.issues if i.check == "overhang"]
    assert len(overhang) == 1
    assert "240 mm2" in overhang[0].message
    assert "90 deg" in overhang[0].message


def test_a_box_has_no_overhang():
    rep = check_part(Box(20, 20, 20), "box", profile=P)
    assert not [i for i in rep.issues if i.check == "overhang"]


def test_45_degree_underside_is_within_the_threshold():
    with BuildPart() as p:
        Box(20, 20, 10)
        chamfer(p.faces().sort_by(Axis.Z)[0].edges().group_by(Axis.X)[0], 4)
    assert not [i for i in check_part(p.part, "c", profile=P).issues if i.check == "overhang"]


# --- holes ------------------------------------------------------------------


def test_a_fillet_is_not_a_hole():
    """A fillet is a cylindrical face too. A naive check calls a 0.8mm fillet a
    1.6mm hole and warns about four of them on every rounded box."""
    with BuildPart() as p:
        Box(30, 30, 6)
        fillet(p.edges().filter_by(Axis.Z), 0.8)
        with Locations((0, 0, 3)):
            Hole(radius=0.6)
    found = sorted(round(d, 2) for d, _c in _holes(p.part))
    assert found == [1.2]


def test_small_hole_warns():
    with BuildPart() as p:
        Box(20, 20, 5)
        Hole(radius=0.5)
    rep = check_part(p.part, "h", profile=P, check_thickness=False)
    assert [i.check for i in rep.issues] == ["hole"]
    assert rep.ok  # a warning, not an error: you can drill it


# --- assembly ---------------------------------------------------------------


def test_interference_volume_is_exact():
    a = Box(20, 20, 10)
    b = Box(20, 20, 10).moved(Location((18, 0, 0)))  # 2mm x 20 x 10 = 400mm3
    rep = check_interference({"a": a, "b": b})
    assert not rep.ok
    assert "400.00 mm3" in rep.issues[0].message


def test_touching_parts_are_not_interfering():
    a = Box(20, 20, 10)
    b = Box(20, 20, 10).moved(Location((20, 0, 0)))  # face to face
    assert check_interference({"a": a, "b": b}).ok


def test_clearance_shortfall_is_caught():
    a = Box(20, 20, 10)
    b = Box(20, 20, 10).moved(Location((29.5, 0, 0)))  # 9.5mm gap
    assert check_clearance({"a": a, "b": b}, [("a", "b", 9.0)]).ok
    assert not check_clearance({"a": a, "b": b}, [("a", "b", 10.0)]).ok


def test_disconnected_solids_in_one_part_are_an_error():
    part = Box(10, 10, 10) + Box(10, 10, 10).moved(Location((30, 0, 0)))
    rep = check_part(part, "split", profile=P, check_thickness=False)
    assert not rep.ok
    assert "2 disconnected solids" in rep.errors[0].message


def test_oversized_part_is_caught():
    small = PrinterProfile(build_volume=(100, 100, 100))
    rep = check_part(Box(150, 20, 20), "big", profile=small, check_thickness=False)
    assert not rep.ok
    assert "build volume" in rep.errors[0].message


# --- profile ----------------------------------------------------------------


def test_holes_grow_and_pegs_shrink():
    """The whole reason no dimension in a design is a literal."""
    assert P.hole(3.0, "free") == pytest.approx(3.0 + 0.15 + 0.45)
    assert P.peg(6.0, "snug") == pytest.approx(6.0 - 0.10 - 0.10)
    assert P.bore(10.0, "press") == pytest.approx(10.0 + 0.15)


def test_unknown_fit_is_refused():
    with pytest.raises(ValueError, match="press | snug | slide | free"):
        P.hole(3.0, "tight-ish")


# --- the pockets actually cut ------------------------------------------------


def test_pockets_remove_material_at_their_locations():
    for pocket in (
        lambda: CounterBore(M3, depth=6, profile=P),
        lambda: InsertBoss(M3, profile=P),
        lambda: NutPocket(M3, profile=P),
        lambda: BearingPocket(BEARINGS["623"], profile=P),
    ):
        with BuildPart() as p:
            Box(30, 30, 10, align=(Align.CENTER, Align.CENTER, Align.MAX))
            with Locations(Plane.XY):
                pocket()
        assert p.part.is_valid and p.part.is_manifold
        assert p.part.volume < 30 * 30 * 10, f"{pocket} cut nothing"


def test_reference_design_validates_and_has_no_errors():
    from designs.roller_bracket import build

    reports = build().validate(samples=800)
    failed = [r.name for r in reports if not r.ok]
    assert not failed, f"reference design regressed: {failed}"


# --- bought components -------------------------------------------------------


def test_unverified_component_stops_the_design():
    """The gate. A mount is a negative of a component, and a negative of a guess
    is scrap — so a component nobody has measured must not reach a printer."""
    from hwkit import SG90, Assembly, MissingComponentData

    asm = Assembly("x", P)
    with pytest.raises(MissingComponentData, match="NOT verified"):
        asm.bought("servo", SG90)


def test_verified_component_passes_and_brings_its_keepouts():
    from hwkit import NEMA17, Assembly

    asm = Assembly("x", P)
    env = asm.bought("motor", NEMA17)
    body_only = NEMA17.body().volume
    assert env.volume > body_only  # the cable keepout is in there too
    assert asm.components["motor"] is NEMA17


def test_require_names_what_to_measure():
    from hwkit import MissingComponentData, require

    with pytest.raises(MissingComponentData, match="connector position"):
        require("some ToF sensor", "sensor")


def test_component_datum_puts_penetrating_features_below_zero():
    """NEMA 17 sits on the plate (+Z) and puts its boss and shaft through it (-Z).
    That sign is how a bracket learns it needs a bore."""
    from hwkit import NEMA17

    bb = NEMA17.body().bounding_box()
    assert bb.max.Z == pytest.approx(48.0)  # body, on the component's side
    assert bb.min.Z == pytest.approx(-24.0)  # shaft, through the plate


def test_mount_holes_cut_the_real_pattern():
    from build123d import Box, BuildPart, Locations, Plane
    from hwkit import NEMA17, MountHoles

    with BuildPart() as p:
        Box(60, 60, 10, align=(Align.CENTER, Align.CENTER, Align.MAX))
        with Locations(Plane.XY):
            MountHoles(NEMA17, kind="insert", profile=P)
    assert p.part.is_valid and p.part.is_manifold
    assert p.part.volume < 60 * 60 * 10
    # four bosses, at the 31mm square pattern
    assert len(NEMA17.mounts) == 4
    assert {abs(m.x) for m in NEMA17.mounts} == {15.5}


def test_motor_mount_design_has_no_interference():
    from designs.motor_mount import build

    reports = build().validate(samples=800)
    assert not [r.name for r in reports if not r.ok]
