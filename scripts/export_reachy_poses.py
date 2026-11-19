# -*- coding: utf-8 -*-
"""ส่งออก "ท่าหัว" ของ Reachy Mini (จาก IK ทางการ) เป็น JSON

รันครั้งเดียวด้วย official env (มี analytical IK + rust bindings):
    reachy_mini_env\\Scripts\\python.exe scripts\\export_reachy_poses.py

ผลลัพธ์: models/reachy_mini/poses.json
    { "<ชื่อท่า>": {"ctrl": [yaw, stewart_1..6], "desc": "..."} , ... }
ใช้โดย scripts/run_two_robots_model.py (รันใน .venv ได้ ไม่ต้องมี official SDK)
"""

import json
from pathlib import Path

import numpy as np
from reachy_mini.kinematics.analytical_kinematics import AnalyticalKinematics
from reachy_mini.utils import create_head_pose

OUT = Path(__file__).resolve().parent.parent / "models" / "reachy_mini" / "poses.json"

# ชื่อท่า -> (kwargs ของ create_head_pose: z=mm, roll/pitch/yaw=องศา)
POSES = {
    "neutral":   dict(z=0.0, roll=0.0, pitch=0.0, yaw=0.0),
    "look_left":  dict(z=2.0, roll=0.0, pitch=0.0, yaw=22.0),
    "look_right": dict(z=2.0, roll=0.0, pitch=0.0, yaw=-22.0),
    "look_up":   dict(z=8.0, roll=0.0, pitch=10.0, yaw=0.0),
    "look_down": dict(z=-8.0, roll=0.0, pitch=-12.0, yaw=0.0),
    "tilt_left":  dict(z=2.0, roll=12.0, pitch=0.0, yaw=0.0),
    "tilt_right": dict(z=2.0, roll=-12.0, pitch=0.0, yaw=0.0),
    "nod":       dict(z=-5.0, roll=0.0, pitch=-16.0, yaw=0.0),
    "lift":      dict(z=14.0, roll=0.0, pitch=6.0, yaw=0.0),
}


def main() -> None:
    kin = AnalyticalKinematics(automatic_body_yaw=False)
    out = {}
    for name, kw in POSES.items():
        pose = create_head_pose(mm=True, degrees=True, **kw)
        q = kin.ik(pose, body_yaw=0.0)
        out[name] = {"ctrl": [float(v) for v in np.asarray(q).ravel()],
                     "desc": ", ".join(f"{k}={v}" for k, v in kw.items())}
        print(f"{name:11s} -> {np.round(q, 3)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nเขียนแล้ว: {OUT}")


if __name__ == "__main__":
    main()
