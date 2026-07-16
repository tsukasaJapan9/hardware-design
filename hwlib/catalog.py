"""調査済み部品の寸法。

一度調べた部品をここに蓄積し、次回以降の調査を省く。

登録のルール:
  - 値は必ず一次情報源（メーカーの機械図面・データシート）で裏を取り、source に URL を書く
  - 裏が取れない項目は「書かない」。推測値を入れると、それが正しい値として使われてしまう
  - 実測した値は confidence="measured" とし、どの個体を測ったか note に残す
"""

from __future__ import annotations

from hwlib.bom import Component, Connector

CATALOG: dict[str, Component] = {
    "raspberry_pi_zero_2w": Component(
        id="raspberry_pi_zero_2w",
        name="Raspberry Pi Zero 2 W",
        category="board",
        # 公式機械図面より: 基板 65 x 30 mm。高さは基板厚 1.0 + 実装部品・コネクタの高さ
        size=(65.0, 30.0, 5.0),
        # 四隅から 3.5 mm。ピッチ 58 x 23 mm
        mount_holes=[(3.5, 3.5), (61.5, 3.5), (3.5, 26.5), (61.5, 26.5)],
        hole_dia=2.75,
        connectors=[
            # 図面の 41.4 / 54 mm はコネクタ中心の基板左端からの距離
            Connector(name="micro_usb_power", pos=(54.0, 0.0, 2.5), size=(8.0, 3.0), face="-y"),
            Connector(name="mini_hdmi", pos=(41.4, 0.0, 2.5), size=(11.0, 4.0), face="-y"),
        ],
        clearance=2.0,
        confidence="datasheet",
        source="https://datasheets.raspberrypi.com/rpizero2/raspberry-pi-zero-2-w-mechanical-drawing.pdf",
        note="高さ 5.0 mm は実装部品込みの概算。ケース設計で余裕がない場合は実測すること",
    ),
    "pi_camera_v2": Component(
        id="pi_camera_v2",
        name="Raspberry Pi Camera Module v2",
        category="sensor",
        # 基板 25 x 24 mm、レンズ突起を含む高さ 9 mm
        size=(25.0, 24.0, 9.0),
        # 取付穴のピッチは一次情報源で確認できなかったため登録しない。
        # ネジ止めする設計にするなら、実測してから mount_holes を追加すること。
        mount_holes=[],
        hole_dia=0.0,
        clearance=1.0,
        confidence="datasheet",
        source="https://www.raspberrypi.com/documentation/accessories/camera.html",
        note=(
            "外形と厚みのみ確認済み。取付穴の位置は未確認（M2 ネジが入るとの記述のみ）。"
            "ネジ止めする場合はノギスで実測すること"
        ),
    ),
    "dynamixel_xl330": Component(
        id="dynamixel_xl330",
        name="ROBOTIS DYNAMIXEL XL330-M077-T / M288-T",
        category="actuator",
        # 公式スペックのケース外形。M077 と M288 は同一ケース
        size=(20.0, 34.0, 26.0),  # W x H x D（e-manual の Specifications）
        # ケース側面・背面の M2 セルフタッピング穴。出力ホーンの M2 パターンとは別。
        # 穴座標は公式図面を正とするため、ここには登録しない（本表の外形値のみで設計しない）
        mount_holes=[],
        hole_dia=2.0,
        clearance=1.0,
        confidence="datasheet",
        source="https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/",
        note=(
            "M077(車輪)・M288(股膝)共通ケース、18g/個。公式図面 X330 より: "
            "出力軸は W方向中央・H方向は上端から 9.5mm（箱中央ではない）。"
            "ホーン穴 = 4xφ1.6・P.C.D φ12・M2タッピング。"
            "実形状モデルは hwlib.parts.xl330 を使う（箱近似ではなく軸原点で扱う）"
        ),
    ),
    "tamiya_narrow_tire_70145": Component(
        id="tamiya_narrow_tire_70145",
        name="タミヤ No.145 ナロータイヤセット (Item 70145)",
        category="wiring",  # 車輪。カテゴリは設計側の BOM で上書きする想定
        # 組立説明図の寸法図より: タイヤ外径 58 x 幅 16 mm
        size=(58.0, 58.0, 16.0),
        # ホイールはハブを 3x8mm タッピングビス3本で三角形に留める。
        # 3点 PCD・中央ボア径は数値が図に無く、実測が必要なため登録しない
        mount_holes=[],
        hole_dia=0.0,
        clearance=1.0,
        confidence="datasheet",
        source="https://www.tamiya.com/japan/products/70145/index.html",
        note=(
            "ソリッドゴムタイヤ+樹脂ホイール2本組、~15g/輪(要実測)。"
            "リム部 42mm、中央部まわり 10mm。ハブB1(六角軸/圧入)・B2(丸軸/3mmナット)付属。"
            "3点留めビス穴の PCD と中央ボア径は図に数値が無いため実測すること"
        ),
    ),
}


def get(name: str) -> Component:
    """カタログから部品を取り出す。"""
    if name not in CATALOG:
        raise KeyError(
            f"'{name}' はカタログにありません。型番から寸法を調査して CATALOG に追加するか、"
            "bom.yaml に直接寸法を書いてください"
        )
    return CATALOG[name]
