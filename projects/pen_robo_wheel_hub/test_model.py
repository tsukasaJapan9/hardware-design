"""変換ハブの検証。

暫定寸法（provisional）のまま骨格を検証する。
形状・ネジ適合・水密は暫定値でも確認できる。実測の確定は製造ゲートで別途強制する。
"""

import warnings

import pytest
from build123d import Align, Cylinder, Pos

from hwlib import verify
from hwlib.features import SCREWS
from hwlib.parts import tamiya_wheel, xl330
from projects.pen_robo_wheel_hub.model import (
    BOM,
    P,
    PROVISIONAL,
    build_all,
    build_hub,
    build_stock,
    horn_screw_positions,
    wheel_screw_positions,
)


@pytest.fixture(scope="module")
def hub():
    return build_hub()


# --- 形状 ---
def test_hub_is_valid_and_watertight(hub):
    verify.assert_valid(hub, "変換ハブ")
    verify.assert_watertight(hub, name="変換ハブ")


def test_horn_bolt_holes_are_actually_cut(hub):
    """M2x4 のバカ穴が実際に開いていること（効かない減算を検出）。"""
    verify.assert_cut(build_stock(), hub, name="ホーン穴＋座ぐり", min_removed=1.0)
    assert len(horn_screw_positions()) == 4


# --- 芯出し（同軸度を出す嵌合）---
def test_hub_has_both_centering_features(hub):
    """スカートが形状として存在し、本体外周がポケット嵌合径になっていること。

    docstring だけが芯出しを約束し、形状は単なる円板、という状態を防ぐ。
    """
    bb = hub.bounding_box()
    expected_z = P.skirt_h + P.body_height
    assert bb.size.Z == pytest.approx(expected_z, abs=0.01), (
        f"全高 {bb.size.Z:.2f} が想定 {expected_z:.2f} と違う。スカートが欠けている可能性がある"
    )
    assert bb.min.Z == pytest.approx(-P.skirt_h, abs=0.01), "スカートが底面から下に伸びていない"
    # 最大径はスカート外径ではなく本体外径（＝ポケット嵌合面）であること
    assert bb.size.X == pytest.approx(P.adapter_od, abs=0.01), (
        f"最大径 {bb.size.X:.2f} が本体外径 {P.adapter_od:.2f} と違う"
    )


def test_skirt_fits_over_horn_without_touching_case():
    """スカートがホーン円板に被り、かつケース前面には当たらないこと。

    ケース前面は回転しない。ここに当たると走行中ずっと擦れる。
    """
    assert P.skirt_id > xl330.HORN_BOSS_DIA, "スカート内径がホーン円板より小さく、嵌らない"
    assert P.skirt_id - xl330.HORN_BOSS_DIA <= 0.4, (
        f"スカートのすきま {P.skirt_id - xl330.HORN_BOSS_DIA:.2f} mm が大きく、芯出しにならない"
    )
    assert P.skirt_h < xl330.HORN_BOSS_H, (
        f"スカート高さ {P.skirt_h} がホーンの出っ張り {xl330.HORN_BOSS_H} 以上。ケース前面に当たる"
    )


def test_hub_seats_inside_wheel_pocket():
    """ハブが本体ごとポケットに収まり、外周で芯出しされること。"""
    assert P.adapter_od < tamiya_wheel.POCKET_DIA, "ハブ外径がポケットより太く、入らない"
    assert tamiya_wheel.POCKET_DIA - P.adapter_od <= 0.4, (
        f"すきま {tamiya_wheel.POCKET_DIA - P.adapter_od:.2f} mm が大きく、芯出しにならない"
    )


def test_wheel_flange_clears_servo_case():
    """ホイールのフランジ端面がホーン当たり面より下に来ないこと。

    ハブを沈めすぎると、フランジがサーボのケース側へ潜り込んで当たる。
    ケース対角は φ42 のフランジ内径より大きいため、接触すれば回らない。
    """
    assert P.wheel_inner_face_z >= 0, (
        f"フランジ端面 Z={P.wheel_inner_face_z:.2f} がホーン当たり面より下。"
        f"ハブ全高 {P.body_height} がポケット深さ {P.wheel_recess_depth} に対して不足"
    )
    parts = build_all()
    verify.assert_no_interference({"servo": parts["servo"], "wheel": parts["wheel"]})


def test_wheel_screw_pattern_is_three(hub):
    assert len(wheel_screw_positions()) == 3


def test_hub_fits_within_wheel_diameter(hub):
    """ハブ外径がホイール外径に収まること（当然だが回転体として妥当性確認）。"""
    bb = hub.bounding_box()
    assert bb.size.X <= BOM["wheel"].size[0]


# --- ネジ適合 ---
def test_wheel_tapping_screw_fit():
    """3x8 タッピングビスの下穴・ねじ込み深さが成立すること。

    実測ウェブ厚 2.0mm でねじ込み 8-2=6.0mm となり、指針（呼び径の2倍）ちょうど。
    余裕はないので、ウェブ厚が個体差で厚い場合は 3x10 に変える。
    """
    s = SCREWS[P.wheel_screw]
    verify.assert_boss_screw_fit(
        screw_dia=s.nominal,
        pilot_dia=s.pilot_dia,
        boss_outer_dia=P.adapter_od,   # 本体が十分太いので割れ余裕は大きい
        boss_depth=P.wheel_tap_depth,
        screw_len=P.wheel_screw_len,
        plate_thickness=P.wheel_boss_wall,  # ホイール壁を通す分
        name="ホイール固定ビス",
    )


def test_hub_body_accommodates_tap_depth():
    """全高が下穴深さ＋底肉を収めていること（ビスが突き抜けない）。

    下穴はスピゴット頂面から掘るため、効く厚みは本体厚ではなく全高。
    """
    assert P.body_height >= P.wheel_tap_depth + P.tap_floor, (
        f"全高 {P.body_height} が不足（下穴 {P.wheel_tap_depth} + 底肉 {P.tap_floor}）"
    )


def test_horn_screw_reaches_horn():
    """M2 がハブを貫通してホーンに規定深さねじ込めること。

    座ぐりで頭を沈めた分だけネジは届く。ネジ長が足りないと、締めたつもりで
    ホーンに数山しか掛からない。XL330 付属の M2x6 では全高 10.7 mm に対して足りず、
    M2x12 を別途調達している（bom.yaml 参照）。
    """
    assert P.cb_depth >= 0, (
        f"M2x{P.horn_screw_len} が長すぎる。ハブ側で使える長さ {P.horn_screw_grip} mm が"
        f"全高 {P.body_height} mm を超え、ホーンに規定 {P.horn_engage} mm より深く入る"
    )
    assert P.horn_screw_grip >= P.body_height - P.cb_depth, "M2 がホーンに届かない"
    # 座ぐりが深すぎるとドライバーが頭に届かない
    assert P.cb_depth <= 4.0, (
        f"座ぐり {P.cb_depth:.2f} mm が深く、φ{SCREWS[P.horn_screw].head_dia} の頭まで"
        "ドライバーが届かない。ネジを長くして頭を浅い位置に上げる"
    )
    # 図面 DP3.0 Max を超えてねじ込むとサーボ内部を破損する
    assert P.horn_engage <= 3.0, "ホーンへのねじ込みが DP3.0 Max を超えている"


# --- 締結が実際に通るか ---
def test_wheel_screw_passes_through_disc_into_hub():
    """3x8 ビスがホイールディスクを貫通してハブの下穴に届くこと。

    ディスク側の穴が袋穴だとビスは入らない。ビスの軸を実体として置き、
    ホイールと重ならない（＝穴が通っている）ことで確認する。
    """
    parts = build_all()
    head_z = tamiya_wheel.web_far_face_z(P.wheel_inner_face_z)
    shank_len = tamiya_wheel.WEB_THICKNESS + P.wheel_tap_depth

    for x, y in wheel_screw_positions():
        # ビス軸: ディスク外側面から -Z へ、板を抜けてハブへ
        shank = Pos(x, y, head_z - shank_len) * Cylinder(
            SCREWS[P.wheel_screw].nominal / 2, shank_len,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        assert verify.overlap_volume(shank, parts["wheel"]) < 0.01, (
            f"ビス位置 ({x:.1f}, {y:.1f}): ホイールディスクの穴が貫通していない"
        )

    # ビス先端がハブの下穴の底を突き抜けないこと
    assert head_z - shank_len >= P.body_height - P.wheel_tap_depth - 0.01


def test_wheel_screw_driver_access():
    """3x8 ビスをホイール外側から締められること。

    ディスクの外側を塞ぐ設計にすると、組み上がった状態でビスを締められない。
    """
    parts = build_all()
    head_z = tamiya_wheel.web_far_face_z(P.wheel_inner_face_z)
    for x, y in wheel_screw_positions():
        verify.assert_tool_access(
            (x, y, head_z), (0, 0, 1), parts,
            name=f"ホイール固定ビス ({x:.1f}, {y:.1f})", driver_dia=6.0,
        )


def test_horn_screw_driver_access():
    """M2 をスピゴット頂面から締められること。

    組立順は「ハブをホーンに締結 → ホイールを被せる」なので、ホイールは障害物に含めない。
    座ぐりが深いため、細軸ドライバー（φ4）で見る。
    """
    parts = build_all()
    obstacles = {"servo": parts["servo"], "hub": parts["hub"]}
    for x, y in horn_screw_positions():
        verify.assert_tool_access(
            (x, y, P.body_height - P.cb_depth), (0, 0, 1), obstacles,
            name=f"ホーン固定ネジ ({x:.1f}, {y:.1f})", driver_dia=4.0,
        )


# --- 干渉（相手部品と）---
def test_hub_does_not_interfere_with_servo_or_wheel():
    """ハブが相手部品と干渉しないこと。

    芯出しの嵌合部にはすきま（skirt_fit / spigot_fit）を持たせているため、
    当たり面での面接触だけになり体積の重なりは出ない。ここを allow で
    素通しすると、嵌合が「食い込み」でも通ってしまう。
    """
    verify.assert_no_interference(build_all())


# --- 製造ゲート（実測待ちの検出）---
@pytest.mark.xfail(reason="嵌合寸法が provisional（実測待ち）。実測して Params 更新後に外す", strict=True)
def test_ready_to_manufacture():
    """印刷・発注してよい状態か。暫定寸法が残っている限り失敗する。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        verify.assert_no_provisional(bom=BOM, dims=PROVISIONAL, context="変換ハブ")


def test_provisional_keys_are_real_params():
    """PROVISIONAL のキーが実在する Params フィールドであること（打ち間違い防止）。"""
    for key in PROVISIONAL:
        assert hasattr(P, key), f"PROVISIONAL のキー '{key}' は Params に無い"
