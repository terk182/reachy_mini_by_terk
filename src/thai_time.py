"""บริบทวัน–เวลาไทยสำหรับ LLM (ให้หุ่นตอบเรื่องวัน/เวลา/เทศกาลได้)

ทำไมต้องมี: LLM ไม่รู้ว่าวันนี้วันอะไร → เด็กถาม "วันนี้วันอะไร" หุ่นจะตอบไม่ได้
วิธีใช้: สร้างข้อความสั้น ๆ แล้วส่งเป็น `extra_context` ให้ `ask_llm()` ใน voice_assistant

    from src.thai_time import build_time_context
    ctx = build_time_context()   # "วันนี้เป็นวันอังคารที่ 15 กันยายน 2569 เวลา 14:35 น. ..."
"""

from __future__ import annotations

import datetime as _dt

# ชื่อวัน (index = date.weekday(): 0=จันทร์)
THAI_WEEKDAYS = ("จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์")

# ชื่อเดือน (index = month-1)
THAI_MONTHS = (
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
)

# วันสำคัญแบบวันที่คงที่ (เดือน, วัน, ชื่อ) — เฉพาะที่เด็กไทยสนุกด้วย
FIXED_EVENTS = (
    (1, 1, "วันขึ้นปีใหม่"),
    (4, 13, "วันสงกรานต์"),
    (4, 14, "วันสงกรานต์"),
    (4, 15, "วันสงกรานต์"),
    (6, 26, "วันสุนทรภู่"),
    (8, 12, "วันแม่แห่งชาติ"),
    (8, 18, "วันวิทยาศาสตร์แห่งชาติ"),
    (12, 5, "วันพ่อแห่งชาติ"),
    (12, 25, "วันคริสต์มาส"),
)


def thai_weekday(d: _dt.date) -> str:
    """ชื่อวันภาษาไทย เช่น 'อังคาร'"""
    return THAI_WEEKDAYS[d.weekday()]


def thai_date(d: _dt.date) -> str:
    """วันที่แบบไทย/พ.ศ. เช่น '15 กันยายน 2569'"""
    return f"{d.day} {THAI_MONTHS[d.month - 1]} {d.year + 543}"


def childrens_day(year: int) -> _dt.date:
    """วันเด็กแห่งชาติ = เสาร์ที่ 2 ของมกราคม"""
    first = _dt.date(year, 1, 1)
    first_sat = first + _dt.timedelta(days=(5 - first.weekday()) % 7)
    return first_sat + _dt.timedelta(days=7)


def upcoming_events(ref: _dt.date, days_ahead: int = 120) -> list[tuple[str, int]]:
    """วันสำคัญที่กำลังจะถึงภายใน `days_ahead` วัน → [(ชื่อ, อีกกี่วัน)] (0 = วันนี้)

    ค่าเริ่มต้น 120 วัน — ให้ LLM ตอบ "อีกกี่วันถึงวันพ่อ" ได้โดยอ่านจาก context
    (ไม่ต้องคำนวณเอง ซึ่งโมเดลเล็กคำนวณพลาดบ่อย)
    นับรวมปีถัดไปด้วย (กันกรณีปลาย ธ.ค. แล้ว "วันขึ้นปีใหม่" อยู่ในสัปดาห์หน้า)
    """
    candidates: list[tuple[str, _dt.date]] = []
    for month, day, name in FIXED_EVENTS:
        for year in (ref.year, ref.year + 1):
            try:
                candidates.append((name, _dt.date(year, month, day)))
            except ValueError:  # วันที่ไม่มีในปีนั้น (เช่น 29 ก.พ.)
                continue
    for year in (ref.year, ref.year + 1):
        candidates.append(("วันเด็กแห่งชาติ", childrens_day(year)))

    found = [
        (name, days)
        for name, when in candidates
        if 0 <= (days := (when - ref).days) <= days_ahead
    ]
    # เรียงใกล้วันก่อน + ตัดชื่อซ้ำ (สงกรานต์มี 3 วัน)
    seen: set[str] = set()
    unique: list[tuple[str, int]] = []
    for name, days in sorted(found, key=lambda x: x[1]):
        if name not in seen:
            seen.add(name)
            unique.append((name, days))
    return unique


def build_time_context(now: _dt.datetime | None = None, days_ahead: int = 120) -> str:
    """ข้อความบริบทวัน–เวลา (ภาษาไทย) สำหรับฉีดเข้า prompt ของ LLM

    ใส่วันสำคัญพร้อม "อีก N วัน" ตรง ๆ — LLM ไม่ต้องคำนวณวันที่เอง
    """
    now = now or _dt.datetime.now()
    today = now.date()
    text = (
        f"ข้อมูลปัจจุบัน: วันนี้เป็นวัน{thai_weekday(today)}ที่ {thai_date(today)} "
        f"เวลา {now.hour:02d}:{now.minute:02d} น."
    )
    events = upcoming_events(today, days_ahead)
    if events:
        text += " วันสำคัญที่กำลังจะถึง: " + ", ".join(
            f"{name} อีก {days} วัน" for name, days in events
        )
    return text
