"""ชั้นควบคุมระดับสูงของ Reachy Mini DIY

backend:
  - "hardware" : ควบคุม STS3215 จริงผ่าน ServoBus (USB-TTL)
  - "sim"      : จำลองการเคลื่อนไหว (ไม่ต้องมีฮาร์ดแวร์)

ใช้งาน:
    with Robot(backend="sim") as robot:      # หรือ backend="hardware"
        robot.wake_up().wave()
"""

from __future__ import annotations

import math
import time

from .stewart import StewartHead


def _rad(deg):
    return math.radians(deg)


def _deg(rad):
    return math.degrees(rad)


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


class Robot:
    # หุ่น DIY: หน้า=+Y -> ก้ม/เงย(nod)=roll, เอียง=pitch
    nod_axis = "roll"

    def __init__(self, backend="sim", port=None, config=None, gui=False):
        """gui: False = ไม่มี, True/'mujoco' = MuJoCo 3D, 'matplotlib' = matplotlib 3D"""
        from config.robot_config import get_config

        self.config = dict(config or get_config())
        self.backend = backend
        self._bus = None
        self._sim = None
        self._viewer = None
        self.head = None
        # ตำแหน่งหัวล่าสุด (สำหรับ interpolation แบบ eased)
        self._pose = {
            "z": float(self.config["stewart"]["z_home"]),
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0,
        }

        if backend == "hardware":
            from .servo_bus import ServoBus

            self._bus = ServoBus(port=port, baudrate=self.config["baudrate"])
            self.head = StewartHead(
                self._bus,
                self.config["servo_ids"]["head"],
                self.config["stewart"],
            )
        elif backend == "sim":
            from .sim_robot import SimRobot

            viewer = self._make_viewer(gui)
            self._sim = SimRobot(self.config, viewer=viewer)
            self._viewer = viewer
        else:
            raise ValueError(f"backend ไม่รู้จัก: {backend} (ใช้ sim / hardware)")

    def _make_viewer(self, gui):
        """สร้าง viewer ตามที่เลือก: True/'mujoco' -> MuJoCo, 'matplotlib' -> matplotlib"""
        if gui is True:
            gui = "mujoco"
        if gui == "mujoco":
            try:
                from .mujoco_sim import MuJoCoSim

                return MuJoCoSim(self.config)
            except Exception as exc:  # noqa: BLE001 - fallback headless
                print(f"[Robot] เปิด MuJoCo ไม่ได้ ({exc}) — รันแบบไม่มี GUI")
                return None
        if gui == "matplotlib":
            from .sim_gui import SimulationViewer

            return SimulationViewer(self.config)
        return None

    # ---------- คุณสมบัติ ----------
    @property
    def is_sim(self):
        return self.backend == "sim"

    def check_connection(self) -> bool:
        """เช็คว่า serial ยังคุยกับ servo ได้จริง — ถ้าไม่ ให้ reconnect

        กันกรณี USB re-enumerate แล้ว handle เก่า "เขียนไม่ error แต่ servo ไม่ขยับ"
        (Windows serial zombie handle) — ใช้ ping กลับเพื่อยืนยัน
        """
        if self.is_sim or self._bus is None:
            return True
        if self._bus.health_check():
            return True
        print("[Robot] servo ไม่ตอบ — ลองเชื่อมต่อพอร์ตใหม่")
        return self._bus.reconnect()

    # ---------- การเคลื่อนไหว ----------
    def set_head_pose(self, z=None, roll=0.0, pitch=0.0, yaw=0.0, duration=1.0):
        """ตั้งท่าหัว: z=mm, มุมเป็นองศา"""
        lim = self.config["limits"]
        st = self.config["stewart"]
        if z is None:
            z = st["z_home"]
        z = _clamp(float(z), *lim["head_z_mm"])
        pitch = _clamp(float(pitch), *lim["head_pitch_deg"])
        roll = _clamp(float(roll), *lim["head_roll_deg"])
        yaw = _clamp(float(yaw), *lim["head_yaw_deg"])
        speed = self.config["motion"]["default_speed"]

        self._pose = {"z": z, "roll": roll, "pitch": pitch, "yaw": yaw}

        if self.is_sim:
            self._sim.set_head_pose(z, roll, pitch, yaw, duration)
        else:
            self.head.set_pose(z, _rad(roll), _rad(pitch), _rad(yaw), speed=speed)
            time.sleep(duration)  # รอให้หัวขยับเสร็จ (hardware)
        return self

    def set_head_pose_eased(self, z=None, roll=0.0, pitch=0.0, yaw=0.0,
                            duration=1.0, method="cartoon", steps=24):
        """ตั้งท่าหัวแบบ eased — interpolate จากท่าปัจจุบันไปเป้าหมาย

        method: linear / min_jerk / ease_in_out / cartoon (เด้งน่ารักแบบการ์ตูน)
        """
        from .motion_easing import time_trajectory

        start = dict(self._pose)
        target = {
            "z": start["z"] if z is None else float(z),
            "roll": float(roll),
            "pitch": float(pitch),
            "yaw": float(yaw),
        }
        steps = max(2, int(steps))
        dt = duration / steps
        for i in range(1, steps + 1):
            t = time_trajectory(i / steps, method)
            pose = {k: start[k] + (target[k] - start[k]) * t for k in target}
            self.set_head_pose(z=pose["z"], roll=pose["roll"],
                               pitch=pose["pitch"], yaw=pose["yaw"], duration=dt)
            if self.is_sim:
                time.sleep(dt)
        return self

    def set_base(self, angle_deg, duration=1.0):
        """หมุนตัว (องศา, 0 = กลาง)"""
        lo, hi = self.config["limits"]["base_deg"]
        angle_deg = _clamp(float(angle_deg), lo, hi)
        if self.is_sim:
            self._sim.set_base(angle_deg, duration)
        else:
            pos = self._bus.deg_to_pos(angle_deg + 180.0)  # 0° = ตำแหน่งกลาง
            self._bus.set_position(
                self.config["servo_ids"]["base"], pos,
                speed=self.config["motion"]["default_speed"],
            )
            time.sleep(duration)  # รอให้หมุนเสร็จ (hardware)
        return self

    def set_antennas(self, left=0.0, right=0.0, duration=0.5):
        """ขยับเสาอากาศ (เรเดียน)"""
        lo, hi = self.config["limits"]["antenna_rad"]
        left = _clamp(float(left), lo, hi)
        right = _clamp(float(right), lo, hi)
        if self.is_sim:
            self._sim.set_antennas(left, right, duration)
        else:
            ids = self.config["servo_ids"]["antennas"]
            homes = (self.config.get("antennas") or {}).get("home_pos") or [2048, 2048]
            for sid, rad, home in zip(ids, (left, right), homes):
                # 0 rad = ท่าชี้ตรง (home ที่ calibrate แล้ว)
                pos = int(round(home + _deg(rad) * 4096.0 / 360.0)) % 4096
                self._bus.set_position(
                    sid, pos, speed=self.config["motion"]["default_speed"])
            time.sleep(duration)  # รอให้เสาอากาศขยับเสร็จ (hardware)
        return self

    # ---------- ท่าทางสำเร็จรูป ----------
    def wake_up(self):
        """ท่าเริ่มต้น (ตั้งตรง)"""
        self.set_head_pose(z=None, roll=0, pitch=0, yaw=0)
        self.set_base(0)
        self.set_antennas(0, 0)
        return self

    def wave(self):
        """โบกเสาอากาศ (ทักทาย)"""
        n = self.config["motion"]["wave_loops"]
        self.set_head_pose(roll=10, duration=0.5)  # ก้มเล็กน้อย (หน้า=+Y -> nod=roll)
        for _ in range(n):
            self.set_antennas(1.0, -1.0, duration=0.3)
            self.set_antennas(-1.0, 1.0, duration=0.3)
        self.set_antennas(0, 0, duration=0.3)
        self.set_head_pose(roll=0, duration=0.5)
        return self

    def look_around(self):
        """มองซ้าย-ขวา (หมุนตัวผ่านมอเตอร์ฐาน — Stewart yaw เสื่อมเมื่อจานตรง)"""
        self.set_base(-45, duration=1.0)
        self.set_base(45, duration=1.5)
        self.set_base(0, duration=1.0)
        return self

    def turn(self, side=1, amount=30):
        """หมุนลำตัวไปซ้าย(-1)/ขวา(1) แล้วกลับ (เหมือนหันไปมองข้าง)"""
        self.set_base(amount * side, duration=0.6)
        self.set_base(0, duration=0.6)
        return self

    # ---------- ท่าทางน่ารัก (ใช้ easing cartoon = เด้งแบบการ์ตูน) ----------
    def bow(self, depth=25):
        """โค้งคำนับ — ก้มหัวลึก ค้าง แล้วกลับ"""
        self.set_head_pose_eased(roll=-depth, duration=1.0, method="cartoon")
        self.set_head_pose_eased(roll=-depth, z=64, duration=0.8, method="cartoon")
        self.set_head_pose_eased(roll=0, z=70, duration=1.2, method="ease_in_out")
        return self

    def nod(self, times=3):
        """พยักหน้า (yes) — ก้ม/เงยเร็ว ๆ แบบเด้ง"""
        for _ in range(times):
            self.set_head_pose_eased(roll=-12, duration=0.3, method="cartoon")
            self.set_head_pose_eased(roll=10, duration=0.3, method="cartoon")
        self.set_head_pose_eased(roll=0, duration=0.3, method="ease_in_out")
        return self

    def shake_head(self, times=2):
        """ส่ายหัว (no) — หันซ้ายขวาผ่านมอเตอร์ฐาน"""
        for _ in range(times):
            self.set_base(-30, duration=0.4)
            self.set_base(30, duration=0.4)
        self.set_base(0, duration=0.4)
        return self

    def head_tilt(self, side=-1):
        """เอียงหัวน่ารัก (เหมือนน้องหมา) — เอียงข้าง ค้าง แล้วกลับ"""
        self.set_head_pose_eased(pitch=18 * side, duration=1.0, method="cartoon")
        self.set_head_pose_eased(pitch=0, duration=0.6, method="ease_in_out")
        return self

    def happy(self):
        """ดีใจ — หมุนลำตัวนิด ๆ + เด้งขึ้นลง + โบกเสาอากาศ"""
        self.set_base(-25, duration=0.5)
        self.set_base(25, duration=0.5)
        self.set_base(0, duration=0.5)
        for _ in range(2):
            self.set_head_pose_eased(z=76, duration=0.4, method="cartoon")
            self.set_head_pose_eased(z=66, duration=0.4, method="cartoon")
        self.set_head_pose_eased(z=70, duration=0.4, method="ease_in_out")
        self.set_antennas(1.0, -1.0, duration=0.3)
        self.set_antennas(-1.0, 1.0, duration=0.3)
        self.set_antennas(0, 0, duration=0.3)
        return self

    def dance(self):
        """เต้น — หมุนลำตัวซ้ายขวา + เอียงหัว + ก้มเงยแบบเด้ง"""
        for _ in range(2):
            self.set_base(-45, duration=0.6)
            self.set_base(45, duration=0.6)
        self.set_base(0, duration=0.6)
        for _ in range(2):
            self.set_head_pose_eased(pitch=-15, duration=0.4, method="cartoon")
            self.set_head_pose_eased(pitch=15, duration=0.4, method="cartoon")
        self.set_head_pose_eased(roll=-12, duration=0.5, method="cartoon")
        self.set_head_pose_eased(roll=12, duration=0.5, method="cartoon")
        self.set_head_pose_eased(roll=0, pitch=0, duration=0.5, method="ease_in_out")
        return self

    def random_cute(self):
        """สุ่มทำท่าทางน่ารัก 1 ท่า (ใช้ตอน idle — ดึงดูดเด็กในงานจัดแสดง)"""
        import random

        acts = [
            lambda: self.nod(2),
            lambda: self.head_tilt(-1),
            lambda: self.head_tilt(1),
            lambda: self.wave(),
            lambda: self.happy(),
            lambda: self.look_around(),
            lambda: self.turn(1),
            lambda: self.turn(-1),
            lambda: self.bow(depth=15),
            lambda: self.dance(),
        ]
        random.choice(acts)()
        return self

    # ---------- การอ่านค่า ----------
    def get_positions(self):
        """อ่านตำแหน่งมอเตอร์ทั้งหมด (dict: id -> pos หรือ None)"""
        if self.is_sim:
            return self._sim.get_state()
        out = {}
        for sid in self._all_ids():
            out[sid] = self._bus.get_position(sid)
        return out

    # ---------- จัดการ lifecycle ----------
    def hold(self):
        """ค้างหน้าต่าง viewer ไว้จนกว่าผู้ใช้จะปิด (ดูหุ่นได้นานๆ)"""
        if self._viewer is not None and hasattr(self._viewer, "wait_until_closed"):
            print("[Robot] หน้าต่างยังเปิดอยู่ — ปิดหน้าต่างเมื่อดูเสร็จ")
            self._viewer.wait_until_closed()

    def close(self):
        if self._bus is not None:
            self._bus.close()
        if self._viewer is not None:
            self._viewer.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    # ---------- ตัวช่วยภายใน ----------
    def _all_ids(self):
        c = self.config["servo_ids"]
        return list(c["head"]) + [c["base"]] + list(c["antennas"])
