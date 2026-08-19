"""อ่านภาพจาก USB camera ด้วย OpenCV (DirectShow backend)

บน Windows ใช้ CAP_DSHOW เพราะ:
- ลำดับ index ตรงกับ DirectShow (ตรวจชื่อได้ด้วย pygrabber)
- เปิดกล้อง USB generic (UVC) ได้เสถียรกว่า MSMF
"""

from __future__ import annotations

import cv2


def list_cameras() -> list[tuple[int, str]]:
    """คืน [(index, ชื่อกล้อง)] เรียงตามลำดับ DirectShow

    ใช้ pygrabber ถ้ามี (ได้ชื่อจริง) ถ้าไม่มี fallback สแกน index 0..7
    """
    try:
        from pygrabber.dshow_graph import FilterGraph

        devices = FilterGraph().get_input_devices()
        return [(i, name) for i, name in enumerate(devices) if name]
    except Exception:  # noqa: BLE001
        out = []
        for i in range(8):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                out.append((i, f"camera {i}"))
            cap.release()
        return out


def resolve_camera(spec) -> int:
    """แปลง spec (None / int / ชื่อบางส่วน) -> index กล้อง

    - None -> 0
    - int  -> ใช้ตรง ๆ
    - str  -> match ชื่อกล้องแบบ case-insensitive (เช่น "usb", "lifecam")
    """
    if spec is None:
        return 0
    if isinstance(spec, int):
        return spec
    for idx, name in list_cameras():
        if str(spec).lower() in name.lower():
            return idx
    if str(spec).isdigit():
        return int(spec)
    raise OSError(f"ไม่พบกล้อง '{spec}' — ใช้ --list-cameras ดูรายการ")


class Camera:
    def __init__(self, camera_id=0, width=640, height=480):
        self.camera_id = camera_id
        self.cap = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise OSError(f"เปิดกล้องไม่สำเร็จ (camera_id={camera_id})")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def read(self):
        """คืน frame BGR หรือ None ถ้าอ่านไม่ได้"""
        ok, frame = self.cap.read()
        return frame if ok else None

    def release(self):
        self.cap.release()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()
        return False
