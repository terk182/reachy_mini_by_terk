"""สร้างไฟล์ STL ตัวอย่างสำหรับหุ่น Reachy Mini DIY (ชุด STS3215 + crank-rod)

สร้างชิ้นส่วน 2 กลุ่ม:
  A) สำหรับ MuJoCo sim (ชื่อตรงกับ config.meshes.parts):
     base, lower_plate, leg, top_plate, head, antenna
  B) สำหรับ print จริง (ชิ้นส่วนกลไก):
     crank_arm (แขนหมุน 40mm) + rod (ก้านต่อ 85mm)

วิธีใช้:
    python scripts/generate_sample_stls.py
"""

import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.robot_config import DEFAULT_CONFIG  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[1] / DEFAULT_CONFIG["meshes"]["dir"]
SEG = 32  # ความละเอียดวงกลม

# --- ขนาดจาก config (STS3215 build) ---
st = DEFAULT_CONFIG["stewart"]
LEG_HOME = st["leg_home"]                     # ~79.8 mm
LOWER_R = st["base_radius"]                   # 38 (Reachy ทางการ)
TOP_R = st["top_radius"]                      # 30 (Reachy ทางการ)
ARM_LEN = st["arm_len"]                       # 40 (แขนหมุน)
ROD_LEN = st["rod_len"]                       # 85 (ก้านต่อ)
HEAD_R = 25.0
ANTENNA_LEN = 45.0
MOTOR_R = 55.0     # รัศมีตำแหน่งยึดมอเตอร์บนจานล่าง (เผื่อตัวมอเตอร์ 40mm)
MOTOR_W = 42.0     # ความกว้างช่องมอเตอร์ (40mm + เผื่อ)


# ---------- เครื่องมือ ----------
def _write_stl(path, vertices, faces):
    """เขียน binary STL: vertices (N,3), faces (M,3)"""
    tris = np.asarray(vertices)[np.asarray(faces)]
    with open(path, "wb") as f:
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", len(tris)))
        for tri in tris:
            v0, v1, v2 = tri
            n = np.cross(v1 - v0, v2 - v0)
            nl = float(np.linalg.norm(n))
            n = n / nl if nl > 1e-12 else np.zeros(3)
            f.write(struct.pack("<12f", *n, *tri.ravel()))
            f.write(struct.pack("<H", 0))


def _assemble(parts):
    """รวมหลายชิ้น (verts, faces) เป็น mesh เดียว"""
    verts, faces = [], []
    for v, f in parts:
        base = len(verts)
        verts.extend(np.asarray(v).tolist())
        faces.extend((np.asarray(f) + base).tolist())
    return np.array(verts), np.array(faces)


def _cylinder(r, z0, z1, seg=SEG):
    """ทรงกระบอกแกน Z ตั้งแต่ z=z0 ถึง z=z1"""
    a = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    top = np.stack([r * np.cos(a), r * np.sin(a), np.full(seg, z1)], 1)
    bot = np.stack([r * np.cos(a), r * np.sin(a), np.full(seg, z0)], 1)
    verts = np.vstack([np.array([0.0, 0.0, z1]), np.array([0.0, 0.0, z0]), top, bot])
    faces, ti, bi = [], 2, 2 + seg
    for i in range(seg):
        j = (i + 1) % seg
        faces.append([ti + i, bi + i, bi + j])
        faces.append([ti + i, bi + j, ti + j])
    for i in range(1, seg - 1):
        faces.append([0, ti + i + 1, ti + i])   # ฝาบน (+Z)
        faces.append([1, bi + i, bi + i + 1])   # ฝาล่าง (-Z)
    return verts, np.array(faces)


def _frustum(r0, r1, z0, z1, seg=SEG):
    """กรวยตัด (base foot) แกน Z"""
    a = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    top = np.stack([r1 * np.cos(a), r1 * np.sin(a), np.full(seg, z1)], 1)
    bot = np.stack([r0 * np.cos(a), r0 * np.sin(a), np.full(seg, z0)], 1)
    verts = np.vstack([np.array([0.0, 0.0, z1]), np.array([0.0, 0.0, z0]), top, bot])
    faces, ti, bi = [], 2, 2 + seg
    for i in range(seg):
        j = (i + 1) % seg
        faces.append([ti + i, bi + i, bi + j])
        faces.append([ti + i, bi + j, ti + j])
    for i in range(1, seg - 1):
        faces.append([0, ti + i + 1, ti + i])
        faces.append([1, bi + i, bi + i + 1])
    return verts, np.array(faces)


def _prism(n, r, z0, z1):
    """ปริซึม n เหลี่ยม แกน Z"""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    top = np.stack([r * np.cos(a), r * np.sin(a), np.full(n, z1)], 1)
    bot = np.stack([r * np.cos(a), r * np.sin(a), np.full(n, z0)], 1)
    verts = np.vstack([top, bot])
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j])
        faces.append([i, n + j, n + i])
    for i in range(1, n - 1):
        faces.append([0, i + 1, i])
        faces.append([n, n + i, n + i + 1])
    return verts, np.array(faces)


def _sphere(r, lats=16, lons=24):
    """ทรงกลมรัศมี r จุดศูนย์กลางที่ origin"""
    phi = np.linspace(0, np.pi, lats)
    theta = np.linspace(0, 2 * np.pi, lons, endpoint=False)
    verts = [[r * np.sin(p) * np.cos(t), r * np.sin(p) * np.sin(t), r * np.cos(p)]
             for p in phi for t in theta]
    verts = np.array(verts)
    faces = []
    for i in range(lats - 1):
        for j in range(lons):
            j2 = (j + 1) % lons
            a, b = i * lons + j, i * lons + j2
            c, d = (i + 1) * lons + j, (i + 1) * lons + j2
            faces.append([a, b, d])
            faces.append([a, d, c])
    return verts, np.array(faces)

def _box(cx, cy, cz, sx, sy, sz):
    """กล่อง กึ่งกลาง (cx,cy,cz) ขนาด sx,sy,sz"""
    x0, x1 = cx - sx / 2, cx + sx / 2
    y0, y1 = cy - sy / 2, cy + sy / 2
    z0, z1 = cz - sz / 2, cz + sz / 2
    v = np.array([
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
    ], dtype=float)
    f = np.array([
        [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
        [0, 4, 1], [1, 4, 5], [3, 2, 7], [7, 2, 6],
        [0, 3, 4], [4, 3, 7], [1, 5, 2], [2, 5, 6],
    ])
    return v, f

def _rot_x(verts, ang_deg):
    """หมุนจุดรอบแกน X (แปลงทรงกระบอกแกน Z -> แกน Y)"""
    c, s = np.cos(np.radians(ang_deg)), np.sin(np.radians(ang_deg))
    r = np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    return np.asarray(verts) @ r.T


# ---------- ประกอบชิ้นส่วน ----------
def _build_parts():
    # ฐาน: กรวยตัด (เท้าบาน, ใหญ่ขึ้นรองรับหัวที่หนัก) กลาง origin
    base_v, base_f = _frustum(55.0, 38.0, -25.0, 25.0)

    # จานล่าง: ปริซึม 6 เหลี่ยม (รัศมีจาก config) หนา 10 + หมุดนำตำแหน่งมอเตอร์ 6 จุด
    lower_v, lower_f = _prism(6, LOWER_R, -5.0, 5.0)
    pins = []
    for i in range(6):
        a = np.deg2rad(i * 60.0)
        pin_v, pin_f = _cylinder(5.0, 3.0, 8.0)
        offset = np.array([MOTOR_R * np.cos(a), MOTOR_R * np.sin(a), 0.0])
        pins.append((pin_v + offset, pin_f))
    lower_v, lower_f = _assemble([(lower_v, lower_f)] + pins)

    # ขา (strut จริง = ก้านตรงจากจานล่างไปจานบน) ใช้ใน sim
    leg_v, leg_f = _cylinder(6.0, 0.0, LEG_HOME)

    # จานบน: ปริซึม 6 เหลี่ยม (รัศมีจาก config) หนา 8
    top_v, top_f = _prism(6, TOP_R, -4.0, 4.0)

    # หัว: ทรงกลม (หน้า = +Y)
    head_v, head_f = _sphere(HEAD_R)

    # เสาอากาศ: ยาว 45 ไปทาง +Y
    ant_v, ant_f = _cylinder(4.5, 0.0, ANTENNA_LEN)
    ant_v = _rot_x(ant_v, -90.0)

    # แขนหมุน (crank): 40mm + ดุมกลาง (print จริง)
    arm_v, arm_f = _assemble([
        _box(0.0, 0.0, 0.0, ARM_LEN, 8.0, 5.0),   # แขน
        _cylinder(7.0, -4.5, 4.5),                # ดุมยึดเพลา
    ])

    # ก้านต่อ (rod): 85mm + หัวบอล 2 ด้าน (print จริง)
    rod_body, rod_f = _cylinder(3.0, 0.0, ROD_LEN)
    rod_body = _rot_x(rod_body, -90.0)  # ตาม +Y
    tip, tip_f = _sphere(5.0)
    tip2 = tip + np.array([0.0, ROD_LEN, 0.0])
    rod_v, rod_f = _assemble([(rod_body, rod_f), (tip, tip_f), (tip2, tip_f)])

    return {
        "base.stl": (base_v, base_f),
        "lower_plate.stl": (lower_v, lower_f),
        "leg.stl": (leg_v, leg_f),
        "top_plate.stl": (top_v, top_f),
        "head.stl": (head_v, head_f),
        "antenna.stl": (ant_v, ant_f),
        # --- ชิ้นส่วนกลไก (print จริง, ไม่ใช้ใน sim) ---
        "crank_arm.stl": (arm_v, arm_f),
        "rod.stl": (rod_v, rod_f),
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    parts = _build_parts()
    for fname, (v, f) in parts.items():
        path = OUT_DIR / fname
        _write_stl(path, v, f)
        print(f"  เขียน {path}  (verts={len(v)}, faces={len(f)})")
    print(f"\nสร้าง STL ครบ {len(parts)} ชิ้นใน {OUT_DIR}")
    print("  - sim ใช้: base/lower_plate/leg/top_plate/head/antenna")
    print("  - print จริงเพิ่ม: crank_arm (แขน 40mm) + rod (ก้าน 85mm)")


if __name__ == "__main__":
    main()
