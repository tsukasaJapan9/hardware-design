"""XL330 → タミヤホイール 変換ハブ。

pen_robo の駆動輪を XL330-M077 の出力ホーンに結合する。仕様書 §6.2。

方式: 付属ハブを使わず、変換ハブをホイールの 3x8mm タッピング穴（3点）に直接ボルト留め。
同軸度を確保するため二重に芯出しする。
  - XL330 側: ホーン中央ボスに嵌める凹パイロット（底面）で芯出し、M2x4 でボルト留め
  - ホイール側: ハブ座ぐりに嵌る外径スピゴット（OD）で芯出し、3x8mm ビス3本で留め

座標系: 回転軸 = Z。原点はハブ底面（ホーン当たり面）の中心。Z+ がホイール側。

暫定寸法（provisional）は PROVISIONAL に列挙。印刷前に verify.assert_no_provisional で確定を強制する。
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

from build123d import Align, Box, Cylinder, Part, Pos

from hwlib.bom import load_bom
from hwlib.features import SCREWS

HERE = Path(__file__).parent
BOM = load_bom(HERE / "bom.yaml")
OUT = HERE / "out"


# 実測が未確定の暫定寸法。{パラメータ名: 測り方}。印刷前に必ず実測して Params を更新し、
# ここから消す。残っている限り verify.assert_no_provisional が失敗する。
PROVISIONAL: dict[str, str] = {
    "horn_pcd": "XL330 出力ホーンの対向する M2 穴の中心間距離（＝PCD）",
    "horn_boss_dia": "ホーン中央の突起（ボス/スプライン）の外径",
    "horn_boss_h": "ホーン中央ボスがホーン上面から出ている高さ",
    "wheel_recess_dia": "ホイール内側のハブ座ぐりの直径（ここにハブ外径が嵌る）",
    "wheel_recess_depth": "ハブ座ぐりの深さ",
    "wheel_bolt_pcd": "ホイールの 3 本ビス穴の PCD（隣り合う2穴の中心間から算出）",
    "wheel_bore_dia": "ホイール中央ボアの直径（M2 ネジ頭がここに収まる必要がある）",
    "wheel_boss_wall": "ホイールのビス穴部の壁厚（3x8 ビスがこれを通ってハブへねじ込む）",
}


@dataclass(frozen=True)
class Params:
    """設計パラメータ。暫定値は PROVISIONAL に対応する項目を実測後に更新する。"""

    # --- 暫定（実測待ち）。当面は妥当な仮値 ---
    horn_pcd: float = 8.0
    horn_boss_dia: float = 8.0
    horn_boss_h: float = 1.5
    wheel_recess_dia: float = 26.0
    wheel_recess_depth: float = 3.0
    wheel_bolt_pcd: float = 20.0
    wheel_bore_dia: float = 10.0
    wheel_boss_wall: float = 2.0

    # --- 確定（設計上の選択・はめ合い） ---
    horn_screw: str = "M2"       # ホーン固定ネジ
    wheel_screw: str = "M3"      # 3x8 タッピングビス（呼び径3）
    wheel_screw_len: float = 8.0
    pilot_fit: float = 0.10      # 凹パイロットのすきま（片側）
    spigot_fit: float = 0.10     # 外径スピゴットのすきま（片側）
    body_thickness: float = 8.0  # ハブ本体の厚み
    cb_depth: float = 2.0        # M2 ネジ頭の座ぐり深さ
    tap_floor: float = 1.5       # 下穴の底に残す肉厚

    @property
    def adapter_od(self) -> float:
        """ハブ外径。ホイール座ぐりにスピゴット嵌合させて芯出しする。"""
        return self.wheel_recess_dia - 2 * self.spigot_fit

    @property
    def wheel_tap_depth(self) -> float:
        """ホイール固定ビスがハブにねじ込まれる深さ。

        3x8 ビスはホイール壁（wheel_boss_wall）を通ってからハブに入るため、
        ねじ込み深さ = ビス長 - 壁厚。本体はこれ + 底肉を収める厚みが要る。
        """
        return self.wheel_screw_len - self.wheel_boss_wall


P = Params()


def _polar(radius: float, count: int, start_deg: float = 0.0) -> list[tuple[float, float]]:
    """半径 radius 上に count 個、等間隔に並ぶ (x, y)。"""
    return [
        (radius * math.cos(math.radians(start_deg + 360 * i / count)),
         radius * math.sin(math.radians(start_deg + 360 * i / count)))
        for i in range(count)
    ]


def horn_screw_positions() -> list[tuple[float, float]]:
    return _polar(P.horn_pcd / 2, 4, start_deg=45)


def wheel_screw_positions() -> list[tuple[float, float]]:
    return _polar(P.wheel_bolt_pcd / 2, 3, start_deg=90)


def build_hub() -> Part:
    """変換ハブ本体（印刷対象）。"""
    t = P.body_thickness
    hub = Cylinder(P.adapter_od / 2, t, align=(Align.CENTER, Align.CENTER, Align.MIN))

    # 底面: ホーン中央ボスに嵌る凹パイロット（芯出し）
    hub -= Cylinder(
        (P.horn_boss_dia + 2 * P.pilot_fit) / 2, P.horn_boss_h,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )

    m2 = SCREWS[P.horn_screw]
    for x, y in horn_screw_positions():
        # M2 バカ穴（貫通）
        hub -= Pos(x, y, 0) * Cylinder(
            m2.clearance_dia / 2, t, align=(Align.CENTER, Align.CENTER, Align.MIN)
        )
        # ネジ頭の座ぐり（上面から）。頭がホイール側に出ないようにする
        hub -= Pos(x, y, t - P.cb_depth) * Cylinder(
            (m2.head_dia + 0.4) / 2, P.cb_depth + 0.01,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

    # ホイール固定用: 3x8 タッピングビスの下穴（上面から本体へ）
    m3 = SCREWS[P.wheel_screw]
    tap_depth = P.wheel_tap_depth
    for x, y in wheel_screw_positions():
        hub -= Pos(x, y, t - tap_depth) * Cylinder(
            m3.pilot_dia / 2, tap_depth + 0.01,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
    return hub


# --- 相手部品のモック（干渉・目視確認用。印刷対象ではない） ---
def servo_mock() -> Part:
    """XL330 の外形。回転軸を Z に合わせ、ホーン当たり面（Z=0）の下に置く。"""
    w, h, d = BOM["xl330"].size  # 20 x 34 x 26
    # 出力軸のケース内オフセットは実測待ちのため、軸を中心とした概略配置
    return Pos(0, 0, -d) * Box(w, h, d, align=(Align.CENTER, Align.CENTER, Align.MIN))


def wheel_mock() -> Part:
    """タミヤホイールの外形。内側面をハブ上面に合わせて置く。"""
    dia, _, width = BOM["wheel"].size  # 58 x 58 x 16
    wheel = Pos(0, 0, P.body_thickness) * Cylinder(
        dia / 2, width, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    # 中央ボア（M2 頭の逃げ確認用）
    wheel -= Pos(0, 0, P.body_thickness) * Cylinder(
        P.wheel_bore_dia / 2, width, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    return wheel


def build_all() -> dict[str, Part]:
    return {"hub": build_hub(), "servo": servo_mock(), "wheel": wheel_mock()}


def export(out_dir: Path = OUT) -> None:
    from build123d import export_step, export_stl

    out_dir.mkdir(parents=True, exist_ok=True)
    hub = build_hub()
    export_stl(hub, str(out_dir / "hub.stl"), tolerance=0.02)
    export_step(hub, str(out_dir / "hub.step"))
    print(f"出力しました: {out_dir}")


def main() -> None:
    if "--show" in sys.argv:
        from hwlib.render import show
        show(build_all())
    elif "--render" in sys.argv:
        from hwlib.render import render
        path = render(build_all(), OUT / "assembly.png", opacity={"servo": 0.3, "wheel": 0.3})
        print(f"レンダリングしました: {path}")
    elif "--export" in sys.argv:
        export()
    else:
        print(__doc__)
        print("使い方: python -m projects.pen_robo_wheel_hub.model [--show|--render|--export]")


if __name__ == "__main__":
    main()
