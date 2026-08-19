r"""GUI ควบคุมท่าทาง Reachy Mini DIY — ปุ่มท่าพื้นฐานผ่าน Robot API

ใช้ควบคุมหุ่น (hardware) หรือจำลอง (sim) ในหน้าต่างเดียว

วิธีใช้:
    .venv\Scripts\python.exe scripts\pose_gui.py           # hardware (auto-detect COM)
    .venv\Scripts\python.exe scripts\pose_gui.py --sim     # โหมดจำลอง (ไม่ต้องมีหุ่น)

⚠️ หมายเหตุทิศทาง (สำคัญ — หน้า/กล้อง = +Y):
    ก้ม/เงยหน้า     = roll   (ลบ=ก้ม, บวก=เงย)
    เอียงซ้าย/ขวา  = pitch  (ลบ=ซ้าย, บวก=ขวา)
    หันซ้าย/ขวา    = set_base (มอเตอร์ฐาน ID7)
    ยก/ลดหัว      = z (mm)
"""

import argparse
import queue
import sys
import threading
from pathlib import Path

import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.robot import Robot  # noqa: E402

BG = "#1e1e1e"
FG = "#e0e0e0"
ACCENT = "#4da3ff"
BTN_BG = "#2d2d2d"
BTN_ACTIVE = "#0f766e"

# --- ท่าพื้นฐาน (ชื่อปุ่ม, method ของ Robot, พารามิเตอร์) ---
# "nod" = ก้ม/เงย, "tilt" = เอียง — แปลงเป็นแกนจริงตาม nod_axis ของหุ่นที่รัน
#   DIY (หน้า=+Y):  nod=roll, tilt=pitch
#   official (หน้า=+X): nod=pitch, tilt=roll
HEAD_POSES = [
    ("🏠 Home",       "set_head_pose", {"z": 70, "nod": 0, "tilt": 0}),
    ("⬆️ ยกหัว",      "set_head_pose", {"z": 80}),
    ("⬇️ ลดหัว",      "set_head_pose", {"z": 60}),
    ("🙇 ก้มหน้า",     "set_head_pose", {"nod": -20}),
    ("🙆 เงยหน้า",     "set_head_pose", {"nod": 20}),
    ("⬅️ เอียงซ้าย",   "set_head_pose", {"tilt": -20}),
    ("➡️ เอียงขวา",   "set_head_pose", {"tilt": 20}),
]

BODY_POSES = [
    ("🔁 หันซ้าย",     "set_base", {"angle_deg": -30}),  # ลบ = ซ้าย (verified)
    ("🔁 หันขวา",     "set_base", {"angle_deg": 30}),    # บวก = ขวา (verified)
    ("➖ หันกลาง",     "set_base", {"angle_deg": 0}),
]

ACTIONS = [
    ("🌅 ตื่น wake_up",        "wake_up", {}),
    ("👋 ทักทาย wave",         "wave", {}),
    ("👀 มองรอบ look_around",  "look_around", {}),
]

CUTE_POSES = [
    ("🙇 โค้งคำนับ",    "bow", {}),
    ("🙂 พยักหน้า",     "nod", {}),
    ("🙅 ส่ายหัว",      "shake_head", {}),
    ("🐶 เอียงหัวน่ารัก", "head_tilt", {}),
    ("🎉 ดีใจ",        "happy", {}),
    ("🕺 เต้น",         "dance", {}),
]


class PoseApp:
    """หน้าต่างปุ่มท่าทาง: ส่งคำสั่งให้ Robot ผ่าน queue + worker thread"""

    def __init__(self, root: tk.Tk, backend: str, port: str | None = None,
                 real: bool = False):
        self.root = root
        self.backend = backend
        self.port = port
        self.real = real
        self.q: queue.Queue = queue.Queue()
        self._ready = False
        self._nod_axis = "roll"  # default DIY; worker จะอัปเดตหลังต่อหุ่น

        title = "Reachy Mini — ท่าทาง (official)" if real else f"Reachy Mini — ท่าทาง ({backend})"
        root.title(title)
        root.geometry("520x680")
        root.configure(bg=BG)

        self._build_ui()
        self.status_var.set("กำลังเชื่อมต่อ...")

        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    # ---------- UI ----------
    def _build_ui(self):
        header = tk.Label(
            self.root,
            text="ท่าพื้นฐาน Reachy Mini DIY",
            bg=BG, fg=ACCENT, font=("Segoe UI", 14, "bold"))
        header.pack(pady=(14, 2))

        self.status_var = tk.StringVar(value="")
        self.status_label = tk.Label(self.root, textvariable=self.status_var,
                                     bg=BG, fg="#9ca3af", font=("Segoe UI", 10))
        self.status_label.pack(pady=(0, 8))

        # --- หัว (Stewart) ---
        self._section("หัว — Stewart platform")
        grid = tk.Frame(self.root, bg=BG)
        grid.pack(fill="x", padx=14)
        for idx, (label, method, params) in enumerate(HEAD_POSES):
            btn = self._pose_button(grid, label, method, params)
            btn.grid(row=idx // 2, column=idx % 2, sticky="ew",
                     padx=4, pady=4)
        for col in range(2):
            grid.columnconfigure(col, weight=1)

        # --- ฐาน (yaw) ---
        self._section("หมุนตัว — มอเตอร์ฐาน (yaw)")
        base_grid = tk.Frame(self.root, bg=BG)
        base_grid.pack(fill="x", padx=14)
        for idx, (label, method, params) in enumerate(BODY_POSES):
            btn = self._pose_button(base_grid, label, method, params)
            btn.grid(row=0, column=idx, sticky="ew", padx=4, pady=4)
        for col in range(len(BODY_POSES)):
            base_grid.columnconfigure(col, weight=1)

        # --- ท่าทางสำเร็จรูป ---
        self._section("ท่าทางสำเร็จรูป")
        act_grid = tk.Frame(self.root, bg=BG)
        act_grid.pack(fill="x", padx=14)
        for idx, (label, method, params) in enumerate(ACTIONS):
            btn = self._pose_button(act_grid, label, method, params)
            btn.grid(row=0, column=idx, sticky="ew", padx=4, pady=4)
        for col in range(len(ACTIONS)):
            act_grid.columnconfigure(col, weight=1)

        # --- ท่าทางน่ารัก ---
        self._section("ท่าทางน่ารัก")
        cute_grid = tk.Frame(self.root, bg=BG)
        cute_grid.pack(fill="x", padx=14)
        for idx, (label, method, params) in enumerate(CUTE_POSES):
            btn = self._pose_button(cute_grid, label, method, params)
            btn.grid(row=idx // 3, column=idx % 3, sticky="ew", padx=4, pady=4)
        for col in range(3):
            cute_grid.columnconfigure(col, weight=1)

        # --- หมายเหตุ ---
        note = tk.Label(
            self.root,
            text="ทิศทาง: ก้ม/เงย=roll · เอียงซ้าย/ขวา=pitch · หันซ้าย/ขวา=ฐาน (ลบ=ซ้าย, บวก=ขวา)",
            bg=BG, fg="#6b7280", font=("Segoe UI", 9), justify="left")
        note.pack(side="bottom", fill="x", padx=14, pady=10)

    def _section(self, text):
        tk.Label(self.root, text=text, bg=BG, fg="#d1d5db",
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=18, pady=(10, 2))

    def _pose_button(self, parent, label, method, params):
        btn = tk.Button(
            parent, text=label, command=lambda m=method, p=params: self._send(m, p),
            bg=BTN_BG, fg=FG, activebackground=BTN_ACTIVE, activeforeground="white",
            relief="flat", font=("Segoe UI", 11), padx=6, pady=8, cursor="hand2")
        return btn

    # ---------- คำสั่ง ----------
    def _send(self, method, params):
        if not self._ready:
            return
        self.q.put((method, params))

    def _run(self):
        """worker thread: สร้าง Robot/RealRobot แล้ววนรับคำสั่งจาก queue"""
        try:
            if self.real:
                from src.real_robot import RealRobot

                if not RealRobot.available():
                    raise RuntimeError(
                        "official daemon ไม่พร้อม — รัน "
                        "reachy_mini_env\\Scripts\\reachy-mini-daemon.exe --sim ก่อน")
                robot = RealRobot()
            else:
                robot = Robot(backend=self.backend, port=self.port)

            self._nod_axis = getattr(robot, "nod_axis", "roll")
            self._set_status("พร้อม ✅", ACCENT)
            self._ready = True
            while True:
                method, params = self.q.get()
                if method is None:
                    break
                try:
                    self._set_status(f"กำลัง {method}...", "#f59e0b")
                    getattr(robot, method)(**self._resolve(params))
                    self._set_status("พร้อม ✅", ACCENT)
                except Exception as exc:  # noqa: BLE001
                    self._set_status(f"ผิดพลาด: {exc}", "#ef4444")
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"เชื่อมต่อไม่สำเร็จ: {exc}", "#ef4444")

    def _resolve(self, params):
        """แปลง 'nod'/'tilt' → แกนจริงตาม nod_axis ของหุ่นที่ต่ออยู่"""
        out = dict(params)
        nod = self._nod_axis  # "roll" (DIY) / "pitch" (official)
        tilt = "pitch" if nod == "roll" else "roll"
        if "nod" in out:
            out[nod] = out.pop("nod")
        if "tilt" in out:
            out[tilt] = out.pop("tilt")
        return out

    def _set_status(self, text, color=FG):
        def _apply():
            self.status_var.set(text)
            self.status_label.configure(fg=color)
        self.root.after(0, _apply)

    # ---------- ปิด ----------
    def close(self):
        self.q.put((None, {}))
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="GUI ท่าทาง Reachy Mini")
    parser.add_argument("--sim", action="store_true", help="โหมดจำลอง (ไม่ต้องมีหุ่น)")
    parser.add_argument("--real", action="store_true",
                        help="ใช้โมเดล Reachy Mini แท้ (official daemon)")
    parser.add_argument("--port", default=None, help="พอร์ตอนุกรม (hardware)")
    args = parser.parse_args()

    root = tk.Tk()
    app = PoseApp(
        root,
        backend="sim" if args.sim else "hardware",
        port=args.port,
        real=args.real,
    )
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    main()
