# このリポジトリの約束事

## 文章は日本語で書く

新しく作るファイルは日本語。対象は、README、スキル定義、コード中のコメントと docstring、
検証器が出力するメッセージ、コミットメッセージ、PR 本文。人間が読むテキストすべて。

コードの識別子は英語のまま。変数名、関数名、クラス名、辞書のキー、`Mode.SUBTRACT` のような
ライブラリ由来の語。

### 文体

- **体言止めを基本とする**
- 「です・ます」調は使わない
- 1文に1つの内容

### 簡潔かつ明確に

削るもの。

- 言い換えによる繰り返し
- 前置きと断り書き
- 中身のない言い回し（「〜という点に留意が必要」）
- 修辞と比喩
- 読者の行動を変えない情報

残すもの。事実と、その根拠。とくに**なぜそうなのか**。

「最小肉厚 1.2mm」だけでは不足。「外周3本ぶん。2本ではあいだにインフィルが入らず割れる」まで
書く。理由のない規則は、状況が変わったときに誰も判断できない。

簡潔さと明確さが衝突したら、明確さを優先。読み返させたり質問させたりすれば、短く書いて
節約した分は消える。

### 日本語で直接書く

英語で下書きしてから訳さない。英語の語順と修辞構造が残り、日本語として読めないものになる。

内容だけを持って、白紙から日本語で書く。英語版を横に置かない。

### 技術用語

定着した日本語の技術用語を使う。造語や直訳はしない。

初出時は「日本語（English）」と併記。2回目以降は日本語のみ。併記の目的は、一次資料
（build123d のドキュメント、OCC の API、スライサーの設定項目、ネジやベアリングの規格）が
すべて英語であるため、検索できる語を残すこと。

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

定訳が無い語、あるいは英語のほうが通りが良い語は、英語のまま使う。併記しない
（keepout、footprint、datum など）。迷ったら、その分野の技術者が実際に口にする語を選ぶ。

**表に無い技術用語を使ったら、その場で表に追加。** 同じ変更のコミットに含める。訳語を決める
のは、その語を最初に使うとき。あとでまとめてやると、同じ語が場所によって違う訳になり、
検索もできなくなる。

訳語を変えたら、既存の日本語ファイル全体を新しい訳語に統一する。表と本文が食い違う状態を
残さない。

## 設計

設計の作法はスキルにある。ハードウェアを設計する前に読む。

- `.claude/skills/build123d-hardware/SKILL.md` — ワークフローと教義
- `.claude/skills/build123d-hardware/references/design-rules.md` — 数値と、その根拠
- `.claude/skills/build123d-hardware/references/build123d-api.md` — build123d の落とし穴
- `.claude/skills/build123d-hardware/references/components.md` — 買う部品の測り方

## git

新しい実装を始める前に、必ず main に戻ってから作業ブランチを切る。

```bash
git checkout main && git pull
git checkout -b feature/<name>
```

## 検証

コードを変更したら、コミット前に必ず通す。

```bash
uv run pytest                                 # 検証器は答えが既知のテストで固定してある
uv run python -m examples.parts_box           # 3つの設計がすべて通ることを確認
uv run python -m examples.motor_mount
uv run python -m examples.roller_bracket
```

検証器のメッセージ文言はテストが assert している。出力を変えたら、テストも一緒に直す。
