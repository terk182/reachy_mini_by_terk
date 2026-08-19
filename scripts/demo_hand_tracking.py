"""สาธิต: ติดตามมือด้วยกล้อง USB -> หุ่นเคลื่อนไหวตาม

วิธีใช้:
    python scripts/demo_hand_tracking.py                     # โหมดจำลอง
    python scripts/demo_hand_tracking.py --gui               # + หน้าต่าง 3D หุ่น
    python scripts/demo_hand_tracking.py --hardware          # หุ่นจริง
    python scripts/demo_hand_tracking.py --camera 1          # กล้องตัวอื่น

กด q เพื่อออก
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402

from src.camera import Camera, list_cameras, resolve_camera  # noqa: E402
from src.robot import Robot  # noqa: E402
from src.vision import HandTracker, apply_deadzone  # noqa: E402

ALPHA = 0.35   # low-pass filter (ลดการสั่น)
DEADZONE = 0.08  # โซนกลางไม่ขยับ (กัน servo สั่น)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ติดตามมือด้วยกล้อง USB")
    parser.add_argument("--hardware", action="store_true", help="ใช้หุ่นจริง")
    parser.add_argument("--port", default=None)
    parser.add_argument("--camera", default="lifecam",
                        help="ชื่อหรือ id กล้อง (default 'lifecam' = กล้อง USB)")
    parser.add_argument("--list-cameras", action="store_true",
                        help="แสดงรายการกล้องแล้วออก")
    parser.add_argument("--gui", action="store_true",
                        help="แสดงหน้าต่าง 3D หุ่น (โหมดจำลองเท่านั้น, MuJoCo)")
    args = parser.parse_args()

    if args.list_cameras:
        print("กล้องที่เจอ:")
        for idx, name in list_cameras():
            print(f"  [{idx}] {name}")
        return
camera_id
    camera_id = resolve_camera(args.camera)

    backend = "hardware" if args.hardware else "sim"
    robot = Robot(backend=backend, port=args.port,
                  gui="mujoco" if (args.gui and backend == "sim") else False)
    robot.wake_up()

    smooth = {"base": 0.0, "roll": 0.0, "z": 55.0}

    try:
        with Camera(args.camera) as cam, HandTracker() as tracker:
            while True:
                frame = cam.read()
                if frame is None:
                    print("อ่านภาพจากกล้องไม่ได้")
                    break

                hand = tracker.detect(frame)
                if hand is not None:
                    x, y, z = hand
                    # deadzone กัน servo สั่นตอนมืออยู่กึ่งกลาง
                    x = apply_deadzone(x, DEADZONE)
                    y = apply_deadzone(y, DEADZONE)
                    target = {
                        "base": x * 60.0,   # ซ้าย/ขวา -> หมุนตัว
                        "roll": y * 25.0,   # บน/ล่าง -> ก้ม/เงย (หน้า=+Y -> nod=roll)
                        "z": 55.0 + (1.0 - min(1.0, z + 0.5)) * 15.0,
                    }
                    for k in smooth:
                        smooth[k] += ALPHA * (target[k] - smooth[k])
                    robot.set_head_pose(z=smooth["z"], roll=smooth["roll"],
                                        pitch=0.0, yaw=0.0)
                    robot.set_base(smooth["base"])
                    color = (0, 255, 0)
                else:
                    color = (0, 0, 255)

                h, w = frame.shape[:2]
                cv2.circle(frame, (w // 2, h // 2), 6, color, -1)
                cv2.putText(frame, f"hand: {hand is not None}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                cv2.imshow("Reachy Mini DIY - Hand Tracking", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        robot.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
