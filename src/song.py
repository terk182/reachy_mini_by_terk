"""หุ่นร้องเพลง — สังเคราะห์เมโลดี้ด้วย numpy + เล่นผ่าน sounddevice

ไม่มี dependency เพิ่ม (ใช้ numpy + sounddevice ที่มีอยู่แล้วในโปรเจกต์)
เมโลดี้เป็นเพลงสาธารณสมบัติ (public domain): Twinkle Twinkle / Happy Birthday
ตอนเล่นหุ่นจะเต้นตามจังหวะไปพร้อมกัน (ขยับหัว + เสาอากาศสลับข้าง)
"""

from __future__ import annotations

import threading
import time

import numpy as np

# --- ความถี่โน้ต (Hz) ---
NOTE_FREQ = {
    "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23,
    "G4": 392.00, "A4": 440.00, "B4": 493.88,
    "C5": 523.25, "D5": 587.33, "E5": 659.25, "F5": 698.46, "G5": 783.99,
}

# --- เมโลดี้: [(โน้ต, จำนวน beat), ...] ---
MELODIES: dict[str, list[tuple[str, float]]] = {
    "twinkle": [
        ("C4", 1), ("C4", 1), ("G4", 1), ("G4", 1), ("A4", 1), ("A4", 1), ("G4", 2),
        ("F4", 1), ("F4", 1), ("E4", 1), ("E4", 1), ("D4", 1), ("D4", 1), ("C4", 2),
        ("G4", 1), ("G4", 1), ("F4", 1), ("F4", 1), ("E4", 1), ("E4", 1), ("D4", 2),
        ("G4", 1), ("G4", 1), ("F4", 1), ("F4", 1), ("E4", 1), ("E4", 1), ("D4", 2),
        ("C4", 1), ("C4", 1), ("G4", 1), ("G4", 1), ("A4", 1), ("A4", 1), ("G4", 2),
        ("F4", 1), ("F4", 1), ("E4", 1), ("E4", 1), ("D4", 1), ("D4", 1), ("C4", 2),
    ],
    "happy_birthday": [
        ("G4", 1), ("G4", 1), ("A4", 2), ("G4", 2), ("C5", 2), ("B4", 4),
        ("G4", 1), ("G4", 1), ("A4", 2), ("G4", 2), ("D5", 2), ("C5", 4),
        ("G4", 1), ("G4", 1), ("G5", 2), ("E5", 2), ("C5", 2), ("B4", 2), ("A4", 4),
        ("F5", 1), ("F5", 1), ("E5", 2), ("C5", 2), ("D5", 2), ("C5", 4),
    ],
    # เพลงช้าง (เพลงเด็กไทย พื้นบ้าน — public domain)
    # "ช้าง ช้าง ช้าง น้องเคยเห็นช้างหรือเปล่า..."
    "chang": [
        ("G4", 1), ("G4", 1), ("E4", 1),           # ช้าง ช้าง ช้าง
        ("G4", 1), ("G4", 1), ("E4", 1),           # น้องเคยเห็น
        ("G4", 1), ("A4", 1), ("G4", 1), ("E4", 2),  # ช้างหรือเปล่า
        ("E4", 1), ("G4", 1), ("G4", 1),           # ช้างมันตัวโต
        ("F4", 1), ("E4", 1), ("D4", 1), ("C4", 2),  # ไม่เบา
        ("C4", 1), ("F4", 1), ("F4", 1),           # จมูกยาว ๆ
        ("E4", 1), ("D4", 1), ("C4", 2),           # เรียกว่างวง
    ],
}

SAMPLE_RATE = 22050


def _note(freq: float, dur: float, sr: int, volume: float) -> np.ndarray:
    """สร้างโน้ต 1 ตัว (sine + harmonic พร้อม envelope กันเสียงคลิก)"""
    n = int(sr * dur)
    t = np.arange(n) / sr
    tone = (
        np.sin(2 * np.pi * freq * t)
        + 0.4 * np.sin(4 * np.pi * freq * t)
        + 0.15 * np.sin(6 * np.pi * freq * t)
    )
    # envelope: attack 15ms, release 80ms
    env = np.ones(n, dtype=np.float32)
    a = min(int(sr * 0.015), n // 2)
    r = min(int(sr * 0.08), n // 2)
    if a > 0:
        env[:a] = np.linspace(0.0, 1.0, a)
    if r > 0:
        env[-r:] = np.linspace(1.0, 0.0, r)
    # เว้นช่องเล็กท้ายโน้ตให้แยกจังหวะชัด
    gap = min(int(sr * 0.02), n // 4)
    if gap > 0:
        env[-gap:] = 0.0
    return (tone * env * volume).astype(np.float32)


def synthesize(melody: list[tuple[str, float]], beat: float = 0.35,
               volume: float = 0.6, sr: int = SAMPLE_RATE) -> np.ndarray:
    """เมโลดี้ → PCM float32 mono (sr=22050)"""
    out = np.zeros(0, dtype=np.float32)
    for name, beats in melody:
        freq = NOTE_FREQ.get(name)
        if freq is None:
            continue
        out = np.concatenate([out, _note(freq, beats * beat, sr, volume)])
    return out


def play(pcm: np.ndarray, sr: int = SAMPLE_RATE, block: bool = True) -> None:
    """เล่น PCM ผ่าน sounddevice"""
    import sounddevice as sd

    sd.play(pcm, sr)
    if block:
        sd.wait()


def sing(robot, melody: str = "twinkle", beat: float = 0.35,
         volume: float = 0.6) -> None:
    """ร้องเพลง + เต้นตามจังหวะ (block จนเพลงจบ)

    robot.nod_axis กำหนดแกนก้ม/เงย (roll = DIY, pitch = official)
    """
    notes = MELODIES.get(melody, MELODIES["twinkle"])
    pcm = synthesize(notes, beat=beat, volume=volume)
    done = threading.Event()

    def _play():
        try:
            play(pcm, sr=SAMPLE_RATE, block=True)
        except Exception as exc:  # noqa: BLE001 — ไม่มี output device ก็ข้าม
            print(f"[song] เล่นไม่สำเร็จ: {exc}")
        finally:
            done.set()

    threading.Thread(target=_play, daemon=True).start()

    axis = getattr(robot, "nod_axis", "roll")
    sign = 1
    step = min(0.45, beat * 1.3)
    try:
        while not done.is_set():
            robot.set_head_pose(**{axis: 10 * sign}, duration=step)
            robot.set_antennas(0.6 * sign, -0.6 * sign, duration=step)
            sign = -sign
            if getattr(robot, "is_sim", False):
                time.sleep(step)  # sim ไม่ sleep เอง — หน่วงให้จังหวะ
    finally:
        # timeout กัน hang ถ้า sounddevice ไม่มี output / ค้าง
        done.wait(timeout=len(pcm) / SAMPLE_RATE + 3.0)
        try:
            robot.set_head_pose(**{axis: 0}, duration=0.4)
            robot.set_antennas(0, 0, duration=0.4)
        except Exception:  # noqa: BLE001
            pass
