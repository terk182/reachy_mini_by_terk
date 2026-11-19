"""GUI รวม "แชท + กล้อง" ของ Reachy Mini DIY (Tkinter, ไม่ต้องลงแพ็กเกจใหม่)

หน้าตา: ซ้าย = ภาพจากกล้อง USB (มีกรอบใบหน้า/FPS) · ขวา = แชทกับ LLM
       ล่าง = แถบสถานะ (backend, โมเดล, กล้อง)

ฟีเจอร์:
- ธีม "kid" น่ารัก ๆ (ค่าเริ่มต้น): หัวเรื่อง + หน้าหุ่น (kaomoji ตามอารมณ์),
  แชทเป็น bubble (คุณ = ฟ้า / พี่ทด = เหลือง / น้องนุ = เขียว), ปุ่มสีสันโหญ่ ๆ — เปลี่ยนเป็นธีมเดิมด้วย --theme dark
- พิมพ์คุย → LLM (persona พี่ทด เด็ก ๆ) → หุ่นขยับตามอารมณ์ + พูด (เปิด/ปิดได้)
- ปุ่ม 🎤 พูด — ใช้ STT (remote/local ตาม config) + เลือกไมค์จาก dropdown ได้
- กล้อง: เลือกอุปกรณ์, เปิด/ปิด, ตรวจจับใบหน้า (YuNet), แสดง FPS
- LLM เรียก tool ได้ (เต้น/โบกมือ/ร้องเพลง) เหมือน voice_assistant
- ฉีดวัน–เวลา–เทศกาล (src/thai_time) ให้หุ่นตอบเรื่องวันได้
- เลือกกล้อง/ไมค์จาก dropdown + ปุ่ม 🔄 สแกนใหม่ (หลังเสียบ/ถอดอุปกรณ์)
  → ค่าไมค์ถูกจำไว้ใน config/local_config.json อัตโนมัติ

วิธีใช้:
    .venv\\Scripts\\python.exe scripts\\app_gui.py                 # sim (ไม่เปิด 3D)
    .venv\\Scripts\\python.exe scripts\\app_gui.py --robot-gui     # sim + หน้าต่าง MuJoCo 3D
    .venv\\Scripts\\python.exe scripts\\app_gui.py --hardware      # หุ่นจริง STS3215
    .venv\\Scripts\\python.exe scripts\\app_gui.py --camera 1      # ระบุ index กล้อง
    .venv\\Scripts\\python.exe scripts\\app_gui.py --list-cameras  # ดูก่อนว่าใช้ index ไหน
    .venv\\Scripts\\python.exe scripts\\app_gui.py --list-mics     # ดูไมค์ทั้งหมด
    .venv\\Scripts\\python.exe scripts\\app_gui.py --theme dark     # โหมดหน้าตาเดิม (สําหรับ dev)
    .venv\\Scripts\\python.exe scripts\\app_gui.py --smoke 5       # ทดสอบเอง (ซ่อนหน้าต่าง,
                                                                   #   รัน 5 วิ แล้วออก)
"""

import argparse
import queue
import sys
import threading
import time
from pathlib import Path

import tkinter as tk
from tkinter import scrolledtext

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402
from PIL import Image, ImageTk  # noqa: E402

from config.robot_config import get_config  # noqa: E402
from src.camera import Camera, list_cameras, resolve_camera  # noqa: E402
from src.expressions import (  # noqa: E402
    apply_emotion,
    detect_emotion,
    speak_with_motion,
    strip_emotion_tag,
)
from src.dual_llm import TwoRobotConsultant  # noqa: E402
from src.llm import OllamaClient  # noqa: E402
from src.robot import Robot  # noqa: E402
from src.robot_tools import TOOLS, execute as execute_tool  # noqa: E402
from src.robot_tools import as_text_tool_call  # noqa: E402
from src.thai_time import build_time_context  # noqa: E402

# ---------- ธีม ----------
# kid = โทนเด็กน่ารัก (สีฟ้าอ่อน–เหลือง–ชมพู, ฟอนต์ใหญ่) · dark = โทนเดิมสำหรับ dev/ผู้ใหญ่
THEMES = {
    "kid": {
        "bg": "#EAF6FF", "fg": "#263238", "panel": "#FFFFFF",
        "video_bg": "#D4ECFF",
        "bubble_user": "#CDEBFF", "bubble_robot": "#FFF3BF",
        "bubble_robot_b": "#DFF5E3", "sys_fg": "#78909C",
        "accent": "#FF8FAB", "accent_hi": "#FF6F91",
        "accent2": "#FFD166", "accent2_hi": "#FFC233",
        "mint": "#9BE7C4", "mint_hi": "#6FDCA8",
        "status_bg": "#4CC9F0",
        "ready_bg": "#3ECF6E",     # 🟢 พร้อมรับคำสั่งเสียง / พูดเสร็จ
        "ready_soft": "#D8F5DE",   # 🟢 พื้นหลังทั้งแอปตอนพร้อม (เขียวอ่อน)
        "font": ("Leelawadee UI", 11),
        "font_bold": ("Leelawadee UI", 11, "bold"),
        "font_title": ("Leelawadee UI", 18, "bold"),
        "font_chat": ("Leelawadee UI", 12),
        "font_entry": ("Leelawadee UI", 13),
        "face_font": ("Segoe UI Symbol", 22),
    },
    "dark": {
        "bg": "#1e1e1e", "fg": "#e0e0e0", "panel": "#252526",
        "video_bg": "#000000",
        "bubble_user": "#264F78", "bubble_robot": "#33363B",
        "bubble_robot_b": "#2E4034", "sys_fg": "#9cdcfe",
        "accent": "#3C6E71", "accent_hi": "#4C8C90",
        "accent2": "#4A4E69", "accent2_hi": "#5A5F80",
        "mint": "#3C6E71", "mint_hi": "#4C8C90",
        "status_bg": "#007acc",
        "ready_bg": "#2EA043",     # 🟢 พร้อมรับคำสั่งเสียง / พูดเสร็จ
        "ready_soft": "#1E3A26",   # 🟢 พื้นหลังทั้งแอปตอนพร้อม (เขียวเข้ม)
        "font": ("Consolas", 11),
        "font_bold": ("Consolas", 11, "bold"),
        "font_title": ("Consolas", 14, "bold"),
        "font_chat": ("Consolas", 11),
        "font_entry": ("Consolas", 12),
        "face_font": ("Consolas", 18),
    },
}

# หน้าหุ่น (kaomoji) ตามอารมณ์ — แสดงบนหัวหน้าต่าง
FACE_BY_EMOTION = {
    "happy": "(＾▽＾)", "sad": "(╥﹏╥)", "angry": "(｀Д´)",
    "surprised": "(⊙_⊙)", "neutral": "(・_・)",
}
FACE_READY = "(◕‿◕)"     # พร้อมคุย
FACE_THINKING = "(・ω・)"  # กำลังคิด
FACE_LISTEN = "(・_・)?"   # กำลังฟัง

VIDEO_W, VIDEO_H = 640, 480
FPS_TARGET = 25.0     # จำกัด fps การแสดง (ประหยัด CPU)


def _fill_option_menu(menu: tk.OptionMenu, var: tk.StringVar,
                      values: list[str], callback) -> None:
    """เติมรายการใน OptionMenu ใหม่ (ใช้ตอนสแกนอุปกรณ์) โดยเรียก callback เฉพาะตอนผู้ใช้คลิก"""
    sub = menu["menu"]
    sub.delete(0, "end")
    for value in values:
        def _select(v=value):
            var.set(v)
            callback(v)
        sub.add_command(label=value, command=_select)


def _index_from_label(label: str) -> int | None:
    """'1: Microsoft LifeCam' -> 1 (คืน None ถ้าอ่านไม่ได้)"""
    head = label.split(":", 1)[0].strip()
    return int(head) if head.isdigit() else None


class AppGUI:
    """หน้าต่างเดียว: วิดีโอกล้อง + แชท + ปุ่มควบคุมหุ่น"""

    def __init__(self, root: tk.Tk, robot, llm: OllamaClient, cam_spec="lifecam",
                 theme: str = "kid", robot_b=None,
                 consultant: TwoRobotConsultant | None = None):
        self.root = root
        self.robot = robot
        self.robot_b = robot_b              # 🤝 หุ่นตัวที่ 2 (None = โหมดหุ่นเดี่ยว)
        self.consultant = consultant        # 🤝 TwoRobotConsultant หรือ None
        self._b_name = getattr(consultant, "name_b", None) or "น้องนุ"
        _cfg0 = get_config()
        _robot0 = _cfg0.get("robot") or {}
        self._a_name = _robot0.get("name") or "พี่ทด"
        self._a_voice = _robot0.get("voice")            # "male"/"female"/None
        self._b_voice = (_cfg0.get("robot_b") or {}).get("voice")
        self.llm = llm
        self.history: list[dict] = []
        self.T = THEMES.get(theme, THEMES["kid"])   # โทนสี/ฟอนต์ทั้งแอป

        # --- สถานะกล้อง ---
        self._cam_spec = cam_spec
        self._cam_stop = threading.Event()
        self._cam_thread: threading.Thread | None = None
        self._video_q: queue.Queue = queue.Queue(maxsize=2)
        self._ui_q: queue.Queue = queue.Queue()   # คิวงาน UI จาก worker thread
        self._photo = None            # อ้างอิง ImageTk กัน GC ลบภาพ
        self._faces_on = True         # mirror ของ checkbox (อ่านจาก thread ปลอดภัย)
        self._tracking = True         # 👀 ขยับหุ่นตามใบหน้า (mirror ของ checkbox)
        self._action_busy = False     # กำลังทำท่าจากปุ่ม — หยุดติดตามหน้าชั่วคราว
        self._track_last = 0.0        # เวลาสั่งขยับตามหน้าครั้งล่าสุด
        self._track_xy = [0.0, 0.0]   # (base, roll) หลัง low-pass
        self._track_cmd = [0.0, 0.0]  # ค่าสั่งล่าสุดที่ส่งมอเตอร์
        self._gesture_on = True       # ✋ ทำท่าตามมือ (mirror ของ checkbox)
        self._gesture_tick = 0        # นับเฟรม — ตรวจจับท่ามือทุก ~3 เฟรม
        self._gesture_hold = {"name": None, "count": 0}
        self._gesture_cooldown = 0.0  # ห้ามท่าเดิมซ้ำเร็วเกิน
        self._gesture_rec = None      # GestureRecognizer (โหลด lazy)
        # checkbox เป็น "แหล่งความจริง" ของสถานะ (ค่าเริ่มต้น = เปิดทั้งหมด)
        self._faces_var = tk.BooleanVar(master=root, value=True)   # 🔍 จับหน้า
        self._track_var = tk.BooleanVar(master=root, value=True)   # 👀 ตามหน้า
        self._gesture_var = tk.BooleanVar(master=root, value=True)  # ✋ ตามมือ
        self._speak_var = tk.BooleanVar(master=root, value=True)    # 🔊 พูดตอบ
        self._anim_var = tk.BooleanVar(master=root, value=True)     # 🎭 ขยับตามอารมณ์
        self._listen_var = tk.BooleanVar(master=root, value=True)   # 🎧 ฟังอัตโนมัติ
        self._speaking = False        # กำลังเล่นเสียงอยู่ (กันฟังอัตโนมัติชน)
        self._listening = False       # ★ กำลังฟังอยู่ — กันฟังซ้อน (race → ได้ยินเสียงหุ่นเอง/ข้อความมั่ว)
        self._closing = False         # กำลังปิดหน้าต่าง
        self._detector = None         # YuNet (สร้างตอนใช้ครั้งแรก)
        self._frames_shown = 0        # นับเฟรมที่แสดง (ใช้ตอน --smoke)
        self._busy = False            # กำลังรอ LLM ตอบ
        self._busy_since = 0.0        # ⏱ เริ่ม busy เมื่อไหร่ (กันค้างถาวร)
        self._speak_since = 0.0       # ⏱ เริ่มขยับ/พูดเมื่อไหร่ (กันค้างถาวร)
        self._led_ready = None        # สถานะไฟ (None = ยังไม่รู้ → วาดรอบแรก)
        self._transcribing = False    # กำลังถอดความเสียง (ไม่โชว์ไฟเขียว)
        self._refresh_mic = False     # ธง: ขอรีเฟรชสตรีมไมค์หลังหุ่นพูดจบ
        # 🎚 เกณฑ์รับเสียง (สไลเดอร์) + 📊 VU meter บน GUI
        self._thr_manual = None       # ค่าที่ผู้ใช้ตั้งเอง (None = อัตโนมัติ ให้ calibrate ปรับ)
        self._thr_syncing = False     # กัน command ยิงซ้ำตอน sync สไลเดอร์เอง
        self._thr_last = None         # ค่าเกณฑ์ที่ประมวลผลแล้วล่าสุด (กันยิงซ้ำ)
        self._thr_save_job = None     # after-id ของการบันทึกแบบหน่วง (debounce)
        self._vu_peak = 0.0           # 📊 เส้น peak-hold บน VU meter (ค่อย ๆ ลด)
        # 🔔 popup เตือนจังหวะพูด (หน้าต่างลอย ไม่แย่งโฟกัส)
        self._popup = None            # Toplevel — สร้าง lazy ครั้งแรกที่ใช้
        self._popup_state = None      # None / "wait" (รอหุ่น) / "go" (ถึงตาคุณ)
        self._popup_text = None       # ข้อความที่โชว์อยู่ (กันอัปเดตซ้ำ)
        self._popup_job = None        # after-id ของการซ่อนอัตโนมัติ
        self._muted_prev = False      # สถานะ mute รอบก่อน (จับ "เพิ่งพูดจบ")

        # --- สถานะไมค์ (ใช้ตอนกด 🎤) ---
        self._mic_index: int | None = None
        self._devices_ready = False   # กันบันทึก config ตอนสร้างหน้าต่างรอบแรก
        self._save_audio = False      # --save-audio: บันทึก WAV ทุกครั้งที่ฟัง
        self._cont = None             # ไมค์เปิดค้าง (ContinuousMic) — โหลดแบบ lazy

        self._build_ui()

        # ตัวเฝ้าสาย USB: กัน zombie handle (เขียนได้แต่ servo ไม่ขยับ) — ตรวจทุก 10 วิ
        threading.Thread(target=self._conn_watchdog, daemon=True).start()

    # ================= UI =================
    def _build_ui(self):
        T = self.T
        self.root.title(f"{self._a_name} — แชท & กล้อง")
        self.root.geometry("1140x690")
        self.root.configure(bg=T["bg"])

        # ---------- หัวเรื่องน่ารัก ๆ + หน้าหุ่น (kaomoji) ----------
        header = tk.Frame(self.root, bg=T["bg"])
        header.pack(fill="x", padx=10, pady=(8, 0))
        self._face_label = tk.Label(header, text=FACE_READY, font=T["face_font"],
                                    bg=T["bg"], fg=T["accent_hi"])
        self._face_label.pack(side="left")
        titles = tk.Frame(header, bg=T["bg"])
        titles.pack(side="left", padx=(10, 0))
        tk.Label(titles, text=self._a_name, font=T["font_title"],
                 bg=T["bg"], fg=T["fg"]).pack(anchor="w")
        tk.Label(titles, text="เพื่อนคู่หูของเด็ก ๆ — คุยเล่นได้ ล่องกล้องได้",
                 font=T["font"], bg=T["bg"], fg=T["sys_fg"]).pack(anchor="w")

        body = tk.Frame(self.root, bg=T["bg"])
        body.pack(fill="both", expand=True, padx=8, pady=8)

        # ---------- ซ้าย: วิดีโอ ----------
        left = tk.Frame(body, bg=T["video_bg"], bd=4, relief="ridge")
        left.pack(side="left", fill="both", expand=False)

        # ⚠️ width/height ของ Label เป็น "จำนวนตัวอักษร" ไม่ใช่ pixel → ต้องใช้ Frame
        # ขนาด pixel คงที่ + pack_propagate(False) ไม่งั้นช่องวิดีโอจะใหญ่จนหน้าแชทหลุดจอ
        video_box = tk.Frame(left, bg="#000000", width=VIDEO_W, height=VIDEO_H)
        video_box.pack(padx=4, pady=4)
        video_box.pack_propagate(False)

        self.video_label = tk.Label(
            video_box, bg="#000000", fg="white",
            text="กล้องปิดอยู่ — กด 'เปิดกล้อง' นะ",
            font=T["font"],
        )
        self.video_label.pack(fill="both", expand=True)

        cam_bar = tk.Frame(left, bg=T["video_bg"])
        cam_bar.pack(fill="x", padx=4, pady=(2, 0))
        tk.Label(cam_bar, text="📷", bg=T["video_bg"], fg=T["fg"],
                 font=T["font_bold"]).pack(side="left")

        self._cam_choice = tk.StringVar(value="(กำลังค้นหา...)")
        self._cam_menu = tk.OptionMenu(cam_bar, self._cam_choice, "(กำลังค้นหา...)",
                                       command=self._on_cam_change)
        self._cam_menu.configure(bg=T["panel"], fg=T["fg"],
                                 highlightbackground=T["video_bg"],
                                 activebackground=T["panel"], font=T["font"])
        self._cam_menu["menu"].configure(bg=T["panel"], fg=T["fg"])
        self._cam_menu.pack(side="left", padx=(4, 8))

        self.cam_btn = tk.Button(cam_bar, text="เปิดกล้อง", width=10,
                                 command=self.toggle_camera, bg=T["mint"],
                                 activebackground=T["mint_hi"], fg=T["fg"],
                                 font=T["font_bold"], relief="flat")
        self.cam_btn.pack(side="left")
        tk.Checkbutton(
            cam_bar, text="จับหน้า", variable=self._faces_var,
            command=self._on_faces_toggle, bg=T["video_bg"], fg=T["fg"],
            selectcolor=T["panel"], activebackground=T["video_bg"],
            activeforeground=T["fg"], font=T["font"],
        ).pack(side="left", padx=(8, 0))
        tk.Checkbutton(
            cam_bar, text="👀 ตามหน้า", variable=self._track_var,
            command=self._on_track_toggle, bg=T["video_bg"], fg=T["fg"],
            selectcolor=T["panel"], activebackground=T["video_bg"],
            activeforeground=T["fg"], font=T["font"],
        ).pack(side="left", padx=(8, 0))
        tk.Checkbutton(
            cam_bar, text="✋ ตามมือ", variable=self._gesture_var,
            command=self._on_gesture_toggle, bg=T["video_bg"], fg=T["fg"],
            selectcolor=T["panel"], activebackground=T["video_bg"],
            activeforeground=T["fg"], font=T["font"],
        ).pack(side="left", padx=(8, 0))

        # ---------- แถวไมค์ (ใช้ตอนกด 🎤) ----------
        mic_bar = tk.Frame(left, bg=T["video_bg"])
        mic_bar.pack(fill="x", padx=4, pady=(4, 4))
        tk.Label(mic_bar, text="🎙", bg=T["video_bg"], fg=T["fg"],
                 font=T["font_bold"]).pack(side="left")

        self._mic_choice = tk.StringVar(value="(กำลังค้นหา...)")
        self._mic_menu = tk.OptionMenu(mic_bar, self._mic_choice, "(กำลังค้นหา...)",
                                       command=self._on_mic_change)
        self._mic_menu.configure(bg=T["panel"], fg=T["fg"],
                                 highlightbackground=T["video_bg"],
                                 activebackground=T["panel"], font=T["font"])
        self._mic_menu["menu"].configure(bg=T["panel"], fg=T["fg"])
        self._mic_menu.pack(side="left", padx=(4, 8))

        tk.Button(mic_bar, text="🔄 สแกนใหม่", command=self._rescan_devices,
                  bg=T["accent2"], activebackground=T["accent2_hi"], fg=T["fg"],
                  font=T["font_bold"], relief="flat").pack(side="left")
        # ★ ปุ่มกู้กรณีไมค์ค้างเงียบ — กดปุ่มเดียว ไม่ต้องปิดทั้งแอป
        tk.Button(mic_bar, text="♻️ รีสตาร์ทไมค์", command=self.restart_mic,
                  bg=T["accent"], activebackground=T["accent_hi"], fg="white",
                  font=T["font_bold"], relief="flat").pack(side="left", padx=(6, 0))

        # ---------- แถวปรับเกณฑ์รับเสียง (🎚 สไลเดอร์) ----------
        # เลื่อนแล้วมีผลกับไมค์ค้างทันที · ขีดส้มบน VU ด้านล่าง = ตำแหน่งเกณฑ์ปัจจุบัน
        thr_bar = tk.Frame(left, bg=T["video_bg"])
        thr_bar.pack(fill="x", padx=4, pady=(0, 2))
        tk.Label(thr_bar, text="🎚 เกณฑ์เสียง", bg=T["video_bg"], fg=T["fg"],
                 font=T["font_bold"]).pack(side="left")
        tk.Button(thr_bar, text="➖", command=lambda: self._bump_thr(-0.005),
                  bg=T["panel"], activebackground=T["panel"], fg=T["fg"],
                  font=T["font"], relief="flat", padx=3,
                  ).pack(side="left", padx=(4, 0))
        self._thr_scale = tk.Scale(
            thr_bar, from_=0.005, to=0.100, resolution=0.005, orient="horizontal",
            showvalue=0, command=self._on_thr_change, length=110, width=12,
            bg=T["video_bg"], fg=T["fg"], troughcolor=T["panel"],
            activebackground=T["accent"], highlightthickness=0,
        )
        self._thr_scale.pack(side="left", fill="x", expand=True, padx=4)
        tk.Button(thr_bar, text="➕", command=lambda: self._bump_thr(+0.005),
                  bg=T["panel"], activebackground=T["panel"], fg=T["fg"],
                  font=T["font"], relief="flat", padx=3,
                  ).pack(side="left")
        self._thr_lbl = tk.Label(thr_bar, text="0.000", width=6, anchor="e",
                                 bg=T["video_bg"], fg=T["accent_hi"],
                                 font=T["font_bold"])
        self._thr_lbl.pack(side="left", padx=(6, 0))
        self._thr_auto_var = tk.BooleanVar(master=self.root, value=True)
        tk.Checkbutton(
            thr_bar, text="อัตโนมัติ", variable=self._thr_auto_var,
            command=self._on_thr_auto, bg=T["video_bg"], fg=T["fg"],
            selectcolor=T["panel"], activebackground=T["video_bg"],
            activeforeground=T["fg"], font=T["font"],
        ).pack(side="left", padx=(6, 0))

        # ---------- แถว VU meter (📊 ระดับเสียงสด) ----------
        vu_bar = tk.Frame(left, bg=T["video_bg"])
        vu_bar.pack(fill="x", padx=4, pady=(0, 4))
        tk.Label(vu_bar, text="📊 ระดับเสียง", bg=T["video_bg"], fg=T["fg"],
                 font=T["font_bold"]).pack(side="left")
        self._vu_canvas = tk.Canvas(vu_bar, height=20, bg=T["panel"],
                                    highlightthickness=0, bd=0)
        self._vu_canvas.pack(side="left", fill="x", expand=True, padx=(4, 6))
        self._vu_lbl = tk.Label(vu_bar, text="—", width=6, anchor="e",
                                bg=T["video_bg"], fg=T["fg"], font=T["font"])
        self._vu_lbl.pack(side="left")
        self._vu_state = tk.Label(vu_bar, text="", width=13, anchor="w",
                                  bg=T["video_bg"], fg=T["sys_fg"], font=T["font"])
        self._vu_state.pack(side="left", padx=(4, 0))
        # ค่าเริ่มต้นสไลเดอร์: ตาม config; ถ้าเคย "ตั้งเอง" ไว้ → ล็อกค่าเดิมไว้เลย
        try:
            _scfg = get_config()["stt"]
        except Exception:  # noqa: BLE001
            _scfg = {}
        _init_thr = float(_scfg.get("speech_threshold", 0.025))
        if _scfg.get("thr_manual"):
            self._thr_manual = _init_thr
        self._thr_auto_var.set(self._thr_manual is None)
        self._sync_thr_slider(_init_thr if self._thr_manual is None else self._thr_manual)

        self._refresh_devices()   # เติมรายการกล้อง/ไมค์จริง

        self.video_info = tk.Label(left, text="—", bg=T["video_bg"],
                                   fg=T["fg"], anchor="w", font=T["font"])
        self.video_info.pack(fill="x", padx=4, pady=(0, 4))

        # ---------- ขวา: แชท ----------
        right = tk.Frame(body, bg=T["bg"])
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        self.chat = scrolledtext.ScrolledText(
            right, wrap="word", state="disabled", font=T["font_chat"],
            bg=T["panel"], fg=T["fg"], insertbackground=T["fg"], height=10,
            padx=8, pady=8, relief="flat",
        )
        # bubble: คุณ (ฟ้า, ขวา) · หุ่นหลัก (เหลือง) · หุ่นคู่ (เขียว) · ระบบ (เทา)
        self.chat.tag_configure("user", background=T["bubble_user"],
                                lmargin1=60, lmargin2=60, rmargin=6,
                                spacing1=4, spacing3=6, justify="right")
        self.chat.tag_configure("robot", background=T["bubble_robot"],
                                lmargin1=6, lmargin2=6, rmargin=60,
                                spacing1=4, spacing3=6, justify="left")
        self.chat.tag_configure("sys", foreground=T["sys_fg"], spacing1=4, spacing3=6)
        # 🤝 ข้อเสริมของหุ่นคู่ — สีเขียวอ่อนให้ต่างจากหุ่นหลัก
        self.chat.tag_configure("robot_b",
                                background=T.get("bubble_robot_b", T["bubble_robot"]),
                                lmargin1=6, lmargin2=6, rmargin=60,
                                spacing1=4, spacing3=6, justify="left")
        self.chat.pack(fill="both", expand=True)

        # ปุ่มคำถามด่วน (ปุ่มโหญ่ ๆ สีสัน น่ารักสำหรับเด็ก)
        quick = tk.Frame(right, bg=T["bg"])
        quick.pack(fill="x", pady=(8, 0))
        quick_items = (("📖 เล่านิทาน", "เล่านิทานให้ฟังหน่อย"),
                       ("💃 เต้น", "เต้นให้ดูหน่อย"),
                       ("🔢 บวกเลข", "3+5 ได้เท่าไหร่"),
                       ("🐰 ช่วยอะไรได้", "ทำอะไรได้บ้าง"))
        for label, text in quick_items:
            tk.Button(quick, text=label, command=lambda t=text: self.ask(t),
                      bg=T["mint"], activebackground=T["mint_hi"], fg=T["fg"],
                      font=T["font_bold"], relief="flat", padx=10, pady=4,
                      ).pack(side="left", padx=(0, 6))

        # ปุ่มทำท่าทางตรง ๆ — ไม่ต้องผ่าน LLM (ใช้ได้เสมอ แม้ server ล่ม)
        motion_bar = tk.Frame(right, bg=T["bg"])
        motion_bar.pack(fill="x", pady=(6, 0))
        tk.Label(motion_bar, text="ทำท่าเลย:", bg=T["bg"], fg=T["fg"],
                 font=T["font_bold"]).pack(side="left")
        for label, tool in (("👋 โบกมือ", "wave"), ("💃 เต้น", "dance"),
                            ("🙇 ค้อม", "bow"), ("📺 มองรอบ", "look_around")):
            tk.Button(motion_bar, text=label, command=lambda t=tool: self.manual_action(t),
                      bg=T["accent"], activebackground=T["accent_hi"], fg="white",
                      font=T["font_bold"], relief="flat", padx=8, pady=3,
                      ).pack(side="left", padx=(6, 0))

        bottom = tk.Frame(right, bg=T["bg"])
        bottom.pack(fill="x", pady=(8, 0))
        self.entry = tk.Entry(bottom, font=T["font_entry"], bg=T["panel"],
                              fg=T["fg"], insertbackground=T["fg"], relief="flat",
                              highlightthickness=2,
                              highlightbackground=T["accent"])
        self.entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.entry.bind("<Return>", lambda _e: self.ask())
        self.send_btn = tk.Button(bottom, text="ส่ง 🚀", width=8, command=self.ask,
                                  bg=T["accent"], activebackground=T["accent_hi"],
                                  fg="white", font=T["font_bold"], relief="flat")
        self.send_btn.pack(side="right", padx=(6, 0))
        self.mic_btn = tk.Button(bottom, text="🎤 พูด", width=8, command=self.listen_click,
                                 bg=T["accent2"], activebackground=T["accent2_hi"], fg=T["fg"],
                                 font=T["font_bold"], relief="flat")
        self.mic_btn.pack(side="right", padx=(6, 0))
        # โหมดฟังอัตโนมัติเปิดเป็นค่าเริ่มต้น → ปุ่มmanual ถูกปิดไว้ก่อน
        self.mic_btn.configure(state="disabled")
        tk.Button(bottom, text="🧹 ล้าง", width=7, command=self.clear,
                  bg=T["mint"], activebackground=T["mint_hi"], fg=T["fg"],
                  font=T["font_bold"], relief="flat").pack(side="right", padx=(6, 0))

        opts = tk.Frame(right, bg=T["bg"])
        opts.pack(fill="x", pady=(6, 0))
        tk.Checkbutton(
            opts, text="🔊 พูดตอบ", variable=self._speak_var,
            command=lambda: print(f"[GUI] 🔊 พูดตอบ = "
                                  f"{'เปิด' if self._speak_var.get() else 'ปิด'}"),
            bg=T["bg"], fg=T["fg"], selectcolor=T["panel"],
            activebackground=T["bg"], activeforeground=T["fg"], font=T["font"],
        ).pack(side="left")
        tk.Checkbutton(
            opts, text="🎭 ขยับ", variable=self._anim_var,
            command=lambda: print(f"[GUI] 🎭 ขยับ = "
                                  f"{'เปิด' if self._anim_var.get() else 'ปิด'}"),
            bg=T["bg"], fg=T["fg"], selectcolor=T["panel"],
            activebackground=T["bg"], activeforeground=T["fg"], font=T["font"],
        ).pack(side="left", padx=(8, 0))
        tk.Checkbutton(
            opts, text="🎧 ฟังอัตโนมัติ", variable=self._listen_var,
            command=self._on_listen_toggle,
            bg=T["bg"], fg=T["fg"], selectcolor=T["panel"],
            activebackground=T["bg"], activeforeground=T["fg"], font=T["font"],
        ).pack(side="left", padx=(8, 0))
        tk.Button(opts, text="🔊 ทดสอบเสียง", command=self.test_voice,
                  bg=T["accent2"], activebackground=T["accent2_hi"], fg=T["fg"],
                  font=T["font_bold"], relief="flat", padx=8,
                  ).pack(side="left", padx=(10, 0))
        tk.Button(opts, text="🎙 วัดเสียง", command=self.measure_mic,
                  bg=T["mint"], activebackground=T["mint_hi"], fg=T["fg"],
                  font=T["font_bold"], relief="flat", padx=8,
                  ).pack(side="left", padx=(6, 0))

        # ---------- แถบสถานะ ----------
        self.status = tk.Label(self.root, text="", bg=T["status_bg"], fg="white",
                               anchor="w", font=T["font_bold"])
        self.status.pack(fill="x", side="bottom")

        # 🟢 เก็บ widget พื้นหลังทั้งหมดไว้สลับเป็นสีเขียวตอนพร้อมรับคำสั่ง
        #    กวาดอัตโนมัติ: ทุก widget ที่พื้นหลังเดิมเป็นสี theme (ข้าม panel/วิดีโอ/ปุ่ม)
        self._bg_targets: list = [(self.root, str(self.root.cget("bg")))]

        def _collect(w):
            for child in w.winfo_children():
                try:
                    bg = str(child.cget("bg"))
                except Exception:  # noqa: BLE001
                    continue
                if bg == T["bg"] or bg == T["video_bg"]:
                    self._bg_targets.append((child, bg))
                _collect(child)

        _collect(self.root)
        self._set_status(f"พร้อมแล้ว — โมเดล {self.llm.model} | กล้อง {self._cam_choice.get()}")

        self._append("ระบบ", f"สวัสดีจ้า! พิมพ์คุยกับ{self._a_name}ได้เลย (โมเดล: {self.llm.model})")
        # ปั๊มภาพวิดีโอเป็นรอบ ๆ (สร้าง PhotoImage ต้องทำใน main thread เท่านั้น)
        self.root.after(30, self._pump_video)

    # ================= อุปกรณ์ (กล้อง/ไมค์) =================
    @staticmethod
    def _list_mics_safe() -> list[tuple[int, str]]:
        """รายชื่อไมค์ — คืน [] ถ้าใช้ sounddevice ไม่ได้"""
        try:
            from src.stt import list_mics
            return list_mics()
        except Exception as exc:  # noqa: BLE001
            print(f"[GUI] อ่านรายการไมค์ไม่ได้: {exc}")
            return []

    def _refresh_devices(self):
        """เติมรายการกล้อง/ไมค์ (เรียกตอนเปิดหน้าต่าง + ปุ่มสแกนใหม่)"""
        cam_labels = [f"{i}: {n}" for i, n in list_cameras()] or ["(ไม่พบกล้อง)"]
        _fill_option_menu(self._cam_menu, self._cam_choice, cam_labels, self._on_cam_change)
        self._cam_choice.set(self._guess_cam_label(cam_labels))

        mic_labels = [f"{i}: {n}" for i, n in self._list_mics_safe()] or ["(ไม่พบไมค์)"]
        _fill_option_menu(self._mic_menu, self._mic_choice, mic_labels, self._on_mic_change)
        self._mic_choice.set(self._default_mic_label(mic_labels))
        self._mic_index = _index_from_label(self._mic_choice.get())
        self._devices_ready = True

    def _rescan_devices(self):
        """ปุ่ม 🔄 — หาใหม่ (หลังเสียบ/ถอดกล้องหรือไมค์)"""
        self._refresh_devices()
        self._set_status(f"สแกนใหม่ — กล้อง: {self._cam_choice.get()} | "
                         f"ไมค์: {self._mic_choice.get()}")

    def _default_mic_label(self, labels: list[str]) -> str:
        """เลือกไมค์เริ่มต้น: ตาม config stt.mic ก่อน ไม่เจอใช้ตัวแรก"""
        spec = get_config()["stt"].get("mic")
        if spec is None:
            return labels[0]
        needle = str(spec).lower()
        # จับคู่ใน pass เดียวเรียงตาม label (index): ชื่อเต็ม (DirectSound idx6)
        # และชื่อตัดสั้น (MME idx1) ต้องเจอ idx1 ก่อน — MME เสียงดังกว่า
        for label in labels:
            name = (label.split(":", 1)[1].strip().lower()
                    if ":" in label else label.lower())
            if needle in label.lower() or (len(name) >= 10 and name in needle):
                return label
        if str(spec).isdigit():
            for label in labels:
                if label.startswith(f"{spec}:"):
                    return label
        return labels[0]

    def _on_mic_change(self, value: str):
        """ผู้ใช้เปลี่ยนไมค์ → จำไว้ใช้กับปุ่ม 🎤 (+ บันทึกค่าเฉพาะเครื่อง)"""
        self._mic_index = _index_from_label(value)
        name = value.split(":", 1)[1].strip() if ":" in value else value
        self._set_status(f"🎙️ ไมค์: {name}" + (
            f" (index {self._mic_index})" if self._mic_index is not None else ""))
        if not self._devices_ready:
            return
        try:
            from config.robot_config import save_local_config
            save_local_config({"stt": {"mic": name}})
        except Exception as exc:  # noqa: BLE001
            print(f"[GUI] บันทึกค่าไมค์ไม่ได้: {exc}")
        # ถ้าไมค์เปิดค้างอยู่ → สลับไปตัวใหม่ทันที (ไม่ต้องปิด-เปิด 🎧 เอง)
        if self._cont is not None and not self._closing:
            self._stop_continuous()
            self._start_continuous()

    def _guess_cam_label(self, names: list[str]) -> str:
        """เลือก label กล้องเริ่มต้นจาก spec ที่ผู้ใช้ให้ (ตรงชื่อก่อน แล้วค่อย index)"""
        spec = str(self._cam_spec).lower()
        for label in names:                        # เช่น "1: Microsoft LifeCam Cinema"
            if spec in label.lower():
                return label
        if str(self._cam_spec).isdigit():
            for label in names:
                if label.startswith(f"{self._cam_spec}:"):
                    return label
        return names[0]

    # ================= กล้อง/วิดีโอ =================
    def toggle_camera(self):
        if self._cam_thread and self._cam_thread.is_alive():
            self._stop_camera()
        else:
            self._start_camera()

    def _start_camera(self):
        label = self._cam_choice.get()
        spec = label.split(":")[0] if ":" in label else label
        try:
            cam_id = resolve_camera(int(spec) if spec.isdigit() else spec)
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"⚠️ เปิดกล้องไม่ได้: {exc}")
            return
        self._cam_stop.clear()
        self._cam_thread = threading.Thread(
            target=self._camera_loop, args=(cam_id,), daemon=True)
        self._cam_thread.start()
        self.cam_btn.configure(text="ปิดกล้อง")
        self._set_status(f"🎥 กล้อง {cam_id} กำลังทำงาน...")

    def _stop_camera(self):
        self._cam_stop.set()
        if self._cam_thread:
            self._cam_thread.join(timeout=1.5)
        self.cam_btn.configure(text="เปิดกล้อง")
        self.video_label.configure(image="", text="กล้องปิดอยู่ — กด 'เปิดกล้อง'")
        self.video_info.configure(text="—")
        self._set_status("กล้องปิด")

    def _on_cam_change(self, _value=None):
        """เปลี่ยนกล้องจาก dropdown — ถ้ากำลังเปิดอยู่ให้รีสตาร์ท"""
        was_running = bool(self._cam_thread and self._cam_thread.is_alive())
        if was_running:
            self._stop_camera()
            self._start_camera()

    def _on_faces_toggle(self):
        self._faces_on = bool(self._faces_var.get())
        print(f"[GUI] 🔍 วาดกรอบหน้า = {'เปิด' if self._faces_on else 'ปิด'}")

    def _on_track_toggle(self):
        """เปิด/ปิดการขยับหุ่นตามใบหน้า"""
        self._tracking = bool(self._track_var.get())
        print(f"[GUI] 👀 ติดตามใบหน้า = {'เปิด' if self._tracking else 'ปิด'}")
        self._set_status("👀 ติดตามใบหน้า: เปิด — หุ่นจะหันตามหน้าเรา"
                         if self._tracking else "👀 ปิดการติดตามใบหน้า")

    # ---------- ติดตามใบหน้า (ขยับหุ่นตามหน้า) ----------
    TRACK_ALPHA = 0.35       # low-pass กันสั่น
    TRACK_DZ = 0.12          # โซนกลาง — ไม่ขยับ (กันส่าย)
    TRACK_MIN_DT = 0.15      # วิ — เว้นช่วงสั่งมอเตอร์
    TRACK_BASE_GAIN = 35.0   # องศา — หน้าเยื้องซ้าย/ขวา → หมุนตัว
    TRACK_ROLL_GAIN = 14.0   # องศา — หน้าเยื้องบน/ล่าง → เงย/ก้ม

    def _track_face(self, center, shape):
        """ขยับฐาน+หัวตามใบหน้า (เรียกจาก camera thread) — ขยับเมื่อเป้าเปลี่ยนชัด"""
        now = time.time()
        if now - self._track_last < self.TRACK_MIN_DT:
            return
        self._track_last = now
        h, w = shape[:2]
        cx, cy = center
        nx = (cx / w) * 2 - 1          # -1..1 ซ้าย/ขวา
        ny = -((cy / h) * 2 - 1)       # -1..1 บน/ล่าง
        dz = self.TRACK_DZ
        nx = 0.0 if abs(nx) <= dz else (nx - dz if nx > 0 else nx + dz)
        ny = 0.0 if abs(ny) <= dz else (ny - dz if ny > 0 else ny + dz)
        t_b = nx * self.TRACK_BASE_GAIN
        t_r = ny * self.TRACK_ROLL_GAIN
        self._track_xy[0] += self.TRACK_ALPHA * (t_b - self._track_xy[0])
        self._track_xy[1] += self.TRACK_ALPHA * (t_r - self._track_xy[1])
        b, r = self._track_xy
        if abs(b - self._track_cmd[0]) < 1.2 and abs(r - self._track_cmd[1]) < 1.2:
            return                     # ใกล้เป้าแล้ว — ไม่สั่งซ้ำ (กันมอเตอร์คราง)
        self._track_cmd[0], self._track_cmd[1] = b, r
        try:
            self.robot.set_base(b, duration=0.05)
            self.robot.set_head_pose(z=None, roll=r, pitch=0.0, yaw=0.0,
                                     duration=0.05)
        except Exception as exc:  # noqa: BLE001 — หุ่นหลุด ไม่ให้กล้องตาย
            print(f"[GUI] 👀 ขยับตามหน้าไม่ได้: {exc}")

    # ---------- ทำท่าตามมือ (✋) ----------
    GESTURE_ACTIONS = {
        "thumbs_up": "happy",     # 👍
        "open_palm": "wave",       # 🖐
        "victory": "dance",        # ✌️
        "love": "bow",             # 🤟 ค้อมคำนับ
        "fist": "shake_head",      # ✊ ส่ายหน้า
        "point": "look_around",    # ☝️ มองรอบ
        "rock": "headbang",        # 🤘 มันส์
        "Thumb_Down": "shake_head",  # 👎 ส่ายหน้า (ไม่เห็นด้วย)
    }
    GESTURE_HOLD = 3        # เห็นท่าเดิมติดกันกี่ครั้ง (ตรวจจับครั้งละ ~3 เฟรม ≈ 0.4s)
    GESTURE_COOLDOWN = 5.0  # วิ — กันท่าเดิมรัว ๆ
    _GESTURE_SKIP = "__skip__"  # เฟรมนี้ยังไม่สุ่มตรวจ — ต้องไม่รีเซ็ต hold

    def _on_gesture_toggle(self):
        """เปิด/ปิดการทำท่าตามมือ"""
        self._gesture_on = bool(self._gesture_var.get())
        print(f"[GUI] ✋ ทำท่าตามมือ = {'เปิด' if self._gesture_on else 'ปิด'}")
        self._set_status("✋ เปิด: ชูมือให้หุ่นทำท่า — 👍 happy · 🖐 โบกมือ · ✌️ เต้น · 🤘 มันส์"
                         if self._gesture_on else "✋ ปิดทำท่าตามมือ")

    def _ensure_gesture_rec(self):
        """โหลด GestureRecognizer ครั้งแรก (mediapipe) — สร้างไม่ได้ → ปิดไปเลย"""
        if self._gesture_rec is None:
            try:
                from src.vision import GestureRecognizer
                self._gesture_rec = GestureRecognizer()
            except Exception as exc:  # noqa: BLE001
                print(f"[GUI] ✋ ใช้ gesture recognizer ไม่ได้: {exc}")
                self._gesture_rec = False
        return self._gesture_rec or None

    def _detect_gesture(self, frame):
        """ตรวจจับท่ามือ (เรียกจาก camera thread) — จำกัดอัตรา ~ทุก 3 เฟรม

        คืน: ชื่อท่า | None (ตรวจแล้ว ไม่มีท่า) | _GESTURE_SKIP (เฟรมนี้ข้าม)
        ⚠️ ห้ามคืน None ตอนข้าม — ไม่งั้น hold ที่นับไว้จะถูกรีเซ็ต → ท่าไปไม่ถึง
        """
        self._gesture_tick += 1
        if self._gesture_tick % 3:
            return self._GESTURE_SKIP
        rec = self._ensure_gesture_rec()
        if rec is None:
            return None
        try:
            return rec.detect(frame)
        except Exception as exc:  # noqa: BLE001
            print(f"[GUI] ✋ ตรวจจับท่ามือผิดพลาด: {exc}")
            return None

    def _handle_gesture(self, g):
        """นับ hold + cooldown → สั่งหุ่นทำท่าตามมือ (เรียกจาก camera thread)"""
        hold = self._gesture_hold
        if g is None:
            # เฟรมที่สุ่มตรวจแล้วไม่เห็นมือ — ลด count แบบรั่วครึ่งแต้ม (ทนหลุดบ่อยแบบสลับ)
            hold["count"] = max(0.0, hold["count"] - 0.5)
            if hold["count"] == 0:
                hold["name"] = None
            return
        if hold["name"] == g:
            hold["count"] += 1
        else:
            if g is not None:
                print(f"[GUI] ✋ เริ่มเห็นท่ามือ: {g} (ชูค้างไว้อีกนิด)")
            hold["name"], hold["count"] = g, 1
        now = time.time()
        if hold["count"] < self.GESTURE_HOLD or now < self._gesture_cooldown:
            return
        tool = self.GESTURE_ACTIONS.get(g)
        if tool is None:
            return
        if self._busy or self._speaking or self._action_busy:
            return   # หุ่นกำลังยุ่ง — ไม่ทำท่าซ้อน
        self._gesture_cooldown = now + self.GESTURE_COOLDOWN
        hold["name"], hold["count"] = None, 0
        print(f"[GUI] ✋ ท่ามือ {g} → ทำท่า {tool}")
        self._gesture_action(tool)

    def _gesture_action(self, tool_name: str):
        """ทำท่าจากท่ามือ — รันในเธรดแยก หุ่นหลุดไม่ทำให้แอปตาย"""
        self._ui_call(self._set_status, f"✋ เห็นท่ามือ — {self._a_name}ทำท่า {tool_name}!")

        def run():
            self._action_busy = True
            try:
                self._ensure_robot_alive()
                execute_tool(self.robot, tool_name, {}, partner=self.robot_b)
            except Exception as exc:  # noqa: BLE001
                print(f"[GUI] ✋ ทำท่าตามมือไม่สำเร็จ: {exc}")
            finally:
                self._action_busy = False
        threading.Thread(target=run, daemon=True).start()

    def _ensure_detector(self):
        """สร้าง YuNet ครั้งแรกที่ใช้ (ถ้าสร้างไม่ได้ → ปิดการตรวจจับไปเลย)"""
        if self._detector is None:
            try:
                from src.face_detector import FaceDetector
                self._detector = FaceDetector()
            except Exception as exc:  # noqa: BLE001
                print(f"[GUI] ใช้ face detector ไม่ได้: {exc}")
                self._detector = False
        return self._detector or None

    def _camera_loop(self, cam_id: int):
        """thread อ่านกล้อง → ส่งเฟรมเข้า queue ให้ main thread แสดง"""
        try:
            with Camera(cam_id, VIDEO_W, VIDEO_H) as cam:
                fps = 0.0
                t_prev = time.time()
                while not self._cam_stop.is_set():
                    frame = cam.read()
                    if frame is None:
                        time.sleep(0.02)
                        continue
                    faces = []
                    if self._faces_on or self._tracking:
                        det = self._ensure_detector()
                        if det is not None:
                            faces = det.detect(frame)
                            if self._faces_on:
                                det.draw(frame, faces)
                    # 👀 ขยับหุ่นตามใบหน้า — หยุดชั่วคราวตอนพูด/คิด/ทำท่า
                    if (faces and self._tracking and not self._speaking
                            and not self._action_busy and not self._busy):
                        self._track_face(faces[0].center, frame.shape)
                    # ✋ ท่ามือ → หุ่นทำท่าตาม (👍✌️🤘 ฯลฯ)
                    gesture = None
                    if self._gesture_on and not self._closing:
                        g = self._detect_gesture(frame)
                        if g != self._GESTURE_SKIP:  # เฟรมที่ข้าม — ไม่รีเซ็ต hold
                            gesture = g
                            self._handle_gesture(g)
                    # FPS แบบ EMA (นิ่งกว่า ค่าจริงต่อเฟรม)
                    now = time.time()
                    dt = max(now - t_prev, 1e-6)
                    t_prev = now
                    fps = fps * 0.9 + (1.0 / dt) * 0.1

                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    info = (f"FPS {fps:4.1f} | {frame.shape[1]}x{frame.shape[0]}"
                            f" | ใบหน้า: {len(faces)}"
                            + (f" | มือ: {gesture}" if gesture else ""))
                    try:
                        self._video_q.put_nowait((rgb, info))
                    except queue.Full:
                        pass  # main thread ยังวาดไม่ทัน → ทิ้งเฟรมเก่า
                    # จำกัด fps การแสดง
                    slack = (1.0 / FPS_TARGET) - (time.time() - now)
                    if slack > 0:
                        time.sleep(slack)
        except Exception as exc:  # noqa: BLE001
            self._ui_call(self._on_camera_error, str(exc))

    def _on_camera_error(self, msg: str):
        self.cam_btn.configure(text="เปิดกล้อง")
        self.video_label.configure(image="", text=f"⚠️ กล้องผิดพลาด:\n{msg}")
        self._set_status(f"⚠️ กล้องผิดพลาด: {msg}")

    def _pump_video(self):
        """วาดเฟรมล่าสุด + ทำงาน UI ที่ worker thread ฝากไว้ (main thread)

        ⚠️ ต้อง reschedule ทุกครั้งแม้ error — ถ้า chain ตาย คิว UI จะค้าง:
        _finish_turn ไม่ถูกเรียก → _busy ค้าง True → หุ่นหูหนวกโดยไร้อาการ
        """
        try:
            self._pump_ui()
            self._update_ready_led()   # 🟢 อัปเดตไฟสถานะทุกรอบ
            self._update_vu()          # 📊 VU meter ระดับไมค์
            self._update_turn_popup()  # 🔔 popup จังหวะพูด (รอหุ่น / ถึงตาคุณ)
            try:
                rgb, info = self._video_q.get_nowait()
                img = Image.fromarray(rgb)
                self._photo = ImageTk.PhotoImage(img)
                self.video_label.configure(image=self._photo, text="")
                self.video_info.configure(text=info)
                self._frames_shown += 1
            except queue.Empty:
                pass
        except Exception as exc:  # noqa: BLE001 — ห้ามให้ chain ตาย
            print(f"[GUI] ⚠️ pump_video ผิดพลาด (chain ไปต่อ): {exc}")
        finally:
            self.root.after(30, self._pump_video)

    def _update_ready_led(self):
        """ไฟสถานะ: เขียว = พร้อมรับคำสั่งเสียง/พูดเสร็จ | สีเดิม = กำลังทำงานหรือค้าง

        คำนวณจาก flag จริงทุก ~30ms — ถ้า process ค้าง (flag ค้าง True) ไฟจะไม่เขียว
        """
        ready = not (self._busy or self._speaking or self._action_busy
                     or self._listening or self._transcribing)
        if ready == self._led_ready:
            return
        self._led_ready = ready
        T = self.T
        green_soft = T.get("ready_soft", "#D8F5DE")
        # พื้นหลังทั้งแอป (frame/label พื้นฐาน) — เขียวอ่อนตอนพร้อม, สีเดิมตอนทำงาน/ค้าง
        for w, orig in getattr(self, "_bg_targets", []):
            try:
                w.configure(bg=(green_soft if ready else orig))
            except Exception:  # noqa: BLE001
                pass
        try:
            self.status.configure(
                bg=(T.get("ready_bg", "#3ECF6E") if ready else T["status_bg"]))
        except Exception:  # noqa: BLE001
            pass

    def _ui_call(self, fn, *args):
        """ให้ worker thread สั่งงาน UI ได้อย่างปลอดภัย (ทำงานจริงใน main thread)

        ⚠️ ห้ามเรียก widget/root.after จาก worker thread ตรง ๆ — Tk ไม่ thread-safe
        """
        self._ui_q.put((fn, args))

    def _pump_ui(self):
        """รัน callback ที่ค้างอยู่ในคิว (เรียกจาก _pump_video ใน main thread)"""
        while True:
            try:
                fn, args = self._ui_q.get_nowait()
            except queue.Empty:
                return
            try:
                fn(*args)
            except Exception as exc:  # noqa: BLE001
                print(f"[GUI] UI callback ผิดพลาด: {exc}")

    # ================= แชท =================
    def _append(self, who: str, text: str):
        """เพิ่มข้อความลงแชทเป็น bubble (คุณ = ฟ้าขวา · หุ่นหลักเหลือง · หุ่นคู่เขียว)"""
        tag = {"คุณ": "user", self._a_name: "robot",
               self._b_name: "robot_b"}.get(who, "sys")
        label = {"คุณ": "🧒 คุณ", self._a_name: f"🐰 {self._a_name}",
                 self._b_name: f"🤖 {self._b_name}"}.get(who, "ℹ️ ระบบ")
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{label}\n{text}\n\n", tag)
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _set_face(self, state: str):
        """เปลี่ยนหน้าหุ่นบนหัวหน้าต่าง (อารมณ์/สถานะ) — เรียกได้จาก main thread เท่านั้น"""
        face = FACE_BY_EMOTION.get(state) or {
            "thinking": FACE_THINKING, "listen": FACE_LISTEN,
            "ready": FACE_READY,
        }.get(state, FACE_READY)
        if getattr(self, "_face_label", None) is not None:
            self._face_label.configure(text=face)

    def clear(self):
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self.history = []
        self._append("ระบบ", "ล้างประวัติแล้ว — เริ่มคุยใหม่ได้เลย")

    def _set_status(self, text: str):
        self.status.configure(text=f" {text}")

    def ask(self, text: str | None = None):
        """ส่งข้อความ (จากช่องพิมพ์ หรือปุ่มด่วน)"""
        if self._busy:
            return
        user_text = (text if text is not None else self.entry.get()).strip()
        if not user_text:
            return
        self.entry.delete(0, "end")
        self._append("คุณ", user_text)
        self.history.append({"role": "user", "content": user_text})
        self._busy = True
        self._busy_since = time.time()
        self.send_btn.configure(state="disabled")
        self._set_status("🤔 กำลังคิด...")
        self._set_face("thinking")
        threading.Thread(target=self._chat_worker, daemon=True).start()

    def _chat_worker(self):
        """thread คุย LLM (อาจเรียก tool 1 ครั้ง) แล้วสั่งหุ่นตอบ

        โหมดหุ่นคู่: A ได้ร่าง → B อ่าน+เสริม (ยังไม่มีใครพูด) →
        A พูดคำตอบ → B พูดข้อเสริม (ผลัดกัน)
        """
        try:
            reply, did_tool = self._chat_with_tools()
        except Exception as exc:  # noqa: BLE001
            self._ui_call(self._append, "ระบบ", f"(LLM ผิดพลาด: {exc})")
            self._ui_call(self._finish_turn)
            return

        emotion = detect_emotion(reply)
        clean = strip_emotion_tag(reply).strip() or "เรียบร้อยจ้า"

        # --- 🤫 ให้หุ่น B ปรึกษา/เสริม ก่อนที่ใครจะพูด ---
        b_text, b_emotion = "", "neutral"
        if self.consultant is not None and self.robot_b is not None:
            self._ui_call(self._set_status,
                          f"🤫 {self._b_name} กำลังปรึกษากับ{self._a_name}...")
            try:
                user_text = next(
                    (str(m.get("content", "")) for m in reversed(self.history)
                     if m.get("role") == "user"), "")
                b_raw = self.consultant.review(user_text, clean, self.history)
                b_emotion = detect_emotion(b_raw)
                b_text = strip_emotion_tag(b_raw).strip()
                if b_text:
                    print(f"[GUI] 🤖 {self._b_name} เสริม: {b_text[:60]!r}")
            except Exception as exc:  # noqa: BLE001 — B ล่มไม่ให้แชทตาย
                print(f"[GUI] ⚠️ {self._b_name} ปรึกษาไม่สำเร็จ: {exc}")

        self.history.append({"role": "assistant", "content": clean})
        if b_text:
            self.history.append({"role": "assistant",
                                 "content": f"({self._b_name}เสริม) {b_text}"})
        print(f"[GUI] 🤖 ตอบ: {clean[:60]!r} | TTS={'on' if self._speak_var.get() else 'off'}"
              f" anim={'on' if self._anim_var.get() else 'off'}"
              f" auto-listen={'on' if self._listen_var.get() else 'off'}"
              + (f" | 🤝 {self._b_name} เสริม" if b_text else ""))
        self._ui_call(self._set_face, emotion)
        self._ui_call(self._append, self._a_name, f"{clean}\n[อารมณ์: {emotion}]")
        if b_text:
            self._ui_call(self._append, self._b_name,
                          f"{b_text}\n[อารมณ์: {b_emotion}]")
        self._ui_call(self._finish_turn)

        # ขยับ + พูด ในเธรดแยก (ไม่ให้ UI ค้างระหว่างเล่นเสียง)
        if self._speak_var.get() or self._anim_var.get():
            if b_text:
                threading.Thread(target=self._react_two,
                                 args=(emotion, clean, b_emotion, b_text),
                                 daemon=True).start()
            else:
                threading.Thread(target=self._react, args=(emotion, clean),
                                 daemon=True).start()
        if did_tool:
            self._ui_call(self._set_status, f"🛠️ {self._a_name}ทำท่าให้แล้ว")

    def _chat_with_tools(self) -> tuple[str, bool]:
        """คุย LLM แบบมี tool calling (ทำท่าได้) — คืน (ข้อความ, ได้ทำท่าไหม)

        เหมือน ask_llm() ใน voice_assistant แต่ตัดการกรอง TOOL_INTENT ออก
        (แชทพิมพ์มือ ไม่มีปัญหา STT ฟังเพี้ยน) และทำเฉพาะ tool ตัวแรก
        """
        ctx = build_time_context()
        sp = f"{ctx}\n\n{self.llm.system_prompt or ''}"
        msg = self.llm.chat_tools(self.history, TOOLS, system_prompt=sp)
        calls = msg.get("tool_calls") or []
        if not calls:
            # โมเดลเล็กบางตัวตอบชื่อ tool เป็นข้อความ (“stop_music”) แทน tool_call
            parsed = as_text_tool_call(msg.get("content"))
            if not parsed:
                return (msg.get("content") or "").strip(), False
            name, targs = parsed
            print(f"[GUI] แกะ tool จากข้อความ: {name}")
            calls = [{"function": {"name": name, "arguments": targs}}]
            msg["tool_calls"] = calls
            msg["content"] = ""

        fn = calls[0].get("function") or {}
        name = fn.get("name", "")
        print(f"[GUI] หุ่นทำท่า: {name}")
        self._ensure_robot_alive()   # กัน USB handle ตายก่อนขยับ
        try:
            result = execute_tool(self.robot, name, fn.get("arguments", {}),
                                  partner=self.robot_b)
        except Exception as exc:  # noqa: BLE001 — หุ่นหลุด ไม่ให้แชทตาย
            result = f"ทำท่าไม่สำเร็จ: {exc}"
            print(f"[GUI] ⚠️ {result}")
        self.history.append(msg)
        self.history.append({"role": "tool", "tool_name": name, "content": result})
        final = self.llm.chat_tools(self.history, None, system_prompt=sp)
        text = (final.get("content") or "").strip()
        if not text:
            # โมเดลเล็กบางครั้งคืนข้อความว่างหลังทำท่า — ใช้คำสั้น ๆ แทน
            # (ไม่ให้หุ่นพูดว่า "(ไม่มีข้อความ)")
            text = "เรียบร้อยจ้า! (happy)"
        return text, True

    def test_voice(self):
        """ปุ่ม 🔊 — เล่นเสียงทดสอบ: พี่ทด (ชาย) แล้วน้องนุ (หญิง) ถ้าเปิดโหมดหุ่นคู่"""
        def run():
            try:
                from src.tts import play_file, synthesize_to_file_cached
                lines = [(self._a_name, self._a_voice)]
                if self.robot_b is not None:
                    lines.append((self._b_name, self._b_voice))
                ok_all = True
                for name, voice in lines:
                    path = synthesize_to_file_cached(
                        f"สวัสดีจ้า นี่คือเสียงของ{name}", voice=voice)
                    ok = play_file(path) if path else False
                    ok_all = ok_all and ok
                    print(f"[GUI] 🔊 ทดสอบเสียง {name}: "
                          f"synth={bool(path)} play={ok} voice={voice}")
                self._ui_call(self._set_status,
                              "🔊 เล่นเสียงทดสอบแล้ว (ได้ยินไหม?)" if ok_all
                              else "⚠️ เล่นเสียงไม่ได้ — เช็คลำโพง/playsound")
            except Exception as exc:  # noqa: BLE001
                print(f"[GUI] 🔊 ทดสอบเสียงผิดพลาด: {exc}")
                self._ui_call(self._set_status, f"⚠️ เสียงผิดพลาด: {exc}")
        self._set_status("🔊 กำลังเล่นเสียงทดสอบ...")
        threading.Thread(target=run, daemon=True).start()

    def manual_action(self, tool_name: str):
        """ปุ่มทำท่าตรง ๆ (ไม่ต้องผ่าน LLM) — รันในเธรดแยก หุ่นหลุดไม่ทำให้แอปตาย"""
        def run():
            self._action_busy = True   # หยุดติดตามหน้าระหว่างทำท่า
            try:
                self._ensure_robot_alive()
                result = execute_tool(self.robot, tool_name, {}, partner=self.robot_b)
                self._ui_call(self._set_status, f"🛠️ {result}")
            except Exception as exc:  # noqa: BLE001
                self._ui_call(self._set_status, f"⚠️ ทำท่าไม่สำเร็จ: {exc}")
            finally:
                self._action_busy = False
        print(f"[GUI] ปุ่มทำท่า: {tool_name}")
        self._set_status(f"🛠️ กำลังทำท่า {tool_name}...")
        threading.Thread(target=run, daemon=True).start()

    # ---------- ตัวเฝ้าการเชื่อมต่อหุ่น (กัน "servo ไม่หมุน") ----------
    def _ensure_robot_alive(self) -> bool:
        """เช็คว่า serial ยังสั่ง servo ได้จริง — ถ้าไม่ ให้ reconnect

        กันเคส Windows zombie handle: หลัง USB re-enumerate เขียนผ่านได้
        แต่ข้อมูลไม่ถึง servo (ไม่มี error) → หุ่นนิ่งทั้งที่ log ขึ้นว่าทำท่า
        """
        try:
            check = getattr(self.robot, "check_connection", None)
            if check is None:
                return True
            if not check():
                print("[GUI] ⚠️ servo ไม่ตอบ — ลองเชื่อมต่อ USB ใหม่แล้ว")
                return False
        except Exception as exc:  # noqa: BLE001
            print(f"[GUI] ⚠️ เช็คการเชื่อมต่อผิดพลาด: {exc}")
        return True

    def _conn_watchdog(self):
        """วนเช็คทุก 10 วิ — เจอ handle ตายจะ reconnect ให้เอง + กัน flag ค้างถาวร"""
        while not self._closing:
            time.sleep(10.0)
            if self._closing:
                return
            # ราวกันตก: busy/speaking ค้างเกินกำหนด = หูหนวกถาวร → ปลดให้
            now = time.time()
            if self._busy and self._busy_since and now - self._busy_since > 90:
                print("[GUI] ⚠️ _busy ค้างเกิน 90วิ — รีเซ็ตให้ (กันหูหนวกถาวร)")
                self._busy = False
                self._ui_call(self._finish_turn)
            if self._speaking and self._speak_since and now - self._speak_since > 90:
                print("[GUI] ⚠️ _speaking ค้างเกิน 90วิ — รีเซ็ตให้")
                self._speaking = False
            if not self._ensure_robot_alive():
                self._ui_call(self._set_status,
                              "⚠️ หุ่นไม่ตอบ USB — เช็คสาย/ลองเสียบพอร์ตอื่น")

    def _react(self, emotion: str, text: str):
        """ขยับหุ่น + พูด (เรียกจาก worker thread) — หุ่นหลุดไม่ทำให้แอปตาย"""
        self._speak_since = time.time()
        self._speaking = True
        try:
            self._react_one(self.robot, emotion, text)
        finally:
            self._speaking = False
            # กันสตรีมไมค์ค้างหลังหุ่นพูด (เจอจริง: หลังตอบ สตรีมส่งศูนย์เป๊ะ)
            # worker จะเป็นคนรีเฟรช (เธรดเดียวคุม stream — กันชน)
            self._refresh_mic = True

    def _react_two(self, emo_a: str, txt_a: str, emo_b: str, txt_b: str):
        """🤝 หุ่น A พูดก่อน → B เสริม — `_speaking` ครอบทั้งสองช่วง (ไมค์ mute ตลอด)"""
        self._speak_since = time.time()
        self._speaking = True
        try:
            self._react_one(self.robot, emo_a, txt_a)
            if self.robot_b is not None and txt_b:
                self._react_one(self.robot_b, emo_b, txt_b)
        finally:
            self._speaking = False
            self._refresh_mic = True

    def _react_one(self, robot, emotion: str, text: str):
        """ขยับ+พูดของหุ่นตัวเดียว — error ไม่ล้มทั้งแอป"""
        try:
            if robot is self.robot:
                self._ensure_robot_alive()   # กัน USB handle ตาย
            elif hasattr(robot, "check_connection"):
                try:
                    robot.check_connection()
                except Exception:  # noqa: BLE001
                    pass
            if self._anim_var.get():
                apply_emotion(robot, emotion)
            if self._speak_var.get():
                voice = self._a_voice if robot is self.robot else self._b_voice
                speak_with_motion(robot, text, voice=voice)
        except Exception as exc:  # noqa: BLE001
            print(f"[GUI] ขยับ/พูดผิดพลาด ({type(robot).__name__}): {exc}")

    # ---------- โหมดฟังอัตโนมัติ (ไมค์เปิดค้าง) ----------
    def _on_listen_toggle(self):
        """เปิด/ปิดโหมดฟังอัตโนมัติ — เปิด = ไมค์เปิดค้าง พูดได้ตลอด"""
        on = self._listen_var.get()
        print(f"[GUI] 🎧 ฟังอัตโนมัติ = {'เปิด' if on else 'ปิด'}")
        if on:
            self._start_continuous()
        else:
            self._stop_continuous()
        self.mic_btn.configure(state=("disabled" if on else "normal"))

    def _start_continuous(self):
        """เปิดไมค์ค้าง (always-on) — ไม่พลาดต้นประโยคเหมือนการฟังเป็นรอบ"""
        if self._cont is not None or self._closing:
            return
        try:
            from src.stt import ContinuousMic

            cfg = get_config()["stt"]
            self._cont = ContinuousMic(
                mic=(self._mic_index if self._mic_index is not None else cfg.get("mic")),
                samplerate=cfg["samplerate"],
                tail_silence=cfg.get("tail_silence", 1.2),
                speech_threshold=cfg.get("speech_threshold", 0.025),
            )
            self._cont.start()
            if self._thr_manual is None:
                thr = float(self._cont.calibrate(1.0))   # วัดเสียงรบกวนห้อง → ตั้งเกณฑ์ให้เหมาะกับไมค์ตัวนี้
            else:
                thr = self._thr_manual                   # ผู้ใช้ตั้งเอง → calibrate ห้ามทับ
                self._cont.speech_threshold = thr
                print(f"[GUI] 🎚 ใช้เกณฑ์ที่ตั้งเอง {thr:.3f} (ข้าม calibrate)")
            if getattr(self, "_thr_scale", None) is not None:
                self._sync_thr_slider(thr)   # ให้สไลเดอร์ตรงกับค่าจริงเสมอ
            threading.Thread(target=self._continuous_worker, daemon=True).start()
            print(f"[GUI] 🎧 เปิดไมค์ค้าง (mic={self._mic_index}) — พูดได้เลย")
            self._set_status("🎧 ฟังอยู่ตลอด — พูดได้เลย")
            self._set_face("listen")
        except Exception as exc:  # noqa: BLE001
            self._cont = None
            print(f"[GUI] 🎧 เปิดไมค์ไม่ได้: {exc}")
            self._set_status(f"⚠️ เปิดไมค์ไม่ได้: {exc}")

    def _stop_continuous(self):
        if self._cont is not None:
            self._cont.stop()
            self._cont = None
        self._set_status("🎧 ปิดฟังอัตโนมัติ — กด 🎤 เมื่อจะพูด")

    # ---------- 🎚 สไลเดอร์เกณฑ์รับเสียง + 📊 VU meter ----------
    def _sync_thr_slider(self, value: float):
        """ตั้งตำแหน่งสไลเดอร์ตามค่าจริง (ไม่บันทึก/ไม่เปลี่ยนค่าที่ใช้อยู่)"""
        self._thr_syncing = True
        try:
            self._thr_last = round(float(value), 3)
            self._thr_scale.set(self._thr_last)
            self._thr_lbl.configure(text=f"{self._thr_last:.3f}")
        finally:
            self._thr_syncing = False

    def _on_thr_change(self, value):
        """ผู้ใช้เลื่อนสไลเดอร์ → มีผลกับไมค์ค้างทันที + ล็อกค่า (calibrate ห้ามทับ)"""
        if self._thr_syncing:
            return
        val = round(float(value), 3)
        if val == self._thr_last:   # ค่าเดิม (เช่น set() ยิง command ซ้ำ) — ข้าม
            return
        self._thr_last = val
        self._thr_lbl.configure(text=f"{val:.3f}")
        self._thr_manual = val
        if self._thr_auto_var.get():   # เลื่อนเอง = ปิดออโต้ให้เลย
            self._thr_auto_var.set(False)
            print("[GUI] 🎚 ตั้งเกณฑ์เอง → ปิดโหมดอัตโนมัติ")
        if self._cont is not None:
            self._cont.speech_threshold = val   # มีผลทันทีกับไมค์ค้าง
        self._set_status(f"🎚 เกณฑ์เสียง {val:.3f} — พูดให้แถบเขียวพ้นขีดส้ม")
        self._schedule_thr_save(val)

    def _bump_thr(self, delta: float):
        """ปุ่ม ➖/➕ — ขยับทีละ 0.005"""
        cur = float(self._thr_scale.get())
        new = round(min(0.100, max(0.005, cur + delta)), 3)
        self._thr_scale.set(new)
        self._on_thr_change(new)   # เผื่อ Tk ไม่ยิง command ตอน set() (ยิงซ้ำก็ข้ามเอง)

    def _schedule_thr_save(self, val: float):
        """หน่วงบันทึก ~0.6 วิ — ระหว่างลากสไลเดอร์จะได้ไม่เขียนไฟล์รัว ๆ"""
        if self._thr_save_job is not None:
            try:
                self.root.after_cancel(self._thr_save_job)
            except Exception:  # noqa: BLE001
                pass
        self._thr_save_job = self.root.after(600, lambda: self._save_thr(val))

    def _save_thr(self, val: float):
        self._thr_save_job = None
        try:
            from config.robot_config import save_local_config
            save_local_config({"stt": {"speech_threshold": val, "thr_manual": True}})
        except Exception as exc:  # noqa: BLE001
            print(f"[GUI] บันทึกเกณฑ์เสียงไม่ได้: {exc}")
        print(f"[GUI] 🎚 เกณฑ์รับเสียง = {val:.3f} (ตั้งเอง — จำไว้ใช้ครั้งหน้า)")

    def _on_thr_auto(self):
        """ติ๊ก 'อัตโนมัติ' → calibrate วัดเสียงห้องใหม่ / ถอดติ๊ก = ล็อกค่าปัจจุบัน"""
        if self._thr_syncing:
            return
        if self._thr_auto_var.get():
            self._thr_manual = None
            thr = None
            if self._cont is not None and not self._closing:
                try:
                    thr = float(self._cont.calibrate(1.0))
                except Exception as exc:  # noqa: BLE001
                    print(f"[GUI] 🎚 calibrate ไม่สำเร็จ: {exc}")
            if thr is not None:
                self._sync_thr_slider(thr)
            try:
                from config.robot_config import save_local_config
                save_local_config({"stt": {"thr_manual": False}})
            except Exception as exc:  # noqa: BLE001
                print(f"[GUI] บันทึกโหมดเกณฑ์เสียงไม่ได้: {exc}")
            cur = float(self._thr_scale.get())
            print(f"[GUI] 🎚 เกณฑ์รับเสียง: อัตโนมัติ (ตอนนี้ {cur:.3f})")
            self._set_status(f"🎚 เกณฑ์อัตโนมัติ — ตอนนี้ {cur:.3f}")
        else:
            val = round(float(self._thr_scale.get()), 3)
            self._thr_manual = val
            self._thr_last = val
            if self._cont is not None:
                self._cont.speech_threshold = val
            print(f"[GUI] 🎚 ล็อกเกณฑ์ที่ {val:.3f} (ตั้งเอง)")
            self._schedule_thr_save(val)

    def _update_vu(self):
        """📊 วาด VU meter ระดับไมค์ (เรียกจาก main thread ทุก ~30ms ผ่าน _pump_video)

        - แถบ: เขียวหม่น = ยังไม่ถึงเกณฑ์ · เขียวสด = ถึงเกณฑ์ (STT ได้ยิน) · แดง = เกือบ clip · เทา = mute
        - ขีดส้ม = ตำแหน่ง speech_threshold (เลื่อนสไลเดอร์แล้วขยับตามทันที)
        - เส้นสี fg = peak-hold (ค่อย ๆ ลด)
        """
        c = getattr(self, "_vu_canvas", None)
        if c is None:
            return
        T = self.T
        try:
            w = int(c.winfo_width())
            h = int(c.winfo_height())
        except Exception:  # noqa: BLE001
            return
        if w <= 4 or h <= 4:
            return   # ยังไม่ถูกจัดวาง — ข้ามรอบนี้
        cont = self._cont
        VMAX = 0.15   # สเกลเต็มแถบ (RMS 0.15 = ดังสุด)

        def xpos(v: float) -> float:
            r = min(max(v, 0.0), VMAX) / VMAX
            return 2.0 + (w - 4.0) * (r ** 0.5)   # สเกลรากที่สอง — ค่าเบา ๆ เห็นชัด

        c.delete("all")
        c.create_rectangle(1, 1, w - 1, h - 1, fill=T["panel"], outline="")
        if cont is None:
            c.create_text(w / 2, h / 2, text="— ปิดไมค์ —", fill=T["sys_fg"],
                          font=T["font"])
            self._vu_lbl.configure(text="—")
            self._vu_state.configure(text="")
            return
        rms = float(getattr(cont, "_last_rms", 0.0))
        pk = float(getattr(cont, "_last_pk", 0.0))
        thr = float(cont.speech_threshold)
        muted = bool(cont.mute)
        rec = bool(getattr(cont, "_recording", False))
        # peak-hold ค่อย ๆ ลด (รีเซ็ตตอนหุ่นพูด/ปิดไมค์)
        self._vu_peak = 0.0 if muted else max(pk, self._vu_peak * 0.985)
        if muted:
            color = "#8A9BA8"    # หุ่นกำลังพูด — เสียงถูกทิ้ง
        elif rms >= VMAX * 0.9:
            color = "#E5484D"    # ใกล้ clip
        elif rms >= thr:
            color = "#3ECF6E"    # ถึงเกณฑ์ → STT ได้ยิน
        else:
            color = "#6B8F7A"    # ยังไม่ถึงเกณฑ์
        if rms > 1e-5:
            x = xpos(rms)
            c.create_rectangle(2, 3, max(x, 3), h - 3, fill=color, outline="")
        if self._vu_peak > 5e-4:
            px = xpos(self._vu_peak)
            c.create_line(px, 2, px, h - 2, fill=T["fg"], width=2)
        tx = xpos(thr)   # 🟠 ขีดเกณฑ์ปัจจุบัน
        c.create_line(tx, 1, tx, h - 1, fill="#FF8A00", width=2)
        if muted:
            state = "🔇 รอหุ่นพูดจบ"
        elif rec:
            state = "🎤 กำลังอัด…"
        elif rms >= thr:
            state = "✅ ได้ยิน"
        else:
            state = ""
        txt = f"{rms:.3f}"
        if self._vu_lbl.cget("text") != txt:
            self._vu_lbl.configure(text=txt)
        if self._vu_state.cget("text") != state:
            self._vu_state.configure(text=state)

    # ---------- 🔔 popup เตือนจังหวะพูด ----------
    def _notify_turn(self, state, text: str | None = None):
        """popup ลอยเหนือหน้าต่าง — 'wait' = รอหุ่น (ค้างไว้) · 'go' = ถึงตาคุณ (3.5 วิ) · None = ซ่อน"""
        if self._popup_job is not None:
            try:
                self.root.after_cancel(self._popup_job)
            except Exception:  # noqa: BLE001
                pass
            self._popup_job = None
        if state is None:
            self._popup_state = None
            self._popup_text = None
            if self._popup is not None:
                self._popup.withdraw()
            return
        if self._popup is None:
            p = tk.Toplevel(self.root)
            p.overrideredirect(True)   # ไม่มีกรอบ/ไม่แย่งโฟกัสการพิมพ์
            try:
                p.attributes("-topmost", True)
                p.attributes("-alpha", 0.96)
            except Exception:  # noqa: BLE001
                pass
            self._popup_frame = tk.Frame(p, padx=20, pady=9)
            self._popup_frame.pack()
            fam = self.T["font_bold"][0]
            self._popup_lbl = tk.Label(self._popup_frame, text="",
                                       font=(fam, 13, "bold"))
            self._popup_lbl.pack()
            self._popup = p
        bg, fg = (("#F6C453", "#3A2C00") if state == "wait"
                  else ("#3ECF6E", "#093C1B"))
        if text is None:
            text = (f"⏳ รอ{self._a_name}พูดจบก่อนนะ…" if state == "wait"
                    else "🎤 ถึงตาคุณแล้ว — พูดได้เลย!")
        self._popup_frame.configure(bg=bg)
        self._popup_lbl.configure(text=text, bg=bg, fg=fg)
        p = self._popup
        p.deiconify()
        p.lift()
        p.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - p.winfo_reqwidth()) // 2
        p.geometry(f"+{max(x, 0)}+{max(self.root.winfo_rooty() + 10, 0)}")
        self._popup_state, self._popup_text = state, text
        if state == "go":            # "ถึงตาพูด" โชว์แป๊บเดียวแล้วหาย
            self._popup_job = self.root.after(3500, lambda: self._notify_turn(None))
        print(f"[GUI] 🔔 popup: {state} — {text}")

    def _update_turn_popup(self):
        """🔔 trigger จากสถานะ mute จริง (เรียกทุก ~30ms จาก _pump_video)

        หุ่น busy/พูด (ไมค์ถูก mute) → โชว์ 'รอ…' ค้างไว้
        เพิ่งพูดจบ (mute หลุด) → แฟลช 'ถึงตาคุณ — พูดได้เลย!' 3.5 วิ
        """
        if not self._listen_var.get():   # ปิดฟังอัตโนมัติ = ไม่มีจังหวะให้เตือน
            if self._popup_state is not None:
                self._notify_turn(None)
            self._muted_prev = False
            return
        muted = bool(self._busy or self._speaking)
        if muted:
            txt = (f"⏳ รอ{self._a_name}พูดจบก่อนนะ…" if self._speaking
                   else f"🤔 {self._a_name}กำลังคิด…")
            if self._popup_state != "wait" or self._popup_text != txt:
                self._notify_turn("wait", txt)
        elif self._muted_prev:
            self._notify_turn("go")      # เพิ่งพูดจบ → ถึงตาคุณ
        self._muted_prev = muted

    def restart_mic(self):
        """♻️ ปิด-เปิดไมค์ค้างใหม่ — กู้กรณีไมค์ค้างเงียบด้วยคลิกเดียว"""
        if not self._listen_var.get():
            self._set_status("🎧 เปิด 'ฟังอัตโนมัติ' ก่อน แล้วค่อยกดรีสตาร์ทไมค์")
            return
        print("[GUI] ♻️ รีสตาร์ทไมค์ (ตามคำขอผู้ใช้)")
        self._stop_continuous()
        self._start_continuous()

    def _continuous_worker(self):
        """เธรดฟังต่อเนื่อง: รอจนผู้ใช้พูดจบ → ส่ง STT → ถาม LLM

        ผูกกับไมค์ตัวที่เปิดตอนเริ่ม — เปลี่ยนไมค์กลางทาง = เธรดนี้จบ (เริ่มตัวใหม่แทน)
        """
        cont = self._cont
        last_hb = time.time()
        last_signal = time.time()   # เวลาล่าสุดที่ยังเห็นสัญญาณจริง (กันสตรีมส่งศูนย์เป๊ะ)
        while cont is self._cont and not self._closing:
            # ขณะหุ่นคิด/พูด → ทิ้งเสียงทั้งหมด (กันหุ่นได้ยินเสียงตัวเอง)
            cont.mute = self._busy or self._speaking
            # ♻️ รีเฟรชสตรีมหลังหุ่นพูดจบ — ล้างอาการ "สตรีมส่งศูนย์" ก่อนผู้ใช้พูดคำต่อไป
            if self._refresh_mic:
                self._refresh_mic = False
                try:
                    cont.stop()
                    time.sleep(0.1)
                    cont.start()
                    last_signal = time.time()
                    print("[GUI] ♻️ รีเฟรชไมค์หลังหุ่นพูดจบ")
                except Exception as exc:  # noqa: BLE001
                    print(f"[GUI] ♻️ รีเฟรชไมค์ไม่สำเร็จ: {exc}")
            clip = cont.read_utterance(timeout=0.3)
            if clip is None:
                now = time.time()
                # ★ ตรวจตรง ๆ: cb สดแต่สัญญาณศูนย์เป๊ะติดกัน 8 วิ = สตรีมแจกความว่างเปล่า
                if cont._sig_peak > 5e-4:
                    last_signal = now
                elif now - last_signal > 8.0:
                    print("[GUI] ♻️ ไม่มีสัญญาณไมค์ 8 วิ — เปิดสตรีมใหม่")
                    try:
                        cont.stop()
                        time.sleep(0.2)
                        cont.start()
                    except Exception as exc:  # noqa: BLE001
                        print(f"[GUI] ♻️ รีสตาร์ทไมค์ไม่สำเร็จ: {exc}")
                    last_signal = now
                cont.ensure_alive()   # ♻️ เส้นทางสำรอง (ไม่มี callback / เงียบเป๊ะ)
                if now - last_hb >= 10.0:   # 💓 heartbeat — วินิจฉัยว่าหูหนวกเพราะอะไร
                    last_hb = now
                    print(f"[GUI] 💓 ฟังอยู่ | mute={cont.mute} busy={self._busy} "
                          f"speaking={self._speaking} thr={cont.speech_threshold:.3f} "
                          f"pk={cont._sig_peak:.3f} rms={cont._rms_peak:.3f} "
                          f"vr={cont._voice_run:.2f} cb={now - cont._last_cb:.1f}s")
                continue
            if self._busy or self._speaking or self._closing:
                continue   # คลิปนั้นเกิดขึ้นตอนหุ่นพูด — ทิ้ง
            print(f"[GUI] 🎤 ได้ยินเสียง {len(clip) / cont.samplerate:.1f}s — กำลังถอดความ...")
            self._ui_call(self._set_status, "⏳ กำลังถอดความ...")
            self._transcribing = True
            try:
                text = self._transcribe(clip)
            finally:
                self._transcribing = False
            if text:
                print(f"[GUI] 🎤 ได้ยิน: {text!r}")
                self._ui_call(self.ask, text)
            else:
                self._ui_call(self._set_status, "🔇 ไม่ได้ยินเสียง — ลองอีกครั้ง")

    def _transcribe(self, clip) -> str:
        """ส่งคลิปเสียงไป STT — remote ก่อน, ล่มกลางทางใช้ whisper local แทน (ช้ากว่าแต่ได้ยิน)"""
        cfg = get_config()["stt"]
        try:
            from src.stt import (audio_to_wav_bytes, looks_like_hallucination,
                                 normalize, transcribe, transcribe_remote)

            audio = normalize(clip)
            wav = audio_to_wav_bytes(audio, cfg["samplerate"])
            if self._save_audio:
                out = Path("cache") / "stt_debug" / f"{time.strftime('%H%M%S')}.wav"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(wav)
                print(f"[STT] บันทึกเสียงตรวจสอบ: {out}")
            if cfg.get("stt_url"):
                try:
                    text = transcribe_remote(
                        wav, cfg["stt_url"],
                        timeout=float(cfg.get("timeout", 20)),
                        api_key=cfg.get("api_key"))
                    # ⚠️ คิด rms จากคลิปดิบ (ก่อน normalize) — rms หลัง normalize ถูกขยาย
                    #    ตาม peak จนคลิปเสียงรบกวนก็เกินเกต 0.06 (คลิป 011312 หลุดจริง 17/9)
                    raw_rms = float((clip.astype("float64") ** 2).mean() ** 0.5)
                    if looks_like_hallucination(text, raw_rms):
                        print(f"[STT] ตัด hallucination {text!r} "
                              f"(rms_dิบ={raw_rms:.3f}) — ขอผู้ใช้พูดใหม่")
                        return ""
                    return text
                except Exception as exc:  # noqa: BLE001 — server ล่ม → fallback ในเครื่อง
                    print(f"[GUI] STT remote ล่ม ({exc}) → ใช้ whisper local (small)")
                    self._ui_call(self._set_status,
                                  "🐢 server ตอบช้า — ใช้โมเดลในเครื่อง (รอสักครู่)...")
            # local: small ให้ภาษาไทยดีกว่า base (โมเดลโหลดครั้งแรกช้าหน่อย)
            return transcribe(audio, model="small", device=cfg.get("device", "auto"),
                              language=cfg.get("language", "th"))
        except Exception as exc:  # noqa: BLE001
            print(f"[GUI] STT ผิดพลาด: {exc}")
            return ""

    def _finish_turn(self):
        self._busy = False
        self.send_btn.configure(state="normal")
        self._set_status(f"พร้อมแล้ว — โมเดล {self.llm.model}")
        # โหมดฟังอัตโนมัติ: ไมค์เปิดค้างอยู่แล้ว — ไม่ต้องจัดคิวฟังใหม่

    # ---------- ปุ่ม/ตัวเลือก ----------
    def measure_mic(self):
        """ปุ่ม 🎙 — อัด 2 วิ แล้วรายงานระดับเสียง (ไว้ปรับ speech_threshold)"""
        def run():
            try:
                import numpy as np

                from src.stt import record
                cfg = get_config()["stt"]
                audio = record(duration=2.0, samplerate=cfg["samplerate"],
                               mic=self._mic_index, early_stop=False)
                rms = float(np.sqrt(np.mean(audio.astype("float64") ** 2))) if audio.size else 0.0
                thr = (float(self._cont.speech_threshold) if self._cont is not None
                       else float(cfg.get("speech_threshold", 0.025)))
                print(f"[GUI] 🎙 ระดับเสียง: RMS={rms:.4f} peak="
                      f"{float(np.abs(audio).max()) if audio.size else 0:.3f} | "
                      f"speech_threshold={thr}")
                self._ui_call(self._set_status,
                              "🎙 ได้ยินชัด! (พูดผ่านเกณฑ์)" if rms >= thr else
                              f"🎙 เบาไป — RMS {rms:.3f} < เกณฑ์ {thr:.3f} "
                              "(ลองพูดใกล้ไมค์ หรือเลื่อนสไลเดอร์ 🎚 ลง)")
            except Exception as exc:  # noqa: BLE001
                print(f"[GUI] 🎙 วัดเสียงผิดพลาด: {exc}")
                self._ui_call(self._set_status, f"⚠️ วัดเสียงไม่ได้: {exc}")
        self._set_status("🎙 กำลังวัดระดับเสียง 2 วิ — พูดได้เลย!")
        threading.Thread(target=run, daemon=True).start()

    def listen_click(self):
        """🎤 → STT → เติมข้อความ → ส่งอัตโนมัติ (กันเรียกซ้ำจนฟังซ้อนกัน)"""
        if self._busy or self._listening:
            return
        self._listening = True
        self._set_status("🎤 กำลังฟัง... (พูดภาษาไทย)")
        self._set_face("listen")
        threading.Thread(target=self._listen_worker, daemon=True).start()

    def _listen_worker(self):
        try:
            self._listen_once()
        finally:
            self._listening = False   # ★ ปล่อยล็อกให้รอบถัดไปฟังได้

    def _listen_once(self):
        try:
            cfg = get_config()["stt"]
            from src.stt import listen

            print(f"[GUI] 🎤 เริ่มฟัง (mic={self._mic_index}, "
                  f"stt_url={cfg.get('stt_url')}) ...")
            save_path = None
            if self._save_audio:
                save_path = str(Path("cache") / "stt_debug" /
                                f"{time.strftime('%H%M%S')}.wav")
            text = listen(
                duration=cfg["duration"], samplerate=cfg["samplerate"],
                language=cfg["language"], model=cfg["model"], device=cfg["device"],
                mic=(self._mic_index if self._mic_index is not None else cfg.get("mic")),
                stt_url=cfg.get("stt_url"),
                early_stop=cfg.get("early_stop", True),
                tail_silence=cfg.get("tail_silence", 0.6),
                speech_threshold=cfg.get("speech_threshold", 0.01),
                stt_api_key=cfg.get("api_key"),
                save_debug=save_path,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[GUI] 🎤 ฟังผิดพลาด: {exc}")
            self._ui_call(self._set_status, f"⚠️ STT ผิดพลาด: {exc}")
            return
        if not text:
            print("[GUI] 🎤 ไม่ได้ยินเสียง (หรือเสียงเบากว่า speech_threshold)")
            self._ui_call(self._set_status, "🔇 ไม่ได้ยินเสียง — ลองอีกครั้ง")
            return
        print(f"[GUI] 🎤 ได้ยิน: {text!r}")
        self._ui_call(self.ask, text)

    # ================= ปิดแอป =================
    def close(self):
        self._closing = True
        self._stop_continuous()
        try:
            if self._gesture_rec:
                self._gesture_rec.close()
        except Exception:  # noqa: BLE001
            pass
        self._cam_stop.set()
        if self._cam_thread:
            self._cam_thread.join(timeout=1.5)
        try:   # หยุดเต้นตามเพลง (ถ้ามี) ก่อนปิดพอร์ต
            from src import dance_sync
            dance_sync.stop_dance("ปิดแอป")
        except Exception:  # noqa: BLE001
            pass
        try:
            self.robot.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self.robot_b is not None:
                self.robot_b.close()
        except Exception:  # noqa: BLE001
            pass
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="Reachy Mini — GUI แชท + กล้อง")
    parser.add_argument("--hardware", action="store_true", help="ใช้หุ่นจริง (STS3215)")
    parser.add_argument("--port", default=None, help="COM port (default auto)")
    parser.add_argument("--real", action="store_true", help="ใช้ official daemon (RealRobot)")
    parser.add_argument("--robot-gui", action="store_true",
                        help="เปิดหน้าต่าง MuJoCo 3D ด้วย (โหมด sim)")
    parser.add_argument("--camera", default="lifecam",
                        help="กล้อง: ชื่อบางส่วน (lifecam) หรือ index (0,1) — default lifecam")
    parser.add_argument("--theme", default="kid", choices=("kid", "dark"),
                        help="ธีมหน้าตา: kid = น่ารักสำหรับเด็ก (ค่าเริ่มต้น) | dark = โหมดเดิม")
    parser.add_argument("--model", default=None, help="โมเดล LLM (default จาก config)")
    parser.add_argument("--list-cameras", action="store_true", help="แสดงกล้องทั้งหมดแล้วออก")
    parser.add_argument("--list-mics", action="store_true", help="แสดงไมค์ทั้งหมดแล้วออก")
    parser.add_argument("--save-audio", action="store_true",
                        help="บันทึกเสียงที่อัดแต่ละรอบลง cache/stt_debug/ (ไว้ตรวจคุณภาพเสียง)")
    parser.add_argument("--smoke", type=float, default=0, metavar="SEC",
                        help="โหมดทดสอบ: ซ่อนหน้าต่าง รัน SEC วินาที (เปิดกล้องถ้าระบุ --camera)")
    parser.add_argument("--smoke-ask", default=None, metavar="ข้อความ",
                        help="โหมดทดสอบ: ส่งข้อความนี้เข้าแชทอัตโนมัติ (ปิดเสียง/ท่า)")
    parser.add_argument("--robot-b", choices=("none", "sim", "hardware"), default="none",
                        help="หุ่นตัวที่ 2 สำหรับโหมด 'ปรึกษากันก่อนตอบ' "
                             "(sim = ยังไม่ต้องมีฮาร์ดแวร์)")
    parser.add_argument("--port-b", default=None, help="COM port ของหุ่น B")
    args = parser.parse_args()

    if args.list_cameras:
        for i, name in list_cameras() or [(None, "(ไม่พบกล้อง)")]:
            print(f"  [{i}] {name}")
        return

    if args.list_mics:
        for i, name in AppGUI._list_mics_safe() or [(None, "(ไม่พบไมค์)")]:
            print(f"  [{i}] {name}")
        return

    cfg = get_config()
    llm_cfg = cfg["llm"]
    model = args.model or llm_cfg["model"]

    client = OllamaClient(
        url=llm_cfg["url"], model=model, api_key=llm_cfg.get("api_key"),
        system_prompt=llm_cfg.get("system_prompt"),
        temperature=llm_cfg.get("temperature", 0.7),
        timeout=llm_cfg.get("timeout", 25.0),
        num_predict=llm_cfg.get("num_predict"),
        max_history=llm_cfg.get("max_history"),
        think=llm_cfg.get("think", False),
        keep_alive=llm_cfg.get("keep_alive", "m"),
    )
    if not client.ping():
        print("⚠️ LLM server ไม่พร้อม — แชทจะตอบไม่ได้ (แต่กล้องยังใช้ได้)")

    # --- 🎨 MuJoCo สองหุ่นในหน้าต่างเดียว (โหมด sim คู่ + --robot-gui) ---
    pair_views = None
    if (args.robot_gui and not args.hardware and not args.real
            and args.robot_b == "sim"):
        try:
            from src.mujoco_sim import create_pair_viewers

            pair_views = create_pair_viewers(cfg)
            print("[GUI] 🎨 MuJoCo หน้าต่างเดียว 2 หุ่น — "
                  f"{cfg.get('robot', {}).get('name', 'พี่ทด')} สีเขียว · "
                  f"{cfg.get('robot_b', {}).get('name', 'น้องนุ')} สีขาว")
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ เปิด MuJoCo คู่ไม่สำเร็จ ({exc}) — ใช้ sim ธรรมดา")
            pair_views = None

    # --- robot ---
    if args.real:
        from src.real_robot import RealRobot

        if not RealRobot.available():
            print("⚠️ official daemon ไม่พร้อม — รัน reachy-mini-daemon ก่อน")
            sys.exit(1)
        robot = RealRobot()
    else:
        backend = "hardware" if args.hardware else "sim"
        try:
            robot = Robot(
                backend=backend, port=(args.port or cfg.get("port")),
                gui=("mujoco" if (args.robot_gui and backend == "sim"
                                  and pair_views is None) else False),
                viewer=(pair_views[0] if pair_views else None),
            )
        except Exception as exc:  # noqa: BLE001 — บอกทางแก้ให้ชัด แทน traceback ยาว ๆ
            print(f"❌ เปิดหุ่นไม่สำเร็จ ({backend}): {exc}")
            if backend == "hardware":
                print("   → เช็คสาย USB-TTL / ลองเสียบพอร์ต USB อื่น แล้วทดสอบ: "
                      ".venv\\Scripts\\python.exe scripts\\scan_servos.py")
            sys.exit(1)
    try:  # กัน USB zombie handle ตั้งแต่เปิดแอป — ให้ wake_up ขยับได้จริง
        if hasattr(robot, "check_connection"):
            robot.check_connection()
    except Exception:  # noqa: BLE001
        pass
    robot.wake_up()

    # --- 🤝 หุ่น B (โหมดสองตัวปรึกษากันก่อนตอบ) ---
    robot_b = None
    consultant = None
    if args.robot_b != "none":
        try:
            from config.robot_config import get_config as _get_cfg_b
            cfg_b = _get_cfg_b("b")          # cal ของน้องนุ (calibration_b.json)
            b_sec = cfg.get("robot_b") or {}
            if not b_sec.get("antennas", True):
                cfg_b.setdefault("antennas", {})["enabled"] = False   # ไม่มีเสาอากาศ
            if b_sec.get("motor"):
                cfg_b.setdefault("motor", {}).update(b_sec["motor"])   # เช่น torque_limit 12V
            port_b = args.port_b or b_sec.get("port")               # COM3 (น้องนุ)
            robot_b = Robot(backend=args.robot_b, port=port_b,
                            config=cfg_b,
                            viewer=(pair_views[1]
                                    if pair_views and args.robot_b == "sim" else None))
            robot_b.wake_up()
        except Exception as exc:  # noqa: BLE001 — B ล่มไม่ให้แอปตาย
            print(f"⚠️ เปิดหุ่น B ไม่สำเร็จ ({exc}) — ใช้โหมดหุ่นเดี่ยวต่อ")
            robot_b = None
    if robot_b is not None:
        bcfg = cfg.get("robot_b", {})
        bllm = bcfg.get("llm", {})
        llm_b = OllamaClient(
            url=llm_cfg["url"],
            model=(bllm.get("model") or model),
            api_key=llm_cfg.get("api_key"),
            system_prompt=bcfg.get("system_prompt"),
            temperature=bllm.get("temperature", 0.6),
            timeout=llm_cfg.get("timeout", 25.0),
            num_predict=bllm.get("num_predict", 160),
            max_history=llm_cfg.get("max_history"),
            think=llm_cfg.get("think", False),
            keep_alive=llm_cfg.get("keep_alive", "m"),
        )
        consultant = TwoRobotConsultant(
            client, llm_b,
            name_a=(cfg.get("robot") or {}).get("name", "พี่ทด"),
            name_b=bcfg.get("name", "น้องนุ"))
        print(f"[GUI] 🤝 เปิดโหมดหุ่นคู่: {bcfg.get('name', 'น้องนุ')} "
              f"({args.robot_b}) — ปรึกษากันก่อนตอบ")

    root = tk.Tk()
    if args.smoke:
        root.withdraw()  # ซ่อนหน้าต่าง (โหมดทดสอบ/CI)
    app = AppGUI(root, robot, client, cam_spec=args.camera, theme=args.theme,
                 robot_b=robot_b, consultant=consultant)
    app._save_audio = args.save_audio
    root.protocol("WM_DELETE_WINDOW", app.close)

    if args.smoke:
        # โหมดทดสอบ: เปิดกล้อง (ถ้าสั่ง) + รัน loop สั้น ๆ แล้วสรุปผล
        app._track_var.set(False)
        app._tracking = False    # โหมดทดสอบ: ไม่ขยับหุ่นตามหน้า
        app._gesture_var.set(False)
        app._gesture_on = False  # โหมดทดสอบ: ไม่ทำท่าตามมือ
        if args.camera is not None and str(args.camera).lower() != "none":
            app._start_camera()
        if args.smoke_ask:
            app._speak_var.set(False)   # ไม่เล่นเสียง/ไม่ขยับ ระหว่างทดสอบ
            app._anim_var.set(False)
            app._listen_var.set(False)
            app.ask(args.smoke_ask)
            t_wait = time.time() + max(args.smoke, 20.0)
            while time.time() < t_wait and app._busy:
                root.update()
                time.sleep(0.02)
            last = app.history[-1]["content"] if app.history else "(ว่าง)"
            print(f"[smoke] ถาม: {args.smoke_ask}")
            print(f"[smoke] ตอบ: {last[:120]}")
        t_end = time.time() + args.smoke
        while time.time() < t_end:
            root.update()
            time.sleep(0.02)
        print(f"[smoke] เฟรมที่แสดง: {app._frames_shown} | กล้อง: {app._cam_choice.get()} | ไมค์: {app._mic_choice.get()}")
        print("[smoke] OK ✅")
        app.close()
        return

    # เปิดกล้องให้เลยตั้งแต่เปิดแอป (กด "ปิดกล้อง" ทีหลังได้)
    app._start_camera()
    # โหมดฟังอัตโนมัติ (ค่าเริ่มต้น): เปิดไมค์ค้าง พูดได้เลยไม่ต้องกดปุ่ม
    if app._listen_var.get():
        root.after(1500, app._start_continuous)

    try:
        root.mainloop()
    finally:
        try:
            robot.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
