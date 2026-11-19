# -*- coding: utf-8 -*-
"""ท่าเต้นหุ่นจริง 2 ตัว — เต้นพร้อมกัน / ผลัดกันเต้น

    # โชว์ครบ: พร้อมกัน -> ผลัดกัน -> พร้อมกันปิดท้าย
    .venv\\Scripts\\python.exe scripts\\two_robots_dance.py

    # เต้นพร้อมกันตลอด
    .venv\\Scripts\\python.exe scripts\\two_robots_dance.py --mode together

    # ผลัดกันเต้น (A เต้น -> B เต้น สลับกัน)
    .venv\\Scripts\\python.exe scripts\\two_robots_dance.py --mode alternate --rounds 3

    # ปรับจังหวะ/ความเร็ว
    .venv\\Scripts\\python.exe scripts\\two_robots_dance.py --bpm 140 --speed 800 --acc 20
"""

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_two_robots_poses import open_robots  # noqa: E402

BASE_CENTER = 2048
CPD = 4096.0 / 360.0


def dance_frame(t: float, bpm: float):
    """ท่าเต้น ณ เวลา t → (dz_mm, roll_deg, pitch_deg, yaw_deg, base_deg)

    4 ห้อง (bar) วนซ้ำ ห้องละ 4 จังหวะ:
      1) เด้ง + ส่าย   2) ส่ายข้างแรง + หมุนตัว   3) พยัก + กลิ้งหัว   4) วงกลม + เด้งปิด
    """
    beat = 60.0 / bpm
    bar_len = beat * 4
    bar = int(t // bar_len) % 4
    ph = (t % bar_len) / beat          # 0..4 จังหวะในห้อง
    s = math.sin(math.pi * ph)         # 0 → 1 → 0 ต่อ 2 จังหวะ
    a = 2 * math.pi * ph / 4.0         # มุมวงกลมตลอดห้อง

    if bar == 0:                       # เด้ง + ส่ายหัว
        dz, roll, pitch = 5.0 * abs(s), 14.0 * math.sin(a), -7.0 * abs(s)
    elif bar == 1:                     # ส่ายข้างแรง + หมุนตัว
        dz, roll, pitch = 2.5 * abs(s), 20.0 * math.sin(a), 4.0 * s
    elif bar == 2:                     # พยัก + กลิ้งหัว
        dz, roll, pitch = 3.5 * abs(s), 11.0 * math.cos(a), -12.0 * math.sin(a)
    else:                              # วนกลม + เด้งปิดท้าย
        dz, roll, pitch = 6.0 * abs(s), 15.0 * math.cos(a), 12.0 * math.sin(a)

    base = 12.0 * math.sin(a)          # ส่ายฐานเบา ๆ (±12°)
    return dz, roll, pitch, 0.0, base


def idle_frame(t: float):
    """ท่าของตัวที่ไม่ได้เต้น — ยืนโยกเบา ๆ / มองเพื่อนเต้น"""
    b = 60.0 / 110.0
    return (1.5 * abs(math.sin(math.pi * t / (b * 4))),
            8.0 * math.sin(t * 0.9),
            3.0 * math.sin(t * 0.6), 0.0, 0.0)


def main():
    ap = argparse.ArgumentParser(description="ท่าเต้นหุ่นจริง 2 ตัว")
    ap.add_argument("--mode", choices=["together", "alternate", "both"], default="both")
    ap.add_argument("--bpm", type=float, default=120.0, help="จังหวะต่อนาที")
    ap.add_argument("--speed", type=int, default=800)
    ap.add_argument("--acc", type=int, default=20, help="อัตราเร่ง 0-254 (ต่ำ = กระชับ/สนุก)")
    ap.add_argument("--dt", type=float, default=0.05, help="รอบส่งคำสั่ง (วินาที)")
    ap.add_argument("--rounds", type=int, default=2, help="จำนวนรอบตอนผลัดกันเต้น")
    ap.add_argument("--segment", type=float, default=8.0,
                    help="เวลาแต่ละช่วง (วินาที) — 1 ห้อง = 4 จังหวะ")
    args = ap.parse_args()

    robots = open_robots("both")
    if len(robots) < 2:
        sys.exit("ต้องมีหุ่น 2 ตัว (COM4 พี่ทด + COM3 น้องนุ)")
    (name_a, ra), (name_b, rb) = robots
    z_a = ra.config["stewart"]["z_home"]
    z_b = rb.config["stewart"]["z_home"]
    base0 = {id(ra): ra._bus.get_position(ra.config["servo_ids"]["base"]) or BASE_CENTER,
             id(rb): rb._bus.get_position(rb.config["servo_ids"]["base"]) or BASE_CENTER}

    def send(r, z_home, frame):
        """frame = (dz, roll, pitch, yaw, base_deg) — base เป็นองศาจริงจากศูนย์กลาง"""
        dz, roll, pitch, yaw, base_deg = frame
        r.head.set_pose(z_home + dz, math.radians(roll), math.radians(pitch),
                        math.radians(yaw), speed=args.speed, acc=args.acc)
        ratio = float((r.config.get("base") or {}).get("gear_ratio", 1.0) or 1.0)
        pos = int(round(BASE_CENTER + (base_deg / ratio) * CPD)) % 4096
        r._bus.set_position(r.config["servo_ids"]["base"], pos, speed=args.speed)

    def run(duration, a_active, b_active, label):
        print(f"   {label}")
        t0 = time.time()
        while True:
            t = time.time() - t0
            if t >= duration:
                break
            send(ra, z_a, dance_frame(t, args.bpm) if a_active else idle_frame(t))
            send(rb, z_b, dance_frame(t, args.bpm) if b_active else idle_frame(t))
            time.sleep(args.dt)

    def rest():
        for r, z in ((ra, z_a), (rb, z_b)):
            r.head.set_pose(z, 0.0, 0.0, 0.0, speed=args.speed, acc=args.acc)
            r._bus.set_position(r.config["servo_ids"]["base"], BASE_CENTER,
                                speed=args.speed)
        time.sleep(1.5)

    try:
        print(f"🕺 ท่าเต้น ({args.mode}, {args.bpm:.0f} BPM)")
        if args.mode == "together":
            run(args.segment * 2, True, True, "เต้นพร้อมกัน")
        elif args.mode == "alternate":
            for i in range(args.rounds):
                run(args.segment, True, False, f"รอบ {i + 1}: {name_a} เต้น · {name_b} โยกตาม")
                run(args.segment, False, True, f"รอบ {i + 1}: {name_b} เต้น · {name_a} โยกตาม")
        else:
            run(args.segment, True, True, "1) เต้นพร้อมกัน")
            for i in range(args.rounds):
                run(args.segment, True, False, f"2.{i + 1}) {name_a} เต้นเดี่ยว")
                run(args.segment, False, True, f"3.{i + 1}) {name_b} เต้นเดี่ยว")
            run(args.segment, True, True, "4) เต้นพร้อมกันปิดท้าย")
        rest()
        print("   กลับท่ากลาง ✅")
    finally:
        for _n, r in robots:
            r.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
