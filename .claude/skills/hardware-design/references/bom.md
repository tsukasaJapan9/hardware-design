# 部品表（BOM）

## 部品カテゴリ

`hwlib.bom.CATEGORIES` の全カテゴリについて、**部品を挙げるか、不要な理由を `excluded` に書く。**
どちらも無いと `load_bom()` がエラーになり、設計に進めない。洗い出し漏れを防ぐための仕組み。

| カテゴリ | 内容 |
|---|---|
| `board` | 電子基板（メイン基板、電源基板、変換基板） |
| `sensor` | センサ（カメラ、マイク、距離センサ、IMU） |
| `actuator` | アクチュエータ（モータ、サーボ、駆動基板） |
| `power` | 電源（バッテリー、充電回路、電源スイッチ、DC ジャック） |
| `wiring` | 配線（ハーネス、USB ケーブル、コネクタの挿抜空間） |
| `display_ui` | 表示・操作（ディスプレイ、LED、ボタン） |
| `fastener` | 締結（ネジ、スペーサ、ゴム足） |
| `thermal` | 放熱・通気（ヒートシンク、通気口） |

見落としやすいもの: **配線の取り回し空間、コネクタを挿し抜くための空間、ネジそのもの、ゴム足。**

## 寸法調査の手順

1. 型番を確認する。分からなければユーザに聞く
2. `WebSearch` / `WebFetch` でメーカーの機械図面（mechanical drawing）を探す。
   製品ページの「寸法」欄より、機械図面 PDF のほうが正確
3. 幅・奥行き・高さに加え、**取付穴の位置（部品原点からの座標）と穴径**を取る
4. 出典 URL を `source` に書く
5. **確認できなかった項目は書かない。** 推測値を入れると、それが正しい値として使われる

### 図面・データシートは保存する

入手した公式図面・データシートは **`datasheets/<部品名>/` に保存し、`datasheets/README.md` に
「出典 URL・取得日・その図面から読み取れる寸法」を追記する。**

URL はリンク切れするため、現物が無いと後から寸法の根拠を検証できなくなる。
部品モデル（`hwlib/parts/*.py`）の docstring からも、このローカルパスを参照させる。

なお公式 CAD/図面のサイトには、実行環境から到達できないものがある
（例: robotis.com）。その場合はユーザーにブラウザでの取得を依頼する。

### ネットで確定できない場合

推測せず、**ユーザにノギスでの実測を依頼する。** 測る場所を具体的に示す。

> 「カメラモジュールの取付穴の位置が公式資料で確認できませんでした。次を測ってもらえますか。
> (1) 基板の外形 X × Y、(2) 左下の穴の中心から基板の左端・下端までの距離、
> (3) 穴の中心間ピッチ（横・縦）、(4) 穴の直径」

受け取った値は `confidence: measured` とし、いつ何を測ったかを `note` に残す。

## bom.yaml の書式

```yaml
project: my_case

components:
  - id: pi_zero                    # コード内で参照する識別子
    name: Raspberry Pi Zero 2 W
    category: board
    size: [65.0, 30.0, 5.0]        # 幅 X, 奥行き Y, 高さ Z (mm)
    mount_holes:                    # 部品原点（最小コーナー）からの穴中心
      [[3.5, 3.5], [61.5, 3.5], [3.5, 26.5], [61.5, 26.5]]
    hole_dia: 2.75
    connectors:                     # 外装に開口が必要なもの
      - name: micro_usb_power
        pos: [54.0, 0.0, 2.5]       # 部品ローカル座標でのコネクタ中心
        size: [8.0, 3.0]            # 開口の幅・高さ
        face: "-y"                  # 外向き方向
        depth: 15.0                 # ケーブル挿抜に必要な外側の空間
    clearance: 2.0                  # 周囲に確保する余裕
    retention: M2.6 タッピングネジ x4  # 何で固定するか（必須）
    confidence: datasheet           # datasheet | measured | user_provided
    source: https://...             # datasheet なら必須
    note: 高さ 5.0 は実装部品込みの概算

  - id: screws_lid
    name: タッピングネジ M3 x 10（4 本）
    category: fastener
    size: [3.0, 3.0, 10.0]
    confidence: user_provided
    geometric: false                # CAD に配置しない部品（ネジ、ケーブル本体）
    note: 樹脂直締め

excluded:                            # 不要と判断したカテゴリと、その理由
  actuator: 可動部を持たない
  display_ui: 表示・操作系はなし
  thermal: 発熱が小さく通気口は設けない
```

### 必須項目

- `size` — 3 つとも正の値。1 つでも欠けると設計に進めない
- `confidence` — `datasheet` / `measured` / `user_provided` / `provisional` のいずれか
- `source` — `confidence: datasheet` のときは必須

### provisional（暫定値）

実物がまだ手元になく、寸法を実測できないが、骨格設計を先に進めたい場合に使う。
`confidence: provisional` の部品は設計を止めないが、読み込み時に警告が出る。

モデル側の暫定パラメータ（嵌合の PCD など、BOM の部品ではない寸法）は、
モデルの `PROVISIONAL` 辞書に `{パラメータ名: 測り方}` で列挙する。

**印刷・発注の前に必ず `verify.assert_no_provisional(bom=..., dims=PROVISIONAL)` を通す。**
暫定値が残っていれば、何をどう測るべきかを列挙して失敗する。これが確定を強制する仕組み。
- `retention` — `geometric: true`（既定）の部品は必須。**収まっていても固定されていなければ組み立てられない**

### `geometric: false`

部品表には必要だが、形状として配置しないもの（ネジ、ケーブル本体）。
`assert_all_parts_placed()` の対象外になる。
ただし**配線が占める空間を確保したい場合は `geometric: true` にして体積を持たせる。**

## 部品寸法のカタログ（`hwlib/catalog.py`）

一度調べた部品は `hwlib/catalog.py` に登録し、次回以降の調査を省く。
登録時も出典 URL は必須。裏が取れない項目は登録しない。

## BOM カタログ（HTML）

`projects/*/bom.yaml` の全部品を、三面図（第三角法）と仕様の一覧にした HTML。
部品を型番・寸法・固定方法・出典まで含めて一度に見るためのもの。

```bash
uv run python -m hwlib.bom_catalog                 # out/bom_catalog.html
uv run python -m hwlib.bom_catalog --fragment      # <style> と <main> だけ（Artifact 用）
```

### ルール: BOM を作った・変えたら作り直す

**`bom.yaml` を新規に作ったとき、部品を足したとき、寸法・出典・retention を変えたときは、
カタログを生成し直し、図を目で確認する。** HTML は Read では絵にならないので、
ヘッドレスブラウザでスクリーンショットにしてから Read する。

```bash
google-chrome --headless --disable-gpu --hide-scrollbars \
  --window-size=1150,3000 --screenshot=<スクラッチ>/catalog.png out/bom_catalog.html
```

生成対象は `projects/*/bom.yaml` 全部なので、新しいプロジェクトは置くだけで載る。
一覧に手で追記する場所はない。載らない場合は `load_bom()` が通っていないということ
なので、まず `bom.yaml` の不備を直す。

`uv run pytest` の `tests/test_bom_catalog.py` が、全 BOM の全部品ぶんのカードが
生成されることを確認する。BOM を足してテストが落ちたら、その BOM に不備がある。

### 図の出所は 3 種類

| 種別 | 何を描くか | いつ |
|---|---|---|
| 実形状 | 実際の形（図面・実測に基づくソリッドの投影） | `hwlib/parts/` にモデルがあり、`REAL_SHAPES` に登録した部品 |
| 外形近似 | BOM の `size` の直方体。`mount_holes` があれば穴も開ける | 既定 |
| 略図 | 呼び径と首下長さのみ | `category: fastener` |

図は build123d の `project_to_viewport()` で実際のソリッドを投影して作る。手描きの
近似ではないので、図と CAD の形状はずれない。見える稜線は実線、隠れた稜線は破線。

**実形状モデルを持つ部品を BOM に入れたら `hwlib/bom_catalog.py` の `REAL_SHAPES` に
`(プロジェクト, 部品 id): (形状を返す関数, 出所の説明)` で登録する。**
登録しないと直方体近似のまま描かれる。実形状の外形が BOM の `size` と食い違う場合
（突起を含むなど）は、カタログが「図上の外形」として両方を出す。

### カタログが拾う不備

- **コネクタ開口が面に収まらない部品** — 面の指定と開口寸法の食い違い。図には枠を描かず
  位置だけ示し、仕様表に警告を出す
- **`confidence: provisional` の部品** — 冒頭に一覧で出る。印刷・発注の前に実測して確定する
