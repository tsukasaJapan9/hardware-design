"""スタックチャン 外形の再現（公式 STL の取り込み・組み立て）。

M5Stack 公式スタックチャン（K151）の構造ファイル（STL）を取り込んで外観を再現する。
出典: https://github.com/m5stack/M5_Hardware/tree/master/Products/K151_StackChan/Structures
STL は projects/stackchan/stl/ に保存。

手作りの近似箱ではなく、公式 STL を部品の実形状として読み込む。STL は印刷用に
バラバラの座標に置かれているため、各部品を原点基準に置き直して積み上げる。
組み立ての相対位置（積み上げ高さ・首の隙間）は公式アセンブリが無いため近似。
部品そのものの形状は公式データどおり（正確）。

座標系: 原点 = 底面フットプリントの中心、Z が上。X=幅、Y=奥行き、前面 = -Y。
"""

from __future__ import annotations

import sys
from pathlib import Path

from build123d import Part, Pos, import_stl

HERE = Path(__file__).parent
STL_DIR = HERE / "stl"
OUT = HERE / "out"

ENV_H = 70.5   # 全体高さ（仕様）


def load_part(name: str) -> Part:
    """stl/ から STL を実形状として読み込む。"""
    return import_stl(str(STL_DIR / f"{name}.stl"))


def place(part: Part, *, bottom_z: float | None = None, top_z: float | None = None) -> Part:
    """XY を原点中心に揃え、Z を bottom_z（底）または top_z（頂）に合わせて置く。"""
    bb = part.bounding_box()
    c = bb.center()
    dx, dy = -c.X, -c.Y
    if bottom_z is not None:
        dz = bottom_z - bb.min.Z
    elif top_z is not None:
        dz = top_z - bb.max.Z
    else:
        dz = -c.Z
    return Pos(dx, dy, dz) * part


BASE_TOP = 11.1   # Base の上面 Z（bbox より）


def build_all() -> dict[str, Part]:
    """外観部品を組み立てる（近似: 足＝底、頭＝上で全高 70.5、サーボ首を隙間に通す）。

    公式アセンブリが無いため相対位置は推測。サーボ首（ServoBody）は足の上に載り、
    頭（下面が開いたフレーム）の中へ通って隙間を埋める。
    """
    base = place(load_part("StackChan-Base"), bottom_z=0.0)        # 回転台座（足）
    head = place(load_part("StackChan-MainBody"), top_z=ENV_H)     # 頭（CoreS3 フレーム）
    servo = place(load_part("StackChan-ServoBody"), bottom_z=BASE_TOP)  # サーボ首
    return {"base": base, "servo": servo, "head": head}


def export(out_dir: Path = OUT) -> None:
    from build123d import Compound, export_stl

    out_dir.mkdir(parents=True, exist_ok=True)
    asm = Compound(children=list(build_all().values()))
    export_stl(asm, str(out_dir / "stackchan_assembly.stl"), tolerance=0.05)
    print(f"出力しました: {out_dir}")


def main() -> None:
    if "--show" in sys.argv:
        from hwlib.render import show
        show(build_all())
    elif "--render" in sys.argv:
        from hwlib.render import render
        path = render(build_all(), OUT / "assembly.png")
        print(f"レンダリングしました: {path}")
    elif "--export" in sys.argv:
        export()
    else:
        print(__doc__)
        print("使い方: python -m projects.stackchan.model [--show|--render|--export]")


if __name__ == "__main__":
    main()
