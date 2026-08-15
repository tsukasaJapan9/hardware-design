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
parts/          部品ライブラリ。1 部品 1 YAML（＋実形状モデルの .py）
                寸法・出典はここだけが持ち、プロジェクトは use: で参照する
hwlib/
  bom.py        部品表の読み込みと検証（寸法未確定なら設計に進ませない）
  library.py    部品ライブラリの読み込み
  verify.py     収まり・干渉・工具アクセス・挿入性・印刷可否の検証
  features.py   タッピングボス、バカ穴、コネクタ開口
  render.py     目視確認用の PNG 生成、ocp_vscode への送信
  drawing.py    三面図（第三角法）の SVG 生成
  bom_catalog.py  部品ライブラリと全 BOM を三面図つき HTML カタログにまとめる
projects/       設計プロジェクト（1 案件 1 ディレクトリ）
datasheets/     寸法の根拠にした公式図面・データシートの現物
tests/          hwlib 自体のテスト
```

## 部品ライブラリ

部品はプロジェクトの外（`parts/`）に置き、複数のプロジェクトから使い回す。

```yaml
# projects/my_case/bom.yaml
components:
  - use: raspberry_pi_zero_2w    # parts/raspberry_pi_zero_2w.yaml の寸法・出典を使う
    id: pi_zero                  # このプロジェクトでの呼び名
    clearance: 2.0
    retention: M2.6 タッピングネジ x4
```

`bom.yaml` に書けるのは「どう使うか」だけ。寸法・取付穴・コネクタ・出典を
プロジェクト側に書くとエラーになる。これで同じ部品の寸法が散らばらない。

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
uv run python -m hwlib.bom_catalog     # docs/bom_catalog.html
```

部品ライブラリと `projects/*/bom.yaml` を、三面図（第三角法）と仕様の一覧にした HTML を出す。
共有部品は図つきで 1 回だけ載り、使用プロジェクトがリンクで並ぶ。
**部品や BOM を作った・変えたら作り直す**（生成対象は `parts/` と全プロジェクトなので、
新しいファイルは置くだけで載る）。全部品ぶんのカードが出ることは `uv run pytest` が確認する。
図は部品の形状を build123d で投影したもので、手描きではないため形状と図がずれない。
図の出所は部品ごとに 3 種類あり、カードに明示する。

- **実形状** — 部品ファイルの `shape:` が実形状モデルを指す部品（図面・実測に基づく）
- **外形近似** — `size` から作った直方体。取付穴が分かっていれば穴も開ける
- **略図** — 締結部品。呼び径と首下長さのみ

`--fragment` を付けると `<style>` と `<main>` だけを出力する（Artifact などに貼る用）。

生成物だが `docs/bom_catalog.html` はリポジトリに含める。部品を変えたときの差分を
レビューで追えるようにするため。**部品や BOM を変えたら作り直してコミットする。**
（`out/` は STL・確認用 PNG と同じ捨ててよい生成物の置き場で、`.gitignore` 対象）

## リファレンス実装

`projects/example_camera_case/` — Raspberry Pi Zero 2 W + カメラ + バッテリーのケース。
5 段階を一通り通した例。外形 85 x 121 x 25 mm。
