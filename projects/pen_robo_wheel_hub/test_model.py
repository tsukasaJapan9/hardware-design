"""変換ハブの検証。

暫定寸法（provisional）のまま骨格を検証する。
形状・ネジ適合・水密は暫定値でも確認できる。実測の確定は製造ゲートで別途強制する。
"""

import warnings

import pytest
from build123d import Cylinder, Align

from hwlib import verify
from hwlib.features import SCREWS
from projects.pen_robo_wheel_hub.model import (
    BOM,
    P,
    PROVISIONAL,
    build_all,
    build_hub,
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
    solid = Cylinder(P.adapter_od / 2, P.body_thickness, align=(Align.CENTER, Align.CENTER, Align.MIN))
    verify.assert_cut(solid, hub, name="ホーン穴＋座ぐり", min_removed=1.0)
    assert len(horn_screw_positions()) == 4


def test_wheel_screw_pattern_is_three(hub):
    assert len(wheel_screw_positions()) == 3


def test_hub_fits_within_wheel_diameter(hub):
    """ハブ外径がホイール外径に収まること（当然だが回転体として妥当性確認）。"""
    bb = hub.bounding_box()
    assert bb.size.X <= BOM["wheel"].size[0]


# --- ネジ適合 ---
def test_wheel_tapping_screw_fit():
    """3x8 タッピングビスの下穴・ねじ込み深さが成立すること。"""
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
    """本体厚が下穴深さ＋底肉を収めていること（ビスが突き抜けない）。"""
    assert P.body_thickness >= P.wheel_tap_depth + P.tap_floor, (
        f"本体厚 {P.body_thickness} が不足（下穴 {P.wheel_tap_depth} + 底肉 {P.tap_floor}）"
    )


# --- 干渉（相手部品と）---
def test_hub_does_not_interfere_with_servo_or_wheel():
    """ハブが相手部品と干渉しないこと。パイロットのはめ合いは接触のみ。"""
    parts = build_all()
    # パイロット嵌合部はわずかに触れる設計のため許容する
    verify.assert_no_interference(
        parts, allow={frozenset(("hub", "servo")), frozenset(("hub", "wheel"))}
    )


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
