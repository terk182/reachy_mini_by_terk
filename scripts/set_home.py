"""ตั้งมอเตอร์ทุกตัวไปที่ตำแหน่งกลาง (2048) หรือตำแหน่งที่กำหนด

ใช้ก่อนประกอบ link (ติด crank) ให้มุมอ้างอิงตรงกันทุกขา

วิธีใช้:
    .venv\\Scripts\\python.exe scripts\\set_home.py              # ทุกตัว (1-9) -> 2048
    .venv\\Scripts\\python.exe scripts\\set_home.py --pos 1024   # ทุกตัว -> 1024
    .venv\\Scripts\\python.exe scripts\\set_home.py --ids 7 8 9  # เฉพาะตัวที่ระบุ
    .venv\\Scripts\\python.exe scripts\\set_home.py --port COM3
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.servo_bus import ServoBus  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="ตั้งมอเตอร์ STS3215 ไปตำแหน่งที่กำหนด")
    parser.add_argument("--pos", type=int, default=2048,
                        help="ตำแหน่งเป้าหมาย (0-4095, default 2048=กลาง)")
    parser.add_argument("--ids", type=int, nargs="+", default=list(range(1, 10)),
                        help="ID ที่ต้องการ (default 1-9)")
    parser.add_argument("--port", default=None, help="พอร์ตอนุกรม (default auto)")
    parser.add_argument("--speed", type=int, default=600, help="ความเร็ว (default 600)")
    args = parser.parse_args()

    pos = max(0, min(4095, args.pos))
    bus = ServoBus(port=args.port, baudrate=1_000_000)
    try:
        print(f"set ID {args.ids} -> {pos} ...")
        bus.sync_set_position([(sid, pos) for sid in args.ids], speed=args.speed)
        time.sleep(1.5)
        print("อ่านกลับ:")
        for sid in args.ids:
            print(f"  ID {sid}: {bus.get_position(sid)}")
    finally:
        bus.close()


if __name__ == "__main__":
    main()
