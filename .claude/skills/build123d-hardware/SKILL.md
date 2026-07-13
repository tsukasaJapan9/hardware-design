---
name: build123d-hardware
description: build123d による 3D プリント部品の設計。実測プロファイル由来の公差、金属締結（熱圧入インサート・ナット・ネジ）、ベアリング、Joint による組立、幾何検証（肉厚・オーバーハング・干渉・挿入経路・すきま）、STL/STEP/部品表の出力。ブラケット、マウント、筐体、機構、治具など、他の部品と嵌め合う印刷部品を設計するときに使う。Use when designing 3D-printable brackets, mounts, enclosures, mechanisms or jigs that must mate with other parts or bought hardware.
---

# build123d で「組み立てられる」部品を設計する

見た目が正しくても、組み立てられなければ失敗作。「CAD 上は合っている」と「刷った部品が
組み上がる」のあいだには、4つの隔たりがある。

1. **公差（tolerance）** — φ3.0 でモデリングした穴は約 2.85mm で出る。寸法はすべて実測済みの
   `PrinterProfile` から導出し、数値を直接書かない。
2. **締結** — 印刷したねじ山はすぐ潰れる。熱圧入インサート（heat-set insert）・ナット・
   機械ねじを使う。
3. **製造性** — オーバーハング（overhang）は垂れ、薄い壁は消え、小さい穴は潰れる。
4. **干渉（interference）** — 部品どうしは同じ空間を占められない。回る部品には回るための
   空間が必要。

1つ目は測るしかない。残り3つは検査できるので、`hwkit` が検査する。問題が見つかるのは
4時間の造形後ではなく、数秒後。

## 実行

```bash
uv run python -m examples.<name>            # 検証してレポートを表示
uv run python -m examples.<name> --export   # 検証を通れば out/<name>/ へ出力
uv run python -m hwkit.calibrate            # 較正クーポンの出力
uv run python -m tools.view <name>          # OCP CAD ビューアで実形状を確認
```

## ワークフロー

### 0. 設計より先に、買う部品のモデリング

ブラケットの形状は、保持する部品の寸法をそのまま写した空洞として決まる。部品の寸法が
推測なら、出来上がるのも推測を写した造形物。

サーボ、センサ、基板、バッテリー、モーター。設計を始める前に、それぞれを
`hwkit/components.py` の `Component` として登録する。実寸法、取付穴、そして **keepout**。
これが済むまで、後の工程は始めない。

ネジ穴の位置だけでは足りない。部品はネジではぶつからない。ぶつかるのは、挿す空間のない
USB プラグ、壁に向かって出るサーボのケーブル、ブラケットの腕と重なるホーンの回転軌跡、
1mm 膨らんだバッテリー。これらを keepout 体積として登録すれば、干渉チェックが実体と
同じ扱いで検査する。

```python
SOME_SENSOR = Component(
    name="...", kind="sensor",
    source="ノギスで実測、2026-07-13",     # またはデータシート名
    verified=True,                          # 実物と照合して初めて True
    vols=(
        Vol("box", (25.0, 11.0, 1.6), at=(0, 0, 0), why="基板本体"),
        Vol("box", (8.0, 6.0, 12.0), at=(-8, 0, 1.6), role="keepout",
            why="JST コネクタの挿抜空間"),
    ),
    mounts=(Mount(-9.0, 0.0, 2.2, "M2"), Mount(9.0, 0.0, 2.2, "M2")),
)
```

**データム（datum）。** z = 0 が取付面。原点はネジ穴パターンの中心。**+Z が部品の載る側、
−Z がブラケットを貫く側。** モーターのパイロットボス（pilot boss）と軸、開口部から垂れ下が
るサーボの筐体、基板裏のはんだ面 — 負の Z にある形状が「ブラケットのここに穴が必要」と伝える。

登録後は `asm.bought("motor", NEMA17)` がエンベロープ（envelope。本体 + keepout）を検査に
渡し、`MountHoles(NEMA17, kind="insert")` が配置先の面に取付穴パターンを開ける。

#### 寸法が分からないとき: ユーザーに訊く。推測しない

代替手段なし。ライブラリに無い部品、または `verified=False` の部品を使おうとすると、
設計はそこで止まる。

```
MissingComponentData: 'SG90 micro servo' is in the library but NOT verified.
These numbers are nominal. Ask the user to confirm them against the part in
their hand before anything gets printed.
```

これが出たら、あるいはモデルの無い部品をユーザーが指定したら、作業を止めて
`hwkit.components.CHECKLIST[kind]` の項目を引用して訊く。

> このブラケットの設計にはサーボの実寸法が必要です。SG90 は個体差が大きいので、
> お手元のものを測っていただくか、データシートをいただけますか。
> - 本体の長さ × 幅 × 高さ（タブではなく筐体）
> - タブのネジ穴の中心間距離と、穴の直径
> - 出力軸の位置（ネジ穴パターン中心からのずれと方向）
> - ホーンの突出量と、回転軌跡の直径
> - ケーブルが出る面と、曲げに必要な空間

写真から寸法を読まない。ネット上の値を平均しない。「あとで直す」前提の仮の値も置かない。
1mm 違えば刷り直しになる。回答が得られたら、出所を `source=` に記録した `Component` を
追加し、`verified=True` にしてから設計に入る。

質問は一度にまとめて出す。1項目ずつ訊いて設計に戻る繰り返しは、ユーザーの負担が大きい。

ライブラリには `NEMA17` と `RPI5` が検証済み（公開規格）、`SG90` と `CELL_18650` が公称値・
未検証として入っている。未検証の2つはユーザーに質問するための出発点であり、そのまま印刷
してよいという意味ではない。

### 1. 較正。プリンタと材料の組ごとに1回

嵌合（fit）を信用する前に、まず較正（calibration）。圧入（press fit）が決まるか、ボスが
割れるかの分かれ目。

```bash
uv run python -m hwkit.calibrate    # -> out/calibration.stl
```

刷って、ノギスで測り、`printer_profile.json` に書き込み、`"calibrated": true` にする。
それまで、すべての部品表に未較正の警告が載る。`PrinterProfile()` の既定値は FDM/PLA の
一般的な値であって、目の前のプリンタの値ではないから。

未較正のままなら、その旨を一度伝えて先へ進む。既定値を実測値のように扱わない。

### 2. 部品ではなく、アセンブリの設計

部品はアセンブリを設計した結果として決まる。`Assembly` から始め、何と何が嵌まるかを
build123d の Joint で宣言し、何が**動く**か・何が**入る**かも宣言する。

```python
from build123d import *
from hwkit import *

P = load_profile()

def bracket() -> Part:
    with BuildPart() as p:
        Box(40, 30, 5, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations(Plane.XY.offset(5)):          # 天面から掘る
            with Locations((-14, 0), (14, 0)):
                CounterBore(M3, depth=5, profile=P)  # ネジ頭は面一（flush）に沈む
    RigidJoint("foot", p.part, Location((0, 0, 0)))
    return p.part

asm = Assembly("gizmo", P)
b = asm.add("base", base(), support="none", note="インサートは上面から")
r = asm.add("bracket", bracket(), print_orientation=Rotation(0, 0, 0))
asm.mate(b.joints["top"], r.joints["foot"])
asm.must_move("roller", "bracket", 0.5)              # 検証器が強制する宣言
asm.goes_in("lid", "box", direction=(0, 0, 1),       # 同上
            clearance=P.gap("slide"))
asm.buy("M3 x 12 六角穴付きボルト", 4, "ブラケット固定用")
asm.step("ベースに M3 インサートを4個圧入。冷めるまで触らない。")
```

座標系は2つあり、混同しやすい。`add()` が**設計座標系**のスナップショットを取り、印刷性の
検査と STL 出力はそちらで行う。`mate()` は部品を**組立座標系**へ動かし、干渉とすきま
（clearance）はそちらで見る。Joint が部品を回した後でも `print_orientation` が意味を持つのは、この分離が
あるから。

### 3. 出力前の検証

```python
for r in asm.validate():
    print(r)
```

エラーは出力を止める。警告は、理解したうえで受け入れるかどうかの判断材料。

| チェック | 捕まえるもの | 深刻度 |
|---|---|---|
| `manifold` | 壊れた形状。1部品のはずが実は2つの離れた塊 | エラー |
| `bounds` | 造形範囲（build volume）に収まらない | エラー |
| `wall` | 薄い壁。**穴と縁のあいだに残る薄肉**も | ノズル径2倍未満でエラー |
| `hole` | 印刷で潰れる小径穴 | 警告 |
| `overhang` | サポート必要角を超える下向き面。水平天井はブリッジ扱い | 警告 |
| `interference` | 部品どうしの重なり。組立が物理的に不可能 | エラー |
| `insertion` | 定位置まで**到達できない**、または入れるすきまが無い | エラー |
| `clearance` | 動くべき部品に、動くすきまが無い | エラー |

**干渉チェックだけでは足りない。ここが罠。** 干渉が見るのは「重なっているか」だけ。空洞と
ぴったり同寸のフタは重なりゼロ。干渉チェックは通る。そして入らない。65.00mm で
モデリングしたフタは造形板（build plate）から 65.15mm で出てくる。**入るとは、重なって
いないことではなく、動かしてもまだ触れないこと。**

だから、どこかへ**入れる**もの — フタ、ベアリング、ポケットに落とすナット、スタンドオフ
（standoff）のあいだの基板 — には宣言を付ける。

```python
asm.goes_in("lid", "box", direction=(0, 0, 1), clearance=P.gap("slide"))
```

部品を挿入経路に沿って引き出しながら、各位置で2つを確認する。**ぶつからないか**（最終位置
には収まるのに途中で引っかかるもの。リップの奥のベアリングなど。最終位置の干渉チェックには
原理的に見えない）。**clearance ぶん横にずらしても触れないか**（すきまゼロの嵌め合い。
干渉チェックには表現できない）。

警告は軽視しない。参照設計では、座ぐり（counterbore）がフィレットに食い込んでできた
1mm² のひさしをオーバーハングチェックが4箇所検出した。レンダリングでは見えず、放置すれば
合わせ面にサポート痕が残るところだった。

### 4. 出力

`asm.export()` の出力物。部品ごとに**印刷姿勢へ回して Z=0 に置いた** STL（スライサーで
回転させないこと）、組立位置のままの STEP、`BOM.md`、`ASSEMBLY.md`。

エラーが残る設計は出力しない。実装の型は `examples/parts_box.py`。

## 原則

**モデリングしていない部品の周りを設計しない。** 推測でモデリングもしない — 訊く。
手順0を飛ばした代償が最大。間違った寸法の周りを削ったブラケットは、手に取るまで
完璧に見える。

**印刷ねじ山を作らない。** 第一候補は `InsertBoss`（熱圧入。強く、再利用可）、次が
`NutPocket`（ナット捕捉。追加費用ゼロ）。素穴へのタッピングは軽負荷かつ組立1回まで。

**すきまを数値で直接書かない。** `P.hole(3.0, "free")`、`P.bore(10.0, "press")`、
`P.peg(6.0, "snug")`、`P.gap("slide")`。較正し直せば全設計の全嵌合が追随する。ソース中の
`3.4` は追随しない。

**姿勢は強度で決める。表面品質は二の次。** 層は積層方向を横切る引張で剥がれる。曲げを
受けるブラケットでは、層が荷重方向に沿って走る向きに。姿勢を選ぶ本当の理由はたいてい
こちらで、サポートの都合ではない。

**付け根にフィレット。** リブや立ち壁が板に取り付く隅が、印刷部品の折れる場所。層が
引き剥がされる方向に力を受けるため。

**買う部品もモデリングする。** ベアリング、軸、モーターは `asm.bought()` で登録。出力は
されないが、干渉チェックは**モデリングされたものしか見えない**。実際にぶつかるのは、
たいてい買った部品のほう。

**サポートは設計で消す。** オーバーハング下の面取り、丸穴の代わりのティアドロップ
（teardrop）、2分割してネジ留め。合わせ面にサポートを生やすより、どれも良い。

## ファイル案内

- `hwkit/components.py` — **最初に読む。** `Component` `Vol` `Mount` `MountHoles`、データム
  規約、測定チェックリスト、未検証部品を止めるゲート。
- `hwkit/profile.py` — `PrinterProfile` と嵌合の等級。
- `hwkit/fasteners.py` — `ClearanceHole` `CounterBore` `CounterSink` `InsertBoss`
  `NutPocket`、M2〜M6 の寸法表。
- `hwkit/parts.py` — `BearingPocket` `ShaftBore`、ベアリングと軸の寸法表。
- `hwkit/validate.py` — 各チェックの実装と、その書き方になっている理由。
- `hwkit/assembly.py` — `Assembly`、2つの座標系、部品表と出力。
- `examples/parts_box.py` — 最小の完結した設計。「フタは入るのか」。最初に写す手本。
- `examples/motor_mount.py` — 買った部品の周りを削る設計。
- `examples/roller_bracket.py` — 圧入、ベアリング、回転部のすきま。
- `references/components.md` — 部品の測り方と、ユーザーへの訊き方。
- `references/design-rules.md` — 設計則の数値と、その根拠。
- `references/build123d-api.md` — **build123d のコードを書く前に読む。** 1件につき約1時間を
  節約する落とし穴の一覧。
