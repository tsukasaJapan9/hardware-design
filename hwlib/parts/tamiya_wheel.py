"""タミヤ No.145 ナロータイヤ（Item 70145、58mm 径）の実形状モデル。

出所: タミヤ 70145 組立説明図（0900 ©2000 TAMIYA）の寸法図。

座標系（このモデルの約束）:
  - 原点 = 車輪の回転軸中心（軸は Z 方向）
  - +Z = ハブ取付面（変換ハブが当たる内側）の向き
  - タイヤはこの原点を中心に、幅方向（Z）に広がる

図面から確定した datum:
  - タイヤ外径 58 mm、タイヤ幅 16 mm
  - リム（樹脂ホイール）外径 42 mm
  - ハブ取付穴 = 3 穴、PCD 20 mm（図面「10mm」= 軸中心から穴中心までの半径）
  - 3x8mm タッピングビスでハブ（または変換ハブ）を留める

方式上の決定（ユーザー確定）:
  - 中央ボアは使わない。芯出しは 3 穴（PCD20）＋外径スピゴットで行うため、
    中央ボア径・座ぐり深さは設計に不要（実測しない）

未確定（provisional・実測が必要な場合のみ）:
  - リム内側の座ぐり形状の細部（本モデルでは平面近似）
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Align, Cylinder, Part, Pos

# 図面確定値 [mm]
TIRE_OD = 58.0
TIRE_WIDTH = 16.0
RIM_OD = 42.0
BOLT_PCD = 20.0          # ハブ取付穴のピッチ円直径（図面 10mm 半径 x2）
BOLT_COUNT = 3
BOLT_HOLE_DIA = 3.0      # 3x8 タッピングビスの通る穴（概略）


@dataclass(frozen=True)
class TamiyaWheel:
    """タミヤ 70145 ホイールの基準寸法と特徴点。原点は回転軸中心。"""

    def bolt_positions(self, start_deg: float = 90.0) -> list[tuple[float, float]]:
        """ハブ取付穴の中心 (x, y)。PCD20 上に3点等配。"""
        r = BOLT_PCD / 2
        return [
            (r * math.cos(math.radians(start_deg + 360 * i / BOLT_COUNT)),
             r * math.sin(math.radians(start_deg + 360 * i / BOLT_COUNT)))
            for i in range(BOLT_COUNT)
        ]


def body(*, inner_face_z: float = 0.0) -> Part:
    """ホイール（タイヤ＋リム）の外形。原点＝回転軸中心。

    inner_face_z にハブ取付面（内側）を置き、そこから +Z 側（サーボと反対の外側）へ
    幅ぶん広がる。実機では、サーボ → 変換ハブ → ホイールの順に軸方向へ並ぶため、
    ホイールはハブより外側（+Z）に来る。
    タイヤは中実ゴムのため外形の円柱で近似する（走行接地の確認に十分）。
    """
    p = TamiyaWheel()

    # タイヤ本体（中実円柱）。内側面を inner_face_z に、外側（+Z）へ幅ぶん伸ばす
    wheel = Pos(0, 0, inner_face_z) * Cylinder(
        TIRE_OD / 2, TIRE_WIDTH, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )

    # ハブ取付穴（内側面から +Z 側へ浅く。3x8 ビス位置の目印・干渉確認用）
    for x, y in p.bolt_positions():
        wheel -= Pos(x, y, inner_face_z - 0.5) * Cylinder(
            BOLT_HOLE_DIA / 2, 8.0, align=(Align.CENTER, Align.CENTER, Align.MIN)
        )
    return wheel


def rim_recess_diameter() -> float:
    """変換ハブの外径スピゴットが嵌る、リム内側の基準径。

    リム外径 42mm を基準にする。実際の座ぐり径はこれ以下で、変換ハブ側の
    adapter_od はこれより小さく取る（スピゴットすきま分）。
    """
    return RIM_OD
