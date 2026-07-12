"""Geometry checks that catch the failures you would otherwise find at the printer.

Each check answers one question that costs a print to answer empirically:

  manifold    - will the slicer even accept this solid?
  bounds      - does it fit on the plate?
  wall        - is anything thinner than the extruder can lay down?
  hole        - is any hole too small to survive?
  overhang    - what needs support, and how much?
  interference- do two parts of the assembly occupy the same space?
  clearance   - do parts that must move actually have room to?

None of this replaces a test print. It replaces the *stupid* test prints.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from build123d import Axis, GeomType, Location, Part, Vector
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepTools import BRepTools

from .profile import DEFAULT, PrinterProfile

# Two solids that merely touch produce a boolean intersection of ~0 volume plus
# numeric noise. Anything under this is contact, not interference.
TOUCH_VOL = 1e-3


@dataclass
class Issue:
    check: str
    severity: str  # "error" | "warn"
    message: str
    where: tuple[float, float, float] | None = None

    def __str__(self) -> str:
        mark = "ERROR" if self.severity == "error" else "warn "
        loc = f"  at ({self.where[0]:.1f}, {self.where[1]:.1f}, {self.where[2]:.1f})" if self.where else ""
        return f"  [{mark}] {self.check}: {self.message}{loc}"


@dataclass
class Report:
    name: str
    issues: list[Issue] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, check, severity, message, where=None):
        self.issues.append(Issue(check, severity, message, where))

    def __str__(self) -> str:
        head = f"{'PASS' if self.ok else 'FAIL'}  {self.name}"
        lines = [head]
        for k, v in self.stats.items():
            lines.append(f"  . {k}: {v}")
        lines += [str(i) for i in self.issues] or ["  . no issues"]
        return "\n".join(lines)


# --- single-part checks -------------------------------------------------------


def check_part(
    part: Part,
    name: str = "part",
    *,
    profile: PrinterProfile = DEFAULT,
    samples: int = 3000,
    check_thickness: bool = True,
) -> Report:
    """Run every printability check on one part, as oriented for printing.

    The part must already be sitting the way it will print: +Z is up, and the
    plate is at Z = min(bounding box). Overhang and bridging results are
    meaningless otherwise.
    """
    rep = Report(f"{name}")
    bb = part.bounding_box()
    rep.stats["size"] = f"{bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm"
    rep.stats["volume"] = f"{part.volume / 1000:.1f} cm3"

    _check_solid(part, rep)
    _check_bounds(part, rep, profile)
    _check_holes(part, rep, profile)
    _check_overhangs(part, rep, profile, samples)
    if check_thickness:
        _check_walls(part, rep, profile, samples)
    return rep


def _check_solid(part: Part, rep: Report) -> None:
    if not part.is_valid:
        rep.add("manifold", "error", "shape is not a valid solid; OCC geometry is broken")
    if not part.is_manifold:
        rep.add("manifold", "error", "shape is not manifold; the slicer will produce garbage")
    solids = part.solids()
    if len(solids) > 1:
        rep.add(
            "manifold",
            "error",
            f"{len(solids)} disconnected solids in one part; they will print as "
            "loose pieces. Split them into separate parts or connect them.",
        )


def _check_bounds(part: Part, rep: Report, profile: PrinterProfile) -> None:
    bb = part.bounding_box()
    bv = profile.build_volume
    for axis, size, limit in zip("XYZ", (bb.size.X, bb.size.Y, bb.size.Z), bv):
        if size > limit:
            rep.add(
                "bounds",
                "error",
                f"{size:.1f}mm on {axis} exceeds the {limit:.0f}mm build volume",
            )


def _holes(part: Part):
    """Every cylindrical face that is actually a hole, as (diameter, centre).

    A cylindrical face is a hole, rather than a peg or a fillet, when it is
    concave (the solid's outward normal points in toward the axis, into the
    void) and sweeps most of the way round. The sweep test is what keeps a
    1mm fillet from being reported as a 2mm hole.
    """
    for face in part.faces().filter_by(GeomType.CYLINDER):
        surf = BRepAdaptor_Surface(face.wrapped)
        cyl = surf.Cylinder()
        radius = cyl.Radius()

        u0, u1, _v0, _v1 = BRepTools.UVBounds_s(face.wrapped)
        if u1 - u0 < math.pi:  # a fillet, not a bore
            continue

        p = face.center()
        ax = cyl.Axis()
        origin = Vector(ax.Location().X(), ax.Location().Y(), ax.Location().Z())
        direction = Vector(ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z())
        offset = p - origin
        radial = offset - direction * offset.dot(direction)
        if radial.length < 1e-9:
            continue
        if face.normal_at(p).dot(radial.normalized()) >= 0:  # convex: a peg
            continue
        yield radius * 2, p


def _check_holes(part: Part, rep: Report, profile: PrinterProfile) -> None:
    """Holes too small to survive the print."""
    seen: set[tuple] = set()
    for dia, c in _holes(part):
        if dia >= profile.min_hole_dia:
            continue
        key = (round(c.X, 1), round(c.Y, 1), round(dia, 2))
        if key in seen:
            continue
        seen.add(key)
        rep.add(
            "hole",
            "warn",
            f"{dia:.2f}mm hole is below the {profile.min_hole_dia}mm minimum; "
            "it may close up, and will need drilling out if it does",
            (c.X, c.Y, c.Z),
        )


def _mesh(part: Part, samples: int):
    """Sample the surface: (point, outward unit normal, area) per triangle.

    The normal comes from `Face.normal_at`, which is orientation-aware, and NOT
    from the triangle winding. Winding is unreliable at trim boundaries — the
    sliver triangles where a bore meets a flat face come back flipped, and a
    flipped normal on a top face reads as a horizontal ceiling that is not there.
    Asking the face itself costs a little and is always right.

    Tolerance is tuned so a part yields roughly `samples` triangles: fine enough
    to catch a thin rib, coarse enough that the ray casting finishes.
    """
    bb = part.bounding_box()
    tol = max(bb.diagonal / 400, 0.05)
    out = []
    for face in part.faces():
        try:
            verts, tris = face.tessellate(tol)
        except Exception:
            continue
        for ia, ib, ic in tris:
            pa, pb, pc = verts[ia], verts[ib], verts[ic]
            area = (pb - pa).cross(pc - pa).length / 2
            if area < 1e-7:
                continue
            centroid = (pa + pb + pc) / 3
            try:
                normal = face.normal_at(centroid)
            except Exception:
                continue
            out.append((centroid, normal, area))

    if len(out) > samples:
        step = len(out) / samples
        out = [out[int(i * step)] for i in range(samples)]
    return out


def _check_overhangs(
    part: Part, rep: Report, profile: PrinterProfile, samples: int
) -> None:
    """Downward-facing surface steeper than the printer can hold up.

    Overhang angle is measured from vertical: a vertical wall is 0 degrees and
    needs nothing, a flat ceiling is 90 degrees and is either a bridge or a pile
    of spaghetti. For an outward unit normal n on a downward face, that angle is
    asin(-n.z).
    """
    if profile.process != "fdm":
        return
    plate = part.bounding_box().min.Z
    bad_area = 0.0
    flat_area = 0.0
    worst: tuple[float, Vector] | None = None

    for centroid, n, area in _mesh(part, samples):
        if n.Z >= 0:
            continue
        # Resting on the plate: supported by definition.
        if centroid.Z - plate < profile.layer_height * 1.5:
            continue
        angle = math.degrees(math.asin(min(1.0, -n.Z)))
        if angle <= profile.max_overhang:
            continue
        bad_area += area
        if angle > 80:
            flat_area += area
        if worst is None or angle > worst[0]:
            worst = (angle, centroid)

    if bad_area <= 0.5:
        rep.stats["overhang"] = "none, prints unsupported"
        return

    rep.stats["overhang"] = f"{bad_area:.0f} mm2 beyond {profile.max_overhang:.0f} deg"
    sev = "warn"
    msg = (
        f"{bad_area:.0f} mm2 of downward surface exceeds {profile.max_overhang:.0f} deg "
        f"(worst {worst[0]:.0f} deg) and needs support"
    )
    if flat_area > 0.5:
        msg += (
            f"; {flat_area:.0f} mm2 of it is near-horizontal ceiling, which is a bridge "
            "or a support scar on a surface you may care about"
        )
    rep.add("overhang", sev, msg, (worst[1].X, worst[1].Y, worst[1].Z))


def _check_walls(
    part: Part,
    rep: Report,
    profile: PrinterProfile,
    samples: int,
    area_floor: float = 2.0,
) -> None:
    """Local wall thickness, measured along the inward normal at surface samples.

    For each sample we intersect the whole infinite line with the solid, sort
    the hits, and take the material span that begins at the sample. Working from
    the true entry and exit rather than from the sample point matters: the sample
    comes from a triangle mesh, and on a concave face (the inside of a bore) the
    mesh chord sits *outside* the material, so stepping "inward" from it and
    taking the first hit measures the sag of the chord, not the wall. That reads
    as 0.00mm on every part with a hole in it.

    Two caveats. It measures along the normal, not the true inscribed distance,
    so a sharp wedge can read thicker than it is; it never reads thicker than
    the wall, which is the safe direction. And a wall is only reported once at
    least `area_floor` mm2 of surface is that thin, which keeps the slivers at a
    chamfer tip from being reported as a structural problem.
    """
    limit = profile.min_wall
    reach = part.bounding_box().diagonal
    grain = max(reach / 400, 0.05)  # the tessellation deviation; hits closer
    snap = grain * 4  # together than this are the same hit

    found: list[tuple[float, float, Vector]] = []  # (thickness, area, where)

    for centroid, n, area in _mesh(part, samples):
        inward = -n
        origin = centroid - inward * reach  # start well clear of the solid
        try:
            hits = part.find_intersection_points(Axis(origin, inward))
        except Exception:
            continue

        ts: list[float] = []
        for p, _hn in hits:
            t = (p - origin).dot(inward)
            if not ts or t - ts[-1] > 1e-6:
                ts.append(t)
        ts.sort()
        # Collapse hits the mesh cannot tell apart, then pair them into the
        # solid spans the line passes through.
        merged: list[float] = []
        for t in ts:
            if merged and t - merged[-1] < 1e-6:
                continue
            merged.append(t)
        if len(merged) < 2 or len(merged) % 2:
            continue  # grazing or tangent: no honest span to measure

        here = reach  # the sample sits at t = reach by construction
        best: tuple[float, float] | None = None  # (distance from sample, span)
        for i in range(0, len(merged), 2):
            entry, exit_ = merged[i], merged[i + 1]
            gap = abs(entry - here)
            if best is None or gap < best[0]:
                best = (gap, exit_ - entry)
        if best is None or best[0] > snap:
            continue  # the span near the sample is not the one we started on

        found.append((best[1], area, centroid))

    if not found:
        rep.stats["min wall"] = "not measured"
        return

    found.sort(key=lambda f: f[0])
    thin = [f for f in found if f[0] < limit]
    thin_area = sum(f[1] for f in thin)

    # The thinnest wall backed by a real amount of surface, not by one sliver.
    running = 0.0
    effective = found[0][0]
    where = found[0][2]
    for t, area, pt in found:
        running += area
        effective, where = t, pt
        if running >= area_floor:
            break

    rep.stats["min wall"] = f"{effective:.2f}mm"
    if effective >= limit:
        return

    sev = "error" if effective < profile.nozzle * 2 else "warn"
    rep.add(
        "wall",
        sev,
        f"thinnest section is {effective:.2f}mm, under the {limit:.1f}mm minimum "
        f"({thin_area:.0f} mm2 of surface is thinner than that). Below "
        f"{profile.nozzle * 2:.1f}mm the slicer drops the wall altogether.",
        (where.X, where.Y, where.Z),
    )


# --- assembly checks ----------------------------------------------------------


def check_interference(
    parts: dict[str, Part], *, tol: float = TOUCH_VOL
) -> Report:
    """Do any two placed parts occupy the same space?

    Parts must already be in their assembled positions. Overlap means the
    assembly is impossible: something has to give, and in the real world it is
    either the plastic or your patience.
    """
    rep = Report("interference")
    names = list(parts)
    rep.stats["pairs"] = len(names) * (len(names) - 1) // 2

    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            try:
                overlap = (parts[a] & parts[b]).volume
            except Exception:
                continue
            if overlap > tol:
                c = (parts[a] & parts[b]).center()
                rep.add(
                    "interference",
                    "error",
                    f"{a} and {b} overlap by {overlap:.2f} mm3",
                    (c.X, c.Y, c.Z),
                )
    return rep


def check_insertion(
    moving: Part,
    fixed: Part,
    direction: tuple[float, float, float],
    distance: float,
    *,
    clearance: float,
    steps: int = 6,
    names: tuple[str, str] = ("part", "assembly"),
) -> Report:
    """Can the part actually be got into place, and does it have room once there?

    `direction` is the way the part travels to come OUT, `distance` how far until
    it is clear. The part is walked back along that path from its seated position,
    and at every step two things are asked.

    **Does it collide?** This catches the part that fits perfectly where it ends up
    but cannot reach there — a bearing behind a lip, a nut in a pocket with no
    mouth. Final-position interference is blind to it, because in the final
    position there is nothing wrong.

    **Can it be nudged sideways by `clearance` and still not collide?** This is the
    one that matters, and it is the reason overlap alone is not enough. A lid cut
    to exactly the size of its cavity has *zero* overlap — it passes every
    interference check ever written — and it will not go in, because a printed lid
    that measures 65.00mm in CAD comes off the bed at 65.15mm. Room is not the
    absence of overlap. Room is being able to move and still not touch.

    Seated contact is fine: the lid rests on its posts, and sliding it sideways
    does not change that. Only lateral collision is reported.
    """
    a, b = names
    rep = Report(f"insertion: {a} into {b}")
    rep.stats["path"] = f"{distance:.0f}mm along {direction}, {steps} steps"
    rep.stats["needs"] = f"{clearance:.2f}mm of side room"

    d = Vector(*direction).normalized()
    # Any two directions across the path. Which two does not matter; what matters
    # is that we push the part around in the plane it has to slide through.
    seed = Vector(0, 0, 1) if abs(d.Z) < 0.9 else Vector(1, 0, 0)
    u = d.cross(seed).normalized()
    v = d.cross(u).normalized()

    blocked: tuple[float, float] | None = None  # (t, overlap)
    tight: tuple[float, float] | None = None  # (t, overlap when nudged)

    for i in range(steps + 1):
        t = distance * i / steps
        along = moving.moved(Location(d * t))
        try:
            overlap = (along & fixed).volume
        except Exception:
            continue
        if overlap > TOUCH_VOL and (blocked is None or overlap > blocked[1]):
            blocked = (t, overlap)

        for lateral in (u, -u, v, -v):
            nudged = moving.moved(Location(d * t + lateral * clearance))
            try:
                ov = (nudged & fixed).volume
            except Exception:
                continue
            if ov > TOUCH_VOL and (tight is None or ov > tight[1]):
                tight = (t, ov)

    if blocked is not None:
        t, overlap = blocked
        rep.add(
            "insertion",
            "error",
            f"{a} collides with {b} by {overlap:.1f} mm3 at {t:.1f}mm along the "
            f"insertion path. It fits where it ends up and cannot get there — "
            f"check for a lip, an undercut, or a boss in the way.",
        )

    if tight is not None:
        t, ov = tight
        where = "seated" if t < 1e-6 else f"{t:.1f}mm along the path"
        rep.add(
            "insertion",
            "error",
            f"{a} has less than {clearance:.2f}mm of side room in {b} ({where}): "
            f"nudging it sideways by that much drives {ov:.1f} mm3 into the other "
            f"part. Zero overlap is not a fit — a printed part comes off the bed "
            f"oversized, and with no room it does not go in.",
        )

    if rep.ok:
        rep.stats["result"] = "goes in, and has room"
    return rep


def check_clearance(
    parts: dict[str, Part],
    pairs: list[tuple[str, str, float]],
) -> Report:
    """Do parts that must move relative to each other have room?

    `pairs` is (part_a, part_b, min_gap_mm). Use it for anything that rotates,
    slides, or is meant to be removable without a hammer.
    """
    rep = Report("clearance")
    for a, b, want in pairs:
        got = parts[a].distance_to(parts[b])
        if got < want:
            rep.add(
                "clearance",
                "error",
                f"{a} to {b} is {got:.2f}mm, needs {want:.2f}mm to move freely",
            )
        else:
            rep.stats[f"{a}~{b}"] = f"{got:.2f}mm (want {want:.2f})"
    return rep
