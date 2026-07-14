"""Raspberry Pi Zero 2 W + カメラ + バッテリーを収めるケース。

スキルの 5 段階（ヒアリング → 部品の洗い出し → 寸法調査 → 設計 → 検証）を
一通り通したリファレンス実装。検証は test_model.py にある。

座標系: 内寸の左手前・底面を原点 (0, 0, 0) とし、Z が上。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from build123d import Align, Box, Cylinder, Part, Pos

from hwlib.bom import load_bom
from hwlib.features import SCREWS, clearance_hole, rect_opening, tapping_boss

HERE = Path(__file__).parent
BOM_PATH = HERE / "bom.yaml"
OUT = HERE / "out"


@dataclass(frozen=True)
class Params:
    """設計パラメータ。数値はすべてここに集約し、モデル本体に直接書かない。"""

    # 内寸。部品の配置から決まる
    inner_w: float = 80.0    # X
    inner_d: float = 116.0   # Y
    inner_h: float = 20.0    # Z

    wall: float = 2.5
    floor: float = 2.5
    lid_thickness: float = 2.5

    # 蓋の固定（ケース四隅のボス）
    lid_screw: str = "M3"
    lid_screw_len: float = 10.0
    lid_boss_depth: float = 8.0
    lid_boss_inset: float = 5.0  # 内寸の角からボス中心までの距離

    # 基板の固定
    board_screw: str = "M2.6"
    board_screw_len: float = 8.0
    board_boss_h: float = 7.0   # 基板の下に確保する高さ（配線・端子の逃げ）
    board_boss_depth: float = 7.0

    # 部品の配置（内寸座標での最小コーナー）
    board_pos: tuple[float, float, float] = (10.0, 12.0, 7.0)
    # カメラは台座に載せ、レンズ面を蓋の内側に合わせる（Z = 内寸高さ - カメラ高さ）
    camera_pos: tuple[float, float, float] = (30.0, 50.0, 11.0)
    battery_pos: tuple[float, float, float] = (12.0, 79.0, 0.0)

    camera_lens_dia: float = 12.0
    # カメラを横方向に拘束するリブ
    camera_rib_gap: float = 0.5    # カメラとリブの隙間（入れられる程度に）
    camera_rib_thickness: float = 2.0
    camera_rib_height: float = 4.0  # 台座上面からの高さ

    driver_dia: float = 6.0  # 組み立てに使うドライバーの軸径


P = Params()
BOM = load_bom(BOM_PATH)


def lid_boss_positions() -> list[tuple[float, float]]:
    """蓋を留めるボスの位置（内寸座標）。四隅。"""
    i = P.lid_boss_inset
    return [
        (i, i),
        (P.inner_w - i, i),
        (i, P.inner_d - i),
        (P.inner_w - i, P.inner_d - i),
    ]


def board_boss_positions() -> list[tuple[float, float]]:
    """基板を留めるボスの位置（内寸座標）。基板の取付穴に合わせる。"""
    bx, by, _ = P.board_pos
    return [(bx + hx, by + hy) for hx, hy in BOM["pi_zero"].mount_holes]


def interior() -> Part:
    """内部空間。部品がここに収まっているかを確認するために使う。"""
    return Box(P.inner_w, P.inner_d, P.inner_h, align=(Align.MIN, Align.MIN, Align.MIN))


def camera_mount() -> Part:
    """カメラの台座と位置決めリブ。

    カメラを底に置くだけでは固定されず、レンズも蓋から遠ざかる。
    台座でレンズ面を蓋の内側まで持ち上げ、リブで横方向を拘束し、蓋で上から押さえる。
    """
    cx, cy, cz = P.camera_pos
    cw, cd, _ = BOM["camera"].size

    # 台座（カメラの真下）。上面がカメラの底面 (z = cz) になる高さ
    mount = Pos(cx, cy, 0) * Box(cw, cd, cz, align=(Align.MIN, Align.MIN, Align.MIN))

    # 位置決めリブ: カメラの外周を囲む枠。カメラとの間に隙間を設けて入れられるようにする
    g, t, h = P.camera_rib_gap, P.camera_rib_thickness, P.camera_rib_height
    outer = Pos(cx - g - t, cy - g - t, cz) * Box(
        cw + 2 * (g + t), cd + 2 * (g + t), h, align=(Align.MIN, Align.MIN, Align.MIN)
    )
    inner = Pos(cx - g, cy - g, cz) * Box(
        cw + 2 * g, cd + 2 * g, h, align=(Align.MIN, Align.MIN, Align.MIN)
    )
    return mount + (outer - inner)


def build_base() -> Part:
    """ケース本体（上面が開いたトレー）。"""
    outer = Pos(-P.wall, -P.wall, -P.floor) * Box(
        P.inner_w + 2 * P.wall,
        P.inner_d + 2 * P.wall,
        P.inner_h + P.floor,
        align=(Align.MIN, Align.MIN, Align.MIN),
    )
    base = outer - interior()

    # 蓋を留めるボス（内寸の底から天面まで）
    for x, y in lid_boss_positions():
        base += Pos(x, y, 0) * tapping_boss(P.lid_screw, height=P.inner_h, depth=P.lid_boss_depth)

    # 基板を留めるボス
    for x, y in board_boss_positions():
        base += Pos(x, y, 0) * tapping_boss(
            P.board_screw, height=P.board_boss_h, depth=P.board_boss_depth
        )

    # カメラの台座と位置決めリブ
    base += camera_mount()

    # 電源コネクタの開口（手前の壁）
    conn = BOM["pi_zero"].connectors[0]
    cx, _, cz = conn.pos
    bx, by, bz = P.board_pos
    base -= rect_opening(
        center=(bx + cx, 0.0, bz + cz),
        face="-y",
        size=conn.size,
        wall_thickness=P.wall,
    )
    return base


def build_lid() -> Part:
    """蓋。四隅にネジのバカ穴、カメラのレンズ穴を持つ。"""
    lid = Pos(-P.wall, -P.wall, P.inner_h) * Box(
        P.inner_w + 2 * P.wall,
        P.inner_d + 2 * P.wall,
        P.lid_thickness,
        align=(Align.MIN, Align.MIN, Align.MIN),
    )

    for x, y in lid_boss_positions():
        lid -= Pos(x, y, P.inner_h) * clearance_hole(P.lid_screw, P.lid_thickness)

    cam = BOM["camera"]
    cx, cy, _ = P.camera_pos
    lens_center = (cx + cam.size[0] / 2, cy + cam.size[1] / 2)
    lid -= Pos(lens_center[0], lens_center[1], P.inner_h) * Cylinder(
        radius=P.camera_lens_dia / 2,
        height=P.lid_thickness,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )
    return lid


def place_components() -> dict[str, Part]:
    """BOM の部品を配置する。geometric: false の部品（ネジ等）は含まない。"""
    positions = {
        "pi_zero": P.board_pos,
        "camera": P.camera_pos,
        "battery": P.battery_pos,
    }
    return {cid: Pos(*pos) * BOM[cid].mock() for cid, pos in positions.items()}


def screw_heads() -> dict[str, list[tuple[float, float, float]]]:
    """ネジ頭の位置。ドライバーが入るかの確認に使う。"""
    board_top = P.board_pos[2] + BOM["pi_zero"].size[2]
    return {
        # 蓋のネジは蓋の上面から締める
        P.lid_screw: [
            (x, y, P.inner_h + P.lid_thickness) for x, y in lid_boss_positions()
        ],
        # 基板のネジは基板の上面から締める（蓋を閉じる前）
        P.board_screw: [(x, y, board_top) for x, y in board_boss_positions()],
    }


def build_all() -> dict[str, Part]:
    """アセンブリ全体。"""
    return {"base": build_base(), "lid": build_lid(), **place_components()}


def export(out_dir: Path = OUT) -> None:
    """3D プリントする部品を STL に出力する。"""
    from build123d import export_step, export_stl

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, part in (("base", build_base()), ("lid", build_lid())):
        export_stl(part, str(out_dir / f"{name}.stl"), tolerance=0.02)
        export_step(part, str(out_dir / f"{name}.step"))
    print(f"出力しました: {out_dir}")


def main() -> None:
    if "--show" in sys.argv:
        # ocp_vscode のビューアに送る。VSCode で OCP CAD Viewer を開いておくこと
        from hwlib.render import show

        show(build_all())
    elif "--render" in sys.argv:
        from hwlib.render import render

        path = render(build_all(), OUT / "assembly.png", opacity={"base": 0.35, "lid": 0.25})
        print(f"レンダリングしました: {path}")
    elif "--export" in sys.argv:
        export()
    else:
        print(__doc__)
        print("使い方: python -m projects.example_camera_case.model [--show|--render|--export]")


if __name__ == "__main__":
    main()
