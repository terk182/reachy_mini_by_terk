"""หุ่นยนต์จำลอง (backend="sim")

ใช้พัฒนา logic / demo ได้โดยไม่ต้องมีฮาร์ดแวร์จริง
(อยากได้หน้าต่าง 3D แบบ MuJoCo ดูคำแนะนำใน README -> official simulation)
"""

from __future__ import annotations

import time


class SimRobot:
    def __init__(self, config, viewer=None):
        self.config = config
        self.viewer = viewer
        self.state = {
            "head": {
                "z": config["stewart"]["z_home"],
                "roll": 0.0,
                "pitch": 0.0,
                "yaw": 0.0,
            },
            "base": 0.0,
            "antennas": [0.0, 0.0],
        }
        self.history = []
        self.dt = config["motion"]["sim_dt"]
        print("[Sim] เริ่มโหมดจำลอง (ไม่ต้องใช้ฮาร์ดแวร์)")
        self._notify()

    def _notify(self):
        """อัปเดต GUI (ถ้ามี)"""
        if self.viewer is not None:
            self.viewer.update(self.state)

    def _log(self, action, **kw):
        self.history.append((time.time(), action, dict(kw)))
        values = " ".join(f"{k}={v:.2f}" for k, v in kw.items())
        print(f"[Sim] {action:9s} | {values}")

    def set_head_pose(self, z, roll, pitch, yaw, duration):
        self.state["head"] = {"z": z, "roll": roll, "pitch": pitch, "yaw": yaw}
        self._log("head", z=z, roll=roll, pitch=pitch, yaw=yaw)
        self._notify()
        time.sleep(min(duration, self.dt * 5))

    def set_base(self, angle_deg, duration):
        self.state["base"] = angle_deg
        self._log("base", angle_deg=angle_deg)
        self._notify()
        time.sleep(min(duration, self.dt * 5))

    def set_antennas(self, left, right, duration):
        self.state["antennas"] = [left, right]
        self._log("antennas", left=left, right=right)
        self._notify()
        time.sleep(min(duration, self.dt * 5))

    def get_state(self):
        return dict(self.state)
