"""RealRobot — ขับ Reachy Mini แท้ผ่าน REST API ของ official daemon

มี interface เดียวกับ src/robot.py (set_head_pose / set_base / set_antennas /
wake_up / wave / look_around / close) แต่สั่งงานผ่าน daemon ทางการ
→ แสดงผลเป็น **โมเดล Reachy Mini แท้** ในหน้าต่าง MuJoCo

⚠️ ต้องรัน official daemon ก่อน:
    reachy_mini_env\\Scripts\\reachy-mini-daemon.exe --sim

ใช้งานแทน Robot ได้เลย:
    from src.real_robot import RealRobot
    with RealRobot() as robot:
        robot.wave()
"""

from __future__ import annotations

import json
import math
import urllib.request

from config.robot_config import get_config

DAEMON_URL = "http://localhost:8000"


class RealRobot:
    """ควบคุม Reachy Mini แท้ (official daemon) ผ่าน REST API"""

    # โมเดลทางการ: หน้า=+X -> ก้ม/เงย(nod)=pitch, เอียง=roll (ตรงข้ามหุ่น DIY)
    nod_axis = "pitch"

    def __init__(self, url=DAEMON_URL):
        self.base = url.rstrip("/")
        # z_home ใช้แปลงท่า home ของเรา -> z=0 ของทางการ (กลาง)
        self.z_home_mm = float(get_config()["stewart"]["z_home"])

    # ---------- HTTP ----------
    def _post(self, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload or {}).encode("utf-8")
        req = urllib.request.Request(
            self.base + path, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def available(url=DAEMON_URL, timeout=2) -> bool:
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/docs",
                                        timeout=timeout) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001
            return False

    # ---------- สร้าง payload (แยกไว้ให้ test ได้) ----------
    def _build_goto_payload(self, head=None, antennas=None, body_yaw=None,
                            duration=1.0, interpolation="minjerk") -> dict:
        """head: dict(x,y,z,roll,pitch,yaw) เป็น เมตร/เรเดียน
        antennas: (ขวา, ซ้าย) เรเดียน | body_yaw: เรเดียน
        """
        payload = {"duration": float(duration), "interpolation": interpolation}
        if head is not None:
            payload["head_pose"] = {k: float(v) for k, v in head.items()}
        if antennas is not None:
            payload["antennas"] = [float(antennas[0]), float(antennas[1])]
        if body_yaw is not None:
            payload["body_yaw"] = float(body_yaw)
        return payload

    # ---------- API เดียวกับ Robot ----------
    def goto(self, head=None, antennas=None, body_yaw=None,
             duration=1.0, interpolation="minjerk") -> dict:
        """ส่งคำสั่ง goto ไป daemon ตรงๆ (หน่วย เมตร/เรเดียน)"""
        return self._post(
            "/api/move/goto",
            self._build_goto_payload(head, antennas, body_yaw,
                                     duration, interpolation),
        )

    def set_head_pose(self, z=None, roll=0.0, pitch=0.0, yaw=0.0, duration=1.0):
        """z=mm (สัมพัทธ์กับ z_home), มุม=องศา — เหมือน Robot"""
        z_rel_m = 0.0
        if z is not None:
            z_rel_m = (float(z) - self.z_home_mm) / 1000.0
        self.goto(head={
            "x": 0.0, "y": 0.0, "z": z_rel_m,
            "roll": math.radians(roll),
            "pitch": math.radians(pitch),
            "yaw": math.radians(yaw),
        }, duration=duration)
        return self

    def set_base(self, angle_deg, duration=1.0):
        """หมุนตัว (องศา)"""
        self.goto(body_yaw=math.radians(angle_deg), duration=duration)
        return self

    def set_antennas(self, left=0.0, right=0.0, duration=0.5):
        """เสาอากาศ (เรเดียน) — daemon รับ [ขวา, ซ้าย]"""
        self.goto(antennas=[float(right), float(left)], duration=duration)
        return self

    # ---------- ท่าทางสำเร็จรูป ----------
    def wake_up(self):
        try:
            self._post("/api/move/play/wake_up")
        except Exception:  # noqa: BLE001
            pass
        return self

    def goto_sleep(self):
        try:
            self._post("/api/move/play/goto_sleep")
        except Exception:  # noqa: BLE001
            pass
        return self

    def wave(self):
        self.set_head_pose(pitch=10, duration=0.5)
        for _ in range(3):
            self.set_antennas(left=1.0, right=-1.0, duration=0.3)
            self.set_antennas(left=-1.0, right=1.0, duration=0.3)
        self.set_antennas(0, 0, duration=0.3)
        self.set_head_pose(pitch=0, duration=0.5)
        return self

    def look_around(self):
        self.set_head_pose(yaw=-45, duration=1.0)
        self.set_head_pose(yaw=45, duration=1.5)
        self.set_head_pose(yaw=0, duration=1.0)
        return self

    # ---------- ท่าทางน่ารัก (nod=pitch, tilt=roll — หน้า=+X) ----------
    def bow(self, depth=25):
        """โค้งคำนับ — ก้มหัวลึก ค้าง แล้วกลับ"""
        self.set_head_pose(pitch=-depth, duration=1.0)
        self.set_head_pose(pitch=-depth, z=self.z_home_mm - 6, duration=0.8)
        self.set_head_pose(pitch=0, z=self.z_home_mm, duration=1.2)
        return self

    def nod(self, times=3):
        """พยักหน้า (yes) — ก้ม/เงยเร็ว ๆ"""
        for _ in range(times):
            self.set_head_pose(pitch=-12, duration=0.3)
            self.set_head_pose(pitch=10, duration=0.3)
        self.set_head_pose(pitch=0, duration=0.3)
        return self

    def shake_head(self, times=2):
        """ส่ายหัว (no) — หันซ้ายขวา (official มี neck yaw จริง)"""
        for _ in range(times):
            self.set_head_pose(yaw=-30, duration=0.4)
            self.set_head_pose(yaw=30, duration=0.4)
        self.set_head_pose(yaw=0, duration=0.4)
        return self

    def head_tilt(self, side=-1):
        """เอียงหัวน่ารัก (เหมือนน้องหมา)"""
        self.set_head_pose(roll=18 * side, duration=1.0)
        self.set_head_pose(roll=0, duration=0.6)
        return self

    def happy(self):
        """ดีใจ — เด้งขึ้นลง + โบกเสาอากาศ"""
        for _ in range(2):
            self.set_head_pose(z=self.z_home_mm + 6, duration=0.4)
            self.set_head_pose(z=self.z_home_mm - 4, duration=0.4)
        self.set_head_pose(z=self.z_home_mm, duration=0.4)
        self.set_antennas(1.0, -1.0, duration=0.3)
        self.set_antennas(-1.0, 1.0, duration=0.3)
        self.set_antennas(0, 0, duration=0.3)
        return self

    def dance(self):
        """เต้นเล็ก ๆ — เอียงซ้ายขวา + ก้มเงย"""
        for _ in range(2):
            self.set_head_pose(roll=-15, duration=0.4)
            self.set_head_pose(roll=15, duration=0.4)
        self.set_head_pose(pitch=-12, duration=0.5)
        self.set_head_pose(pitch=12, duration=0.5)
        self.set_head_pose(pitch=0, roll=0, duration=0.5)
        return self

    # ---------- lifecycle ----------
    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
