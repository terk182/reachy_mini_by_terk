"""สแกนหา ID ของมอเตอร์ STS3215 บน bus

วิธีใช้:
    python scripts/scan_servos.py
    python scripts/scan_servos.py --port COM5
    python scripts/scan_servos.py --timeout 0.06      # bus ช้า/USB-TTL ตอบช้า
    python scripts/scan_servos.py --range 1 30        # สแกนเฉพาะช่วง
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
    parser.add_argument("--timeout", type=float, default=0.04,
                        help="เวลารอตอบต่อ ID (วินาที; default 0.04 — 10ms สั้นเกินบน Windows)")
    parser.add_argument("--range", nargs=2, type=int, default=[1, 253],
                        metavar=("FROM", "TO"), help="ช่วง ID ที่สแกน (default 1 253)")
    args = parser.parse_args()

    bus = ServoBus(port=args.port, baudrate=args.baud)
    found = []
    lo, hi = args.range
    try:
        for sid in range(lo, hi + 1):
            if bus.ping(sid, timeout=args.timeout):
                found.append(sid)
                print(f"  พบมอเตอร์ ID={sid}")
    finally:
        bus.close()

    if not found:
        print("ไม่พบมอเตอร์ — ตรวจสอบสายไฟ / ไฟเลี้ยง 7.4V / baudrate")
        print("   ถ้าหารุ่นที่ ID เพี้ยน: เหลือมอเตอร์ตัวเดียวบนบัส แล้วรัน "
              "'--range 1 253 --timeout 0.06'")
    else:
        print(f"พบทั้งหมด {len(found)} ตัว: {found}")


if __name__ == "__main__":
    main()

