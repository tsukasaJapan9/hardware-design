"""DYNAMIXEL XL330-M077-T / M288-T の実形状モデル。

出所: ROBOTIS 公式図面 X330（28-May-20, [FOR REFERENCE ONLY]）と e-manual。
M077 と M288 はケース・ホーン・取付穴が共通。

座標系（このモデルの約束）:
  - 原点 = 出力軸の中心（軸は Z 方向）
  - +Z = 出力ホーンが出る向き（相手部品を取り付ける側）
  - +X = ケース幅（W=20）方向、+Y = ケース高さ（H=34）方向

図面から確定した datum:
  - ケース外形 W20 x H34 x D26 mm
  - 出力軸は W 方向は中央、H 方向は「ホーン側から見た上端」から 9.5 mm
  - ホーン穴 = 4 x φ1.6、P.C.D φ12、90度等配、M2 タッピング（深さ最大 3.0）
  - ケース背面(IDLER)側の取付穴も 4 x φ1.6、P.C.D φ12

未確定（provisional・STEP か実測で詰める）:
  - 奥行き(D=26)方向での軸位置。前面図に現れないため暫定で D 中央付近に置く
  - ホーンの突起（ボス）形状の細部
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Align, Box, Cylinder, Part, Pos

# 図面確定値 [mm]
CASE_W = 20.0
CASE_H = 34.0
CASE_D = 26.0
AXIS_FROM_TOP = 9.5      # 出力軸中心の、ケース上端（ホーン側頂）からの距離
HORN_PCD = 12.0          # ホーン穴のピッチ円直径
HORN_HOLE_DIA = 1.6      # ホーン穴の径（M2 タッピング下穴）
HORN_SCREW = "M2"

# 未確定（provisional）
AXIS_FROM_FRONT = 13.0   # 奥行き方向の軸位置（暫定: D 中央）。STEP/実測で確定する


@dataclass(frozen=True)
class XL330:
    """XL330 の基準寸法と特徴点。原点は出力軸中心。"""

    # ケース最小コーナーの、軸原点からのオフセット。
    # X: 軸は W 中央 → -W/2。Y: 軸は上端から 9.5 → 上端が +9.5、最小コーナーは +9.5-H。
    @property
    def case_min_corner(self) -> tuple[float, float, float]:
        return (-CASE_W / 2, AXIS_FROM_TOP - CASE_H, -AXIS_FROM_FRONT)

    def horn_hole_positions(self, count: int = 4, start_deg: float = 45.0) -> list[tuple[float, float]]:
        """ホーン穴の中心 (x, y)。原点＝軸中心を中心に P.C.D φ12 の円周上。"""
        r = HORN_PCD / 2
        return [
            (r * math.cos(math.radians(start_deg + 360 * i / count)),
             r * math.sin(math.radians(start_deg + 360 * i / count)))
            for i in range(count)
        ]


HORN_BOSS_DIA = HORN_PCD + 4.0   # ホーン外径の概略（φ12 穴円 + 縁）。細部は provisional
HORN_BOSS_H = 2.0                 # ホーンがケース前面から出る高さ（概略）


def body(*, with_horn_holes: bool = True) -> Part:
    """XL330 の外形ソリッド（実形状の近似）。原点＝出力軸中心。

    ケースを図面 datum の位置に置くことで、軸まわりの相手部品を正しく設計できる。
    ホーンの頂面を Z=0（軸原点の高さ）に合わせ、ケースはその -Z 側に伸ばす。
    配線コネクタなどの細部は干渉確認に不要なため省く。
    """
    p = XL330()
    cx, cy, _ = p.case_min_corner

    # ケース: ホーン頂 Z=0 の下（-Z 側）に奥行き D ぶん伸ばす
    case = Pos(cx, cy, -HORN_BOSS_H - CASE_D) * Box(
        CASE_W, CASE_H, CASE_D, align=(Align.MIN, Align.MIN, Align.MIN)
    )
    # ホーンの突起（相手部品が当たる面）。頂面が Z=0
    case += Pos(0, 0, -HORN_BOSS_H) * Cylinder(
        HORN_BOSS_DIA / 2, HORN_BOSS_H, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )

    if with_horn_holes:
        for x, y in p.horn_hole_positions():
            case -= Pos(x, y, -HORN_BOSS_H - 0.5) * Cylinder(
                HORN_HOLE_DIA / 2, 3.0, align=(Align.CENTER, Align.CENTER, Align.MIN)
            )
    return case


def output_axis() -> tuple[float, float, float]:
    """出力軸の位置（このモデルでは原点）。"""
    return (0.0, 0.0, 0.0)
