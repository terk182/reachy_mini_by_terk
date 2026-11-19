"""Calibrate อัตโนมัติสำหรับ Stewart platform (หา leg_home / pos_center)

3 ขั้นตอน:
  geometric  — คำนวณ leg_home จากเรขาคณิต (ไม่ต้องมีฮาร์ดแวร์) + บันทึก calibration.json
  zero      — อ่านตำแหน่ง home จริงของมอเตอร์แต่ละตัว (ต้องจัดหัวให้อยู่ท่า home ก่อน)
              -> บันทึก leg_home_pos (ตำแหน่ง center เฉพาะขา)
  verify    — สั่งท่า -> อ่านกลับ -> FK เปรียบเทียบกับท่าที่สั่ง (รายงานความแม่นยำ)

วิธีใช้:
  python scripts/calibrate.py                          # geometric
  python scripts/calibrate.py --hardware               # geometric + zero
  python scripts/calibrate.py --verify --hardware      # ตรวจสอบความแม่นยำ
  python scripts/calibrate.py --hardware --port COM5
  python scripts/calibrate.py --hardware --robot b      # calibrate น้องนุ (calibration_b.json)
  python scripts/calibrate.py --hardware --robot b --no-release   # อ่านท่าที่จัดไว้ทันที
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.robot_config import get_config, save_calibration  # noqa: E402
from src.stewart import (  # noqa: E402
    forward_kinematics,
    home_pos_to_center,
    leg_lengths,
    servo_pos_to_length,
)


def _geometric(config) -> dict:
    """คำนวณ leg_home จากเรขาคณิต: ความยาวขาที่ท่า home (z_home, มุม 0)"""
    st = config["stewart"]
    lengths = leg_lengths(
        st["z_home"], 0.0, 0.0, 0.0,
        st["base_radius"], st["top_radius"],
        st.get("top_offset_deg", 30.0), st.get("layout", "paired"),
    )
    leg_home = float(sum(lengths) / len(lengths))
    print(f"[geometric] ความยาวขา home = {leg_home:.3f} mm "
          f"(จากเรขาคณิต z_home={st['z_home']} mm, มุม 0)")
    return {"leg_home": round(leg_home, 4)}


def _zero(config, port, release: bool = True) -> dict:
    """อ่านตำแหน่ง home จริงของมอเตอร์ 6 ตัว (ปล่อย torque ให้จัดหัวได้เอง แล้วเปิดกลับ)

    release=False → อ่านทันทีโดยไม่ปล่อย torque (ใช้เมื่องัดท่าไว้แล้วและไม่อยากให้หัวทรุด)
    """
    from src.servo_bus import ServoBus

    st = config["stewart"]
    ids = config["servo_ids"]["head"]

    bus = ServoBus(port=port, baudrate=config["baudrate"])
    try:
        missing = [sid for sid in ids if not bus.ping(sid)]
        if missing:
            raise SystemExit(f"มอเตอร์หัวไม่ตอบสนอง: {missing} — เช็คสายไฟ/ID")

        if release:
            # ปล่อย torque (limp) ให้จัดหัวได้เอง — encoder ยังอ่านตำแหน่งได้
            for sid in ids:
                bus.set_torque(sid, False)
            print("\n[zero] ปล่อย torque แล้ว — จัดหัวให้อยู่ในท่า home: "
                  "ระดับ (ไม่เอียง), สูง "
                  f"z_home ≈ {st['z_home']} mm จากจานล่าง")
            input("[zero] พร้อมแล้วกด Enter เพื่ออ่านตำแหน่ง... ")
        else:
            print("\n[zero] อ่านตำแหน่งทันที (ไม่ปล่อย torque) — "
                  "ใช้ท่าที่จัดไว้แล้วเป็นท่า home")

        home_pos = []
        for sid in ids:
            pos = bus.get_position(sid)
            if pos is None:
                raise SystemExit(f"อ่านตำแหน่ง ID {sid} ไม่ได้")
            home_pos.append(pos)
            print(f"  ID {sid}: home position = {pos}")

        # เปิด torque กลับ (ล็อกหัวหลังอ่าน)
        for sid in ids:
            bus.set_torque(sid, True)
        print("[zero] เปิด torque กลับแล้ว (ล็อกหัว)")
    finally:
        bus.close()

    print(f"[zero] บันทึก leg_home_pos = {home_pos}")
    return {"leg_home_pos": home_pos}


def _zero_antennas(config, port) -> dict:
    """อ่านตำแหน่ง home จริงของเสาอากาศ (ID 8, 9) — ชี้ตรง = 0 rad"""
    from src.servo_bus import ServoBus

    ids = config["servo_ids"]["antennas"]
    bus = ServoBus(port=port, baudrate=config["baudrate"])
    try:
        missing = [sid for sid in ids if not bus.ping(sid)]
        if missing:
            raise SystemExit(f"มอเตอร์เสาอากาศไม่ตอบสนอง: {missing} — เช็คสายไฟ/ID")

        # ปล่อย torque ให้จัดเสาอากาศได้เอง
        for sid in ids:
            bus.set_torque(sid, False)
        print("\n[zero-antennas] ปล่อย torque แล้ว — จัดเสาอากาศทั้ง 2 ข้าง "
              "ให้ชี้ไปด้านหน้า (ท่าตรง, 0 rad)")
        input("[zero-antennas] พร้อมแล้วกด Enter เพื่ออ่านตำแหน่ง... ")

        home = []
        for sid in ids:
            pos = bus.get_position(sid)
            if pos is None:
                raise SystemExit(f"อ่านตำแหน่ง ID {sid} ไม่ได้")
            home.append(pos)
            print(f"  ID {sid}: home position = {pos}")

        for sid in ids:
            bus.set_torque(sid, True)
        print("[zero-antennas] เปิด torque กลับแล้ว (ล็อกเสาอากาศ)")
    finally:
        bus.close()

    print(f"[zero-antennas] บันทึก antenna_home_pos = {home}")
    return {"home_pos": home}


def _verify(config, port, n_poses=5) -> None:
    """สั่งท่า -> อ่านตำแหน่ง -> แปลงเป็นความยาว -> FK -> เปรียบเทียบ"""
    from src.servo_bus import ServoBus
    from src.stewart import StewartHead

    st = config["stewart"]
    ids = config["servo_ids"]["head"]
    bus = ServoBus(port=port, baudrate=config["baudrate"])
    try:
        head = StewartHead(bus, ids, st)
        mech = st.get("mechanism", "leadscrew")
        print(f"[verify] mechanism={mech}, n_poses={n_poses}")

        poses = [
            (st["z_home"], 0.0, 0.0, 0.0),
            (st["z_home"] + 8.0, 0.1, 0.0, 0.0),
            (st["z_home"] - 6.0, 0.0, 0.15, 0.0),
            (st["z_home"] + 5.0, -0.08, 0.1, 0.25),
            (st["z_home"], 0.0, 0.0, -0.3),
        ][:n_poses]

        worst = 0.0
        for (z, roll, pitch, yaw) in poses:
            head.set_pose(z, roll, pitch, yaw, speed=500)
            time.sleep(1.2)   # รอหัวขยับเสร็จก่อนอ่านกลับ (0.5 วิ สั้นเกิน — อ่านได้ค่ากลางทาง)
            # อ่านกลับ
            lengths = []
            centers = st.get("leg_home_pos")
            for i, sid in enumerate(ids):
                pos = bus.get_position(sid)
                if pos is None:
                    raise SystemExit(f"อ่านตำแหน่ง ID {sid} ไม่ได้")
                solution = st.get("solution", [0] * 6)[i] if st.get("solution") else 0
                if centers:
                    center = home_pos_to_center(
                        centers[i], st["leg_home"],
                        st.get("arm_len", 40.0), st.get("rod_len", 85.0),
                        solution)
                else:
                    center = st.get("pos_center", 2048)
                lengths.append(servo_pos_to_length(
                    pos, st["leg_home"], st["pitch"], pos_center=center,
                    mechanism=mech, arm_len=st.get("arm_len", 40.0),
                    rod_len=st.get("rod_len", 85.0), solution=solution))
            # FK (ระบุ x0 = ท่าที่สั่ง เพื่อล็อก assembly mode)
            (z2, r2, p2, y2), residual = forward_kinematics(
                lengths, st["base_radius"], st["top_radius"],
                st.get("top_offset_deg", 30.0), st.get("layout", "paired"),
                x0=(z, roll, pitch, yaw))
            err_z = abs(z2 - z)
            err_ang = max(abs(r2 - roll), abs(p2 - pitch), abs(y2 - yaw))
            worst = max(worst, err_z, err_ang)
            print(f"  สั่ง z={z:.1f} r={roll:+.2f} p={pitch:+.2f} y={yaw:+.2f} | "
                  f"FK ได้ z={z2:.2f} r={r2:+.3f} p={p2:+.3f} y={y2:+.3f} | "
                  f"err z={err_z:.2f}mm มุม={err_ang:.3f}rad | res={residual:.1e}")

        print(f"\n[verify] ค่าคลาดเคลื่อนสูงสุด: {worst:.3f}")
        print("  ✅ แม่นยำดี" if worst < 2.0 else "  ⚠️ ยังสูง — ตรวจสอบ calibrate/กลไก")
    finally:
        bus.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Calibrate Stewart platform อัตโนมัติ")
    parser.add_argument("--hardware", action="store_true", help="มีหุ่นจริง (อ่านมอเตอร์)")
    parser.add_argument("--port", default=None, help="พอร์ตอนุกรม (hardware)")
    parser.add_argument("--antennas", action="store_true",
                        help="calibrate เฉพาะเสาอากาศ (ID 8,9) — ไม่แตะหัว")
    parser.add_argument("--verify", action="store_true",
                        help="ตรวจสอบความแม่นยำ (สั่ง->อ่าน->FK)")
    parser.add_argument("--no-save", action="store_true",
                        help="คำนวณอย่างเดียว ไม่บันทึก calibration.json")
    parser.add_argument("--no-release", action="store_true",
                        help="อ่านตำแหน่งทันที ไม่ปล่อย torque (ใช้ท่าที่จัดไว้แล้ว)")
    parser.add_argument("--robot", choices=["a", "b"], default="a",
                        help="หุ่นที่จะ calibrate: a = พี่ทด (calibration.json) · "
                             "b = น้องนุ (calibration_b.json)")
    args = parser.parse_args()

    config = get_config(args.robot)
    updates = {}

    updates.update(_geometric(config))

    if args.hardware and not args.verify:
        if args.antennas:
            ant = _zero_antennas(config, args.port)
            if not args.no_save:
                path = save_calibration(ant, section="antennas", robot=args.robot)
                print(f"\nบันทึก antenna calibration ({args.robot}) -> {path}")
                print("   ค่าที่บันทึก:", ant)
        else:
            updates.update(_zero(config, args.port, release=not args.no_release))

    if not args.no_save and updates:
        path = save_calibration(updates, robot=args.robot)
        print(f"\nบันทึก calibration ({args.robot}) -> {path}")
        print("   ค่าที่บันทึก:", updates)

    if args.verify:
        if not args.hardware:
            parser.error("--verify ต้องใช้กับ --hardware (ต้องมีหุ่นจริง)")
        _verify(config, args.port)

    print("\nเสร็จสิ้น ✅")


if __name__ == "__main__":
    main()
