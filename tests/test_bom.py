"""BOM の検証。

寸法が未確定の部品があれば、設計に進ませずエラーにすることを確認する。
"""

import textwrap

import pytest

from hwlib.bom import BomError, load_bom

# 全カテゴリを埋めた最小の BOM
MINIMAL = """
project: test
components:
  - id: board1
    name: テスト基板
    category: board
    size: [65.0, 30.0, 5.0]
    retention: M3 タッピングネジ x4
    confidence: datasheet
    source: https://example.com/datasheet.pdf
excluded:
  sensor: センサは使わない
  actuator: 可動部なし
  power: USB 給電のみ
  wiring: 基板直結のため配線なし
  display_ui: 表示なし
  fastener: 圧入のみ
  thermal: 発熱が小さい
"""


def write(tmp_path, text):
    p = tmp_path / "bom.yaml"
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return p


def test_valid_bom_loads(tmp_path):
    bom = load_bom(write(tmp_path, MINIMAL))
    assert bom.ids == {"board1"}
    assert bom["board1"].size == (65.0, 30.0, 5.0)


def test_mock_matches_size(tmp_path):
    bom = load_bom(write(tmp_path, MINIMAL))
    mock = bom["board1"].mock()
    bb = mock.bounding_box()
    assert (round(bb.size.X), round(bb.size.Y), round(bb.size.Z)) == (65, 30, 5)


def test_missing_size_is_rejected(tmp_path):
    """寸法が空の部品があれば設計に進ませない。"""
    bad = MINIMAL.replace("size: [65.0, 30.0, 5.0]", "size: []")
    with pytest.raises(BomError, match="size が未確定"):
        load_bom(write(tmp_path, bad))


def test_missing_confidence_is_rejected(tmp_path):
    """出所が不明な寸法は受け付けない。推測値での設計を防ぐ。"""
    bad = MINIMAL.replace("confidence: datasheet", "confidence: guess")
    with pytest.raises(BomError, match="confidence"):
        load_bom(write(tmp_path, bad))


def test_datasheet_without_source_is_rejected(tmp_path):
    """データシート由来と言うなら出典 URL を必須にする。"""
    bad = MINIMAL.replace("    source: https://example.com/datasheet.pdf\n", "")
    with pytest.raises(BomError, match="source"):
        load_bom(write(tmp_path, bad))


def test_uncovered_category_is_rejected(tmp_path):
    """検討していないカテゴリがあれば設計に進ませない（部品の洗い出し漏れを防ぐ）。"""
    bad = MINIMAL.replace("  power: USB 給電のみ\n", "")
    with pytest.raises(BomError, match="power"):
        load_bom(write(tmp_path, bad))


def test_missing_retention_is_rejected(tmp_path):
    """固定方法が書かれていない部品があれば設計に進ませない。

    箱に収まっていても、固定されていなければ組み立てたことにならない。
    """
    bad = MINIMAL.replace("    retention: M3 タッピングネジ x4\n", "")
    with pytest.raises(BomError, match="retention"):
        load_bom(write(tmp_path, bad))
