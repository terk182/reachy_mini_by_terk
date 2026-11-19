# -*- coding: utf-8 -*-
"""หุ่น 2 ตัวเต้นตามจังหวะเพลงจริง (เปิด YouTube ใน browser + ฟังเสียงจากลำโพง)

    # เปิดลิงก์ YouTube แล้วเต้นพร้อมกัน (หุ่นจริง COM4 + COM3)
    .venv\\Scripts\\python.exe scripts\\two_robots_music_dance.py https://youtu.be/xxxx

    # เลือกโหมด: together / alternate / canon / mirror / free / show
    .venv\\Scripts\\python.exe scripts\\two_robots_music_dance.py "ชื่อเพลง" --mode show

    # ลองใน MuJoCo (ไม่ต้องมีหุ่น)
    .venv\\Scripts\\python.exe scripts\\two_robots_music_dance.py https://youtu.be/xxxx --backend sim

    # ไม่เปิด browser — เต้นตามเสียงอะไรก็ได้ที่กำลังเล่นอยู่ในเครื่อง
    .venv\\Scripts\\python.exe scripts\\two_robots_music_dance.py --mode mirror

    # ตื่นเต้นจัดเต็ม / อินเนอร์ซึ้ง ๆ
    .venv\\Scripts\\python.exe scripts\\two_robots_music_dance.py https://youtu.be/xxxx --style hype

ระหว่างเต้น พิมพ์ชื่อโหมด (หรือ auto/hype/inner) แล้ว Enter เพื่อเปลี่ยน · พิมพ์ q (หรือ Ctrl+C) เพื่อหยุด
"""

import argparse
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import dance_sync, music  # noqa: E402
from src.beat import BeatTracker  # noqa: E402
from src.robot import Robot  # noqa: E402


def open_sim(which: str, gui: bool):
    from config.robot_config import get_config

    cfg = get_config()
    name_a = (cfg.get("robot") or {}).get("name", "พี่ทด")
    name_b = (cfg.get("robot_b") or {}).get("name", "น้องนุ")
    view_a = view_b = None
    if gui and which == "both":
        from src.mujoco_sim import create_pair_viewers

        view_a, view_b = create_pair_viewers(cfg)
    robots = []
    if which in ("a", "both"):
        robots.append((name_a, Robot(backend="sim", viewer=view_a,
                                     gui="mujoco" if gui and which == "a" else False)))
    if which in ("b", "both"):
        robots.append((name_b, Robot(backend="sim", viewer=view_b,
                                     gui="mujoco" if gui and which == "b" else False)))
    return robots


def main():
    ap = argparse.ArgumentParser(description="หุ่น 2 ตัวเต้นตามเพลง YouTube")
    ap.add_argument("query", nargs="?", default="",
                    help="ลิงก์ YouTube / video id / ชื่อเพลง (ว่าง = ไม่เปิด browser)")
    ap.add_argument("--mode", default="together",
                    help="together | alternate | canon | mirror | free | show")
    ap.add_argument("--style", default="auto",
                    help="auto (ตามความดังเพลง) | hype (ตื่นเต้นตลอด) | inner (อินเนอร์)")
    ap.add_argument("--amount", type=float, default=1.2,
                    help="ขนาดท่า (1.0 ปกติ · 1.2 default · 1.5 จัดเต็ม — ถูก clamp ตาม limits)")
    ap.add_argument("--backend", choices=["hardware", "sim"], default="hardware")
    ap.add_argument("--one", choices=["a", "b", "both"], default="both")
    ap.add_argument("--no-gui", action="store_true", help="sim แบบไม่เปิดหน้าต่าง")
    ap.add_argument("--bpm", type=float, default=120.0,
                    help="จังหวะเริ่มต้น/จังหวะคงที่ถ้าฟังเสียงไม่ได้")
    ap.add_argument("--no-listen", action="store_true",
                    help="ไม่ฟังเสียงลำโพง — เต้นที่ --bpm คงที่")
    ap.add_argument("--duration", type=float, default=None, help="เต้นกี่วินาที (ว่าง = จนกว่าจะหยุด)")
    ap.add_argument("--speed", type=int, default=None, help="ความเร็ว servo (hardware)")
    ap.add_argument("--acc", type=int, default=20, help="อัตราเร่ง 0-254")
    ap.add_argument("--lead", type=float, default=0.12,
                    help="ส่งท่าล่วงหน้า (วินาที) ชดเชยหน่วง — หุ่นช้ากว่าเพลงให้เพิ่ม")
    args = ap.parse_args()

    if args.backend == "hardware":
        from test_two_robots_poses import open_robots

        robots = open_robots(args.one)
    else:
        robots = open_sim(args.one, gui=not args.no_gui)
    if not robots:
        sys.exit("ไม่มีหุ่น")
    names = [n for n, _ in robots]

    if args.query:
        ok, msg = music.open_youtube(args.query)
        print(("🎵 " if ok else "⚠️ ") + msg)

    tracker = BeatTracker(default_bpm=args.bpm, use_loopback=not args.no_listen)
    done = threading.Event()
    ctl = dance_sync.start_dance(
        [r for _, r in robots], mode=args.mode, tracker=tracker, names=names,
        lead_s=args.lead, style=args.style, amount=args.amount, max_duration=args.duration, speed=args.speed, acc=args.acc,
        on_stop=lambda reason: done.set(),
    )

    def read_stdin():
        for line in sys.stdin:
            cmd = line.strip()
            if not cmd:
                continue
            if cmd.lower() in ("q", "quit", "exit", "stop"):
                dance_sync.stop_dance()
                return
            if cmd.lower() in dance_sync.STYLES:
                dance_sync.set_style(cmd)
            else:
                dance_sync.set_mode(cmd)

    threading.Thread(target=read_stdin, daemon=True).start()
    print(f"💃 {' + '.join(names)} เต้นแบบ {ctl.mode} / {ctl.style} — พิมพ์ชื่อโหมดหรือ auto/hype/inner เพื่อเปลี่ยน, q = หยุด")
    try:
        last = 0.0
        while not done.is_set():
            time.sleep(0.2)
            if time.time() - last >= 3.0:
                last = time.time()
                st = ctl.status()
                hear = ("🔊" if st["audible"] else "🔈") if st["listening"] else "⏱️"
                print(f"   {hear} {st['bpm']:.0f} BPM · มั่นใจ {st['confidence']:.2f} "
                      f"· โหมด {st['mode']} · {st['style']}/{st['level']} "
                      f"(พลัง {st['energy']:.2f})")
    except KeyboardInterrupt:
        pass
    finally:
        dance_sync.stop_dance()
        if args.query:
            music.pause_youtube()
        tracker.stop()
        for _n, r in robots:
            r.close()
    print(f"จบ — {ctl.stop_reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
