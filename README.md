# hardware-design

build123d による 3D プリント筐体・ブラケット・ロボット部品の設計。

Claude Code のスキル `.claude/skills/hardware-design/` として使う。
ヒアリング → 部品の洗い出し → 寸法調査 → CAD 設計 → 検証 の 5 段階で設計を進める。

## 何を保証するか

1. **必要な部品が部品表にすべて含まれていること**
2. **3D プリントした外装にすべての部品が収まり、ネジで実際に組み立てられること**

Claude は形状を直接見られない。そこで正しさは `hwlib/verify.py` で機械的に確認し、
そのうえで PNG を生成して目視確認し、最後に ocp_vscode で人間が確認する。

build123d のブール減算は、対象に当たらなくても例外を出さない。体積も面数も変わらないまま
処理が成功するため、**穴あけが効かなくてもエラーにならない**。レンダリングもこの不正な形状に
対して成功する。したがって検証は「数値 → 画像 → 人間」の順に行う。

## 構成

```
.claude/skills/hardware-design/   スキル本体（ワークフローと参照資料）
hwlib/
  bom.py        部品表の読み込みと検証（寸法未確定なら設計に進ませない）
  verify.py     収まり・干渉・工具アクセス・挿入性・印刷可否の検証
  features.py   タッピングボス、バカ穴、コネクタ開口
  render.py     目視確認用の PNG 生成、ocp_vscode への送信
  catalog.py    調査済み部品の寸法
  drawing.py    三面図（第三角法）の SVG 生成
  bom_catalog.py  全 BOM を三面図つき HTML カタログにまとめる
projects/       設計プロジェクト（1 案件 1 ディレクトリ）
tests/          hwlib 自体のテスト
```

## 使い方

```bash
uv sync
uv run pytest                                                  # 検証
uv run python -m projects.example_camera_case.model --render   # PNG を出力
uv run python -m projects.example_camera_case.model --show     # ocp_vscode で表示
uv run python -m projects.example_camera_case.model --export   # STL / STEP を出力
```

`--show` には VSCode の OCP CAD Viewer 拡張が必要。

## BOM カタログ

```bash
uv run python -m hwlib.bom_catalog     # out/bom_catalog.html
```

`projects/*/bom.yaml` の全部品を、三面図（第三角法）と仕様の一覧にした HTML を出す。
図は BOM の値から作った形状を build123d で投影したもので、手描きではないため
形状と図がずれない。図の出所は部品ごとに 3 種類あり、カードに明示する。

- **実形状** — `hwlib.parts` に実形状モデルがある部品（図面・実測に基づく）
- **外形近似** — BOM の `size` から作った直方体。取付穴が分かっていれば穴も開ける
- **略図** — 締結部品。呼び径と首下長さのみ

`--fragment` を付けると `<style>` と `<main>` だけを出力する（Artifact などに貼る用）。

## リファレンス実装

`projects/example_camera_case/` — Raspberry Pi Zero 2 W + カメラ + バッテリーのケース。
5 段階を一通り通した例。外形 85 x 121 x 25 mm。
