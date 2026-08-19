"""สแกนหา ID ของมอเตอร์ STS3215 บน bus

วิธีใช้:
    python scripts/scan_servos.py
    python scripts/scan_servos.py --port COM5
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.servo_bus import ServoBus  # noqa: E402


def main():
    import argparse

    parser = argparse.ArgumentParser(description="สแกนหา STS3215 บน bus")
    parser.add_argument("--port", default=None, help="พอร์ตอนุกรม (ถ้าไม่ระบุ auto-detect)")
    parser.add_argument("--baud", type=int, default=1_000_000, help="baudrate (default 1M)")
    args = parser.parse_args()

    bus = ServoBus(port=args.port, baudrate=args.baud)
    found = []
    for sid in range(1, 254):
        if bus.ping(sid, timeout=0.01):
            found.append(sid)
            print(f"  พบมอเตอร์ ID={sid}")
    bus.close()

    if not found:
        print("ไม่พบมอเตอร์ — ตรวจสอบสายไฟ / ไฟเลี้ยง 7.4V / baudrate")
    else:
        print(f"พบทั้งหมด {len(found)} ตัว: {found}")


if __name__ == "__main__":
    main()
