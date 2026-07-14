# 配置・干渉・組み立て可能性の検証

`hwlib.verify` の使い方。すべて失敗時に `AssertionError` を出し、何がどう違うかを数値で示す。

## 部品の配置

`bom.yaml` の各部品は `Component.mock()` で外形の直方体になる。
部品ローカル座標の原点は最小コーナー。配置は `Pos(x, y, z) * mock` で行う。

```python
BOM = load_bom("bom.yaml")
components = {
    "pi_zero": Pos(10, 12, 7) * BOM["pi_zero"].mock(),
    "camera":  Pos(30, 50, 11) * BOM["camera"].mock(),
}
```

配置座標は `Params` dataclass にまとめる。モデル本体に数値を直接書かない。

## 検証の一覧

### 部品が揃っているか

```python
verify.assert_all_parts_placed(BOM, components)
```

BOM にあるのに配置されていない部品、配置されているのに BOM に無い部品を検出する。
`geometric: false`（ネジ、ケーブル本体）は対象外。

### 収まっているか

```python
cavity = Box(inner_w, inner_d, inner_h, align=(Align.MIN,)*3)
for name, part in components.items():
    verify.assert_contained(part, cavity, name=name)
```

### 干渉していないか

```python
verify.assert_no_interference({"base": base, **components})
verify.assert_clearance(components["battery"], components["camera"], min_gap=2.0)
```

`assert_no_interference` は総当たりで重なりの体積を見る。
面が接しているだけ（重なり体積 0）は干渉としない。

意図的な接触があるペアは `allow={frozenset(("a", "b"))}` で除外する。

### ドライバーが届くか

```python
verify.assert_tool_access(
    (x, y, z),          # ネジ頭の位置
    (0, 0, 1),          # ドライバーを差し込む方向
    obstacles,          # 障害物（部品とケース）
    driver_dia=6.0,
)
```

ネジ頭から指定方向に円柱を伸ばし、障害物と干渉しないことを確認する。
**ここが通らない設計は組み立てられない。**

### 部品を入れられるか

```python
verify.assert_insertable("camera", components["camera"], (0, 0, 1), obstacles, distance=60)
```

部品を指定方向へ動かしたときの掃引体積を作り、経路上に障害物がないことを確認する。
収まっていても経路がふさがれていれば組み立てられない。

### 組み立て順序を反映する

**障害物は「その作業をする時点で存在するもの」だけを渡す。**

例: 基板のネジを締める時点では蓋はまだ無い。蓋を障害物に含めると、
実際には組み立てられる設計が不合格になる。

```python
# 部品を入れる → 基板を留める → 蓋を閉じて留める
obstacles = {"base": base, **components}   # 蓋は含めない
```

逆に、蓋を閉じた後にしか締められないネジがあるなら、蓋を含めて確認する。

### コネクタの開口

```python
verify.assert_connector_access(
    (x, y, z),      # コネクタ中心（アセンブリ座標）
    "-y",           # 外向き方向
    (8.0, 3.0),     # 開口の幅・高さ
    base,
    depth=15.0,     # ケーブル挿抜に必要な外側の空間
)
```

コネクタ位置から外向きに角柱を伸ばし、外装と干渉しなければ開口がある。
角柱は外装の外まで届く長さに自動調整されるため、コネクタが壁から離れていても見逃さない。

### タッピングネジの寸法

```python
verify.assert_boss_screw_fit(
    screw_dia=3.0, pilot_dia=2.4, boss_outer_dia=6.6,
    boss_depth=8.0, screw_len=10.0, plate_thickness=2.5,
)
```

下穴径・ボス肉厚・ねじ込み深さ・ネジ長の整合を確認する。
`hwlib.features.SCREWS` の値を使えば自動的に整合する。

## 固定されているか

**干渉チェックは「箱の中で部品が浮いている」状態を素通りさせる。**
収まっていることと固定されていることは別物。

すべての部品について `bom.yaml` の `retention` に固定方法を書く（未記入はエラー）。
固定のために形状が必要なら、台座・リブ・ボスを外装に作る。

例: カメラを底に置くだけではレンズが蓋から遠ざかり、固定もされない。
台座で持ち上げ、リブで横方向を拘束し、蓋で上から押さえる
（`projects/example_camera_case/model.py` の `camera_mount()`）。

## 3D プリント

```python
verify.assert_watertight(part)              # 必須。水密でなければスライスできない
verify.check_min_wall(part, 1.2)            # 警告のリストを返す
verify.check_overhang(part, max_angle=45)   # 警告のリストを返す
```

`check_*` は警告を返すだけで例外を出さない。OCCT のオフセット処理は失敗しやすく、
これ単独で設計 NG と判定できないため。
