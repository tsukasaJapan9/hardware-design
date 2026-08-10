"""スタックチャンの頭 側面グリル（丸穴 3 つ）にはめ込む犬の垂れ耳アクセサリー。

頭（MainBody）の両側面グリルにある丸穴 3 つへペグで差し込んで固定する。
取り付け板と耳は同一形状 ―― 犬の垂れ耳ローブの輪郭をそのまま板（厚み ear_th）として
使い、その裏面（頭側）に 3 本のペグを立てる。左右は YZ 面のミラー。

穴の実測（model の頭を原点中心に置いた座標系。pyvista で STL を断面計測）:
  - 中心 Y = -11.6 / -3.6 / +4.4（ピッチ 8.0）、Z = 17.0
  - +X 面 X≈27.0。口元 φ6.1 の面取り → 直管 φ4.85、深さ約 6mm（X≈20 で底）

座標系は頭を原点中心に置いた frame（accessory.head_centered() と一致）。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from build123d import (
    Align, Axis, Cylinder, Part, Plane, Polygon, Pos, Rot, extrude, fillet, mirror,
)

from projects.stackchan.model import load_part, place

HERE = Path(__file__).parent
OUT = HERE / "out"


@dataclass(frozen=True)
class Params:
    # 穴（実測、頭中心座標）
    hole_y: tuple[float, ...] = (-11.6, -3.6, 4.4)
    hole_z: float = 17.0
    face_x: float = 27.0        # +X 外面
    bore_dia: float = 4.85      # 直管部の径
    hole_depth: float = 6.0     # 直管部の深さ

    # ペグ（はめ込み側）。FDM で締まり嵌めになるようすきまを取る
    peg_clear: float = 0.15     # 片側すきま（"ぴったり"＝締まり寄り）
    peg_len: float = 5.0        # 差し込み長（穴深さ 6 に対し 1 残す）
    peg_leadin: float = 0.6     # 先端の面取り（入りやすく）

    # 耳＝取り付け板（同一形状）。犬の垂れ耳ローブを Y-Z 断面に作り X へ厚みぶん出す。
    # 付け根（上）は 3 ペグ列（Y=-11.6..4.4, Z=17）を覆う幅。そこから下へ丸く垂れる。
    ear_th: float = 6.0         # 板厚＝耳厚（X 方向、外側へ）
    ear_top_z: float = 24.0     # 付け根（上端）Z
    ear_tip_z: float = -14.0    # 耳先（下端）Z ＝ 垂れる先
    ear_tip_y: float = -6.0     # 耳先の Y（やや前傾）
    ear_top_y0: float = -15.0   # 付け根の前(-Y)端（ペグ列 -11.6 を覆う）
    ear_top_y1: float = 8.0     # 付け根の後(+Y)端（ペグ列 +4.4 を覆う）
    ear_mid_bulge: float = 1.0  # 中ほどの膨らみ
    ear_r: float = 6.0          # 角丸（垂れ耳の丸み）

    @property
    def peg_dia(self) -> float:
        return self.bore_dia - 2 * self.peg_clear


P = Params()


def _peg(radius: float, length: float, x_start: float, y: float, z: float, leadin: float) -> Part:
    """X 軸に沿ったペグ。x_start から +X へ length。先端(-X 側)に面取り。"""
    peg = Pos(x_start, y, z) * Rot(0, 90, 0) * Cylinder(
        radius, length, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    tip = peg.faces().sort_by(Axis.X)[0].edges()   # 先端(-X)の縁
    return fillet(tip, radius=min(leadin, radius - 0.4))


def _ear_lobe() -> Part:
    """犬の垂れ耳ローブ（＝取り付け板）。付け根（上）から下へ丸く垂れる断面を +X へ押し出す。"""
    p = P
    mid_z = (p.ear_top_z + p.ear_tip_z) / 2
    prof = Polygon(
        (p.ear_top_y0, p.ear_top_z),               # 付け根・前
        (p.ear_top_y1, p.ear_top_z),               # 付け根・後
        (p.ear_top_y1 + p.ear_mid_bulge, mid_z),   # 中ほど・後
        (p.ear_tip_y, p.ear_tip_z),                # 耳先（下端）
        (p.ear_top_y0 - p.ear_mid_bulge, mid_z),   # 中ほど・前
        align=None,
    )
    prof = fillet(prof.vertices(), radius=p.ear_r)
    lobe = extrude(Plane.YZ * prof, amount=p.ear_th)
    # 押し出し方向に依らず、内面を +X 面(face_x)に合わせて外側へ出す
    return Pos(p.face_x - lobe.bounding_box().min.X, 0, 0) * lobe


def build_ear_right() -> Part:
    """+X 側の耳（耳ローブ＝取り付け板 ＋ 3 ペグ）。頭中心座標。"""
    p = P
    acc = _ear_lobe()
    for y in p.hole_y:
        acc += _peg(p.peg_dia / 2, p.peg_len, p.face_x - p.peg_len, y, p.hole_z, p.peg_leadin)
    return acc


def build_ear_left() -> Part:
    """-X 側の耳。右耳を YZ 面でミラー。"""
    return mirror(build_ear_right(), about=Plane.YZ)


def head_centered() -> Part:
    """フィット確認用に、頭(MainBody)を原点中心に置いて返す（穴計測と同じ frame）。"""
    return place(load_part("StackChan-MainBody"))


def build_all() -> dict[str, Part]:
    return {
        "head": head_centered(),
        "ear_right": build_ear_right(),
        "ear_left": build_ear_left(),
    }


def export(out_dir: Path = OUT) -> None:
    from build123d import export_step, export_stl

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, part in (("ear_right", build_ear_right()), ("ear_left", build_ear_left())):
        export_stl(part, str(out_dir / f"{name}.stl"), tolerance=0.02)
        export_step(part, str(out_dir / f"{name}.step"))
    print(f"出力しました: {out_dir}")


def main() -> None:
    if "--show" in sys.argv:
        from hwlib.render import show
        show(build_all())
    elif "--render" in sys.argv:
        from hwlib.render import render
        path = render(build_all(), OUT / "accessory.png", opacity={"head": 0.4})
        print(f"レンダリングしました: {path}")
    elif "--export" in sys.argv:
        export()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
