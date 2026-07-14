"""検証関数そのものの検証。

各関数について「正常な形状を通すこと」と「異常な形状を確実に落とすこと」の両方を確認する。
落とせない検証関数は存在価値がないため、失敗ケースのテストを必ず対にする。
"""

import pytest
from build123d import Align, Box, Cylinder, Pos

from hwlib import verify
from hwlib.features import SCREWS, clearance_hole, tapping_boss


# --------------------------------------------------------------------------
# assert_cut: 効かなかった減算を検出できるか
# --------------------------------------------------------------------------
def test_assert_cut_passes_when_hole_is_actually_cut():
    box = Box(40, 30, 10)
    cut = box - Cylinder(radius=3, height=20)
    verify.assert_cut(box, cut, name="穴")


def test_assert_cut_detects_missed_cut():
    """部品の外で減算しても build123d は例外を出さない。それを検出できること。"""
    box = Box(40, 30, 10)
    missed = box - Pos(500, 0, 0) * Cylinder(radius=3, height=20)
    assert missed.volume == box.volume  # 例外は出ず、体積も変わらない

    with pytest.raises(AssertionError, match="減算が効いていない"):
        verify.assert_cut(box, missed, name="穴")


# --------------------------------------------------------------------------
# assert_contained: 外装からのはみ出しを検出できるか
# --------------------------------------------------------------------------
def test_assert_contained_passes_when_inside():
    verify.assert_contained(Box(10, 10, 10), Box(30, 30, 30))


def test_assert_contained_detects_part_sticking_out():
    outside = Pos(14, 0, 0) * Box(10, 10, 10)
    with pytest.raises(AssertionError, match="はみ出している"):
        verify.assert_contained(outside, Box(30, 30, 30), name="基板")


# --------------------------------------------------------------------------
# assert_no_interference: 部品同士の干渉を検出できるか
# --------------------------------------------------------------------------
def test_assert_no_interference_passes_when_apart():
    verify.assert_no_interference({"a": Box(10, 10, 10), "b": Pos(20, 0, 0) * Box(10, 10, 10)})


def test_assert_no_interference_detects_overlap():
    with pytest.raises(AssertionError, match="干渉しています"):
        verify.assert_no_interference({"a": Box(10, 10, 10), "b": Pos(5, 0, 0) * Box(10, 10, 10)})


def test_assert_clearance_detects_insufficient_gap():
    a, b = Box(10, 10, 10), Pos(12, 0, 0) * Box(10, 10, 10)  # 隙間 2mm
    verify.assert_clearance(a, b, 2.0)
    with pytest.raises(AssertionError, match="隙間が"):
        verify.assert_clearance(a, b, 5.0)


# --------------------------------------------------------------------------
# assert_tool_access: ドライバーが入らない設計を検出できるか
# --------------------------------------------------------------------------
def test_assert_tool_access_passes_when_clear():
    verify.assert_tool_access((0, 0, 0), (0, 0, 1), {"基板": Pos(50, 0, 0) * Box(20, 20, 5)})


def test_assert_tool_access_detects_blocking_part():
    """ネジの真上に部品があると締められない。"""
    blocker = Pos(0, 0, 20) * Box(30, 30, 5)
    with pytest.raises(AssertionError, match="ドライバー"):
        verify.assert_tool_access((0, 0, 0), (0, 0, 1), {"ふさぐ部品": blocker})


# --------------------------------------------------------------------------
# assert_insertable: 入れられない部品を検出できるか
# --------------------------------------------------------------------------
def test_assert_insertable_passes_when_path_is_clear():
    part = Box(10, 10, 10)
    verify.assert_insertable("部品", part, (0, 0, 1), {"横の壁": Pos(30, 0, 0) * Box(5, 30, 30)}, distance=50)


def test_assert_insertable_detects_blocked_path():
    """真上に蓋があると、上から入れることも取り出すこともできない。"""
    part = Box(10, 10, 10)
    lid = Pos(0, 0, 20) * Box(40, 40, 3)
    with pytest.raises(AssertionError, match="取り出せない"):
        verify.assert_insertable("部品", part, (0, 0, 1), {"蓋": lid}, distance=50)


# --------------------------------------------------------------------------
# assert_connector_access: 開口の無い外装を検出できるか
# --------------------------------------------------------------------------
def test_assert_connector_access_passes_with_opening():
    wall = Box(40, 4, 20, align=(Align.CENTER, Align.MIN, Align.CENTER))
    wall -= Pos(0, 0, 0) * Box(12, 10, 6, align=(Align.CENTER, Align.MIN, Align.CENTER))  # 開口
    verify.assert_connector_access((0, 0, 0), "+y", (8, 4), wall, depth=10)


def test_assert_connector_access_detects_missing_opening():
    wall = Box(40, 4, 20, align=(Align.CENTER, Align.MIN, Align.CENTER))  # 開口なし
    with pytest.raises(AssertionError, match="開口がない"):
        verify.assert_connector_access((0, 0, 0), "+y", (8, 4), wall, depth=10)


def test_assert_connector_access_detects_missing_opening_even_when_wall_is_far():
    """コネクタが壁から離れていても見逃さないこと。

    プローブの長さが足りないと壁に届かず、開口が無くても合格してしまう。
    """
    far_wall = Pos(0, 50, 0) * Box(40, 4, 20, align=(Align.CENTER, Align.MIN, Align.CENTER))
    with pytest.raises(AssertionError, match="開口がない"):
        verify.assert_connector_access((0, 0, 0), "+y", (8, 4), far_wall, depth=5)


# --------------------------------------------------------------------------
# assert_boss_screw_fit: タッピングネジの寸法
# --------------------------------------------------------------------------
@pytest.mark.parametrize("size", sorted(SCREWS))
def test_screw_table_is_self_consistent(size):
    """SCREWS の値が、自分自身の設計ルールを満たしていること。"""
    s = SCREWS[size]
    verify.assert_boss_screw_fit(
        screw_dia=s.nominal,
        pilot_dia=s.pilot_dia,
        boss_outer_dia=s.boss_outer_dia,
        boss_depth=s.min_engagement + 1.0,
        screw_len=s.min_engagement + 2.0,
        plate_thickness=2.0,
        name=size,
    )


def test_boss_screw_fit_detects_oversized_pilot_hole():
    """下穴が太すぎるとネジが効かない。"""
    with pytest.raises(AssertionError, match="下穴"):
        verify.assert_boss_screw_fit(
            screw_dia=3.0, pilot_dia=3.0, boss_outer_dia=6.6,
            boss_depth=7.0, screw_len=8.0, plate_thickness=2.0,
        )


def test_boss_screw_fit_detects_shallow_engagement():
    """ねじ込み深さが足りないと保持力が出ない。"""
    with pytest.raises(AssertionError, match="ねじ込み深さ"):
        verify.assert_boss_screw_fit(
            screw_dia=3.0, pilot_dia=2.4, boss_outer_dia=6.6,
            boss_depth=3.0, screw_len=5.0, plate_thickness=2.0,
        )


def test_boss_screw_fit_detects_screw_too_long():
    """ネジがボスの底を突き抜ける。"""
    with pytest.raises(AssertionError, match="突き抜ける"):
        verify.assert_boss_screw_fit(
            screw_dia=3.0, pilot_dia=2.4, boss_outer_dia=6.6,
            boss_depth=6.0, screw_len=20.0, plate_thickness=2.0,
        )


# --------------------------------------------------------------------------
# 形状・メッシュ
# --------------------------------------------------------------------------
def test_assert_valid_and_watertight():
    part = Box(20, 20, 10) - Cylinder(radius=3, height=20)
    verify.assert_valid(part)
    verify.assert_watertight(part)


def test_assert_bbox_detects_wrong_size():
    part = Box(20, 20, 10)
    verify.assert_bbox(part, (20, 20, 10))
    with pytest.raises(AssertionError, match="X 方向"):
        verify.assert_bbox(part, (25, 20, 10))


# --------------------------------------------------------------------------
# features
# --------------------------------------------------------------------------
def test_tapping_boss_has_pilot_hole():
    """ボスに下穴が実際に開いていること。"""
    s = SCREWS["M3"]
    solid = Cylinder(radius=s.boss_outer_dia / 2, height=10, align=(Align.CENTER, Align.CENTER, Align.MIN))
    boss = tapping_boss("M3", height=10)
    verify.assert_valid(boss, "M3 ボス")
    verify.assert_cut(solid, boss, name="ボスの下穴")


def test_tapping_boss_rejects_too_deep_pilot():
    with pytest.raises(ValueError, match="ボス高さ"):
        tapping_boss("M3", height=5, depth=8)


def test_clearance_hole_is_larger_than_screw():
    assert SCREWS["M3"].clearance_dia > SCREWS["M3"].nominal
    hole = clearance_hole("M3", thickness=3)
    verify.assert_bbox(hole, (3.4, 3.4, 3.0), tol=0.05)
