# build123d の書き方

バージョン 0.11.x。単位は mm。

## 2 つの書き方

**Algebra モード**（本リポジトリの標準）— 演算子で組み立てる。関数として書けるため検証しやすい。

```python
from build123d import *

part = Box(40, 30, 10)
part -= Pos(10, 0, 0) * Cylinder(radius=3, height=20)   # 減算
part += Pos(0, 0, 10) * Box(10, 10, 5)                  # 加算
part &= Box(35, 35, 35)                                  # 積
```

**Builder モード** — `with` で文脈を作る。複雑なスケッチや選択操作に向く。

```python
with BuildPart() as bp:
    Box(40, 30, 10)
    with Locations((10, 0, 0)):
        Cylinder(radius=3, height=20, mode=Mode.SUBTRACT)
part = bp.part
```

混在させない。1 ファイル内ではどちらかに統一する。

## 配置

```python
Pos(10, 20, 0) * shape                       # 平行移動
Rot(0, 0, 45) * shape                        # 回転（度）
Plane(origin=(0,0,10), z_dir=(0,0,1)) * shape  # 平面に載せる
```

`Plane` に `z_dir` だけを渡すと x 軸の向きが定まらない。開口など向きが重要な場合は
`x_dir` も明示するか、`hwlib.verify.face_plane()` を使う。

## 基本形状

```python
Box(w, d, h, align=(Align.MIN, Align.MIN, Align.MIN))   # 原点を最小コーナーに
Cylinder(radius=r, height=h, align=(Align.CENTER, Align.CENTER, Align.MIN))
Sphere(radius=r)
Cone(bottom_radius=a, top_radius=b, height=h)
```

`align` の既定は中心。**部品配置では `Align.MIN` を使うと BOM のローカル座標と一致して扱いやすい。**

## 選択と加工

```python
part.faces().sort_by(Axis.Z)[-1]              # 一番上の面
part.edges().filter_by(GeomType.CIRCLE)       # 円形のエッジ
part.edges().group_by(Axis.Z)[0]              # 最下段のエッジ群

part = fillet(part.edges().filter_by(Axis.Z), radius=2)
part = chamfer(part.edges(), length=0.5)
```

フィレットは印刷時の応力集中を減らすが、内側の隅（壁と床の交線）に入れると
オーバーハングが増える。外側の角に入れる。

## 測る

```python
part.volume                    # 体積
part.bounding_box()            # .min / .max / .size (Vector)
part.is_valid                  # プロパティ。メソッドではない
len(part.faces())              # 面の数
a.distance_to(b)               # 最短距離
(a & b).volume                 # 重なりの体積。干渉していなければ 0
```

## 出力

```python
export_stl(part, "out/part.stl", tolerance=0.02)   # 3D プリント用
export_step(part, "out/part.step")                  # 他の CAD との交換用
```

`tolerance` はメッシュの粗さ。小さいほど滑らかで重い。0.02 前後で十分。

## ネジ・ナットの形状

`bd_warehouse` を使う。自作しない。

```python
from bd_warehouse.fastener import PanHeadScrew, HexNut
```

ただし本リポジトリの締結は**タッピングネジ（樹脂直締め）**が標準で、
下穴とボスは `hwlib.features.tapping_boss()` で作る。ネジ自体の形状は通常必要ない。

## 見る

```python
from hwlib.render import render, show

render({"base": base, "lid": lid}, "out/assembly.png", opacity={"base": 0.35})  # PNG（Claude が確認）
show({"base": base, "lid": lid})                                                 # ocp_vscode（人間が確認）
```
