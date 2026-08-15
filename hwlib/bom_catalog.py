"""BOM カタログ（HTML）の生成。

部品ライブラリ（parts/）と projects/*/bom.yaml を読み、1 枚の HTML にまとめる。

  部品ライブラリ    共有部品を三面図つきで 1 回だけ載せ、使用プロジェクトを示す
  プロジェクト別    どの部品をどう使うか（固定方法・クリアランス・設計上の判断）

同じ部品を複数のプロジェクトで使っても図と寸法は 1 か所にまとまる。

図は部品の形状を build123d で投影したもの（hwlib.drawing）。形状の出所は
3 通りあり、カードに明示する。

  実形状     parts/*.yaml の shape: が指す実形状モデル（図面・実測に基づく）
  外形近似   size から作った直方体。取付穴があれば穴も開ける
  略図       締結部品。呼び径と首下長さだけを図示する

使い方:
    uv run python -m hwlib.bom_catalog              # out/bom_catalog.html に出力
    uv run python -m hwlib.bom_catalog --fragment   # body 断片のみ（Artifact 用）
"""

from __future__ import annotations

import sys
import warnings
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from build123d import Align, Cylinder, Part, Pos

from hwlib.bom import CATEGORIES, Bom, Component, Connector, component_from_dict, load_bom
from hwlib.drawing import Mark, fastener_svg, three_view_svg
from hwlib.library import all_parts, load_shape

ROOT = Path(__file__).resolve().parent.parent
PROJECTS_DIR = ROOT / "projects"
DEFAULT_OUT = ROOT / "out" / "bom_catalog.html"

# 寸法の信頼度。ラベル、意味、強調の種別。
CONFIDENCE: dict[str, tuple[str, str, str]] = {
    "datasheet": ("データシート", "メーカーの機械図面・データシートに基づく（出典 URL あり）", "ok"),
    "measured": ("実測", "ユーザがノギスで実測した値", "ok"),
    "user_provided": ("ユーザ指定", "ユーザが直接指定した値", "ok"),
    "provisional": ("暫定", "仮値。骨格設計には使えるが、印刷・発注の前に実測して確定する", "warn"),
}

FACE_LABEL = {
    "+x": "右面 (+X)", "-x": "左面 (-X)", "+y": "背面 (+Y)",
    "-y": "前面 (-Y)", "+z": "上面 (+Z)", "-z": "底面 (-Z)",
}


def category_label(category: str) -> str:
    """カテゴリの短い名前。CATEGORIES の説明から括弧の前だけを取る。"""
    return CATEGORIES[category].split("（")[0]


def esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def fmt(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


# --- 形状 ---------------------------------------------------------------


@dataclass(frozen=True)
class Drawing:
    """1 部品ぶんの図と、その図が何に基づくか。

    outline は図に描かれた外形 (W, D, H)。BOM の size と一致しないことがある
    （実形状モデルが BOM の直方体に入らない突起を持つ場合など）ため、
    食い違うときはカードに両方を出して読み手が誤解しないようにする。
    """

    svg: str
    kind: str  # "実形状" / "外形近似" / "略図"
    basis: str
    outline: tuple[float, float, float] | None = None


def mock_with_holes(component: Component) -> Part:
    """BOM の外形直方体。取付穴が分かっていれば Z 方向に開けておく。

    穴を実際に開けるのは、投影がそのまま平面図の円・正面図の破線になるため。
    図に手で描き足すより形状と図が食い違わない。
    """
    part = component.mock()
    if component.mount_holes and component.hole_dia > 0:
        _, _, h = component.size
        for x, y in component.mount_holes:
            part -= Pos(x, y, 0) * Cylinder(
                component.hole_dia / 2, h, align=(Align.CENTER, Align.CENTER, Align.MIN)
            )
    return part


def face_extent(component: Component, face: str) -> tuple[float, float]:
    """コネクタが載る面の寸法 (幅, 高さ)。面内の 2 軸を size から取る。"""
    w, d, h = component.size
    return {"x": (d, h), "y": (w, h), "z": (w, d)}[face[-1]]


def connector_fits(component: Component, connector: Connector) -> bool:
    """コネクタ開口がその面に収まるか。

    収まらない場合は bom.yaml 側の食い違い（面の取り違えなど）を疑う。
    図では枠を描かず、仕様表に警告を出す。
    """
    fw, fh = face_extent(component, connector.face)
    cw, ch = connector.size
    return cw <= fw + 1e-6 and ch <= fh + 1e-6


def draw(component: Component) -> Drawing:
    """部品 1 点の図を作る。実形状 → 締結部品の略図 → 外形近似 の順に選ぶ。"""
    if component.shape:
        part = load_shape(component.shape)()
        size = part.bounding_box().size
        return Drawing(
            three_view_svg(part), "実形状",
            f"{component.shape}（部品ライブラリの shape:）",
            (size.X, size.Y, size.Z),
        )

    if component.category == "fastener":
        nominal, _, length = component.size
        return Drawing(
            fastener_svg(nominal, length),
            "略図",
            "呼び径と首下長さのみ（size より）",
        )

    marks = [
        Mark(label=c.name, face=c.face, pos=c.pos, size=c.size,
             outline=connector_fits(component, c))
        for c in component.connectors
    ]
    basis = "size から作った直方体"
    if component.mount_holes and component.hole_dia > 0:
        basis += f"＋取付穴 φ{fmt(component.hole_dia)} × {len(component.mount_holes)}"
    return Drawing(three_view_svg(mock_with_holes(component), marks=marks), "外形近似", basis)


# --- HTML ---------------------------------------------------------------


def spec_rows(component: Component, drawing: Drawing) -> str:
    """部品そのものの仕様（ライブラリが持つ値）。使い方はプロジェクト側に出す。"""
    w, d, h = component.size
    label, meaning, tone = CONFIDENCE[component.confidence]

    rows: list[tuple[str, str]] = [
        ("外形寸法", f"W {fmt(w)} × D {fmt(d)} × H {fmt(h)} mm"
                     f'<span class="muted"> CAD の収まり検証はこの値で行う</span>'),
        ("カテゴリ", f"{category_label(component.category)}<span class=\"muted\"> / {component.category}"
                     "（プロジェクトで上書き可）</span>"),
        (
            "寸法の信頼度",
            f'<span class="badge {tone}">{label}</span>'
            f'<span class="muted"> {esc(meaning)}</span>',
        ),
        ("図の種別", f'<span class="badge kind">{drawing.kind}</span>'
                     f'<span class="muted"> {esc(drawing.basis)}</span>'),
    ]

    # 図の外形が size の直方体と食い違う場合は、その差を明示する
    if drawing.outline and any(
        abs(a - b) > 0.05 for a, b in zip(drawing.outline, component.size)
    ):
        ow, od, oh = drawing.outline
        rows.append(
            ("図上の外形", f"W {fmt(ow)} × D {fmt(od)} × H {fmt(oh)} mm"
                           f'<span class="muted"> 実形状モデルの外形。size は'
                           f"ケース部の値で、突起（ホーンなど）を含まないため一致しない</span>")
        )

    if component.mount_holes:
        holes = "、".join(f"({fmt(x)}, {fmt(y)})" for x, y in component.mount_holes)
        rows.insert(2, ("取付穴", f"φ{fmt(component.hole_dia)} × {len(component.mount_holes)}"
                                  f'<span class="muted"> 中心座標 {holes}</span>'))
    if component.connectors:
        items = []
        for i, c in enumerate(component.connectors, start=1):
            warn = ""
            if not connector_fits(component, c):
                fw, fh = face_extent(component, c.face)
                warn = (
                    f'<div class="inline-warn">開口 {fmt(c.size[0])} × {fmt(c.size[1])} mm が'
                    f"{FACE_LABEL.get(c.face, c.face)}（{fmt(fw)} × {fmt(fh)} mm）に収まらない。"
                    "部品ライブラリの face か開口寸法を要確認（図では枠を描かず位置だけ示す）</div>"
                )
            items.append(
                f'<li><span class="num">{i}</span> {esc(c.name)}'
                f'<span class="muted"> {FACE_LABEL.get(c.face, c.face)} / '
                f"開口 {fmt(c.size[0])} × {fmt(c.size[1])} mm / "
                f"挿抜空間 {fmt(c.depth)} mm</span>{warn}</li>"
            )
        rows.append(("コネクタ開口", f'<ul class="conn">{"".join(items)}</ul>'))
    if component.source:
        rows.append(("出典", f'<a href="{esc(component.source)}">{esc(component.source)}</a>'))
    if component.datasheet:
        rows.append(("図面", f"<code>{esc(component.datasheet)}</code>"
                             '<span class="muted"> リポジトリに保存した現物</span>'))

    return "".join(
        f'<tr><th>{key}</th><td>{value}</td></tr>' for key, value in rows
    )


def card_html(component: Component, *, anchor: str, users: str = "", source_file: str = "") -> str:
    """部品 1 点のカード（三面図＋仕様）。"""
    drawing = draw(component)
    note = (
        f'<p class="note">{esc(component.note.strip())}</p>'
        if component.note.strip() else ""
    )
    tags = [f'<span class="tag">{category_label(component.category)}</span>']
    if component.confidence == "provisional":
        tags.append('<span class="tag warn">寸法 暫定</span>')

    return f"""
<article class="card" id="{esc(anchor)}">
  <header class="card-head">
    <h3>{esc(component.name)}</h3>
    <div class="tags"><code>{esc(component.id)}</code>{"".join(tags)}</div>
    {f'<p class="path"><code>{esc(source_file)}</code></p>' if source_file else ""}
  </header>
  <div class="card-body">
    <figure class="drawing">{drawing.svg}</figure>
    <div class="spec">
      <table>{spec_rows(component, drawing)}</table>
      {note}
      {users}
    </div>
  </div>
</article>"""


def library_components() -> dict[str, Component]:
    """部品ライブラリを Component にして返す（図と仕様の生成用）。"""
    return {pid: component_from_dict(part) for pid, part in all_parts().items()}


def usage(boms: list[tuple[Path, Bom]]) -> dict[str, list[tuple[str, str]]]:
    """ライブラリ部品 id → [(プロジェクト, そこでの部品 id), ...]。"""
    used: dict[str, list[tuple[str, str]]] = {}
    for _, bom in boms:
        for c in bom.components:
            if c.library_id:
                used.setdefault(c.library_id, []).append((bom.project, c.id))
    return used


def usage_html(users: list[tuple[str, str]]) -> str:
    if not users:
        return ('<p class="users"><span class="muted">まだどのプロジェクトからも'
                "使われていない</span></p>")
    links = "".join(
        f'<a class="chip" href="#{esc(project)}--{esc(cid)}">{esc(project)}'
        f'<span class="muted"> / {esc(cid)}</span></a>'
        for project, cid in users
    )
    return f'<p class="users"><span class="users-label">使用</span>{links}</p>'


def library_html(boms: list[tuple[Path, Bom]]) -> str:
    """部品ライブラリの section。共有部品を三面図つきで 1 回だけ載せる。"""
    used = usage(boms)
    components = library_components()
    cards = "".join(
        card_html(
            component,
            anchor=f"part--{pid}",
            users=usage_html(used.get(pid, [])),
            source_file=f"parts/{pid}.yaml",
        )
        for pid, component in sorted(components.items())
    )
    return f"""
<section class="library" id="library">
  <h2>部品ライブラリ</h2>
  <p class="summary"><code>parts/</code> に置いた共有部品 {len(components)} 点。
  寸法・出典はここだけが持ち、プロジェクトは <code>use:</code> で参照する。</p>
  {cards}
</section>"""


def project_summary(path: Path) -> tuple[str, str]:
    """brief.md から見出しと最初の段落を取る。無ければ空文字。"""
    brief = path / "brief.md"
    if not brief.exists():
        return "", ""
    title, summary = "", ""
    lines = brief.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            title = line[2:].split("—")[0].strip()
            rest = [ln.strip() for ln in lines[i + 1:]]
            paragraph: list[str] = []
            for ln in rest:
                if ln.startswith("#"):
                    break
                if not ln:
                    if paragraph:
                        break
                    continue
                paragraph.append(ln)
            summary = " ".join(paragraph)
            break
    return title, summary


def component_row(bom: Bom, c: Component) -> str:
    """プロジェクトの部品 1 行（どう使うか）。"""
    if c.library_id:
        part = (f'<a href="#part--{esc(c.library_id)}">{esc(c.name)}</a>'
                f'<span class="sub">parts/{esc(c.library_id)}.yaml</span>')
    else:
        part = (f'{esc(c.name)}<span class="sub">bom.yaml に直接記載'
                "（ライブラリ未登録）</span>")
    w, d, h = c.size
    dash = '<span class="muted">—</span>'
    retention = esc(c.retention) if c.retention else dash
    clearance = fmt(c.clearance) if c.geometric else dash
    placed = "配置する" if c.geometric else '<span class="muted">しない</span>'
    return (
        f'<tr id="{esc(bom.project)}--{esc(c.id)}">'
        f"<td><code>{esc(c.id)}</code></td>"
        f'<td class="part-cell">{part}</td>'
        f'<td class="num-cell">{fmt(w)} × {fmt(d)} × {fmt(h)}</td>'
        f'<td class="ret-cell">{retention}</td>'
        f'<td class="num-cell">{clearance}</td>'
        f"<td>{placed}</td>"
        f'<td class="note-cell">{esc(project_note(c))}</td>'
        "</tr>"
    )


def project_note(c: Component) -> str:
    """プロジェクト側で書いた note。ライブラリ由来の行は落とす。

    note は「ライブラリの note ＋ プロジェクトの note」を改行でつないだもの
    （hwlib.bom.resolve_library_ref）。プロジェクト表にはその後半だけを出す。
    """
    if not c.library_id:
        return c.note.strip()
    library_note = (all_parts().get(c.library_id, {}).get("note") or "").strip()
    text = c.note.strip()
    if library_note and text.startswith(library_note):
        text = text[len(library_note):]
    return text.strip()


def project_html(path: Path, bom: Bom) -> str:
    title, summary = project_summary(path)
    heading = title or bom.project
    excluded = "".join(
        f"<li><b>{category_label(cat)}</b>：{esc(reason)}</li>"
        for cat, reason in sorted(bom.excluded.items())
    )
    excluded_block = (
        f'<details class="excluded"><summary>不要と判断したカテゴリ '
        f'（{len(bom.excluded)} 件）</summary><ul>{excluded}</ul></details>'
        if bom.excluded else ""
    )
    rows = "".join(component_row(bom, c) for c in bom.components)
    # ライブラリに無い部品（直書き）は図が他に出ないので、ここにカードを置く
    cards = "".join(
        card_html(c, anchor=f"{bom.project}--{c.id}--card")
        for c in bom.components if not c.library_id
    )
    return f"""
<section class="project" id="{esc(bom.project)}">
  <h2>{esc(heading)}</h2>
  <p class="path"><code>projects/{esc(bom.project)}/bom.yaml</code> · 部品 {len(bom.components)} 点</p>
  {f'<p class="summary">{esc(summary)}</p>' if summary else ""}
  {excluded_block}
  <div class="scroll">
  <table class="list">
    <thead><tr><th>id</th><th>部品（ライブラリ）</th><th>W × D × H [mm]</th>
    <th>固定方法</th><th>クリアランス [mm]</th><th>CAD 配置</th><th>設計上の判断</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  </div>
  {cards}
</section>"""


def index_html(boms: list[tuple[Path, Bom]]) -> str:
    used = usage(boms)
    rows = []
    for pid, component in sorted(library_components().items()):
        label, _, tone = CONFIDENCE[component.confidence]
        w, d, h = component.size
        # 同じプロジェクトで複数回使う部品は、どの部品として使っているかも出す
        seen = [project for project, _ in used.get(pid, [])]
        users = "".join(
            f'<a class="chip" href="#{esc(project)}--{esc(cid)}">{esc(project)}'
            + (f'<span class="muted"> / {esc(cid)}</span>' if seen.count(project) > 1 else "")
            + "</a>"
            for project, cid in used.get(pid, [])
        ) or '<span class="muted">未使用</span>'
        rows.append(
            f'<tr><td><a href="#part--{esc(pid)}"><code>{esc(pid)}</code></a></td>'
            f"<td>{esc(component.name)}</td>"
            f"<td>{category_label(component.category)}</td>"
            f'<td class="num-cell">{fmt(w)} × {fmt(d)} × {fmt(h)}</td>'
            f'<td><span class="badge {tone}">{label}</span></td>'
            f"<td>{users}</td></tr>"
        )
    return f"""
<section class="index">
  <h2>部品一覧</h2>
  <div class="scroll">
  <table class="list">
    <thead><tr><th>部品 id</th><th>部品名</th><th>カテゴリ</th>
    <th>W × D × H [mm]</th><th>寸法の信頼度</th><th>使用プロジェクト</th></tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
  </div>
</section>"""


def provisional_html(boms: list[tuple[Path, Bom]]) -> str:
    items = [
        f"<li><code>{esc(bom.project)}</code> / <code>{esc(c.id)}</code> "
        f"{esc(c.name)}<span class=\"muted\"> — {esc(c.note.strip().splitlines()[0] if c.note.strip() else '')}</span></li>"
        for _, bom in boms
        for c in bom.provisional
    ]
    if not items:
        return ""
    return f"""
<section class="callout">
  <h2>寸法が暫定の部品（{len(items)} 点）</h2>
  <p>骨格設計には使えるが、印刷・発注の前に実測して確定すること。</p>
  <ul>{"".join(items)}</ul>
</section>"""


LEGEND = """
<section class="legend">
  <h2>図の読み方</h2>
  <div class="legend-grid">
    <div>
      <h3>投影法</h3>
      <p>第三角法。左下が正面図（-Y から見る）、その上が平面図（+Z から見下ろす）、
      右が右側面図（+X から見る）。</p>
    </div>
    <div>
      <h3>線種</h3>
      <ul class="linekey">
        <li><svg width="42" height="10"><line class="edge" x1="2" y1="5" x2="40" y2="5"/></svg> 見える稜線</li>
        <li><svg width="42" height="10"><line class="hidden" x1="2" y1="5" x2="40" y2="5"/></svg> 隠れた稜線</li>
        <li><svg width="42" height="10"><line class="dim" x1="2" y1="5" x2="40" y2="5"/></svg> 寸法（mm）</li>
        <li><svg width="42" height="10"><rect class="mark" x="2" y="1" width="38" height="8"/></svg> コネクタ開口</li>
      </ul>
    </div>
    <div>
      <h3>寸法</h3>
      <p>W（幅 X）・D（奥行き Y）・H（高さ Z）を 1 回ずつ記入。値は部品ライブラリの
      <code>size</code>、実形状モデルの部品はその外形。単位は mm。</p>
    </div>
    <div>
      <h3>図の種別</h3>
      <ul>
        <li><span class="badge kind">実形状</span> 図面・実測に基づく実際の形</li>
        <li><span class="badge kind">外形近似</span> 外形寸法から作った直方体</li>
        <li><span class="badge kind">略図</span> 締結部品。呼び径と首下長さのみ</li>
      </ul>
    </div>
    <div>
      <h3>部品とプロジェクトの分担</h3>
      <p>寸法・取付穴・コネクタ・出典は <code>parts/&lt;id&gt;.yaml</code> が持つ。
      固定方法・クリアランス・CAD に配置するかは、使う側の
      <code>bom.yaml</code> が決める。</p>
    </div>
  </div>
</section>"""


CSS = """
:root {
  --bg: #f6f7f9; --panel: #ffffff; --ink: #1a1d21; --muted: #6b7280;
  --line: #d8dce2; --edge: #1f2933; --hidden: #9aa3ad; --dim: #c0392b;
  --mark: #2563eb; --accent: #1f6feb; --warn-bg: #fff4e5; --warn-ink: #92400e;
  --ok-bg: #eaf3ff; --ok-ink: #1e4d91; --kind-bg: #eef0f3; --kind-ink: #454b54;
  --fill: #e9ecef;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #14171a; --panel: #1c2024; --ink: #e6e8ea; --muted: #98a1ac;
    --line: #2f353c; --edge: #d7dde3; --hidden: #6d7681; --dim: #ff8a75;
    --mark: #6ea8ff; --accent: #79b8ff; --warn-bg: #3a2c14; --warn-ink: #f0c274;
    --ok-bg: #16283f; --ok-ink: #9dc4f5; --kind-bg: #262b31; --kind-ink: #b6bec7;
    --fill: #2a3037;
  }
}
:root[data-theme="dark"] {
  --bg: #14171a; --panel: #1c2024; --ink: #e6e8ea; --muted: #98a1ac;
  --line: #2f353c; --edge: #d7dde3; --hidden: #6d7681; --dim: #ff8a75;
  --mark: #6ea8ff; --accent: #79b8ff; --warn-bg: #3a2c14; --warn-ink: #f0c274;
  --ok-bg: #16283f; --ok-ink: #9dc4f5; --kind-bg: #262b31; --kind-ink: #b6bec7;
  --fill: #2a3037;
}

body {
  margin: 0; padding: 0 20px 80px;
  background: var(--bg); color: var(--ink);
  font-family: "Hiragino Sans", "Noto Sans JP", "Yu Gothic", Meiryo, system-ui, sans-serif;
  line-height: 1.7; font-size: 15px;
}
main { max-width: 1080px; margin: 0 auto; }
h1 { font-size: 1.7rem; margin: 40px 0 6px; letter-spacing: .02em; text-wrap: balance; }
h2 { font-size: 1.2rem; margin: 0 0 10px; text-wrap: balance; }
h3 { font-size: 1rem; margin: 0 0 6px; text-wrap: balance; }
a { color: var(--accent); }
a:focus-visible, summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px;
  border-radius: 2px; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .88em; }
.lead { color: var(--muted); margin: 0 0 28px; }
.muted { color: var(--muted); font-weight: normal; }
.scroll { overflow-x: auto; }

section { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
  padding: 20px 22px; margin: 0 0 22px; }
.project { padding-bottom: 8px; }
.path { margin: -6px 0 10px; color: var(--muted); font-size: .85rem; }
.summary { margin: 0 0 14px; }

table { border-collapse: collapse; width: 100%; }
.list { font-size: .9rem; min-width: 720px; }
.list th, .list td { text-align: left; padding: 7px 8px; border-bottom: 1px solid var(--line); }
.list th:first-child, .list td:first-child { padding-left: 0; }
.list thead th { color: var(--muted); font-weight: 600; white-space: nowrap; }
.num-cell { white-space: nowrap; font-variant-numeric: tabular-nums; }

.card { border: 1px solid var(--line); border-radius: 8px; margin: 0 0 18px;
  background: var(--panel); overflow: hidden; }
.card-head { padding: 12px 16px; border-bottom: 1px solid var(--line); }
.card-head h3 { margin: 0; font-size: 1.02rem; }
.tags { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 6px; }
.tag { font-size: .74rem; padding: 1px 8px; border-radius: 999px;
  background: var(--kind-bg); color: var(--kind-ink); }
.tag.ghost { background: transparent; border: 1px solid var(--line); color: var(--muted); }
.tag.warn { background: var(--warn-bg); color: var(--warn-ink); }
.card-body { display: grid; grid-template-columns: minmax(0, max-content) minmax(300px, 1fr);
  gap: 4px 18px; padding: 14px 16px 18px; align-items: start; }
.drawing { margin: 0; overflow-x: auto; }
.spec table th { text-align: left; vertical-align: top; white-space: nowrap;
  color: var(--muted); font-weight: 600; font-size: .84rem; padding: 5px 12px 5px 0; }
.spec table td { vertical-align: top; font-size: .88rem; padding: 5px 0;
  border-bottom: 1px solid var(--line); word-break: break-word;
  font-variant-numeric: tabular-nums; }
.spec table tr:last-child td { border-bottom: none; }
.note { font-size: .85rem; color: var(--muted); margin: 12px 0 0;
  border-left: 2px solid var(--line); padding-left: 10px; white-space: pre-line; }
ul.conn { margin: 0; padding-left: 0; list-style: none; }
ul.conn li { margin-bottom: 3px; }
.inline-warn { background: var(--warn-bg); color: var(--warn-ink); border-radius: 4px;
  padding: 5px 8px; margin: 4px 0 8px; font-size: .82rem; line-height: 1.5; }
.users { display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline;
  margin: 12px 0 0; font-size: .84rem; }
.users-label { color: var(--muted); }
.chip { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: .78rem;
  background: var(--ok-bg); color: var(--ok-ink); text-decoration: none; }
.chip:hover { text-decoration: underline; }
.note-cell { min-width: 165px; font-size: .84rem; color: var(--muted); }
.ret-cell { min-width: 140px; }
.part-cell { min-width: 170px; }
.list td:last-child, .list th:last-child { padding-right: 0; }
.sub { display: block; color: var(--muted); font-size: .8rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.projects-head { padding-bottom: 12px; }
.library .card { margin-bottom: 22px; }
.card-head .path { margin: 4px 0 0; }
.num { display: inline-block; width: 16px; height: 16px; line-height: 16px; text-align: center;
  border-radius: 50%; background: var(--mark); color: #fff; font-size: .7rem; margin-right: 5px; }

.badge { display: inline-block; font-size: .74rem; padding: 1px 8px; border-radius: 4px;
  background: var(--ok-bg); color: var(--ok-ink); white-space: nowrap; }
.badge.warn { background: var(--warn-bg); color: var(--warn-ink); }
.badge.kind { background: var(--kind-bg); color: var(--kind-ink); }

.excluded { margin: 0 0 18px; font-size: .88rem; }
.excluded summary { cursor: pointer; color: var(--muted); }
.excluded ul { margin: 8px 0 0; }
.callout { border-left: 4px solid var(--warn-ink); }
.callout h2 { color: var(--warn-ink); }
.legend-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 18px; font-size: .88rem; }
.legend-grid p, .legend-grid ul { margin: 0; }
.legend-grid ul { padding-left: 18px; }
ul.linekey { list-style: none; padding: 0; }
ul.linekey li { display: flex; align-items: center; gap: 8px; }

/* 図 */
svg.tv { max-width: 100%; height: auto; display: block; }
.edge { fill: none; stroke: var(--edge); stroke-width: 1.4; stroke-linejoin: round; }
.edge.fill { fill: var(--fill); }
.hidden { fill: none; stroke: var(--hidden); stroke-width: 1; stroke-dasharray: 5 3; }
.dim { stroke: var(--dim); fill: var(--dim); stroke-width: .8; }
.ext { stroke: var(--dim); stroke-width: .5; opacity: .65; }
.dimtext { fill: var(--dim); font-size: 11px; font-family: ui-monospace, Menlo, monospace; }
.viewlabel { fill: var(--muted); font-size: 11px; }
.note-svg, svg .note { fill: var(--muted); font-size: 10px; }
.scalebar { stroke: var(--muted); stroke-width: 1; }
.center { stroke: var(--hidden); stroke-width: .7; stroke-dasharray: 9 2 2 2; }
.mark { fill: none; stroke: var(--mark); stroke-width: 1.2; stroke-dasharray: 4 2; }
.marknum { fill: var(--mark); }
.marknumtext { fill: #fff; font-size: 10px; }

@media (max-width: 780px) {
  .card-body { grid-template-columns: 1fr; }
}
"""


def build_body(boms: list[tuple[Path, Bom]]) -> str:
    used = sum(len(bom.components) for _, bom in boms)
    projects = "".join(project_html(path, bom) for path, bom in boms)
    return f"""<main>
<h1>BOM カタログ</h1>
<p class="lead">部品ライブラリ <code>parts/</code> の {len(all_parts())} 点と、
それを使う {len(boms)} プロジェクト（延べ {used} 点）· 生成日 {date.today().isoformat()}</p>
{index_html(boms)}
{provisional_html(boms)}
{LEGEND}
{library_html(boms)}
<section class="projects-head">
  <h2>プロジェクト別 BOM</h2>
  <p class="summary">どの部品をどう使うか。寸法は部品ライブラリ側にあり、
  ここに書けるのは固定方法・クリアランス・CAD に配置するか・設計上の判断だけ。</p>
</section>
{projects}
</main>"""


def load_all(projects_dir: Path = PROJECTS_DIR) -> list[tuple[Path, Bom]]:
    """projects/*/bom.yaml をすべて読む。

    暫定寸法の警告はカタログ側で一覧にするため、ここでは止めない。
    """
    out: list[tuple[Path, Bom]] = []
    for path in sorted(projects_dir.iterdir()):
        bom_file = path / "bom.yaml"
        if not bom_file.exists():
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out.append((path, load_bom(bom_file)))
    return out


def build_catalog(out_path: Path = DEFAULT_OUT, *, fragment: bool = False) -> Path:
    """カタログを生成して書き出す。fragment=True なら body 断片のみ。"""
    boms = load_all()
    body = build_body(boms)
    if fragment:
        html = f"<style>{CSS}</style>\n{body}\n"
    else:
        html = (
            "<!doctype html>\n<html lang=\"ja\">\n<head>\n"
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            "<title>BOM カタログ</title>\n"
            f"<style>{CSS}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def main() -> None:
    fragment = "--fragment" in sys.argv
    out = DEFAULT_OUT
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
    path = build_catalog(out, fragment=fragment)
    print(f"出力しました: {path}")


if __name__ == "__main__":
    main()
