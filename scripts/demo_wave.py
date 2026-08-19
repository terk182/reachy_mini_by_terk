"""สาธิต: หุ่นทักทาย — ทำงานได้ทั้งโหมดจำลอง (GUI 3D MuJoCo) และหุ่นจริง

วิธีใช้:
    python scripts/demo_wave.py                      # โหมดจำลอง + MuJoCo 3D
    python scripts/demo_wave.py --gui-type matplotlib
    python scripts/demo_wave.py --no-gui             # โหมดจำลอง text
    python scripts/demo_wave.py --hardware           # หุ่นจริง (STS3215)
    python scripts/demo_wave.py --hardware --port COM5
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.robot import Robot  # noqa: E402


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Reachy Mini DIY — ทักทาย")
    parser.add_argument("--hardware", action="store_true", help="ใช้หุ่นจริง (STS3215)")
    parser.add_argument("--port", default=None, help="พอร์ตอนุกรม (เฉพาะ hardware)")
    parser.add_argument("--gui-type", choices=["mujoco", "matplotlib"],
                        default="mujoco", help="engine หน้าต่าง 3D (โหมดจำลอง)")
    parser.add_argument("--no-gui", action="store_true", help="ไม่แสดงหน้าต่าง 3D")
    args = parser.parse_args()

    backend = "hardware" if args.hardware else "sim"
    gui = False if (args.no_gui or backend == "hardware") else args.gui_type
    with Robot(backend=backend, port=args.port, gui=gui) as robot:
        robot.wake_up()
        robot.wave()
        robot.look_around()
        robot.wake_up()
    print("เสร็จสิ้น ✅")


if __name__ == "__main__":
    main()
