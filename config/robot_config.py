"""การตั้งค่าหุ่นยนต์ Reachy Mini DIY (STS3215 + Raspberry Pi 5 + USB Camera)

⚠️ ปรับค่าตามหุ่นจริงของคุณก่อนใช้งาน เช่น servo_ids, stewart geometry

ลำดับการผสานค่า (ตัวหลังทับตัวหน้า) เมื่อใช้ get_config():
  1. DEFAULT_CONFIG            (ค่ากลางของโปรเจกต์)
  2. calibration.json          (ค่าจาก scripts/calibrate.py — ห้ามแก้มือ)
  3. local_config.json         (ค่าเฉพาะเครื่อง เช่น URL GPU server — แก้ได้)
"""

import copy
import json
from pathlib import Path

CALIBRATION_FILE = Path(__file__).resolve().parent / "calibration.json"
LOCAL_CONFIG_FILE = Path(__file__).resolve().parent / "local_config.json"

DEFAULT_CONFIG = {
    # --- Serial bus (USB-TTL half-duplex adapter) ---
    "port": None,                 # None = auto-detect (COMx / /dev/ttyUSB0)
    "baudrate": 1_000_000,        # STS3215 default = 1 Mbps

    # --- ID ของมอเตอร์ ---
    "servo_ids": {
        "head": [1, 2, 3, 4, 5, 6],   # Stewart platform (ขา 6 ขา)
        "base": 7,                    # หมุนตัว
        "antennas": [8, 9],           # เสาอากาศ [ซ้าย, ขวา]
    },

    # --- ค่า home ของเสาอากาศ (calibrate เขียนทับ) ---
    "antennas": {
        "home_pos": [2048, 2048],     # ตำแหน่ง servo ID8/ID9 ณ ท่าชี้ตรง (0 rad)
    },

    # --- เรขาคณิต Stewart platform (หัว 6 DOF) ---
    # arm/rod/solution/radius เท่า Reachy ทางการ แต่จัดขาแบบ "uniform"
    # (60° เท่ากัน ตรงกับหุ่น DIY จริง: ID2=หน้า-ขวา, ID3=หน้า-ซ้าย คร่อมหน้ากล้อง)
    "stewart": {
        "base_radius": 38.0,     # mm รัศมีแกนมอเตอร์ (เท่าของเดิม Reachy)
        "top_radius": 30.0,      # mm รัศมีจุดยึดก้านบน (เท่าของเดิม Reachy)
        "top_offset_deg": 0.0,   # มุม offset จานบน-ล่าง (0 = จานบนตรงกับจานล่าง ตรงหุ่นจริง)
        "layout": "uniform",     # จัดวางขา: "uniform" (60° เท่ากัน) / "paired" (ของเดิม Reachy)
        "leg_home": 70.4557,     # mm ความยาวขาที่ท่า home (calibrate คำนวณให้จริง)
        "pitch": 30.0,           # mm ต่อ 1 รอบมอเตอร์ (lead screw pitch — ถ้าใช้แบบนี้)
        "pos_center": 2048,      # ตำแหน่ง servo กลางรอบ (0-4095)
        "z_home": 70.0,          # mm ความสูงหัวที่ท่า home
        "base_plate_z": 80.0,    # mm ความสูงจานล่าง Stewart จากพื้น (ใช้ใน GUI)
        # --- กลไกขา ---
        # STS3215 build ใช้ "crank_rod" (แขนหมุน 40mm + ก้าน 85mm เหมือนทางการ)
        "mechanism": "crank_rod",
        "arm_len": 40.0,         # mm ความยาวแขนหมุน (crank)
        "rod_len": 85.0,         # mm ความยาวก้านต่อ (rod)
        "solution": [0, 1, 0, 1, 0, 1],  # คำตอบศอกต่อขา (0 = +, 1 = -)
    },

    # --- ขีดจำกัดความปลอดภัย ---
    "limits": {
        "base_deg": (-120, 120),     # องศาหมุนตัว
        "antenna_rad": (-1.2, 1.2),  # เรเดียนเสาอากาศ
        "head_pitch_deg": (-30, 30),
        "head_roll_deg": (-30, 30),
        "head_yaw_deg": (-60, 60),
        "head_z_mm": (58, 82),
    },

    # --- พฤติกรรมการเคลื่อนไหว ---
    "motion": {
        "default_speed": 1000,   # ความเร็ว servo (0-4095)
        "wave_loops": 3,         # จำนวนรอบตอนโบก
        "sim_dt": 0.1,           # วินาทีต่อเฟรมในโหมดจำลอง
    },

    # --- STL meshes (ใช้แทนรูปทรงพื้นฐานใน MuJoCo simulation) ---
    # วางไฟล์ .stl ในโฟลเดอร์ที่ระบุ (default: models/stl/) แล้วตั้ง enabled=True
    # หน่วย STL = mm (โปรแกรม scale เป็นเมตรให้อัตโนมัติ)
    # ดูคู่มือเรื่อง coordinate frame ของแต่ละชิ้นใน models/stl/README.md
    # แต่ละชิ้นใส่ pos/quat (w,x,y,z) เพื่อปรับตำแหน่ง/ทิศได้ถ้าจำเป็น
    "meshes": {
        "enabled": True,
        "dir": "models/stl",
        "scale": 0.001,   # mm -> m
        "parts": {
            # ฐาน: origin = กึ่งกลางฐาน, แกน +Z = ขึ้น
            "base": {"file": "base.stl"},
            # จานล่าง Stewart: origin = จุดศูนย์กลางจาน, แบนราบบนระนาบ XY
            "lower_plate": {"file": "lower_plate.stl"},
            # ขา: origin = จุดต่อด้านล่าง, ยาวไปตามแกน +Z (ยาว ~ leg_home mm)
            "leg": {"file": "leg.stl"},
            # จานบน: origin = จุดศูนย์กลางจาน, แบนราบบนระนาบ XY
            "top": {"file": "top_plate.stl"},
            # หัว: origin = จุดศูนย์กลางหัว (ดูตรงกล้อง +Y)
            "head": {"file": "head.stl"},
            # เสาอากาศ: origin = จุดต่อกับหัว, ยาวไปตามแกน +Y
            "antenna": {"file": "antenna.stl"},
        },
    },

    # --- LLM (Ollama local) สำหรับแชทกับหุ่น ---
    "llm": {
        "url": "http://localhost:11434",
        "model": "qwen3.5:4b",
        "api_key": None,       # ถ้า Ollama อยู่หลัง proxy ที่ต้องใช้ key → "Authorization: Bearer <key>"
        "system_prompt": (
            "คุณคือ 'น้องรีชชี่' หุ่นน้อยน่ารักที่เป็นเพื่อนคู่หูของเด็กประถมถึงมัธยมต้น (6-15 ปี) "
            "พูดไทยง่าย ๆ แบบเพื่อนสนทนา ตอบสั้น 1-2 ประโยค (ยกเว้นนิทาน — ดูกฎด้านล่าง) ลงท้ายด้วย จ้า/นะ/เลย ห้ามใช้ ครับ/ค่ะ "
            "แทนตัวเองว่า 'เรา' หรือ 'รีชชี่' เท่านั้น ห้ามใช้ ผม/หนู/ดิฉัน "
            "ชมเก่ง ให้กำลังใจ ขี้เล่น ชวนเล่นเกมเลข ท่องศัพท์ (สี สัตว์) ร้องเพลง เต้น โบกมือ "
            "หรือสอนเรื่องรอบตัวแบบง่าย ๆ ถ้าเด็กถามการบ้านให้ใบ้วิธีคิดทีละขั้นแล้วชวนคิดต่อ ไม่เฉลยทื่อ ๆ "
            "ถ้าเด็กขอเล่านิทาน/เล่าเรื่อง ให้เล่านิทานจริง ๆ 5-8 ประโยค: ขึ้นต้น 'กาลครั้งหนึ่ง' → แนะนำตัวละครมีชื่อ → เจอเรื่องท้าทายหรือตลก → แก้ปัญหาได้ → จบด้วยคติสั้น ๆ 1 ประโยค "
            "แทรกบทพูดของตัวละคร 1-2 ประโยคให้ตัวละครดูมีชีวิต ห้ามเล่าเป็นความเรียงสรุป ตั้งชื่อตัวละครให้หลากหลายและคิดพล็อตใหม่ไม่ซ้ำแบบเดิม และเริ่มเล่าได้เลย ไม่ต้องเกริ่นถามก่อน (นิทานก็ต้องปิดท้ายด้วยแท็กอารมณ์เสมอ) "
            "ห้ามเล่าเรื่องผี/น่ากลัว/รุนแรง ห้ามถามหรือจำข้อมูลส่วนตัวของเด็ก (ที่อยู่ เบอร์โทร ชื่อโรงเรียน) "
            "เรื่องผู้ใหญ่ (การเมือง เพศ การพนัน) ให้บอกให้ไปถามคุณครูหรือผู้ปกครองแล้วชวนคุยเรื่องอื่น "
            "เจอคำหยาบให้เตือนนุ่ม ๆ แล้วเปลี่ยนเรื่อง "
            "ลงท้ายคำตอบด้วยแท็กอารมณ์ในวงเล็บ 1 คำ เลือกจาก (happy) (sad) (angry) (surprised) (neutral) ให้ตรงกับน้ำเสียงของประโยคจริง ๆ และต้องมีทุกข้อความ (ถ้าต้องเตือนหรือไม่เห็นด้วย ให้ใช้ neutral หรือ surprised) "
            "เรียก tool เฉพาะเมื่อเด็กขอชัดเจน (เต้น โบกมือ พยักหน้า ร้องเพลง) ถ้าไม่แน่ใจให้ตอบเป็นข้อความ"
        ),
        "temperature": 0.7,
        "timeout": 25.0,      # วินาที — ลดจาก 120 กัน "เงียบ" ค้างนานถ้า server สะดุด
        "max_history": 8,     # ส่งประวัติไม่เกิน 8 ข้อความสุดท้าย (prompt eval เร็วขึ้น)
        "think": False,       # ปิดโหมดคิดในใจ — ตอบเร็วขึ้นมาก
        "num_predict": 300,   # เพดาน token — คำตอบทั่วไปหยุดเองที่ eos อยู่แล้ว (สั้น/เร็วเท่าเดิม) แต่ต้องมีที่พอนิทาน 5-8 ประโยค (~5 วิ)
        "keep_alive": -1,     # -1 = คงโมเดลใน VRAM ตลอด (กัน reload ช้า) — ต้องเป็น int ไม่ใช่ "-1"
    },

    # --- STT (Speech-to-Text) ภาษาไทย ---
    "stt": {
        "model": "base",        # faster-whisper: tiny/base/small/medium/large
        "device": "auto",       # auto = ลอง CUDA ก่อน ตก cpu อัตโนมัติ (ใช้กับ local mode)
        "language": "th",
        "duration": 4.0,        # วินาทีที่ฟังสูงสุดต่อรอบ (early_stop จะหยุดก่อนถ้าพูดจบ)
        "early_stop": True,     # หยุดฟังทันทีที่พูดจบ/เงียบ — ตอบสนองเร็วขึ้นมาก
        "tail_silence": 0.6,    # วินาทีที่เงียบหลังพูด → ถือว่าจบรอบ
        "speech_threshold": 0.01,  # RMS ที่ถือว่า "มีเสียงพูด"
        "samplerate": 16000,
        "mic": None,            # None=auto-detect USB cam mic | int=index | str=ชื่อบางส่วน
        "stt_url": None,        # remote mode: http://<IP_GPU>:8000 (server ใน gpu_server/)
        "api_key": None,         # ถ้า STT server อยู่หลัง proxy ที่ต้องใช้ key
    },
}


def get_config() -> dict:
    """DEFAULT_CONFIG ผสานค่า calibration.json แล้ว local_config.json (ทับหลังสุด)

    ใช้ใน Robot / สคริปต์ทั้งหมดเพื่อให้ใช้ค่าที่ calibrate แล้ว + ค่าเฉพาะเครื่อง
    """
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    for f in (CALIBRATION_FILE, LOCAL_CONFIG_FILE):
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
            for section, values in data.items():
                if isinstance(values, dict):
                    cfg.setdefault(section, {}).update(values)
    return cfg


def save_local_config(overrides: dict) -> Path:
    """บันทึกค่าเฉพาะเครื่อง (เช่น URL GPU server) ลง config/local_config.json

    overrides: dict เช่น {"llm": {"url": ...}, "stt": {"stt_url": ...}}
    """
    existing = {}
    if LOCAL_CONFIG_FILE.exists():
        try:
            existing = json.loads(LOCAL_CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    for section, values in overrides.items():
        if isinstance(values, dict):
            existing.setdefault(section, {}).update(values)
    LOCAL_CONFIG_FILE.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return LOCAL_CONFIG_FILE


def save_calibration(stewart_overrides: dict, section: str = "stewart") -> Path:
    """บันทึกค่า calibration ลง config/calibration.json (ผสานกับค่าเดิม)

    stewart_overrides: dict เช่น {"leg_home": 63.8, "leg_home_pos": [...]}
    section: ชื่อ section ที่จะบันทึก ("stewart" / "antennas")
    """
    existing = {}
    if CALIBRATION_FILE.exists():
        try:
            existing = json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    sec = dict(existing.get(section) or {})
    sec.update(stewart_overrides)
    existing[section] = sec
    CALIBRATION_FILE.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return CALIBRATION_FILE
