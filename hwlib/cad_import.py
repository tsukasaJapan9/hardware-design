"""公式 CAD（STEP / メッシュ）を部品の実形状として読み込む。

部品を直方体で近似すると、回転軸やネジ穴が実物とずれる（例: サーボの出力軸は
ケース中心ではない）。公式 STEP を読み込めば、軸・穴の位置を実物どおりに扱える。

使い方の流れ:
  1. load_step() で STEP を Solid として読む
  2. describe() で外形・円筒面（＝穴や軸）を一覧し、どれが基準かを特定する
  3. find_holes() で特定の半径・向きの穴の中心座標を取り出す
  4. 取り出した座標を基準に、相手部品（マウント・ハブ）を設計する
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from build123d import Axis, GeomType, Plane, Pos, Solid, Vector, import_step


def load_step(path: str | Path) -> Solid:
    """STEP を Solid として読み込む。

    build123d の import_step は Solid を返すため、そのまま干渉計算やブール演算に使える。
    """
    solid = import_step(str(path))
    if isinstance(solid, (list, tuple)):
        solid = solid[0]
    return solid


@dataclass
class Hole:
    """円筒面から検出した穴（またはボス/軸）。"""

    center: tuple[float, float, float]  # 円筒軸上の中点
    axis: tuple[float, float, float]    # 円筒の軸方向（単位ベクトル）
    radius: float

    @property
    def xy(self) -> tuple[float, float]:
        return (round(self.center[0], 3), round(self.center[1], 3))


def _cylinder_radius(face) -> float | None:
    """円筒面の半径。面の円形エッジから取る。"""
    for e in face.edges():
        if e.geom_type == GeomType.CIRCLE:
            try:
                return float(e.radius)
            except Exception:  # noqa: BLE001
                continue
    return None


def cylinders(solid: Solid) -> list[Hole]:
    """Solid 中のすべての円筒面を穴候補として列挙する。"""
    found: list[Hole] = []
    for f in solid.faces():
        if f.geom_type != GeomType.CYLINDER:
            continue
        r = _cylinder_radius(f)
        if r is None:
            continue
        c = f.center()
        try:
            n = f.normal_at()
        except Exception:  # noqa: BLE001
            n = Vector(0, 0, 1)
        found.append(
            Hole(center=(c.X, c.Y, c.Z), axis=(n.X, n.Y, n.Z), radius=r)
        )
    return found


def find_holes(
    solid: Solid,
    *,
    radius: float | None = None,
    radius_tol: float = 0.3,
    axis: str | None = None,
) -> list[Hole]:
    """条件に合う穴を絞り込む。

    radius — 呼びたい穴半径（例: M2 バカ穴なら約 1.1）。radius_tol 以内を拾う
    axis   — 穴の向き "x"/"y"/"z"（軸がこの方向に平行なものだけ）
    """
    holes = cylinders(solid)
    if radius is not None:
        holes = [h for h in holes if abs(h.radius - radius) <= radius_tol]
    if axis is not None:
        idx = {"x": 0, "y": 1, "z": 2}[axis]
        holes = [h for h in holes if abs(abs(h.axis[idx]) - 1.0) < 1e-3]
    return holes


def describe(solid: Solid) -> str:
    """STEP の中身を把握するための診断。外形と円筒面を一覧する。

    どの円筒が出力軸か、どれがネジ穴かを人が特定するために使う。
    """
    bb = solid.bounding_box()
    lines = [
        f"体積: {solid.volume:.1f} mm^3",
        f"外形 (X,Y,Z): "
        f"{bb.size.X:.2f} x {bb.size.Y:.2f} x {bb.size.Z:.2f} mm",
        f"範囲 min: ({bb.min.X:.2f}, {bb.min.Y:.2f}, {bb.min.Z:.2f})  "
        f"max: ({bb.max.X:.2f}, {bb.max.Y:.2f}, {bb.max.Z:.2f})",
        "円筒面（穴・軸の候補）:",
    ]
    cyls = sorted(cylinders(solid), key=lambda h: h.radius)
    for h in cyls:
        cx, cy, cz = h.center
        ax, ay, az = h.axis
        lines.append(
            f"  r={h.radius:6.3f}  center=({cx:7.2f},{cy:7.2f},{cz:7.2f})  "
            f"axis=({ax:+.2f},{ay:+.2f},{az:+.2f})"
        )
    lines.append(f"円筒面の総数: {len(cyls)}")
    return "\n".join(lines)


def recenter_xy(solid: Solid, center_xy: tuple[float, float]) -> Solid:
    """指定した XY 点（例: 出力軸）が原点に来るよう平行移動する。

    直方体近似では軸が中心だったが、実物の軸位置を原点に合わせることで、
    相手部品（ハブなど）を軸基準で設計できる。
    """
    return Pos(-center_xy[0], -center_xy[1], 0) * solid
