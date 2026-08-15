"""公式スタックチャン（K151）の構造 STL を取得する。

STL はサイズが大きく（合計約 2.7MB）、M5Stack の公式データのためリポジトリには含めない。
モデル（model.py / accessory.py）を動かす前に、このスクリプトで stl/ に取得する。

出典: https://github.com/m5stack/M5_Hardware/tree/master/Products/K151_StackChan/Structures

使い方:
    uv run python -m projects.stackchan.fetch_stl
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

RAW_BASE = (
    "https://raw.githubusercontent.com/m5stack/M5_Hardware/master/"
    "Products/K151_StackChan/Structures"
)
PARTS = [
    "StackChan-Base",
    "StackChan-BaseCover",
    "StackChan-BearingFixture",
    "StackChan-LightGuideBar-A",
    "StackChan-LightGuideBar-B",
    "StackChan-MainBody",
    "StackChan-ServoArm",
    "StackChan-ServoBody",
    "StackChan-ServoCover",
    "StackChan-ServoSideCover",
]

STL_DIR = Path(__file__).parent / "stl"


def fetch(force: bool = False) -> None:
    STL_DIR.mkdir(parents=True, exist_ok=True)
    for name in PARTS:
        dst = STL_DIR / f"{name}.stl"
        if dst.exists() and not force:
            print(f"skip  {name}.stl（取得済み）")
            continue
        url = f"{RAW_BASE}/{name}.stl"
        urllib.request.urlretrieve(url, dst)
        print(f"取得  {name}.stl ({dst.stat().st_size} bytes)")


if __name__ == "__main__":
    fetch()
