"""部品表（BOM）の読み込みと検証。

bom.yaml を読み込み、寸法が確定していない部品があればエラーにする。
これにより「寸法未確定のまま CAD 設計に進む」ことを機械的に防ぐ。

部品は `use: <部品 id>` で部品ライブラリ（`parts/`、hwlib.library）を参照する。
bom.yaml に書くのは「どう使うか」だけで、寸法はライブラリが持つ。同じ部品を
複数のプロジェクトから使い回しても、寸法の出所は 1 か所に固定される。
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from build123d import Align, Box, Part, Pos

from hwlib.library import LibraryError, load_part

# 部品の洗い出しで確認すべきカテゴリ。
# 各カテゴリは「部品がある」か「不要である理由が記録されている」かのどちらかでなければならない。
CATEGORIES = {
    "board": "電子基板（メイン基板、電源基板、変換基板）",
    "sensor": "センサ（カメラ、マイク、距離センサ、IMU）",
    "actuator": "アクチュエータ（モータ、サーボ、駆動基板）",
    "power": "電源（バッテリー、充電回路、電源スイッチ、DC ジャック）",
    "wiring": "配線（ハーネス、USB ケーブル、コネクタの挿抜空間）",
    "display_ui": "表示・操作（ディスプレイ、LED、ボタン）",
    "fastener": "締結（ネジ、スペーサ、ゴム足）",
    "thermal": "放熱・通気（ヒートシンク、通気口）",
}

# 寸法の信頼度。この 3 つ以外は「未確定」とみなして設計に進ませない。
VALID_CONFIDENCE = {
    "datasheet",  # データシート・製品ページに基づく
    "measured",   # ユーザがノギスで実測した
    "user_provided",  # ユーザが値を直接指定した
    "provisional",  # 暫定値。骨格設計を進めるための仮値で、印刷・発注の前に実測して確定する
}

# 印刷・発注に進んでよい（＝確定した）信頼度。provisional はここに含めない。
CONFIRMED_CONFIDENCE = VALID_CONFIDENCE - {"provisional"}

# 部品ライブラリだけが持てる項目。プロジェクトが上書きすると、同じ部品の寸法が
# プロジェクトごとに散らばり、ライブラリ化した意味が無くなるためエラーにする。
LIBRARY_ONLY = {
    "name", "size", "mount_holes", "hole_dia", "connectors",
    "confidence", "source", "datasheet", "shape",
}

# プロジェクトが決める項目（＝その部品を「どう使うか」）。
PROJECT_FIELDS = {"use", "id", "category", "retention", "clearance", "geometric", "note"}


class BomError(Exception):
    """BOM の不備。設計に進んではいけない状態を表す。"""


@dataclass
class Connector:
    """外装に開口が必要なコネクタ。

    pos は部品ローカル座標系（部品の最小コーナーが原点）でのコネクタ中心。
    depth はケーブルを挿し抜きするために外側に必要な空間の奥行き。
    """

    name: str
    pos: tuple[float, float, float]
    size: tuple[float, float]
    face: str  # "+x", "-x", "+y", "-y", "+z", "-z"
    depth: float = 10.0


@dataclass
class Component:
    """BOM の 1 部品。

    size は (幅 X, 奥行き Y, 高さ Z) mm。
    mount_holes は部品ローカル座標での取付穴中心 (x, y)。
    """

    id: str
    name: str
    category: str
    size: tuple[float, float, float]
    confidence: str
    source: str = ""
    mount_holes: list[tuple[float, float]] = field(default_factory=list)
    hole_dia: float = 0.0
    connectors: list[Connector] = field(default_factory=list)
    clearance: float = 1.0
    note: str = ""
    # CAD に配置して干渉を見る対象か。
    # ネジやハーネスは部品表には必要だが、形状として配置する対象ではない場合がある。
    # ただし配線が占める空間を確保したい場合は geometric: true にして体積を持たせる。
    geometric: bool = True
    # 何でこの部品を固定するか（ネジ、ポケット、蓋で押さえる、両面テープ など）。
    # 収まっていても固定されていなければ組み立てたことにならない。
    # 干渉チェックは「箱の中で部品が浮いている」状態を素通りさせるため、宣言を必須にする。
    retention: str = ""
    # 参照した部品ライブラリの id（parts/<library_id>.yaml）。直書きの部品では空。
    library_id: str = ""
    # 実形状モデル "<module>:<関数>"。ライブラリから引き継ぐ。
    shape: str = ""
    # 寸法の根拠になるローカルの図面（datasheets/ 配下）。
    datasheet: str = ""

    def mock(self) -> Part:
        """部品の簡易ソリッド（外形の直方体）。

        部品ローカル座標の原点は最小コーナー。配置側で Pos/Rot を掛けて使う。
        """
        return Box(*self.size, align=(Align.MIN, Align.MIN, Align.MIN))

    def mock_with_clearance(self) -> Part:
        """周囲クリアランスを含めた占有領域。干渉チェックに使う。"""
        c = self.clearance
        w, d, h = self.size
        return Pos(-c, -c, -c) * Box(
            w + 2 * c, d + 2 * c, h + 2 * c, align=(Align.MIN, Align.MIN, Align.MIN)
        )


@dataclass
class Bom:
    """部品表。"""

    project: str
    components: list[Component]
    excluded: dict[str, str] = field(default_factory=dict)

    def __getitem__(self, component_id: str) -> Component:
        for c in self.components:
            if c.id == component_id:
                return c
        raise KeyError(f"部品 '{component_id}' は BOM にありません")

    @property
    def ids(self) -> set[str]:
        return {c.id for c in self.components}

    @property
    def geometric_ids(self) -> set[str]:
        """CAD に配置すべき部品の id。ネジなど形状を持たせない部品は含まない。"""
        return {c.id for c in self.components if c.geometric}

    @property
    def provisional(self) -> list[Component]:
        """寸法が暫定（実測待ち）の部品。印刷・発注の前に確定させる必要がある。"""
        return [c for c in self.components if c.confidence == "provisional"]

    def by_category(self, category: str) -> list[Component]:
        return [c for c in self.components if c.category == category]


def resolve_library_ref(raw: dict) -> dict:
    """`use:` の部品をライブラリから引き、プロジェクト側の指定と合成する。

    寸法系（LIBRARY_ONLY）をプロジェクトが書いていたらエラーにする。
    これを許すと同じ部品の寸法がプロジェクトごとに散らばり、ライブラリ化した
    意味が無くなる。値を変えたいならライブラリ側を直すか、別部品として登録する。
    """
    part = load_part(raw["use"])

    overridden = sorted(set(raw) & LIBRARY_ONLY)
    if overridden:
        raise BomError(
            f"{overridden} は部品ライブラリだけが持つ項目です。"
            f"値を変えるなら parts/{raw['use']}.yaml を直すか、別の部品として登録すること"
            "（プロジェクトごとに寸法を書き換えると、出所が 1 か所でなくなる）"
        )
    unknown = sorted(set(raw) - PROJECT_FIELDS)
    if unknown:
        raise BomError(
            f"知らない項目 {unknown}。use: で参照する部品に書けるのは "
            f"{sorted(PROJECT_FIELDS - {'use'})}"
        )

    merged = {k: v for k, v in part.items() if k not in ("id", "note")}
    merged.update({k: v for k, v in raw.items() if k not in ("use", "note")})
    merged["id"] = raw.get("id", part["id"])
    merged["library_id"] = part["id"]

    # note は部品の性質（ライブラリ）と設計上の判断（プロジェクト）の両方を残す
    notes = [
        text.strip()
        for text in (part.get("note", ""), raw.get("note", ""))
        if text and str(text).strip()
    ]
    merged["note"] = "\n".join(notes)
    return merged


def component_from_dict(raw: dict) -> Component:
    """辞書を Component にする。検証はしない（呼ぶ側の責任）。

    load_bom（プロジェクトの部品）と、部品ライブラリを単体で図面化する側
    （hwlib.bom_catalog）の両方から使うため分けてある。
    """
    connectors = [
        Connector(
            name=c["name"],
            pos=tuple(c["pos"]),
            size=tuple(c["size"]),
            face=c["face"],
            depth=c.get("depth", 10.0),
        )
        for c in raw.get("connectors", [])
    ]
    return Component(
        id=raw["id"],
        name=raw.get("name", raw["id"]),
        category=raw["category"],
        size=tuple(float(v) for v in raw["size"]),
        confidence=raw["confidence"],
        source=raw.get("source", ""),
        mount_holes=[tuple(h) for h in raw.get("mount_holes", [])],
        hole_dia=raw.get("hole_dia", 0.0),
        connectors=connectors,
        clearance=raw.get("clearance", 1.0),
        note=raw.get("note", ""),
        geometric=raw.get("geometric", True),
        retention=raw.get("retention", ""),
        library_id=raw.get("library_id", ""),
        shape=raw.get("shape", ""),
        datasheet=raw.get("datasheet", ""),
    )


def load_bom(path: str | Path) -> Bom:
    """bom.yaml を読み込み、検証する。

    不備があれば BomError を送出し、設計に進ませない。
    """
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    components: list[Component] = []
    problems: list[str] = []

    for i, raw in enumerate(data.get("components", [])):
        cid = raw.get("id") or raw.get("use") or f"<{i} 番目の部品: id なし>"

        # 部品ライブラリを参照している場合は、まず寸法を引いてくる
        if "use" in raw:
            try:
                raw = resolve_library_ref(raw)
            except (BomError, LibraryError) as e:
                problems.append(f"{cid}: {e}")
                continue

        size = raw.get("size")
        if not size or len(size) != 3 or any(v is None or v <= 0 for v in size):
            problems.append(f"{cid}: size が未確定（[幅, 奥行き, 高さ] mm を調査すること）")
            continue

        confidence = raw.get("confidence")
        if confidence not in VALID_CONFIDENCE:
            problems.append(
                f"{cid}: confidence が '{confidence}' — "
                f"{sorted(VALID_CONFIDENCE)} のいずれかにすること。"
                "ネットで確定できないならユーザに実測を依頼する"
            )
            continue

        if confidence == "datasheet" and not raw.get("source"):
            problems.append(f"{cid}: confidence=datasheet なら source（出典 URL）が必要")
            continue

        category = raw.get("category")
        if category not in CATEGORIES:
            problems.append(f"{cid}: category が不正 '{category}' — {sorted(CATEGORIES)}")
            continue

        if raw.get("geometric", True) and not raw.get("retention"):
            problems.append(
                f"{cid}: retention が未記入 — この部品を何で固定するかを書くこと"
                "（例: 'M3 タッピングネジ x4'、'ポケットに収めて蓋で押さえる'、'両面テープ'）。"
                "収まっていても固定されていなければ組み立てられない"
            )
            continue

        components.append(component_from_dict(raw))

    excluded = data.get("excluded", {}) or {}

    # カテゴリの網羅性: 部品があるか、不要である理由が記録されているか
    covered = {c.category for c in components} | set(excluded)
    missing = set(CATEGORIES) - covered
    if missing:
        problems.append(
            "次のカテゴリが未確認です。部品を追加するか、excluded に不要な理由を書くこと: "
            + ", ".join(f"{m}（{CATEGORIES[m]}）" for m in sorted(missing))
        )

    if problems:
        raise BomError(
            f"{path} に不備があります。設計（段階 4）に進めません:\n"
            + "\n".join(f"  - {p}" for p in problems)
        )

    bom = Bom(project=data.get("project", path.parent.name), components=components, excluded=excluded)

    # 暫定寸法は骨格設計を止めないが、確定していないことを明示的に警告する。
    # 印刷・発注の前に verify.assert_no_provisional() で確定を確認すること。
    if bom.provisional:
        warnings.warn(
            f"{path}: 寸法が暫定（provisional）の部品があります。"
            "骨格設計は進められますが、印刷・発注の前に実測して確定すること: "
            + ", ".join(c.id for c in bom.provisional),
            stacklevel=2,
        )

    return bom
