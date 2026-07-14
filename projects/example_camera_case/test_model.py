"""example_camera_case の検証。

確認すること:
  A. BOM の部品がすべて設計に含まれているか
  B. 外装に収まり、ネジで組み立てられるか
  C. 3D プリントできるか
"""

import pytest
from build123d import Pos

from hwlib import verify
from hwlib.features import SCREWS
from projects.example_camera_case.model import (
    BOM,
    P,
    board_boss_positions,
    build_base,
    build_lid,
    interior,
    lid_boss_positions,
    place_components,
    screw_heads,
)


@pytest.fixture(scope="module")
def base():
    return build_base()


@pytest.fixture(scope="module")
def lid():
    return build_lid()


@pytest.fixture(scope="module")
def components():
    return place_components()


# --------------------------------------------------------------------------
# A. 必要な部品がすべて含まれているか
# --------------------------------------------------------------------------
def test_all_bom_parts_are_placed(components):
    verify.assert_all_parts_placed(BOM, components)


def test_every_category_is_accounted_for():
    """BOM の読み込み時点で全カテゴリの検討が済んでいること（load_bom が保証）。"""
    assert BOM.ids  # 読み込めた時点で検証は通っている
    assert "actuator" in BOM.excluded  # 不要と判断した理由が残っている


# --------------------------------------------------------------------------
# B. 外装に収まり、組み立てられるか
# --------------------------------------------------------------------------
def test_shapes_are_valid(base, lid):
    verify.assert_valid(base, "ケース本体")
    verify.assert_valid(lid, "蓋")


def test_all_components_fit_inside(components):
    """すべての部品が内寸に収まっていること。"""
    cavity = interior()
    for name, part in components.items():
        verify.assert_contained(part, cavity, name=name)


def test_no_interference(base, components):
    """部品同士、および部品とケース（壁・ボス）が干渉しないこと。"""
    verify.assert_no_interference({"base": base, **components})


def test_battery_keeps_clearance_from_camera(components):
    """バッテリーは膨らむため、隣の部品との隙間を確保する。"""
    verify.assert_clearance(
        components["battery"], components["camera"], BOM["battery"].clearance, name="バッテリー↔カメラ"
    )


def test_connector_has_opening(base, components):
    """電源コネクタの位置にケースの開口があり、ケーブルを挿せること。"""
    conn = BOM["pi_zero"].connectors[0]
    bx, by, bz = P.board_pos
    cx, cy, cz = conn.pos
    verify.assert_connector_access(
        (bx + cx, by + cy, bz + cz),
        conn.face,
        conn.size,
        base,
        depth=conn.depth,
        name=conn.name,
    )


def test_lens_has_opening(lid, components):
    """カメラのレンズが蓋の穴から外を見られること。"""
    cam = BOM["camera"]
    cx, cy, cz = P.camera_pos
    lens_top = (cx + cam.size[0] / 2, cy + cam.size[1] / 2, cz + cam.size[2])
    verify.assert_connector_access(
        lens_top, "+z", (8.0, 8.0), lid, depth=10.0, name="レンズ"
    )


def test_camera_lens_reaches_the_lid():
    """カメラのレンズ面が蓋の内側に接すること。

    箱の底に置いただけではレンズと蓋が離れ、視野がケラれるうえ固定もされない。
    """
    cz = P.camera_pos[2]
    lens_top = cz + BOM["camera"].size[2]
    assert lens_top == pytest.approx(P.inner_h), (
        f"レンズ面 z={lens_top} が蓋の内側 z={P.inner_h} に届いていない"
    )


def test_every_component_declares_how_it_is_retained():
    """すべての部品に固定方法が宣言されていること。

    干渉チェックは「箱の中で部品が浮いている」状態を素通りさせる。
    収まっていることと固定されていることは別物なので、宣言を必須にする。
    ネジやケーブル自体（geometric: false）は固定される側ではないため対象外。
    """
    for c in BOM.components:
        if c.geometric:
            assert c.retention, f"{c.id}: 固定方法が宣言されていない"


@pytest.mark.parametrize("screw_size", ["M3", "M2.6"])
def test_tapping_screws_fit(screw_size):
    """タッピングネジの下穴・ねじ込み深さ・ネジ長が成立すること。"""
    s = SCREWS[screw_size]
    if screw_size == P.lid_screw:
        screw_len, boss_depth, plate = P.lid_screw_len, P.lid_boss_depth, P.lid_thickness
    else:
        screw_len, boss_depth = P.board_screw_len, P.board_boss_depth
        plate = 1.6  # 基板厚

    verify.assert_boss_screw_fit(
        screw_dia=s.nominal,
        pilot_dia=s.pilot_dia,
        boss_outer_dia=s.boss_outer_dia,
        boss_depth=boss_depth,
        screw_len=screw_len,
        plate_thickness=plate,
        name=f"{screw_size} ボス",
    )


def test_driver_can_reach_every_screw(base, components):
    """すべてのネジをドライバーで締められること。

    組み立て順は「部品を入れる → 基板を留める → 蓋を閉じて留める」。
    基板のネジを締める時点で蓋はまだ無いため、蓋は障害物に含めない。
    ケース本体（壁・ボス・リブ）は障害物に含める。
    """
    obstacles = {"base": base, **components}
    for screw_size, heads in screw_heads().items():
        for pos in heads:
            verify.assert_tool_access(
                pos,
                (0, 0, 1),
                obstacles,
                name=f"{screw_size} ネジ",
                driver_dia=P.driver_dia,
            )


def test_every_component_can_be_inserted(base, components):
    """すべての部品を上から入れられること（蓋を閉じる前）。

    収まっていても、経路がふさがっていれば組み立てられない。
    """
    obstacles = {"base": base, **components}
    for name, part in components.items():
        verify.assert_insertable(name, part, (0, 0, 1), obstacles, distance=60)


# --------------------------------------------------------------------------
# C. 3D プリントできるか
# --------------------------------------------------------------------------
def test_printable_parts_are_watertight(base, lid):
    verify.assert_watertight(base, name="ケース本体")
    verify.assert_watertight(lid, name="蓋")
