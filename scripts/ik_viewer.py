"""Interactive IK viewer สำหรับ Stewart platform (หัว 6 DOF) Reachy Mini DIY

ปรับ z / roll / pitch / yaw ด้วย slider แล้วดูสดๆ:
  - ขา 6 ขาในรูป 3D (จานล่าง -> จานบน)
  - ความยาวขา 6 ขา (mm)
  - มุม crank 6 ขา (องศา)
  - ตำแหน่ง servo 6 ขา (0-4095)

ใช้ค่าจาก config/robot_config.py + calibration.json (get_config) เหมือนหุ่นจริง

วิธีใช้:
    .venv\\Scripts\\python.exe scripts\\ik_viewer.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.widgets import Slider

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.robot_config import get_config  # noqa: E402
from src.stewart import (  # noqa: E402
    crank_angle_2bar,
    crank_to_servo_pos,
    leg_endpoints,
    leg_lengths,
)


def _circle3d(radius, z, n=48):
    """วงกลมบนระนาบ z (สำหรับวาดจาน)"""
    t = np.linspace(0, 2 * np.pi, n, endpoint=True)
    return radius * np.cos(t), radius * np.sin(t), np.full_like(t, z)


def main() -> None:
    cfg = get_config()
    st = cfg["stewart"]
    lim = cfg["limits"]

    base_r = st["base_radius"]
    top_r = st["top_radius"]
    layout = st.get("layout", "paired")
    top_offset = st.get("top_offset_deg", 30.0)
    arm = st.get("arm_len", 40.0)
    rod = st.get("rod_len", 85.0)
    solutions = st.get("solution", [0] * 6)
    pos_center = st.get("pos_center", 2048)
    z_home = float(st["z_home"])

    # จุดจานล่างคงที่ (z=0) — จานบนถูกหมุน/เลื่อนตาม pose
    base_pts, _ = leg_endpoints(z_home, 0.0, 0.0, 0.0,
                                base_r, top_r, top_offset, layout)

    fig = plt.figure(figsize=(11, 8))
    ax = fig.add_subplot(111, projection="3d")
    plt.subplots_adjust(left=0.02, bottom=0.32, top=0.96, right=0.98)

    def _add_slider(label, lo, hi, init, ypos, fmt="%.1f"):
        axs = plt.axes([0.15, ypos, 0.72, 0.025])
        return Slider(axs, label, lo, hi, valinit=init, valfmt=fmt)

    sl_z = _add_slider("z (mm)", *lim["head_z_mm"], z_home, 0.22)
    sl_roll = _add_slider("roll (deg)", *lim["head_roll_deg"], 0.0, 0.17)
    sl_pitch = _add_slider("pitch (deg)", *lim["head_pitch_deg"], 0.0, 0.12)
    sl_yaw = _add_slider("yaw (deg)", *lim["head_yaw_deg"], 0.0, 0.07)

    info = fig.text(0.03, 0.94, "", va="top", fontsize=8, family="monospace")

    def update(_=None):
        z = sl_z.val
        roll = math.radians(sl_roll.val)
        pitch = math.radians(sl_pitch.val)
        yaw = math.radians(sl_yaw.val)

        _, top_world = leg_endpoints(z, roll, pitch, yaw,
                                     base_r, top_r, top_offset, layout)
        lengths = leg_lengths(z, roll, pitch, yaw,
                              base_r, top_r, top_offset, layout)

        ax.clear()
        ax.set_title(
            f"IK Viewer — z={z:.1f}mm  roll={sl_roll.val:+.1f}°  "
            f"pitch={sl_pitch.val:+.1f}°  yaw={sl_yaw.val:+.1f}°")
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
        ax.set_zlabel("Z (mm)")

        # จานล่าง
        ax.plot(*_circle3d(base_r, 0.0), color="tab:blue", lw=1.5, alpha=0.7)
        ax.scatter(*base_pts, color="tab:blue", s=18, depthshade=False)

        # จานบน (เส้นโครง + จุดยึดก้าน)
        for i in range(6):
            j = (i + 1) % 6
            ax.plot([top_world[0, i], top_world[0, j]],
                    [top_world[1, i], top_world[1, j]],
                    [top_world[2, i], top_world[2, j]],
                    color="tab:green", lw=1.5, alpha=0.7)
        ax.scatter(*top_world, color="tab:green", s=18, depthshade=False)

        # ขา 6 ขา (สีตามความยาว) + สรุป IK
        lo, hi = min(lengths), max(lengths)
        span = (hi - lo) or 1.0
        lines = []
        for i, L in enumerate(lengths):
            sol = solutions[i] if i < len(solutions) else 0
            theta = crank_angle_2bar(L, arm, rod, sol)
            pos = crank_to_servo_pos(L, arm, rod, sol, pos_center)
            color = plt.cm.viridis((L - lo) / span)
            ax.plot([base_pts[0, i], top_world[0, i]],
                    [base_pts[1, i], top_world[1, i]],
                    [base_pts[2, i], top_world[2, i]],
                    color=color, lw=2.5)
            lines.append(f"ขา{i + 1}: L={L:6.2f} mm  "
                         f"θ={math.degrees(theta):+7.2f}°  servo={pos:4d}")

        info.set_text(
            f"เรขาคณิต: base={base_r} top={top_r} arm={arm} rod={rod} "
            f"layout={layout}  leg_home={st.get('leg_home', '-')}\n"
            + "\n".join(lines))

        rng = max(base_r, top_r) + arm + rod + 10
        ax.set_xlim(-rng, rng)
        ax.set_ylim(-rng, rng)
        ax.set_zlim(0, z_home + arm + rod + 10)
        fig.canvas.draw_idle()

    for s in (sl_z, sl_roll, sl_pitch, sl_yaw):
        s.on_changed(update)
    update()
    print("ปิดหน้าต่างเพื่อจบโปรแกรม")
    plt.show()


if __name__ == "__main__":
    main()
