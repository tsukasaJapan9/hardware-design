"""部品ライブラリ（`parts/`）の読み込み。

部品の寸法はプロジェクトではなくライブラリが持つ。同じ部品を複数のプロジェクトから
使い回しても、寸法の出所は 1 か所（`parts/<id>.yaml`）に固定される。

    parts/
      dynamixel_xl330.yaml    寸法・出典・信頼度（1 部品 1 ファイル）
      xl330.py                実形状モデル（YAML の shape: が指す）

プロジェクトの `bom.yaml` は `use: <部品 id>` で参照し、「どう使うか」だけを書く。
寸法をプロジェクト側で書き換えることはできない（hwlib.bom.LIBRARY_ONLY）。

登録のルール:
  - 値は必ず一次情報源（メーカーの機械図面・データシート）で裏を取り、source に URL を書く
  - 裏が取れない項目は「書かない」。推測値を入れると、それが正しい値として使われてしまう
  - 実測した値は confidence: measured とし、いつ何を測ったか note に残す
"""

from __future__ import annotations

import difflib
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import yaml

PARTS_DIR = Path(__file__).resolve().parent.parent / "parts"

# 部品ファイルに書ける項目。ここに無いキーは書き間違いとして弾く。
PART_FIELDS = {
    "id",          # 部品 id。ファイル名と一致させる
    "name",        # 製品名・型番
    "category",    # 既定のカテゴリ。プロジェクトで上書きできる
    "size",        # [幅 X, 奥行き Y, 高さ Z] mm
    "mount_holes",
    "hole_dia",
    "connectors",
    "confidence",
    "source",      # 出典 URL
    "datasheet",   # datasheets/ 配下に保存した図面の実体（任意）
    "shape",       # 実形状モデル "<module>:<関数>"（任意）
    "note",
}


class LibraryError(Exception):
    """部品ライブラリの不備。"""


def _read(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise LibraryError(f"{path}: 中身が辞書ではありません")

    unknown = set(data) - PART_FIELDS
    if unknown:
        raise LibraryError(
            f"{path}: 知らない項目 {sorted(unknown)}。"
            f"書けるのは {sorted(PART_FIELDS)}。"
            "固定方法（retention）やクリアランスは部品ではなく使い方なので "
            "projects/<name>/bom.yaml に書く"
        )
    if data.get("id") != path.stem:
        raise LibraryError(
            f"{path}: id が '{data.get('id')}' でファイル名 '{path.stem}' と違います。"
            "参照は id で行うため、一致させること"
        )
    return data


@lru_cache(maxsize=1)
def all_parts() -> dict[str, dict[str, Any]]:
    """`parts/*.yaml` を全部読む。id をキーにした辞書。"""
    if not PARTS_DIR.is_dir():
        raise LibraryError(f"部品ライブラリ {PARTS_DIR} がありません")
    return {path.stem: _read(path) for path in sorted(PARTS_DIR.glob("*.yaml"))}


def load_part(part_id: str) -> dict[str, Any]:
    """ライブラリから部品を取り出す。無ければ候補を添えてエラーにする。"""
    parts = all_parts()
    if part_id not in parts:
        hint = difflib.get_close_matches(part_id, parts, n=3)
        raise LibraryError(
            f"'{part_id}' は部品ライブラリにありません。"
            + (f"もしかして: {', '.join(hint)}。" if hint else "")
            + f"型番から寸法を調査して {PARTS_DIR.name}/{part_id}.yaml を作るか、"
            "bom.yaml に直接寸法を書いてください"
        )
    return parts[part_id]


def load_shape(spec: str) -> Callable[[], Any]:
    """`shape:` の指す実形状モデルの関数を取り出す。

    書式は "<module>:<関数>"（例: "parts.xl330:body"）。
    形状は build123d の Part を返す引数なしの関数であること。
    """
    import importlib

    module_name, _, func_name = spec.partition(":")
    if not module_name or not func_name:
        raise LibraryError(f"shape: '{spec}' の書式が不正です（'<module>:<関数>' で書く）")
    try:
        module = importlib.import_module(module_name)
        return getattr(module, func_name)
    except (ImportError, AttributeError) as e:
        raise LibraryError(f"shape: '{spec}' を解決できません（{type(e).__name__}: {e}）") from e
