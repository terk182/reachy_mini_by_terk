# -*- coding: utf-8 -*-
"""ท่า "คุย/ปรึกษากัน" สำหรับหุ่นจริง 2 ตัว (พี่ทด + น้องนุ)

    .venv\\Scripts\\python.exe scripts\\two_robots_consult_demo.py
    .venv\\Scripts\\python.exe scripts\\two_robots_consult_demo.py --mirror   # ถ้าหันผิดข้าง
    .venv\\Scripts\\python.exe scripts\\two_robots_consult_demo.py --loops 2 --turn 22
บท: หันเข้าหากัน -> พี่ทดคิด (เอียงหัว/ก้มมอง) -> พี่ทดพยักหน้าพูด ->
     น้องนุฟัง (เงย/เอียง) -> น้องนุพยักหน้าตอบ -> พยักหน้าตกลงกันพร้อมกัน -> กลับท่ากลาง
"""

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_two_robots_poses import open_robots  # noqa: E402  (ใช้ตัวเปิดหุ่นชุดเดียวกัน)


BASE_CENTER = 2048      # 0° = หันหน้าตรง


def main():
    ap = argparse.ArgumentParser(description="ท่า 'ปรึกษากัน' ของหุ่น 2 ตัว")
    ap.add_argument("--speed", type=int, default=600)
    ap.add_argument("--loops", type=int, default=1)
    ap.add_argument("--turn", type=float, default=25.0,
                    help="องศาที่หมุนตัว/หันหัวเข้าหากัน (default 25 — ค่าที่ทดสอบแล้ว)")
    ap.add_argument("--mirror", action="store_true",
                    help="กลับข้างทั้งหมด (ค่าเริ่มต้น = หันเข้าหากัน; ใส่ flag นี้ถ้าหันออกจากกัน)")
    ap.add_argument("--settle", type=float, default=0.0,
                    help="เพิ่มเวลาหน่วงต่อท่า (วินาที)")
    ap.add_argument("--end-turn", type=float, default=0.0,
                    help="มุมฐานตอนจบ: 0 = กลับท่ากลาง (default) · 180 = หันหลัง")
    args = ap.parse_args()

    robots = open_robots("both")
    if len(robots) < 2:
        sys.exit("ต้องมีหุ่น 2 ตัว (พี่ทด COM4 + น้องนุ COM3)")
    (name_a, ra), (name_b, rb) = robots
    # ค่าเริ่มต้น calibrate จากการทดสอบจริง: sign=-1 = หันเข้าหากัน
    # (--mirror = sign +1 สำหรับการวางหุ่นสลับข้าง)
    sign = 1.0 if args.mirror else -1.0

    # ฐาน: จำตำแหน่งปัจจุบันเป็นศูนย์ แล้วส่ายรอบ ๆ (±turn องศา)
    base_a = ra._bus.get_position(ra.config["servo_ids"]["base"]) or 2048
    base_b = rb._bus.get_position(rb.config["servo_ids"]["base"]) or 2048
    counts_per_deg = 4096.0 / 360.0

    def move(pa, pb, dur, label):
        """pa/pb = (z, roll, pitch, yaw, base_delta_deg) — สั่งพร้อมกันแล้วรอครั้งเดียว

        base_delta_deg เป็น **องศาจริง** — แปลงเป็น count ของ servo ด้วย base.gear_ratio
        (อัตราทดที่วัดจริง = 0.5 → ต้องสั่ง servo 2 เท่าของมุมที่ต้องการ)
        """
        for r, p, base0 in ((ra, pa, base_a), (rb, pb, base_b)):
            z, roll, pitch, yaw, base_deg = p
            r.head.set_pose(z, math.radians(roll), math.radians(pitch),
                            math.radians(yaw), speed=args.speed)
            ratio = float((r.config.get("base") or {}).get("gear_ratio", 1.0) or 1.0)
            pos = int(round(base0 + (base_deg / ratio) * counts_per_deg)) % 4096
            r._bus.set_position(r.config["servo_ids"]["base"], pos, speed=args.speed)
        time.sleep(dur + args.settle)
        print(f"   {label}")

    T = args.turn
    # ทิศจริง (user ยืนยันกับหุ่นจริง 2026-11-07):
    #   pos เพิ่ม (2048→2387) = หัน**ขวา** · pos ลด (2048→1707) = หัน**ซ้าย** (ทั้งสองตัว)
    #   COMBO ที่หันเข้าหากัน = พี่ทด +T (ขวา) / น้องนุ −T (ซ้าย)  ✅
    base_a = +T * sign
    base_b = -T * sign
    # หัว (yaw): บิดจานบน — ผลน้อยมาก แค่ให้หัวเอียงเข้าหาคู่เล็กน้อย
    yaw_a = +T * 0.35 * sign
    yaw_b = -T * 0.35 * sign
    tilt_a = -8.0 * sign
    tilt_b = +8.0 * sign

    try:
        print(f"[{name_a} + {name_b}] ท่า 'ปรึกษากัน'")
        for loop in range(args.loops):
            print(f" รอบที่ {loop + 1}")
            move((70, 0, 0, 0, 0), (70, 0, 0, 0, 0), 0.8, "1) ตั้งตรง มองหน้า")
            move((70, tilt_a * 0.6, -4, yaw_a * 0.6, base_a * 0.7),
                 (70, tilt_b * 0.6, 2, yaw_b * 0.6, base_b * 0.7),
                 0.9, "2) หันเข้าหากัน")
            move((72, tilt_a, 12, yaw_a, base_a),
                 (71, tilt_b, 4, yaw_b, base_b),
                 0.8, f"3) {name_a} เงยคิด + {name_b} ฟัง")
            move((68, tilt_a * 0.6, -10, yaw_a, base_a),
                 (71, tilt_b, 4, yaw_b, base_b),
                 0.7, f"4) {name_a} พยักหน้า")
            move((70, tilt_a * 0.4, 2, yaw_a, base_a),
                 (72, tilt_b, 12, yaw_b, base_b),
                 0.9, f"5) {name_b} รับช่วงพูด")
            move((70, tilt_a * 0.4, 2, yaw_a, base_a),
                 (68, tilt_b * 0.6, -10, yaw_b, base_b),
                 0.7, f"6) {name_b} พยักหน้า")
            move((70, 0, 8, yaw_a * 0.4, base_a * 0.5),
                 (70, 0, 8, yaw_b * 0.4, base_b * 0.5),
                 0.6, "7) ตกลงกัน (พยักหน้าพร้อมกัน)")
            move((69, 0, -8, yaw_a * 0.4, base_a * 0.5),
                 (69, 0, -8, yaw_b * 0.4, base_b * 0.5),
                 0.6, "   ...อีกครั้ง")
            if args.end_turn:
                move((70, 0, 0, 0, args.end_turn),
                     (70, 0, 0, 0, args.end_turn),
                     2.5, f"8) หันหลัง {args.end_turn:.0f}° (จบ)")
            else:
                # กลับมาด้านหน้าแบบสัมบูรณ์ (pos 2048 = 0°) ไม่ว่าเริ่มจากมุมไหน
                for _n, r in robots:
                    r._bus.set_position(r.config["servo_ids"]["base"],
                                        BASE_CENTER, speed=args.speed)
                    r.head.set_pose(r.config["stewart"]["z_home"], 0.0, 0.0, 0.0,
                                    speed=args.speed)
                time.sleep(2.5)
                print("   8) กลับมาด้านหน้า (0°) จบ")
        print("เสร็จสิ้น ✅")
    finally:
        for _n, r in robots:
            r.close()


if __name__ == "__main__":
    main()
