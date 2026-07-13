# このリポジトリの約束事

## 文章

人間が読むテキストはすべて日本語。README、スキル定義、コメント、docstring、検証器の出力、
コミットメッセージ、PR 本文。

コードの識別子は英語のまま。変数名、関数名、クラス名、辞書のキー、`Mode.SUBTRACT` のような
ライブラリ由来の語。

### 文体

- 体言止めが基本。「です・ます」調は使わない
- 1文に1つの内容
- 英語から訳さない。内容だけを持って、日本語で書き起こす

### 削るもの

- 言い換えによる繰り返し
- 前置き（「以下に述べるように」）
- 中身のない言い回し（「〜に留意が必要」）
- 修辞と比喩
- 読み手の判断を変えない情報

### 残すもの

事実と、その根拠。

「最小肉厚 1.2mm」では足りない。「外周3本ぶん。2本ではあいだにインフィルが入らず割れる」まで
書く。根拠がなければ、条件が変わったときに誰も判断できない。

短さより分かりやすさを優先する。読み返しや質問が発生すれば、短くした意味がない。

### 技術用語

定着した用語を使う。造語や直訳は避ける。

初出時のみ「日本語（English）」と併記。一次資料（build123d、OCC、スライサー、ネジやベアリングの
規格）が英語のため、検索できる語を残す。

```
最小肉厚（wall thickness）は 1.2mm。外周3本ぶんで、2本では割れる。
ベアリングは圧入（press fit）で、押すのは外輪（outer race）だけ。
```

| 日本語 | 英語 |
|---|---|
| 圧入 | press fit |
| すきま | clearance |
| 干渉 | interference |
| 公差 | tolerance |
| オーバーハング | overhang |
| ブリッジ | bridge |
| フィレット | fillet |
| 面取り | chamfer |
| 肉厚 | wall thickness |
| ボス | boss |
| 座ぐり | counterbore |
| 皿もみ | countersink |
| 熱圧入インサート | heat-set insert |
| 内輪 / 外輪 | inner race / outer race |
| 象足 | elephant foot |
| 造形板 | build plate |
| 造形範囲 | build volume |
| 多様体 | manifold |

定訳が無い語、英語のほうが通じる語は英語のまま。併記しない（keepout、footprint、datum）。

表に無い用語を使ったら、その場で表に追加し、同じコミットに含める。あとでまとめると、同じ語が
場所によって違う訳になる。訳語を変えたときは、既存の日本語ファイルもまとめて揃える。

## 設計

設計の作法はスキルにある。ハードウェアを設計する前に読む。

- `.claude/skills/build123d-hardware/SKILL.md` — ワークフローと教義
- `.claude/skills/build123d-hardware/references/design-rules.md` — 数値と、その根拠
- `.claude/skills/build123d-hardware/references/build123d-api.md` — build123d の落とし穴
- `.claude/skills/build123d-hardware/references/components.md` — 買う部品の測り方

## git

新しい実装を始める前に、main に戻ってから作業ブランチを切る。

```bash
git checkout main && git pull
git checkout -b feature/<name>
```

## 検証

コードを変更したら、コミット前に通す。

```bash
uv run pytest
uv run python -m examples.parts_box
uv run python -m examples.motor_mount
uv run python -m examples.roller_bracket
```

検証器のメッセージ文言はテストが assert している。出力を変えたら、テストも直す。
