"""設計の検証。

Claude は形状を直接見られないため、正しさはここで機械的に確認する。
すべての assert_* は失敗時に AssertionError を送出し、何がどう違うかを数値で示す。

重要: build123d のブール減算は、対象に当たらなくても例外を出さない。
体積も面数も変わらないまま処理が「成功」する。assert_cut() で毎回確認すること。
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import trimesh
from build123d import Align, Box, Cylinder, Part, Plane, Pos, Vector, export_stl

# 体積比較の許容誤差 (mm^3)。OCCT の数値誤差を吸収する。
EPS_VOLUME = 1e-3


# --------------------------------------------------------------------------
# 基本
# --------------------------------------------------------------------------
def assert_valid(part: Part, name: str = "part") -> None:
    """トポロジが健全であること。is_valid はメソッドではなくプロパティ。"""
    assert part.is_valid, f"{name}: 形状が不正（OCCT のトポロジ検査に失敗）"
    assert part.volume > 0, f"{name}: 体積が 0"


def assert_cut(before: Part, after: Part, *, name: str = "cut", min_removed: float = 0.1) -> None:
    """ブール減算が実際に効いたことを確認する。

    穴あけ対象から外れた位置で減算しても例外は出ない。体積が減ったかで判定する。
    """
    removed = before.volume - after.volume
    assert removed >= min_removed, (
        f"{name}: 減算が効いていない（除去された体積 {removed:.4f} mm^3 < {min_removed}）。"
        "切り欠きの位置・向き・サイズが対象から外れている可能性がある"
    )


def assert_bbox(part: Part, expected: tuple[float, float, float], *, tol: float = 0.01, name: str = "part") -> None:
    """外形寸法が期待どおりであること。"""
    bb = part.bounding_box()
    actual = (bb.size.X, bb.size.Y, bb.size.Z)
    for axis, a, e in zip("XYZ", actual, expected):
        assert abs(a - e) <= tol, (
            f"{name}: {axis} 方向の外形が {a:.3f} mm（期待 {e:.3f} mm、許容 ±{tol}）"
        )


def assert_volume(part: Part, expected: float, *, rel_tol: float = 0.02, name: str = "part") -> None:
    """体積が期待どおりであること。"""
    assert math.isclose(part.volume, expected, rel_tol=rel_tol), (
        f"{name}: 体積が {part.volume:.2f} mm^3（期待 {expected:.2f} mm^3、許容 ±{rel_tol:.0%}）"
    )


# --------------------------------------------------------------------------
# A. 必要な部品がすべて含まれているか
# --------------------------------------------------------------------------
def assert_all_parts_placed(bom, placed: dict[str, Part]) -> None:
    """BOM の全部品がアセンブリに配置されていること。

    設計中に忘れられた部品を検出する。
    ネジなど geometric: false の部品は配置対象外として扱う。
    """
    missing = bom.geometric_ids - set(placed)
    assert not missing, (
        f"BOM にあるがアセンブリに配置されていない部品: {sorted(missing)}。"
        "設計に含めるか、BOM で geometric: false にすること"
    )
    unknown = set(placed) - bom.ids
    assert not unknown, (
        f"アセンブリにあるが BOM にない部品: {sorted(unknown)}。BOM に追加すること"
    )


# --------------------------------------------------------------------------
# B. 外装に収まり、組み立てられるか
# --------------------------------------------------------------------------
def assert_contained(part: Part, container: Part, *, name: str = "part", tol: float = EPS_VOLUME) -> None:
    """part が container の内側に完全に収まっていること。"""
    outside = (part - container).volume
    assert outside <= tol, (
        f"{name}: 外装の内側からはみ出している（はみ出し体積 {outside:.3f} mm^3）"
    )


def overlap_volume(a: Part, b: Part) -> float:
    """2 つの形状が重なっている体積。重なりがなければ 0。"""
    return (a & b).volume


def assert_no_interference(parts: dict[str, Part], *, allow: set[frozenset[str]] | None = None, tol: float = EPS_VOLUME) -> None:
    """部品同士が干渉していないこと（総当たり）。

    allow に入れたペアは意図的な接触として無視する（例: 基板とボスの座面）。
    """
    allow = allow or set()
    names = sorted(parts)
    collisions = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if frozenset((a, b)) in allow:
                continue
            v = overlap_volume(parts[a], parts[b])
            if v > tol:
                collisions.append(f"{a} <-> {b}: {v:.3f} mm^3")
    assert not collisions, "部品が干渉しています:\n" + "\n".join(f"  - {c}" for c in collisions)


def assert_clearance(a: Part, b: Part, min_gap: float, *, name: str = "") -> None:
    """2 つの部品が規定の隙間を保っていること。"""
    gap = a.distance_to(b)
    assert gap >= min_gap - 1e-6, (
        f"{name or 'clearance'}: 隙間が {gap:.3f} mm しかない（必要 {min_gap} mm）"
    )


def _unit(direction: tuple[float, float, float]) -> Vector:
    v = Vector(*direction)
    return v / v.length


def swept_volume(part: Part, direction: tuple[float, float, float], distance: float, *, steps: int = 12) -> Part:
    """part を direction 方向に distance だけ動かしたときの掃引体積。

    部品を出し入れする経路が空いているかを調べるために使う。
    段階的に複製して和を取るため、実際の掃引体積以上（安全側）になる。
    """
    d = _unit(direction)
    swept = part
    for i in range(1, steps + 1):
        swept += Pos(*(d * (distance * i / steps))) * part
    return swept


def assert_insertable(
    name: str,
    part: Part,
    direction: tuple[float, float, float],
    obstacles: dict[str, Part],
    *,
    distance: float = 100.0,
    tol: float = EPS_VOLUME,
) -> None:
    """部品を direction 方向に取り出せる（＝逆順に入れられる）こと。

    経路上に障害物があれば、収まってはいても組み立てられない。
    """
    path = swept_volume(part, direction, distance) - part
    blocked = []
    for other, shape in obstacles.items():
        if other == name:
            continue
        v = overlap_volume(path, shape)
        if v > tol:
            blocked.append(f"{other}: {v:.3f} mm^3")
    assert not blocked, (
        f"{name}: {direction} 方向に取り出せない（組み立て順序が成立しない）。"
        "経路上の障害物:\n" + "\n".join(f"  - {b}" for b in blocked)
    )


def assert_tool_access(
    screw_pos: tuple[float, float, float],
    direction: tuple[float, float, float],
    obstacles: dict[str, Part],
    *,
    name: str = "screw",
    driver_dia: float = 6.0,
    driver_len: float = 60.0,
    tol: float = EPS_VOLUME,
) -> None:
    """ネジを締めるドライバーが入る空間があること。

    screw_pos（ネジ頭の位置）から direction 方向にドライバーを表す円柱を伸ばし、
    他の部品と干渉しないことを確認する。ここが通らない設計は組み立てられない。
    """
    d = _unit(direction)
    driver = Plane(origin=screw_pos, z_dir=d) * Cylinder(
        radius=driver_dia / 2, height=driver_len, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    blocked = []
    for other, shape in obstacles.items():
        v = overlap_volume(driver, shape)
        if v > tol:
            blocked.append(f"{other}: {v:.3f} mm^3")
    assert not blocked, (
        f"{name} {screw_pos}: ドライバー（φ{driver_dia} × {driver_len} mm）が入らない。"
        "干渉:\n" + "\n".join(f"  - {b}" for b in blocked)
    )


# 面の向き → 外向き単位ベクトル
FACE_DIR = {
    "+x": (1, 0, 0), "-x": (-1, 0, 0),
    "+y": (0, 1, 0), "-y": (0, -1, 0),
    "+z": (0, 0, 1), "-z": (0, 0, -1),
}


def face_plane(origin: tuple[float, float, float], face: str) -> Plane:
    """外装の面に貼り付く平面。z 軸が外向き、x 軸が開口の「幅」方向。

    Plane に z_dir だけを渡すと x 軸の向きが自動で決まり、開口の幅と高さが
    どの軸に対応するか定まらない。開口を作る側（features.rect_opening）と
    確認する側（assert_connector_access）で解釈がずれるため、ここで固定する。

    側面（±x, ±y）: 幅 = 水平方向、高さ = Z 方向
    天面・底面（±z）: 幅 = X 方向、高さ = Y 方向
    """
    x_dir = (0, 1, 0) if face in ("+x", "-x") else (1, 0, 0)
    return Plane(origin=origin, x_dir=x_dir, z_dir=FACE_DIR[face])


def assert_connector_access(
    connector_pos: tuple[float, float, float],
    face: str,
    opening_size: tuple[float, float],
    enclosure: Part,
    *,
    depth: float = 10.0,
    name: str = "connector",
    tol: float = EPS_VOLUME,
) -> None:
    """コネクタの位置に外装の開口があり、ケーブルを挿せること。

    コネクタ位置から外向きに伸ばした角柱が外装と干渉しなければ、開口がある。
    """
    w, h = opening_size

    # プローブが壁に届かないと、開口が無くても合格してしまう。
    # 外装の外まで必ず貫くよう、必要な長さを外装のバウンディングボックスから計算する。
    bb = enclosure.bounding_box()
    px, py, pz = connector_pos
    reach = {
        "+x": bb.max.X - px, "-x": px - bb.min.X,
        "+y": bb.max.Y - py, "-y": py - bb.min.Y,
        "+z": bb.max.Z - pz, "-z": pz - bb.min.Z,
    }[face] + 2.0
    length = max(depth, reach)

    probe = face_plane(connector_pos, face) * Box(
        w, h, length, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    v = overlap_volume(probe, enclosure)
    assert v <= tol, (
        f"{name} {connector_pos} ({face} 面): 外装に開口がない、または開口が小さい"
        f"（外装と {v:.3f} mm^3 干渉）。ケーブルを挿せない"
    )


def assert_boss_screw_fit(
    *,
    screw_dia: float,
    pilot_dia: float,
    boss_outer_dia: float,
    boss_depth: float,
    screw_len: float,
    plate_thickness: float,
    name: str = "boss",
) -> None:
    """タッピングネジ（樹脂直締め）の寸法が成立すること。

    下穴が太すぎるとネジが効かず、細すぎるとボスが割れる。
    ねじ込み深さが足りなければ保持力が出ない。
    """
    lo, hi = screw_dia * 0.75, screw_dia * 0.85
    assert lo <= pilot_dia <= hi, (
        f"{name}: 下穴 φ{pilot_dia} が不適切（M{screw_dia} には φ{lo:.2f}〜φ{hi:.2f}）。"
        "太すぎるとネジが効かず、細すぎるとボスが割れる"
    )

    # ボスの肉厚は呼び径の 0.6 倍以上（一般的な樹脂ボスの設計指針）
    min_wall = screw_dia * 0.6
    wall = (boss_outer_dia - pilot_dia) / 2
    assert wall >= min_wall, (
        f"{name}: ボスの肉厚 {wall:.2f} mm が薄い（呼び径の 0.6 倍 = {min_wall:.2f} mm 以上必要）。"
        "ねじ込み時に割れる"
    )

    engagement = min(boss_depth, screw_len - plate_thickness)
    assert engagement >= screw_dia * 2, (
        f"{name}: ねじ込み深さ {engagement:.2f} mm が不足（呼び径の 2 倍 = "
        f"{screw_dia * 2:.2f} mm 以上必要）。ネジ長 {screw_len} / 板厚 {plate_thickness} / ボス深さ {boss_depth}"
    )

    assert screw_len - plate_thickness <= boss_depth, (
        f"{name}: ネジがボスの底を突き抜ける"
        f"（ねじ込み長 {screw_len - plate_thickness:.2f} mm > ボス深さ {boss_depth} mm）"
    )


# --------------------------------------------------------------------------
# C. 3D プリントできるか
# --------------------------------------------------------------------------
def assert_watertight(part: Part, *, name: str = "part", tolerance: float = 0.05) -> None:
    """STL に出力したメッシュが水密であること。3D プリントの前提条件。"""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "check.stl"
        export_stl(part, str(path), tolerance=tolerance)
        mesh = trimesh.load(str(path))
    assert mesh.is_watertight, f"{name}: メッシュが水密でない（穴が開いている）。スライスできない"
    assert mesh.is_winding_consistent, f"{name}: 面の向きが一貫していない"


def check_min_wall(part: Part, min_wall: float, *, name: str = "part") -> list[str]:
    """薄肉部の検出（警告）。

    収縮オフセットで消える体積があれば薄肉が疑われる。
    OCCT のオフセットは失敗しやすいため、これ単独で設計 NG とは判定しない。
    """
    try:
        shrunk = part.offset_3d(None, -min_wall / 2)
    except Exception as e:  # noqa: BLE001 — オフセット失敗自体が有用な情報
        return [f"{name}: 肉厚チェックを実行できなかった（{type(e).__name__}: {e}）。目視で確認すること"]
    if shrunk is None or shrunk.volume <= 0:
        return [f"{name}: 収縮で形状が消えた。全体が {min_wall} mm 未満の可能性がある"]
    return []


def check_overhang(part: Part, *, max_angle: float = 45.0, name: str = "part") -> list[str]:
    """サポートが必要な下向き面の検出（警告）。

    印刷方向は +Z を上とみなす。
    """
    warnings = []
    limit = math.cos(math.radians(180 - max_angle))
    for face in part.faces():
        n = face.normal_at()
        if n.Z < limit and face.area > 1.0:
            warnings.append(
                f"{name}: 面積 {face.area:.1f} mm^2 の下向き面（法線 Z={n.Z:.2f}）— サポートが必要"
            )
    return warnings
