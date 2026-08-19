r"""เกมท่องศัพท์ภาษาอังกฤษ — หุ่นสอนคำศัพท์ แล้วให้เด็กพูดตาม

รัน:
    .venv\Scripts\python.exe scripts\game_vocab.py --hardware
    .venv\Scripts\python.exe scripts\game_vocab.py --hardware --set colors
    .venv\Scripts\python.exe scripts\game_vocab.py --hardware --list

ชุดคำศัพท์: colors / animals / numbers / school
หุ่นจะพูด "สีแดง ภาษาอังกฤษคือ Red นะครับ หนูลองพูดตามว่า Red" แล้วชม
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.robot_config import get_config  # noqa: E402
from src.expressions import speak_with_motion  # noqa: E402
from src.stt import listen, resolve_mic  # noqa: E402

VOCAB = {
    "colors": [
        ("สีแดง", "Red"), ("สีเหลือง", "Yellow"), ("สีฟ้า", "Blue"),
        ("สีเขียว", "Green"), ("สีขาว", "White"), ("สีดำ", "Black"),
    ],
    "animals": [
        ("แมว", "Cat"), ("หมา", "Dog"), ("ช้าง", "Elephant"),
        ("นก", "Bird"), ("ปลา", "Fish"), ("กระต่าย", "Rabbit"),
    ],
    "numbers": [
        ("หนึ่ง", "One"), ("สอง", "Two"), ("สาม", "Three"),
        ("สี่", "Four"), ("ห้า", "Five"), ("หก", "Six"),
        ("เจ็ด", "Seven"), ("แปด", "Eight"), ("เก้า", "Nine"), ("สิบ", "Ten"),
    ],
    "school": [
        ("หนังสือ", "Book"), ("ดินสอ", "Pencil"), ("ปากกา", "Pen"),
        ("โต๊ะ", "Table"), ("เก้าอี้", "Chair"), ("ครู", "Teacher"),
    ],
}


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
    parser = argparse.ArgumentParser(description="เกมท่องศัพท์กับ Reachy Mini")
    parser.add_argument("--hardware", action="store_true")
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--port", default=None)
    parser.add_argument("--gui", default=False)
    parser.add_argument("--mic", default=None, help="ไมค์: auto/index/ชื่อ")
    parser.add_argument("--set", default="colors", choices=list(VOCAB))
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        for name, words in VOCAB.items():
            print(f"  {name:8s} ({len(words)} คำ): {', '.join(w[0] for w in words)}")
        return

    cfg = get_config()
    stt = cfg["stt"]
    mic = resolve_mic(args.mic or stt.get("mic"))

    robot = build_robot(args)
    robot.wake_up()

    words = VOCAB[args.set]
    speak_with_motion(robot, f"มาเรียนคำศัพท์ภาษาอังกฤษชุด {args.set} กันนะครับ หนูพูดตามผมได้เลยครับ")

    try:
        for thai, eng in words:
            robot.nod(1)
            speak_with_motion(robot, f"{thai} ภาษาอังกฤษคือ {eng} นะครับ")
            time.sleep(0.3)
            speak_with_motion(robot, f"ลองพูดตามว่า {eng}")
            time.sleep(1.2)  # เว้นให้เด็กพูดตาม
            robot.happy()
            speak_with_motion(robot, "ดีมากครับ เก่งจังเลย")

        robot.dance()
        speak_with_motion(robot, "เยี่ยมมากครับ วันนี้หนูได้เรียนรู้คำศัพท์ใหม่ ๆ หลายคำเลยครับ")
    except KeyboardInterrupt:
        print("\n[game_vocab] หยุด (Ctrl+C)")
    finally:
        robot.close()


if __name__ == "__main__":
    main()
