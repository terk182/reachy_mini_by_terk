"""ทดสอบ control Reachy Mini แท้แบบวนลูปอัตโนมัติ

วนลูปส่งคำสั่งท่าทางไป daemon ทางการ (REST API) แล้วอ่านค่ากลับมาตรวจสอบ
หุ่นต้องรัน official daemon + MuJoCo sim ก่อน:
    reachy_mini_env\\Scripts\\reachy-mini-daemon.exe --sim

วิธีใช้:
    .venv\\Scripts\\python.exe scripts\\test_control_loop.py              # 3 รอบ
    .venv\\Scripts\\python.exe scripts\\test_control_loop.py --loops 5
    .venv\\Scripts\\python.exe scripts\\test_control_loop.py --forever   # รันจน Ctrl+C
    .venv\\Scripts\\python.exe scripts\\test_control_loop.py --interval 0.3
    .venv\\Scripts\\python.exe scripts\\test_control_loop.py --no-check  # ไม่อ่านค่ากลับ
"""

import argparse
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.real_robot import RealRobot  # noqa: E402

DAEMON_URL = "http://127.0.0.1:8000"


def get_json(path: str):
    """GET ค่าจาก daemon แล้วคืน dict"""
    with urllib.request.urlopen(DAEMON_URL + path, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def read_state():
    """อ่านท่าปัจจุบัน: (head, body_yaw_deg, antennas_deg)"""
    head = get_json("/api/state/present_head_pose")
    yaw = get_json("/api/state/present_body_yaw")
    ant = get_json("/api/state/present_antenna_joint_positions")
    return head, yaw, ant


def build_moves(robot: RealRobot):
    """สร้างชุดคำสั่งทดสอบ: รายการ (ชื่อ, ฟังก์ชัน, ระยะเวลา)"""
    moves = []

    def add(name, fn, dur):
        moves.append((name, fn, dur))

    add("wake_up", lambda: robot.wake_up(), 3.0)
    # แกน Z (ความสูงหัว)
    add("z+ (78 mm)", lambda: robot.set_head_pose(z=78), 1.0)
    add("z- (62 mm)", lambda: robot.set_head_pose(z=62), 1.0)
    # แกน roll (เอียงซ้าย-ขวา)
    add("roll +20°", lambda: robot.set_head_pose(roll=20), 1.0)
    add("roll -20°", lambda: robot.set_head_pose(roll=-20), 1.0)
    # แกน pitch (ก้ม-เงย)
    add("pitch +25°", lambda: robot.set_head_pose(pitch=25), 1.0)
    add("pitch -25°", lambda: robot.set_head_pose(pitch=-25), 1.0)
    # แกน yaw (หมุนหัวซ้าย-ขวา)
    add("yaw +40°", lambda: robot.set_head_pose(yaw=40), 1.0)
    add("yaw -40°", lambda: robot.set_head_pose(yaw=-40), 1.0)
    # หมุนตัว (base)
    add("base +60°", lambda: robot.set_base(60), 1.0)
    add("base -60°", lambda: robot.set_base(-60), 1.0)
    # เสาอากาศ
    add("antenna L/R", lambda: robot.set_antennas(1.0, -1.0), 0.6)
    add("antenna R/L", lambda: robot.set_antennas(-1.0, 1.0), 0.6)
    # ท่ารวมทุกแกน
    add("combined pose", lambda: robot.goto(
        head={"x": 0.0, "y": 0.0, "z": 0.008,
              "roll": 0.2, "pitch": 0.3, "yaw": 0.4},
        body_yaw=0.35, antennas=[0.8, -0.8], duration=1.2), 1.6)
    # กลับ home
    add("home", lambda: robot.goto(
        head={"x": 0.0, "y": 0.0, "z": 0.0,
              "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        body_yaw=0.0, antennas=[0.0, 0.0], duration=1.2), 1.6)
    return moves


def main():
    parser = argparse.ArgumentParser(description="ทดสอบ control Reachy Mini แท้แบบวนลูป")
    parser.add_argument("--loops", type=int, default=3, help="จำนวนรอบ (default 3)")
    parser.add_argument("--forever", action="store_true", help="รันวนไม่รู้จบจน Ctrl+C")
    parser.add_argument("--interval", type=float, default=0.4,
                        help="วินาทีเพิ่มหลังแต่ละท่า (default 0.4)")
    parser.add_argument("--no-check", action="store_true",
                        help="ไม่อ่านค่ากลับ (เร็วขึ้น)")
    args = parser.parse_args()

    if not RealRobot.available():
        print("⚠️ daemon ไม่พร้อม — รันก่อน: "
              "reachy_mini_env\\Scripts\\reachy-mini-daemon.exe --sim")
        return 1

    robot = RealRobot()
    moves = build_moves(robot)
    ok_count = fail_count = loop = 0

    print(f"🧪 ทดสอบ control อัตโนมัติ — {len(moves)} คำสั่ง/รอบ "
          f"({'∞' if args.forever else args.loops} รอบ) "
          f"{'ตรวจค่ากลับ' if not args.no_check else 'ไม่ตรวจค่ากลับ'}")
    try:
        while True:
            loop += 1
            print(f"\n===== 🔁 รอบที่ {loop} =====")
            for name, fn, dur in moves:
                try:
                    fn()
                    ok = True
                except Exception as exc:  # noqa: BLE001
                    ok = False
                    err = f" ({exc})"
                # รอให้ท่าจบแล้วค่อยไปท่าถัดไป
                time.sleep(dur + args.interval)

                if args.no_check:
                    print(f"  [{'✅' if ok else '❌'}] {name}")
                else:
                    try:
                        head, yaw, ant = read_state()
                        print(
                            f"  [{'✅' if ok else '❌'}] {name:16s}"
                            f" -> z={head['z']*1000:5.0f}mm "
                            f"r={math.degrees(head['roll']):5.1f}° "
                            f"p={math.degrees(head['pitch']):5.1f}° "
                            f"y={math.degrees(head['yaw']):5.1f}° "
                            f"base={math.degrees(yaw):5.1f}° "
                            f"ant=[{math.degrees(ant[0]):5.1f},{math.degrees(ant[1]):5.1f}]°"
                        )
                    except Exception as exc:  # noqa: BLE001
                        print(f"  [{'✅' if ok else '❌'}] {name} (อ่านค่ากลับไม่ได้{exc})")
                ok_count += ok
                fail_count += 0 if ok else 1

            if not args.forever and loop >= args.loops:
                break
    except KeyboardInterrupt:
        print("\n⏹ หยุด (Ctrl+C)")

    print(f"\n🏁 เสร็จ: OK={ok_count} ❌FAIL={fail_count} "
          f"({len(moves)*loop} คำสั่งทั้งหมด)")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
