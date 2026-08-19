"""Vision: ติดตามมือ

- ถ้ามี mediapipe: ใช้ HandLandmarker (แม่นยำ, ได้ระยะ z)
- ถ้าไม่มี: fallback เป็น skin detection (แค่ x, y)
"""

from __future__ import annotations

import os
import urllib.request

import cv2
import numpy as np

_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/"
              "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task")
_MODEL_FILE = os.path.join(os.path.dirname(__file__), "hand_landmarker.task")


def _ensure_model(path=_MODEL_FILE) -> str:
    if os.path.exists(path):
        return path
    print("[Vision] กำลังดาวน์โหลดโมเดล hand_landmarker.task ...")
    urllib.request.urlretrieve(_MODEL_URL, path)
    return path


class HandTracker:
    """ตรวจจับมือ คืนค่า (x, y, z) ปกติ -1..1

    x = ซ้าย/ขวา, y = บน/ล่าง, z = ใกล้/ไกล
    คืน None เมื่อไม่พบมือ
    """

    def __init__(self, model_path=_MODEL_FILE):
        self.mode = "skin"
        self._landmarker = None
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision

            path = _ensure_model(model_path)
            base = mp_python.BaseOptions(model_asset_path=path)
            options = mp_vision.HandLandmarkerOptions(
                base_options=base,
                num_hands=1,
                min_hand_detection_confidence=0.5,
            )
            self._landmarker = mp_vision.HandLandmarker.create_from_options(options)
            self._mp_image = mp.Image
            self._mp_image_format = mp.ImageFormat
            self.mode = "mediapipe"
            print("[Vision] ใช้ MediaPipe HandLandmarker")
        except Exception as exc:  # noqa: BLE001 - fallback เสมอ
            print(f"[Vision] MediaPipe ไม่พร้อม ({exc}) -> ใช้ skin detection แทน")

    def detect(self, frame_bgr):
        if frame_bgr is None:
            return None
        if self.mode == "mediapipe":
            return self._mediapipe_detect(frame_bgr)
        return self._skin_detect(frame_bgr)

    def _mediapipe_detect(self, frame_bgr):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = self._mp_image(image_format=self._mp_image_format.SRGB, data=rgb)
        result = self._landmarker.detect(image)
        if not result.hand_landmarks:
            return None
        wrist = result.hand_landmarks[0][0]
        return (wrist.x * 2 - 1, -(wrist.y * 2 - 1), wrist.z)

    @staticmethod
    def _skin_detect(frame_bgr):
        """fallback: หา contour ผิวหนังที่ใหญ่ที่สุด (YCrCb)"""
        ycrcb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YCrCb)
        mask = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
        mask = cv2.medianBlur(mask, 5)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        c = max(contours, key=cv2.contourArea)
        if cv2.contourArea(c) < 1500:
            return None
        m = cv2.moments(c)
        if m["m00"] == 0:
            return None
        h, w = frame_bgr.shape[:2]
        cx, cy = m["m10"] / m["m00"], m["m01"] / m["m00"]
        return (cx / w * 2 - 1, -(cy / h * 2 - 1), 0.0)

    def close(self):
        if self._landmarker is not None:
            self._landmarker.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


# --- ท่ามือสั่งงาน (MediaPipe GestureRecognizer) ---
_GESTURE_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/"
                      "gesture_recognizer/gesture_recognizer/float16/1/"
                      "gesture_recognizer.task")
_GESTURE_MODEL_FILE = os.path.join(os.path.dirname(__file__),
                                   "gesture_recognizer.task")


def _ensure_gesture_model(path=_GESTURE_MODEL_FILE) -> str:
    """ดาวน์โหลดโมเดล gesture_recognizer.task (~8MB) ถ้ายังไม่มี"""
    if os.path.exists(path):
        return path
    print("[Vision] กำลังดาวน์โหลดโมเดล gesture_recognizer.task ...")
    urllib.request.urlretrieve(_GESTURE_MODEL_URL, path)
    return path


class GestureRecognizer:
    """รู้จำท่ามือด้วย MediaPipe GestureRecognizer

    คืนคีย์ท่าที่ normalized: thumbs_up / open_palm / fist / victory / point / love
    คืน None เมื่อไม่พบมือหรือไม่มีท่าที่รู้จัก
    """

    GESTURE_MAP = {
        "Thumb_Up": "thumbs_up",
        "Open_Palm": "open_palm",
        "Closed_Fist": "fist",
        "Victory": "victory",
        "Pointing_Up": "point",
        "ILoveYou": "love",
    }

    def __init__(self, model_path=_GESTURE_MODEL_FILE):
        self.mode = "none"
        self._recognizer = None
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision

            path = _ensure_gesture_model(model_path)
            base = mp_python.BaseOptions(model_asset_path=path)
            options = mp_vision.GestureRecognizerOptions(
                base_options=base,
                num_hands=1,
                min_hand_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._recognizer = mp_vision.GestureRecognizer.create_from_options(options)
            self._mp_image = mp.Image
            self._mp_image_format = mp.ImageFormat
            self.mode = "mediapipe"
            print("[Vision] ใช้ MediaPipe GestureRecognizer")
        except Exception as exc:  # noqa: BLE001 - fallback: ไม่มีท่ามือ
            print(f"[Vision] GestureRecognizer ไม่พร้อม ({exc}) — ข้ามท่ามือ")

    def detect(self, frame_bgr):
        if frame_bgr is None or self._recognizer is None:
            return None
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = self._mp_image(image_format=self._mp_image_format.SRGB, data=rgb)
        result = self._recognizer.recognize(image)
        if not result.gestures or not result.gestures[0]:
            return None
        name = result.gestures[0][0].category_name
        if name == "None":
            return None
        return self.GESTURE_MAP.get(name, name)

    def close(self):
        if self._recognizer is not None:
            self._recognizer.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


# --- helpers: ลดการสั่น + ตรวจจับคนเข้ามา ---
def apply_deadzone(value: float, threshold: float = 0.08) -> float:
    """ค่ารอบศูนย์เล็ก ๆ → 0 (กัน servo สั่นตอนมือ/หน้าอยู่กึ่งกลางภาพ)"""
    return 0.0 if abs(value) < threshold else value


class Smoother:
    """Low-pass filter สำหรับค่า scalar — ลดการสั่นของ servo"""

    def __init__(self, alpha=0.3, value=0.0):
        self.alpha = alpha
        self.value = value

    def update(self, target: float) -> float:
        self.value += self.alpha * (target - self.value)
        return self.value

    def reset(self, value=0.0) -> None:
        self.value = value


class PresenceDetector:
    """ตรวจจับ 'มีคนเข้ามาใหม่' / 'คนออกไป' จาก bool 'เห็นหน้าไหม' ต่อเฟรม

    ใช้หน่วงเวลา (debounce) กันการสั่นของ face detection
    """

    def __init__(self, appear_time=1.5, gone_time=3.0):
        self.appear_time = appear_time
        self.gone_time = gone_time
        self.present = False
        self._seen_since = None   # เวลาที่เริ่มเห็นต่อเนื่อง
        self._gone_since = None   # เวลาที่เริ่มไม่เห็นต่อเนื่อง

    def update(self, detected: bool, now: float):
        """คืน 'arrived' / 'left' / None"""
        if detected:
            self._gone_since = None
            if self._seen_since is None:
                self._seen_since = now
            if not self.present and (now - self._seen_since) >= self.appear_time:
                self.present = True
                return "arrived"
        else:
            self._seen_since = None
            if self._gone_since is None:
                self._gone_since = now
            if self.present and (now - self._gone_since) >= self.gone_time:
                self.present = False
                return "left"
        return None
