# -*- coding: utf-8 -*-
"""ตั้งหุ่นจริงให้อยู่ "ท่าตรง / center home" — หัวระดับ + **ฐานกลับศูนย์กลาง (0°)**

    .venv\\Scripts\\python.exe scripts\\two_robots_neutral.py
    .venv\\Scripts\\python.exe scripts\\two_robots_neutral.py --head-only    # ไม่แตะฐาน
    .venv\\Scripts\\python.exe scripts\\two_robots_neutral.py --one a --speed 300

ฐาน: pos 2048 = 0° (ศูนย์กลาง) ตาม `set_base(0)` ใน src/robot.py
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_two_robots_poses import open_robots  # noqa: E402

BASE_CENTER = 2048          # 0° = กลาง


def main():
    ap = argparse.ArgumentParser(description="ตั้งท่าตรง + ฐานกลับศูนย์กลาง")
    ap.add_argument("--one", choices=["a", "b", "both"], default="both")
    ap.add_argument("--speed", type=int, default=400,
                    help="ความเร็ว servo (400 = ช้า ปลอดภัยตอนหมุนฐานไกล)")
    ap.add_argument("--head-only", action="store_true",
                    help="ตั้งเฉพาะหัว ไม่หมุนฐานกลับศูนย์กลาง")
    args = ap.parse_args()

    robots = open_robots(args.one)
    try:
        # 1) หัว -> ระดับ
        for _name, r in robots:
            z = r.config["stewart"]["z_home"]
            r.head.set_pose(z, 0.0, 0.0, 0.0, speed=args.speed)

        # 2) ฐาน -> ศูนย์กลาง (2048 = 0°)
        max_delta = 0.0
        if not args.head_only:
            for name, r in robots:
                sid = r.config["servo_ids"]["base"]
                cur = r._bus.get_position(sid) or BASE_CENTER
                delta_deg = (BASE_CENTER - cur) * 360.0 / 4096.0
                delta_deg = (delta_deg + 180.0) % 360.0 - 180.0    # ทางสั้นสุด
                max_delta = max(max_delta, abs(delta_deg))
                r._bus.set_position(sid, BASE_CENTER, speed=args.speed)
                print(f"{name}: ฐาน {cur} -> {BASE_CENTER} ({delta_deg:+.1f}°)")
            # หมุนไกลต้องรอนานขึ้น (วัดจริง: 178° ที่ speed 400 ใช้ ~5 วิ)
            time.sleep(max(2.5, max_delta / 60.0 + 1.5))

        time.sleep(0.8)
        for name, r in robots:
            st = r.config["stewart"]
            head_now = [r._bus.get_position(s) for s in r.config["servo_ids"]["head"]]
            base_now = r._bus.get_position(r.config["servo_ids"]["base"]) or BASE_CENTER
            rel_deg = (base_now - BASE_CENTER) * 360.0 / 4096.0   # 0° = ตรงกลาง
            rel_deg = (rel_deg + 180.0) % 360.0 - 180.0
            print(f"{name}: หัวต่างจาก home: "
                  f"{[n - h for n, h in zip(head_now, st['leg_home_pos'])]}"
                  f" | ฐาน pos={base_now} = {rel_deg:+.1f}° จากศูนย์กลาง")
        print("ท่าตรง (center home) ✅")
    finally:
        for _name, r in robots:
            r.close()


if __name__ == "__main__":
    main()
