"""スタックチャン 外形（公式 STL 取り込み）の検証。

外観再現のみが対象。公式 STL が読み込め、想定の外形寸法を持ち、組み立てが
全高 70.5 に収まることを確認する。部品形状の正しさは公式データに依拠する。
"""

import pytest

from projects.stackchan.model import ENV_H, STL_DIR, build_all, load_part

# 公式 STL の実測外形（bbox）。取り違え・破損の検出用
EXPECTED_SIZE = {
    "StackChan-Base": (48.0, 56.0, 11.1),
    "StackChan-MainBody": (54.0, 46.7, 54.0),
}


def test_stl_files_exist():
    for name in EXPECTED_SIZE:
        assert (STL_DIR / f"{name}.stl").exists(), f"{name}.stl が無い"


@pytest.mark.parametrize("name,size", EXPECTED_SIZE.items())
def test_part_loads_with_expected_size(name, size):
    p = load_part(name)
    bb = p.bounding_box().size
    for got, exp, axis in zip((bb.X, bb.Y, bb.Z), size, "XYZ"):
        assert got == pytest.approx(exp, abs=0.5), f"{name} の {axis} が {got:.1f}（想定 {exp}）"


def test_assembly_within_overall_height():
    """組み立ての全高が仕様 70.5 に収まり、足が Z=0 に接地すること。"""
    parts = build_all()
    zmin = min(p.bounding_box().min.Z for p in parts.values())
    zmax = max(p.bounding_box().max.Z for p in parts.values())
    assert zmin == pytest.approx(0.0, abs=0.01), "足が Z=0 に接地していない"
    assert zmax == pytest.approx(ENV_H, abs=0.01), f"全高が {ENV_H} でない（{zmax:.1f}）"


def test_parts_centered_in_xy():
    """各部品が XY 原点中心に置かれていること（組み立ての基準）。"""
    for name, p in build_all().items():
        c = p.bounding_box().center()
        assert c.X == pytest.approx(0.0, abs=0.01), f"{name} が X 中心でない"
        assert c.Y == pytest.approx(0.0, abs=0.01), f"{name} が Y 中心でない"
