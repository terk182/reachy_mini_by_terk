"""Stewart platform 6-DOF สำหรับหัว Reachy Mini DIY

ออกแบบ: จานล่าง 6 จุด (รัศมี base_radius) + จานบน 6 จุด (รัศมี top_radius)
วางเป็นคู่ 3 คู่ (paired) เหมือน Reachy ทางการ ขาแต่ละขาเชื่อมจานล่าง-จานบน

IK: กำหนดท่าจานบน (z, roll, pitch, yaw) -> คำนวณความยาวขา 6 ขา -> แปลงเป็น
ตำแหน่ง servo ผ่านกลไกขา:
  - "leadscrew" : ขา = สกรู (ความยาว ∝ มุมมอเตอร์, เส้นตรง)
  - "crank_rod" : ขา = แขนหมุน (crank) + ก้านต่อ (rod) — แบบเดียวกับ Reachy ทางการ
                  (แก้ 2-bar triangle มี 2 คำตอบ เลือกด้วย solution)

มี FK (Newton) สำหรับตรวจสอบความถูกต้องของ IK แบบไป-กลับ
"""

from __future__ import annotations

import math

import numpy as np


def _rotation_matrix(roll, pitch, yaw):
    """เมทริกซ์หมุน (ZYX: yaw -> pitch -> roll)"""
    cr, sr = np.cos(roll), np.sin(roll)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return rz @ ry @ rx


# ---------- การจัดวางขา (layout) ----------
# แบบ Reachy ทางการ: ขา 6 ขาเป็น 3 คู่ คร่อมมุม 60°/180°/300°
# แต่ละคู่ห่างกัน 2·half-width (base กับ top ต่างกันเล็กน้อย) -> ขาเอียงเข้าหาศูนย์กลาง
_OFFICIAL_PAIR_CENTERS_DEG = (60.0, 180.0, 300.0)
_OFFICIAL_BASE_HALF_DEG = 15.2576   # องศา ครึ่งความกว้างคู่ (ฝั่งแกนมอเตอร์)
_OFFICIAL_TOP_HALF_DEG = 13.4933    # องศา ครึ่งความกว้างคู่ (ฝั่งจุดยึดก้านบน)


def _paired_angles(centers_deg, half_deg):
    """มุมจุดยึดแบบ paired (3 คู่) -> np.array 6 มุม (rad) เรียง [คู่1-, คู่1+, ...]"""
    angles = []
    for c in centers_deg:
        angles.append(c - half_deg)
        angles.append(c + half_deg)
    return np.deg2rad(np.asarray(angles, dtype=float))


def leg_endpoints(z, roll, pitch, yaw, base_radius, top_radius,
                  top_offset_deg=30.0, layout="paired"):
    """คำนวณตำแหน่งจุดของขา 6 ขา

    layout:
      - "paired"  (default, แบบ Reachy ทางการ): 3 คู่ คร่อม 60/180/300°
      - "uniform": ห่างเท่ากัน 60° (แบบเดิม) + หมุนจานบนอีก top_offset_deg

    คืน (base_pts, top_world) รูป (3, 6) — แต่ละคอลัมน์คือจุด [x, y, z] (mm)
    (ใช้ทั้งคำนวณความยาวขา และวาด GUI)
    """
    if layout == "paired":
        base_angles = _paired_angles(
            _OFFICIAL_PAIR_CENTERS_DEG, _OFFICIAL_BASE_HALF_DEG)
        top_angles = _paired_angles(
            _OFFICIAL_PAIR_CENTERS_DEG, _OFFICIAL_TOP_HALF_DEG)
    else:  # "uniform"
        angles = np.deg2rad(np.arange(6) * 60.0)
        base_angles = angles
        top_angles = angles + np.deg2rad(top_offset_deg)

    base_pts = np.stack([
        [base_radius * np.cos(a), base_radius * np.sin(a), 0.0]
        for a in base_angles
    ], axis=1)
    top_pts = np.stack([
        [top_radius * np.cos(a), top_radius * np.sin(a), 0.0]
        for a in top_angles
    ], axis=1)

    r = _rotation_matrix(roll, pitch, yaw)
    p = np.array([0.0, 0.0, z])
    top_world = p[:, None] + r @ top_pts
    return base_pts, top_world


def leg_lengths(z, roll, pitch, yaw, base_radius, top_radius,
                top_offset_deg=30.0, layout="paired"):
    """คำนวณความยาวขา 6 ขา (mm) สำหรับท่าจานบนที่กำหนด"""
    base_pts, top_world = leg_endpoints(
        z, roll, pitch, yaw, base_radius, top_radius, top_offset_deg, layout)
    return [float(np.linalg.norm(top_world[:, i] - base_pts[:, i]))
            for i in range(6)]


def length_to_servo_pos(
    length,
    leg_home,
    pitch_mm,
    pos_center=2048,
    mechanism="leadscrew",
    arm_len=40.0,
    rod_len=85.0,
    solution=0,
):
    """แปลงความยาวขา (mm) -> ตำแหน่ง servo (0-4095)

    mechanism="leadscrew": ความยาว ∝ มุม (เส้นตรง)
    mechanism="crank_rod": แก้ 2-bar triangle (แขนหมุน + ก้านต่อ)
    """
    if mechanism == "leadscrew":
        delta_deg = (length - leg_home) / pitch_mm * 360.0
        pos = pos_center + delta_deg * 4096.0 / 360.0
        return int(round(np.clip(pos, 0, 4095)))
    if mechanism == "crank_rod":
        return crank_to_servo_pos(length, arm_len, rod_len, solution, pos_center)
    raise ValueError(f"mechanism ไม่รู้จัก: {mechanism} (ใช้ leadscrew / crank_rod)")


# ---------- กลไก crank + rod (แบบ Reachy ทางการ) ----------

def crank_angle_2bar(leg_length, arm_len, rod_len, solution=0):
    """มุมแขนหมุน (crank) จากความยาวขา — สองท่อน (แขน + ก้าน)

    กฎโคไซน์:  rod_len² = arm_len² + leg_length² - 2·arm_len·leg_length·cos(θ)
    มี 2 คำตอบ (ศอกบน/ล่าง) เลือกด้วย solution (0 = +θ, 1 = -θ)

    คืน θ ในหน่วยเรเดียน (θ=0 = แขนชี้ไปทางจานบน)
    """
    length = float(leg_length)
    a, b = float(arm_len), float(rod_len)
    if length <= 0 or a <= 0 or b <= 0:
        raise ValueError("arm_len / rod_len / leg_length ต้องเป็นบวก")
    # เงื่อนไขเข้าได้: |a-b| <= L <= a+b (ถ้าเกิน clip ให้ได้มุมที่สุดขั้ว)
    cos_theta = (a * a + length * length - b * b) / (2.0 * a * length)
    cos_theta = float(np.clip(cos_theta, -1.0, 1.0))
    theta = math.acos(cos_theta)
    return theta if solution == 0 else -theta


def crank_to_servo_pos(leg_length, arm_len, rod_len, solution=0, pos_center=2048):
    """ความยาวขา -> ตำแหน่ง servo (0-4095) สำหรับกลไก crank+rod"""
    theta = crank_angle_2bar(leg_length, arm_len, rod_len, solution)
    pos = pos_center + math.degrees(theta) / 360.0 * 4096.0
    return int(round(np.clip(pos, 0, 4095)))


def home_pos_to_center(home_pos, leg_home, arm_len, rod_len, solution):
    """แปลงตำแหน่ง servo ที่ท่า home -> ตำแหน่ง servo ที่ θ=0 (pos_center)

    crank_to_servo_pos ใช้ pos_center = ตำแหน่งที่ θ=0 (แขนชี้ขึ้น, L=arm+rod)
    แต่ calibrate เก็บ leg_home_pos = ตำแหน่งที่ท่า home (L=leg_home)
    -> ต้องเลื่อนกลับ ±θ_home ก่อนนำไปใช้เป็น pos_center
    """
    theta_home = crank_angle_2bar(leg_home, arm_len, rod_len, solution)
    return home_pos - math.degrees(theta_home) / 360.0 * 4096.0


def crank_angle_to_leg_length(theta, arm_len, rod_len, solution=0):
    """มุมแขนหมุน (rad) -> ความยาวขา (mm) — กลับจาก crank_angle_2bar

    จาก b² = a² + L² - 2aL·cosθ แก้สมการกำลังสองได้ 2 ราก:
      L = a·cosθ ± sqrt(b² - a²·sin²θ)
    รากหนึ่งคือความยาวจริง (บวก) อีกรากคือค่าลบหลอก (a² < b² เสมอ) —
    และ ±θ (solution 0/1) ให้ L เท่ากัน → เลือกรากที่เป็นบวกเสมอ
    """
    a, b = float(arm_len), float(rod_len)
    c = math.cos(theta)
    inside = b * b - a * a * (1.0 - c * c)
    inside = max(0.0, inside)
    return a * c + math.sqrt(inside)


def servo_pos_to_length(
    pos,
    leg_home,
    pitch_mm,
    pos_center=2048,
    mechanism="leadscrew",
    arm_len=40.0,
    rod_len=85.0,
    solution=0,
):
    """ตำแหน่ง servo (0-4095) -> ความยาวขา (mm) — กลับจาก length_to_servo_pos

    ใช้ในการ calibrate/verify (อ่านตำแหน่งจริง -> คำนวณ FK)
    """
    if mechanism == "leadscrew":
        return leg_home + (pos - pos_center) * pitch_mm / 4096.0
    if mechanism == "crank_rod":
        theta = math.radians((pos - pos_center) / 4096.0 * 360.0)
        return crank_angle_to_leg_length(theta, arm_len, rod_len, solution)
    raise ValueError(f"mechanism ไม่รู้จัก: {mechanism} (ใช้ leadscrew / crank_rod)")


def crank_tip_reach(leg_length, arm_len, rod_len, solution=0):
    """ตรวจสอบว่าปลายก้านถึงจุดยึดจานบนจริงไหม (คืนระยะจากปลายก้านถึงจุดยึด)

    ใช้ทดสอบว่า 2-bar solver ถูกต้อง: ค่าที่ได้ต้อง ≈ rod_len
    """
    theta = crank_angle_2bar(leg_length, arm_len, rod_len, solution)
    # จุดปลายแขน (แขนหมุนในระนาบ, จุดยึดจานบนอยู่ที่ (L, 0))
    tip = (arm_len * math.cos(theta), arm_len * math.sin(theta))
    attach = (leg_length, 0.0)
    return math.hypot(tip[0] - attach[0], tip[1] - attach[1])


# ---------- FK (Forward Kinematics) เชิงตัวเลข ----------

def forward_kinematics(
    target_lengths,
    base_radius,
    top_radius,
    top_offset_deg=30.0,
    layout="paired",
    x0=None,
    max_iter=100,
    tol=1e-9,
):
    """FK: ความยาวขา 6 ขา (mm) -> ท่าจานบน (z, roll, pitch, yaw)

    แก้ด้วย Newton (finite-difference Jacobian) โดยสมมติจานบนอยู่กึ่งกลาง (x=y=0)
    เหมือนกับที่ IK ของเราใช้ — ใช้ตรวจสอบ IK แบบไป-กลับ

    ⚠️ FK ของ Stewart มีหลายคำตอบ (assembly modes) — ถ้าไม่ระบุ x0 อาจเจอ
    solution อื่นที่ให้ความยาวขาเท่ากันได้ (ไม่ใช่บั๊ก แต่เป็นคุณสมบัติทางเรขาคณิต)
    ระบุ x0=(z, roll, pitch, yaw) ที่ใกล้เคียงเพื่อล็อกให้อยู่ในท่าเดียวกัน

    คืน (pose: tuple(z, roll, pitch, yaw), residual)
    """
    target = np.asarray(target_lengths, dtype=float)
    if target.shape != (6,):
        raise ValueError("target_lengths ต้องเป็น array 6 ค่า")

    # จุดเริ่มต้น: ค่าเฉลี่ยความยาวขา (ประมาณ z) หรือ x0 ที่ให้มา
    x = (np.array(x0, dtype=float) if x0 is not None
         else np.array([float(np.mean(target)), 0.0, 0.0, 0.0]))
    residual = float("inf")
    for _ in range(max_iter):
        lengths = np.array(leg_lengths(
            x[0], x[1], x[2], x[3], base_radius, top_radius,
            top_offset_deg, layout))
        r = lengths - target
        residual = float(np.max(np.abs(r)))
        if residual < tol:
            break
        jac = np.zeros((6, 4))
        h = 1e-6
        for j in range(4):
            xp = x.copy()
            xp[j] += h
            lp = np.array(leg_lengths(
                xp[0], xp[1], xp[2], xp[3], base_radius, top_radius,
                top_offset_deg, layout))
            jac[:, j] = (lp - lengths) / h
        dx = np.linalg.lstsq(jac, -r, rcond=None)[0]
        x += dx

    # บังคับท่า "หงาย" (z > 0): ถ้าได้ท่ากระจก (z<0) ให้สะท้อนกลับ
    # เพราะ pose (z,r,p,y) กับ (-z,-r,-p,y) ให้ความยาวขาเท่ากัน (สมมาตรจานล่าง z=0)
    if x[0] < 0:
        x[0] = -x[0]
        x[1] = -x[1]
        x[2] = -x[2]

    return (float(x[0]), float(x[1]), float(x[2]), float(x[3])), residual


class StewartHead:
    """ควบคุมหัว Stewart platform ผ่าน ServoBus

    รองรับกลไกขา 2 แบบ (cfg["mechanism"]):
      - "leadscrew" : ขา = สกรู (ความยาว ∝ มุมมอเตอร์)
      - "crank_rod" : ขา = แขนหมุน + ก้านต่อ (แบบ Reachy ทางการ, ใช้ arm_len/rod_len/solution)
    """

    def __init__(self, bus, servo_ids, cfg):
        self.bus = bus
        self.servo_ids = list(servo_ids)
        self.cfg = cfg
        self.mechanism = cfg.get("mechanism", "leadscrew")
        self.solutions = cfg.get("solution", [])
        # ตำแหน่ง home จริงต่อขา (จากการ calibrate) — ถ้ามี ใช้แทน pos_center รวม
        self.home_positions = cfg.get("leg_home_pos")

    def set_pose(self, z, roll=0.0, pitch=0.0, yaw=0.0, speed=1000):
        """ตั้งท่าหัว: z=mm, roll/pitch/yaw=เรเดียน

        คืนค่าความยาวขาที่คำนวณได้ (สำหรับการ calibrate)
        """
        lengths = leg_lengths(
            z, roll, pitch, yaw,
            self.cfg["base_radius"], self.cfg["top_radius"],
            self.cfg.get("top_offset_deg", 30.0), self.cfg.get("layout", "paired"),
        )
        targets = []
        for i, (sid, length) in enumerate(zip(self.servo_ids, lengths)):
            solution = self.solutions[i] if i < len(self.solutions) else 0
            # ใช้ตำแหน่ง home เฉพาะขา ถ้ามีการ calibrate แล้ว
            center = self.cfg.get("pos_center", 2048)
            if self.home_positions and i < len(self.home_positions):
                center = home_pos_to_center(
                    self.home_positions[i],
                    self.cfg["leg_home"],
                    self.cfg.get("arm_len", 40.0),
                    self.cfg.get("rod_len", 85.0),
                    solution,
                )
            pos = length_to_servo_pos(
                length,
                self.cfg["leg_home"],
                self.cfg["pitch"],
                pos_center=center,
                mechanism=self.mechanism,
                arm_len=self.cfg.get("arm_len", 40.0),
                rod_len=self.cfg.get("rod_len", 85.0),
                solution=solution,
            )
            targets.append((sid, pos))
        self.bus.sync_set_position(targets, speed=speed)
        return lengths

    def home(self, speed=1000):
        """กลับท่าเริ่มต้น (หัวตั้งตรง)"""
        return self.set_pose(self.cfg["z_home"], speed=speed)
