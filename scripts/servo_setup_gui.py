r"""GUI setup servo STS3215 — สแกน / ตั้ง ID / ทดสอบ

ใช้แทน command line (scan_servos.py / set_servo_id.py / test_servos.py)
ในหน้าต่างเดียว:

วิธีใช้:
    .venv\Scripts\python.exe scripts\servo_setup_gui.py
"""

import queue
import sys
import threading
import time
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.servo_bus import ServoBus, list_serial_ports  # noqa: E402

BG = "#1e1e1e"
FG = "#e0e0e0"
ACCENT = "#4da3ff"


class ServoSetupApp:
    """หน้าต่าง setup servo: เชื่อมต่อ, สแกน, ตั้ง ID, ทดสอบ"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.bus: ServoBus | None = None
        self.q: queue.Queue = queue.Queue()

        root.title("Servo Setup — STS3215")
        root.geometry("640x560")
        root.configure(bg=BG)

        self._build_ui()
        self._refresh_ports()
        self._op_busy = False  # กัน scan/sweep รันพร้อมกัน (ชนกันแล้วผลเพี้ยน)
        root.after(100, self._poll_queue)

    # ---------- UI ----------
    def _build_ui(self):
        # แถวเชื่อมต่อ
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(top, text="พอร์ต:", bg=BG, fg=FG).pack(side="left")
        self.port_var = tk.StringVar(value="auto")
        self.port_combo = ttk.Combobox(top, textvariable=self.port_var, width=20)
        self.port_combo.pack(side="left", padx=(0, 6))
        tk.Button(top, text="↻", command=self._refresh_ports,
                  bg="#374151", fg="white", width=3).pack(side="left", padx=(0, 8))
        tk.Label(top, text="Baud:", bg=BG, fg=FG).pack(side="left")
        self.baud_var = tk.StringVar(value="1000000")
        tk.Entry(top, textvariable=self.baud_var, width=9,
                 bg="#2d2d2d", fg=FG, insertbackground=FG).pack(side="left", padx=(0, 8))
        self.btn_connect = tk.Button(top, text="เชื่อมต่อ", command=self._toggle_connect,
                                     bg="#0c4a6e", fg="white", width=10)
        self.btn_connect.pack(side="left")
        self.status_var = tk.StringVar(value="● ยังไม่เชื่อมต่อ")
        self.status_lbl = tk.Label(top, textvariable=self.status_var, bg=BG, fg="#f87171")
        self.status_lbl.pack(side="left", padx=10)

        # แถวสแกน
        scan_row = tk.Frame(self.root, bg=BG)
        scan_row.pack(fill="x", padx=10, pady=4)
        tk.Button(scan_row, text="🔍 สแกนหา ID", command=self._scan,
                  bg="#166534", fg="white", width=14).pack(side="left")
        self.scan_hint = tk.Label(scan_row, text="(ping ID 1-253)",
                                  bg=BG, fg="#9ca3af")
        self.scan_hint.pack(side="left", padx=8)

        # ส่วนกลาง: listbox + panel ตั้งค่า/ทดสอบ
        mid = tk.Frame(self.root, bg=BG)
        mid.pack(fill="both", expand=True, padx=10, pady=4)

        # listbox พบมอเตอร์
        left = tk.Frame(mid, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        tk.Label(left, text="พบมอเตอร์:", bg=BG, fg=FG).pack(anchor="w")
        self.listbox = tk.Listbox(left, bg="#2d2d2d", fg=FG, height=12,
                                  selectbackground=ACCENT, font=("Consolas", 12))
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(left, command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=sb.set)

        # panel ขวา
        right = tk.Frame(mid, bg=BG, width=220)
        right.pack(side="right", fill="y", padx=(10, 0))

        # ตั้ง ID
        idf = tk.LabelFrame(right, text=" ตั้ง ID ", bg=BG, fg=FG, padx=8, pady=8)
        idf.pack(fill="x", pady=(0, 8))
        tk.Label(idf, text="ID ปัจจุบัน:", bg=BG, fg=FG).grid(row=0, column=0, sticky="w")
        self.old_id = ttk.Spinbox(idf, from_=1, to=253, width=6)
        self.old_id.set(1)
        self.old_id.grid(row=0, column=1, pady=2)
        tk.Label(idf, text="ID ใหม่:", bg=BG, fg=FG).grid(row=1, column=0, sticky="w")
        self.new_id = ttk.Spinbox(idf, from_=1, to=253, width=6)
        self.new_id.set(2)
        self.new_id.grid(row=1, column=1, pady=2)
        tk.Button(idf, text="ตั้ง ID", command=self._set_id,
                  bg="#b45309", fg="white", width=12).grid(row=2, column=0, columnspan=2, pady=4)
        tk.Label(idf, text="⚠️ ตัวเดียวบนบัสเท่านั้น!", bg=BG, fg="#fbbf24",
                 font=("Segoe UI", 8)).grid(row=3, column=0, columnspan=2)

        # ทดสอบ
        tst = tk.LabelFrame(right, text=" ทดสอบ (ID ที่เลือก) ", bg=BG, fg=FG,
                            padx=8, pady=8)
        tst.pack(fill="x")
        row = tk.Frame(tst, bg=BG)
        row.pack(fill="x", pady=2)
        tk.Button(row, text="Ping", command=self._ping, bg="#0c4a6e", fg="white",
                  width=7).pack(side="left", padx=2)
        tk.Button(row, text="Sweep", command=self._sweep, bg="#166534", fg="white",
                  width=7).pack(side="left", padx=2)
        tk.Button(row, text="อ่านค่า", command=self._read, bg="#6d28d9", fg="white",
                  width=7).pack(side="left", padx=2)
        self.test_hint = tk.Label(tst, text="เลือก ID จากรายการซ้ายก่อน",
                                  bg=BG, fg="#9ca3af", font=("Segoe UI", 8))
        self.test_hint.pack(anchor="w", pady=(4, 0))

        # log
        self.log = scrolledtext.ScrolledText(self.root, wrap="word", height=10,
                                             bg="#111111", fg=FG,
                                             font=("Consolas", 10),
                                             insertbackground=FG, state="disabled")
        self.log.pack(fill="both", expand=False, padx=10, pady=(4, 10))

    # ---------- พอร์ต ----------
    def _refresh_ports(self):
        try:
            ports = list_serial_ports()
        except Exception:  # noqa: BLE001
            ports = []
        self.port_combo["values"] = ["auto"] + [d for d, _ in ports]
        if not ports:
            self.port_combo.set("auto")
            self._log("ไม่พบพอร์ตอนุกรม — ตรวจสอบ USB-TTL ที่เสียบอยู่")
        else:
            self._log("พอร์ตที่พบ: " + ", ".join(
                f"{d} ({desc})" for d, desc in ports))

    # ---------- เชื่อมต่อ ----------
    def _toggle_connect(self):
        if self.bus is not None:
            self.bus.close()
            self.bus = None
            self.btn_connect.config(text="เชื่อมต่อ", bg="#0c4a6e")
            self._set_status("● ยังไม่เชื่อมต่อ", "#f87171")
            self._log("ปิดพอร์ตแล้ว")
            return
        port = self.port_var.get().strip()
        port = None if port in ("", "auto") else port
        try:
            baud = int(self.baud_var.get().strip())
        except ValueError:
            messagebox.showerror("ผิดพลาด", "Baud ต้องเป็นตัวเลข")
            return
        try:
            self.bus = ServoBus(port=port, baudrate=baud)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("เชื่อมต่อไม่ได้", str(exc))
            return
        self.btn_connect.config(text="ตัดการเชื่อมต่อ", bg="#b91c1c")
        self._set_status("● เชื่อมต่อแล้ว", "#4ade80")
        self._log(f"เปิดพอร์ต {self.bus.port} @ {baud} baud สำเร็จ")

    # ---------- สแกน ----------
    def _start_op(self, fn):
        """รันงาน bus ใน thread — ทีละงาน (กัน scan/sweep ชนกัน)"""
        if self._op_busy:
            messagebox.showinfo("กำลังทำงาน", "รอให้งานก่อนหน้าจบก่อนครับ")
            return
        self._op_busy = True

        def wrapper():
            try:
                fn()
            finally:
                self._op_busy = False

        threading.Thread(target=wrapper, daemon=True).start()

    def _scan(self):
        if self.bus is None:
            messagebox.showwarning("ยังไม่เชื่อมต่อ", "กด 'เชื่อมต่อ' ก่อน")
            return

        def work():
            self.q.put(("clear", None))
            self._log("เริ่มสแกน ID 1-253 ...")
            found = []
            for sid in range(1, 254):
                try:
                    if self.bus.ping(sid, timeout=0.005):
                        found.append(sid)
                        self.q.put(("found", sid))
                except Exception:  # noqa: BLE001
                    break
            self.q.put(("log", f"สแกนเสร็จ: พบ {len(found)} ตัว {found}"))

        self._start_op(work)

    # ---------- ตั้ง ID ----------
    def _set_id(self):
        if self.bus is None:
            messagebox.showwarning("ยังไม่เชื่อมต่อ", "กด 'เชื่อมต่อ' ก่อน")
            return
        try:
            old = int(self.old_id.get())
            new = int(self.new_id.get())
        except ValueError:
            messagebox.showerror("ผิดพลาด", "ID ต้องเป็นตัวเลข 1-253")
            return
        if not (1 <= new <= 253):
            messagebox.showerror("ผิดพลาด", "ID ใหม่ต้องอยู่ 1-253")
            return
        if not messagebox.askokcancel(
                "ยืนยันตั้ง ID",
                f"ตั้ง ID {old} -> {new}\n\n⚠️ ต้องมีมอเตอร์เพียงตัวเดียวต่อกับ bus!\n"
                f"หลังตั้งแล้วให้ถอดปลั๊ก-เสียบใหม่"):
            return
        if not self.bus.ping(old):
            messagebox.showerror("ไม่พบมอเตอร์", f"ไม่พบมอเตอร์ ID={old}")
            return
        self.bus.set_id(old, new)
        self._log(f"ตั้ง ID {old} -> {new} เรียบร้อย (ถอดปลั๊ก-เสียบใหม่เพื่อให้มีผล)")

    # ---------- ทดสอบ ----------
    def _selected_id(self):
        sel = self.listbox.curselection()
        if sel:
            return int(self.listbox.get(sel[0]))
        messagebox.showwarning("ยังไม่เลือก", "เลือก ID จากรายการซ้ายก่อน")
        return None

    def _ping(self):
        if self._op_busy:
            messagebox.showinfo("กำลังทำงาน", "รอให้งานก่อนหน้าจบก่อนครับ")
            return
        sid = self._selected_id()
        if sid is None or self.bus is None:
            return
        ok = self.bus.ping(sid)
        self._log(f"Ping ID {sid}: {'✅ ตอบสนอง' if ok else '❌ ไม่ตอบสนอง'}")

    def _sweep(self):
        if self._op_busy:
            messagebox.showinfo("กำลังทำงาน", "รอให้งานก่อนหน้าจบก่อนครับ")
            return
        sid = self._selected_id()
        if sid is None or self.bus is None:
            return

        def work():
            self.q.put(("log", f"[ID {sid}] เริ่ม sweep ..."))
            for pos in (2048, 1024, 2048, 3072, 2048):
                self.bus.set_position(sid, pos, speed=1000)
                time.sleep(0.6)
                got = self.bus.get_position(sid)
                load = self.bus.get_load(sid)
                self.q.put(("log", f"  สั่ง {pos:4d} | อ่าน {got} | load={load}"))
            self.q.put(("log", f"[ID {sid}] sweep เสร็จ ✅"))

        self._start_op(work)

    def _read(self):
        if self._op_busy:
            messagebox.showinfo("กำลังทำงาน", "รอให้งานก่อนหน้าจบก่อนครับ")
            return
        sid = self._selected_id()
        if sid is None or self.bus is None:
            return
        pos = self.bus.get_position(sid)
        load = self.bus.get_load(sid)
        volt = self.bus.get_voltage(sid)
        self._log(f"[ID {sid}] pos={pos} load={load} volt={volt}V")

    # ---------- ตัวช่วย ----------
    def _log(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _set_status(self, text, color):
        self.status_var.set(text)
        self.status_lbl.config(fg=color)

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "found":
                    self.listbox.insert("end", payload)
                elif kind == "clear":
                    self.listbox.delete(0, "end")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def on_close(self):
        if self.bus is not None:
            try:
                self.bus.close()
            except Exception:  # noqa: BLE001
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = ServoSetupApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
