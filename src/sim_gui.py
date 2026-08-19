"""GUI 3D สำหรับโหมดจำลอง — ใช้ matplotlib (mplot3d)

แสดงหุ่นยนต์ Reachy Mini DIY:
  - ฐาน/พื้น + เสาค้ำ
  - จานล่าง Stewart (หมุนตาม base)
  - ขา 6 ขา + จานบน (คำนวณด้วย IK จริงจาก stewart.leg_endpoints)
  - หัวพร้อมตำแหน่งกล้อง
  - เสาอากาศ 2 ข้าง

กดปุ่มปิดหน้าต่างเพื่อจบโปรแกรม
"""

from __future__ import annotations

import math

import matplotlib.pyplot as plt
import numpy as np

from .stewart import leg_endpoints

RENDER_LIMIT = 150   # mm (ครึ่งหนึ่งของกล่องวาด)
RENDER_Z_MAX = 230   # mm


def _circle(radius: float, n: int = 48):
    """คืน (xs, ys) จุดวงกลมรัศมี radius"""
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return radius * np.cos(t), radius * np.sin(t)


def _rot_z_xy(points, angle_rad):
    """หมุนจุด (2, N) รอบแกน Z ตามมุม angle_rad -> คืน (2, N)"""
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    r = np.array([[c, -s], [s, c]])
    return r @ np.asarray(points)


class SimulationViewer:
    """หน้าต่าง 3D ที่อัปเดตตาม state ของหุ่นยนต์"""

    def __init__(self, config, title="Reachy Mini DIY - Simulation"):
        self.config = config
        self.st = config["stewart"]
        self.fig = None
        self.ax = None
        plt.ion()
        self.fig = plt.figure(figsize=(8, 8))
        self.ax = self.fig.add_subplot(111, projection="3d")
        self.ax.set_xlabel("X (mm)")
        self.ax.set_ylabel("Y (mm)")
        self.ax.set_zlabel("Z (mm)")
        self.ax.set_box_aspect((1, 1, 1))
        self._last_state = None
        self._title = title

    # ---------- วาด ----------
    def update(self, state):
        """วาดใหม่ตาม state: {head: {...}, base: deg, antennas: [rad, rad]}"""
        self._last_state = state
        self.ax.clear()
        self.ax.set_title(self._title)
        self._draw_robot(state)
        self.ax.set_xlim(-RENDER_LIMIT, RENDER_LIMIT)
        self.ax.set_ylim(-RENDER_LIMIT, RENDER_LIMIT)
        self.ax.set_zlim(0, RENDER_Z_MAX)
        self.fig.canvas.draw_idle()
        plt.pause(0.02)

    def _draw_robot(self, state):
        st = self.st
        base_z = st.get("base_plate_z", 80.0)
        base_angle = math.radians(state["base"])

        # --- ฐาน/พื้น ---
        gx, gy = _circle(55.0)
        self.ax.plot(gx, gy, np.zeros_like(gx), color="0.6", lw=1.5)
        for ang in (0, 90, 180, 270):
            x, y = 45 * math.cos(math.radians(ang)), 45 * math.sin(math.radians(ang))
            self.ax.plot([x, x], [y, y], [0, base_z], color="0.4", lw=2)

        # --- จานล่าง Stewart (หมุนตาม base) ---
        bx, by = _circle(st["base_radius"])
        rot = _rot_z_xy(np.vstack([bx, by]), base_angle)
        self.ax.plot(rot[0], rot[1], np.full_like(rot[0], base_z),
                     color="tab:blue", lw=2)

        # --- ขา + จานบน (ใช้ IK จริง) ---
        head = state["head"]
        base_pts, top_world = leg_endpoints(
            head["z"],
            math.radians(head["roll"]),
            math.radians(head["pitch"]),
            math.radians(head["yaw"]),
            st["base_radius"], st["top_radius"],
            st.get("top_offset_deg", 30.0), st.get("layout", "paired"),
        )
        lift = np.array([[0.0], [0.0], [base_z]])
        base_pts = base_pts + lift
        top_world = top_world + lift

        base_xy = _rot_z_xy(base_pts[:2, :], base_angle)
        top_xy = _rot_z_xy(top_world[:2, :], base_angle)

        for i in range(6):
            self.ax.plot(
                [base_xy[0, i], top_xy[0, i]],
                [base_xy[1, i], top_xy[1, i]],
                [base_pts[2, i], top_world[2, i]],
                color="tab:red", lw=3,
            )

        # จานบน
        top_c = np.hstack([top_xy, top_xy[:, :1]])
        top_z = np.hstack([top_world[2], top_world[2, :1]])
        self.ax.plot(top_c[0], top_c[1], top_z, color="tab:green", lw=2)

        # --- หัว (มีกล้อง) ---
        center = top_world.mean(axis=1)
        head_center = center + np.array([0.0, 0.0, 20.0])
        hc_xy = _rot_z_xy(head_center[:2][:, None], base_angle).flatten()
        self.ax.scatter(hc_xy[0], hc_xy[1], head_center[2],
                        color="tab:purple", s=250, marker="o")
        # กล้อง (ลูกศรชี้ไปด้านหน้า +)
        cam = head_center + np.array([0.0, 25.0, 0.0])
        cam_xy = _rot_z_xy(cam[:2][:, None], base_angle).flatten()
        self.ax.plot([hc_xy[0], cam_xy[0]], [hc_xy[1], cam_xy[1]],
                     [head_center[2], cam[2]], color="tab:cyan", lw=3)

        # --- เสาอากาศ 2 ข้าง ---
        for rad, side in zip(state["antennas"], (1, -1)):
            d = np.array([math.sin(rad) * side, side * 0.35, 1.0])
            d = d / np.linalg.norm(d) * 45.0
            tip = head_center + d
            tip_xy = _rot_z_xy(tip[:2][:, None], base_angle).flatten()
            self.ax.plot([hc_xy[0], tip_xy[0]], [hc_xy[1], tip_xy[1]],
                         [head_center[2], tip[2]], color="tab:orange", lw=3)

        # --- ข้อความสถานะ ---
        status = (
            f"head z={head['z']:.0f} r={math.degrees(head['roll']):.0f} "
            f"p={math.degrees(head['pitch']):.0f} y={math.degrees(head['yaw']):.0f} | "
            f"base={state['base']:.0f}° | "
            f"ant=[{state['antennas'][0]:.2f}, {state['antennas'][1]:.2f}]"
        )
        self.ax.text2D(0.02, 0.97, status, transform=self.ax.transAxes,
                       fontsize=9, color="0.15")

    # ---------- จัดการ lifecycle ----------
    def close(self):
        if self.fig is not None:
            plt.ioff()
            plt.close(self.fig)
            self.fig = None
