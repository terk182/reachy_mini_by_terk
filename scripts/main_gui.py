"""Reachy Mini DIY — Control Panel (GUI สำหรับ setup + run โค้ดต่าง ๆ)

รวมทุกอย่างไว้ในหน้าต่างเดียว:
  - สถานะ (LLM/STT server, ไมค์)
  - ปุ่มรันสคริปต์ทั้งหมด (voice assistant, vision, demo, hardware, diagnostics)
  - ตั้งค่า (model, speech_threshold) → save ลง local_config.json
  - log สดของสคริปต์ที่รัน + ปุ่มหยุด

วิธีใช้:
    .venv\\Scripts\\python.exe scripts\\main_gui.py
"""
from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))

import tkinter as tk  # noqa: E402
from tkinter import messagebox, scrolledtext, ttk  # noqa: E402

from config.robot_config import get_config, save_local_config  # noqa: E402
from src.stt import list_mics, resolve_mic  # noqa: E402


class ControlPanel:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Reachy Mini DIY — Control Panel")
        root.geometry("860x760")
        self.proc: subprocess.Popen | None = None
        self.cfg = get_config()

        self._build_ui()
        self.refresh_status()
        self.refresh_mic()

    # ---------------- UI ----------------
    def _build_ui(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=6, pady=6)

        run_tab = ttk.Frame(nb)
        nb.add(run_tab, text="🎛️ Run")

        # ---- สถานะ ----
        status = ttk.LabelFrame(run_tab, text="สถานะ")
        status.pack(fill="x", padx=6, pady=4)
        self.llm_var = tk.StringVar(value="LLM: ตรวจสอบ...")
        self.stt_var = tk.StringVar(value="STT: ตรวจสอบ...")
        self.mic_var = tk.StringVar(value="ไมค์: ...")
        ttk.Label(status, textvariable=self.llm_var).pack(anchor="w", padx=6)
        ttk.Label(status, textvariable=self.stt_var).pack(anchor="w", padx=6)
        ttk.Label(status, textvariable=self.mic_var).pack(anchor="w", padx=6)
        bar = ttk.Frame(status)
        bar.pack(fill="x", padx=6, pady=2)
        ttk.Button(bar, text="รีเฟรชสถานะ", command=self.refresh_status).pack(side="left")
        ttk.Button(bar, text="ตรวจ AI (test_ai)", command=lambda: self.run("test_ai.py")).pack(side="left", padx=4)
        ttk.Button(bar, text="รายการไมค์", command=lambda: self.run("voice_assistant.py", ["--list-mics"])).pack(side="left")

        # ใช้ scrollable frame สำหรับปุ่มเยอะ
        canvas = tk.Canvas(run_tab, highlightthickness=0)
        vsb = ttk.Scrollbar(run_tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        body = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        # ---- เสียง & AI ----
        ai = ttk.LabelFrame(body, text="เสียง & AI")
        ai.pack(fill="x", padx=6, pady=4)
        self.va_mode = tk.StringVar(value="sim")
        row = ttk.Frame(ai)
        row.pack(fill="x", padx=6, pady=2)
        ttk.Label(row, text="🎙️ Voice Assistant:").pack(side="left")
        ttk.Combobox(row, textvariable=self.va_mode, values=["sim", "hardware", "real"],
                     state="readonly", width=9).pack(side="left", padx=4)
        self.va_nogui = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="ไม่เปิด 3D GUI", variable=self.va_nogui).pack(side="left", padx=4)
        ttk.Button(row, text="▶ Run", command=self.run_voice_assistant).pack(side="left", padx=4)

        ttk.Button(ai, text="💬 Chat GUI", command=lambda: self.run("chat_gui.py", ["--no-gui"])).pack(fill="x", padx=6, pady=1)
        ttk.Button(ai, text="🤖 Test AI services", command=lambda: self.run("test_ai.py")).pack(fill="x", padx=6, pady=1)

        # ---- วิชั่น ----
        vis = ttk.LabelFrame(body, text="วิชั่น (กล้อง)")
        vis.pack(fill="x", padx=6, pady=4)
        ttk.Button(vis, text="👀 Face tracking", command=lambda: self.run("demo_face_tracking.py")).pack(fill="x", padx=6, pady=1)
        ttk.Button(vis, text="✋ Hand tracking", command=lambda: self.run("demo_hand_tracking.py")).pack(fill="x", padx=6, pady=1)

        # ---- ท่าทาง & Demo ----
        demo = ttk.LabelFrame(body, text="ท่าทาง & Demo")
        demo.pack(fill="x", padx=6, pady=4)
        ttk.Button(demo, text="👋 Wave (ทักทาย)", command=lambda: self.run("demo_wave.py")).pack(fill="x", padx=6, pady=1)
        ttk.Button(demo, text="🎲 สุ่มท่าทางน่ารัก", command=lambda: self.run("demo_random.py", ["--forever"])).pack(fill="x", padx=6, pady=1)
        ttk.Button(demo, text="🎭 Pose GUI (DIY)", command=lambda: self.run("pose_gui.py", ["--sim"])).pack(fill="x", padx=6, pady=1)
        ttk.Button(demo, text="🎭 Pose GUI (original — daemon)", command=lambda: self.run("pose_gui.py", ["--real"])).pack(fill="x", padx=6, pady=1)
        ttk.Button(demo, text="🖥️ Simulation (MuJoCo 3D)", command=lambda: self.run("run_simulation.py", ["--hold"])).pack(fill="x", padx=6, pady=1)

        # ---- ฮาร์ดแวร์ ----
        hw = ttk.LabelFrame(body, text="ฮาร์ดแวร์ (STS3215)")
        hw.pack(fill="x", padx=6, pady=4)
        ttk.Button(hw, text="🔍 Scan servos", command=lambda: self.run("scan_servos.py")).pack(fill="x", padx=6, pady=1)
        ttk.Button(hw, text="⚙️ Test servos", command=lambda: self.run("test_servos.py")).pack(fill="x", padx=6, pady=1)
        ttk.Button(hw, text="🛠️ Servo setup GUI", command=lambda: self.run("servo_setup_gui.py")).pack(fill="x", padx=6, pady=1)

        # ---- Calibration (มอเตอร์) ----
        cal = ttk.LabelFrame(body, text="Calibration (มอเตอร์)")
        cal.pack(fill="x", padx=6, pady=4)
        ttk.Button(cal, text="📐 Geometric (คำนวณ leg_home)",
                   command=lambda: self.run("calibrate.py")).pack(fill="x", padx=6, pady=1)
        ttk.Button(cal, text="🎯 Zero หัว (มอเตอร์ 1-6) — จัดหัวแล้วกด Enter ในหน้าต่างใหม่",
                   command=lambda: self.run_console("calibrate.py", ["--hardware"])).pack(fill="x", padx=6, pady=1)
        ttk.Button(cal, text="📡 Zero เสาอากาศ (8-9) — จัดเสาแล้วกด Enter",
                   command=lambda: self.run_console("calibrate.py", ["--hardware", "--antennas"])).pack(fill="x", padx=6, pady=1)
        ttk.Button(cal, text="🔬 Verify ความแม่นยำ (สั่ง→อ่าน→FK)",
                   command=lambda: self.run_console("calibrate.py", ["--verify", "--hardware"])).pack(fill="x", padx=6, pady=1)
        ttk.Button(cal, text="🏠 Set home (มอเตอร์ 1-9)", command=lambda: self.run("set_home.py")).pack(fill="x", padx=6, pady=1)
        ttk.Button(cal, text="🆔 Set servo ID", command=self.ask_set_servo_id).pack(fill="x", padx=6, pady=1)

        # ---- วินิจฉัย ----
        diag = ttk.LabelFrame(body, text="วินิจฉัย")
        diag.pack(fill="x", padx=6, pady=4)
        ttk.Button(diag, text="🧪 Self test", command=lambda: self.run("self_test.py")).pack(fill="x", padx=6, pady=1)

        # ---- ตั้งค่า tab ----
        cfg_tab = ttk.Frame(nb)
        nb.add(cfg_tab, text="⚙️ ตั้งค่า")
        self._build_settings(cfg_tab)

        # ---- log ----
        logf = ttk.LabelFrame(self.root, text="Log")
        logf.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.logbox = scrolledtext.ScrolledText(logf, height=10, state="disabled",
                                                font=("Consolas", 9))
        self.logbox.pack(fill="both", expand=True, padx=4, pady=4)
        btns = ttk.Frame(logf)
        btns.pack(fill="x", padx=4, pady=(0, 4))
        ttk.Button(btns, text="⏹ หยุด process", command=self.stop_proc).pack(side="left")
        ttk.Button(btns, text="ล้าง log", command=self.clear_log).pack(side="left", padx=4)

    def _build_settings(self, tab: ttk.Frame):
        cfg = self.cfg
        llm = cfg["llm"]
        stt = cfg["stt"]

        f = ttk.LabelFrame(tab, text="ตั้งค่า (บันทึกลง config/local_config.json)")
        f.pack(fill="x", padx=6, pady=6)

        self.model_var = tk.StringVar(value=llm.get("model", ""))
        self.threshold_var = tk.StringVar(value=str(stt.get("speech_threshold", 0.01)))
        self.llm_url_var = tk.StringVar(value=llm.get("url", ""))
        self.stt_url_var = tk.StringVar(value=stt.get("stt_url", "") or "")

        def row(label, var):
            r = ttk.Frame(f)
            r.pack(fill="x", padx=6, pady=3)
            ttk.Label(r, text=label, width=18).pack(side="left")
            ttk.Entry(r, textvariable=var).pack(side="left", fill="x", expand=True)

        row("LLM url:", self.llm_url_var)
        row("LLM model:", self.model_var)
        row("STT url:", self.stt_url_var)
        row("speech_threshold:", self.threshold_var)

        ttk.Button(f, text="💾 บันทึก", command=self.save_settings).pack(anchor="w", padx=6, pady=6)
        ttk.Label(f, text="หมายเหตุ: stt_url/llm_url เว้นว่าง = ใช้ default", foreground="gray").pack(anchor="w", padx=6)

    # ---------------- การรัน ----------------
    def run(self, script: str, args: list[str] | None = None):
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("กำลังรัน", "มี process ค้างอยู่ — กด 'หยุด process' ก่อน")
            return
        cmd = [sys.executable, "-X", "utf8", str(SCRIPTS / script), *(args or [])]
        self._start(cmd)

    def run_voice_assistant(self):
        args = []
        mode = self.va_mode.get()
        if mode == "hardware":
            args.append("--hardware")
        elif mode == "real":
            args.append("--real")
        if self.va_nogui.get():
            args.append("--no-gui")
        self.run("voice_assistant.py", args)

    def run_console(self, script: str, args: list[str] | None = None):
        """เปิดสคริปต์ในหน้าต่าง console ใหม่ (สำหรับ interactive input() เช่น calibrate)"""
        cmd = [sys.executable, "-X", "utf8", str(SCRIPTS / script), *(args or [])]
        self._append_log("$ (console ใหม่) " + " ".join(cmd) + "\n")
        subprocess.Popen(cmd, cwd=ROOT, creationflags=subprocess.CREATE_NEW_CONSOLE)

    def ask_set_servo_id(self):
        win = tk.Toplevel(self.root)
        win.title("Set servo ID")
        ttk.Label(win, text="ID ปัจจุบัน:").grid(row=0, column=0, padx=6, pady=4, sticky="e")
        old = ttk.Entry(win, width=8)
        old.insert(0, "1")
        old.grid(row=0, column=1, padx=6, pady=4)
        ttk.Label(win, text="ID ใหม่:").grid(row=1, column=0, padx=6, pady=4, sticky="e")
        new = ttk.Entry(win, width=8)
        new.grid(row=1, column=1, padx=6, pady=4)

        def go():
            try:
                o = int(old.get())
                n = int(new.get())
            except ValueError:
                messagebox.showerror("ผิด", "กรอกเลข ID")
                return
            win.destroy()
            self.run("set_servo_id.py", ["--old", str(o), "--new", str(n)])

        ttk.Button(win, text="▶ Run", command=go).grid(row=2, column=0, columnspan=2, pady=6)

    def _start(self, cmd: list[str]):
        self.clear_log()
        self._append_log("$ " + " ".join(cmd) + "\n")
        self.proc = subprocess.Popen(
            cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        threading.Thread(target=self._pump, args=(self.proc,), daemon=True).start()

    def _pump(self, proc: subprocess.Popen):
        assert proc.stdout is not None
        for line in proc.stdout:
            self.root.after(0, lambda l=line: self._append_log(l))
        proc.wait()
        self.root.after(0, lambda: self._append_log(f"\n[จบ exit={proc.returncode}]\n"))

    def stop_proc(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self._append_log("\n[หยุดแล้ว]\n")
            except Exception as exc:  # noqa: BLE001
                self._append_log(f"\n[หยุดไม่สำเร็จ: {exc}]\n")

    # ---------------- log ----------------
    def _append_log(self, text: str):
        self.logbox.configure(state="normal")
        self.logbox.insert("end", text)
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def clear_log(self):
        self.logbox.configure(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.configure(state="disabled")

    # ---------------- สถานะ ----------------
    def refresh_status(self):
        threading.Thread(target=self._check_status, daemon=True).start()

    def _check_status(self):
        import json
        import urllib.request

        cfg = self.cfg
        llm_url = cfg["llm"]["url"]
        stt_url = cfg["stt"].get("stt_url")

        def http_ok(url: str, timeout=4) -> bool:
            try:
                with urllib.request.urlopen(url, timeout=timeout):
                    return True
            except Exception:  # noqa: BLE001
                return False

        llm_ok = http_ok(llm_url.rstrip("/") + "/api/tags")
        stt_ok = bool(stt_url) and http_ok(stt_url.rstrip("/") + "/health")
        self.root.after(0, lambda: self.llm_var.set(
            f"LLM: {'✅' if llm_ok else '❌'} {llm_url}  model={cfg['llm']['model']}"))
        self.root.after(0, lambda: self.stt_var.set(
            f"STT: {'✅' if stt_ok else '❌'} {stt_url or '(ไม่ได้ตั้ง)'}"))

    def refresh_mic(self):
        try:
            idx = resolve_mic(None)
            name = dict(list_mics()).get(idx, f"index {idx}") if idx is not None else "ไม่พบ"
            self.mic_var.set(f"ไมค์: [{idx}] {name}")
        except Exception as exc:  # noqa: BLE001
            self.mic_var.set(f"ไมค์: ตรวจไม่ได้ ({exc})")

    # ---------------- ตั้งค่า ----------------
    def save_settings(self):
        overrides: dict = {}
        try:
            th = float(self.threshold_var.get())
        except ValueError:
            messagebox.showerror("ผิด", "speech_threshold ต้องเป็นตัวเลข")
            return
        overrides["stt"] = {"speech_threshold": th}
        if self.llm_url_var.get().strip():
            overrides["llm"] = {"url": self.llm_url_var.get().strip()}
        if self.model_var.get().strip():
            overrides["llm"] = overrides.get("llm", {})
            overrides["llm"]["model"] = self.model_var.get().strip()
        if self.stt_url_var.get().strip():
            overrides["stt"]["stt_url"] = self.stt_url_var.get().strip()
        try:
            save_local_config(overrides)
            self.cfg = get_config()
            messagebox.showinfo("บันทึกแล้ว", "บันทึกลง config/local_config.json แล้ว")
            self.refresh_status()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("ผิดพลาด", str(exc))


def main():
    root = tk.Tk()
    ControlPanel(root)
    root.mainloop()


if __name__ == "__main__":
    main()
