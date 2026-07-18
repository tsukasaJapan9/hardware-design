"""タミヤ No.145 ナロータイヤ（Item 70145、58mm 径）の実形状モデル。

出所: タミヤ 70145 組立説明図（0900 ©2000 TAMIYA）。
図面の現物: datasheets/tamiya_70145/70145.pdf（読み取れる寸法は datasheets/README.md）

座標系（このモデルの約束）:
  - 原点 = 車輪の回転軸中心（軸は Z 方向）
  - +Z = ホイール幅方向。inner_face_z にハブ側フランジ端面を置く

部品構成（組立説明図 1 より）:
  - B3 = 樹脂ホイール（外径 42、スプール状）+ ゴムタイヤ（外径 58）の 2 部品
  - B1（六角シャフト用）/ B2（丸シャフト用）= 三角形のハブ。本設計の変換ハブが置き換える
  - B4 = 3mm ナット（丸シャフト用。本設計では使わない）

ホイールの形状（組立図の B3 立体図より）:
  **両面対称のスプール（糸巻き）形状**。平らな円板ではない。
  外周は両端のフランジ（外径 42）とその間の溝で、溝にタイヤが嵌る。
  ウェブ（板）は幅方向の中央にあり、両面が同じ深さのポケットになっている。
  したがってホイールはどちら向きにも取り付けられる。

純正ハブ B1/B2 の芯出し方式（立体図より）:
  1. B1/B2 の中央ボスが、ウェブ中央の**中心ボア**に嵌る（これが芯出しの主体）
  2. B1/B2 の面から出た**位置決めピン 3 本**が、ウェブの小穴 3 個に入る（回り止め）
  3. 3x8 タッピングビス 3 本が、ウェブの大穴 3 個を貫通してハブにねじ込まれる
  ウェブの穴は計 6 個（大3・小3）が PCD20 上に 60 度ごとに交互に並ぶ。

締結方向: ビスはハブと反対の面から入り、ウェブを貫通してハブにねじ込む。
ウェブ側の穴はバカ穴で、ねじ山が立つのはハブ側だけ。

実測で確定（2026-07-19）:
  WHEEL_WIDTH 11.0 / WEB_THICKNESS 2.0 / POCKET_DIA 38.0 /
  CENTER_BORE_DIA 8.5 / PIN_HOLE_DIA 1.5

未確定（provisional・実測が必要）:
  - PIN_HOLE_START_DEG  ビス穴に対するピン穴の位相（60 度ずれと仮定）。
    位置決めピンを使う設計にする場合のみ必要
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Align, Cylinder, Part, Pos

# 図面確定値 [mm]
TIRE_OD = 58.0
TIRE_WIDTH = 16.0
FLANGE_OD = 42.0         # 樹脂ホイールのフランジ外径（図面 42mm）
RIM_OD = FLANGE_OD       # 旧名。外部参照の互換のために残す
BOLT_PCD = 20.0          # ハブ取付穴のピッチ円直径（図面 10mm 半径 x2）
BOLT_COUNT = 3
BOLT_HOLE_DIA = 3.4      # ウェブ側は 3mm ビスのバカ穴（貫通）

# 実測値（2026-07-19、ユーザーがノギスで実測）[mm]
# 図面に数値が無いため実測で確定した。タイヤ幅 16 に対しホイール幅は 11 で、
# タイヤが両側に 2.5 ずつはみ出す。ポケット径 38 はフランジ肉厚 (42-38)/2 = 2.0 に相当。
WHEEL_WIDTH = 11.0       # 樹脂ホイールの幅（タイヤ幅 16 とは別物）
WEB_THICKNESS = 2.0      # ウェブ板厚。ビスがここを貫通する
POCKET_DIA = 38.0        # ポケット径（フランジ内側）
CENTER_BORE_DIA = 8.5    # ウェブ中央の穴。純正はここにハブのボスが嵌る
PIN_HOLE_DIA = 1.5       # 位置決めピン穴

# 未確定（provisional・実測待ち）
PIN_COUNT = 3
PIN_HOLE_START_DEG = 30.0  # ビス穴（90度基準）に対して 60 度ずらした位置（位相は未確認）


def pocket_depth() -> float:
    """片面ポケットの深さ。両面対称なので (幅 - ウェブ厚) / 2。"""
    return (WHEEL_WIDTH - WEB_THICKNESS) / 2


@dataclass(frozen=True)
class TamiyaWheel:
    """タミヤ 70145 ホイールの基準寸法と特徴点。原点は回転軸中心。"""

    def bolt_positions(self, start_deg: float = 90.0) -> list[tuple[float, float]]:
        """ビス穴（大穴 3 個）の中心 (x, y)。PCD20 上に 3 点等配。"""
        return _polar(BOLT_PCD / 2, BOLT_COUNT, start_deg)

    def pin_positions(self, start_deg: float = PIN_HOLE_START_DEG) -> list[tuple[float, float]]:
        """位置決めピン穴（小穴 3 個）の中心 (x, y)。ビス穴と 60 度ずれて交互に並ぶ。"""
        return _polar(BOLT_PCD / 2, PIN_COUNT, start_deg)


def _polar(radius: float, count: int, start_deg: float) -> list[tuple[float, float]]:
    return [
        (radius * math.cos(math.radians(start_deg + 360 * i / count)),
         radius * math.sin(math.radians(start_deg + 360 * i / count)))
        for i in range(count)
    ]


def body(*, inner_face_z: float = 0.0) -> Part:
    """ホイール（樹脂スプール＋ゴムタイヤ）の外形。原点＝回転軸中心。

    inner_face_z にハブ側フランジの端面を置き、そこから +Z へホイール幅ぶん伸びる。

    軸方向の構成（inner_face_z を z0、ポケット深さを d とする）:
      z0 .. z0+d              ハブ側ポケット（変換ハブが入る空間）
      z0+d .. z0+d+web        ウェブ（板）。ビス・ピン・中心ボアが通る
      z0+d+web .. z0+2d+web   反対側ポケット（ビスを差し込む側）
    外周はフランジ外径 42、その外にタイヤ（外径 58）が嵌る。
    """
    p = TamiyaWheel()
    z0 = inner_face_z
    d = pocket_depth()

    # 樹脂ホイールの素地（外径 42 の円柱）
    wheel = Pos(0, 0, z0) * Cylinder(
        FLANGE_OD / 2, WHEEL_WIDTH, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )

    # 両面のポケット（対称）。これがスプール形状を作る
    for face_z in (z0, z0 + d + WEB_THICKNESS):
        wheel -= Pos(0, 0, face_z) * Cylinder(
            POCKET_DIA / 2, d, align=(Align.CENTER, Align.CENTER, Align.MIN)
        )

    # 中心ボア（貫通）。純正ハブはここにボスを嵌めて芯出しする
    wheel -= Pos(0, 0, z0) * Cylinder(
        CENTER_BORE_DIA / 2, WHEEL_WIDTH, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )

    # ビス穴（大3）と位置決めピン穴（小3）。どちらもウェブを貫通する
    for x, y in p.bolt_positions():
        wheel -= Pos(x, y, z0) * Cylinder(
            BOLT_HOLE_DIA / 2, WHEEL_WIDTH, align=(Align.CENTER, Align.CENTER, Align.MIN)
        )
    for x, y in p.pin_positions():
        wheel -= Pos(x, y, z0) * Cylinder(
            PIN_HOLE_DIA / 2, WHEEL_WIDTH, align=(Align.CENTER, Align.CENTER, Align.MIN)
        )

    # タイヤ（ゴムリング）。フランジ外径に嵌り、ホイール幅の中央に揃える
    tire_z = z0 + (WHEEL_WIDTH - TIRE_WIDTH) / 2
    tire = Pos(0, 0, tire_z) * Cylinder(
        TIRE_OD / 2, TIRE_WIDTH, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    tire -= Pos(0, 0, tire_z) * Cylinder(
        FLANGE_OD / 2, TIRE_WIDTH, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    return wheel + tire


def web_near_face_z(inner_face_z: float = 0.0) -> float:
    """ウェブのハブ側の面（ハブが突き当たる面）の Z。"""
    return inner_face_z + pocket_depth()


def web_far_face_z(inner_face_z: float = 0.0) -> float:
    """ウェブの反対側の面（ビス頭が座る面）の Z。工具アクセスの検証に使う。"""
    return inner_face_z + pocket_depth() + WEB_THICKNESS


def rim_recess_diameter() -> float:
    """変換ハブの外径スピゴットが嵌るポケットの径（provisional）。"""
    return POCKET_DIA
