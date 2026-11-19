# -*- coding: utf-8 -*-
"""MuJoCo 2 หุ่น Reachy Mini (โมเดลทางการ) — **รันใน .venv ได้** ไม่ต้องใช้ official SDK

ใช้เฉพาะ:
  - models/reachy_mini/mjcf/reachy_mini.xml + assets/*.stl  (คัดลอกจาก official description)
  - models/reachy_mini/poses.json                            (ท่าหัวที่ export จาก IK ทางการ)

    .venv\\Scripts\\python.exe scripts\\run_two_robots_model.py
    .venv\\Scripts\\python.exe scripts\\run_two_robots_model.py --facing each-other

ค่าเริ่มต้น `--facing viewer` = หันหน้าเข้าจอผู้ชม (พี่ทดซ้าย · น้องนุขวา)
ถ้าต้องการท่าที่คำนวณสดด้วย IK ทางการทั้งหมด (ไม่ผ่าน poses.json)
ให้ใช้ scripts\\run_two_robots_official.py ใน reachy_mini_env แทน
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import mujoco
import mujoco.viewer
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
XML = ROOT / "models" / "reachy_mini" / "mjcf" / "reachy_mini.xml"
POSES_JSON = ROOT / "models" / "reachy_mini" / "poses.json"

GREEN_RGBA = np.array([0.10, 0.60, 0.25, 1.0])
WHITE_RGBA = np.array([0.95, 0.95, 0.92, 1.0])

# ลำดับท่าทาง: (ชื่อท่า, เวลาค้าง) — ผลัดกันขยับเหมือนคุยกัน
SEQ_A = [("neutral", 0.6), ("look_left", 1.1), ("nod", 0.5),
         ("look_up", 0.9), ("tilt_left", 0.9), ("neutral", 1.2)]
SEQ_B = [("neutral", 0.9), ("nod", 0.6), ("look_right", 1.1),
         ("lift", 0.7), ("tilt_right", 0.9), ("look_down", 0.7)]

# มุมกล้อง: viewer = กล้องอยู่ฝั่ง +X ตรงหน้าหุ่น (หุ่นหันหน้า +X) · เอียง 10° ให้มีมิติ
CAM = {
    "viewer": dict(azimuth=10.0, elevation=-14.0, distance=1.05, lookat=[0.0, 0.0, 0.18]),
    "each-other": dict(azimuth=160.0, elevation=-18.0, distance=1.0, lookat=[0.0, 0.0, 0.2]),
}

SPACING = 0.20            # ระยะซ้าย/ขวา ±0.20 m → หุ่นห่างกัน 0.40 m
TURN_RAD = 1.05           # หมุนตัว 60° ไปหาคู่สนทนา
TURN_SIGN = {"a_": +1.0, "b_": -1.0}      # A หันไป +Y (หา B) · B หันไป −Y (หา A)
TURN_POSE = {"a_": "look_left", "b_": "look_right"}
TURN_SCHEDULE = {"a_": (2.0, 2.8), "b_": (7.0, 2.8)}   # (วินาทีเริ่ม, ระยะเวลาค้าง)
TURN_PERIOD = 12.5


def _load_colored(rgba, xml: Path = XML):
    """โหลดสเปกหุ่น แล้วย้อมวัสดุทั้งหมดเป็นสีเดียว"""
    if not xml.exists():
        raise FileNotFoundError(f"ไม่พบโมเดล: {xml}")
    spec = mujoco.MjSpec.from_file(str(xml))
    for mat in spec.materials:
        mat.rgba = rgba
    return spec


def build_scene(xml: Path = XML, facing: str = "viewer"):
    """ซีน: พื้น + แสง + หุ่น 2 ตัว

    facing="viewer"     → หันหน้าเข้าจอผู้ชม: A เขียว (y−0.16 = ซ้าย) · B ขาว (y+0.16 = ขวา)
    facing="each-other" → หันเข้าหากัน: A ที่ x−0.16 · B ที่ x+0.16 (หมุน 180°)
    """
    scene = mujoco.MjSpec()
    scene.worldbody.add_geom(
        name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE,
        size=[1.0, 1.0, 0.05], rgba=[0.25, 0.30, 0.35, 1.0])
    scene.worldbody.add_light(
        name="key", pos=[0.0, 0.0, 3.5], dir=[0.0, 0.0, -1.0],
        type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL)

    if facing == "each-other":
        # หุ่นทางการหันหน้า +X → A หันไปหา B, B หมุน 180° หา A
        pos_a, quat_a = [-0.16, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]
        pos_b, quat_b = [0.16, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]
    else:
        # หันหน้าเข้าจอผู้ชม: ยืนคู่ขนานกัน (กล้องอยู่ฝั่ง +X) — ห่างกัน 2×SPACING
        pos_a, quat_a = [0.0, -SPACING, 0.0], [1.0, 0.0, 0.0, 0.0]
        pos_b, quat_b = [0.0, SPACING, 0.0], [1.0, 0.0, 0.0, 0.0]

    fa = scene.worldbody.add_frame(name="a_origin", pos=pos_a, quat=quat_a)
    scene.attach(_load_colored(GREEN_RGBA, xml), prefix="a_", frame=fa)
    fb = scene.worldbody.add_frame(name="b_origin", pos=pos_b, quat=quat_b)
    scene.attach(_load_colored(WHITE_RGBA, xml), prefix="b_", frame=fb)
    return scene


def _smooth(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return u * u * (3.0 - 2.0 * u)


def turn_weight(t: float, start: float, dur: float,
                period: float = TURN_PERIOD, ramp: float = 0.7) -> float:
    """0..1 = ระดับการหันไปหาคู่สนทนา (ขึ้น→ค้าง→ลง แบบนุ่มนวล)"""
    u = (t - start) % period
    if u >= dur:
        return 0.0
    if u < ramp:
        return _smooth(u / ramp)
    if u > dur - ramp:
        return _smooth((dur - u) / ramp)
    return 1.0


class GesturePlayer:
    """เล่นลำดับท่า (จาก poses.json) แบบ hold → blend → hold วนซ้ำ"""

    def __init__(self, poses: dict, sequence, transition: float = 0.7,
                 offset: float = 0.0, start_pose: str = "neutral"):
        self.transition = transition
        self.offset = offset
        kfs = [(0.0, np.array(poses[start_pose]["ctrl"], dtype=float))]
        t = 0.0
        for i, (name, hold) in enumerate(sequence):
            t += transition + hold
            kfs.append((t, np.array(poses[name]["ctrl"], dtype=float)))
        # กลับมาท่าเริ่มต้นแล้วจบรอบ
        t += transition + 0.4
        kfs.append((t, kfs[0][1]))
        self.kfs = kfs
        self.period = t

    def at(self, t: float) -> np.ndarray:
        tt = (t + self.offset) % self.period
        for i in range(len(self.kfs) - 1):
            t0, v0 = self.kfs[i]
            t1, v1 = self.kfs[i + 1]
            if t0 <= tt < t1:
                dur = t1 - t0
                hold = max(0.0, dur - self.transition)
                local = tt - t0
                if local <= hold:
                    return v0
                u = _smooth((local - hold) / self.transition)
                return v0 * (1.0 - u) + v1 * u
        return self.kfs[-1][1]


def _actuator_ids(model, prefixes=("a_", "b_")):
    ids = {}
    for p in prefixes:
        ids[p] = {}
        for name in ["yaw_body"] + [f"stewart_{i}" for i in range(1, 7)] + \
                    ["right_antenna", "left_antenna"]:
            aid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, f"{p}{name}")
            if aid < 0:
                raise KeyError(f"ไม่พบ actuator: {p}{name}")
            ids[p][name] = aid
    return ids


def main() -> None:
    ap = argparse.ArgumentParser(description="MuJoCo 2 หุ่น Reachy Mini (โมเดลทางการ)")
    ap.add_argument("--facing", choices=["viewer", "each-other"], default="viewer",
                    help="viewer = หันหน้าเข้าจอผู้ชม (ค่าเริ่มต้น) · each-other = หันหน้าเข้าหากัน")
    args = ap.parse_args()

    if not POSES_JSON.exists():
        print(f"❌ ไม่พบ {POSES_JSON}\n   สร้างด้วย: reachy_mini_env\\Scripts\\python.exe scripts\\export_reachy_poses.py")
        sys.exit(1)
    poses = json.loads(POSES_JSON.read_text(encoding="utf-8"))

    model = build_scene(facing=args.facing).compile()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    act = _actuator_ids(model)
    print(f"[model] nbody={model.nbody} nq={model.nq} nu={model.nu} — 2 หุ่นจาก XML+STL ทางการ")

    player_a = GesturePlayer(poses, SEQ_A, offset=0.0)
    player_b = GesturePlayer(poses, SEQ_B, offset=2.3)

    viewer = mujoco.viewer.launch_passive(model, data,
                                          show_left_ui=False, show_right_ui=False)
    cam = CAM[args.facing]
    with viewer.lock():
        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        viewer.cam.distance = cam["distance"]
        viewer.cam.azimuth = cam["azimuth"]
        viewer.cam.elevation = cam["elevation"]
        viewer.cam.lookat[:] = cam["lookat"]
    face_txt = "หันหน้าเข้าจอ" if args.facing == "viewer" else "หันหน้าเข้าหากัน"
    print(f"[model] เปิดหน้าต่างแล้ว — พี่ทด (เขียว) + น้องนุ (ขาว) {face_txt} · ปิดหน้าต่าง/Ctrl+C เพื่อออก")

    t0 = time.time()
    try:
        while viewer.is_running():
            tick = time.time()
            t = tick - t0
            for prefix, player, sway_ph in (("a_", player_a, 0.0), ("b_", player_b, 1.7)):
                q = player.at(t)                     # [yaw, stewart_1..6]
                # จังหวะหันไปมองคู่สนทนา (เฉพาะโหมดหันหน้าเข้าจอ)
                w = turn_weight(t, *TURN_SCHEDULE[prefix]) if args.facing == "viewer" else 0.0
                if w > 0.0:
                    target = np.array(poses[TURN_POSE[prefix]]["ctrl"], dtype=float)
                    q = q * (1.0 - 0.85 * w) + target * (0.85 * w)
                body_yaw = q[0] + 0.10 * math.sin(0.6 * t + sway_ph)
                if w > 0.0:
                    body_yaw += TURN_SIGN[prefix] * TURN_RAD * w
                data.ctrl[act[prefix]["yaw_body"]] = body_yaw
                for i in range(6):
                    data.ctrl[act[prefix][f"stewart_{i + 1}"]] = q[i + 1]
                wig = 0.30 * math.sin(2.4 * t + sway_ph)
                data.ctrl[act[prefix]["right_antenna"]] = wig
                data.ctrl[act[prefix]["left_antenna"]] = -wig
            for _ in range(10):                      # 20 ms @ timestep 0.002
                mujoco.mj_step(model, data)
            viewer.sync()
            time.sleep(max(0.0, 0.04 - (time.time() - tick)))
    except KeyboardInterrupt:
        pass
    finally:
        try:
            viewer.close()
        except Exception:  # noqa: BLE001
            pass
    print("[model] ปิดแล้ว")


if __name__ == "__main__":
    main()
