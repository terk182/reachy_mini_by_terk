"""เปิด MuJoCo หน้าต่างเดียว 2 หุ่น — พี่ทดสีเขียว · น้องนุสีขาว (ไม่มี GUI แชท)

ใช้:
    .venv\\Scripts\\python.exe scripts\\run_two_robots.py --hold

--hold = ค้างหน้าต่างไว้จนกว่าจะปิด / กด Ctrl+C
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.robot_config import get_config  # noqa: E402
from src.mujoco_sim import create_pair_viewers  # noqa: E402
from src.robot import Robot  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="MuJoCo 2 หุ่น (เขียว/ขาว)")
    ap.add_argument("--hold", action="store_true",
                    help="ค้างหน้าต่างไว้จนปิด/Ctrl+C")
    args = ap.parse_args()

    cfg = get_config()
    name_a = (cfg.get("robot") or {}).get("name", "พี่ทด")
    name_b = (cfg.get("robot_b") or {}).get("name", "น้องนุ")

    view_a, view_b = create_pair_viewers(cfg)
    robot_a = Robot(backend="sim", viewer=view_a)
    robot_b = Robot(backend="sim", viewer=view_b)

    print(f"[demo] {name_a} (สีเขียว) + {name_b} (สีขาว) — หันหน้าเข้าหากัน")
    robot_a.wake_up()
    robot_b.wake_up()

    # ทักทายกันเบา ๆ ให้เห็นว่าขยับได้
    robot_a.set_base(-15, duration=0.6)
    robot_b.set_base(15, duration=0.6)
    robot_a.set_antennas(0.7, -0.7, duration=0.5)
    robot_b.set_antennas(-0.7, 0.7, duration=0.5)
    time.sleep(1.0)
    robot_a.set_antennas(0, 0, duration=0.4)
    robot_b.set_antennas(0, 0, duration=0.4)
    robot_a.set_head_pose(roll=8, duration=0.5)
    robot_b.set_head_pose(roll=-8, duration=0.5)
    time.sleep(0.8)
    robot_a.set_head_pose(roll=0, duration=0.5)
    robot_b.set_head_pose(roll=0, duration=0.5)
    robot_a.set_base(0, duration=0.5)
    robot_b.set_base(0, duration=0.5)

    if args.hold:
        print("[demo] หน้าต่างเปิดค้างอยู่ — ลากหมุน/ซูมได้ · ปิดหน้าต่างหรือ Ctrl+C เพื่อออก")
        try:
            while True:
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass

    robot_a.close()
    robot_b.close()
    print("[demo] ปิดแล้ว")


if __name__ == "__main__":
    main()
