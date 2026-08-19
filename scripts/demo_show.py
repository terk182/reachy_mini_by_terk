r"""โชว์อัตโนมัติ Reachy Mini — ใช้สอนเด็ก / ถ่าย YouTube เป็นตอน ๆ

หุ่นจะพูด + ขยับตามลำดับฉากที่กำหนดไว้ (scripted show) — กดรันครั้งเดียว
แล้วปล่อยให้มันโชว์เองทั้งชุด เหมาะกับ: เปิดงานนิทรรศการ, ถ่ายคลิป, สอนในห้อง

วิธีใช้:
    .venv\Scripts\python.exe scripts\demo_show.py --hardware              # โชว์ทั้งหมด
    .venv\Scripts\python.exe scripts\demo_show.py --hardware --scene intro  # ฉากเดียว
    .venv\Scripts\python.exe scripts\demo_show.py --hardware --list         # ดูรายชื่อฉาก
    .venv\Scripts\python.exe scripts\demo_show.py --sim --gui mujoco        # ดูใน sim

ฉาก (SCENES) เรียงตามนี้ — แก้ข้อความ/ท่าทางได้ที่ตัวแปร SCENES ด้านล่าง
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.expressions import speak_with_motion  # noqa: E402

# ---------------------------------------------------------------
# ฉากโชว์: id, (คำพูด...), [ท่าทาง...]
# ท่าทาง = ชื่อเมธอดใน Robot: wave/nod/bow/dance/happy/head_tilt/
#          look_around/shake_head/random_cute — และ "sing" (ร้องเพลง)
# ---------------------------------------------------------------
SCENES = [
    (
        "intro",
        (
            "สวัสดีครับทุกคน ผมชื่อน้องรีชชี่",
            "เป็นหุ่นยนต์เพื่อนเล่นของเด็ก ๆ ครับ ยินดีที่ได้เจอทุกคนนะครับ",
        ),
        ["wave"],
    ),
    (
        "parts",
        (
            "ผมมีหูเป็นไมโครโฟน เอาไว้ฟังเสียงทุกคน",
            "มีตาเป็นกล้อง เอาไว้มองเห็น",
            "มีสมองเป็นคอมพิวเตอร์ และมีกล้ามเนื้อเป็นมอเตอร์ครับ",
        ),
        ["head_tilt", "look_around"],
    ),
    (
        "move",
        (
            "ดูสิครับ ผมขยับหัวได้แบบนี้",
            "แล้วก็โค้งคำนับให้ทุกคนด้วยนะครับ",
        ),
        ["nod", "bow"],
    ),
    (
        "sing",
        ("ผมร้องเพลงได้นะครับ ตั้งใจฟังให้ดีนะครับ",),
        ["sing"],
    ),
    (
        "dance",
        ("และผมก็เต้นได้ด้วยนะครับ ดูสิครับ",),
        ["dance"],
    ),
    (
        "story",
        (
            "ผมเล่านิทานได้ด้วยนะครับ",
            "กาลครั้งหนึ่ง มีหุ่นยนต์ตัวน้อยที่อยากเป็นเพื่อนกับเด็ก ๆ ทุกคนครับ",
        ),
        ["happy"],
    ),
    (
        "goodbye",
        ("ขอบคุณทุกคนที่ฟังจนจบนะครับ แล้วเจอกันใหม่ครับ บ๊ายบาย",),
        ["wave", "bow"],
    ),
]


def build_robot(args):
    """สร้าง robot ตาม flag: --real / --hardware / sim"""
    if args.real:
        from src.real_robot import RealRobot

        if not RealRobot.available():
            raise SystemExit(
                "⚠️ daemon ไม่พร้อม — รัน official daemon ก่อน เช่น "
                "reachy_mini_env\\Scripts\\reachy-mini-daemon.exe --sim")
        print("[demo_show] ใช้ official daemon (Reachy Mini แท้)")
        return RealRobot()

    from src.robot import Robot

    backend = "hardware" if args.hardware else "sim"
    gui = args.gui if not args.hardware else False
    print(f"[demo_show] backend={backend} gui={gui}")
    return Robot(backend=backend, port=args.port, gui=gui)


def _act(robot, name: str) -> None:
    """ทำท่าทางตามชื่อ — 'sing' เรียก src.song.sing ที่เหลือเรียกเมธอด robot"""
    if name == "sing":
        from src.song import sing

        sing(robot, melody=args_sing_melody)
        return
    fn = getattr(robot, name, None)
    if fn is None:
        print(f"[demo_show] ⚠️ ไม่มีท่าทาง {name}")
        return
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 — โชว์ต้องไม่ตายกลางคัน
        print(f"[demo_show] ⚠️ ท่า {name} ผิดพลาด: {exc}")


args_sing_melody = "twinkle"


def run_scene(robot, scene) -> None:
    """เล่น 1 ฉาก: พูดทีละบรรทัด + ทำท่าทาง"""
    _, lines, actions = scene
    for action in actions:
        _act(robot, action)
        time.sleep(0.3)
    for line in lines:
        print(f"[demo_show] 🗣️ {line}")
        speak_with_motion(robot, line)
        time.sleep(0.4)
    time.sleep(args_scene_gap)


args_scene_gap = 1.0


def main() -> None:
    global args_sing_melody, args_scene_gap

    parser = argparse.ArgumentParser(description="Reachy Mini auto show")
    parser.add_argument("--hardware", action="store_true", help="ใช้หุ่น STS3215 จริง")
    parser.add_argument("--real", action="store_true", help="ใช้ official daemon")
    parser.add_argument("--port", default=None)
    parser.add_argument("--gui", default=False, help="sim: mujoco/matplotlib/False")
    parser.add_argument("--scene", default=None, help="เล่นเฉพาะฉาก (id)")
    parser.add_argument("--list", action="store_true", help="แสดงรายชื่อฉากแล้วออก")
    parser.add_argument("--melody", default="twinkle", help="เพลง: twinkle/happy_birthday")
    parser.add_argument("--gap", type=float, default=1.0, help="วินาทีเว้นระหว่างฉาก")
    args = parser.parse_args()

    if args.list:
        for sid, lines, actions in SCENES:
            print(f"  {sid:10s} พูด {len(lines)} ประโยค | ท่าทาง: {', '.join(actions)}")
        return

    args_sing_melody = args.melody
    args_scene_gap = args.gap

    robot = build_robot(args)
    robot.wake_up()

    scenes = [s for s in SCENES if args.scene is None or s[0] == args.scene]
    if args.scene and not scenes:
        print(f"⚠️ ไม่มีฉากชื่อ {args.scene} — ใช้ --list ดูรายชื่อ")
        robot.close()
        sys.exit(1)

    print(f"[demo_show] เริ่มโชว์ {len(scenes)} ฉาก...")
    try:
        for scene in scenes:
            print(f"[demo_show] ▶ ฉาก {scene[0]}")
            run_scene(robot, scene)
        print("[demo_show] ✅ จบโชว์")
    except KeyboardInterrupt:
        print("\n[demo_show] หยุด (Ctrl+C)")
    finally:
        robot.close()


if __name__ == "__main__":
    main()
