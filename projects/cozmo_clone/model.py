"""Cozmo クローン — 胴体・頭部・リフトアームの骨格設計。

4 自由度（車輪 L/R・リフトアーム・ヘッドチルト）をすべて DYNAMIXEL XL330 で構成し、
車輪はタミヤ 70145（58mm）を pen_robo_wheel_hub の変換ハブで結合する。

座標系: 胴体の内寸の「左・前・床」を原点 (0, 0, 0) とする。
  +X = 右、+Y = 後方、+Z = 上
  したがって Y=0 が前面の内壁、Y=inner_d が背面の内壁。

XL330 の向きの約束:
  BOM のモックは (W20, H34, D26) の直方体。これを Rot(0, 90, 0) で寝かせて使うため、
  配置後の外形は (X, Y, Z) = (D26, H34, W20) になる。
  出力軸は D 方向（＝配置後の X）に平行で、
    Y 方向: ケースの H 上端から 9.5 mm（図面 datum）。H 上端を「前」に向けるので axis_y = y0 + 9.5
    Z 方向: W の中央なので axis_z = z0 + CASE_W / 2
  この 9.5 mm は箱の中央ではない。hwlib.parts.xl330 の AXIS_FROM_TOP と同じ値を使う。

搭載物の階層（Z）:
  0〜30    車輪サーボ・NiMH パック・崖センサ・カメラ
  30〜50   リフトサーボ・ヘッドチルトサーボ・サーボ I/F 基板・AtomS3R・DC-DC・コンデンサ・電源スイッチ
  50〜52.5 天板
  56〜     頭部（天板の上でチルトする）

車輪サーボとリフトサーボ、車輪サーボとヘッドチルトサーボは Y 範囲を共有し、Z 階層で分ける。
これにより胴体長を 115 mm に抑えている（直列に並べると 150 mm を超える）。

**カメラは頭部ではなく胴体前面上部に置く。** 頭部に Unit OLED（高さ 30）と
Unit CamS3（高さ 24）を縦に重ねると頭部内寸に 54 mm 必要で、全高が 125 mm に達して
胴体長 115 mm に対して不自然に背高になる。胴体前面に移すと全高 103 mm に収まり、
かつ頭部チルトで映像が揺れない。brief.md の「カメラ窓: 頭部前面」からの逸脱。

胴体の外側に出る部品（車輪・ハブ・リフトアーム・頭部・キャスタ・首の配線・OLED）は
内部空間の収まり検査（assert_contained）の対象外として扱う。

暫定寸法（provisional）は BOM 側と PROVISIONAL に列挙。印刷前に
verify.assert_no_provisional で確定を強制する。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from build123d import Align, Axis, Box, Cone, Cylinder, Part, Pos, Rot, fillet

from hwlib.bom import load_bom
from hwlib.features import SCREWS, clearance_hole, rect_opening, tapping_boss
from hwlib.parts.xl330 import AXIS_FROM_TOP, CASE_D, CASE_W

HERE = Path(__file__).parent
BOM_PATH = HERE / "bom.yaml"
OUT = HERE / "out"

# 実測が未確定で、BOM の size 以外にモデルが依存している暫定寸法。
# {パラメータ名: 測り方}。印刷前に必ず実測して Params を更新し、ここから消す。
# 残っている限り verify.assert_no_provisional が失敗する。
PROVISIONAL: dict[str, str] = {
    "oled_window_w": (
        "Unit OLED のガラス面の有効表示エリアの幅。"
        "モジュール外形ではなく、実際に光る領域を測る"
    ),
    "oled_window_h": "Unit OLED の有効表示エリアの高さ",
    "oled_window_offset_z": (
        "Unit OLED のモジュール下端から有効表示エリアの中心までの高さ。"
        "現状はモジュール高さの中央（15.0）と仮定している"
    ),
    "cam_lens_offset_z": (
        "Unit CamS3 のモジュール下端からレンズ中心までの高さ。"
        "現状はモジュール高さの中央付近（12.0）と仮定している"
    ),
}

# 胴体の内部空間に収まる必要がない部品（外に出る、または壁・天板を貫く）
OUTSIDE_INTERIOR = {
    "wheel_l", "wheel_r", "caster_rear", "neck_harness", "unit_oled",
}


@dataclass(frozen=True)
class Params:
    """設計パラメータ。数値はすべてここに集約し、モデル本体に直接書かない。"""

    # --- 胴体の内寸（部品の配置から決まる） ---
    inner_w: float = 60.0    # X。車輪サーボ 2 個（各 D26）が左右の壁に張り付いて入る幅
    inner_d: float = 126.0   # Y
    inner_h: float = 54.0    # Z。2 階層に収める高さ

    wall: float = 2.5
    floor: float = 2.5
    top_plate: float = 2.5

    # --- 締結 ---
    shell_screw: str = "M2.6"
    shell_screw_len: float = 8.0
    shell_boss_depth: float = 6.0
    shell_boss_inset: float = 6.0   # 内寸の角からボス中心までの距離
    # 天板ボスは床から立てず、壁に融合させて上部だけに設ける。
    # 床から立てると NiMH パックとサーボが内寸をほぼ埋めているため必ず干渉する。
    shell_boss_base_z: float = 32.0
    # 天板は前部プレートと、NiMH パックの上を覆うスナップフィット蓋に分ける。
    # パックは幅 57 mm で内寸 60 mm をほぼ埋めるため、その上にネジボスを立てると
    # パックを真上に抜けなくなる（＝交換できない）。蓋はタブで留めてネジを使わない。
    plate_split_y: float = 76.0
    tab_w: float = 1.6              # スナップタブの脚の厚み
    tab_len: float = 14.0           # 同 長さ（Y 方向）
    tab_h: float = 6.0              # 同 高さ
    tab_bump: float = 1.2           # 側壁のポケットに食い込む量
    board_screw: str = "M2"
    board_screw_len: float = 6.0
    board_boss_h: float = 6.0       # 基板の下に確保する高さ（配線・端子の逃げ）
    # M2x6 が基板厚 1.6 を通ると 4.4 mm ねじ込まれる。下穴はそれ以上の深さが必要
    board_boss_depth: float = 5.0

    # --- 車輪 ---
    # 出力軸の位置。axis_z が接地高さを決める（接地 Z = axis_z - タイヤ半径）
    wheel_axis_y: float = 48.0
    wheel_axis_z: float = 20.0
    hub_thickness: float = 8.0       # pen_robo_wheel_hub の body_thickness
    hub_od: float = 36.0             # 同 adapter_od（リム外径 42 - マージン 6）
    wheel_opening_margin: float = 2.0  # 側壁のハブ通し穴の、ハブ外径に対する片側余裕

    # --- リフトアーム / ヘッドチルト（胴体前部、左右に振り分ける） ---
    # 車輪サーボの前に並べる。同軸（左=リフト、右=チルト）にして胴体長を節約する。
    front_servo_y: float = 2.0       # 前部サーボ外形の最小 Y
    front_servo_z: float = 8.0       # 同 最小 Z（崖センサの上に載せる）
    arm_length: float = 34.0         # 軸中心からフォーク先端まで
    arm_thickness: float = 4.0       # アームの板厚（X 方向）
    arm_width: float = 10.0          # アームの幅
    # 先端のフォーク。実物は前方に張り出す大きな C 字のグリッパ
    fork_h: float = 24.0             # フォークの縦板の高さ
    fork_tongue: float = 12.0        # 前方へ出す舌の長さ
    # 回転の符号: X 軸まわりの正回転で「前端が下がる」。俯き = 正、仰ぎ = 負。
    # 中立姿勢の俯角。フォーク先端が接地面のすぐ上（数 mm）に来る角度にする。
    # 大きくしすぎると先端が接地面より下に潜り、机を叩く。
    arm_angle_deg: float = 6.0

    # チルトブラケットは胴体外壁とタイヤ内側面の隙間（62.5〜68 mm）を立ち上がる。
    # 板厚と隙間はこの 5.5 mm に収まるよう決める。タイヤ側に 1.5 mm 残す。
    bracket_t: float = 3.0           # チルトブラケットの板厚
    bracket_gap: float = 1.0         # ブラケット立ち上がり部と胴体外壁の隙間

    # --- 頭部シェル ---
    # 実物 Cozmo の頭部は機体の 4〜5 割を占める大きな塊で、前面のほぼ全面が顔。
    # 小さな箱を胴体の上に載せると「カメラを載せた台車」に見えてしまう。
    head_w: float = 54.0
    head_d: float = 44.0
    head_h: float = 46.0
    head_wall: float = 2.5
    head_offset_y: float = -34.0     # チルト軸から見た頭部の最小 Y
    # 46.0 でチルト両端の天板干渉がぎりぎり消える。印刷公差ぶん 2 mm 余裕を持たせる
    head_offset_z: float = 48.0      # チルト軸から見た頭部の最小 Z（天板より上に出す）
    # ヘッドチルトの可動域（度）。俯き = 正、仰ぎ = 負（arm_angle_deg と同じ規約）。
    # 実物 Cozmo 相当の 俯角 20 度 / 仰角 25 度。
    head_tilt_min_deg: float = -25.0
    # 俯角の上限は「頭部がカメラの視界に入らない角度」で決まる。+14 度から写り込む。
    # カメラが胴体固定であることの代償。実物 Cozmo の俯角（約 22 度）より浅い。
    head_tilt_max_deg: float = 12.0

    # 顔の窓（Unit OLED の有効表示エリア）。**暫定値**
    oled_window_w: float = 29.0
    oled_window_h: float = 15.0
    oled_window_offset_z: float = 15.0   # OLED モジュール下端から窓中心まで
    # カメラのレンズ穴。**暫定値**
    cam_lens_dia: float = 9.0
    cam_lens_offset_z: float = 12.0      # カメラモジュール下端からレンズ中心まで
    cam_dfov_deg: float = 66.5           # Unit CamS3 の対角視野角
    cam_view_len: float = 150.0          # 視界の検査に使う距離

    # --- 部品の配置（配置後のバウンディングボックス最小コーナー） ---
    # 前部（Y 2〜38）: 崖センサ・前部サーボ・カメラ
    cliff_l_pos: tuple[float, float, float] = (8.0, 16.0, 0.0)
    cliff_r_pos: tuple[float, float, float] = (40.0, 16.0, 0.0)
    camera_pos: tuple[float, float, float] = (10.0, 2.0, 28.0)
    neck_harness_pos: tuple[float, float, float] = (20.0, 14.0, 30.0)
    # 後部下段（Y 74〜124）: NiMH パックとキャスタ
    battery_pos: tuple[float, float, float] = (1.5, 74.0, 6.0)
    caster_pos: tuple[float, float, float] = (20.0, 88.0, -9.0)
    # 上段（Z 32〜54）。取付ボスが車輪サーボ（Z 10〜30）に当たらない高さに置く。
    # 天板ボス（Y=70 付近）とは Y を離し、ドライバーが互いに干渉しないようにする。
    # サーボ I/F 基板は車輪サーボの上に置く。NiMH パックの上に置くと、その取付ボスが
    # パックの真上に立ってしまい、パックを抜けなくなる（＝交換できない）。
    if_board_pos: tuple[float, float, float] = (5.0, 45.0, 36.0)
    bulk_cap_pos: tuple[float, float, float] = (12.0, 70.0, 32.0)
    power_switch_pos: tuple[float, float, float] = (0.0, 82.0, 32.0)
    atoms3r_pos: tuple[float, float, float] = (28.0, 100.0, 32.0)
    dcdc_pos: tuple[float, float, float] = (0.0, 104.0, 32.0)

    # --- 外観（Cozmo に寄せる造形） ---
    # 実物 Cozmo は角が大きく丸められ、車輪部は履帯ハウジングで覆われている。
    # 内部空間は直方体のまま残し、外殻だけを丸めるので搭載物の収まりには影響しない。
    body_fillet: float = 6.0         # 胴体の縦稜のフィレット半径
    head_fillet: float = 7.0         # 頭部の稜のフィレット半径
    # 車輪の上を覆うフェンダー（履帯ハウジングに見せる）
    fender_gap: float = 1.0          # タイヤ外周との隙間
    fender_t: float = 2.5            # フェンダーの肉厚
    # フェンダーの前端。チルトブラケットの掃引（チルト -25〜+20 度で Y=34 付近まで来る）を
    # 避ける位置。34 で干渉が消え、印刷公差ぶん 4 mm 余裕を見て 38 にしている。
    fender_y_min: float = 38.0
    # 背面上部の張り出し（実物の「バックパック」に相当）
    hump_w: float = 34.0
    hump_d: float = 30.0
    hump_h: float = 8.0
    hump_fillet: float = 3.0
    # 顔のパネル（黒い面）。この中に OLED の窓を開ける
    # 実物は頭部前面の 8 割ほどを黒いパネルが占める
    face_panel_w: float = 46.0
    face_panel_h: float = 34.0
    face_panel_depth: float = 1.2    # 掘り込みの深さ（head_wall を貫かないこと）
    face_panel_fillet: float = 8.0
    # 頭部から前方に垂らす「あご」。天板との隙間（13 mm）を隠して頭部を大きく見せる造形。
    # **現状は 0（無効）。** 干渉だけなら 10 mm まで許容できるが、カメラが胴体固定のため
    # あごを付けるほど俯いたときの視界を塞ぐ（camera_view_cone のテストで検出）。
    # カメラを頭部に移せる寸法が判明したら、その時点で有効化を検討する。
    chin_h: float = 0.0

    driver_dia: float = 6.0          # 組み立てに使うドライバーの軸径

    # ---- 導出値 ----
    @property
    def tire_radius(self) -> float:
        return 29.0   # タミヤ 70145 の外径 58 / 2

    @property
    def ground_z(self) -> float:
        """接地面の Z。"""
        return self.wheel_axis_z - self.tire_radius

    @property
    def wheel_servo_y(self) -> float:
        """車輪サーボ外形の最小 Y。軸が H 上端から 9.5 mm の位置に来るように置く。"""
        return self.wheel_axis_y - AXIS_FROM_TOP

    @property
    def wheel_servo_z(self) -> float:
        """車輪サーボ外形の最小 Z。軸が W の中央に来るように置く。"""
        return self.wheel_axis_z - CASE_W / 2

    @property
    def front_axis(self) -> tuple[float, float]:
        """前部サーボ（リフト・チルト）の回転軸 (y, z)。左右で共通。"""
        return (self.front_servo_y + AXIS_FROM_TOP, self.front_servo_z + CASE_W / 2)

    @property
    def head_origin(self) -> tuple[float, float, float]:
        """頭部シェルの最小コーナー（胴体座標）。"""
        ay, az = self.front_axis
        return (
            (self.inner_w - self.head_w) / 2,
            ay + self.head_offset_y,
            az + self.head_offset_z,
        )

    @property
    def plate_top(self) -> float:
        return self.inner_h + self.top_plate


P = Params()
BOM = load_bom(BOM_PATH)

# XL330 を寝かせる回転。配置後の外形は (D, H, W)
SERVO_ROT = (0.0, 90.0, 0.0)
# 表示面／レンズ面が +Z にある部品を、前（-Y）に向ける回転
FACE_FORWARD_ROT = (90.0, 0.0, 0.0)


# --------------------------------------------------------------------------
# 配置のヘルパー
# --------------------------------------------------------------------------
def _place(
    cid: str,
    pos: tuple[float, float, float],
    *,
    rot: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Part:
    """BOM のモックを回転させ、回転後のバウンディングボックス最小コーナーを pos に合わせる。

    回転してから最小コーナーで位置を決めるため、回転による原点のずれを気にしなくてよい。
    """
    m = Rot(*rot) * BOM[cid].mock()
    bb = m.bounding_box()
    return Pos(pos[0] - bb.min.X, pos[1] - bb.min.Y, pos[2] - bb.min.Z) * m


def _cut(part: Part, tool: Part, name: str, *, min_removed: float = 0.1) -> Part:
    """減算し、実際に効いたことを確認する。

    build123d のブール減算は対象に当たらなくても例外を出さない。体積も面数も変わらない
    まま「成功」するため、穴あけが効かない設計ミスが検出されずに通ってしまう。
    ここで毎回体積の減少を確認する。
    """
    from hwlib.verify import assert_cut

    after = part - tool
    assert_cut(part, after, name=name, min_removed=min_removed)
    return after


def _rotate_about(part: Part, angle_deg: float, pivot_y: float, pivot_z: float) -> Part:
    """YZ 平面内で (pivot_y, pivot_z) を中心に X 軸まわりに回す。"""
    return Pos(0, pivot_y, pivot_z) * Rot(angle_deg, 0, 0) * Pos(0, -pivot_y, -pivot_z) * part


def interior() -> Part:
    """胴体の内部空間。部品がここに収まっているかの確認に使う。"""
    return Box(P.inner_w, P.inner_d, P.inner_h, align=(Align.MIN, Align.MIN, Align.MIN))


def shell_boss_positions() -> list[tuple[float, float]]:
    """前部プレートを留めるボスの位置（内寸座標）。

    後方の 2 点は胴体後端ではなく、NiMH パックの手前（plate_split_y の前）に置く。
    パックの上にボスを立てるとパックが抜けなくなるため。
    """
    i = P.shell_boss_inset
    y_rear = P.plate_split_y - i
    return [
        (i, i),
        (P.inner_w - i, i),
        (i, y_rear),
        (P.inner_w - i, y_rear),
    ]


def hatch_tab_positions() -> list[tuple[float, float]]:
    """バッテリー蓋のスナップタブの位置 (x_inner_face, sign)。sign は食い込む向き。"""
    return [(0.0, -1.0), (P.inner_w, 1.0)]


def _hatch_tab_pockets() -> Part:
    """側壁に設けるスナップタブのポケット（切り欠く側）。"""
    y0 = (P.plate_split_y + P.inner_d) / 2 - P.tab_len / 2
    z0 = P.inner_h - P.tab_h
    cut = None
    for x_face, sign in hatch_tab_positions():
        x_min = x_face - P.wall - 0.5 if sign < 0 else x_face
        pocket = Pos(x_min, y0 - 0.5, z0 + 1.0) * Box(
            P.wall + 0.5, P.tab_len + 1.0, P.tab_h - 1.0,
            align=(Align.MIN, Align.MIN, Align.MIN),
        )
        cut = pocket if cut is None else cut + pocket
    return cut


def if_board_boss_positions() -> list[tuple[float, float]]:
    """サーボ I/F 基板を留めるボスの位置。基板外形図で確定した取付穴に合わせる。"""
    bx, by, _ = P.if_board_pos
    return [(bx + hx, by + hy) for hx, hy in BOM["servo_if_board"].mount_holes]


# --------------------------------------------------------------------------
# 部品の配置
# --------------------------------------------------------------------------
def servo_placements() -> dict[str, tuple[float, float, float]]:
    """XL330 4 軸の外形の最小コーナー。すべて寝かせて軸を X 方向に向ける。

    前部が左=リフト・右=チルト（同軸）、その後ろに左右の車輪サーボ。
    """
    right_x = P.inner_w - CASE_D
    return {
        "servo_lift": (0.0, P.front_servo_y, P.front_servo_z),
        "servo_head": (right_x, P.front_servo_y, P.front_servo_z),
        "servo_wheel_l": (0.0, P.wheel_servo_y, P.wheel_servo_z),
        "servo_wheel_r": (right_x, P.wheel_servo_y, P.wheel_servo_z),
    }


def head_components() -> dict[str, Part]:
    """頭部に載る部品（顔の OLED）。表示面を前（-Y）に向け、前面の内側に貼り付ける。"""
    hx, hy, hz = P.head_origin
    m = Rot(*FACE_FORWARD_ROT) * BOM["unit_oled"].mock()
    bb = m.bounding_box()
    x0 = hx + (P.head_w - bb.size.X) / 2
    y0 = hy + P.head_wall
    z0 = hz + (P.head_h - bb.size.Z) / 2      # 頭部内で高さ中央に置く
    return {"unit_oled": Pos(x0 - bb.min.X, y0 - bb.min.Y, z0 - bb.min.Z) * m}


def oled_module_bottom_z() -> float:
    """頭部内の OLED モジュール下端の Z。顔の窓の位置計算に使う。"""
    return head_components()["unit_oled"].bounding_box().min.Z


def place_components() -> dict[str, Part]:
    """BOM の geometric な部品をすべて配置する。"""
    parts: dict[str, Part] = {}

    for cid, pos in servo_placements().items():
        parts[cid] = _place(cid, pos, rot=SERVO_ROT)

    # 車輪（胴体の外側）。タイヤは軸を中心にした円柱で近似する
    ay, az = P.wheel_axis_y, P.wheel_axis_z
    for cid, sign, horn_x in (("wheel_l", -1.0, 0.0), ("wheel_r", 1.0, P.inner_w)):
        tire_width = BOM[cid].size[2]
        x_a = horn_x + sign * P.hub_thickness
        x_b = horn_x + sign * (P.hub_thickness + tire_width)
        parts[cid] = Pos(min(x_a, x_b), ay, az) * Rot(0, 90, 0) * Cylinder(
            P.tire_radius, tire_width, align=(Align.CENTER, Align.CENTER, Align.MIN)
        )

    for cid, pos in (
        ("battery_nimh", P.battery_pos),
        ("servo_if_board", P.if_board_pos),
        ("dcdc_5v", P.dcdc_pos),
        ("bulk_cap", P.bulk_cap_pos),
        ("cliff_sensor_fl", P.cliff_l_pos),
        ("cliff_sensor_fr", P.cliff_r_pos),
        ("neck_harness", P.neck_harness_pos),
        ("caster_rear", P.caster_pos),
    ):
        parts[cid] = _place(cid, pos)

    # AtomS3R は USB-C（BOM では -y 面）が胴体背面を向くよう 180 度回す
    parts["atoms3r"] = _place("atoms3r", P.atoms3r_pos, rot=(0.0, 0.0, 180.0))
    # 電源スイッチはレバーが左側面（-x）を向くよう 90 度回す
    parts["power_switch"] = _place("power_switch", P.power_switch_pos, rot=(0.0, 0.0, 90.0))
    # カメラは胴体前面に、レンズを前（-Y）に向けて置く
    parts["unit_cams3"] = _place("unit_cams3", P.camera_pos, rot=FACE_FORWARD_ROT)

    parts.update(head_components())
    return parts


# --------------------------------------------------------------------------
# 印刷する部品
# --------------------------------------------------------------------------
def _side_opening(wall_inner_x: float, y: float, z: float, radius: float) -> Part:
    """側壁を貫く円形の開口（切り欠く側）。wall_inner_x は壁の内側面の X。"""
    return Pos(wall_inner_x - 2.0, y, z) * Rot(0, 90, 0) * Cylinder(
        radius, P.wall + 4.0, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )


def _wall_openings() -> Part:
    """側壁の開口。車輪ハブ 2 箇所、リフト軸・チルト軸 2 箇所。"""
    hub_r = P.hub_od / 2 + P.wheel_opening_margin
    # ブラケット／アームの断面は arm_width 角。円形開口には外接円が入る必要がある
    shaft_r = P.arm_width * 2 ** 0.5 / 2 + 1.0
    ay, az = P.wheel_axis_y, P.wheel_axis_z
    uy, uz = P.front_axis

    cut = _side_opening(-P.wall, ay, az, hub_r)        # 左の車輪
    cut += _side_opening(P.inner_w, ay, az, hub_r)     # 右の車輪
    cut += _side_opening(-P.wall, uy, uz, shaft_r)     # 左のリフト軸
    cut += _side_opening(P.inner_w, uy, uz, shaft_r)   # 右のチルト軸
    return cut


def _floor_openings() -> Part:
    """床の開口。崖センサの覗き穴 2 箇所と、キャスタを通す穴。"""
    c = BOM["cliff_sensor_fl"]
    cut = None
    for pos in (P.cliff_l_pos, P.cliff_r_pos):
        hole = Pos(pos[0] + c.size[0] / 2, pos[1] + c.size[1] / 2, -P.floor - 2.0) * Cylinder(
            4.0, P.floor + 4.0, align=(Align.CENTER, Align.CENTER, Align.MIN)
        )
        cut = hole if cut is None else cut + hole

    cx, cy, _ = P.caster_pos
    cw, cd, _ = BOM["caster_rear"].size
    cut += Pos(cx, cy, -P.floor - 2.0) * Box(
        cw, cd, P.floor + 4.0, align=(Align.MIN, Align.MIN, Align.MIN)
    )
    return cut


def _fender(x_min: float, x_max: float) -> Part:
    """車輪の上を覆うフェンダー。履帯ハウジングに見せるための造形。

    タイヤ外周より fender_gap だけ外側の円弧シェル。上半分だけ残し、
    前端はリフトアーム／チルトブラケットの掃引を避けて fender_y_min で切る。
    """
    ay, az = P.wheel_axis_y, P.wheel_axis_z
    r_in = P.tire_radius + P.fender_gap
    r_out = r_in + P.fender_t
    width = x_max - x_min

    ring = Pos(x_min, ay, az) * Rot(0, 90, 0) * (
        Cylinder(r_out, width, align=(Align.CENTER, Align.CENTER, Align.MIN))
        - Cylinder(r_in, width, align=(Align.CENTER, Align.CENTER, Align.MIN))
    )
    # 上半分かつ Y >= fender_y_min の部分だけ残す
    keep = Pos(x_min, P.fender_y_min, az) * Box(
        width, ay + r_out - P.fender_y_min, r_out,
        align=(Align.MIN, Align.MIN, Align.MIN),
    )
    return ring & keep


def build_body() -> Part:
    """胴体シェル（上面が開いたトレー）。外殻の縦稜を丸め、車輪にフェンダーを付ける。"""
    outer = Pos(-P.wall, -P.wall, -P.floor) * Box(
        P.inner_w + 2 * P.wall,
        P.inner_d + 2 * P.wall,
        P.inner_h + P.floor,
        align=(Align.MIN, Align.MIN, Align.MIN),
    )
    # 内部空間は直方体のまま。外殻だけ丸めるので、角の肉厚が増えるだけで収まりは変わらない
    outer = fillet(outer.edges().filter_by(Axis.Z), radius=P.body_fillet)

    body = _cut(outer, interior(), "胴体の内部空間", min_removed=1000.0)

    # 車輪のフェンダー（左右）。胴体外壁に付け根を合わせて一体化する
    body += _fender(-P.wall - P.tire_radius - P.fender_gap - P.fender_t + 8.0, -P.wall)
    body += _fender(P.inner_w + P.wall, P.inner_w + P.wall + P.tire_radius + P.fender_gap + P.fender_t - 8.0)

    # 天板ボスは shell_boss_base_z から天面まで。床から立てると搭載物と必ず干渉する
    boss_h = P.inner_h - P.shell_boss_base_z
    for x, y in shell_boss_positions():
        body += Pos(x, y, P.shell_boss_base_z) * tapping_boss(
            P.shell_screw, height=boss_h, depth=P.shell_boss_depth
        )

    for x, y in if_board_boss_positions():
        body += Pos(x, y, P.if_board_pos[2] - P.board_boss_h) * tapping_boss(
            P.board_screw, height=P.board_boss_h, depth=P.board_boss_depth
        )

    body = _cut(body, _wall_openings(), "側壁の開口（車輪ハブ・リフト軸・チルト軸）")
    body = _cut(body, _floor_openings(), "床の開口（崖センサ・キャスタ）")
    body = _cut(body, _hatch_tab_pockets(), "バッテリー蓋のタブポケット")

    # 電源スイッチ（左側面）。レバーが -x を向く
    sw_bb = _place("power_switch", P.power_switch_pos, rot=(0.0, 0.0, 90.0)).bounding_box()
    body = _cut(
        body,
        rect_opening(
            center=(0.0, (sw_bb.min.Y + sw_bb.max.Y) / 2, (sw_bb.min.Z + sw_bb.max.Z) / 2),
            face="-x",
            size=(sw_bb.size.Y, sw_bb.size.Z),
            wall_thickness=P.wall,
        ),
        "電源スイッチの開口",
    )
    # AtomS3R の USB-C（背面）。180 度回してあるのでコネクタは +y 面に来る
    conn = BOM["atoms3r"].connectors[0]
    a_bb = _place("atoms3r", P.atoms3r_pos, rot=(0.0, 0.0, 180.0)).bounding_box()
    body = _cut(
        body,
        rect_opening(
            center=(a_bb.max.X - conn.pos[0], P.inner_d, a_bb.min.Z + conn.pos[2]),
            face="+y",
            size=conn.size,
            wall_thickness=P.wall,
        ),
        "AtomS3R の USB-C 開口",
    )
    # カメラのレンズ穴（前面）
    cam_bb = _place("unit_cams3", P.camera_pos, rot=FACE_FORWARD_ROT).bounding_box()
    body = _cut(
        body,
        Pos((cam_bb.min.X + cam_bb.max.X) / 2, 2.0, cam_bb.min.Z + P.cam_lens_offset_z)
        * Rot(90, 0, 0)
        * Cylinder(P.cam_lens_dia / 2, P.wall + 4.0, align=(Align.CENTER, Align.CENTER, Align.MIN)),
        "カメラのレンズ穴",
    )
    return body


def build_top_plate() -> Part:
    """天板。四隅にネジのバカ穴、首の配線を通す開口を持つ。"""
    plate = Pos(-P.wall, -P.wall, P.inner_h) * Box(
        P.inner_w + 2 * P.wall,
        P.plate_split_y + P.wall,
        P.top_plate,
        align=(Align.MIN, Align.MIN, Align.MIN),
    )
    for i, (x, y) in enumerate(shell_boss_positions()):
        plate = _cut(
            plate,
            Pos(x, y, P.inner_h) * clearance_hole(P.shell_screw, P.top_plate),
            f"天板のバカ穴 {i}",
        )

    # 首の配線を通す開口（配線の断面より片側 1 mm 大きく）
    nx, ny, _ = P.neck_harness_pos
    nw, nd, _ = BOM["neck_harness"].size
    plate = _cut(
        plate,
        Pos(nx - 1.0, ny - 1.0, P.inner_h - 1.0) * Box(
            nw + 2.0, nd + 2.0, P.top_plate + 2.0, align=(Align.MIN, Align.MIN, Align.MIN)
        ),
        "首の配線を通す開口",
    )
    return plate


def build_battery_hatch() -> Part:
    """NiMH パックの上を覆うスナップフィット蓋。工具レスで開閉する。

    ネジを使わないのは、パック幅 57 mm が内寸 60 mm をほぼ埋めており、
    パックの上にネジボスを立てるとパックを真上に抜けなくなるため。
    """
    y0 = P.plate_split_y
    depth = P.inner_d + P.wall - y0
    hatch = Pos(-P.wall, y0, P.inner_h) * Box(
        P.inner_w + 2 * P.wall, depth, P.top_plate,
        align=(Align.MIN, Align.MIN, Align.MIN),
    )

    # スナップタブ: 内側に下ろした脚と、側壁のポケットに食い込む突起
    tab_y0 = (P.plate_split_y + P.inner_d) / 2 - P.tab_len / 2
    z0 = P.inner_h - P.tab_h
    for x_face, sign in hatch_tab_positions():
        leg_x = x_face + 0.4 if sign < 0 else x_face - 0.4 - P.tab_w
        hatch += Pos(leg_x, tab_y0, z0) * Box(
            P.tab_w, P.tab_len, P.tab_h, align=(Align.MIN, Align.MIN, Align.MIN)
        )
        bump_x = x_face - P.tab_bump if sign < 0 else x_face
        hatch += Pos(bump_x, tab_y0, z0 + 1.0) * Box(
            P.tab_bump, P.tab_len, P.tab_h - 3.0,
            align=(Align.MIN, Align.MIN, Align.MIN),
        )

    # 背面上部の張り出し（実物の「バックパック」に相当）
    hump = Pos(
        (P.inner_w - P.hump_w) / 2,
        P.inner_d + P.wall - P.hump_d - 4.0,
        P.inner_h + P.top_plate - 1.0,
    ) * Box(P.hump_w, P.hump_d, P.hump_h + 1.0, align=(Align.MIN, Align.MIN, Align.MIN))
    hump = fillet(hump.edges().filter_by(Axis.Z), radius=P.hump_fillet)
    return hatch + hump


def build_head(tilt_deg: float = 0.0) -> Part:
    """頭部シェル + チルトブラケット。tilt_deg でチルト軸まわりに回した姿勢を作る。

    背面を開放し、そこから Unit OLED を入れて背面パネルで押さえる想定。
    ブラケットは右側面のホーンから、胴体外壁の外側を通って頭部の底に回り込む。
    """
    hx, hy, hz = P.head_origin
    shell = Pos(hx, hy, hz) * Box(
        P.head_w, P.head_d, P.head_h, align=(Align.MIN, Align.MIN, Align.MIN)
    )
    # 縦稜と横稜を丸める。実物 Cozmo の頭部は角が大きく落ちている
    shell = fillet(shell.edges().filter_by(Axis.Z), radius=P.head_fillet)
    shell = fillet(shell.edges().filter_by(Axis.X), radius=P.head_fillet * 0.6)

    cavity = Pos(hx + P.head_wall, hy + P.head_wall, hz + P.head_wall) * Box(
        P.head_w - 2 * P.head_wall,
        P.head_d - P.head_wall,          # 背面は開放
        P.head_h - 2 * P.head_wall,
        align=(Align.MIN, Align.MIN, Align.MIN),
    )
    head = _cut(shell, cavity, "頭部の内部空間", min_removed=1000.0)

    # 顔のパネル（黒い面に見せる掘り込み）。前面を貫通させず、窓だけを貫く。
    # 実物 Cozmo は顔の大部分が 1 枚の黒いパネルで、その奥に小さなディスプレイがある。
    window_z = oled_module_bottom_z() + P.oled_window_offset_z
    panel = Pos(
        hx + (P.head_w - P.face_panel_w) / 2,
        hy - 0.01,
        window_z - P.face_panel_h / 2,
    ) * Box(P.face_panel_w, P.face_panel_depth + 0.01, P.face_panel_h,
            align=(Align.MIN, Align.MIN, Align.MIN))
    panel = fillet(panel.edges().filter_by(Axis.Y), radius=P.face_panel_fillet)
    head = _cut(head, panel, "顔のパネルの掘り込み")

    # 顔の窓（OLED の有効表示エリア）。前面 = -Y
    head = _cut(
        head,
        rect_opening(
            center=(hx + P.head_w / 2, hy, window_z),
            face="-y",
            size=(P.oled_window_w, P.oled_window_h),
            wall_thickness=P.head_wall,
            margin=0.0,
        ),
        "顔の窓（OLED の有効表示エリア）",
    )

    # 前方に垂らす「あご」。胴体前面より手前にだけ出す
    if P.chin_h > 0.0:
        chin_y_max = -P.wall - 1.5
        chin = Pos(hx, hy, hz - P.chin_h) * Box(
            P.head_w, chin_y_max - hy, P.chin_h, align=(Align.MIN, Align.MIN, Align.MIN)
        )
        chin = fillet(chin.edges().filter_by(Axis.Z), radius=P.head_fillet)
        head += chin

    uy, uz = P.front_axis
    t, w = P.bracket_t, P.arm_width
    x_root = P.inner_w                      # ホーン当たり面（右側壁の内側）
    x_rise = P.inner_w + P.wall + P.bracket_gap   # 立ち上がり部の内側 X

    # ホーンに留まる円板
    bracket = Pos(x_root, uy, uz) * Rot(0, 90, 0) * Cylinder(
        SCREWS["M2"].boss_outer_dia / 2 + 3.0, t,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )
    # 円板から外側へ渡る板
    bracket += Pos(x_root, uy - w / 2, uz - w / 2) * Box(
        x_rise + t - x_root, w, w, align=(Align.MIN, Align.MIN, Align.MIN)
    )
    # 外壁の外を立ち上がる板
    bracket += Pos(x_rise, uy - w / 2, uz - w / 2) * Box(
        t, w, hz - (uz - w / 2), align=(Align.MIN, Align.MIN, Align.MIN)
    )
    # 頭部の底へ回り込む板
    bracket += Pos(hx + P.head_w / 2, uy - w / 2, hz - t) * Box(
        x_rise + t - (hx + P.head_w / 2), w, t, align=(Align.MIN, Align.MIN, Align.MIN)
    )
    return _rotate_about(head + bracket, tilt_deg, uy, uz)


def build_lift_arm() -> Part:
    """リフトアーム。左側面のホーンから前方へ伸び、先端にフォークを持つ。"""
    ly, lz = P.front_axis
    t, w = P.arm_thickness, P.arm_width
    x0 = -P.wall - t

    # 軸まわりの根元（ホーンに留まる円板）
    hub = Pos(x0, ly, lz) * Rot(0, 90, 0) * Cylinder(
        SCREWS["M2"].boss_outer_dia / 2 + 3.0, t,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )
    # アーム本体（軸から前方 = -Y へ）
    arm = Pos(x0, ly - P.arm_length, lz - w / 2) * Box(
        t, P.arm_length, w, align=(Align.MIN, Align.MIN, Align.MIN)
    )
    # 先端のフォーク（キューブを掛ける爪）。実物にならい、縦板 + 前方への舌の C 字にする
    fork_y = ly - P.arm_length
    arm += Pos(x0, fork_y, lz - w / 2 - P.fork_h + w) * Box(
        t, w, P.fork_h, align=(Align.MIN, Align.MIN, Align.MIN)
    )
    arm += Pos(x0, fork_y - P.fork_tongue, lz - w / 2 - P.fork_h + w) * Box(
        t, P.fork_tongue, w, align=(Align.MIN, Align.MIN, Align.MIN)
    )
    return _rotate_about(hub + arm, P.arm_angle_deg, ly, lz)


def camera_view_cone() -> Part:
    """カメラの視野を表す円錐。頭部がここに入ると映像に写り込む。

    カメラは胴体に固定で頭部と一緒に動かないため、頭部を下げたときに
    頭部の下端やあごが視界に入りうる。これを機械的に検出するために使う。
    """
    import math

    lens = _lens_center()
    half = math.radians(P.cam_dfov_deg / 2)
    r = P.cam_view_len * math.tan(half)
    # -Y 方向へ開く円錐。頂点をレンズ位置に置く
    return Pos(*lens) * Rot(90, 0, 0) * Cone(
        bottom_radius=0.5, top_radius=r, height=P.cam_view_len,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )


def _lens_center() -> tuple[float, float, float]:
    """カメラのレンズ中心（胴体座標）。"""
    bb = _place("unit_cams3", P.camera_pos, rot=FACE_FORWARD_ROT).bounding_box()
    return ((bb.min.X + bb.max.X) / 2, -P.wall, bb.min.Z + P.cam_lens_offset_z)


def head_group(tilt_deg: float = 0.0) -> dict[str, Part]:
    """頭部シェルと、頭部に載る部品をまとめてチルトさせたもの。

    チルト時の干渉を見るときは、シェルだけを回して搭載物を置き去りにしてはいけない。
    頭部に載っている OLED はシェルと一体で動く。
    """
    uy, uz = P.front_axis
    group = {"head": build_head(tilt_deg)}
    for cid, part in head_components().items():
        group[cid] = _rotate_about(part, tilt_deg, uy, uz)
    return group


def build_hub() -> Part:
    """XL330 → タミヤホイール変換ハブ。pen_robo_wheel_hub の設計をそのまま流用する。"""
    from projects.pen_robo_wheel_hub.model import build_hub as _hub

    return _hub()


def place_hubs() -> dict[str, Part]:
    """変換ハブを左右に配置する。ホーン当たり面が側壁の内側面に来る。"""
    ay, az = P.wheel_axis_y, P.wheel_axis_z
    hub = build_hub()
    return {
        "hub_l": Pos(0.0, ay, az) * Rot(0, -90, 0) * hub,
        "hub_r": Pos(P.inner_w, ay, az) * Rot(0, 90, 0) * hub,
    }


# --------------------------------------------------------------------------
# アセンブリ
# --------------------------------------------------------------------------
def printed_parts() -> dict[str, Part]:
    """3D プリントする部品。"""
    return {
        "body": build_body(),
        "top_plate": build_top_plate(),
        "battery_hatch": build_battery_hatch(),
        "head": build_head(),
        "lift_arm": build_lift_arm(),
        **place_hubs(),
    }


def build_all() -> dict[str, Part]:
    return {**printed_parts(), **place_components()}


def overall_size() -> tuple[float, float, float]:
    """機体全体の外形 (X, Y, Z)。接地面からの高さを含む。"""
    parts = build_all()
    xs = [p.bounding_box() for p in parts.values()]
    return (
        max(b.max.X for b in xs) - min(b.min.X for b in xs),
        max(b.max.Y for b in xs) - min(b.min.Y for b in xs),
        max(b.max.Z for b in xs) - P.ground_z,
    )


def export(out_dir: Path = OUT) -> None:
    from build123d import export_step, export_stl

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, part in printed_parts().items():
        export_stl(part, str(out_dir / f"{name}.stl"), tolerance=0.02)
        export_step(part, str(out_dir / f"{name}.step"))
    print(f"出力しました: {out_dir}")


def main() -> None:
    if "--show" in sys.argv:
        from hwlib.render import show

        show(build_all())
    elif "--render" in sys.argv:
        from hwlib.render import render

        path = render(
            build_all(),
            OUT / "assembly.png",
            opacity={"body": 0.3, "top_plate": 0.25, "battery_hatch": 0.25, "head": 0.3},
        )
        print(f"レンダリングしました: {path}")
    elif "--export" in sys.argv:
        export()
    else:
        print(__doc__)
        print("使い方: python -m projects.cozmo_clone.model [--show|--render|--export]")


if __name__ == "__main__":
    main()
