"""ทดสอบมอเตอร์: sweep มุม + อ่าน feedback

วิธีใช้:
    python scripts/test_servos.py            # ทดสอบ ID 1-9
    python scripts/test_servos.py 1 2 3      # เฉพาะบางตัว
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.servo_bus import ServoBus  # noqa: E402


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ทดสอบมอเตอร์ STS3215")
    parser.add_argument("ids", nargs="*", type=int, help="ID ที่จะทดสอบ (default: 1-9)")
    parser.add_argument("--port", default=None)
    args = parser.parse_args()

    bus = ServoBus(port=args.port)
    ids = args.ids or list(range(1, 10))

    for sid in ids:
        if not bus.ping(sid):
            print(f"[ID {sid}] ไม่ตอบสนอง (ข้าม)")
            continue
        print(f"[ID {sid}] เริ่ม sweep ...")
        for pos in (2048, 1024, 2048, 3072, 2048):
            bus.set_position(sid, pos, speed=500)
            time.sleep(0.4)
            got = bus.get_position(sid)
            load = bus.get_load(sid)
            print(f"  -> สั่ง {pos} | อ่านได้ {got} | load={load}")
        time.sleep(0.2)

    bus.close()
    print("เสร็จสิ้น ✅")


if __name__ == "__main__":
    main()
