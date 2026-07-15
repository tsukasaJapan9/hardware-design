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

## カタログ

一度調べた部品は `hwlib/catalog.py` に登録し、次回以降の調査を省く。
登録時も出典 URL は必須。裏が取れない項目は登録しない。
