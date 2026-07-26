"""Cozmo クローンの検証。

暫定寸法（provisional）のまま骨格を検証する。形状・収まり・干渉・組み立て可能性・
ネジ適合・水密は暫定値でも確認できる。実測の確定は製造ゲート
（test_ready_to_manufacture）で別途強制する。

**この検証が通っても「意図した形」であることは保証されない。**
数値検証は寸法しか見ないため、--render した PNG での目視確認と ocp_vscode での
人間の確認が別途必要（スキルの段階 5 の 2 と 3）。
"""

import warnings

import pytest

from hwlib import verify
from hwlib.features import SCREWS
from projects.cozmo_clone.model import (
    BOM,
    OUTSIDE_INTERIOR,
    P,
    PROVISIONAL,
    build_all,
    camera_view_cone,
    head_group,
    interior,
    if_board_boss_positions,
    overall_size,
    printed_parts,
    servo_placements,
    shell_boss_positions,
)


@pytest.fixture(scope="module")
def assembly():
    return build_all()


@pytest.fixture(scope="module")
def components(assembly):
    """BOM に載っている購入部品だけ（印刷部品を除く）。"""
    return {k: v for k, v in assembly.items() if k in BOM.geometric_ids}


@pytest.fixture(scope="module")
def cavity():
    return interior()


# --------------------------------------------------------------------------
# A. 必要な部品がすべて含まれているか
# --------------------------------------------------------------------------
def test_all_bom_parts_are_placed(components):
    verify.assert_all_parts_placed(BOM, components)


def test_every_category_is_accounted_for():
    """全カテゴリに部品があるか、excluded に理由があること。"""
    from hwlib.bom import CATEGORIES

    covered = {c.category for c in BOM.components} | set(BOM.excluded)
    assert not set(CATEGORIES) - covered


def test_every_component_declares_how_it_is_retained():
    """収まっているだけでなく、何で固定するかが宣言されていること。"""
    missing = [c.id for c in BOM.components if c.geometric and not c.retention]
    assert not missing, f"retention 未記入: {missing}"


def test_all_four_axes_are_xl330():
    """4 自由度すべてが XL330 であること（設計の前提）。"""
    ids = set(servo_placements())
    assert ids == {"servo_wheel_l", "servo_wheel_r", "servo_lift", "servo_head"}
    for cid in ids:
        assert BOM[cid].size == (20.0, 34.0, 26.0), f"{cid} が XL330 のケース外形でない"


# --------------------------------------------------------------------------
# B. 外装に収まり、組み立てられるか
# --------------------------------------------------------------------------
def test_shapes_are_valid(assembly):
    for name, part in printed_parts().items():
        verify.assert_valid(part, name)


def test_all_components_fit_inside(components, cavity):
    """胴体内に置く部品が内部空間に収まっていること。

    車輪・ハブ・キャスタ・首の配線・頭部の OLED は意図的に外へ出るため対象外。
    """
    for name, part in components.items():
        if name in OUTSIDE_INTERIOR:
            continue
        verify.assert_contained(part, cavity, name=name)


def test_no_interference(assembly):
    verify.assert_no_interference(assembly)


@pytest.mark.parametrize("tilt", [-25.0, -20.0, -10.0, -5.0, 0.0, 4.0, 8.0, 12.0])
def test_head_clears_everything_through_tilt_range(assembly, tilt):
    """ヘッドチルトの可動域全域で、頭部とブラケットが何にも当たらないこと。

    中立姿勢だけを見ると、可動端や中間角で天板やタイヤに当たる設計を見逃す。
    頭部に載る部品はシェルと一体で回す（置き去りにすると偽の干渉が出る）。
    """
    group = head_group(tilt)
    obstacles = {k: v for k, v in assembly.items() if k not in group}
    blocked = {
        f"{name}<->{k}": round(verify.overlap_volume(part, v), 3)
        for name, part in group.items()
        for k, v in obstacles.items()
        if verify.overlap_volume(part, v) > verify.EPS_VOLUME
    }
    assert not blocked, f"チルト {tilt:+.0f} 度で干渉: {blocked}"


@pytest.mark.parametrize("tilt", [-25.0, -10.0, 0.0, 6.0, 12.0])
def test_camera_view_is_not_blocked_by_the_head(tilt):
    """チルト可動域全域で、頭部がカメラの視界に入らないこと。

    カメラは胴体に固定で頭部と一緒に動かないため、頭部を下げると
    頭部の下端が画角に入り込む。干渉検査では検出できない種類の破綻。
    """
    cone = camera_view_cone()
    blocked = {
        name: round(verify.overlap_volume(part, cone), 1)
        for name, part in head_group(tilt).items()
        if verify.overlap_volume(part, cone) > verify.EPS_VOLUME
    }
    assert not blocked, f"チルト {tilt:+.0f} 度で頭部がカメラに写り込む: {blocked}"


def test_tilt_bracket_clears_the_tire_in_x():
    """チルトブラケットの立ち上がり部が、胴体外壁とタイヤ内側面の隙間に収まること。

    X 方向で重なっていると、チルトのたびにタイヤを削る。
    """
    wall_outer = P.inner_w + P.wall
    tire_inner = P.inner_w + P.hub_thickness
    rise_min = wall_outer + P.bracket_gap
    rise_max = rise_min + P.bracket_t
    assert rise_min > wall_outer, "ブラケットが胴体外壁に食い込んでいる"
    assert rise_max < tire_inner, (
        f"ブラケット（X {rise_min}〜{rise_max}）がタイヤ内側面 X {tire_inner} に食い込む"
    )


# 組み立て順序。後の工程の部品は、前の工程では障害物として存在しない。
# NiMH パックは上段基板より先に入れる（＝上段基板は障害物に含めない）。
ASSEMBLY_ORDER = [
    "servo_lift", "servo_head", "servo_wheel_l", "servo_wheel_r",
    "cliff_sensor_fl", "cliff_sensor_fr", "unit_cams3",
    "battery_nimh",
    "servo_if_board", "atoms3r", "dcdc_5v", "bulk_cap", "power_switch",
]


@pytest.mark.parametrize("cid", ["battery_nimh", "servo_if_board", "atoms3r", "unit_cams3"])
def test_main_components_can_be_inserted(assembly, components, cid):
    """主要部品を上から入れられること（天板・頭部を外した状態）。

    収まっていても経路がふさがれていれば組み立てられない。
    障害物は「その作業の時点で存在するもの」だけを渡す（references/assembly.md）。
    ASSEMBLY_ORDER で cid より後の部品はまだ付いていない。
    """
    step = ASSEMBLY_ORDER.index(cid)
    installed = set(ASSEMBLY_ORDER[:step])
    obstacles = {
        k: v
        for k, v in assembly.items()
        if k == "body" or (k in installed and k not in OUTSIDE_INTERIOR)
        if k not in ("top_plate", "battery_hatch", "head")
    }
    verify.assert_insertable(cid, components[cid], (0, 0, 1), obstacles, distance=80.0)


def test_driver_can_reach_top_plate_screws(assembly):
    """天板のネジをドライバーで締められること。天板を閉じた後に締める。"""
    obstacles = {k: v for k, v in assembly.items() if k not in ("head", "battery_hatch")}
    for x, y in shell_boss_positions():
        verify.assert_tool_access(
            (x, y, P.plate_top),
            (0, 0, 1),
            obstacles,
            name="天板ネジ",
            driver_dia=P.driver_dia,
        )


def test_driver_can_reach_if_board_screws(assembly, components):
    """サーボ I/F 基板のネジを締められること。天板と頭部が無い状態で締める。"""
    obstacles = {
        k: v
        for k, v in assembly.items()
        if k not in ("top_plate", "battery_hatch", "head", "servo_if_board")
    }
    board_top = P.if_board_pos[2] + BOM["servo_if_board"].size[2]
    for x, y in if_board_boss_positions():
        verify.assert_tool_access(
            (x, y, board_top),
            (0, 0, 1),
            obstacles,
            name="I/F 基板ネジ",
            driver_dia=P.driver_dia,
        )


# --------------------------------------------------------------------------
# 開口部
# --------------------------------------------------------------------------
def test_camera_lens_has_an_opening(assembly):
    """カメラのレンズ位置に胴体前面の開口があること。"""
    cam = assembly["unit_cams3"].bounding_box()
    verify.assert_connector_access(
        ((cam.min.X + cam.max.X) / 2, 0.0, cam.min.Z + P.cam_lens_offset_z),
        "-y",
        (P.cam_lens_dia * 0.7, P.cam_lens_dia * 0.7),
        assembly["body"],
        name="カメラのレンズ",
    )


def test_atoms3r_usb_has_an_opening(assembly):
    """AtomS3R の USB-C にケーブルを挿せること（ケースを開けずに書き込める）。"""
    conn = BOM["atoms3r"].connectors[0]
    bb = assembly["atoms3r"].bounding_box()
    verify.assert_connector_access(
        (bb.max.X - conn.pos[0], P.inner_d, bb.min.Z + conn.pos[2]),
        "+y",
        conn.size,
        assembly["body"],
        depth=conn.depth,
        name="AtomS3R の USB-C",
    )


def test_power_switch_has_an_opening(assembly):
    """電源スイッチのレバーが外（左側面）に出ていること。"""
    bb = assembly["power_switch"].bounding_box()
    verify.assert_connector_access(
        (0.0, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2),
        "-x",
        (bb.size.Y * 0.8, bb.size.Z * 0.8),
        assembly["body"],
        name="電源スイッチ",
    )


def test_face_window_is_cut_through(assembly):
    """顔の窓が頭部前面を貫通していること。"""
    hx, hy, _ = P.head_origin
    from projects.cozmo_clone.model import oled_module_bottom_z

    verify.assert_connector_access(
        (hx + P.head_w / 2, hy, oled_module_bottom_z() + P.oled_window_offset_z),
        "-y",
        (P.oled_window_w * 0.9, P.oled_window_h * 0.9),
        assembly["head"],
        depth=3.0,
        name="顔の窓",
    )


# --------------------------------------------------------------------------
# ネジ適合
# --------------------------------------------------------------------------
def test_top_plate_tapping_screws_fit():
    s = SCREWS[P.shell_screw]
    verify.assert_boss_screw_fit(
        screw_dia=s.nominal,
        pilot_dia=s.pilot_dia,
        boss_outer_dia=s.boss_outer_dia,
        boss_depth=P.shell_boss_depth,
        screw_len=P.shell_screw_len,
        plate_thickness=P.top_plate,
        name="天板ネジ",
    )


def test_board_tapping_screws_fit():
    s = SCREWS[P.board_screw]
    verify.assert_boss_screw_fit(
        screw_dia=s.nominal,
        pilot_dia=s.pilot_dia,
        boss_outer_dia=s.boss_outer_dia,
        boss_depth=P.board_boss_depth,
        screw_len=P.board_screw_len,
        plate_thickness=1.6,   # 基板厚
        name="基板ネジ",
    )


# --------------------------------------------------------------------------
# 3D プリント
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name", ["body", "top_plate", "battery_hatch", "head", "lift_arm", "hub_l", "hub_r"]
)
def test_printed_parts_are_watertight(name):
    verify.assert_watertight(printed_parts()[name], name=name)


# --------------------------------------------------------------------------
# 機体としての成立性
# --------------------------------------------------------------------------
def test_body_has_ground_clearance():
    """胴体の底が接地面より上にあること（引きずらない）。"""
    body_bottom = -P.floor
    assert body_bottom > P.ground_z, (
        f"胴体の底 Z={body_bottom} が接地面 Z={P.ground_z} より下にある"
    )
    assert body_bottom - P.ground_z >= 3.0, (
        f"地上高 {body_bottom - P.ground_z:.1f} mm が小さすぎる（3 mm 以上必要）"
    )


def test_caster_reaches_the_ground():
    """第 3 の接地点が接地面に届いていること。届かないと前後に倒れる。"""
    caster_bottom = P.caster_pos[2]
    assert caster_bottom <= P.ground_z + 0.5, (
        f"キャスタの底 Z={caster_bottom} が接地面 Z={P.ground_z} に届いていない"
    )


def test_lift_arm_tip_sits_just_above_the_floor(assembly):
    """中立姿勢でフォーク先端が接地面のすぐ上にあること。

    高すぎるとキューブをすくえず、低すぎる（接地面より下）と机を叩いて
    走行できない。上限だけを見ると後者を見逃す。
    """
    height = assembly["lift_arm"].bounding_box().min.Z - P.ground_z
    assert height > 0.0, (
        f"アーム先端が接地面より {-height:.1f} mm 下に潜っている。机を叩く"
    )
    assert height <= 20.0, (
        f"アーム先端が接地面から {height:.1f} mm の高さにある。"
        "これではキューブをすくえない（20 mm 以下にすること）"
    )


def test_overall_size_is_near_the_target():
    """外形がヒアリングの目標（全長 約 150 mm）から大きく外れていないこと。"""
    w, d, h = overall_size()
    assert d <= 165.0, f"全長 {d:.1f} mm が目標 150 mm から離れすぎている"
    assert w <= 120.0, f"全幅 {w:.1f} mm が大きすぎる"
    assert h <= 125.0, f"全高 {h:.1f} mm が大きすぎる"


# --------------------------------------------------------------------------
# 製造ゲート（実測待ちの検出）
# --------------------------------------------------------------------------
@pytest.mark.xfail(
    reason="M5Stack 製品の寸法と顔の窓が provisional（実測待ち）。実測して確定後に外す",
    strict=True,
)
def test_ready_to_manufacture():
    """印刷・発注してよい状態か。暫定寸法が残っている限り失敗する。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        verify.assert_no_provisional(bom=BOM, dims=PROVISIONAL, context="cozmo_clone")


def test_provisional_keys_are_real_params():
    """PROVISIONAL のキーが実在する Params フィールドであること（打ち間違い防止）。"""
    for key in PROVISIONAL:
        assert hasattr(P, key), f"PROVISIONAL のキー '{key}' は Params に無い"
