# -*- coding: utf-8 -*-
"""MuJoCo 2 หุ่น — ใช้ **โมเดล Reachy Mini ทางการ** (articulated เต็มรูปแบบ)

พี่ทด (A) = สีเขียว · น้องนุ (B) = สีขาว — หันหน้าเข้าหากัน ขยับหัว/เสาแบบมีชีวิต

ต้องรันด้วย Python ของ official SDK (มี reachy_mini + rust kinematics + scipy):
    reachy_mini_env\\Scripts\\python.exe scripts\\run_two_robots_official.py

ปิดหน้าต่างหรือกด Ctrl+C เพื่อออก
"""

import math
import sys
import time
from importlib.resources import files

import mujoco
import mujoco.viewer
import numpy as np
import reachy_mini
from reachy_mini.kinematics.analytical_kinematics import AnalyticalKinematics
from reachy_mini.utils import create_head_pose

MJCF = files(reachy_mini).joinpath(
    "descriptions/reachy_mini/mjcf/reachy_mini.xml")

GREEN_RGBA = np.array([0.10, 0.60, 0.25, 1.0])
WHITE_RGBA = np.array([0.95, 0.95, 0.92, 1.0])

SPACING = 0.20            # ระยะซ้าย/ขวา ±0.20 m → หุ่นห่างกัน 0.40 m
TURN_RAD = 1.05           # หมุนตัว 60° ไปหาคู่สนทนา
TURN_SIGN = {"a_": +1.0, "b_": -1.0}      # A หันไป +Y (หา B) · B หันไป −Y (หา A)
TURN_SCHEDULE = {"a_": (2.0, 2.8), "b_": (7.0, 2.8)}   # (วินาทีเริ่ม, ระยะเวลาค้าง)
TURN_PERIOD = 12.5


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


def _load_colored(rgba):
    """โหลดสเปกหุ่นทางการ แล้วย้อมวัสดุทั้งหมดเป็นสีเดียว (เขียว/ขาว)"""
    spec = mujoco.MjSpec.from_file(str(MJCF))
    for mat in spec.materials:
        mat.rgba = rgba
    return spec


def build_scene(facing: str = "viewer"):
    """ซีน: พื้น + แสง + หุ่น 2 ตัว

    facing="viewer"     → หันหน้าเข้าจอผู้ชม: A (y−0.16 = ซ้าย) · B (y+0.16 = ขวา)
    facing="each-other" → หันเข้าหากัน: A ที่ x−0.16 · B ที่ x+0.16 (หมุน 180°)
    """
    scene = mujoco.MjSpec()
    scene.worldbody.add_geom(
        name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE,
        size=[1.0, 1.0, 0.05], rgba=[0.25, 0.30, 0.35, 1.0])
    scene.worldbody.add_light(
        name="key", pos=[0.0, 0.0, 3.5], dir=[0.0, 0.0, -1.0], directional=True)

    if facing == "each-other":
        pos_a, quat_a = [-0.16, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]
        pos_b, quat_b = [0.16, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]     # B หมุน 180° หา A
    else:
        pos_a, quat_a = [0.0, -SPACING, 0.0], [1.0, 0.0, 0.0, 0.0]   # หันหน้าเข้าจอ
        pos_b, quat_b = [0.0, SPACING, 0.0], [1.0, 0.0, 0.0, 0.0]

    fa = scene.worldbody.add_frame(name="a_origin", pos=pos_a, quat=quat_a)
    scene.attach(_load_colored(GREEN_RGBA), prefix="a_", frame=fa)
    fb = scene.worldbody.add_frame(name="b_origin", pos=pos_b, quat=quat_b)
    scene.attach(_load_colored(WHITE_RGBA), prefix="b_", frame=fb)
    return scene


def main():
    model = build_scene().compile()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    # actuator ids (ชื่อนำหน้าด้วย prefix จาก attach)
    names = []
    for p in ("a_", "b_"):
        names += [f"{p}yaw_body"] + [f"{p}stewart_{i}" for i in range(1, 7)]
        names += [f"{p}right_antenna", f"{p}left_antenna"]
    act = {n: mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, n)
           for n in names}
    missing = [n for n, i in act.items() if i < 0]
    if missing:
        print(f"❌ ไม่พบ actuator: {missing[:5]} ...")
        sys.exit(1)
    print(f"[scene] compiled — nbody={model.nbody} nq={model.nq} "
          f"nu={model.nu} (2 หุ่นทางการ)")

    kin_a = AnalyticalKinematics(automatic_body_yaw=False)
    kin_b = AnalyticalKinematics(automatic_body_yaw=False)

    viewer = mujoco.viewer.launch_passive(
        model, data, show_left_ui=False, show_right_ui=False)
    with viewer.lock():
        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        viewer.cam.distance = 1.05
        viewer.cam.azimuth = 10.0         # กล้องอยู่ฝั่ง +X เอียง 10° ให้มีมิติ
        viewer.cam.elevation = -14.0
        viewer.cam.lookat[:] = [0.0, 0.0, 0.18]
    print("[scene] เปิดหน้าต่างแล้ว — พี่ทด (เขียว) + น้องนุ (ขาว) หันหน้าเข้าจอ · ปิดหน้าต่าง/Ctrl+C เพื่อออก")

    t0 = time.time()
    try:
        while viewer.is_running():
            tick = time.time()
            t = tick - t0
            for prefix, kin, phase in (("a_", kin_a, 0.0), ("b_", kin_b, 2.1)):
                # จังหวะหันไปมองคู่สนทนา (body yaw + head yaw)
                w = turn_weight(t, *TURN_SCHEDULE[prefix])
                body_yaw = TURN_SIGN[prefix] * TURN_RAD * w
                # ท่าหัว sway เบา ๆ + พยักหน้าเป็นจังหวะ + หันไปหาคู่
                pose = create_head_pose(
                    z=3.0 * math.sin(1.0 * t + phase),
                    roll=5.0 * math.sin(1.4 * t + phase),
                    yaw=10.0 * math.sin(0.5 * t + phase) + TURN_SIGN[prefix] * 20.0 * w,
                    mm=True, degrees=True)
                q = kin.ik(pose, body_yaw=body_yaw)     # [yaw, stewart_1..6]
                data.ctrl[act[f"{prefix}yaw_body"]] = q[0]
                for i in range(6):
                    data.ctrl[act[f"{prefix}stewart_{i + 1}"]] = q[i + 1]
                wig = 0.35 * math.sin(2.2 * t + phase)
                data.ctrl[act[f"{prefix}right_antenna"]] = wig
                data.ctrl[act[f"{prefix}left_antenna"]] = -wig
            for _ in range(10):                    # 20 ms @ timestep 0.002
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
    print("[scene] ปิดแล้ว")


if __name__ == "__main__":
    main()
