# build123d, the parts that will bite you

Verified against **build123d 0.11.1**. Every item here is something that failed
first and was fixed after, not something copied from a tutorial. Read it before
writing build123d code; each entry is worth roughly an hour.

## Properties that look like methods

```python
part.is_valid       # property. part.is_valid() raises TypeError: 'bool' object is not callable
part.is_manifold    # property
part.volume         # property
part.area           # property
face.center()       # method. Not symmetric with the above, sorry.
```

## `.move()` returns a new object

Inside a builder, this silently does nothing:

```python
with BuildPart() as p:
    Cylinder(2, 10).move(Pos(0, 0, -5))   # WRONG: the cylinder is added unmoved,
                                          # and the moved copy is thrown away
```

`Cylinder(...)` registers itself with the builder at construction. `.move()` hands
back a *different* object that nobody is holding. Place things with `Locations`
instead, or build the solid context-free and add it:

```python
with BuildPart() as p:
    with Locations((0, 0, -5)):
        Cylinder(2, 10)
```

## Sketch objects do not work inside `BuildPart`

```python
with BuildPart() as p:
    RegularPolygon(3, 6)   # RuntimeError: RegularPolygon applies to ['BuildSketch']
```

Either nest a `BuildSketch` and `extrude`, or build the solid from topology
directly, which is what the pockets in `hwkit/fasteners.py` do:

```python
from build123d import Face, Solid, Wire, Vector
pts = [Vector(...), ...]
solid = Solid.extrude(Face(Wire.make_polygon(pts, close=True)), (0, 0, -depth))
```

## Context-free geometry

Anything that must be built while a builder is active (inside a custom part
object, for instance) has to avoid the builder-aware classes. Use topology:

```python
Solid.make_cylinder(radius, height, Plane(origin=(0, 0, 0), z_dir=(0, 0, -1)))  # hangs DOWN
Solid.make_cone(r_bottom, r_top, height, plane)
Solid.make_box(dx, dy, dz, plane)
Solid.extrude(face, direction_vector)
a.fuse(b).clean()   # boolean union; .clean() merges the coplanar faces
```

## Custom part objects: subclass `BasePartObject`

This is how you get `Locations` and `Mode` support for free, and it is how
build123d's own `Hole` is written:

```python
class InsertBoss(BasePartObject):
    _applies_to = [BuildPart._tag]

    def __init__(self, screw, *, depth=None, mode=Mode.SUBTRACT):
        solid = _drill(screw.insert_hole / 2, depth)   # context-free
        super().__init__(part=solid, align=None, mode=mode)
```

`align=None` leaves the solid where you built it — which is what you want for a
pocket that must drill DOWN from its location. `align=(CENTER, CENTER, CENTER)`
would re-centre it on the location and the pocket would stick out the top too.

**Do not name an attribute `depth`, `radius`, `area`, or `volume`.** They collide
with read-only `Shape` properties and you get
`AttributeError: property 'depth' of 'InsertBoss' object has no setter`.

## Cutting from a face

```python
with Locations(Plane(top_face)):        # a plane ON the face, +Z out of it
    with Locations((-10, 0), (10, 0)):  # face-local XY
        CounterBore(M3, depth=6)
```

`Plane(face)` is fragile if the face selection is fragile. When the geometry is
known, `Plane.XY.offset(5)` is deterministic and cannot pick the wrong face.
Selecting with `.sort_by(Axis.Z)[-1]` breaks the moment you add a taller feature.

## `find_intersection_points` is an infinite line, not a ray

```python
hits = part.find_intersection_points(Axis(origin, direction))
# -> [(point, normal), ...] — INCLUDING points behind the origin
```

Filter forward hits yourself:

```python
ts = [(p - origin).dot(direction) for p, _n in hits if (p - origin).dot(direction) > 0]
```

## Mesh winding is not reliable; face normals are

`part.tessellate(tol)` returns triangles whose winding is *mostly* outward, but
the sliver triangles at a trim boundary — where a bore meets a flat face — come
back flipped. A flipped normal on a top face reads as a horizontal ceiling that
does not exist, and your overhang check invents support that nothing needs.

Take the normal from the face, which is orientation-aware and always right:

```python
for face in part.faces():
    verts, tris = face.tessellate(tol)
    for ia, ib, ic in tris:
        centroid = (verts[ia] + verts[ib] + verts[ic]) / 3
        normal = face.normal_at(centroid)   # trust this
```

## Mesh points on a concave face lie *outside* the solid

A triangle is a chord. On a convex surface the chord sits inside the material; on
a concave one — the inside of a bore — it sits in the void. Any algorithm that
steps "just inside" from a mesh point and takes the first hit will measure the sag
of the chord, about 0.00mm, on every part that has a hole in it.

Work from true entry and exit instead: intersect the whole line, sort the hits,
pair them into solid spans, and take the span that starts at your sample.
`hwkit/validate.py::_check_walls` does this.

## `Face.radius` can be `None`

And a fillet is a cylindrical face too, so a naive "small cylinder = small hole"
check reports every 0.8mm fillet as a 1.6mm hole. Get the radius from the
adaptor, and tell a hole from a fillet by *concavity* (the outward normal points
in toward the axis) and *sweep* (a bore goes most of the way round; a fillet
turns 90°):

```python
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepTools import BRepTools

surf = BRepAdaptor_Surface(face.wrapped)
radius = surf.Cylinder().Radius()
u0, u1, _, _ = BRepTools.UVBounds_s(face.wrapped)
if u1 - u0 < math.pi:
    continue          # a fillet, not a bore
```

## Joints

```python
RigidJoint("foot", part, Location((0, 0, 0)))
RevoluteJoint("spin", part, axis=Axis.Z)
a.joints["shaft_axis"].connect_to(b.joints["spin"], angle=0)
```

`connect_to` **mutates the child**: it moves `b` to meet `a`. So after mating,
the part object is in the assembly frame, not the frame you authored it in. If
you need the original — and you do, for print orientation and STL export — take a
snapshot first. There is no `Shape.copy()`; use `copy.deepcopy(part)`, which
preserves joints and is properly independent.

## Booleans and distance

```python
overlap = (a & b).volume     # > ~1e-3 means real interference, not just contact
gap     = a.distance_to(b)   # minimum distance between two shapes
```

## Export

```python
export_stl(part, "part.stl")     # mesh, for the slicer
export_step(compound, "asm.step")  # exact geometry, for other CAD
import_step(path); import_stl(path)
```

An STL carries no units and no orientation; sit the part on Z=0 yourself and say
so on the BOM, or somebody will rotate it in the slicer and print your bearing
seat as an overhang.
