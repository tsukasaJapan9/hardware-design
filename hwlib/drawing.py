"""三面図（第三角法）の SVG 生成。

BOM の部品を図面として並べるための作図モジュール。形状は build123d の
`project_to_viewport()` で投影する。手描きの近似ではなく実際のソリッドの
稜線を落とすため、図と CAD の形状はずれない。

配置（第三角法）:

    平面図
    正面図  右側面図

視線と軸の対応（実測で確認済み。VIEWS の u_axis / v_axis がその対応）:
  平面図   = +Z から見下ろす。図の右 = +X、図の上 = +Y
  正面図   = -Y から見る。    図の右 = +X、図の上 = +Z
  右側面図 = +X から見る。    図の右 = +Y、図の上 = +Z

投影は「見える稜線（実線）」と「隠れた稜線（破線）」を分けて返すため、
穴や内部形状も図面として読める。

寸法は W（幅 X）・D（奥行き Y）・H（高さ Z）を 1 回ずつだけ入れる。
同じ寸法を複数の図に重複して書かないのは製図の慣習に合わせたもの。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from build123d import Edge, GeomType, Part

# --- 投影 ---------------------------------------------------------------


@dataclass(frozen=True)
class View:
    """1 つの投影図の定義。

    direction は部品から視点へ向かう向き。u_axis / v_axis は投影後の
    図の「右方向」「上方向」に対応する部品座標系の軸。
    """

    key: str
    label: str
    direction: tuple[float, float, float]
    up: tuple[float, float, float]
    u_axis: str
    v_axis: str


VIEWS: tuple[View, ...] = (
    View("top", "平面図", (0, 0, 1), (0, 1, 0), "X", "Y"),
    View("front", "正面図", (0, -1, 0), (0, 0, 1), "X", "Z"),
    View("right", "右側面図", (1, 0, 0), (0, 0, 1), "Y", "Z"),
)

Polyline = list[tuple[float, float]]


def _sample(edge: Edge, segments: int = 48) -> Polyline:
    """稜線を折れ線に離散化する。直線は 2 点、曲線は分割して近似する。"""
    if edge.geom_type == GeomType.LINE:
        params = [0.0, 1.0]
    else:
        params = [i / segments for i in range(segments + 1)]
    return [(p.X, p.Y) for p in edge.positions(params)]


def _to_polylines(edges: Iterable[Edge], du: float, dv: float) -> list[Polyline]:
    """投影された稜線を部品座標に戻した折れ線に変換する。

    project_to_viewport() は look_at を原点とした座標を返すため、
    注記（コネクタ位置など）と重ねられるよう部品座標へ平行移動する。
    """
    return [[(u + du, v + dv) for u, v in _sample(e)] for e in edges]


def project_view(part: Part, view: View) -> tuple[list[Polyline], list[Polyline]]:
    """1 方向から投影し、(見える稜線, 隠れた稜線) を部品座標の折れ線で返す。"""
    bbox = part.bounding_box()
    center = bbox.center()
    # 遠方から見て平行投影に近づける（focus 未指定なので正射影）
    distance = max(bbox.size.X, bbox.size.Y, bbox.size.Z) * 10 + 100
    origin = tuple(
        getattr(center, axis) + d * distance
        for axis, d in zip("XYZ", view.direction)
    )
    visible, hidden = part.project_to_viewport(
        origin, view.up, (center.X, center.Y, center.Z)
    )
    du = getattr(center, view.u_axis)
    dv = getattr(center, view.v_axis)
    return _to_polylines(visible, du, dv), _to_polylines(hidden, du, dv)


# --- SVG の部品 ---------------------------------------------------------

ARROW_LEN = 6.0
ARROW_HALF = 2.2


def _fmt(value: float) -> str:
    """寸法値の表記。小数第 2 位まで、末尾の 0 は落とす。

    桁数は BOM カタログの仕様表と揃える。図と表で違う丸め方をすると、
    同じ寸法が別の値に見える。
    """
    text = f"{value:.2f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _path(points: Polyline) -> str:
    head = f"M {points[0][0]:.2f} {points[0][1]:.2f}"
    rest = " ".join(f"L {x:.2f} {y:.2f}" for x, y in points[1:])
    return f"{head} {rest}".strip()


def _arrow(tip_x: float, tip_y: float, dx: float, dy: float) -> str:
    """矢羽。(dx, dy) は矢の向く単位ベクトル。"""
    bx, by = tip_x - dx * ARROW_LEN, tip_y - dy * ARROW_LEN
    px, py = -dy * ARROW_HALF, dx * ARROW_HALF
    pts = f"{tip_x:.2f},{tip_y:.2f} {bx + px:.2f},{by + py:.2f} {bx - px:.2f},{by - py:.2f}"
    return f'<polygon class="dim" points="{pts}"/>'


def _dim_horizontal(x1: float, x2: float, y: float, ext_y: float, text: str) -> str:
    """水平寸法。ext_y は寸法補助線を引き出す図形側の Y。"""
    return "".join(
        [
            f'<line class="ext" x1="{x1:.2f}" y1="{ext_y:.2f}" x2="{x1:.2f}" y2="{y + 4:.2f}"/>',
            f'<line class="ext" x1="{x2:.2f}" y1="{ext_y:.2f}" x2="{x2:.2f}" y2="{y + 4:.2f}"/>',
            f'<line class="dim" x1="{x1:.2f}" y1="{y:.2f}" x2="{x2:.2f}" y2="{y:.2f}"/>',
            _arrow(x1, y, -1, 0),
            _arrow(x2, y, 1, 0),
            f'<text class="dimtext" x="{(x1 + x2) / 2:.2f}" y="{y - 5:.2f}" '
            f'text-anchor="middle">{_esc(text)}</text>',
        ]
    )


def _dim_vertical(y1: float, y2: float, x: float, ext_x: float, text: str) -> str:
    """垂直寸法。ext_x は寸法補助線を引き出す図形側の X。"""
    mid = (y1 + y2) / 2
    return "".join(
        [
            f'<line class="ext" x1="{ext_x:.2f}" y1="{y1:.2f}" x2="{x - 4:.2f}" y2="{y1:.2f}"/>',
            f'<line class="ext" x1="{ext_x:.2f}" y1="{y2:.2f}" x2="{x - 4:.2f}" y2="{y2:.2f}"/>',
            f'<line class="dim" x1="{x:.2f}" y1="{y1:.2f}" x2="{x:.2f}" y2="{y2:.2f}"/>',
            _arrow(x, y1, 0, -1),
            _arrow(x, y2, 0, 1),
            f'<text class="dimtext" x="{x - 5:.2f}" y="{mid:.2f}" text-anchor="middle" '
            f'transform="rotate(-90 {x - 5:.2f} {mid:.2f})">{_esc(text)}</text>',
        ]
    )


def _scale_bar(x: float, y: float, scale: float) -> str:
    """縮尺の目安。画面上の 1 mm は環境で変わるため、長さを明示した棒で示す。"""
    for length in (100, 50, 20, 10, 5, 2, 1):
        if length * scale <= 90:
            break
    px = length * scale
    return "".join(
        [
            f'<line class="scalebar" x1="{x:.2f}" y1="{y:.2f}" x2="{x + px:.2f}" y2="{y:.2f}"/>',
            f'<line class="scalebar" x1="{x:.2f}" y1="{y - 3:.2f}" x2="{x:.2f}" y2="{y + 3:.2f}"/>',
            f'<line class="scalebar" x1="{x + px:.2f}" y1="{y - 3:.2f}" '
            f'x2="{x + px:.2f}" y2="{y + 3:.2f}"/>',
            f'<text class="note" x="{x + px + 6:.2f}" y="{y + 4:.2f}">{length} mm</text>',
        ]
    )


# --- 三面図 -------------------------------------------------------------

PAD_LEFT = 54.0
PAD_RIGHT = 14.0
PAD_TOP = 22.0
PAD_BOTTOM = 46.0
GAP = 26.0  # 図と図のすきま


@dataclass(frozen=True)
class Mark:
    """図に重ねる注記（コネクタ開口など）。

    face の向きから、実寸で現れる図（正面図・平面図・右側面図）を選んで描く。
    pos は部品座標の中心、size は面内の (幅, 高さ)。
    """

    label: str
    face: str
    pos: tuple[float, float, float]
    size: tuple[float, float]
    # 開口が面からはみ出す場合は枠を描かない。図をまたいで線が伸び、
    # 別の図の形状と誤読されるため。位置だけを番号で示す。
    outline: bool = True


_FACE_VIEW = {"+x": "right", "-x": "right", "+y": "front", "-y": "front",
              "+z": "top", "-z": "top"}


def three_view_svg(
    part: Part,
    *,
    width: float = 560.0,
    max_height: float = 360.0,
    max_scale: float = 14.0,
    marks: Sequence[Mark] = (),
) -> str:
    """部品の三面図（第三角法）を SVG 文字列で返す。

    尺度は図が枠に収まるよう自動で決め、実寸が読めるよう寸法とスケールバーを添える。
    """
    bbox = part.bounding_box()
    w, d, h = bbox.size.X, bbox.size.Y, bbox.size.Z
    x0, y0, z0 = bbox.min.X, bbox.min.Y, bbox.min.Z
    x1, y1, z1 = bbox.max.X, bbox.max.Y, bbox.max.Z

    avail_w = width - PAD_LEFT - PAD_RIGHT - GAP
    avail_h = max_height - PAD_TOP - PAD_BOTTOM - GAP
    scale = min(avail_w / (w + d), avail_h / (d + h), max_scale)

    left = PAD_LEFT
    right = PAD_LEFT + w * scale + GAP
    top = PAD_TOP
    front_top = PAD_TOP + d * scale + GAP
    height = front_top + h * scale + PAD_BOTTOM
    # 図が縦で決まったときに右が大きく余らないよう、枠を中身に合わせて詰める
    # （スケールバーとその文字が入る幅は残す）
    width = min(width, max(right + d * scale + PAD_RIGHT, PAD_LEFT + 170))

    # 図面座標 (u, v)[mm] → SVG 座標[px]
    def place(view_key: str, u: float, v: float) -> tuple[float, float]:
        if view_key == "top":
            return left + (u - x0) * scale, top + (y1 - v) * scale
        if view_key == "front":
            return left + (u - x0) * scale, front_top + (z1 - v) * scale
        return right + (u - y0) * scale, front_top + (z1 - v) * scale

    out: list[str] = [
        f'<svg class="tv" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img">'
    ]

    for view in VIEWS:
        visible, hidden = project_view(part, view)
        out.append(f'<g data-view="{view.key}">')
        for polyline in hidden:
            out.append(
                f'<path class="hidden" d="{_path([place(view.key, u, v) for u, v in polyline])}"/>'
            )
        for polyline in visible:
            out.append(
                f'<path class="edge" d="{_path([place(view.key, u, v) for u, v in polyline])}"/>'
            )
        out.append("</g>")

    # コネクタなどの注記。実寸で現れる図にだけ重ねる
    for i, mark in enumerate(marks, start=1):
        view_key = _FACE_VIEW.get(mark.face)
        if view_key is None:
            continue
        px, py, pz = mark.pos
        mu, mv = {
            "front": (px, pz),
            "top": (px, py),
            "right": (py, pz),
        }[view_key]
        mw, mh = mark.size
        cx, cy = place(view_key, mu, mv)
        if mark.outline:
            out.append(
                f'<rect class="mark" x="{cx - mw * scale / 2:.2f}" y="{cy - mh * scale / 2:.2f}" '
                f'width="{mw * scale:.2f}" height="{mh * scale:.2f}"/>'
            )
        out.append(f'<circle class="marknum" cx="{cx:.2f}" cy="{cy:.2f}" r="7"/>')
        out.append(
            f'<text class="marknumtext" x="{cx:.2f}" y="{cy + 3.5:.2f}" '
            f'text-anchor="middle">{i}</text>'
        )

    # 寸法（W・D・H を 1 回ずつ）
    out.append(
        _dim_horizontal(left, left + w * scale, front_top + h * scale + 22,
                        front_top + h * scale, f"W {_fmt(w)}")
    )
    out.append(
        _dim_vertical(front_top, front_top + h * scale, PAD_LEFT - 20, left, f"H {_fmt(h)}")
    )
    out.append(
        _dim_vertical(top, top + d * scale, PAD_LEFT - 20, left, f"D {_fmt(d)}")
    )

    # 図の名前
    for view, (lx, ly) in (
        (VIEWS[0], (left, top - 7)),
        (VIEWS[1], (left, front_top - 7)),
        (VIEWS[2], (right, front_top - 7)),
    ):
        out.append(f'<text class="viewlabel" x="{lx:.2f}" y="{ly:.2f}">{view.label}</text>')

    out.append(_scale_bar(left, height - 12, scale))
    out.append("</svg>")
    return "".join(out)


# --- 締結部品（ネジ）の略図 ---------------------------------------------


def fastener_svg(nominal: float, length: float, *, max_width: float = 560.0) -> str:
    """ネジの側面略図。呼び径と長さ（首下）を寸法で示す。

    ネジは回転対称なので三面図にしても情報が増えない。頭の形・ねじ山は
    製品によるため、規格品の呼び径と首下長さだけを図示する略図とする。
    """
    height = 150.0
    head_d = nominal * 1.9
    head_h = nominal * 0.7
    # 横は枠に収める。縦は頭の径が図からはみ出さないように抑える
    scale = min((max_width - 180) / max(length + head_h, 1.0), 80.0 / head_d, 26.0)

    axis_y = 62.0
    x_head = 80.0
    x_neck = x_head + head_h * scale
    x_tip = x_neck + length * scale
    width = max(x_tip + 96, 320.0)

    shaft_half = nominal * scale / 2
    head_half = head_d * scale / 2

    parts = [
        f'<svg class="tv" viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" '
        f'height="{height:.0f}" xmlns="http://www.w3.org/2000/svg" role="img">',
        # 頭（なべ頭を想定した角丸）
        f'<rect class="edge fill" x="{x_head:.2f}" y="{axis_y - head_half:.2f}" '
        f'width="{head_h * scale:.2f}" height="{head_half * 2:.2f}" '
        f'rx="{min(head_h * scale * 0.55, head_half * 0.35):.2f}"/>',
        # 軸部（首下）
        f'<rect class="edge fill" x="{x_neck:.2f}" y="{axis_y - shaft_half:.2f}" '
        f'width="{length * scale:.2f}" height="{shaft_half * 2:.2f}"/>',
        # 中心線
        f'<line class="center" x1="{x_head - 14:.2f}" y1="{axis_y:.2f}" '
        f'x2="{x_tip + 14:.2f}" y2="{axis_y:.2f}"/>',
        _dim_horizontal(x_neck, x_tip, axis_y + shaft_half + 34, axis_y + shaft_half,
                        f"L {_fmt(length)}（首下）"),
        _dim_vertical(axis_y - shaft_half, axis_y + shaft_half, x_tip + 34, x_tip,
                      f"φ{_fmt(nominal)}"),
        f'<text class="viewlabel" x="16" y="{axis_y - 26:.2f}">側面図</text>',
        f'<text class="note" x="16" y="{height - 14:.2f}">'
        f'頭の形・ねじ山は略図（製品による）</text>',
        "</svg>",
    ]
    return "".join(parts)
