"""XL330 → タミヤホイール 変換ハブ。

pen_robo の駆動輪を XL330-M077 の出力ホーンに結合する。仕様書 §6.2。

方式: 付属ハブを使わず、変換ハブをホイールの 3x8mm タッピング穴（3点）に直接ボルト留め。
同軸度を確保するため二重に芯出しする。
  - XL330 側: ホーン円板の外周に被せるスカート（底面から -Z）で芯出し、M2x4 でボルト留め
  - ホイール側: リム内側の座ぐりに嵌る外径スピゴット（上面から +Z）で芯出し、3x8mm ビス3本で留め

軸方向の当たり面は、回転する部品どうしだけが触れるようにする。ハブ底面（Z=0）がホーン頂面に
当たり、スカートはケース前面まで届かせない（skirt_clearance ぶん浮かせる）。

座標系: 回転軸 = Z。原点はハブ底面（ホーン当たり面）の中心。Z+ がホイール側。

暫定寸法（provisional）は PROVISIONAL に列挙。印刷前に verify.assert_no_provisional で確定を強制する。
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

from build123d import Align, Cylinder, Part, Pos

from hwlib.bom import load_bom
from hwlib.features import SCREWS
from hwlib.parts import tamiya_wheel, xl330

HERE = Path(__file__).parent
BOM = load_bom(HERE / "bom.yaml")
OUT = HERE / "out"


# 実測が未確定の暫定寸法。{パラメータ名: 測り方}。印刷前に必ず実測して Params を更新し、
# ここから消す。残っている限り verify.assert_no_provisional が失敗する。
# 外形・穴位置は公式図面（XL330: X330、タミヤ: 70145 組立説明図）で確定した。
# 一方、芯出しの嵌合面はどちらの図面にも数値が無いため、実測に頼らざるを得ない。
# 中央ボアは使わない方針のため、ボア径は実測項目に含めない。
PROVISIONAL: dict[str, str] = {
    "horn_boss_dia": "XL330 出力ホーン円板の外径。芯出しスカートが被る相手面",
    "horn_boss_h": "ホーン円板がケース前面から出ている高さ。スカート高さの上限になる",
}


@dataclass(frozen=True)
class Params:
    """設計パラメータ。暫定値は PROVISIONAL に対応する項目を実測後に更新する。"""

    # --- XL330 側: 公式図面 X330 で確定 ---
    horn_pcd: float = 12.0       # ホーン穴 P.C.D φ12（4xφ1.6, 90度等配）

    # --- XL330 側: 暫定（実測待ち。hwlib.parts.xl330 が出所） ---
    horn_boss_dia: float = xl330.HORN_BOSS_DIA
    horn_boss_h: float = xl330.HORN_BOSS_H

    # --- タミヤ側: 70145 組立説明図で確定 ---
    wheel_bolt_pcd: float = tamiya_wheel.BOLT_PCD  # 3穴 PCD20（図面 10mm 半径 x2）
    rim_od: float = tamiya_wheel.RIM_OD            # ホイールディスク外径 42

    # --- タミヤ側: 実測で確定（2026-07-19。hwlib.parts.tamiya_wheel が出所） ---
    # ビスが貫通するウェブの板厚。ねじ込み深さ = ビス長 - この厚み
    wheel_boss_wall: float = tamiya_wheel.WEB_THICKNESS
    wheel_recess_dia: float = tamiya_wheel.POCKET_DIA
    wheel_recess_depth: float = tamiya_wheel.pocket_depth()
    wheel_width: float = tamiya_wheel.WHEEL_WIDTH
    wheel_center_bore_dia: float = tamiya_wheel.CENTER_BORE_DIA
    wheel_pin_hole_dia: float = tamiya_wheel.PIN_HOLE_DIA

    # --- 確定（設計上の選択・はめ合い） ---
    horn_screw: str = "M2"       # ホーン固定ネジ
    horn_screw_len: float = 8.0  # M2x8（付属の M2x6 では届かない。BOM 参照）
    horn_engage: float = 3.0     # ホーンへのねじ込み深さ（図面 DP3.0 Max）
    wheel_screw: str = "M3"      # 3x8 タッピングビス（呼び径3）
    wheel_screw_len: float = 8.0
    pocket_fit: float = 0.10     # ハブ外径とポケット壁のすきま（片側）
    wheel_gap: float = 0.50      # ホイールのフランジ端面とホーン当たり面のすきま
    skirt_fit: float = 0.10      # 芯出しスカートのすきま（片側）
    skirt_wall: float = 1.5      # スカートの肉厚
    skirt_clearance: float = 0.5  # スカート先端とケース前面のすきま（擦れ防止）
    tap_floor: float = 1.5       # 下穴の底に残す肉厚

    @property
    def adapter_od(self) -> float:
        """ハブ外径。ホイールのポケットに片側 pocket_fit のすきまで嵌る。

        ハブは本体ごとポケットの中に収まり、この外周が全高にわたって
        ポケット壁と嵌合して芯出しする（純正ハブ B1/B2 と同じ収まり方）。
        """
        return self.wheel_recess_dia - 2 * self.pocket_fit

    @property
    def body_height(self) -> float:
        """ハブの全高（底面 Z=0 から上面まで）。スカートは含まない。

        上面はホイールのウェブに突き当たる。次の 2 つの下限で決まる:
          - ポケット深さ + wheel_gap: これを下回るとホイールのフランジ端面が
            ホーン当たり面より下に来て、サーボのケースに突っ込む
          - 下穴深さ + 底肉: 3x8 ビスが底を突き抜けない厚み
        """
        return max(
            self.wheel_recess_depth + self.wheel_gap,
            self.wheel_tap_depth + self.tap_floor,
        )

    @property
    def wheel_inner_face_z(self) -> float:
        """ホイールのハブ側フランジ端面の Z。ウェブがハブ上面に接する位置から逆算する。"""
        return self.body_height - self.wheel_recess_depth

    @property
    def skirt_id(self) -> float:
        """芯出しスカートの内径。ホーン円板の外周に片側 skirt_fit で被る。"""
        return self.horn_boss_dia + 2 * self.skirt_fit

    @property
    def skirt_od(self) -> float:
        return self.skirt_id + 2 * self.skirt_wall

    @property
    def skirt_h(self) -> float:
        """スカートが底面から -Z へ伸びる高さ。ケース前面に届かせない。"""
        return self.horn_boss_h - self.skirt_clearance

    @property
    def horn_screw_grip(self) -> float:
        """M2 がハブ側で使える長さ。ネジ長からホーンへのねじ込み分を引いた残り。"""
        return self.horn_screw_len - self.horn_engage

    @property
    def cb_depth(self) -> float:
        """M2 ネジ頭の座ぐり深さ（ハブ上面から掘る）。

        頭の座面から底面までが grip 以内に収まる深さまで沈める。これが足りないと
        ネジがホーンに届かず、深すぎるとドライバーが届かない。
        """
        return self.body_height - self.horn_screw_grip

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


def build_stock() -> Part:
    """穴を開ける前のハブ外形。assert_cut の比較基準になるので分けてある。

    軸方向の構成（下から）:
      Z = -skirt_h .. 0    芯出しスカート（ホーン円板の外周に被る中空リング）
      Z = 0 .. body_height 本体円柱 φadapter_od。ホイールのポケットに丸ごと収まる
    """
    h = P.body_height

    stock = Cylinder(P.adapter_od / 2, h, align=(Align.CENTER, Align.CENTER, Align.MIN))

    # XL330 側の芯出し: ホーン円板の外周に被せるスカート。内側をくり抜いてリングにする
    skirt = Pos(0, 0, -P.skirt_h) * Cylinder(
        P.skirt_od / 2, P.skirt_h, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    skirt -= Pos(0, 0, -P.skirt_h) * Cylinder(
        P.skirt_id / 2, P.skirt_h, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    return stock + skirt


def build_hub() -> Part:
    """変換ハブ本体（印刷対象）。原点＝回転軸。底面 Z=0 が XL330 ホーン頂に当たる。

    芯出しは両端の嵌合で行う。ボルトのバカ穴にはガタがあるため、締結だけに頼らない。
      - XL330 側: スカート内周がホーン円板の外周に嵌る
      - ホイール側: 本体の外周が全高にわたってポケット壁に嵌る（純正 B1/B2 と同じ）
    上面はホイールのウェブに突き当たり、軸方向の位置を決める。
    """
    h = P.body_height
    hub = build_stock()

    m2 = SCREWS[P.horn_screw]
    for x, y in horn_screw_positions():
        # M2 バカ穴（底面から上面まで貫通）
        hub -= Pos(x, y, 0) * Cylinder(
            m2.clearance_dia / 2, h, align=(Align.CENTER, Align.CENTER, Align.MIN)
        )
        # ネジ頭の座ぐり（上面から）。頭が出るとウェブに当たって浮く
        hub -= Pos(x, y, h - P.cb_depth) * Cylinder(
            (m2.head_dia + 0.4) / 2, P.cb_depth + 0.01,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

    # ホイール固定用: 3x8 タッピングビスの下穴（上面から）
    m3 = SCREWS[P.wheel_screw]
    tap_depth = P.wheel_tap_depth
    for x, y in wheel_screw_positions():
        hub -= Pos(x, y, h - tap_depth) * Cylinder(
            m3.pilot_dia / 2, tap_depth + 0.01,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
    return hub


# --- 相手部品のモック（干渉・目視確認用。印刷対象ではない） ---
def servo_mock() -> Part:
    """XL330 の実形状。原点＝出力軸、ホーン頂が Z=0。図面 datum を反映済み。"""
    return xl330.body()


def wheel_mock() -> Part:
    """タミヤホイールの実形状。ウェブがハブ上面に接する位置に置く。

    ハブはポケットの中に沈むため、フランジ端面はハブ上面より下（サーボ寄り）に来る。
    """
    return tamiya_wheel.body(inner_face_z=P.wheel_inner_face_z)


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
