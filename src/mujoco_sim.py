"""MuJoCo simulation สำหรับหุ่น Reachy Mini DIY

สร้าง MJCF model ของหุ่นของเราเอง (ฐานหมุน + Stewart platform 6 ขา + หัว + เสาอากาศ)
แล้วขับเคลื่อนแบบ kinematic จาก state ของหุ่น (ผ่าน IK จริงใน stewart.py)

- ใช้ mujoco.viewer (หน้าต่าง 3D โต้ตอบได้: ลากหมุน/ซูม)
- ไม่ต้องมีฮาร์ดแวร์ ใช้พัฒนา logic/demo ได้เหมือนหุ่นจริง

วิธีใช้ผ่าน Robot:
    with Robot(backend="sim", gui="mujoco") as robot:
        robot.wave()
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import mujoco
import mujoco.viewer  # ต้อง import แยก (ไม่ถูกรวมกับ import mujoco)
import numpy as np

from .stewart import leg_endpoints, leg_lengths

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ลำดับชิ้นส่วนที่รองรับ mesh (ต้องตรงกับ config.meshes.parts)
MESH_PART_NAMES = ("base", "lower_plate", "leg", "top", "head", "antenna")


def _mm(x: float) -> float:
    """mm -> m (หน่วยของ MuJoCo)"""
    return x / 1000.0


def _quat_from_rpy(roll, pitch, yaw):
    """มุม Euler ZYX (Rz@Ry@Rx) -> quaternion (w, x, y, z) ของ MuJoCo"""
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    return np.array([
        cy * cp * cr + sy * sp * sr,
        cy * cp * sr - sy * sp * cr,
        cy * sp * cr + sy * cp * sr,
        sy * cp * cr - cy * sp * sr,
    ], dtype=float)


def _quat_align_z(direction):
    """quaternion ที่หมุนแกน +Z ไปทาง direction"""
    d = np.asarray(direction, dtype=float)
    d = d / np.linalg.norm(d)
    z = np.array([0.0, 0.0, 1.0])
    c = float(np.dot(z, d))
    if np.allclose(np.cross(z, d), 0):
        if c > 0:
            return np.array([1.0, 0.0, 0.0, 0.0])
        return np.array([0.0, 1.0, 0.0, 0.0])  # หมุน 180° รอบ X
    v = np.cross(z, d)
    q = np.array([1.0 + c, v[0], v[1], v[2]])
    return q / np.linalg.norm(q)


def _quat_mul(a, b):
    """คูณ quaternion (w, x, y, z): a * b"""
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    ], dtype=float)


def _quat_z(angle):
    """quaternion หมุนรอบแกน Z ด้วยมุม angle"""
    return np.array([math.cos(angle / 2), 0.0, 0.0, math.sin(angle / 2)], dtype=float)


def _resolve_meshes(config):
    """ค้นหาไฟล์ STL ตาม config.meshes -> dict {part_name: Path}

    คืนเฉพาะชิ้นส่วนที่หาไฟล์เจอ (ไม่เจอ -> ไม่ใส่ใน dict = ใช้รูปทรงพื้นฐาน)
    """
    meshes = config.get("meshes") or {}
    if not meshes.get("enabled"):
        return {}
    mdir = Path(meshes.get("dir", "models/stl"))
    if not mdir.is_absolute():
        mdir = PROJECT_ROOT / mdir
    parts = meshes.get("parts") or {}
    found = {}
    for name, entry in parts.items():
        fname = entry if isinstance(entry, str) else entry.get("file")
        if not fname:
            continue
        p = mdir / fname
        if p.exists():
            found[name] = p
    return found


def _mesh_geom(name, material, config):
    """สร้าง tag <geom type="mesh"> พร้อม pos/quat alignment จาก config"""
    entry = (config.get("meshes") or {}).get("parts", {}).get(name, {})
    if isinstance(entry, str):
        entry = {}
    pos = entry.get("pos", [0.0, 0.0, 0.0])
    quat = entry.get("quat", [1.0, 0.0, 0.0, 0.0])
    pos_s = " ".join(f"{v:.6f}" for v in pos)
    quat_s = " ".join(f"{v:.6f}" for v in quat)
    return (f'<geom type="mesh" mesh="{name}" pos="{pos_s}" '
            f'quat="{quat_s}" material="{material}"/>')


def build_mjcf(config) -> str:
    """สร้าง MJCF XML ของหุ่น DIY ตาม config

    ถ้ามีไฟล์ STL (config.meshes.enabled=True) จะใช้ mesh แทนรูปทรงพื้นฐาน
    """
    st = config["stewart"]
    found = _resolve_meshes(config)
    lim = config["limits"]
    base_radius = _mm(st["base_radius"])
    top_radius = _mm(st["top_radius"])
    lower_plate_z = _mm(st.get("base_plate_z", 80.0))
    z_home = st["z_home"]
    head_radius = _mm(25.0)
    antenna_len = _mm(45.0)
    base_deg_max = abs(lim["base_deg"][1])

    # จุด 6 จุดของจานล่าง/จานบน (เรขาคณิตเดียวกับ stewart.py — คำนวณในหน่วย mm)
    base_arr, top_arr = leg_endpoints(
        st["z_home"], 0.0, 0.0, 0.0,
        st["base_radius"], st["top_radius"],
        st.get("top_offset_deg", 30.0), st.get("layout", "paired"),
    )
    base_pts = [(x * 0.001, y * 0.001) for x, y in base_arr[:2].T]
    top_pts = [(x * 0.001, y * 0.001) for x, y in top_arr[:2].T]

    # ทิศทางขา (จากจุดล่างไปจุดบนตอนท่า home) + ความยาวขา home
    leg_dirs, leg_home = [], None
    for (bx, by), (tx, ty) in zip(base_pts, top_pts):
        d = np.array([tx - bx, ty - by, _mm(z_home)])
        leg_home = float(np.linalg.norm(d))
        leg_dirs.append(d / leg_home)

    L = []
    L.append('<mujoco model="Reachy Mini DIY">')
    L.append('  <compiler angle="radian" coordinate="local"/>')
    L.append('  <option timestep="0.002"/>')
    L.append('  <visual><global azimuth="140" elevation="-20"/></visual>')
    L.append('  <asset>')
    L.append('    <texture type="skybox" builtin="gradient" rgb1="0.2 0.3 0.5" rgb2="0 0 0" width="512" height="512"/>')
    L.append('    <texture type="2d" name="ground" builtin="checker" rgb1="0.25 0.3 0.35" rgb2="0.15 0.2 0.25" width="300" height="300"/>')
    L.append('    <material name="ground" texture="ground" texuniform="true" texrepeat="8 8" reflectance="0.2"/>')
    L.append('    <material name="blue" rgba="0.2 0.4 1 1"/>')
    L.append('    <material name="green" rgba="0.2 1 0.3 1"/>')
    L.append('    <material name="red" rgba="1 0.25 0.25 1"/>')
    L.append('    <material name="orange" rgba="1 0.6 0.1 1"/>')
    L.append('    <material name="purple" rgba="0.7 0.3 1 1"/>')
    # mesh assets (ถ้ามีไฟล์ STL)
    scale = (config.get("meshes") or {}).get("scale", 0.001)
    for name in MESH_PART_NAMES:
        if name in found:
            L.append(f'    <mesh name="{name}" file="{found[name].as_posix()}" '
                     f'scale="{scale} {scale} {scale}"/>')
    L.append('  </asset>')
    L.append('  <worldbody>')
    L.append('    <light directional="true" diffuse="0.6 0.6 0.6" specular="0.2 0.2 0.2" pos="0.5 1 2" dir="0 -1 -1"/>')
    L.append('    <geom name="ground" type="plane" size="1 1 1" material="ground"/>')

    # ---- torso (หมุนตัว) ----
    L.append('    <body name="torso" pos="0 0 0.015">')
    L.append(f'      <joint type="hinge" axis="0 0 1" name="base_joint" range="{-base_deg_max} {base_deg_max}"/>')
    if "base" in found:
        L.append(f'      {_mesh_geom("base", "blue", config)}')
    else:
        L.append('      <geom type="cylinder" size="0.05 0.02" pos="0 0 -0.005" material="blue"/>')
    if "lower_plate" in found:
        L.append(f'      {_mesh_geom("lower_plate", "blue", config)}')
    else:
        L.append(f'      <geom type="cylinder" size="{base_radius:.6f} 0.008" pos="0 0 {lower_plate_z:.6f}" material="blue"/>')

    # ---- ขา 6 ขา (slide ตามแนวขา) ----
    for i, ((bx, by), d) in enumerate(zip(base_pts, leg_dirs)):
        q = _quat_align_z(d)
        qs = " ".join(f"{v:.6f}" for v in q)
        L.append(f'      <body name="leg{i}" pos="{bx:.6f} {by:.6f} {lower_plate_z:.6f}" quat="{qs}">')
        L.append(f'        <joint type="slide" axis="0 0 1" name="leg{i}" range="-0.2 0.2"/>')
        if "leg" in found:
            L.append(f'        {_mesh_geom("leg", "red", config)}')
        else:
            L.append(f'        <geom type="capsule" fromto="0 0 0 0 0 {leg_home:.6f}" size="0.007" material="red"/>')
        L.append('      </body>')
    L.append('  </body>')  # ปิด torso

    # ---- จานบน + หัว (free joint ระดับ worldbody; หมุนตาม base โดยโค้ด) ----
    L.append(f'    <body name="top" pos="0 0 {lower_plate_z:.6f}">')
    L.append('      <joint type="free" name="top_free"/>')
    if "top" in found:
        L.append(f'      {_mesh_geom("top", "green", config)}')
    else:
        L.append(f'      <geom type="cylinder" size="{top_radius:.6f} 0.012" pos="0 0 0.01" material="green"/>')
    L.append('      <body name="head" pos="0 0 0.06">')
    if "head" in found:
        L.append(f'        {_mesh_geom("head", "purple", config)}')
    else:
        L.append(f'        <geom type="sphere" size="{head_radius:.6f}" material="purple"/>')
    L.append('        <site name="camera" pos="0 0.04 0.02" size="0.008" rgba="0.2 0.9 1 1"/>')
    for side, name in ((-1.0, "antenna_L"), (1.0, "antenna_R")):
        L.append(f'        <body name="{name}" pos="0 {side * 0.03:.3f} {head_radius + 0.01:.3f}">')
        L.append(f'          <joint type="hinge" axis="0 0 1" name="{name}_joint" range="-2 2"/>')
        if "antenna" in found:
            L.append(f'          {_mesh_geom("antenna", "orange", config)}')
        else:
            L.append(f'          <geom type="capsule" fromto="0 0 0 0 {side * antenna_len:.4f} 0" size="0.006" material="orange"/>')
        L.append('        </body>')
    L.append('      </body>')
    L.append('    </body>')
    L.append('  </worldbody>')
    L.append('</mujoco>')
    return "\n".join(L)


# ===========================================================================
# 🎨 หุ่นคู่: หน้าต่างเดียว 2 ตัว (A = เขียว · B = ขาว) หันหน้าเข้าหากัน
#    หมายเหตุ: ฟังก์ชันด้านล่าง "mirror" โครงสร้างของ build_mjcf() ข้างบน
#    แต่เพิ่ม prefix ให้ชื่อ body/joint + origin + ชุดสีต่อหุ่น
#    (จงใจไม่แก้ build_mjcf เดิม เพื่อไม่กระทบหุ่นเดี่ยว/self_test)
# ===========================================================================

PAIR_PALETTES = {
    "green": {                      # พี่ทด
        "base": "0.10 0.55 0.22 1",
        "lower_plate": "0.12 0.68 0.30 1",
        "leg": "0.35 0.85 0.45 1",
        "top": "0.15 0.75 0.30 1",
        "head": "0.45 0.90 0.55 1",
        "antenna": "0.80 0.95 0.40 1",
    },
    "white": {                      # น้องนุ
        "base": "0.90 0.90 0.88 1",
        "lower_plate": "0.95 0.95 0.93 1",
        "leg": "0.82 0.82 0.82 1",
        "top": "0.97 0.97 0.95 1",
        "head": "1.0 1.0 0.98 1",
        "antenna": "0.88 0.88 0.88 1",
    },
}


def build_mjcf_pair(config_a, config_b) -> str:
    """MJCF หน้าต่างเดียว 2 หุ่น — A เขียว (x −0.16) · B ขาว (x +0.16)"""
    specs = [
        {"prefix": "a_", "origin": (-0.16, 0.0), "palette": PAIR_PALETTES["green"]},
        {"prefix": "b_", "origin": (0.16, 0.0), "palette": PAIR_PALETTES["white"]},
    ]
    st = config_a["stewart"]
    found = _resolve_meshes(config_a)
    lim = config_a["limits"]
    base_radius = _mm(st["base_radius"])
    top_radius = _mm(st["top_radius"])
    lower_plate_z = _mm(st.get("base_plate_z", 80.0))
    z_home = st["z_home"]
    head_radius = _mm(25.0)
    antenna_len = _mm(45.0)
    base_deg_max = abs(lim["base_deg"][1])

    base_arr, top_arr = leg_endpoints(
        st["z_home"], 0.0, 0.0, 0.0,
        st["base_radius"], st["top_radius"],
        st.get("top_offset_deg", 30.0), st.get("layout", "paired"),
    )
    base_pts = [(x * 0.001, y * 0.001) for x, y in base_arr[:2].T]
    top_pts = [(x * 0.001, y * 0.001) for x, y in top_arr[:2].T]
    leg_dirs, leg_home = [], None
    for (bx, by), (tx, ty) in zip(base_pts, top_pts):
        d = np.array([tx - bx, ty - by, _mm(z_home)])
        leg_home = float(np.linalg.norm(d))
        leg_dirs.append(d / leg_home)

    L = []
    L.append('<mujoco model="Reachy Mini DIY x2">')
    L.append('  <compiler angle="radian" coordinate="local"/>')
    L.append('  <option timestep="0.002"/>')
    L.append('  <visual><global azimuth="140" elevation="-20"/></visual>')
    L.append('  <asset>')
    L.append('    <texture type="skybox" builtin="gradient" rgb1="0.2 0.3 0.5" rgb2="0 0 0" width="512" height="512"/>')
    L.append('    <texture type="2d" name="ground" builtin="checker" rgb1="0.25 0.3 0.35" rgb2="0.15 0.2 0.25" width="300" height="300"/>')
    L.append('    <material name="ground" texture="ground" texuniform="true" texrepeat="8 8" reflectance="0.2"/>')
    # วัสดุแยกต่อหุ่น (ชื่อนำหน้าด้วย prefix)
    for spec in specs:
        p = spec["prefix"]
        for part, rgba in spec["palette"].items():
            L.append(f'    <material name="{p}{part}" rgba="{rgba}"/>')
    scale = (config_a.get("meshes") or {}).get("scale", 0.001)
    for name in MESH_PART_NAMES:
        if name in found:
            L.append(f'    <mesh name="{name}" file="{found[name].as_posix()}" '
                     f'scale="{scale} {scale} {scale}"/>')
    L.append('  </asset>')
    L.append('  <worldbody>')
    L.append('    <light directional="true" diffuse="0.6 0.6 0.6" specular="0.2 0.2 0.2" pos="0.5 1 2" dir="0 -1 -1"/>')
    L.append('    <geom name="ground" type="plane" size="1 1 1" material="ground"/>')

    for spec in specs:
        p = spec["prefix"]
        ox, oy = spec["origin"]
        # ---- torso ----
        L.append(f'    <body name="{p}torso" pos="{ox:.3f} {oy:.3f} 0.015">')
        L.append(f'      <joint type="hinge" axis="0 0 1" name="{p}base_joint" range="{-base_deg_max} {base_deg_max}"/>')
        if "base" in found:
            L.append(f'      {_mesh_geom("base", f"{p}base", config_a)}')
        else:
            L.append(f'      <geom type="cylinder" size="0.05 0.02" pos="0 0 -0.005" material="{p}base"/>')
        if "lower_plate" in found:
            L.append(f'      {_mesh_geom("lower_plate", f"{p}lower_plate", config_a)}')
        else:
            L.append(f'      <geom type="cylinder" size="{base_radius:.6f} 0.008" pos="0 0 {lower_plate_z:.6f}" material="{p}lower_plate"/>')
        # ---- ขา 6 ขา ----
        for i, ((bx, by), d) in enumerate(zip(base_pts, leg_dirs)):
            q = _quat_align_z(d)
            qs = " ".join(f"{v:.6f}" for v in q)
            L.append(f'      <body name="{p}leg{i}" pos="{bx:.6f} {by:.6f} {lower_plate_z:.6f}" quat="{qs}">')
            L.append(f'        <joint type="slide" axis="0 0 1" name="{p}leg{i}" range="-0.2 0.2"/>')
            if "leg" in found:
                L.append(f'        {_mesh_geom("leg", f"{p}leg", config_a)}')
            else:
                L.append(f'        <geom type="capsule" fromto="0 0 0 0 0 {leg_home:.6f}" size="0.007" material="{p}leg"/>')
            L.append('      </body>')
        L.append('    </body>')  # ปิด torso

        # ---- จานบน + หัว ----
        L.append(f'    <body name="{p}top" pos="{ox:.3f} {oy:.3f} {lower_plate_z:.6f}">')
        L.append(f'      <joint type="free" name="{p}top_free"/>')
        if "top" in found:
            L.append(f'      {_mesh_geom("top", f"{p}top", config_a)}')
        else:
            L.append(f'      <geom type="cylinder" size="{top_radius:.6f} 0.012" pos="0 0 0.01" material="{p}top"/>')
        L.append(f'      <body name="{p}head" pos="0 0 0.06">')
        if "head" in found:
            L.append(f'        {_mesh_geom("head", f"{p}head", config_a)}')
        else:
            L.append(f'        <geom type="sphere" size="{head_radius:.6f}" material="{p}head"/>')
        L.append(f'        <site name="{p}camera" pos="0 0.04 0.02" size="0.008" rgba="0.2 0.9 1 1"/>')
        for side, name in ((-1.0, "antenna_L"), (1.0, "antenna_R")):
            L.append(f'        <body name="{p}{name}" pos="0 {side * 0.03:.3f} {head_radius + 0.01:.3f}">')
            L.append(f'          <joint type="hinge" axis="0 0 1" name="{p}{name}_joint" range="-2 2"/>')
            if "antenna" in found:
                L.append(f'          {_mesh_geom("antenna", f"{p}antenna", config_a)}')
            else:
                L.append(f'          <geom type="capsule" fromto="0 0 0 0 {side * antenna_len:.4f} 0" size="0.006" material="{p}antenna"/>')
            L.append('        </body>')
        L.append('      </body>')
        L.append('    </body>')

    L.append('  </worldbody>')
    L.append('</mujoco>')
    return "\n".join(L)


class MuJoCoPair:
    """หน้าต่าง MuJoCo เดียวที่มีหุ่น 2 ตัว — A เขียว (พี่ทด) · B ขาว (น้องนุ)

    หันหน้าเข้าหากัน (A เอียง +90° ไปทาง +X, B −90° ไปทาง −X)
    """

    PREFIX = {"a": "a_", "b": "b_"}
    ORIGIN = {"a": (-0.16, 0.0), "b": (0.16, 0.0)}
    BASE_OFFSET = {"a": -90.0, "b": 90.0}   # องศา — ให้หันเข้าหากัน

    def __init__(self, config, show=True):
        self.config = config
        self.st = config["stewart"]
        self.lower_plate_z = _mm(self.st.get("base_plate_z", 80.0))

        xml = build_mjcf_pair(config, config)
        self.model = mujoco.MjModel.from_xml_string(xml)
        self.data = mujoco.MjData(self.model)

        home_base, home_top = leg_endpoints(
            self.st["z_home"], 0.0, 0.0, 0.0,
            self.st["base_radius"], self.st["top_radius"],
            self.st.get("top_offset_deg", 30.0), self.st.get("layout", "paired"),
        )
        self.leg_home_mm = float(np.linalg.norm(home_top[:, 0] - home_base[:, 0]))

        self.qpos_adr = {}
        for i in range(self.model.njnt):
            name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_JOINT, i)
            if name:
                self.qpos_adr[name] = self.model.jnt_qposadr[i]

        self.viewer = None
        if show:
            self._launch_viewer()

    def _launch_viewer(self):
        try:
            self.viewer = mujoco.viewer.launch_passive(self.model, self.data)
            print("[MuJoCo] เปิดหน้าต่าง 3D 2 หุ่น (A เขียว / B ขาว) — ลากหมุน / scroll ซูม")
        except Exception as exc:  # noqa: BLE001 - headless ได้
            print(f"[MuJoCo] เปิด viewer ไม่ได้ ({exc}) — รันแบบ headless")
            self.viewer = None

    def _apply(self, which: str, state):
        """เขียน qpos ของหุ่นตัว which ('a'/'b') จาก state แล้ว sync"""
        d = self.data
        p = self.PREFIX[which]
        ox, oy = self.ORIGIN[which]
        head = state["head"]
        base_deg = state["base"] + self.BASE_OFFSET[which]

        d.qpos[self.qpos_adr[f"{p}base_joint"]] = math.radians(base_deg)

        z_m = _mm(head["z"]) + self.lower_plate_z
        roll = math.radians(head["roll"])
        pitch = math.radians(head["pitch"])
        yaw = math.radians(head["yaw"])
        q_rel = _quat_from_rpy(roll, pitch, yaw)
        q_world = _quat_mul(_quat_z(math.radians(base_deg)), q_rel)
        addr = self.qpos_adr[f"{p}top_free"]
        d.qpos[addr:addr + 3] = [ox, oy, z_m]
        d.qpos[addr + 3:addr + 7] = q_world

        lengths = leg_lengths(
            head["z"], roll, pitch, yaw,
            self.st["base_radius"], self.st["top_radius"],
            self.st.get("top_offset_deg", 30.0), self.st.get("layout", "paired"),
        )
        for i, length in enumerate(lengths):
            d.qpos[self.qpos_adr[f"{p}leg{i}"]] = (length - self.leg_home_mm) / 1000.0

        d.qpos[self.qpos_adr[f"{p}antenna_L_joint"]] = state["antennas"][0]
        d.qpos[self.qpos_adr[f"{p}antenna_R_joint"]] = state["antennas"][1]

        mujoco.mj_forward(self.model, d)
        if self.viewer is not None:
            self.viewer.sync()

    def update_a(self, state):
        self._apply("a", state)

    def update_b(self, state):
        self._apply("b", state)

    def close(self):
        if self.viewer is not None:
            try:
                self.viewer.close()
            except Exception:  # noqa: BLE001
                pass
            self.viewer = None

    def wait_until_closed(self):
        if self.viewer is None:
            return
        try:
            while self.viewer.is_running():
                time.sleep(0.1)
        except Exception:  # noqa: BLE001
            time.sleep(0.5)


class _PairViewAdapter:
    """อแดปเตอร์ให้ SimRobot เรียก viewer.update(state) แบบหุ่นเดี่ยวได้"""

    def __init__(self, pair: MuJoCoPair, which: str):
        self._pair = pair
        self._which = which

    def update(self, state):
        getattr(self._pair, f"update_{self._which}")(state)

    def close(self):
        self._pair.close()          # idempotent — หุ่นตัวที่สองปิดซ้ำได้

    def wait_until_closed(self):
        self._pair.wait_until_closed()


def create_pair_viewers(config, show=True):
    """สร้างหน้าต่าง 2 หุ่น → คืน (viewer_A, viewer_B) สำหรับ Robot(..., viewer=...)"""
    pair = MuJoCoPair(config, show=show)
    return _PairViewAdapter(pair, "a"), _PairViewAdapter(pair, "b")


class MuJoCoSim:
    """จำลองหุ่น DIY ใน MuJoCo — ขับ qpos โดยตรง (kinematic) จาก IK จริง"""

    def __init__(self, config, show=True):
        self.config = config
        self.st = config["stewart"]
        self.lower_plate_z = _mm(self.st.get("base_plate_z", 80.0))

        xml = build_mjcf(config)
        self.model = mujoco.MjModel.from_xml_string(xml)
        self.data = mujoco.MjData(self.model)

        found = _resolve_meshes(config)
        if found:
            print("[MuJoCo] ใช้ STL mesh: " + ", ".join(sorted(found)))
        else:
            print("[MuJoCo] ไม่พบไฟล์ STL — ใช้รูปทรงพื้นฐาน "
                  "(วาง STL ใน models/stl/ แล้วตั้ง meshes.enabled=True)")

        # ความยาวขา home จริง (จากเรขาคณิต)
        home_base, home_top = leg_endpoints(
            self.st["z_home"], 0.0, 0.0, 0.0,
            self.st["base_radius"], self.st["top_radius"],
            self.st.get("top_offset_deg", 30.0), self.st.get("layout", "paired"),
        )
        self.leg_home_mm = float(np.linalg.norm(home_top[:, 0] - home_base[:, 0]))

        # qpos address ของ joint
        self.qpos_adr = {}
        for i in range(self.model.njnt):
            name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_JOINT, i)
            if name:
                self.qpos_adr[name] = self.model.jnt_qposadr[i]

        self.viewer = None
        if show:
            self._launch_viewer()

    def _launch_viewer(self):
        try:
            self.viewer = mujoco.viewer.launch_passive(self.model, self.data)
            print("[MuJoCo] เปิดหน้าต่าง 3D viewer แล้ว (ลากหมุน / scroll ซูม)")
        except Exception as exc:  # noqa: BLE001 - headless ได้
            print(f"[MuJoCo] เปิด viewer ไม่ได้ ({exc}) — รันแบบ headless")
            self.viewer = None

    def update(self, state):
        """อัปเดตท่าหุ่นจาก state (เหมือน SimRobot)"""
        d = self.data
        head = state["head"]

        # ฐาน (หมุนตัว)
        d.qpos[self.qpos_adr["base_joint"]] = math.radians(state["base"])

        # จานบน: ตำแหน่ง + มุม (IK จริง) — top อยู่ระดับ world จึงประกอบมุม base
        z_m = _mm(head["z"]) + self.lower_plate_z
        roll = math.radians(head["roll"])
        pitch = math.radians(head["pitch"])
        yaw = math.radians(head["yaw"])
        q_rel = _quat_from_rpy(roll, pitch, yaw)
        q_world = _quat_mul(_quat_z(math.radians(state["base"])), q_rel)
        addr = self.qpos_adr["top_free"]
        d.qpos[addr:addr + 3] = [0.0, 0.0, z_m]
        d.qpos[addr + 3:addr + 7] = q_world

        # ขา 6 ขา: ยาวจาก IK -> slide qpos
        lengths = leg_lengths(
            head["z"], roll, pitch, yaw,
            self.st["base_radius"], self.st["top_radius"],
            self.st.get("top_offset_deg", 30.0), self.st.get("layout", "paired"),
        )
        for i, length in enumerate(lengths):
            d.qpos[self.qpos_adr[f"leg{i}"]] = (length - self.leg_home_mm) / 1000.0

        # เสาอากาศ
        d.qpos[self.qpos_adr["antenna_L_joint"]] = state["antennas"][0]
        d.qpos[self.qpos_adr["antenna_R_joint"]] = state["antennas"][1]

        mujoco.mj_forward(self.model, d)
        if self.viewer is not None:
            self.viewer.sync()

    def render_offscreen(self, width=640, height=480):
        """render ภาพลง numpy array (ใช้เทสต์ headless)"""
        from mujoco import Renderer

        renderer = Renderer(self.model, height=height, width=width)
        try:
            renderer.update_scene(self.data)
            return renderer.render()
        finally:
            renderer.close()

    def close(self):
        if self.viewer is not None:
            self.viewer.close()
            self.viewer = None

    def wait_until_closed(self):
        """รอจนกว่าผู้ใช้ปิดหน้าต่าง viewer (ใช้ hold หน้าต่างไว้ดู)"""
        if self.viewer is None:
            return
        try:
            while self.viewer.is_running():
                time.sleep(0.1)
        except Exception:  # noqa: BLE001 - ถ้า is_running ไม่มี ให้รอสักครู่แล้วคืน
            time.sleep(0.5)
