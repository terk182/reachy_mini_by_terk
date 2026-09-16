"""GUI แชทกับ Reachy Mini ผ่าน LLM (Ollama local)

- พิมพ์คุย -> LLM ตอบ -> หุ่นขยับตามอารมณ์ + พูดเสียง (TTS)
- แสดงหน้าต่าง 3D หุ่น (MuJoCo) ในโหมดจำลอง

วิธีใช้:
    python scripts/chat_gui.py                  # sim + MuJoCo 3D (หุ่น DIY)
    python scripts/chat_gui.py --real           # โมเดล Reachy Mini แท้ (official daemon)
    python scripts/chat_gui.py --no-gui         # sim (ไม่เปิดหน้าต่างหุ่น)
    python scripts/chat_gui.py --hardware       # หุ่นจริง (STS3215)
    python scripts/chat_gui.py --model qwen2.5:3b   # ใช้โมเดลอื่น
"""

import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import scrolledtext

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.robot_config import get_config  # noqa: E402
from src.expressions import (  # noqa: E402
    apply_emotion,
    detect_emotion,
    speak_with_motion,
    strip_emotion_tag,
)
from src.llm import OllamaClient  # noqa: E402
from src.robot import Robot  # noqa: E402


class ChatApp:
    def __init__(self, root: tk.Tk, robot: Robot, llm: OllamaClient):
        self.root = root
        self.robot = robot
        self.llm = llm
        self.history: list[dict] = []

        root.title("Reachy Mini DIY - LLM Chat")
        root.geometry("560x640")
        root.configure(bg="#1e1e1e")

        self.chat = scrolledtext.ScrolledText(
            root, wrap="word", state="disabled",
            font=("Consolas", 11), bg="#1e1e1e", fg="#e0e0e0",
            insertbackground="#e0e0e0",
        )
        self.chat.pack(fill="both", expand=True, padx=8, pady=8)

        bottom = tk.Frame(root, bg="#1e1e1e")
        bottom.pack(fill="x", padx=8, pady=(0, 8))
        self.entry = tk.Entry(bottom, font=("Consolas", 12))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda _e: self.send())
        tk.Button(bottom, text="ส่ง", command=self.send,
                  width=8).pack(side="right", padx=(6, 0))
        tk.Button(bottom, text="🎤 พูด", command=self.listen_click,
                  width=8).pack(side="right", padx=(6, 0))
        tk.Button(bottom, text="ล้าง", command=self.clear,
                  width=6).pack(side="right", padx=(6, 0))

        self._append("ระบบ", f"พร้อมแล้ว (โมเดล: {self.llm.model}) — พิมพ์คุยได้เลย!")

    # ---------- UI ----------
    def _append(self, who: str, text: str):
        self.chat.configure(state="normal")
        self.chat.insert("end", f"[{who}]\n{text}\n\n")
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def clear(self):
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self.history = []

    # ---------- พูด (STT) ----------
    def listen_click(self):
        """กด 🎤 -> ฟังเสียงพูด -> แปลงเป็นข้อความ -> ส่งอัตโนมัติ"""
        self._set_entry("🎤 กำลังฟัง... (พูดภาษาไทย)")
        threading.Thread(target=self._listen_worker, daemon=True).start()

    def _listen_worker(self):
        try:
            from config.robot_config import get_config
            from src.stt import listen

            cfg = get_config()["stt"]
            text = listen(
                duration=cfg["duration"],
                samplerate=cfg["samplerate"],
                language=cfg["language"],
                model=cfg["model"],
                device=cfg["device"],
                mic=cfg.get("mic"),
                stt_url=cfg.get("stt_url"),
                early_stop=cfg.get("early_stop", True),
                tail_silence=cfg.get("tail_silence", 0.6),
                speech_threshold=cfg.get("speech_threshold", 0.01),
            )
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, lambda: self._set_entry(
                f"(STT ผิดพลาด: {exc})"))
            return
        if not text:
            self.root.after(0, lambda: self._set_entry(
                "(ไม่ได้ยินเสียง — ลองอีกครั้ง)"))
            return
        self.root.after(0, lambda: self._set_entry(text))
        self.root.after(0, lambda: self.send())

    def _set_entry(self, text: str):
        self.entry.delete(0, "end")
        self.entry.insert(0, text)

    # ---------- ส่งข้อความ ----------
    def send(self):
        user_text = self.entry.get().strip()
        if not user_text:
            return
        self.entry.delete(0, "end")
        self._append("คุณ", user_text)
        self.history.append({"role": "user", "content": user_text})
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            reply = self.llm.chat(self.history)
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, self._append, "Reachy",
                            f"(เกิดข้อผิดพลาดเชื่อม LLM: {exc})")
            return

        emotion = detect_emotion(reply)
        clean = strip_emotion_tag(reply)
        self.history.append({"role": "assistant", "content": clean})
        self.root.after(0, self._append, "Reachy",
                        f"{clean}\n[อารมณ์: {emotion}]")

        # ขยับหุ่น + พูด (รอ UI อัปเดตสักครู่)
        self.root.after(100, self._react, emotion, clean)

    def _react(self, emotion: str, text: str):
        try:
            apply_emotion(self.robot, emotion)
            speak_with_motion(self.robot, text)
        except Exception as exc:  # noqa: BLE001
            print(f"[Chat] ขยับหุ่น/เสียงผิดพลาด: {exc}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="คุยกับ Reachy Mini ผ่าน LLM (Ollama)")
    parser.add_argument("--hardware", action="store_true", help="ใช้หุ่นจริง")
    parser.add_argument("--port", default=None)
    parser.add_argument("--no-gui", action="store_true", help="ไม่เปิดหน้าต่าง 3D หุ่น")
    parser.add_argument("--model", default=None, help="ชื่อโมเดล Ollama (default จาก config)")
    parser.add_argument("--real", action="store_true",
                        help="ใช้โมเดล Reachy Mini แท้ (official daemon แทนหุ่น DIY)")
    args = parser.parse_args()

    cfg = get_config()
    llm_cfg = cfg["llm"]
    model = args.model or llm_cfg["model"]

    # เช็ค Ollama — ⚠️ ต้องส่ง api_key ด้วย (proxy ตอบ 401 ถ้าไม่ใส่ key)
    if not OllamaClient(url=llm_cfg["url"], api_key=llm_cfg.get("api_key")).ping():
        print("⚠️ Ollama server ไม่พร้อม — รัน `ollama serve` ก่อน")
        sys.exit(1)
    client = OllamaClient(
        url=llm_cfg["url"], model=model,
        api_key=llm_cfg.get("api_key"),
        system_prompt=llm_cfg["system_prompt"],
        temperature=llm_cfg["temperature"],
        timeout=llm_cfg.get("timeout", 120.0),
        num_predict=llm_cfg.get("num_predict"),
        max_history=llm_cfg.get("max_history"),
        think=llm_cfg.get("think", False),
        keep_alive=llm_cfg.get("keep_alive", "30m"),
    )
    if model not in client.list_models():
        print(f"⚠️ ยังไม่มีโมเดล {model} — รัน: ollama pull {model}")
        sys.exit(1)

    backend = "hardware" if args.hardware else "sim"

    if args.real:
        from src.real_robot import RealRobot

        if not RealRobot.available():
            print("⚠️ official daemon ไม่พร้อม — รัน: "
                  "reachy_mini_env\\Scripts\\reachy-mini-daemon.exe --sim ก่อน")
            sys.exit(1)
        robot = RealRobot()
    else:
        robot = Robot(
            backend=backend, port=args.port,
            gui=("mujoco" if (not args.no_gui and backend == "sim") else False),
        )
    robot.wake_up()

    root = tk.Tk()
    ChatApp(root, robot, client)
    try:
        root.mainloop()
    finally:
        robot.close()


if __name__ == "__main__":
    main()
