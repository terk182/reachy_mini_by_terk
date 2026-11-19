# -*- coding: utf-8 -*-
"""พูดปรึกษากัน **พร้อมท่าทาง** (พี่ทด + น้องนุ)

    # ข้อความตัวอย่าง + ขยับหุ่นจริง
    .venv\\Scripts\\python.exe scripts\\two_robots_voice_test.py

    # ให้ LLM คิดจริง
    .venv\\Scripts\\python.exe scripts\\two_robots_voice_test.py --live "ทำไมท้องฟ้าเป็นสีฟ้า"

    # เสียงอย่างเดียว ไม่ต่อหุ่น
    .venv\\Scripts\\python.exe scripts\\two_robots_voice_test.py --no-robot

ลำดับ: หันเข้าหากัน -> พี่ทดพูด (พยักหน้า/ส่ายหัว) น้องนุฟัง (เอียงหัïว) ->
       น้องนุพูด -> กลับมาด้านหน้า
"""

import argparse
import math
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.robot_config import get_config  # noqa: E402
from src.tts import speak  # noqa: E402

DEFAULT_A = "พี่ว่านะ อาหารเช้าที่ทำง่ายสุดคือข้าวต้มกับไข่ต้ม ใช้เวลาไม่ถึงสิบนาที"
DEFAULT_B = "น้องนุเสริมว่า เพิ่มผลไม้สักหน่อยจะอิ่มนานขึ้น และได้วิตามินด้วยนะ"
BASE_CENTER = 2048
CPD = 4096.0 / 360.0


# ---------------------------------------------------------------- ท่าทาง
# แต่ละท่าอยู่ในหน้าต่างเวลา WINDOW วิ และใช้ envelope sin(pi*u) → เริ่ม/จบที่กลางเสมอ
# คืน (dz_mm, d_roll_deg, d_pitch_deg, d_yaw_deg)
WINDOW = 1.7


def _nod(u, env, amp=14.0, freq=1.8):
    """พยักหน้าเป็นจังหวะ"""
    return 0.0, 0.0, -amp * env * math.sin(2 * math.pi * freq * u), 0.0


def _tilt(u, env, amp=18.0):
    """เอียงหัวค้าง (น่ารัก)"""
    return 0.0, amp * env, 4.0 * env, 0.0


def _bounce(u, env, amp=5.0):
    """เด้งขึ้น-ลง"""
    return amp * env * abs(math.sin(2 * math.pi * 1.6 * u)), 3.0 * env, 3.0 * env, 0.0


def _lookup(u, env):
    """เงยขึ้นเหมือนกำลังคิด"""
    return 4.0 * env, -6.0 * env, 12.0 * env, 2.0 * env


def _wiggle(u, env):
    """ส่ายหัวซ้าย-ขวาเร็ว"""
    return 0.0, 8.0 * env, 4.0 * env, 9.0 * env * math.sin(2 * math.pi * 2.0 * u)


def _lean(u, env):
    """เอียงตัวข้าง + พยักเบา"""
    return 2.0 * env, -16.0 * env, -6.0 * env, -4.0 * env


def _giggle(u, env):
    """ขำคิก ๆ — สั่นเร็วเบา ๆ + เด้ง"""
    s = math.sin(2 * math.pi * 3.0 * u)
    return 2.5 * env * abs(s), 5.0 * env * s, 5.0 * env * s, 0.0


def _circle(u, env):
    """กลิ้งหัวเป็นวงกลมช้า ๆ (น่ารักมาก)"""
    a = 2 * math.pi * 0.8 * u
    return 1.5 * env * math.cos(a), 12.0 * env * math.cos(a), 10.0 * env * math.sin(a), 0.0


def _peek(u, env):
    """ก้มมองแล้วเงยขึ้น (ขี้อาย/เล่นซน)"""
    s = math.sin(2 * math.pi * 0.6 * u)
    return 1.0 * env * abs(s), 6.0 * env, -11.0 * env * s, 0.0


def _shy(u, env):
    """เอียงหัว + ย่อตัวลง (ขี้อาย)"""
    return -4.0 * env, 16.0 * env, -7.0 * env, -6.0 * env


def _excited(u, env):
    """ตื่นเต้น — เด้งถี่ + พยักแรง + เอียงสลับ"""
    s = math.sin(2 * math.pi * 1.4 * u)
    return (4.0 * env * abs(math.sin(2 * math.pi * 2.6 * u)),
            14.0 * env * s, 8.0 * env * s, 4.0 * env)


def _double_tilt(u, env):
    """เอียงซ้าย-ขวาเร็ว ๆ สองจังหวะ (ทำหน้าหมั่นไส้)"""
    return 0.0, 15.0 * env * math.sin(2 * math.pi * 1.2 * u), 3.0 * env, 0.0


SPEAK_GESTURES = [
    _nod, _tilt, _bounce, _wiggle, _lookup, _giggle, _circle,
    _excited, _lean, _nod, _double_tilt, _peek, _bounce, _shy,
]
LISTEN_GESTURES = [
    lambda u, env: (0.0, 13.0 * env, 5.0 * env, 0.0),                       # เอียงฟัง
    lambda u, env: (0.0, 0.0, -8.0 * env * abs(math.sin(math.pi * 1.4 * u)), 0.0),  # พยักรับ
    lambda u, env: (4.0 * env, -9.0 * env, 8.0 * env, 0.0),                 # เงยสนใจ
    lambda u, env: (0.0, -11.0 * env, 3.0 * env, 4.0 * env),                # เอียงอีกข้าง
    lambda u, env: (1.5 * env, 7.0 * env * math.sin(2 * math.pi * 0.9 * u),
                    4.0 * env, 0.0),                                        # ส่ายเบา ๆ
]


class Mover(threading.Thread):
    """ขยับหัวแบบ "มีท่าทาง" ระหว่างพูด (speak) หรือฟัง (listen)

    ความสมูธ:
      - สั่งที่ 20 Hz (dt=0.05) — เดิม 8 Hz ทำให้ sine 6 Hz ถูก sample ไม่พอ = กระตุก
      - แต่ละท่าอยู่ในหน้าต่าง WINDOW วิ ใช้ envelope sin(pi*u) → เริ่ม/จบที่กลาง
      - ใส่ acc>0 ให้ servo ค่อย ๆ เร่ง/ผ่อน + deadband กันสั่งซ้ำถี่เกิน
    """

    def __init__(self, robot, mode="speak", speed=700, z_home=70.0,
                 dt=0.05, acc=30, window=WINDOW):
        super().__init__(daemon=True)
        self.r = robot
        self.mode = mode
        self.speed = speed
        self.z_home = z_home
        self.dt = dt
        self.acc = acc
        self.window = window
        self._stop = threading.Event()
        self._last = None

    def _send(self, z, roll_deg, pitch_deg, yaw_deg=0.0):
        """ส่งคำสั่งแบบมี deadband + acc (นุ่ม)"""
        if self._last is not None:
            dz, dr, dp = (abs(z - self._last[0]), abs(roll_deg - self._last[1]),
                          abs(pitch_deg - self._last[2]))
            if dz < 0.15 and dr < 0.3 and dp < 0.3:
                return
        self._last = (z, roll_deg, pitch_deg)
        self.r.head.set_pose(z, math.radians(roll_deg), math.radians(pitch_deg),
                             math.radians(yaw_deg), speed=self.speed, acc=self.acc)

    def run(self):
        t = 0.0
        gestures = SPEAK_GESTURES if self.mode == "speak" else LISTEN_GESTURES
        while not self._stop.is_set():
            u = (t % self.window) / self.window
            idx = int(t // self.window) % len(gestures)
            env = math.sin(math.pi * u)          # 0 → 1 → 0 (นุ่ม)
            dz, droll, dpitch, dyaw = gestures[idx](u, env)
            try:
                self._send(self.z_home + dz, droll, dpitch, dyaw)
            except Exception:  # noqa: BLE001 — หุ่นหลุดไม่ให้ล้มทั้งสคริปต์
                break
            t += self.dt
            time.sleep(self.dt)

    def stop(self):
        self._stop.set()
        self.join(timeout=1.5)


def _face_each_other(robots, turn, speed):
    """หันเข้าหากัน: A +turn (ขวา) · B −turn (ซ้าย)"""
    for (name, r), deg in zip(robots, (+turn, -turn)):
        sid = r.config["servo_ids"]["base"]
        cur = r._bus.get_position(sid) or BASE_CENTER
        ratio = float((r.config.get("base") or {}).get("gear_ratio", 1.0) or 1.0)
        tgt = int(round(cur + (deg / ratio) * CPD)) % 4096
        r._bus.set_position(sid, tgt, speed=speed)
        print(f"   {name}: หัน {'ขวา' if deg > 0 else 'ซ้าย'} {abs(deg):.0f}°")
    time.sleep(1.5)


def _face_front(robots, speed):
    """กลับมาด้านหน้าสัมบูรณ์ (2048 = 0°)"""
    for _name, r in robots:
        r._bus.set_position(r.config["servo_ids"]["base"], BASE_CENTER, speed=speed)
        r.head.set_pose(r.config["stewart"]["z_home"], 0.0, 0.0, 0.0, speed=speed)
    time.sleep(1.8)
    print("   กลับมาด้านหน้า (0°)")


def _live_consult(question: str):
    from src.dual_llm import TwoRobotConsultant
    from src.expressions import detect_emotion, strip_emotion_tag
    from src.llm import OllamaClient

    cfg = get_config()
    bcfg = cfg.get("robot_b", {})
    bllm = bcfg.get("llm", {})

    def client(model, prompt, temp, npred):
        return OllamaClient(
            url=cfg["llm"]["url"], model=model, api_key=cfg["llm"].get("api_key"),
            system_prompt=prompt, temperature=temp,
            timeout=cfg["llm"].get("timeout", 25.0), num_predict=npred,
            max_history=cfg["llm"].get("max_history"), think=cfg["llm"].get("think", False),
            keep_alive=cfg["llm"].get("keep_alive", "m"),
        )

    llm_a = client(cfg["llm"]["model"], cfg["llm"].get("system_prompt"),
                   cfg["llm"].get("temperature", 0.7), cfg["llm"].get("num_predict"))
    llm_b = client(bllm.get("model") or cfg["llm"]["model"], bcfg.get("system_prompt"),
                   bllm.get("temperature", 0.6), bllm.get("num_predict", 160))
    t0 = time.time()
    res = TwoRobotConsultant(
        llm_a, llm_b,
        name_a=(cfg.get("robot") or {}).get("name", "พี่ทด"),
        name_b=bcfg.get("name", "น้องนุ"),
    ).consult(question)
    print(f"(LLM ใช้เวลา {time.time() - t0:.1f}s)")
    return (strip_emotion_tag(res.a_draft).strip(),
            strip_emotion_tag(res.b_note).strip(),
            detect_emotion(res.a_draft), detect_emotion(res.b_note))


def main():
    ap = argparse.ArgumentParser(description="พูดปรึกษากันพร้อมท่าทาง")
    ap.add_argument("question", nargs="?", default="แนะนำเมนูอาหารเช้าที่ทำง่าย ๆ หน่อย")
    ap.add_argument("--live", action="store_true", help="ให้ LLM คิดจริง")
    ap.add_argument("--text-a", default=None)
    ap.add_argument("--text-b", default=None)
    ap.add_argument("--no-robot", action="store_true", help="เสียงอย่างเดียว ไม่ขยับหุ่น")
    ap.add_argument("--turn", type=float, default=25.0, help="องศาที่หันเข้าหากัน")
    ap.add_argument("--speed", type=int, default=700, help="ความเร็ว servo (ต่ำ = นุ่ม/ช้า)")
    ap.add_argument("--acc", type=int, default=30,
                    help="อัตราเร่ง 0-254 (0 = กระชาก, 30-60 = นุ่ม)")
    ap.add_argument("--dt", type=float, default=0.05,
                    help="รอบส่งคำสั่ง (วินาที) — 0.05 = 20 Hz")
    ap.add_argument("--window", type=float, default=WINDOW,
                    help="เวลาเปลี่ยนท่าทีละท่า (วินาที) — น้ำหน่อย = เปลี่ยนท่าถี่ขึ้น")
    args = ap.parse_args()

    cfg = get_config()
    name_a = (cfg.get("robot") or {}).get("name", "พี่ทด")
    voice_a = (cfg.get("robot") or {}).get("voice", "male")
    bcfg = cfg.get("robot_b", {})
    name_b = bcfg.get("name", "น้องนุ")
    voice_b = bcfg.get("voice", "female")

    if args.live:
        print(f"❓ {args.question}")
        text_a, text_b, emo_a, emo_b = _live_consult(args.question)
    else:
        text_a = args.text_a or DEFAULT_A
        text_b = args.text_b or DEFAULT_B
        emo_a, emo_b = "neutral", "happy"

    robots = []
    if not args.no_robot:
        try:
            from test_two_robots_poses import open_robots
            robots = open_robots("both")
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ เปิดหุ่นไม่ได้ ({exc}) — เล่นเสียงอย่างเดียว")

    try:
        if robots:
            print("🎬 หันเข้าหากัน")
            _face_each_other(robots, args.turn, args.speed)

        print(f"\n🐰 {name_a} [{voice_a}/{emo_a}]\n   {text_a}")
        mv_a = Mover(robots[0][1], "speak", args.speed, acc=args.acc, dt=args.dt,
                     window=args.window) if robots else None
        mv_b = Mover(robots[1][1], "listen", args.speed, acc=args.acc, dt=args.dt,
                     window=args.window) if len(robots) > 1 else None
        for m in (mv_a, mv_b):
            if m:
                m.start()
        speak(text_a, voice=voice_a)
        for m in (mv_a, mv_b):
            if m:
                m.stop()
        time.sleep(0.4)

        print(f"\n🤖 {name_b} [{voice_b}/{emo_b}]\n   {text_b}")
        mv_a = Mover(robots[0][1], "listen", args.speed, acc=args.acc, dt=args.dt,
                     window=args.window) if robots else None
        mv_b = Mover(robots[1][1], "speak", args.speed, acc=args.acc, dt=args.dt,
                     window=args.window) if len(robots) > 1 else None
        for m in (mv_a, mv_b):
            if m:
                m.start()
        speak(text_b, voice=voice_b)
        for m in (mv_a, mv_b):
            if m:
                m.stop()

        if robots:
            print("\n🎬 กลับมาด้านหน้า")
            _face_front(robots, args.speed)

        print("\n✅ เสร็จ")
    finally:
        for _n, r in robots:
            r.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
