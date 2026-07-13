# build123d の落とし穴

**build123d 0.11.1** で確認済み。どの項目もチュートリアルの写しではなく、実際に踏んで
直した記録。コードを書く前に読めば、1件につき1時間程度を節約できる。

## メソッドに見えるプロパティ

```python
part.is_valid       # プロパティ。part.is_valid() は TypeError: 'bool' object is not callable
part.is_manifold    # プロパティ
part.volume         # プロパティ
part.area           # プロパティ
face.center()       # こちらはメソッド。対称性はない
```

## `.move()` は新しいオブジェクトを返す

ビルダー内では何も起きない:

```python
with BuildPart() as p:
    Cylinder(2, 10).move(Pos(0, 0, -5))   # 誤り。円柱は元の位置で追加され、
                                          # 動かしたコピーは捨てられる
```

`Cylinder(...)` は生成の時点でビルダーに登録される。`.move()` が返すのは**別の**オブジェクト
で、誰も保持していない。配置は `Locations` で行うか、ビルダー外で形状を組んでから追加する:

```python
with BuildPart() as p:
    with Locations((0, 0, -5)):
        Cylinder(2, 10)
```

## スケッチ用オブジェクトは `BuildPart` 内で使えない

```python
with BuildPart() as p:
    RegularPolygon(3, 6)   # RuntimeError: RegularPolygon applies to ['BuildSketch']
```

`BuildSketch` を入れ子にして `extrude` するか、トポロジー API で直接形状を組む。
`hwkit/fasteners.py` のポケット類は後者:

```python
from build123d import Face, Solid, Wire, Vector
pts = [Vector(...), ...]
solid = Solid.extrude(Face(Wire.make_polygon(pts, close=True)), (0, 0, -depth))
```

## ビルダーに依存しない形状生成

ビルダーが有効な場所で形状を組む必要があるとき（自作部品オブジェクトの内部など）は、
ビルダー連動のクラスを避けてトポロジー API を使う:

```python
Solid.make_cylinder(radius, height, Plane(origin=(0, 0, 0), z_dir=(0, 0, -1)))  # 下向きに伸びる
Solid.make_cone(r_bottom, r_top, height, plane)
Solid.make_box(dx, dy, dz, plane)
Solid.extrude(face, direction_vector)
a.fuse(b).clean()   # 和集合。.clean() が同一平面の面を統合する
```

## 自作部品は `BasePartObject` を継承

`Locations` と `Mode` への対応が継承だけで手に入る。build123d 本体の `Hole` も同じ作り:

```python
class InsertBoss(BasePartObject):
    _applies_to = [BuildPart._tag]

    def __init__(self, screw, *, depth=None, mode=Mode.SUBTRACT):
        solid = _drill(screw.insert_hole / 2, depth)   # ビルダー非依存で生成
        super().__init__(part=solid, align=None, mode=mode)
```

`align=None` は形状を組んだ位置のまま使う指定。配置位置から下向きに掘るポケットには
これが必要。`align=(CENTER, CENTER, CENTER)` にすると配置位置を中心に再配置され、
ポケットが上にも突き出る。

**属性名に `depth`、`radius`、`area`、`volume` を使わない。** `Shape` の読み取り専用
プロパティと衝突して
`AttributeError: property 'depth' of 'InsertBoss' object has no setter` になる。

## 面からの掘り込み

```python
with Locations(Plane(top_face)):        # 面上の平面。+Z は面の外向き
    with Locations((-10, 0), (10, 0)):  # 面ローカルの XY
        CounterBore(M3, depth=6)
```

`Plane(face)` の信頼性は面選択の信頼性と同じ。座標が分かっているなら
`Plane.XY.offset(5)` が決定的で、面を取り違えない。`.sort_by(Axis.Z)[-1]` による選択は、
より高い形状を追加した瞬間に壊れる。

## `find_intersection_points` は半直線ではなく直線

```python
hits = part.find_intersection_points(Axis(origin, direction))
# -> [(point, normal), ...]  原点より後ろの交点も含む
```

前方の交点は自分で選別する:

```python
ts = [(p - origin).dot(direction) for p, _n in hits if (p - origin).dot(direction) > 0]
```

## 三角形の巻き方向は信用できない。面の法線を使う

`part.tessellate(tol)` が返す三角形の巻き方向はおおむね外向きだが、トリム境界 — 穴が平面と
交わる場所 — の細長い三角形は反転して返ることがある。天面で法線（normal）が1つ反転すると、
存在しない水平天井として読まれ、オーバーハングチェックが不要なサポートを要求する。

法線は面から取る。面は向きを保持しており、常に正しい:

```python
for face in part.faces():
    verts, tris = face.tessellate(tol)
    for ia, ib, ic in tris:
        centroid = (verts[ia] + verts[ib] + verts[ic]) / 3
        normal = face.normal_at(centroid)   # こちらを信用する
```

## 凹面のメッシュ点は実体の外側にある

三角形は弦。凸面では弦は材料の内側に沈むが、凹面 — 穴の内壁 — では空洞側に浮く。メッシュ点
から「少し内側」へ進んで最初の交点までを測る方式は、弦のたわみ（約 0.00mm）を肉厚として
返す。穴のある部品すべてで起きる。

正しくは、直線全体との交点を求めてソートし、実体区間のペアに組み、サンプル点から始まる
区間を採用する。実装は `hwkit/validate.py::_check_walls`。

## `Face.radius` は `None` になりうる

さらに、フィレットも円筒面。「小さい円筒面 = 小さい穴」と判定すると、0.8mm のフィレットが
φ1.6 の穴として報告される。半径はアダプタから取り、穴とフィレットは**凹性**（外向き法線が
軸を向く）と**巻き角**（穴はほぼ一周、フィレットは 90° 程度）で見分ける:

```python
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepTools import BRepTools

surf = BRepAdaptor_Surface(face.wrapped)
radius = surf.Cylinder().Radius()
u0, u1, _, _ = BRepTools.UVBounds_s(face.wrapped)
if u1 - u0 < math.pi:
    continue          # フィレット。穴ではない
```

## Joint

```python
RigidJoint("foot", part, Location((0, 0, 0)))
RevoluteJoint("spin", part, axis=Axis.Z)
a.joints["shaft_axis"].connect_to(b.joints["spin"], angle=0)
```

`connect_to` は**子を動かす**。`b` が `a` に合わせて移動するので、接続後の部品は組立座標系に
あり、設計時の座標系には無い。元の姿勢が必要なら — 印刷姿勢の決定と STL 出力で必ず必要に
なる — 先にスナップショットを取る。`Shape.copy()` は存在しないので `copy.deepcopy(part)`。
Joint も保持され、完全に独立したコピーになる。

## ブール演算と距離

```python
overlap = (a & b).volume     # 1e-3 以上なら干渉。それ未満は接触
gap     = a.distance_to(b)   # 2形状間の最短距離
```

## 出力

```python
export_stl(part, "part.stl")       # メッシュ。スライサー用
export_step(compound, "asm.step")  # 厳密形状。他の CAD 用
import_step(path); import_stl(path)
```

STL は単位も姿勢も持たない。Z=0 に置いた状態で出力し、部品表に「回転させない」と明記する。
さもないと誰かがスライサーで回し、ベアリング座がオーバーハングとして刷られる。
