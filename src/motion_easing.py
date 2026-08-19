"""Motion easing — พอร์ตจาก official Reachy Mini (utils/interpolation.py)

easing สำหรับท่าทางน่ารัก: linear / min_jerk / ease_in_out / cartoon
- cartoon = easeInOutBack → เด้งเกินแล้วกลับ (anticipation + overshoot) แบบการ์ตูน
- min_jerk = เนียนไร้กระตุก (ทางวิชาการ)
"""
from __future__ import annotations

from enum import Enum


class Easing(str, Enum):
    LINEAR = "linear"
    MIN_JERK = "min_jerk"
    EASE_IN_OUT = "ease_in_out"
    CARTOON = "cartoon"


def _coerce(method) -> "Easing":
    if isinstance(method, Easing):
        return method
    try:
        return Easing(str(method).lower())
    except ValueError:
        raise ValueError(
            f"ไม่รู้จัก easing: {method!r} (ใช้ linear/min_jerk/ease_in_out/cartoon)"
        )


def time_trajectory(t: float, method="min_jerk") -> float:
    """easing function: t ∈ [0,1] → eased t

    หมายเหตุ cartoon อาจคืนค่า <0 (anticipation) หรือ >1 (overshoot) แล้วกลับมาที่ 1
    """
    m = _coerce(method)
    if t < 0.0 or t > 1.0:
        raise ValueError("t ต้องอยู่ใน [0,1]")

    if m is Easing.LINEAR:
        return t

    if m is Easing.MIN_JERK:
        return 10 * t**3 - 15 * t**4 + 6 * t**5

    if m is Easing.EASE_IN_OUT:
        if t < 0.5:
            return 2 * t * t
        return 1 - ((-2 * t + 2) ** 2) / 2

    # Easing.CARTOON — easeInOutBack
    c1 = 1.70158
    c2 = c1 * 1.525
    if t < 0.5:
        return ((2 * t) ** 2 * ((c2 + 1) * 2 * t - c2)) / 2
    return (((2 * t - 2) ** 2 * ((c2 + 1) * (2 * t - 2) + c2)) + 2) / 2


def eased(start: float, end: float, t: float) -> float:
    """interpolate ค่าเดียวด้วย eased t"""
    return start + (end - start) * t


def eased_waypoints(start: float, end: float, steps: int = 20, method="cartoon"):
    """yield ค่า interpolate จาก start→end ด้วย easing (จุดแรก=start, สุดท้าย=end)"""
    if steps <= 1:
        yield end
        return
    for i in range(steps):
        t = time_trajectory(i / (steps - 1), method)
        yield start + (end - start) * t
