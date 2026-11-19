"""แปลงอารมณ์จากข้อความ -> ท่าทางหุ่นยนต์

LLM จะตอบพร้อมแท็กอารมณ์ เช่น "..." (happy) — เราดึงแท็กออกมาแสดงผล
และสั่งหุ่นขยับตามอารมณ์ ถ้า LLM ไม่ใส่แท็ก จะ fallback ด้วยคำสำคัญ
"""

from __future__ import annotations

import re
import threading

# คำสำคัญสำหรับ fallback (ไทย/อังกฤษ)
EMOTION_KEYWORDS = {
    "happy": ["ดีใจ", "ยินดี", "สนุก", "ขำ", "เยี่ยม", "เก่ง", "สุดยอด", "น่ารัก",
              "😂", "😄", "😊", "haha", "happy", "love", "awesome", "great"],
    "sad": ["เสียใจ", "เศร้า", "เหงา", "เสียดาย", "แย่", "ไม่ดีเลย", "ผิดหวัง",
            "😢", "😭", "sad", "sorry", "bad", "upset"],
    "angry": ["โกรธ", "โมโห", "หงุดหงิด", "ไม่พอใจ", "แย่มาก", "โง่",
              "😠", "😡", "angry", "mad", "furious"],
    "surprised": ["ว้าว", "โอ้โห", "ไม่น่าเชื่อ", "ตกใจ", "จริงหรอ", "อ้าว",
                  "😲", "😱", "wow", "surprised", "unbelievable", "really"],
}

_EMOTIONS = ("happy", "sad", "angry", "surprised", "neutral")


def detect_emotion(text: str) -> str:
    """หาอารมณ์จากข้อความ: แท็ก (emotion) ก่อน แล้ว fallback ด้วยคำสำคัญ"""
    low = text.lower()
    for emo in _EMOTIONS:
        if f"({emo})" in low:
            return emo
    best, best_count = "neutral", 0
    for emo, words in EMOTION_KEYWORDS.items():
        count = sum(1 for w in words if w.lower() in low)
        if count > best_count:
            best, best_count = emo, count
    return best


def strip_emotion_tag(text: str) -> str:
    """ลบแท็ก/บรรยายทุกแบบที่อยู่ในวงเล็บ + แท็กอารมณ์เปล่า ๆ ออกจากข้อความ

    โมเดลเล็ก (qwen3.5:4b) ชอบเขียน "(happy)" "(ready)" "(พยักหน้า 2 ครั้ง)"
    ไว้ในข้อความ — ลบวงเล็บทั้งหมด ไม่ให้ TTS อ่านออกมา
    """
    t = re.sub(r"\([^)]*\)", "", text)  # ลบ (...) ทุกตำแหน่ง
    # ลบคำอารมณ์เปล่า ๆ ท้ายประโยค (โมเดลเล็กอาจไม่ใส่วงเล็บ เช่น "... 2 ค่ะ happy")
    t = re.sub(r"\s*(happy|sad|angry|surprised|neutral)\s*$",
               "", t, flags=re.IGNORECASE)
    return t.strip()


# คำบรรยายท่าทางที่ LLM เขียนเป็นตัวหนังสือ → แปลงเป็น tool จริง
GESTURE_TO_TOOL = {
    "พยักหน้า": "nod",
    "เอียงหัว": "head_tilt",
    "ส่ายหัว": "shake_head",
    "โค้งคำนับ": "bow",
    "โบกมือ": "wave",
    "ไหว้": "wave",
    "เต้น": "dance",
    "หมุนตัว": "turn",
    "ร้องเพลง": "sing",
}


def detect_gesture(text: str):
    """LLM เขียนบรรยายท่าทาง (เช่น "ผมพยักหน้าให้ดู") แทนการเรียก tool

    คืนชื่อ tool (nod/head_tilt/...) หรือ None
    """
    for word, tool in GESTURE_TO_TOOL.items():
        if word in text:
            return tool
    return None


def strip_gesture_words(text: str) -> str:
    """ลบคำบรรยายท่าทางออกจากคำพูด (กัน TTS อ่าน "พยักหน้า" ออกมาทั้งที่ทำจริงแล้ว)"""
    for word in GESTURE_TO_TOOL:
        text = text.replace(word, "")
    return re.sub(r"\s{2,}", " ", text).strip()


def apply_emotion(robot, emotion: str) -> None:
    """สั่งหุ่นขยับตามอารมณ์ (เลือกแกน nod ตามชนิดหุ่นอัตโนมัติ)

    robot.nod_axis: "roll" = หุ่น DIY (หน้า=+Y), "pitch" = Reachy ทางการ (หน้า=+X)
    """
    axis = getattr(robot, "nod_axis", "roll")

    def nod(value: float, duration: float):
        if hasattr(robot, "set_head_pose_eased"):
            robot.set_head_pose_eased(**{axis: value}, duration=duration, method="cartoon")
        else:
            robot.set_head_pose(**{axis: value}, duration=duration)

    if emotion == "happy":
        robot.set_antennas(1.2, -1.2, duration=0.35)
        nod(14, 0.6)
        robot.set_antennas(-1.2, 1.2, duration=0.35)
        nod(0, 0.6)
    elif emotion == "sad":
        nod(-16, 1.0)   # ก้มเศร้า
        robot.set_antennas(-0.6, -0.6, duration=1.0)
        nod(0, 1.0)
    elif emotion == "angry":
        robot.set_antennas(1.4, 1.4, duration=0.35)
        nod(12, 0.35)
        robot.set_antennas(0, 0, duration=0.35)
        nod(0, 0.5)
    elif emotion == "surprised":
        nod(18, 0.5)    # เงยตกใจ
        robot.set_antennas(1.4, -1.4, duration=0.5)
        nod(0, 0.7)
    else:  # neutral
        robot.set_head_pose(roll=0, pitch=0, yaw=0)
        robot.set_antennas(0, 0, duration=0.3)


def talk_animation(robot, stop_event: threading.Event,
                   amplitude: float = 12.0, period: float = 0.28) -> None:
    """ขยับหัว + เสาอากาศตามจังหวะพูด (พยัก + โบกเสาสลับ — ชัดและน่ารัก)

    robot.nod_axis กำหนดแกนก้ม/เงย ("roll" DIY / "pitch" official)
    """
    import time

    axis = getattr(robot, "nod_axis", "roll")
    sign = 1
    try:
        while not stop_event.is_set():
            # หัวพยัก + เสาอากาศโบกสลับข้าง (เหมือนกำลังพูดอย่างตั้งใจ)
            robot.set_head_pose(**{axis: amplitude * sign}, duration=period)
            robot.set_antennas(0.7 * sign, -0.7 * sign, duration=period)
            if getattr(robot, "is_sim", False):
                time.sleep(period)  # sim ไม่ sleep เอง — หน่วงให้จังหวะเนียนใน viewer
            sign = -sign
    finally:
        try:
            robot.set_head_pose(**{axis: 0}, duration=0.3)
            robot.set_antennas(0, 0, duration=0.3)
        except Exception:  # noqa: BLE001
            pass


def speak_with_motion(robot, text: str, voice: str | None = None) -> bool:
    """พูด (TTS) พร้อมขยับหัวตามจังหวะเสียงจริง (audio-reactive)

    voice: "male"/"female" = โปรไฟล์เสียงไทย (gTTS + pitch shift) — None = เสียงเดิม
    ลำดับ:
      1. สังเคราะห์ TTS → MP3
      2. decode → PCM → วิเคราะห์ sway offsets (SwayRollRT จาก official)
      3. เล่นเสียง (thread) + ขยับหัวตาม offset ทีละ hop (50ms)
    ถ้า decode/วิเคราะห์ล้มเหลว → fallback talk_animation แบบ sine เดิม
    """
    from src import speech_sway
    from src.tts import clean_for_speech, play_file, speak, synthesize_to_file_cached

    clean = clean_for_speech(text or "")
    if not clean:
        return True

    mp3 = synthesize_to_file_cached(clean, voice=voice)
    if not mp3:
        return speak(clean, voice=voice)  # สังเคราะห์ไม่ได้ -> พูดแบบเดิม (ไม่มี motion)

    offsets = None
    try:
        pcm, sr = speech_sway.decode_mp3(mp3)
        offsets = speech_sway.compute_offsets(pcm, sr)
    except Exception as exc:  # noqa: BLE001
        print(f"[motion] วิเคราะห์เสียงล้มเหลว ({exc}) -> ใช้ talk_animation แบบเดิม")

    if not offsets:
        return _speak_with_animation(robot, clean, mp3)

    axis = getattr(robot, "nod_axis", "roll")
    hop_s = speech_sway.HOP_MS / 1000.0

    import time

    play_done = threading.Event()

    def play():
        try:
            play_file(mp3, block=True)
        finally:
            play_done.set()

    threading.Thread(target=play, daemon=True).start()

    try:
        sign = 1.0
        for i, sway in enumerate(offsets):
            pose = speech_sway.sway_to_pose(sway, axis)
            robot.set_head_pose(**pose, duration=hop_s)
            # โบกเสาเบา ๆ ตามจังหวะพูด (ทุก ~500ms สลับข้าง) — "พูดพร้อมท่าทาง"
            # แอมพลิจูดต่ำ (0.2 rad) + ช้า — กันเสียง servo กลบเสียงพูด
            if i % 10 == 0:
                robot.set_antennas(0.2 * sign, -0.2 * sign, duration=0.2)
                sign = -sign
            if getattr(robot, "is_sim", False):
                time.sleep(hop_s)
    finally:
        try:
            robot.set_head_pose(roll=0, pitch=0, yaw=0, duration=0.3)
            robot.set_antennas(0, 0, duration=0.3)
        except Exception:  # noqa: BLE001
            pass
        # รอเสียงพูดจบจริง (กันพูดซ้อน) — timeout กัน hang ถ้า audio device ค้าง
        play_done.wait(timeout=3.0)
    return True


def _speak_with_animation(robot, text: str, mp3: str) -> bool:
    """fallback: พยักหัว sine + เสาอากาศโบก พร้อมเล่นเสียง (แบบเดิม)

    เล่นเสียงใน thread + timeout — กัน hang ทั้ง main loop ถ้า audio device ค้าง
    """
    from src.tts import play_file

    stop = threading.Event()
    worker = threading.Thread(
        target=talk_animation, args=(robot, stop), daemon=True)
    worker.start()

    done = threading.Event()
    result = {"ok": False}

    def _play():
        try:
            result["ok"] = play_file(mp3, block=True)
        finally:
            done.set()

    player = threading.Thread(target=_play, daemon=True)
    player.start()
    done.wait(timeout=10.0)  # ประโยค TTS สั้น (~2-4 วิ) — 10 วิเกินพอ
    stop.set()
    worker.join(timeout=2.0)
    return result["ok"]
