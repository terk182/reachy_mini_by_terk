"""Face detection ด้วย YuNet (OpenCV FaceDetectorYN) — แนวทางเดียวกับ Reachy ทางการ

- ใช้โมเดล YuNet จาก opencv_zoo (face_detection_yunet_2023mar.onnx, ~350KB)
  ดาวน์โหลดอัตโนมัติครั้งแรก (โฟลเดอร์เดียวกับไฟล์นี้)
- ไม่ต้องติดตั้งแพ็กเกจเพิ่ม (cv2.FaceDetectorYN มากับ OpenCV ที่ติดตั้งไว้แล้ว)
- เร็วพอสำหรับ Raspberry Pi 5 (CPU only)

ใช้งาน:
    from src.face_detector import FaceDetector
    detector = FaceDetector()
    faces = detector.detect(frame_bgr)   # list ของ Face
"""

from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass

import cv2

_MODEL_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
              "face_detection_yunet/face_detection_yunet_2023mar.onnx")
_MODEL_FILE = os.path.join(os.path.dirname(__file__),
                           "face_detection_yunet_2023mar.onnx")


def _ensure_model(path=_MODEL_FILE) -> str:
    """ดาวน์โหลดโมเดล YuNet ถ้ายังไม่มี"""
    if os.path.exists(path):
        return path
    print("[FaceDetector] กำลังดาวน์โหลดโมเดล YuNet (~350KB) ...")
    urllib.request.urlretrieve(_MODEL_URL, path)
    return path


@dataclass(frozen=True)
class Face:
    """ใบหน้าที่เจอ (พิกเซล): bbox + ตำแหน่งตา/จมูก + คะแนนความมั่นใจ"""

    bbox: tuple[float, float, float, float]   # (x, y, w, h)
    right_eye: tuple[float, float]
    left_eye: tuple[float, float]
    nose: tuple[float, float]
    score: float

    @property
    def center(self) -> tuple[float, float]:
        """จุดกึ่งกลางกรอบ (x, y)"""
        x, y, w, h = self.bbox
        return (x + w / 2.0, y + h / 2.0)


class FaceDetector:
    """ตรวจจับใบหน้าใน frame BGR ด้วย YuNet"""

    def __init__(self, model_path=_MODEL_FILE,
                 score_threshold=0.6, nms_threshold=0.3, top_k=5000):
        path = _ensure_model(model_path)
        self._score_threshold = score_threshold
        # สร้าง detector (input size ตั้งทีหลังตามขนาด frame จริง)
        self._detector = cv2.FaceDetectorYN.create(
            path, "", (320, 320),
            score_threshold, nms_threshold, top_k,
        )
        self._input_size = (320, 320)
        print("[FaceDetector] YuNet พร้อมใช้งาน")

    def detect(self, frame_bgr) -> list[Face]:
        """คืน list ของ Face (เรียงตามคะแนน) หรือ [] ถ้าไม่เจอ"""
        if frame_bgr is None:
            return []
        h, w = frame_bgr.shape[:2]
        if (w, h) != self._input_size:
            self._detector.setInputSize((w, h))
            self._input_size = (w, h)

        ok, faces = self._detector.detect(frame_bgr)
        if not ok or faces is None:
            return []

        result = []
        for f in faces:
            x, y, fw, fh = float(f[0]), float(f[1]), float(f[2]), float(f[3])
            score = float(f[14]) if len(f) > 14 else float(f[10])
            result.append(Face(
                bbox=(x, y, fw, fh),
                right_eye=(float(f[4]), float(f[5])),
                left_eye=(float(f[6]), float(f[7])),
                nose=(float(f[8]), float(f[9])),
                score=score,
            ))
        return result

    def draw(self, frame_bgr, faces: list[Face]) -> None:
        """วาดกรอบใบหน้า + จุดตา/จมูก ลง frame (แก้ไขในที่)"""
        for face in faces:
            x, y, w, h = (int(v) for v in face.bbox)
            cv2.rectangle(frame_bgr, (x, y), (x + w, y + h),
                          (0, 255, 0), 2)
            cv2.putText(frame_bgr, f"{face.score:.2f}", (x, y - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            for pt in (face.right_eye, face.left_eye, face.nose):
                px, py = int(pt[0]), int(pt[1])
                cv2.circle(frame_bgr, (px, py), 3, (0, 200, 255), -1)

    # ---------- รองรับ `with FaceDetector() as det:` ----------
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
