"""頻出フィーチャの生成。

締結はタッピングネジ（樹脂直締め）を前提とする。
下穴径・ボス外径・ねじ込み深さの関係は SCREWS の値で保証する。
ネジ・ナットそのものの形状が必要な場合は bd_warehouse を使う。
"""

from __future__ import annotations

from dataclasses import dataclass

from build123d import Align, Box, Cylinder, Part, Pos


@dataclass(frozen=True)
class TappingScrew:
    """樹脂に直接ねじ込むタッピングネジの寸法。

    pilot_dia: 下穴径。呼び径の 0.8 倍前後。太いとネジが効かず、細いとボスが割れる。
    boss_outer_dia: ボス外径。肉厚を確保するため呼び径の約 2.2 倍。
    min_engagement: 必要なねじ込み深さ。呼び径の 2 倍以上。
    clearance_dia: 反対側の板を通すバカ穴径。
    head_dia: ネジ頭の直径。座ぐりや工具の逃げに使う。
    """

    nominal: float
    pilot_dia: float
    boss_outer_dia: float
    min_engagement: float
    clearance_dia: float
    head_dia: float


# FDM 樹脂（PLA / PETG）でのタッピングを想定した実用値。
# 実機で締めてみて割れる・効かない場合は pilot_dia を 0.1 mm 単位で調整する。
SCREWS: dict[str, TappingScrew] = {
    "M2": TappingScrew(2.0, 1.6, 4.4, 4.0, 2.4, 3.8),
    "M2.6": TappingScrew(2.6, 2.1, 5.7, 5.2, 3.0, 4.8),
    "M3": TappingScrew(3.0, 2.4, 6.6, 6.0, 3.4, 5.6),
    "M4": TappingScrew(4.0, 3.2, 8.8, 8.0, 4.5, 7.4),
}


def tapping_boss(screw: str, height: float, *, depth: float | None = None) -> Part:
    """タッピングネジ用のボス（円柱＋下穴）。

    原点はボスの底面中心。height はボスの高さ、depth は下穴の深さ。
    depth を省略すると必要なねじ込み深さを確保する。
    """
    s = SCREWS[screw]
    depth = depth if depth is not None else min(height, s.min_engagement + 1.0)
    if depth > height:
        raise ValueError(f"下穴の深さ {depth} がボス高さ {height} を超えています")

    boss = Cylinder(
        radius=s.boss_outer_dia / 2, height=height, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    # 下穴は上面から掘る
    pilot = Pos(0, 0, height - depth) * Cylinder(
        radius=s.pilot_dia / 2, height=depth, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    return boss - pilot


def clearance_hole(screw: str, thickness: float) -> Part:
    """ネジを通すバカ穴（切り欠く側の形状）。原点は穴の底面中心。"""
    s = SCREWS[screw]
    return Cylinder(
        radius=s.clearance_dia / 2, height=thickness, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )


def rect_opening(
    center: tuple[float, float, float],
    face: str,
    size: tuple[float, float],
    wall_thickness: float,
    *,
    margin: float = 0.5,
) -> Part:
    """コネクタ用の角穴（切り欠く側の形状）。

    face は開口が向く外向き方向（"+x" など）。margin は挿抜のための余裕。
    壁を確実に貫通させるため、厚み方向に余分を持たせる。
    """
    from hwlib.verify import FACE_DIR, face_plane

    w, h = size
    depth = wall_thickness + 4.0  # 壁を確実に貫く
    d = FACE_DIR[face]
    # 壁の内側から外側へ貫通させるため、開始点を内側にずらす
    origin = tuple(c - n * 2.0 for c, n in zip(center, d))
    return face_plane(origin, face) * Box(
        w + 2 * margin, h + 2 * margin, depth, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
