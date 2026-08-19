"""สาธิต: ติดตามใบหน้าด้วยกล้อง USB -> หุ่นหันหน้าไปทางใบหน้า

วิธีใช้:
    python scripts/demo_face_tracking.py                  # โหมดจำลอง (กล้องแล็ปท็อป)
    python scripts/demo_face_tracking.py --gui            # + หน้าต่าง 3D หุ่น (MuJoCo)
    python scripts/demo_face_tracking.py --real           # โมเดล Reachy Mini แท้ (official daemon)
    python scripts/demo_face_tracking.py --hardware       # หุ่นจริง (STS3215)
    python scripts/demo_face_tracking.py --camera 1       # กล้องตัวอื่น

กด q เพื่อออก
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402

from src.camera import Camera, list_cameras, resolve_camera  # noqa: E402
from src.face_detector import FaceDetector  # noqa: E402
from src.robot import Robot  # noqa: E402

ALPHA = 0.35  # low-pass filter ลดการสั่น


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ติดตามใบหน้าด้วยกล้อง USB")
    parser.add_argument("--hardware", action="store_true", help="ใช้หุ่นจริง")
    parser.add_argument("--port", default=None)
    parser.add_argument("--camera", default="lifecam",
                        help="ชื่อหรือ id กล้อง (default 'lifecam' = กล้อง USB)")
    parser.add_argument("--list-cameras", action="store_true",
                        help="แสดงรายการกล้องแล้วออก")
    parser.add_argument("--gui", action="store_true",
                        help="แสดงหน้าต่าง 3D หุ่น (โหมดจำลองเท่านั้น, MuJoCo)")
    parser.add_argument("--real", action="store_true",
                        help="ใช้โมเดล Reachy Mini แท้ (official daemon)")
    args = parser.parse_args()

    if args.list_cameras:
        print("กล้องที่เจอ:")
        for idx, name in list_cameras():
            print(f"  [{idx}] {name}")
        return

    camera_id = resolve_camera(args.camera)

    backend = "hardware" if args.hardware else "sim"

    if args.real:
        from src.real_robot import RealRobot

        if not RealRobot.available():
            print("⚠️ official daemon ไม่พร้อม — รัน: "
                  "rcamera_idenv\\Scripts\\reachy-mini-daemon.exe --sim ก่อน")
            sys.exit(1)
        robot = RealRobot()
    else:
        robot = Robot(backend=backend, port=args.port,
                      gui="mujoco" if (args.gui and backend == "sim") else False)
    robot.wake_up()

    smooth = {"base": 0.0, "roll": 0.0}

    try:
        with Camera(args.camera) as cam, FaceDetector() as detector:
            while True:
                frame = cam.read()
                if frame is None:
                    print("อ่านภาพจากกล้องไม่ได้")
                    break

                faces = detector.detect(frame)
                detector.draw(frame, faces)

                if faces:
                    face = faces[0]  # ใบหน้าที่มีคะแนนสูงสุด
                    cx, cy = face.center
                    h, w = frame.shape[:2]
                    nx = cx / w * 2 - 1       # -1..1 ซ้าย/ขวา
                    ny = -(cy / h * 2 - 1)    # -1..1 บน/ล่าง
                    target = {
                        "base": nx * 60.0,   # ใบหน้าซ้าย/ขวา -> หมุนตัว (ลบ=ซ้าย, บวก=ขวา)
                        "roll": ny * 25.0,   # ใบหน้าบน/ล่าง -> เงย/ก้ม (หน้า=+Y -> nod=roll)
                    }
                    for k in smooth:
                        smooth[k] += ALPHA * (target[k] - smooth[k])
                    # duration สั้น -> ติดตามลื่น (กัน sleep นานใน hardware)
                    robot.set_head_pose(z=None, roll=smooth["roll"],
                                        pitch=0.0, yaw=0.0, duration=0.05)
                    robot.set_base(smooth["base"], duration=0.05)
                    color = (0, 255, 0)
                else:
                    color = (0, 0, 255)

                cv2.putText(frame, f"faces: {len(faces)}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                # แสดงผลแบบ selfie (กลับซ้าย/ขวา) — detect/ติดตามยังใช้ frame เดิม
                cv2.imshow("Reachy Mini DIY - Face Tracking", cv2.flip(frame, 1))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        robot.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
