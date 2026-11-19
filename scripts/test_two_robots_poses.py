# -*- coding: utf-8 -*-
"""ทดสอบท่าทางหุ่นจริงทั้งสองตัว (พี่ทด COM4 · น้องนุ COM3)

    .venv\\Scripts\\python.exe scripts\\test_two_robots_poses.py
    .venv\\Scripts\\python.exe scripts\\test_two_robots_poses.py --one a     # เฉพาะพี่ทด
    .venv\\Scripts\\python.exe scripts\\test_two_robots_poses.py --speed 400 --settle 1.2

ทดสอบ: home -> ขึ้น/ลง z -> เงย/ก้ม pitch -> กลับท่ากลาง
อ่าน port/config จาก config/local_config.json + calibration ของแต่ละตัวอัตโนมัติ
"""

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.robot_config import get_config  # noqa: E402
from src.robot import Robot  # noqa: E402


def open_robots(which: str):
    """เปิดหุ่นตามที่เลือก (a / b / both) — คืน list ของ Robot"""
    cfg_a = get_config("a")
    cfg_b = get_config("b")
    robots = []
    if which in ("a", "both"):
        cfg_a.setdefault("antennas", {})["enabled"] = False   # เสาอากาศ 8,9 ไม่ต่อ
        robots.append(("พี่ทด", Robot(backend="hardware", port=cfg_a.get("port"),
                                      config=cfg_a)))
    if which in ("b", "both"):
        cfg_b.setdefault("antennas", {})["enabled"] = False   # น้องนุไม่มีเสาอากาศ
        cfg_b.setdefault("motor", {}).update(cfg_a["robot_b"]["motor"])  # 12V torque limit
        port_b = (cfg_b.get("robot_b") or {}).get("port")
        robots.append(("น้องนุ", Robot(backend="hardware", port=port_b, config=cfg_b)))
    return robots


def main():
    ap = argparse.ArgumentParser(description="ทดสอบท่าทางหุ่นจริง")
    ap.add_argument("--one", choices=["a", "b", "both"], default="both")
    ap.add_argument("--speed", type=int, default=600, help="ความเร็ว servo (0-4095)")
    ap.add_argument("--settle", type=float, default=0.9, help="รอให้นิ่งต่อท่า (วินาที)")
    ap.add_argument("--loops", type=int, default=2, help="จำนวนรอบของแต่ละชุดท่า")
    args = ap.parse_args()

    robots = open_robots(args.one)
    if not robots:
        sys.exit("ไม่มีหุ่นให้ทดสอบ")

    def cmd(z=70.0, roll=0.0, pitch=0.0, yaw=0.0, label=""):
        for _name, r in robots:
            r.head.set_pose(z, math.radians(roll), math.radians(pitch),
                            math.radians(yaw), speed=args.speed)
        time.sleep(args.settle)
        print(f"   {label or f'z={z} r={roll} p={pitch} y={yaw}'}")

    try:
        print(f"[{'+'.join(n for n, _ in robots)}] เริ่มทดสอบ")
        print("1) home"); cmd(z=70, label="home z=70")
        print(f"2) ขึ้น-ลง x{args.loops}")
        for _ in range(args.loops):
            cmd(z=78, label="ขึ้น z=78")
            cmd(z=62, label="ลง  z=62")
        cmd(z=70, label="กลับ 70")
        print(f"3) เงย-ก้ม x{args.loops}")
        for _ in range(args.loops):
            cmd(z=70, pitch=15, label="เงย +15°")
            cmd(z=70, pitch=-15, label="ก้ม -15°")
        cmd(z=70, label="กลับตรง")
        print("เสร็จสิ้น ✅")
    finally:
        for _name, r in robots:
            r.close()


if __name__ == "__main__":
    main()
