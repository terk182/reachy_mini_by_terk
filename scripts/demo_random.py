r"""สุ่มท่าทางหุ่น Reachy Mini (random poses)

สุ่มท่าภายใน safety limits จาก config แล้วสั่งหุ่นวนไปเรื่อย ๆ
ใช้ได้ 3 โหมด:
  - DIY sim      : .venv\Scripts\python.exe scripts\demo_random.py
  - หุ่น STS3215  : .venv\Scripts\python.exe scripts\demo_random.py --hardware
  - daemon ทางการ : .venv\Scripts\python.exe scripts\demo_random.py --real

วิธีใช้:
  .venv\Scripts\python.exe scripts\demo_random.py --real --forever
  .venv\Scripts\python.exe scripts\demo_random.py --n 20 --interval 0.5
  .venv\Scripts\python.exe scripts\demo_random.py --seed 42
"""

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.robot_config import get_config  # noqa: E402


def build_robot(args):
    """สร้าง robot ตาม flag: --real (daemon) / --hardware (STS3215) / sim"""
    if args.real:
        from src.real_robot import RealRobot

        if not RealRobot.available():
            raise SystemExit(
                "⚠️ daemon ไม่พร้อม — รัน official daemon ก่อน เช่น "
                "reachy_mini_env\\Scripts\\reachy-mini-daemon.exe --sim")
        print("[demo_random] สั่งผ่าน official daemon (Reachy Mini แท้)")
        return RealRobot()

    from src.robot import Robot

    backend = "hardware" if args.hardware else "sim"
    gui = args.gui if not args.hardware else False
    if args.hardware:
        print("[demo_random] สั่ง STS3215 จริง (hardware)")
    else:
        print(f"[demo_random] DIY sim (gui={gui})")
    return Robot(backend=backend, port=args.port, gui=gui)


def random_pose(rng, limits):
    """สุ่มท่าหนึ่งท่าจากขีดจำกัด config"""
    return (
        rng.uniform(*limits["head_z_mm"]),      # z (mm)
        rng.uniform(*limits["head_roll_deg"]),  # roll (°)
        rng.uniform(*limits["head_pitch_deg"]), # pitch (°)
        rng.uniform(*limits["head_yaw_deg"]),   # yaw (°)
        rng.uniform(*limits["base_deg"]),       # base (°)
        rng.uniform(*limits["antenna_rad"]),    # antenna left (rad)
        rng.uniform(*limits["antenna_rad"]),    # antenna right (rad)
    )


def main():
    parser = argparse.ArgumentParser(description="สุ่มท่าทางหุ่น Reachy Mini")
    parser.add_argument("--real", action="store_true",
                        help="สั่งผ่าน official daemon (sim แท้)")
    parser.add_argument("--hardware", action="store_true",
                        help="หุ่น STS3215 จริง (ผ่าน ServoBus)")
    parser.add_argument("--port", default=None, help="พอร์ตอนุกรม (hardware)")
    parser.add_argument("--gui", default=False, nargs="?",
                        const="mujoco", help="เปิด GUI สำหรับ DIY sim (mujoco/matplotlib)")
    parser.add_argument("--n", type=int, default=10, help="จำนวนท่า (default 10)")
    parser.add_argument("--forever", action="store_true",
                        help="รันไม่รู้จบจน Ctrl+C")
    parser.add_argument("--interval", type=float, default=0.3,
                        help="วินาทีเพิ่มระหว่างท่า (default 0.3)")
    parser.add_argument("--seed", type=int, default=None, help="seed random")
    args = parser.parse_args()

    cfg = get_config()
    limits = cfg["limits"]
    z_home = cfg["stewart"]["z_home"]

    robot = build_robot(args)
    rng = random.Random(args.seed)
    count = 0

    total = "∞" if args.forever else args.n
    print(f"🎲 สุ่มท่าทาง {total} ท่า (Ctrl+C หยุด)\n")
    try:
        while True:
            z, roll, pitch, yaw, base, ant_l, ant_r = random_pose(rng, limits)
            dur = round(rng.uniform(0.6, 1.8), 2)

            robot.set_head_pose(z=z, roll=roll, pitch=pitch, yaw=yaw, duration=dur)
            robot.set_base(base, duration=dur)
            robot.set_antennas(left=ant_l, right=ant_r, duration=dur * 0.5)

            count += 1
            print(f"[{count:3d}] z={z:5.1f}mm r={roll:+6.1f}° p={pitch:+6.1f}° "
                  f"y={yaw:+6.1f}° base={base:+6.1f}° ant=({ant_l:+.2f},{ant_r:+.2f})")

            if not args.forever and count >= args.n:
                break
            time.sleep(dur + args.interval)
    except KeyboardInterrupt:
        print("\n⏹ หยุด (Ctrl+C)")
    finally:
        # กลับ home อย่างปลอดภัย
        robot.set_head_pose(z=z_home, roll=0, pitch=0, yaw=0, duration=1.0)
        robot.set_base(0, duration=1.0)
        robot.set_antennas(0, 0, duration=0.5)
        robot.close()
        print(f"\nกลับ home แล้ว ✅ ({count} ท่า)")


if __name__ == "__main__":
    main()
