r"""แสดงท่าทางของเราบน Reachy Mini แท้ (official MuJoCo model)

ใช้โมเดลแท้จาก official SDK (reachy_mini_env) — ต่างจาก src/mujoco_sim.py
ที่จำลองหุ่น DIY แบบง่ายๆ

⚠️ ต้องรันด้วย python ของ reachy_mini_env (official SDK, Python 3.12):
    reachy_mini_env\Scripts\python.exe scripts\run_real_sim.py
    reachy_mini_env\Scripts\python.exe scripts\run_real_sim.py --hold

- ถ้า official daemon ยังไม่รัน จะเปิดให้อัตโนมัติ (หน้าต่างโมเดลแท้)
- --hold: เปิดหน้าต่างค้างไว้ดูจนกว่าจะปิด
"""

import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEALTH_URL = "http://127.0.0.1:8000/docs"  # FastAPI docs = เช็คว่า server พร้อม


def daemon_running() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=1):
            return True
    except Exception:  # noqa: BLE001
        return False


def start_daemon():
    daemon = ROOT / "reachy_mini_env" / "Scripts" / "reachy-mini-daemon.exe"
    print("[RealSim] เริ่ม official daemon (โมเดล Reachy Mini แท้)...")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    return subprocess.Popen(
        [str(daemon), "--sim", "--scene", "minimal"],
        cwd=str(ROOT), creationflags=flags,
    )


def wait_ready(timeout: float = 90) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if daemon_running():
            return True
        time.sleep(1)
    return False


def main():
    parser = argparse.ArgumentParser(
        description="ท่าทางบน Reachy Mini แท้ (official MuJoCo model)")
    parser.add_argument("--hold", action="store_true",
                        help="เปิดหน้าต่างค้างไว้ดูจนกว่าจะปิด")
    args = parser.parse_args()

    from reachy_mini import ReachyMini  # noqa: E402
    from reachy_mini.utils import create_head_pose  # noqa: E402

    proc = None
    if not daemon_running():
        proc = start_daemon()
        if not wait_ready():
            print("⚠️ daemon ไม่พร้อม — รันเอง: "
                  "reachy_mini_env\\Scripts\\reachy-mini-daemon.exe --sim")
            return
        time.sleep(3)  # ให้ sim wake up

    with ReachyMini(media_backend="no_media") as mini:
        print("✅ เชื่อมต่อ Reachy Mini แท้แล้ว! กำลังแสดงท่าทาง...")
        home = create_head_pose()
        mini.goto_target(head=home, antennas=[0.0, 0.0], duration=1.0)

        # wave
        print("• โบกเสาอากาศ (wave)")
        for _ in range(3):
            mini.goto_target(head=create_head_pose(pitch=10, degrees=True),
                             antennas=[0.6, -0.6], duration=0.4)
            mini.goto_target(head=create_head_pose(pitch=10, degrees=True),
                             antennas=[-0.6, 0.6], duration=0.4)

        # look around
        print("• มองซ้าย-ขวา (look around)")
        mini.goto_target(head=create_head_pose(yaw=-45, degrees=True), duration=1.0)
        mini.goto_target(head=create_head_pose(yaw=45, degrees=True), duration=1.5)
        mini.goto_target(head=create_head_pose(yaw=0, degrees=True), duration=1.0)

        # emotions (happy / surprised)
        print("• อารมณ์: happy / surprised")
        mini.goto_target(head=create_head_pose(roll=8, pitch=8, degrees=True),
                         antennas=[1.0, -1.0], duration=0.5)
        mini.goto_target(head=create_head_pose(roll=-8, pitch=8, degrees=True),
                         antennas=[-1.0, 1.0], duration=0.5)
        mini.goto_target(head=create_head_pose(pitch=18, degrees=True),
                         antennas=[1.2, -1.2], duration=0.4)

        mini.goto_target(head=home, antennas=[0.0, 0.0], duration=1.0)
        print("เสร็จสิ้น ✅")

        if args.hold:
            print("--hold: ปิดหน้าต่าง MuJoCo หรือ Ctrl+C เพื่อจบ")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

    if proc is not None and not args.hold:
        proc.terminate()


if __name__ == "__main__":
    main()
