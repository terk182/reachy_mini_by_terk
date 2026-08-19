"""STS3215Backend — ขับหุ่น DIY (STS3215) ผ่าน official daemon

เป้าหมาย: ให้ community app / SDK ของ Reachy Mini ทางการสั่งงานหุ่น DIY
ที่ใช้มอเตอร์ Feetech STS3215 ได้ โดยไม่ต้องแก้ app ใด ๆ

หลักการ:
- community app = subprocess ที่ใช้ reachy_mini SDK client คุยกับ daemon
  ผ่าน network → app ไม่รู้ว่าเบื้องหลังเป็นมอเตอร์อะไร
- backend ตัวนี้ subclass MockupSimBackend (implement abstract methods +
  run loop + state ครบแล้ว) แล้ว override ให้ส่ง target joint positions
  ไป servo จริงผ่าน src/servo_bus.py + src/stewart.py
- ถ้าไม่มี serial port → ทำงานแบบ dry-run (พฤติกรรมเหมือน MockupSimBackend)

⚠️ ต้อง calibrate จุดศูนย์มุม orbita ↔ servo pos (ดู ORBITA_CAL) เมื่อมีหุ่นจริง
"""

import math
import sys
import time
from pathlib import Path

import numpy as np

from reachy_mini.io.protocol import (
    HeadPoseMsg,
    JointPositionsMsg,
    MotorControlMode,
)

from ..mockup_sim.backend import MockupSimBackend

# project root = d:\Reachy Mini (ขึ้นไป 7 ระดับจากไฟล์นี้)
PROJECT_ROOT = Path(__file__).resolve().parents[7]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from src.stewart import (  # noqa: E402
        crank_angle_to_leg_length,
        crank_to_servo_pos,
        home_pos_to_center,
    )
    _HAVE_STEWART = True
except Exception:  # noqa: BLE001
    _HAVE_STEWART = False

# ค่า calibrate จุดศูนย์/ทิศของมุม orbita ต่อขา (TODO: calibrate กับหุ่นจริง)
# theta_ours = direction * (theta_official - offset)
ORBITA_CAL = {
    "offset": 0.0,       # rad — จุดศูนย์มุม orbita ที่ตรงกับ servo pos 2048
    "direction": 1,      # +1 / -1 — ทิศการหมุนของแขน (กลับด้านถ้าขาผิดทิศ)
}


class STS3215Backend(MockupSimBackend):
    """Mockup-like backend ที่สั่ง STS3215 จริง (หรือ dry-run ถ้าไม่มีฮาร์ดแวร์)"""

    def __init__(
        self,
        serialport: str | None = None,
        check_collision: bool = False,
        kinematics_engine: str = "AnalyticalKinematics",
        use_audio: bool = True,
    ) -> None:
        super().__init__(
            check_collision=check_collision,
            kinematics_engine=kinematics_engine,
            use_audio=use_audio,
        )
        self.serialport = serialport
        self._bus = None
        self._cfg = None
        self._hw_ready = False
        self._init_hardware()

    # ---------- ฮาร์ดแวร์ ----------
    def _init_hardware(self) -> None:
        """เปิด serial bus + ตรวจว่ามอเตอร์ตอบสนอง (ถ้าไม่มี → dry-run)"""
        try:
            from config.robot_config import get_config
            from src.servo_bus import ServoBus

            self._cfg = get_config()
            self._bus = ServoBus(port=self.serialport,
                                 baudrate=self._cfg["baudrate"])
            first = self._cfg["servo_ids"]["head"][0]
            if not self._bus.ping(first):
                raise RuntimeError(f"มอเตอร์ ID {first} ไม่ตอบสนอง")
            self._hw_ready = True
            self.logger.info(
                f"[STS3215] hardware พร้อม (port={self._bus.port})")
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(f"[STS3215] dry-run (ไม่มีฮาร์ดแวร์): {exc}")
            self._bus = None
            self._hw_ready = False

    def _all_ids(self) -> list[int]:
        if self._cfg is None:
            return []
        c = self._cfg["servo_ids"]
        return list(c["head"]) + [c["base"]] + list(c["antennas"])

    # ---------- control loop ----------
    def run(self) -> None:
        """เหมือน MockupSimBackend แต่ส่งคำสั่งไป servo จริงด้วย"""
        control_period = 1.0 / self.control_frequency

        self.update_head_kinematics_model(
            self._head_joint_positions, self._antenna_joint_positions)

        while not self.should_stop.is_set():
            start_t = time.time()

            if self.target_head_joint_positions is not None:
                self._head_joint_positions = (
                    self.target_head_joint_positions.copy())
                self._drive_head(self._head_joint_positions)
            if self.target_antenna_joint_positions is not None:
                self._antenna_joint_positions = (
                    self.target_antenna_joint_positions.copy())
                self._drive_antennas(self._antenna_joint_positions)

            self.current_head_joint_positions = (
                self._head_joint_positions.copy())
            self.current_antenna_joint_positions = (
                self._antenna_joint_positions.copy())

            self.update_head_kinematics_model(
                self.current_head_joint_positions,
                self.current_antenna_joint_positions,
            )

            if self.ik_required:
                try:
                    self.update_target_head_joints_from_ik(
                        self.target_head_pose, self.target_body_yaw)
                except ValueError:
                    pass  # IK failed, keep current positions

            if (self.joint_positions_publisher is not None
                    and self.pose_publisher is not None
                    and not self.is_shutting_down):
                self.joint_positions_publisher.put(
                    JointPositionsMsg(
                        head_joint_positions=(
                            self.current_head_joint_positions.tolist()),
                        antennas_joint_positions=(
                            self.current_antenna_joint_positions.tolist()),
                    ))
                self.pose_publisher.put(
                    HeadPoseMsg(
                        head_pose=self.get_present_head_pose().tolist()))

            self.ready.set()
            elapsed = time.time() - start_t
            time.sleep(max(0, control_period - elapsed))

    # ---------- สั่ง servo ----------
    def _drive_head(self, joints) -> None:
        """joints: [body_yaw, orbita x 6] (เรเดียน) -> servo จริง"""
        if not self._hw_ready or self._bus is None or not _HAVE_STEWART:
            return
        cfg = self._cfg
        st = cfg["stewart"]
        ids = cfg["servo_ids"]["head"]
        speed = cfg["motion"]["default_speed"]

        # body yaw -> มอเตอร์ฐาน (ID base)
        yaw = float(joints[0])
        self._bus.set_position(
            cfg["servo_ids"]["base"],
            self._bus.deg_to_pos(math.degrees(yaw) + 180.0),
            speed=speed,
        )

        # orbita x 6 -> ขา 6 ข้าง (ผ่าน crank-rod geometry)
        leg_home_pos = st.get("leg_home_pos")
        for i in range(6):
            theta_official = float(joints[1 + i])
            theta = (ORBITA_CAL["direction"]
                     * (theta_official - ORBITA_CAL["offset"]))
            leg = crank_angle_to_leg_length(theta, st["arm_len"], st["rod_len"])
            solution = st["solution"][i]
            if leg_home_pos and i < len(leg_home_pos):
                center = home_pos_to_center(
                    leg_home_pos[i], st["leg_home"],
                    st["arm_len"], st["rod_len"], solution)
            else:
                center = st["pos_center"]
            pos = crank_to_servo_pos(
                leg, st["arm_len"], st["rod_len"], solution, center)
            self._bus.set_position(ids[i], pos, speed=speed)

    def _drive_antennas(self, positions) -> None:
        """positions: [ขวา, ซ้าย] (เรเดียน) -> servo เสาอากาศ"""
        if not self._hw_ready or self._bus is None:
            return
        cfg = self._cfg
        ids = cfg["servo_ids"]["antennas"]
        speed = cfg["motion"]["default_speed"]
        for sid, rad in zip(ids, positions):
            self._bus.set_position(
                sid,
                self._bus.deg_to_pos(math.degrees(rad) + 180.0),
                speed=speed,
            )

    # ---------- motor control mode ----------
    def set_motor_control_mode(self, mode: MotorControlMode) -> None:
        """เปิด/ปิด torque ของมอเตอร์ทั้งหมด"""
        self._motor_control_mode = mode
        if self._bus is not None:
            on = mode == MotorControlMode.Enabled
            for sid in self._all_ids():
                self._bus.set_torque(sid, on)

    # ---------- lifecycle ----------
    def close(self) -> None:
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            super().close()
        except AttributeError:
            pass
