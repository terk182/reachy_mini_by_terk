r"""สาธิต vision รวม: สบตา + ท่ามือสั่งงาน + ทักทายเมื่อมีคนเข้ามา

วิธีใช้:
    .venv\Scripts\python.exe scripts\demo_vision.py                  # โหมดจำลอง
    .venv\Scripts\python.exe scripts\demo_vision.py --hardware       # หุ่นจริง
    .venv\Scripts\python.exe scripts\demo_vision.py --camera 1       # กล้องตัวอื่น
    .venv\Scripts\python.exe scripts\demo_vision.py --gui            # + หน้าต่าง MuJoCo 3D

ฟีเจอร์ (เรียงตามความสำคัญตอนทำงาน):
  1. ท่ามือสั่งงาน — ชูนิ้วโป้ง/แบมือ/ชูสองนิ้ว/... -> หุ่นทำแอคชั่น
  2. สบตา         — หุ่นหันหน้าไปทางใบหน้าที่ใกล้ที่สุด
  3. ทักทาย       — มีคนเดินเข้ามาใหม่ -> โบกมือทักทาย

กด q เพื่อออก
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402

from src.camera import Camera, list_cameras, resolve_camera  # noqa: E402
from src.face_detector import FaceDetector  # noqa: E402
from src.robot import Robot  # noqa: E402
from src.vision import (  # noqa: E402
    GestureRecognizer,
    PresenceDetector,
    Smoother,
    apply_deadzone,
)

# ท่ามือ -> (ชื่อ method บน robot, ป้ายข้อความ)
GESTURE_ACTIONS = {
    "thumbs_up": ("happy", "ชูนิ้วโป้ง -> ดีใจ"),
    "open_palm": ("wave", "แบมือ -> โบกมือ"),
    "victory": ("dance", "ชูสองนิ้ว -> เต้น"),
    "love": ("bow", "มือรัก -> โค้งคำนับ"),
    "fist": ("shake_head", "กำหมัด -> ส่ายหัว"),
    "point": ("look_around", "ชี้ขึ้น -> มองหา"),
}

ALPHA = 0.2             # low-pass ติดตามหน้า (ช้าลง = นุ่ม/ส่ายน้อยลง)
DEADZONE = 0.12          # โซนกลางไม่ขยับ (กว้างขึ้น = กันส่ายจาก noise จับใบหน้า)
GESTURE_HOLD_FRAMES = 3  # ต้องเห็นท่าเดิมกี่เฟรมติดกันถึงทำแอคชั่น (กัน false positive)
GESTURE_COOLDOWN = 3.0   # วิ ห้ามทำท่าซ้ำเร็วเกิน


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Vision รวม: สบตา + ท่ามือ + ทักทาย")
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

    camera_id = resolve_camera(args.camera)

    backend = "hardware" if args.hardware else "sim"
    robot = Robot(backend=backend, port=args.port,
                  gui="mujoco" if (args.gui and backend == "sim") else False)
    robot.wake_up()
    if args.hardware:
        print("🤖 หุ่นจริง (hardware) — ขยับตามจริง")
    else:
        print("🤖 หุ่นจำลอง (sim) — ไม่ขยับจริง! ใส่ --hardware ถ้าจะให้ขยับ")

    smooth = {"base": Smoother(ALPHA, 0.0), "roll": Smoother(ALPHA, 0.0)}
    presence = PresenceDetector(appear_time=1.2, gone_time=3.0)
    hold = {"name": None, "count": 0}
    last_action = time.time() - GESTURE_COOLDOWN  # เริ่มต้นให้ทำท่าได้ทันที

    def do_action(name):
        method, label = GESTURE_ACTIONS[name]
        print(f"🖐️ {label}")
        try:
            getattr(robot, method)()
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ ทำท่า {method} ไม่ได้: {exc}")

    try:
        with Camera(camera_id) as cam, FaceDetector() as detector, \
                GestureRecognizer() as gesture:
            while True:
                frame = cam.read()
                if frame is None:
                    print("อ่านภาพจากกล้องไม่ได้")
                    break

                faces = detector.detect(frame)
                detector.draw(frame, faces)
                g = gesture.detect(frame)
                now = time.time()

                # 3) ทักทายเมื่อมีคนเข้ามาใหม่ (หน่วงเวลา debounce กันสั่น)
                event = presence.update(len(faces) > 0, now)
                if event == "arrived":
                    print("👋 มีคนเข้ามา — โบกมือทักทาย")
                    try:
                        robot.wave()
                    except Exception as exc:  # noqa: BLE001
                        print(f"⚠️ โบกมือไม่ได้: {exc}")
                elif event == "left":
                    print("👋 คนเดินออกไปแล้ว")

                # 1) ท่ามือสั่งงาน (สำคัญสุด — ต้องเห็นท่าเดิมต่อเนื่องกันก่อน)
                if g:
                    if hold["name"] == g:
                        hold["count"] += 1
                    else:
                        hold = {"name": g, "count": 1}
                    if hold["count"] >= GESTURE_HOLD_FRAMES and \
                            now - last_action > GESTURE_COOLDOWN:
                        do_action(g)
                        last_action = now
                        hold = {"name": None, "count": 0}
                else:
                    hold = {"name": None, "count": 0}

                # 2) สบตา (face -> หันหน้าไปทางใบหน้า) — ข้ามขณะทำท่ามือ
                if faces and not g:
                    face = faces[0]  # ใบหน้าที่มีคะแนนสูงสุด
                    cx, cy = face.center
                    h, w = frame.shape[:2]
                    nx = apply_deadzone(cx / w * 2 - 1, DEADZONE)   # -1..1 ซ้าย/ขวา
                    ny = apply_deadzone(-(cy / h * 2 - 1), DEADZONE)  # -1..1 บน/ล่าง
                    # หน้า = +Y -> ก้ม/เงย (nod) = roll; หมุนตัว = base
                    # gain ต่ำลง (25°/15°) กันหุ่นส่ายไปมาจาก noise
                    robot.set_head_pose(z=None,
                                        roll=smooth["roll"].update(ny * 15.0),
                                        pitch=0.0, yaw=0.0, duration=0.05)
                    robot.set_base(smooth["base"].update(nx * 25.0), duration=0.05)

                # แสดงผล (selfie กลับซ้าย/ขวา — detect ยังใช้ frame เดิม)
                text = f"faces:{len(faces)} gesture:{g or '-'}"
                cv2.putText(frame, text, (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.imshow("Reachy Mini DIY - Vision", cv2.flip(frame, 1))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        robot.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
