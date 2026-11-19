# -*- coding: utf-8 -*-
"""เต้นตามจังหวะเพลงจริง — หุ่นเดี่ยวหรือหลายตัว หลายโหมด

ท่าทุกท่าเป็นฟังก์ชันของ "เลขจังหวะ" b (float, จาก BeatTracker) → ลงจังหวะตรงเพลงเสมอ
1 ห้อง (bar) = 4 จังหวะ · เปลี่ยนท่าทุกห้อง (crossfade ครึ่งจังหวะ ไม่กระตุก)

โหมด (MODES)
    together   เต้นพร้อมกัน ท่าเดียวกัน
    alternate  ผลัดกันเต้น ทีละ 2 ห้อง (อีกตัวโยกเบา ๆ รอ)
    canon      ท่าเดียวกันแต่ตัวที่ 2 ช้ากว่า 1 จังหวะ (เหลื่อมจังหวะ)
    mirror     กระจกเงา — ซ้าย/ขวากลับด้าน (หันหน้าเข้าหากันดูเหมือนส่องกระจก)
    free       ต่างคนต่างเต้น สุ่มท่าเองแต่ลงจังหวะเดียวกัน
    show       โชว์วนทุกโหมด โหมดละ 4 ห้อง

ใช้งาน
    from src import dance_sync
    dance_sync.start_dance([robot_a, robot_b], mode="mirror")
    dance_sync.set_mode("canon")
    dance_sync.stop_dance()
"""

from __future__ import annotations

import math
import random
import threading
import time

from .beat import BeatTracker

MODES = ("together", "alternate", "canon", "mirror", "free", "show")
MODE_TH = {
    "together": "เต้นพร้อมกัน", "alternate": "ผลัดกันเต้น", "canon": "เหลื่อมจังหวะ",
    "mirror": "กระจกเงา", "free": "ต่างคนต่างเต้น", "show": "โชว์ทุกแบบ",
}
# คำไทย/อังกฤษที่ LLM อาจส่งมา → โหมด
_MODE_ALIASES = {      # ⚠️ ลำดับสำคัญ — คำที่ยาว/ปฏิเสธต้องมาก่อน ("ไม่พร้อม" ก่อน "พร้อม")
    "ไม่พร้อม": "free", "ต่างคน": "free", "คนละ": "free", "อิสระ": "free",
    "พร้อม": "together", "sync": "together", "same": "together",
    "ผลัด": "alternate", "สลับ": "alternate", "turn": "alternate",
    "เหลื่อม": "canon", "ตาม": "canon", "delay": "canon", "offset": "canon",
    "กระจก": "mirror", "สะท้อน": "mirror",
    "random": "free", "independent": "free",
    "โชว์": "show", "ทุกแบบ": "show", "mix": "show", "all": "show",
}
SHOW_ORDER = ("together", "mirror", "canon", "alternate", "free")
# สไตล์พลัง: auto = ตามความดังเพลง · hype = ตื่นเต้นตลอด · inner = อินเนอร์ซึ้ง ๆ
STYLES = ("auto", "hype", "inner")
STYLE_TH = {"auto": "ตามอารมณ์เพลง", "hype": "ตื่นเต้นสุด ๆ", "inner": "อินเนอร์"}


def normalize_style(style) -> str:
    st = str(style or "").strip().lower()
    if st in STYLES:
        return st
    if any(k in st for k in ("hype", "ตื่นเต้น", "มันส์", "สุด", "แรง", "excit", "energ")):
        return "hype"
    if any(k in st for k in ("inner", "อิน", "ซึ้ง", "soft", "ช้า", "เบา", "feel")):
        return "inner"
    return "auto"


def _log(msg: str) -> None:
    """print ที่ไม่พังบน console ที่ไม่รองรับ emoji/ไทย (เช่น cp874)"""
    try:
        print(msg)
    except UnicodeEncodeError:
        import sys
        enc = sys.stdout.encoding or "ascii"
        print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))


def normalize_mode(mode) -> str:
    """แปลงชื่อโหมดจากผู้ใช้/LLM → หนึ่งใน MODES (ไม่รู้จัก = together)"""
    m = str(mode or "").strip().lower()
    if m in MODES:
        return m
    for key, val in _MODE_ALIASES.items():
        if key in m:
            return val
    return "together"


# ---------------------------------------------------------------- ท่าเต้น
# แต่ละท่าคืน (dz_mm, nod_deg, tilt_deg, yaw_deg, base_deg)
#   nod = ก้ม/เงย, tilt = เอียงซ้าย/ขวา — แปลงเป็น roll/pitch ตาม robot.nod_axis

def _hit(b: float) -> float:
    """1 ตรงจังหวะพอดี → 0 กลางจังหวะ (ยอดแหลม ให้ความรู้สึก "ลง" จังหวะ)"""
    return (0.5 * (1.0 + math.cos(2 * math.pi * b))) ** 2


def _bounce(b, amp=1.0):
    h = _hit(b)
    return amp * (5.0 * (1.0 - h) - 2.5), -6.0 * amp * h


def move_bounce(b):
    dz, nod = _bounce(b)
    return dz, nod, 0.0, 0.0, 0.0


def move_sway(b):
    dz, _ = _bounce(b, 0.6)
    return dz, 0.0, 15.0 * math.sin(math.pi * b), 0.0, 10.0 * math.sin(math.pi * b / 2)


def move_groove(b):
    dz, nod = _bounce(b, 0.7)
    return dz, nod * 1.6, 0.0, 12.0 * math.sin(math.pi * b / 2), 0.0


def move_circle(b):
    a = math.pi * b / 2           # 1 รอบต่อ 4 จังหวะ
    dz, _ = _bounce(b, 0.5)
    return dz, 10.0 * math.cos(a), 12.0 * math.sin(a), 0.0, 0.0


def move_twist(b):
    s = math.sin(math.pi * b / 2)
    dz, _ = _bounce(b, 0.6)
    return dz, 0.0, 0.0, -15.0 * s, 25.0 * s


def move_headbang(b):
    h = _hit(b)
    return 3.0 * (1.0 - h) - 1.5, 4.0 - 16.0 * h, 0.0, 0.0, 0.0


def move_look(b):
    # หันซ้าย 2 จังหวะ / ขวา 2 จังหวะ — square wave แบบนุ่ม (ไม่กระชากมอเตอร์)
    side = math.tanh(3.0 * math.sin(math.pi * b / 2)) / math.tanh(3.0)
    dz, nod = _bounce(b, 0.5)
    return dz, nod, 8.0 * side, 22.0 * side, 8.0 * side


def move_idle(b):
    """ท่ารอของตัวที่ไม่ได้เต้น — โยกเบา ๆ ตามจังหวะ"""
    dz, nod = _bounce(b, 0.3)
    return dz, nod, 4.0 * math.sin(math.pi * b / 2), 0.0, 0.0


# ---------- ท่าตื่นเต้น (hype) — ช่วงเพลงมันส์/ดัง ----------
def move_jump(b):
    """กระโดด: ยุบตัวระหว่างจังหวะ แล้วพุ่งขึ้น+เงยหน้าตรงจังหวะ"""
    h = _hit(b)
    side = math.sin(math.pi * b / 2)
    return 11.0 * h - 4.0, 9.0 * h - 3.0, 5.0 * side, 0.0, 10.0 * side


def move_shimmy(b):
    """สั่นไหล่รัว ๆ (2 ครั้งต่อจังหวะ) + เด้ง"""
    dz, nod = _bounce(b, 0.8)
    return dz, nod, 9.0 * math.sin(4 * math.pi * b), 6.0 * math.sin(math.pi * b / 2), 0.0


def move_pump(b):
    """ชกลม: ก้มลงตรงจังหวะ เงยขึ้นตรง "และ" (offbeat) — แบบคนในคอนเสิร์ต"""
    c = math.cos(2 * math.pi * b)
    side = math.sin(math.pi * b / 4)
    return 4.0 * -c, -13.0 * c, 0.0, 18.0 * side, 15.0 * side


def move_hype_twist(b):
    """บิดตัวแรง + เฮดแบงเบา ๆ"""
    s = math.sin(math.pi * b / 2)
    h = _hit(b)
    return 4.0 * (1.0 - h) - 2.0, 3.0 - 10.0 * h, 0.0, -20.0 * s, 40.0 * s


def move_shoulder_pop(b):
    """เอียงกระแทกซ้าย-ขวาสลับทุกจังหวะ"""
    tilt = 17.0 * math.cos(math.pi * b) * (0.5 + 0.5 * math.cos(2 * math.pi * b))
    dz, nod = _bounce(b, 0.6)
    return dz, nod, tilt, 0.0, 6.0 * math.cos(math.pi * b)


# ---------- ท่าอินเนอร์ (soft) — ช่วงเพลงเบา/ซึ้ง ----------
def move_feel(b):
    """อินเนอร์: เงยหน้าเหมือนหลับตาฟัง โยกตัวช้า ๆ ทีละ 8 จังหวะ"""
    a = math.pi * b / 4
    return (3.0 * math.sin(math.pi * b / 2), 11.0 + 4.0 * math.sin(math.pi * b / 2),
            18.0 * math.sin(a), 8.0 * math.sin(a), 15.0 * math.sin(a))


def move_float(b):
    """ลอยตามเพลง: ขึ้นลงช้า ๆ หันมองไกล"""
    a = math.pi * b / 4
    return 6.0 * math.sin(a), 5.0 + 3.0 * math.cos(a), 7.0 * math.sin(math.pi * b / 2),         25.0 * math.sin(a), 10.0 * math.sin(a)


def move_body_wave(b):
    """คลื่นตัว: ขึ้นลง + ก้มเงยเหลื่อมเฟส ดูพลิ้ว"""
    return (5.0 * math.sin(math.pi * b), 10.0 * math.sin(math.pi * b - math.pi / 2),
            6.0 * math.sin(math.pi * b / 2), 0.0, 8.0 * math.sin(math.pi * b / 2))


# ---------- ท่าเพิ่ม (ให้ออกท่าเยอะ ๆ) ----------
def move_spin(b):
    """หมุนตัวกว้าง ๆ ซ้าย-ขวา (ฐาน ±55°) หัวหันสวนนิด ๆ"""
    s = math.sin(math.pi * b / 4)
    dz, nod = _bounce(b, 0.6)
    return dz, nod, 8.0 * s, -18.0 * s, 55.0 * s


def move_peek(b):
    """แอบมอง: โผล่ซ้าย (เอียง+หัน) → กลับกลาง → โผล่ขวา ตามจังหวะ"""
    s = math.sin(math.pi * b / 2)
    h = _hit(b)
    return 3.0 * h, 6.0 * h, 16.0 * s, 28.0 * s, 0.0


def move_yes_yes(b):
    """พยักหน้ารัว 2 ครั้งต่อจังหวะ — "ใช่ ๆ เพลงนี้แหละ!" """
    c = math.cos(4 * math.pi * b)
    dz, _ = _bounce(b, 0.5)
    return dz, 9.0 * c - 2.0, 0.0, 10.0 * math.sin(math.pi * b / 2), 0.0


def move_wiggle(b):
    """ส่ายหัวดุ๊กดิ๊ก (หันซ้ายขวาเร็ว) + ส่ายเอวช้า"""
    dz, nod = _bounce(b, 0.5)
    return dz, nod, 0.0, 20.0 * math.sin(2 * math.pi * b), 18.0 * math.sin(math.pi * b / 2)


def move_rock(b):
    """โยกแบบร็อก: เอียงเยอะ + ก้มตาม + ฐานตาม (2 จังหวะ/ข้าง)"""
    s = math.sin(math.pi * b / 2)
    h = _hit(b)
    return 4.0 * (1.0 - h) - 2.0, -10.0 * h + 4.0, 20.0 * s, 0.0, 22.0 * s


def move_celebrate(b):
    """ฉลอง: เงยหน้าสูง ยืดตัวขึ้น โยกซ้ายขวาเหมือนชูมือ"""
    s = math.sin(math.pi * b)
    h = _hit(b)
    return 6.0 + 4.0 * h, 16.0 + 4.0 * h, 14.0 * s, 12.0 * s, 20.0 * math.sin(math.pi * b / 2)


def move_robot(b):
    """ท่าหุ่นยนต์: ขยับเป็นจังหวะ ๆ (หยุดค้างแล้วสะบัด) หัน/เอียงทีละขั้น"""
    step = math.floor(b)
    frac = b - step
    ease = 0.5 - 0.5 * math.cos(math.pi * min(1.0, frac / 0.35))   # สะบัดเร็วต้นจังหวะ
    pat = [(0, 0, 0), (12, 0, 25), (0, 15, 0), (-12, 0, -25)]
    a, c = pat[int(step) % 4], pat[int(step - 1) % 4]
    yaw, tilt, base = (c[i] + (a[i] - c[i]) * ease for i in range(3))
    return 2.0 * ease, 0.0, tilt, yaw, base


MOVES = {
    "bounce": move_bounce, "sway": move_sway, "groove": move_groove,
    "circle": move_circle, "twist": move_twist, "headbang": move_headbang,
    "look": move_look, "jump": move_jump, "shimmy": move_shimmy, "pump": move_pump,
    "hype_twist": move_hype_twist, "shoulder_pop": move_shoulder_pop,
    "feel": move_feel, "float": move_float, "body_wave": move_body_wave,
    "spin": move_spin, "peek": move_peek, "yes_yes": move_yes_yes,
    "wiggle": move_wiggle, "rock": move_rock, "celebrate": move_celebrate,
    "robot": move_robot,
}
# ระดับพลังของเพลง → ชุดท่า
POOLS = {
    "soft": ["feel", "float", "body_wave", "circle", "spin"],          # อินเนอร์
    "mid": ["bounce", "sway", "groove", "circle", "twist", "look", "shoulder_pop",
            "body_wave", "peek", "wiggle", "rock", "robot", "spin"],
    "hype": ["jump", "shimmy", "pump", "hype_twist", "headbang", "shoulder_pop",
             "yes_yes", "rock", "celebrate", "wiggle", "peek"],
}
# จำนวนท่าต่อห้อง — ช่วงมันส์เปลี่ยนท่าทุก 2 จังหวะ (ออกท่าเยอะ)
SEGMENTS = {"soft": 1, "mid": 2, "hype": 2}
LEVELS = ("soft", "mid", "hype")
SEG_FADE = 0.75       # crossfade ต้นช่วงท่า (จังหวะ)


def default_level(bar: int) -> str:
    """ระดับพลังเมื่อไม่รู้ความดังเพลง — มันส์ขึ้นเรื่อย ๆ แล้วพักอินเนอร์ (8 ห้อง)"""
    return ("mid", "mid", "hype", "hype", "mid", "hype", "hype", "soft")[bar % 8]


def _raw_choice(key: int, seed: int | None, level: str) -> int:
    pool = POOLS.get(level) or POOLS["mid"]
    return random.Random((seed or 0) * 100_003 + key * 7 + LEVELS.index(level)).randrange(len(pool))


def _move_for(key: int, seed: int | None, level: str):
    """ท่าของช่วง key (= bar*2 + ครึ่งห้อง) — deterministic ไม่ซ้ำช่วงก่อนหน้า"""
    pool = POOLS.get(level) or POOLS["mid"]
    i = _raw_choice(key, seed, level)
    if i == _raw_choice(key - 1, seed, level):
        i = (i + 1) % len(pool)
    return MOVES[pool[i]]


def _segment(b: float, level_of):
    """(key, จังหวะที่ผ่านไปในช่วง, level) ของจังหวะ b"""
    bar = int(math.floor(b / 4))
    lv = level_of(bar)
    n = SEGMENTS.get(lv, 1)
    seg_len = 4.0 / n
    k = int((b - bar * 4) // seg_len)
    return bar * 2 + (k if n == 2 else 0), (b - bar * 4) - k * seg_len, lv


def choreo_frame(b: float, seed: int | None = None, level_of=None):
    """ท่าที่จังหวะ b — เปลี่ยนท่าทุกช่วง (1-2 ช่วงต่อห้องตามระดับพลัง) + crossfade

    level_of(bar) -> "soft" | "mid" | "hype" (None = default_level)
    """
    level_of = level_of or default_level
    key, ph, lv = _segment(b, level_of)
    cur = _move_for(key, seed, lv)(b)
    if ph >= SEG_FADE:
        return cur
    pkey, _, plv = _segment(b - ph - 1e-6, level_of)     # ช่วงก่อนหน้า
    prev = _move_for(pkey, seed, plv)(b)
    w = ph / SEG_FADE
    w = w * w * (3 - 2 * w)       # smoothstep
    return tuple(p + (c - p) * w for p, c in zip(prev, cur))


def mirror(frame):
    dz, nod, tilt, yaw, base = frame
    return dz, nod, -tilt, -yaw, -base


def scale(frame, k: float):
    return tuple(v * k for v in frame)


FADE_BEATS = 0.75     # ช่วง crossfade ตอนเปลี่ยนบทบาท/โหมด (จังหวะ)


def _blend(f_prev, f_cur, ph: float):
    """ผสมท่าช่วงต้นของช่วงใหม่ (ph = จังหวะที่ผ่านไปในช่วงนั้น)"""
    if ph >= FADE_BEATS:
        return f_cur
    w = ph / FADE_BEATS
    w = w * w * (3 - 2 * w)
    return tuple(p + (c - p) * w for p, c in zip(f_prev, f_cur))


def _alternate(idx: int, b: float, phrase: int, lv=None):
    return choreo_frame(b, level_of=lv) if phrase % 2 == idx % 2 else move_idle(b)


def mode_frame(mode: str, idx: int, b: float, level_of=None):
    """ท่าของหุ่นตัวที่ idx (0=A, 1=B, ...) ในโหมด mode ณ จังหวะ b"""
    if mode == "show":
        seg = int(math.floor(b / 16))
        ph = b - seg * 16
        cur = _mode_frame(SHOW_ORDER[seg % len(SHOW_ORDER)], idx, b, level_of)
        if ph >= FADE_BEATS:
            return cur
        prev = _mode_frame(SHOW_ORDER[(seg - 1) % len(SHOW_ORDER)], idx, b, level_of)
        return _blend(prev, cur, ph)
    return _mode_frame(mode, idx, b, level_of)


def _mode_frame(mode: str, idx: int, b: float, lv=None):
    if mode == "alternate":
        phrase = int(math.floor(b / 8))            # 2 ห้องต่อคน
        ph = b - phrase * 8
        cur = _alternate(idx, b, phrase, lv)
        return cur if ph >= FADE_BEATS else _blend(_alternate(idx, b, phrase - 1, lv), cur, ph)
    if mode == "free":
        return choreo_frame(b, seed=idx + 1, level_of=lv)
    if idx == 0 or mode == "together":
        return choreo_frame(b, level_of=lv)
    if mode == "canon":
        return choreo_frame(b - float(idx), level_of=lv)   # ตัวที่ idx ช้ากว่า idx จังหวะ
    if mode == "mirror":
        f = choreo_frame(b, level_of=lv)
        return mirror(f) if idx % 2 else f
    return choreo_frame(b, level_of=lv)


# ---------------------------------------------------------------- ตัวควบคุม
class DanceController:
    """เต้นหุ่นหลายตัวตามจังหวะเพลงที่ได้ยินจากลำโพง (thread แยก)"""

    def __init__(self, robots, mode: str = "together", tracker: BeatTracker | None = None,
                 rate_hz: float = 25.0, lead_s: float = 0.12,
                 silence_timeout: float = 8.0, start_timeout: float = 60.0,
                 max_duration: float | None = None, speed: int | None = None,
                 acc: int = 20, names=None, on_stop=None, style: str = "auto",
                 amount: float = 1.2):
        self.robots = [r for r in robots if r is not None]
        self.mode = normalize_mode(mode)
        self.tracker = tracker or BeatTracker()
        self._own_tracker = tracker is None
        self.dt = 1.0 / rate_hz
        self.lead = lead_s                 # ส่งท่าล่วงหน้า ชดเชยหน่วงของมอเตอร์/เสียง
        self.silence_timeout = silence_timeout
        self.start_timeout = start_timeout
        self.max_duration = max_duration
        self.speed = speed
        self.acc = acc
        self.names = list(names or [f"หุ่น{i + 1}" for i in range(len(self.robots))])
        self.on_stop = on_stop
        self.stop_reason = ""
        self._amp = 0.5
        self.style = normalize_style(style)
        self.amount = float(amount)        # ขนาดท่าโดยรวม (1.0 = ปกติ, มาก = ออกท่าเยอะ — clamp ตาม limits)
        self._energy = 0.6                 # ความดังเพลงแบบเรียบ (EMA ~1.5 วินาที)
        self._level = "mid"                # ระดับปัจจุบัน (มี hysteresis)
        self._bar_levels: dict[int, str] = {}   # ระดับที่ล็อกไว้ต่อห้อง (ท่าไม่สลับกลางห้อง)
        self._kick = 0.0                   # แรงกระตุกตามเสียงกลอง (อินกับเพลง)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------- ควบคุม ----------
    def start(self) -> "DanceController":
        for r in self.robots:
            r.dancing = True
        self.tracker.start()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="Dance")
        self._thread.start()
        _log(f"[Dance] 🕺 เริ่มเต้น โหมด {self.mode} ({MODE_TH[self.mode]}) "
              f"× {len(self.robots)} ตัว")
        return self

    def stop(self, reason: str = "สั่งหยุด", wait: bool = True) -> None:
        if not self.stop_reason:
            self.stop_reason = reason
        self._stop.set()
        if wait and self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=3)

    def set_style(self, style) -> str:
        self.style = normalize_style(style)
        # ห้องปัจจุบันคงท่าเดิม (ไม่กระชากกลางห้อง) — ล้างเฉพาะห้องถัดไป
        cur_bar = int(math.floor(self.tracker.beat_position(time.time() + self.lead) / 4))
        for k in [k for k in self._bar_levels if k > cur_bar]:
            del self._bar_levels[k]
        _log(f"[Dance] สไตล์ → {self.style} ({STYLE_TH[self.style]})")
        return self.style

    # ---------- ระดับพลังของเพลง ----------
    def _update_level(self) -> None:
        tr = self.tracker
        if not tr.available:
            return
        e = tr.intensity if tr.audible else 0.0
        self._energy += (e - self._energy) * (self.dt / 1.5)
        if self._level != "hype" and self._energy > 0.74:
            self._level = "hype"
        elif self._level != "soft" and self._energy < 0.38:
            self._level = "soft"
        elif self._level == "hype" and self._energy < 0.62:
            self._level = "mid"
        elif self._level == "soft" and self._energy > 0.5:
            self._level = "mid"

    def level_of(self, bar: int) -> str:
        """ระดับของห้อง bar — ล็อกครั้งแรกที่ถาม (ห้องเดียวกันท่าเดียวตลอด)"""
        lv = self._bar_levels.get(bar)
        if lv is None:
            if self.style == "hype":
                lv = "soft" if bar % 8 == 7 else "hype"       # พักหายใจห้องเดียว
            elif self.style == "inner":
                lv = "mid" if bar % 8 == 7 else "soft"
            elif not self.tracker.available:
                lv = default_level(bar)
            else:
                lv = self._level
            self._bar_levels[bar] = lv
            if len(self._bar_levels) > 64:
                for k in sorted(self._bar_levels)[:32]:
                    del self._bar_levels[k]
        return lv

    def set_mode(self, mode) -> str:
        self.mode = normalize_mode(mode)
        _log(f"[Dance] เปลี่ยนโหมด → {self.mode} ({MODE_TH[self.mode]})")
        return self.mode

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status(self) -> dict:
        t = self.tracker
        return {"mode": self.mode, "bpm": round(t.bpm, 1), "listening": t.available,
                "audible": t.audible, "confidence": round(t.confidence, 2),
                "style": self.style, "level": self._level if t.available else "-",
                "energy": round(self._energy, 2), "running": self.running}

    # ---------- loop ----------
    def _send(self, robot, frame):
        dz, nod, tilt, yaw, base = frame
        z0 = robot.config["stewart"]["z_home"]
        if getattr(robot, "nod_axis", "roll") == "roll":
            roll, pitch = nod, tilt
        else:
            roll, pitch = tilt, nod
        robot.stream_pose(z0 + dz, roll, pitch, yaw, base_deg=base,
                          speed=self.speed, acc=self.acc)

    def _should_stop(self, t0: float, now: float) -> str | None:
        if self.max_duration and now - t0 > self.max_duration:
            return "ครบเวลา"
        tr = self.tracker
        if not tr.available:
            return None                     # ฟังไม่ได้ → เต้นจนสั่งหยุด
        if tr.first_sound == 0.0:
            if now - t0 > self.start_timeout:
                return "ไม่ได้ยินเพลง"
        elif now - tr.last_sound > self.silence_timeout:
            return "เพลงจบ (เงียบ)"
        return None

    def _run(self) -> None:
        t0 = time.time()
        errors = {}
        try:
            while not self._stop.is_set():
                now = time.time()
                reason = self._should_stop(t0, now)
                if reason:
                    self.stop_reason = reason
                    break
                b = self.tracker.beat_position(now + self.lead)
                self._update_level()
                bar_lv = self.level_of(int(math.floor(b / 4)))
                # ความแรงของท่าตามความดังเพลง (ยังไม่มีเสียง = โยกเบา ๆ รอ)
                if self.tracker.audible:
                    target = 0.6 + 0.45 * self.tracker.intensity
                else:
                    target = 0.35 if self.tracker.available else 0.95
                target *= {"hype": 1.15, "soft": 0.95}.get(bar_lv, 1.0)
                self._amp += (target - self._amp) * 0.1
                # อินกับเพลง: กระตุกหัวตามเสียงกลองจริง (นอกเหนือจาก grid จังหวะ)
                self._kick = max(self._kick * 0.72, self.tracker.accent)
                kick = self._kick * (1.3 if bar_lv == "hype" else 0.6 if bar_lv == "soft" else 1.0)
                for i, r in enumerate(self.robots):
                    try:
                        f = scale(mode_frame(self.mode, i, b, self.level_of),
                                  self._amp * self.amount)
                        f = (f[0] + 2.5 * kick, f[1] - 7.0 * kick, f[2], f[3], f[4])
                        self._send(r, f)
                    except Exception as exc:  # noqa: BLE001 — ตัวหนึ่งพังอีกตัวยังเต้นต่อ
                        if i not in errors:
                            errors[i] = exc
                            _log(f"[Dance] ⚠️ {self.names[i]} ส่งท่าไม่ได้: {exc}")
                time.sleep(max(0.0, self.dt - (time.time() - now)))
        finally:
            for r in self.robots:
                try:
                    r.stream_pose(None, 0, 0, 0, base_deg=0.0, speed=self.speed, acc=30)
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(0.6)
            for r in self.robots:
                r.dancing = False
            if self._own_tracker:
                self.tracker.stop()
            _log(f"[Dance] หยุดเต้น — {self.stop_reason or 'สั่งหยุด'}")
            if self.on_stop:
                try:
                    self.on_stop(self.stop_reason)
                except Exception:  # noqa: BLE001
                    pass


# ---------------------------------------------------------------- singleton
_current: DanceController | None = None
_lock = threading.Lock()


def start_dance(robots, mode: str = "together", **kwargs) -> DanceController:
    """เริ่มเต้น (หยุดชุดเดิมก่อนถ้ามี) — คืน DanceController"""
    global _current
    with _lock:
        if _current is not None:
            _current.stop("เริ่มเพลงใหม่")
        # เก็บไว้ก่อน start — ถ้า start พังกลางทาง stop_dance() ยังหยุดได้
        _current = DanceController(robots, mode=mode, **kwargs)
        ctl = _current
    try:
        ctl.start()
    except Exception:
        ctl.stop("เริ่มเต้นไม่สำเร็จ")
        for r in ctl.robots:
            r.dancing = False
        raise
    return ctl


def stop_dance(reason: str = "สั่งหยุด") -> bool:
    """หยุดเต้น — คืน True ถ้ามีการเต้นอยู่"""
    global _current
    with _lock:
        cur, _current = _current, None
    if cur is None:
        return False
    was = cur.running
    cur.stop(reason)
    return was


def set_mode(mode) -> str | None:
    """เปลี่ยนโหมดขณะเต้น — คืนโหมดใหม่ หรือ None ถ้าไม่ได้เต้นอยู่"""
    cur = _current
    if cur is None or not cur.running:
        return None
    return cur.set_mode(mode)


def set_style(style) -> str | None:
    """เปลี่ยนสไตล์ (auto/hype/inner) ขณะเต้น — None ถ้าไม่ได้เต้นอยู่"""
    cur = _current
    if cur is None or not cur.running:
        return None
    return cur.set_style(style)


def current() -> DanceController | None:
    cur = _current
    return cur if cur is not None and cur.running else None
