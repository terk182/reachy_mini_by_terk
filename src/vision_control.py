"""Vision ใน background thread — ตามหน้า (สบตา) + ท่ามือสั่งงาน + ตรวจจับคนเข้ามา

ใช้ร่วมกับ voice_assistant:
- ขณะฟังเสียง หุ่นจะตามหน้า (สบตา) ต่อเนื่อง
- เจอท่ามือ/คนเดินเข้ามา → push เหตุการณ์ลง queue ให้ main loop ไปทำแอคชั่น
- ตอนจะพูด/ทำท่า main loop เรียก pause() → หยุดตามหน้า → resume() หลังจบ
"""

from __future__ import annotations

import queue
import threading
import time

import cv2

from .camera import Camera, resolve_camera
from .face_detector import FaceDetector
from .vision import GestureRecognizer, PresenceDetector, Smoother, apply_deadzone

# ท่ามือ (คีย์จาก GestureRecognizer) → ชื่อ method บน robot
GESTURE_ACTIONS = {
    "thumbs_up": "happy",
    "open_palm": "wave",
    "victory": "dance",
    "love": "bow",
    "fist": "shake_head",
    "point": "look_around",
}

ALPHA = 0.2              # low-pass ตามหน้า (นุ่ม)
DEADZONE = 0.12          # โซนกลางไม่ขยับ (กันส่าย)
GESTURE_HOLD_FRAMES = 5  # ต้องเห็นท่าเดิมกี่เฟรมติดกันถึงนับ (กัน false positive)
GESTURE_COOLDOWN = 5.0   # วิ ห้ามท่ามือซ้ำเร็วเกิน


class VisionThread(threading.Thread):
    """รัน vision วนลูปใน thread แยก — ไม่ block main loop

    เหตุการณ์ถูก push ลง self.events (Queue):
      ("arrived",)         มีคนเข้ามาใหม่ (เห็นหน้าต่อเนื่อง)
      ("left",)            คนเดินออกไป
      ("gesture", name)    เห็นท่ามือ (name = thumbs_up/open_palm/...)
    """

    def __init__(self, robot, camera="lifecam", show=False, daemon=True):
        super().__init__(daemon=daemon)
        self.robot = robot
        self.camera_spec = camera
        self.show = show
        self.events: "queue.Queue" = queue.Queue()
        self._paused = threading.Event()   # set = หยุดตามหน้า (ตอนพูด/ทำท่า)
        self._stop = threading.Event()
        self._cooldown_until = 0.0
        self.name = "VisionThread"

    # ---------- ควบคุมจาก main loop ----------
    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def stop(self) -> None:
        self._stop.set()

    # ---------- thread body ----------
    def run(self) -> None:
        try:
            cid = resolve_camera(self.camera_spec)
            print(f"👁️ Vision: ใช้กล้อง index {cid}")
        except OSError as exc:
            print(f"⚠️ Vision เปิดกล้องไม่ได้ ({exc}) — ข้าม vision")
            return

        smooth = {"base": Smoother(ALPHA, 0.0), "roll": Smoother(ALPHA, 0.0)}
        presence = PresenceDetector(appear_time=1.5, gone_time=5.0)
        hold = {"name": None, "count": 0}

        try:
            with Camera(cid) as cam, FaceDetector() as fd, GestureRecognizer() as gr:
                while not self._stop.is_set():
                    frame = cam.read()
                    if frame is None:
                        time.sleep(0.05)
                        continue

                    faces = fd.detect(frame)
                    g = gr.detect(frame)
                    now = time.time()

                    # presence (debounce กันสั่น)
                    ev = presence.update(len(faces) > 0, now)
                    if ev:
                        self.events.put((ev,))

                    # ท่ามือ — ต้องเห็นท่าเดิมต่อเนื่อง + cooldown
                    if g:
                        if hold["name"] == g:
                            hold["count"] += 1
                        else:
                            hold = {"name": g, "count": 1}
                        if hold["count"] >= GESTURE_HOLD_FRAMES and \
                                now >= self._cooldown_until:
                            self.events.put(("gesture", g))
                            self._cooldown_until = now + GESTURE_COOLDOWN
                            hold = {"name": None, "count": 0}
                    else:
                        hold = {"name": None, "count": 0}

                    # ตามหน้า (สบตา) — หยุดเมื่อ main loop สั่ง pause()
                    if faces and not self._paused.is_set():
                        face = faces[0]  # ใบหน้าที่คะแนนสูงสุด
                        cx, cy = face.center
                        h, w = frame.shape[:2]
                        nx = apply_deadzone(cx / w * 2 - 1, DEADZONE)   # -1..1 ซ้าย/ขวา
                        ny = apply_deadzone(-(cy / h * 2 - 1), DEADZONE)  # -1..1 บน/ล่าง
                        # หน้า = +Y -> ก้ม/เงย (nod) = roll; หมุนตัว = base
                        try:
                            self.robot.set_head_pose(
                                z=None,
                                roll=smooth["roll"].update(ny * 15.0),
                                pitch=0.0, yaw=0.0, duration=0.05)
                            self.robot.set_base(
                                smooth["base"].update(nx * 25.0), duration=0.05)
                        except Exception as exc:  # noqa: BLE001
                            print(f"⚠️ Vision ขยับไม่ได้: {exc}")
                            time.sleep(0.5)

                    # หน้าต่าง preview (ถ้าเปิด --show) — วาดกรอบหน้า + ชื่อท่ามือ
                    if self.show:
                        fd.draw(frame, faces)
                        cv2.putText(frame, f"faces:{len(faces)} gesture:{g or '-'}",
                                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                                    (0, 255, 0), 2)
                        cv2.imshow("Reachy Mini DIY - Vision", cv2.flip(frame, 1))
                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            print("👁️ กด q — ปิดหน้าต่าง vision")
                            self._stop.set()
                            try:
                                cv2.destroyWindow("Reachy Mini DIY - Vision")
                            except Exception:  # noqa: BLE001
                                pass

                    time.sleep(0.03)  # ~30 fps cap
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ Vision thread หยุด: {exc}")
        finally:
            if self.show:
                try:
                    cv2.destroyAllWindows()
                except Exception:  # noqa: BLE001
                    pass
