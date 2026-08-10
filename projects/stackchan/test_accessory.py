"""耳アクセサリーの検証。

穴へのはめ込み（ペグ）の不変条件と、印刷可否（watertight）を確認する。
耳の形を変えてもフィットが壊れないことを保証する。
"""

import pytest

from hwlib import verify
from projects.stackchan.accessory import P, build_ear_left, build_ear_right


def test_ears_are_valid_and_watertight():
    for name, part in (("右耳", build_ear_right()), ("左耳", build_ear_left())):
        verify.assert_valid(part, name)
        verify.assert_watertight(part, name=name)


def test_peg_fits_measured_bore():
    """ペグ径が実測ボアより小さく、締まり嵌めのすきま範囲であること。"""
    assert P.peg_dia < P.bore_dia, "ペグが穴より太い"
    clr = (P.bore_dia - P.peg_dia) / 2
    assert 0.05 <= clr <= 0.4, f"片側すきま {clr:.2f} が締まり嵌めの範囲外"


def test_peg_length_within_hole_depth():
    """ペグ長が穴深さに収まること（底突きしない）。"""
    assert P.peg_len < P.hole_depth, f"ペグ長 {P.peg_len} が穴深さ {P.hole_depth} 以上"


def test_pegs_placed_at_measured_hole_centers():
    """ペグが実測した 3 穴の中心（Y,Z）に、面から内側へ伸びていること。

    各穴中心に細い探り円柱を X 方向へ置き、右耳（ソリッド）と重なることで確認する。
    """
    from build123d import Align, Cylinder, Pos, Rot

    ear = build_ear_right()
    for y in P.hole_y:
        probe = Pos(P.face_x - P.peg_len, y, P.hole_z) * Rot(0, 90, 0) * Cylinder(
            1.0, P.peg_len, align=(Align.CENTER, Align.CENTER, Align.MIN)
        )
        vol = verify.overlap_volume(probe, ear)
        assert vol > 2.0, f"Y={y} にペグが無い（重なり {vol:.2f} mm^3）"
