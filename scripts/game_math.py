r"""เกมทายเลข — หุ่นถามโจทย์บวก/ลบ แล้วฟังคำตอบจากเด็ก

รัน:
    .venv\Scripts\python.exe scripts\game_math.py --hardware
    .venv\Scripts\python.exe scripts\game_math.py --sim --gui mujoco
    .venv\Scripts\python.exe scripts\game_math.py --hardware --rounds 10 --max 20

หุ่นจะ:
  1. พูดโจทย์ เช่น "7 บวก 5 เท่ากับเท่าไหร่ครับ"
  2. ฟังคำตอบ (รองรับทั้งเลขไทยและตัวเลขอาหรับ 0-20)
  3. ตอบถูก → ดีใจ + ชม ; ผิด → เฉลย + ให้กำลังใจ
"""

from __future__ import annotations

import argparse
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.robot_config import get_config  # noqa: E402
from src.expressions import speak_with_motion  # noqa: E402
from src.stt import listen, resolve_mic  # noqa: E402

# --- แปลงคำตอบ: เลขไทย + ตัวเลขอาหรับ (0-20) ---
_NUM_MAP = {
    "ศูนย์": 0, "หนึ่ง": 1, "เอ็ด": 1, "สอง": 2, "สาม": 3, "สี่": 4,
    "ห้า": 5, "หก": 6, "เจ็ด": 7, "แปด": 8, "เก้า": 9, "สิบ": 10,
    "สิบเอ็ด": 11, "สิบสอง": 12, "สิบสาม": 13, "สิบสี่": 14,
    "สิบห้า": 15, "สิบหก": 16, "สิบเจ็ด": 17, "สิบแปด": 18,
    "สิบเก้า": 19, "ยี่สิบ": 20,
}


def parse_answer(text: str):
    """หาตัวเลขจากคำตอบ (อาหรับก่อน แล้วไทย) — คืน None ถ้าไม่เจอ"""
    if not text:
        return None
    m = re.search(r"\d+", text)
    if m:
        return int(m.group())
    t = text.replace(" ", "")
    for word, num in sorted(_NUM_MAP.items(), key=lambda kv: -len(kv[0])):
        if word in t:
            return num
    return None


def build_robot(args):
    if args.real:
        from src.real_robot import RealRobot

        if not RealRobot.available():
            raise SystemExit("⚠️ daemon ไม่พร้อม — รัน official daemon ก่อน")
        return RealRobot()

    from src.robot import Robot

    backend = "hardware" if args.hardware else "sim"
    gui = args.gui if not args.hardware else False
    return Robot(backend=backend, port=args.port, gui=gui)


def main() -> None:
    parser = argparse.ArgumentParser(description="เกมทายเลขกับ Reachy Mini")
    parser.add_argument("--hardware", action="store_true")
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--port", default=None)
    parser.add_argument("--gui", default=False)
    parser.add_argument("--mic", default=None, help="ไมค์: auto/index/ชื่อ")
    parser.add_argument("--rounds", type=int, default=5, help="จำนวนข้อ")
    parser.add_argument("--max", type=int, default=20, help="ผลลัพธ์สูงสุด")
    args = parser.parse_args()

    cfg = get_config()
    stt = cfg["stt"]
    mic = resolve_mic(args.mic or stt.get("mic"))

    robot = build_robot(args)
    robot.wake_up()

    speak_with_motion(robot, "มาเล่นเกมทายเลขกันนะครับ ผมจะถามโจทย์ หนูตอบเป็นตัวเลขได้เลยครับ")
    score = 0

    try:
        for i in range(1, args.rounds + 1):
            op = random.choice(("+", "-"))
            a = random.randint(1, args.max // 2)
            b = random.randint(1, args.max // 2)
            if op == "-" and a < b:
                a, b = b, a
            correct = a + b if op == "+" else a - b

            speak_with_motion(robot, f"ข้อที่ {i} ครับ {a} {'บวก' if op == '+' else 'ลบ'} {b} เท่ากับเท่าไหร่ครับ")

            ans = None
            for _ in range(2):  # ฟังซ้ำได้ 1 รอบถ้าไม่ได้ยิน
                text = listen(
                    duration=5.0, mic=mic, stt_url=stt.get("stt_url"),
                    samplerate=stt["samplerate"], model=stt["model"],
                    device=stt["device"], language=stt["language"],
                    early_stop=stt.get("early_stop", True),
                    tail_silence=stt.get("tail_silence", 0.8),
                    speech_threshold=stt.get("speech_threshold", 0.01),
                )
                print(f"[game_math] ได้ยิน: {text!r}")
                ans = parse_answer(text)
                if ans is not None:
                    break
                speak_with_motion(robot, "ไม่ได้ยินเลยครับ พูดเป็นตัวเลขอีกครั้งได้ไหมครับ")

            if ans == correct:
                score += 1
                robot.happy()
                speak_with_motion(robot, "ถูกต้องครับ เก่งมากเลย")
            else:
                robot.head_tilt()
                speak_with_motion(robot, f"ยังไม่ใช่ครับ คำตอบคือ {correct} นะครับ ไม่เป็นไรสู้ ๆ")

            time.sleep(0.5)

        robot.dance()
        speak_with_motion(robot, f"จบเกมแล้วครับ หนูตอบถูก {score} จาก {args.rounds} ข้อ เก่งมากเลยครับ")
    except KeyboardInterrupt:
        print("\n[game_math] หยุด (Ctrl+C)")
    finally:
        robot.close()


if __name__ == "__main__":
    main()
