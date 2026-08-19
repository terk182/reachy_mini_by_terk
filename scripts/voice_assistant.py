r"""Voice assistant ต่อเนื่อง — ฟังเสียง → LLM → ตอบเสียง + ขยับตามอารมณ์

รับเสียงจากไมค์ (default: auto เลือก USB cam mic) → faster-whisper → Ollama LLM
→ พูดตอบ (TTS) + หุ่นขยับตามอารมณ์ วนไปเรื่อยๆ จนกว่าจะพูด "หยุด" หรือ Ctrl+C

วิธีใช้:
    .venv\Scripts\python.exe scripts\voice_assistant.py --hardware
    .venv\Scripts\python.exe scripts\voice_assistant.py --hardware --list-mics
    .venv\Scripts\python.exe scripts\voice_assistant.py --hardware --mic LifeCam
    .venv\Scripts\python.exe scripts\voice_assistant.py --hardware --model qwen2.5:3b
"""

import argparse
import queue
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.robot_config import get_config  # noqa: E402
from src.expressions import (  # noqa: E402
    apply_emotion,
    detect_emotion,
    detect_gesture,
    speak_with_motion,
    strip_emotion_tag,
    strip_gesture_words,
)
from src.llm import OllamaClient  # noqa: E402
from src.robot import Robot  # noqa: E402
from src.robot_tools import TOOLS, execute as execute_tool  # noqa: E402
from src.song import MELODIES, sing  # noqa: E402
from src.stt import listen, list_mics, resolve_mic  # noqa: E402
from src.vision_control import GESTURE_ACTIONS, VisionThread  # noqa: E402

# คำสั่งหยุด (พูดแล้วออก) — ตรวจแบบระวัง substring กัน false positive
# เช่น "ออก" ใน "ออกมา" ต้องไม่นับเป็นคำสั่งหยุด
STOP_EXACT = (
    "หยุด", "เลิก", "ปิด", "จบ", "พอ", "ออก",
    "stop", "exit", "quit", "bye",
)
STOP_PHRASES = (
    "พอแล้ว", "พอเถอะ", "พอละ", "จบแล้ว", "จบการสนทนา", "จบก่อน",
    "หยุดเลย", "หยุดก่อน", "หยุดคุย", "เลิกคุย", "เลิกแล้ว",
    "ปิดระบบ", "ปิดเครื่อง", "ไม่เล่นแล้ว", "ไม่คุยแล้ว",
    "ไปก่อนนะ", "ไปก่อน", "ออกก่อน", "ออกแล้ว",
)


def is_stop(text: str) -> bool:
    """ตัดสินว่าผู้ใช้สั่งหยุดไหม

    - short (หยุด/เลิก/ปิด/...) → ต้องตรงเป๊ะทั้งประโยค
    - phrase (พอแล้ว/ไปก่อนนะ/...) → substring ได้เฉพาะประโยคสั้น (≤ 20 ตัวอักษร)
      กัน false positive เช่น "...ให้ลูกกลุ่มพอแล้ว" ที่มี "พอแล้ว" ปนอยู่ท้ายประโยคยาว
    """
    t = text.lower().strip()
    if not t:
        return False
    if t in STOP_EXACT:
        return True
    if len(t) <= 20 and any(p in t for p in STOP_PHRASES):
        return True
    import re
    return any(re.search(rf"\b{w}\b", t) for w in ("stop", "exit", "quit"))

# --- โหมดจัดแสดง (exhibition) — หุ่นน่ารัก + ทนเสียงเด็กมารุม ---
IDLE_INTERVAL = 15.0       # วิ เงียบนานเท่านี้ → ทำท่า idle สุ่ม
POST_SPEECH_GAP = 0.5      # วิ พักหลังพูด ก่อนฟังใหม่ (กันได้ยินเสียงตัวเอง)
FALLBACK_COOLDOWN = 8.0    # วิ คั่นการพูด "ว่าไงนะ" (กันพูดรัว)
GREETING_COOLDOWN = 12.0   # วิ ห้ามทักทาย "คนเข้ามา" ซ้ำ (กัน face detection flicker)
GREETING_WORDS = ("สวัสดี", "หวัดดี", "hello", "hi", "hey", "ทักทาย", "ไง")
GREETING_REPLIES = ("สวัสดีจ้า!", "ว่าไงจ๊ะ มาทักทายเราหรอ!", "ดีจัง ได้เจอเธอแล้ว!")
SING_WORDS = ("ร้องเพลง", "ร้องให้ฟัง", "sing", "song", "เพลงให้ฟัง", "ร้องเพลงให้ฟัง")
DANCE_WORDS = ("เต้น", "เตน", "dance")
DANCE_REPLIES = ("เต้นแล้วจ้า สนุกไหม?", "ดูท่าเต้นของหนูสิ!", "โยก ๆ สนุกจังเลย!")
WAVE_WORDS = ("โบกมือ", "โบก", "ไหว้", "wave")
WAVE_REPLIES = ("สวัสดีจ้า!", "โบกมือทักทายทุกคนเลย!", "สวัสดีทุกคนจ้า!")
# ตอบสั้น ๆ ตามท่ามือ (vision) — พูดเมื่อเห็นท่ามือจากกล้อง
GESTURE_REPLIES = {
    "thumbs_up": ("ถูกใจเลย!", "เยี่ยมไปเลย!"),
    "open_palm": ("สวัสดีจ้า!", "ทักทายเหมือนกัน!"),
    "victory": ("สนุกจัง!", "เย้!"),
    "love": ("ขอบคุณนะ!", "รักเหมือนกัน!"),
    "fist": ("โอเค!", "รับทราบ!"),
    "point": ("มีอะไรอยู่ตรงนั้นเหรอ?",),
}
# คำถามตัวตน/ความสามารถ → ตอบทันทีแบบคงที่ (แม่น + เร็ว ไม่รอ LLM ที่อาจตอบเพี้ยน)
SELF_ANSWERS = (
    (("ชื่ออะไร", "คุณชื่อ", "เธอชื่อ", "เป็นใคร"),
     "ฉันชื่อน้องรีชชี่จ้า! หุ่นยนต์เพื่อนเล่นของหนูเอง"),
    (("ทำอะไรได้", "ความสามารถ", "ช่วยอะไรได้", "เล่นอะไรได้"),
     "หนูเต้นได้ ร้องเพลงได้ เล่าเรื่องได้ แล้วก็คุยกับทุกคนได้ด้วยนะ!"),
)
# ท่อง ABC/A-Z → ตอบคงที่ (LLM ตัวเล็กท่องตัวอักษรเพี้ยน)
ABC_WORDS = ("ถึง z", "ถึง ซี", "ถึงซี", "abc", "ตัวอักษร", "a ถึง")
ABC_REPLY = ("เอ บี ซี ดี อี เอฟ จี เอช ไอ เจ เค แอล เอ็ม เอ็น โอ พี คิว อาร์ เอส ที ยู วี ดับเบิลยู เอ็กซ์ วาย แซด!",)
# คำบ่งบอกเจตนาขอท่าทาง (กัน LLM เรียก tool มั่วกับคำที่ฟังไม่ชัด/สั้นเกิน เช่น "แค่..." → dance)
TOOL_INTENT = {
    "wave": ("โบก", "ไหว้", "สวัสดี", "hello", "hi", "ทักทาย", "wave"),
    "dance": ("เต้น", "เตน", "dance", "โยก"),
    "nod": ("พยักหน้า", "เห็นด้วย", "nod"),
    "shake_head": ("ส่าย", "ส่ายหัว", "shake"),
    "head_tilt": ("เอียงหัว", "เอียง", "tilt", "สงสัย"),
    "bow": ("โค้งคำนับ", "คำนับ", "bow"),
    "happy": ("ดีใจ", "ยินดี", "มีความสุข"),
    "look_around": ("มอง", "ดูรอบ", "ดูนู่น"),
    "turn": ("หมุน", "หัน", "turn"),
    "random_cute": ("ทำอะไร", "โชว์", "น่ารัก"),
    "sing": ("ร้อง", "เพลง", "sing", "song", "ช้าง"),
}
FALLBACK_PHRASES = (
    "ว่าไงนะ?",
    "ได้ยินไม่ชัดเลย พูดอีกทีได้ไหม",
    "เข้ามาใกล้ ๆ หน่อยได้ไหม",
)


def ask_llm(client, robot, history):
    """คุย LLM แบบรองรับ tool calling — จำกัดทำท่าแค่ 1 ครั้งต่อคำตอบ

    โมเดลเล็ก (qwen3.5:4b) มักเรียก tool ซ้ำไม่หยุด → ทำเฉพาะ tool แรก
    แล้วถามรอบสุดท้ายแบบไม่ส่ง tools (บังคับตอบเป็นข้อความล้วน)
    คืน (ข้อความ, did_tool) — did_tool=True แปลว่าทำท่าไปแล้ว (กันทำซ้ำจาก gesture)
    """
    msg = client.chat_tools(history, TOOLS)
    tool_calls = msg.get("tool_calls")
    if not tool_calls:
        return (msg.get("content") or ""), False

    # ทำเฉพาะ tool แรกตัวเดียว
    call = tool_calls[0]
    fn = call.get("function") or {}
    name = fn.get("name", "")

    # กัน LLM ตัวเล็กเรียก tool มั่วกับคำที่ฟังไม่ชัด (เช่น "แค่..." → dance)
    # ถ้าผู้ใช้ไม่ได้พูดคำที่บ่งบอกเจตนาท่านั้นเลย → ไม่ทำท่า บังคับตอบข้อความ
    last_user = next(
        (m.get("content", "") for m in reversed(history) if m.get("role") == "user"),
        "",
    )
    if name in TOOL_INTENT and last_user and not any(
        k in last_user.lower() for k in TOOL_INTENT[name]
    ):
        final = client.chat_tools(history, None)
        return (final.get("content") or ""), False

    print(f"🛠️ หุ่นทำท่า: {name}")
    result = execute_tool(robot, name, fn.get("arguments", {}))
    history.append(msg)
    history.append({"role": "tool", "tool_name": name, "content": result})

    # ถามครั้งสุดท้ายโดยไม่ส่ง tools — บังคับตอบเป็นข้อความ (กันเรียก tool ซ้ำ)
    final = client.chat_tools(history, None)
    return (final.get("content") or ""), True


def safe_motion(fn, *args, **kwargs):
    """รันท่าทาง/พูดอย่างปลอดภัย — ถ้า serial/USB หลุด ไม่ให้ loop ตาย"""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ หุ่นไม่ตอบสนอง (ข้ามไป): {exc}")
        return None


_last_arrived_greet = 0.0  # เวลาทักทาย "คนเข้ามา" ครั้งล่าสุด (กันพูดซ้ำจาก face flicker)


def drain_vision_events(vision, robot):
    """ดึงเหตุการณ์จาก vision thread (ท่ามือ/คนเข้ามา) แล้วทำแอคชั่น

    - ทำเฉพาะท่ามือ "ล่าสุด" ตัวเดียว (drop ท่าเก่าที่ค้าง queue)
    - ทักทายคนเข้ามาไม่เกิน 1 ครั้งต่อ GREETING_COOLDOWN วิ
    เรียกตอน vision ยัง paused อยู่ (กันชนกับการตามหน้า)
    """
    global _last_arrived_greet

    events = []
    while True:
        try:
            events.append(vision.events.get_nowait())
        except queue.Empty:
            break
    if not events:
        return

    now = time.time()
    arrived = any(e[0] == "arrived" for e in events)
    left = any(e[0] == "left" for e in events)
    last_gesture = None
    for ev in events:
        if ev[0] == "gesture":
            last_gesture = ev[1]

    if arrived and now - _last_arrived_greet > GREETING_COOLDOWN:
        print("👁️ มีคนเข้ามา — โบกมือทักทาย")
        safe_motion(robot.wave)
        safe_motion(speak_with_motion, robot, random.choice(GREETING_REPLIES))
        _last_arrived_greet = now
    elif left and not arrived:
        print("👁️ คนเดินออกไปแล้ว")

    if last_gesture:
        method = GESTURE_ACTIONS.get(last_gesture)
        if method:
            print(f"👁️ ท่ามือ: {last_gesture} → {method}")
            safe_motion(getattr(robot, method))
            replies = GESTURE_REPLIES.get(last_gesture)
            if replies:
                safe_motion(speak_with_motion, robot, random.choice(replies))


def main():
    parser = argparse.ArgumentParser(description="Voice assistant ต่อเนื่อง")
    parser.add_argument("--hardware", action="store_true", help="ใช้หุ่นจริง")
    parser.add_argument("--port", default=None)
    parser.add_argument("--real", action="store_true",
                        help="ใช้โมเดล Reachy Mini แท้ (official daemon)")
    parser.add_argument("--no-gui", action="store_true",
                        help="sim: ไม่เปิดหน้าต่าง 3D MuJoCo")
    parser.add_argument("--model", default=None, help="ชื่อโมเดล Ollama (default จาก config)")
    parser.add_argument("--mic", default=None,
                        help="ไมค์: auto (หา USB cam) / index / keyword เช่น LifeCam")
    parser.add_argument("--list-mics", action="store_true", help="แสดงรายการไมค์แล้วออก")
    parser.add_argument("--duration", type=float, default=4.0,
                        help="วินาทีที่ฟังต่อรอบ (default 4)")
    parser.add_argument("--vision", action="store_true",
                        help="เปิด vision: ตามหน้า + ท่ามือสั่งงาน + ทักทายคนเข้ามา")
    parser.add_argument("--camera", default="lifecam",
                        help="กล้อง vision (ชื่อหรือ id, default 'lifecam')")
    parser.add_argument("--show", action="store_true",
                        help="เปิดหน้าต่าง preview กล้อง (กรอบหน้า + ท่ามือ)")
    args = parser.parse_args()

    if args.list_mics:
        print("อุปกรณ์เสียงเข้า:")
        for idx, name in list_mics():
            print(f"  [{idx}] {name}")
        return

    cfg = get_config()
    llm_cfg = cfg["llm"]
    stt_cfg = cfg["stt"]
    model = args.model or llm_cfg["model"]

    # เช็ค Ollama + โมเดล
    if not OllamaClient(url=llm_cfg["url"]).ping():
        print("⚠️ Ollama ไม่ได้รัน — เปิดด้วย: ollama serve")
        sys.exit(1)
    client = OllamaClient(
        url=llm_cfg["url"], model=model,
        system_prompt=llm_cfg["system_prompt"],
        temperature=llm_cfg["temperature"],
        timeout=llm_cfg.get("timeout", 120.0),
        num_predict=llm_cfg.get("num_predict"),
        max_history=llm_cfg.get("max_history"),
        think=llm_cfg.get("think", False),
        keep_alive=llm_cfg.get("keep_alive", "30m"),
    )
    if model not in client.list_models():
        print(f"⚠️ ยังไม่มีโมเดล {model} — โหลดด้วย: ollama pull {model}")
        sys.exit(1)

    # เลือกไมค์
    mic_arg = args.mic if args.mic is not None else stt_cfg.get("mic")
    mic_idx = resolve_mic(mic_arg)
    mic_name = dict(list_mics()).get(mic_idx, f"index {mic_idx}") if mic_idx is not None else "default"
    print(f"🎤 ใช้ไมค์: {mic_name}")

    # เช็ค STT server (remote) ไว้ก่อน — ล่มจะได้รู้แต่แรก ไม่รอให้ค้าง
    if stt_cfg.get("stt_url"):
        try:
            import urllib.request

            with urllib.request.urlopen(
                f"{stt_cfg['stt_url'].rstrip('/')}/health", timeout=5
            ) as resp:
                print(f"🎧 STT server พร้อม: {stt_cfg['stt_url']}")
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ STT server ไม่ถึง ({stt_cfg['stt_url']}): {exc}")
            print("   → จะ fallback ใช้ whisper local (ช้าและแม่นน้อยกว่า)")

    if args.real:
        from src.real_robot import RealRobot

        if not RealRobot.available():
            print("⚠️ official daemon ไม่พร้อม — รัน: "
                  "reachy_mini_env\\Scripts\\reachy-mini-daemon.exe --sim ก่อน")
            sys.exit(1)
        robot = RealRobot()
    else:
        backend = "hardware" if args.hardware else "sim"
        gui = "mujoco" if (backend == "sim" and not args.no_gui) else False
        robot = Robot(backend=backend, port=args.port, gui=gui)
    robot.wake_up()

    # vision background thread (ตามหน้า + ท่ามือ + presence) — เปิดเมื่อ --vision
    vision = None
    if args.vision:
        vision = VisionThread(robot, camera=args.camera, show=args.show)
        vision.start()

    # อุ่น TTS ล่วงหน้า — คำทักทาย/fallback ที่พูดบ่อย ตอบทันที ไม่รอ gTTS (~1.7 วิ)
    from src.tts import prewarm_phrases

    prewarm_phrases(list(GREETING_REPLIES) + list(FALLBACK_PHRASES))

    history: list[dict] = []
    last_idle = time.time()
    last_fallback = time.time()
    last_health = time.time()
    print(f"🤖 พร้อมแล้ว (โมเดล: {model}, ฟังรอบละ {args.duration:.0f} วิ) — "
          "พูด 'หยุด' เพื่อจบ")

    try:
        while True:
            # เช็ค serial ทุก ~10 วิ — กัน "เขียนไม่ error แต่ servo ไม่ขยับ"
            # (Windows serial zombie handle หลัง USB re-enumerate)
            if time.time() - last_health > 10.0:
                last_health = time.time()
                robot.check_connection()
            # vision: ดึงเหตุการณ์ (ท่ามือ/คนเข้ามา) ก่อน แล้วเริ่มตามหน้า (สบตา)
            if vision:
                drain_vision_events(vision, robot)
                vision.resume()
            print("🎧 ฟัง...")
            try:
                text, heard = listen(
                    duration=args.duration,
                    mic=mic_idx,
                    stt_url=stt_cfg.get("stt_url"),
                    samplerate=stt_cfg["samplerate"],
                    model=stt_cfg["model"],
                    device=stt_cfg["device"],
                    language=stt_cfg["language"],
                    early_stop=stt_cfg.get("early_stop", True),
                    tail_silence=stt_cfg.get("tail_silence", 0.6),
                    speech_threshold=stt_cfg.get("speech_threshold", 0.01),
                    report_heard=True,
                )
            except Exception as exc:  # noqa: BLE001 — remote STT ล่ม -> fallback local
                print(f"⚠️ STT ผิดพลาด ({exc}) — fallback ใช้ whisper local")
                text, heard = listen(
                    duration=args.duration,
                    mic=mic_idx,
                    stt_url=None,
                    samplerate=stt_cfg["samplerate"],
                    model=stt_cfg["model"],
                    device=stt_cfg["device"],
                    language=stt_cfg["language"],
                    early_stop=stt_cfg.get("early_stop", True),
                    tail_silence=stt_cfg.get("tail_silence", 0.6),
                    speech_threshold=stt_cfg.get("speech_threshold", 0.01),
                    report_heard=True,
                )

            # หยุดตามหน้าระหว่างพูด/ทำท่า (กันชนกับ vision thread)
            if vision:
                vision.pause()

            if text:
                last_idle = time.time()
                print(f"🗣️ ได้ยิน: {text}")
                if is_stop(text):
                    print("👋 จบการสนทนา")
                    break

                # คำทักทาย → โบก + ตอบทันที (ไม่รอ LLM — เร็วและเป็นมิตร)
                if any(g in text.lower() for g in GREETING_WORDS):
                    safe_motion(robot.wave)
                    safe_motion(speak_with_motion, robot, random.choice(GREETING_REPLIES))
                    time.sleep(POST_SPEECH_GAP)
                    continue

                # ขอเพลงช้างโดยเฉพาะ → ร้องเพลงช้าง (ก่อน keyword ร้องเพลงทั่วไป)
                if "ช้าง" in text:
                    print("🐘 ร้องเพลงช้างให้ฟัง...")
                    safe_motion(sing, robot, melody="chang")
                    safe_motion(speak_with_motion, robot, "ช้างช้างช้าง น่ารักไหมจ๊ะ?")
                    time.sleep(POST_SPEECH_GAP)
                    continue

                # ขอร้องเพลง → ร้อง + เต้นทันที (ไม่รอ LLM)
                if any(w in text.lower() for w in SING_WORDS):
                    print("🎵 ร้องเพลงให้ฟัง...")
                    safe_motion(sing, robot, melody=random.choice(list(MELODIES)))
                    safe_motion(speak_with_motion, robot, "เพราะไหมจ๊ะ?")
                    time.sleep(POST_SPEECH_GAP)
                    continue

                # ขอเต้น → เต้นทันที (ไม่รอ LLM)
                if any(w in text.lower() for w in DANCE_WORDS):
                    print("💃 เต้นให้ดู...")
                    safe_motion(execute_tool, robot, "dance", {})
                    safe_motion(speak_with_motion, robot, random.choice(DANCE_REPLIES))
                    time.sleep(POST_SPEECH_GAP)
                    continue

                # ขอโบกมือ/ไหว้ → โบกทันที
                if any(w in text.lower() for w in WAVE_WORDS):
                    print("👋 โบกมือให้ดู...")
                    safe_motion(execute_tool, robot, "wave", {})
                    safe_motion(speak_with_motion, robot, random.choice(WAVE_REPLIES))
                    time.sleep(POST_SPEECH_GAP)
                    continue

                # คำถามตัวตน/ความสามารถ → ตอบทันทีแบบคงที่ (แม่น + เร็ว ไม่รอ LLM)
                self_reply = next(
                    (reply for words, reply in SELF_ANSWERS
                     if any(w in text.lower() for w in words)),
                    None,
                )
                if self_reply:
                    print(f"🤖 ตอบ [happy]: {self_reply}")
                    safe_motion(apply_emotion, robot, "happy")
                    safe_motion(speak_with_motion, robot, self_reply)
                    time.sleep(POST_SPEECH_GAP)
                    continue

                # ท่อง ABC/A-Z → ตอบคงที่ (LLM ตัวเล็กท่องเพี้ยน)
                if any(w in text.lower() for w in ABC_WORDS):
                    print("🔤 ท่อง ABC...")
                    safe_motion(apply_emotion, robot, "happy")
                    safe_motion(speak_with_motion, robot, ABC_REPLY[0])
                    time.sleep(POST_SPEECH_GAP)
                    continue

                # กรองเสียงรบกวนสั้นเกิน
                if len(text.strip()) < 2:
                    continue

                history.append({"role": "user", "content": text})
                try:
                    reply, did_tool = ask_llm(client, robot, history)
                    if not reply.strip():
                        continue
                except Exception as exc:  # noqa: BLE001
                    print(f"⚠️ LLM ผิดพลาด: {exc}")
                    continue

                emotion = detect_emotion(reply)
                clean = strip_emotion_tag(reply)
                # LLM เขียนบรรยายท่าทางเป็นตัวหนังสือ (เช่น "ผมพยักหน้า") แทนเรียก tool
                # → ทำท่าจริง + ลบคำบรรยายออกจากคำพูด (กัน TTS อ่าน "พยักหน้า" ออกมา)
                gesture = None if did_tool else detect_gesture(reply)
                if gesture:
                    print(f"🛠️ หุ่นทำท่า: {gesture} (จากคำพูด)")
                    safe_motion(execute_tool, robot, gesture, {})
                    clean = strip_gesture_words(clean)
                history.append({"role": "assistant", "content": clean})
                print(f"🤖 ตอบ [{emotion}]: {clean}")

                # ขยับหุ่น + พูด (หัวพยักตามจังหวะพูด)
                safe_motion(apply_emotion, robot, emotion)
                safe_motion(speak_with_motion, robot, clean)
                time.sleep(POST_SPEECH_GAP)
            elif heard:
                # ได้ยินเสียงแต่ฟังไม่ออก → ท่าสงสัย (จำกัดความถี่กันพูดรัว)
                if time.time() - last_fallback > FALLBACK_COOLDOWN:
                    safe_motion(robot.head_tilt, random.choice((-1, 1)))
                    safe_motion(speak_with_motion, robot, random.choice(FALLBACK_PHRASES))
                    last_fallback = time.time()
                    last_idle = time.time()
                    time.sleep(POST_SPEECH_GAP)
            else:
                # เงียบสนิท → ทำท่า idle น่ารักเป็นระยะ
                if time.time() - last_idle > IDLE_INTERVAL:
                    print("🎭 ทำท่า idle...")
                    safe_motion(robot.random_cute)
                    last_idle = time.time()
    except KeyboardInterrupt:
        print("\n👋 จบ (Ctrl+C)")
    finally:
        if vision:
            vision.stop()
            vision.join(timeout=2.0)
        robot.close()


if __name__ == "__main__":
    main()
