"""形状の目視確認用 PNG の生成。

Claude はこの PNG を Read ツールで開いて形状を確認する。生成しただけで完了としない。

注意: レンダリングは形状が不正でも成功する。必ず verify.py の数値検証を通してから使う。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import pyvista as pv  # noqa: E402
from build123d import Part, export_stl  # noqa: E402

# 部品ごとの色。アセンブリで部品を見分けるために使う。
PALETTE = [
    "#4c72b0", "#dd8452", "#55a868", "#c44e52", "#8172b3",
    "#937860", "#da8bc3", "#8c8c8c", "#ccb974", "#64b5cd",
]

VIEWS = ("iso", "front", "right", "top")


def _to_mesh(part: Part, tolerance: float = 0.05) -> pv.PolyData:
    """build123d の形状を pyvista のメッシュに変換する。"""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "m.stl"
        export_stl(part, str(path), tolerance=tolerance)
        mesh = pv.read(str(path))
    # STL は法線が揃っていないことがあり、陰影が破綻するため揃え直す
    return mesh.compute_normals(auto_orient_normals=True, consistent_normals=True)


def render(
    parts: Part | dict[str, Part],
    out_path: str | Path,
    *,
    opacity: dict[str, float] | None = None,
    window_size: tuple[int, int] = (1400, 1100),
) -> Path:
    """4 面（アイソメ・正面・右・上）を 1 枚の PNG にまとめて出力する。

    1 枚にまとめるのは、1 回の Read で全体を把握できるようにするため。
    parts に辞書を渡すとアセンブリとして部品ごとに色を変えて描画する。
    外装を半透明にしたい場合は opacity で指定する（例: {"enclosure": 0.3}）。
    """
    if isinstance(parts, Part):
        parts = {"part": parts}
    opacity = opacity or {}

    meshes = {name: _to_mesh(p) for name, p in parts.items()}
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pl = pv.Plotter(shape=(2, 2), off_screen=True, window_size=window_size)
    for i, view in enumerate(VIEWS):
        pl.subplot(i // 2, i % 2)
        for j, (name, mesh) in enumerate(meshes.items()):
            pl.add_mesh(
                mesh,
                color=PALETTE[j % len(PALETTE)],
                opacity=opacity.get(name, 1.0),
                smooth_shading=False,
                show_edges=False,
            )
            # 三角形分割の線ではなく、実際の稜線だけを描く
            edges = mesh.extract_feature_edges(
                feature_angle=25, boundary_edges=False, non_manifold_edges=False
            )
            if edges.n_points:
                pl.add_mesh(edges, color="#222222", line_width=2)

        label = view if len(meshes) == 1 else f"{view}  [{', '.join(meshes)}]"
        pl.add_text(label, font_size=9, color="black")
        {
            "iso": pl.view_isometric,
            "front": pl.view_xz,  # -Y から見る
            "right": pl.view_yz,  # +X から見る
            "top": pl.view_xy,    # +Z から見る
        }[view]()
        pl.reset_camera()

    pl.set_background("white")
    pl.screenshot(str(out_path))
    pl.close()
    return out_path


def show(parts: Part | dict[str, Part]) -> None:
    """ocp_vscode のビューアに送り、人間が確認できるようにする。

    VSCode の OCP CAD Viewer、または `python -m ocp_vscode --port 3939` で起動した
    スタンドアロンのビューア（ブラウザで http://127.0.0.1:3939/viewer）に送る。

    カメラは毎回リセットする。前回の視点を保持すると、形状が画面外に出て
    「何も表示されない」ように見えることがあるため。
    """
    from ocp_vscode import Camera, set_defaults
    from ocp_vscode import show as ocp_show

    set_defaults(reset_camera=Camera.RESET)

    if isinstance(parts, Part):
        ocp_show(parts)
    else:
        ocp_show(*parts.values(), names=list(parts))
