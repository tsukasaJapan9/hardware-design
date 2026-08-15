"""部品ライブラリ（parts/）の検証。

守りたいのは「同じ部品の寸法が 1 か所にしかない」こと。
プロジェクトが寸法を書き換えられてしまうとこれが崩れるため、機械的に禁止する。
"""

import textwrap

import pytest

from hwlib import library
from hwlib.bom import BomError, load_bom
from hwlib.library import LibraryError, all_parts, load_part, load_shape

# ライブラリを参照する最小の BOM（全カテゴリを excluded で埋めてある）
USING_LIBRARY = """
project: test
components:
  - use: raspberry_pi_zero_2w
    id: pi
    retention: M2.6 タッピングネジ x4
excluded:
  sensor: なし
  actuator: なし
  power: なし
  wiring: なし
  display_ui: なし
  fastener: なし
  thermal: なし
"""


def write(tmp_path, text):
    path = tmp_path / "bom.yaml"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


# --- ライブラリそのもの ---
def test_all_parts_load():
    """parts/*.yaml が全部読めること。"""
    parts = all_parts()
    assert parts, "parts/ に部品が 1 つも無い"
    for part_id, part in parts.items():
        assert part["id"] == part_id
        assert len(part["size"]) == 3 and all(v > 0 for v in part["size"])
        assert part["confidence"], f"{part_id}: confidence が無い"


def test_datasheet_confidence_needs_source():
    """データシート由来と書くなら出典 URL があること。"""
    for part_id, part in all_parts().items():
        if part["confidence"] == "datasheet":
            assert part.get("source"), f"{part_id}: confidence=datasheet なのに source が無い"


def test_declared_shapes_resolve():
    """shape: が実際に呼べる関数を指していること。"""
    for part_id, part in all_parts().items():
        if part.get("shape"):
            assert load_shape(part["shape"])().volume > 0, f"{part_id}: shape が形状を返さない"


def test_unknown_part_is_rejected():
    with pytest.raises(LibraryError, match="ライブラリにありません"):
        load_part("no_such_part")


def test_unknown_part_suggests_close_name():
    """打ち間違いには候補を出す。"""
    with pytest.raises(LibraryError, match="dynamixel_xl330"):
        load_part("dynamixel_xl33")


def test_unknown_field_is_rejected(tmp_path, monkeypatch):
    """部品ファイルに使い方（retention など）を書いたら弾く。"""
    (tmp_path / "dummy.yaml").write_text(
        "id: dummy\nname: ダミー\ncategory: board\nsize: [1, 1, 1]\n"
        "confidence: user_provided\nretention: ネジ\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(library, "PARTS_DIR", tmp_path)
    all_parts.cache_clear()
    with pytest.raises(LibraryError, match="retention"):
        all_parts()
    all_parts.cache_clear()


def test_id_must_match_filename(tmp_path, monkeypatch):
    (tmp_path / "dummy.yaml").write_text(
        "id: other\nname: ダミー\ncategory: board\nsize: [1, 1, 1]\nconfidence: user_provided\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(library, "PARTS_DIR", tmp_path)
    all_parts.cache_clear()
    with pytest.raises(LibraryError, match="ファイル名"):
        all_parts()
    all_parts.cache_clear()


# --- BOM からの参照 ---
def test_use_resolves_dimensions(tmp_path):
    """寸法・取付穴・コネクタ・出典がライブラリから入ること。"""
    bom = load_bom(write(tmp_path, USING_LIBRARY))
    pi = bom["pi"]
    assert pi.size == (65.0, 30.0, 5.0)
    assert len(pi.mount_holes) == 4
    assert pi.hole_dia == 2.75
    assert pi.connectors[0].name == "micro_usb_power"
    assert pi.source.startswith("https://")
    assert pi.library_id == "raspberry_pi_zero_2w"


def test_id_defaults_to_part_id(tmp_path):
    bom = load_bom(write(tmp_path, USING_LIBRARY.replace("    id: pi\n", "")))
    assert bom["raspberry_pi_zero_2w"].library_id == "raspberry_pi_zero_2w"


def test_overriding_dimensions_is_rejected(tmp_path):
    """寸法をプロジェクト側で書き換えたらエラー。出所を 1 か所に保つ。"""
    bad = USING_LIBRARY.replace("    id: pi\n", "    id: pi\n    size: [60.0, 30.0, 5.0]\n")
    with pytest.raises(BomError, match="部品ライブラリだけが持つ項目"):
        load_bom(write(tmp_path, bad))


def test_overriding_source_is_rejected(tmp_path):
    bad = USING_LIBRARY.replace("    id: pi\n", "    id: pi\n    source: https://example.com\n")
    with pytest.raises(BomError, match="部品ライブラリだけが持つ項目"):
        load_bom(write(tmp_path, bad))


def test_usage_fields_can_be_set(tmp_path):
    """使い方（固定方法・クリアランス・カテゴリ・CAD 配置）は上書きできる。"""
    text = USING_LIBRARY.replace(
        "    retention: M2.6 タッピングネジ x4\n",
        "    retention: 両面テープ\n    clearance: 3.0\n    category: display_ui\n",
    ).replace("  display_ui: なし", "  board: 表示器として扱うため board は無し")
    pi = load_bom(write(tmp_path, text))["pi"]
    assert (pi.retention, pi.clearance, pi.category) == ("両面テープ", 3.0, "display_ui")


def test_note_keeps_both_sides(tmp_path):
    """note は部品の性質（ライブラリ）と設計上の判断（プロジェクト）の両方を残す。"""
    text = USING_LIBRARY.replace(
        "    retention: M2.6 タッピングネジ x4\n",
        "    retention: M2.6 タッピングネジ x4\n    note: 蓋のリブで押さえる\n",
    )
    note = load_bom(write(tmp_path, text))["pi"].note
    assert "蓋のリブで押さえる" in note
    assert "ネジ穴ピッチ" in note, "ライブラリ側の note が落ちている"


def test_unknown_usage_field_is_rejected(tmp_path):
    bad = USING_LIBRARY.replace("    id: pi\n", "    id: pi\n    retensión: typo\n")
    with pytest.raises(BomError, match="知らない項目"):
        load_bom(write(tmp_path, bad))


def test_missing_part_reports_which_bom(tmp_path):
    bad = USING_LIBRARY.replace("use: raspberry_pi_zero_2w", "use: raspberry_pi_zero_3w")
    with pytest.raises(BomError, match="raspberry_pi_zero_3w"):
        load_bom(write(tmp_path, bad))


def test_retention_still_required(tmp_path):
    """ライブラリ参照でも、固定方法の記入は免除されない。"""
    bad = USING_LIBRARY.replace("    retention: M2.6 タッピングネジ x4\n", "")
    with pytest.raises(BomError, match="retention"):
        load_bom(write(tmp_path, bad))
