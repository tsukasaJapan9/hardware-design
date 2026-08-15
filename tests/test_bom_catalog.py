"""BOM カタログの検証。

図は目で見て確かめるものだが、次の 2 つは機械的に確認できるので自動化する。

  - 図が実際の形状の投影になっていること（寸法値が形状の外形と一致する）
  - 全部品がカタログに載り、抜けが出ないこと
"""

import pytest
from build123d import Align, Box, Pos

from hwlib.bom import Component, Connector
from hwlib.bom_catalog import (
    build_body,
    build_catalog,
    connector_fits,
    draw,
    load_all,
)
from hwlib.drawing import VIEWS, project_view, three_view_svg


@pytest.fixture(scope="module")
def boms():
    return load_all()


def test_projection_matches_shape():
    """投影した稜線の広がりが、その視点から見た外形と一致すること。

    軸の取り違え（正面図に奥行きが出るなど）はこれで落ちる。
    """
    part = Pos(3, -4, 5) * Box(40, 20, 10, align=(Align.MIN,) * 3)
    expected = {"top": (40, 20), "front": (40, 10), "right": (20, 10)}

    for view in VIEWS:
        visible, _ = project_view(part, view)
        points = [p for polyline in visible for p in polyline]
        span_u = max(u for u, _ in points) - min(u for u, _ in points)
        span_v = max(v for _, v in points) - min(v for _, v in points)
        assert span_u == pytest.approx(expected[view.key][0], abs=0.01)
        assert span_v == pytest.approx(expected[view.key][1], abs=0.01)


def test_projection_keeps_part_coordinates():
    """投影の座標が部品座標のままであること（注記を重ねられる前提）。"""
    part = Pos(100, 0, 0) * Box(10, 10, 10, align=(Align.MIN,) * 3)
    visible, _ = project_view(part, VIEWS[1])  # 正面図: u = X
    us = [u for polyline in visible for u, _ in polyline]
    assert min(us) == pytest.approx(100, abs=0.01)


def test_hidden_edges_are_separated():
    """隠れた穴が破線側に出ること。実線と破線を描き分けている根拠。"""
    from build123d import Cylinder

    part = Box(30, 30, 10, align=(Align.MIN,) * 3)
    part -= Pos(15, 15, 0) * Cylinder(3, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
    _, hidden = project_view(part, VIEWS[1])  # 正面図から見れば穴は隠れる
    assert hidden, "貫通穴が隠れ線として出ていない"


def test_svg_is_well_formed():
    """SVG が閉じており、寸法が入っていること。"""
    svg = three_view_svg(Box(20, 10, 5, align=(Align.MIN,) * 3))
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    for label in ("W 20", "D 10", "H 5", "平面図", "正面図", "右側面図"):
        assert label in svg


def test_connector_fit_check():
    """面に収まらない開口を検出すること。"""
    component = Component(
        id="c", name="c", category="board", size=(50.0, 40.0, 10.0),
        confidence="user_provided", retention="ネジ",
    )
    assert connector_fits(component, Connector("ok", (0, 0, 0), (8.0, 3.0), "-y"))
    assert not connector_fits(component, Connector("ng", (0, 0, 0), (48.0, 48.0), "-y"))


def test_every_component_has_a_drawing(boms):
    """全部品に図が付くこと。図の種別も想定の 3 種に収まること。"""
    assert boms, "projects 配下に bom.yaml が見つからない"
    for path, bom in boms:
        for component in bom.components:
            drawing = draw(bom.project, component)
            assert drawing.svg.startswith("<svg")
            assert drawing.kind in {"実形状", "外形近似", "略図"}


def test_catalog_lists_every_component(boms):
    """生成した HTML に全部品の id・部品名が載ること。"""
    html = build_body(boms)
    for _, bom in boms:
        for component in bom.components:
            assert f"{bom.project}--{component.id}" in html, f"{component.id} のカードがない"
            assert component.name in html


def test_catalog_writes_file(tmp_path):
    out = build_catalog(tmp_path / "catalog.html")
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")
    assert "<title>BOM カタログ</title>" in text
