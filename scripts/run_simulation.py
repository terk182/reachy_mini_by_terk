"""รันโหมดจำลอง: แสดงท่าทางต่างๆ ในหน้าต่าง 3D (MuJoCo) โดยไม่ต้องใช้ฮาร์ดแวร์

วิธีใช้:
    python scripts/run_simulation.py                     # MuJoCo 3D (default)
    python scripts/run_simulation.py --hold              # ค้างหน้าต่างไว้ดูจนกว่าจะปิด
    python scripts/run_simulation.py --gui-type matplotlib
    python scripts/run_simulation.py --no-gui            # แบบ text เท่านั้น
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.robot import Robot  # noqa: E402


def main():
    import argparse

    parser = argparse.ArgumentParser(description="รันโหมดจำลอง Reachy Mini DIY")
    parser.add_argument("--gui-type", choices=["mujoco", "matplotlib"],
                        default="mujoco", help="engine สำหรับหน้าต่าง 3D")
    parser.add_argument("--no-gui", action="store_true", help="ไม่แสดงหน้าต่าง 3D")
    parser.add_argument("--hold", action="store_true",
                        help="ค้างหน้าต่างไว้ดูจนกว่าจะปิด")
    args = parser.parse_args()

    gui = False if args.no_gui else args.gui_type
    with Robot(backend="sim", gui=gui) as robot:
        robot.wake_up()
        robot.look_around()
        robot.wave()
        robot.wake_up()
        if args.hold:
            robot.hold()
    print("จำลองเสร็จสิ้น ✅")


if __name__ == "__main__":
    main()
