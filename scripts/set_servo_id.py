"""ตั้ง ID ให้มอเตอร์ STS3215

⚠️ สำคัญ: ต้องมีมอเตอร์เพียงตัวเดียวต่อกับ bus เท่านั้น!
หลังตั้ง ID แล้วให้ถอดปลั๊กแล้วเสียบใหม่เพื่อให้มีผล

วิธีใช้:
    python scripts/set_servo_id.py --old 1 --new 2
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.servo_bus import ServoBus  # noqa: E402


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ตั้ง ID ให้ STS3215 (มอเตอร์ตัวเดียวบน bus)")
    parser.add_argument("--old", type=int, default=1, help="ID ปัจจุบัน (default 1)")
    parser.add_argument("--new", type=int, required=True, help="ID ใหม่ (1-253)")
    parser.add_argument("--port", default=None)
    args = parser.parse_args()

    if not (1 <= args.new <= 253):
        print("ID ต้องอยู่ระหว่าง 1-253")
        sys.exit(1)

    bus = ServoBus(port=args.port)
    if not bus.ping(args.old):
        print(f"ไม่พบมอเตอร์ ID={args.old} — เช็คสายไฟ / ไฟเลี้ยง")
        bus.close()
        sys.exit(1)

    bus.set_id(args.old, args.new)
    bus.close()
    print(f"ตั้ง ID {args.old} -> {args.new} เรียบร้อย")
    print("👉 ถอดปลั๊กแล้วเสียบใหม่ เพื่อให้การเปลี่ยน ID มีผล")


if __name__ == "__main__":
    main()
