"""Function calling — ให้ LLM สั่งท่าทางหุ่นเองได้ (Ollama tools format)

LLM (gemma4) ตัดสินใจเองว่าเมื่อไหร่ควรโบกมือ/เต้น/พยักหน้า แล้วเรียก tool
ที่นี่มี 2 ส่วน:
  TOOLS   — นิยาม tool ส่งให้ Ollama (OpenAI-compatible)
  execute — แปลง tool call → เรียกเมธอดใน Robot จริง
"""

from __future__ import annotations

import json

# --- นิยาม tool (description ภาษาไทยให้ LLM เลือกถูก) ---
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "wave",
            "description": "โบกเสาอากาศ/โบกมือทักทาย",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dance",
            "description": "เต้นเล็ก ๆ น่ารัก (เอียงซ้ายขวา + ก้มเงย)",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nod",
            "description": "พยักหน้า (ใช่/รับทราบ)",
            "parameters": {
                "type": "object",
                "properties": {
                    "times": {"type": "integer", "description": "จำนวนครั้ง 1-4 (default 3)"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shake_head",
            "description": "ส่ายหัว (ไม่/ปฏิเสธ)",
            "parameters": {
                "type": "object",
                "properties": {
                    "times": {"type": "integer", "description": "จำนวนครั้ง (default 2)"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "head_tilt",
            "description": "เอียงหัวน่ารักแบบน้องหมา",
            "parameters": {
                "type": "object",
                "properties": {
                    "side": {"type": "integer", "description": "1 = เอียงซ้าย, -1 = เอียงขวา"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bow",
            "description": "โค้งคำนับ",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "happy",
            "description": "ดีใจ เด้งขึ้นลง + โบกเสาอากาศ",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "look_around",
            "description": "มองซ้ายขวา (หมุนตัว)",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "turn",
            "description": "หมุนลำตัวไปซ้ายหรือขวาแล้วกลับ (หันไปมองข้าง)",
            "parameters": {
                "type": "object",
                "properties": {
                    "side": {"type": "string", "description": "left หรือ right"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "random_cute",
            "description": "สุ่มทำท่าทางน่ารัก 1 ท่า",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sing",
            "description": "ร้องเพลง/ฮัมเพลง (เล่นเมโลดี้พร้อมเต้นตามจังหวะ)",
            "parameters": {
                "type": "object",
                "properties": {
                    "melody": {
                        "type": "string",
                        "enum": ["twinkle", "happy_birthday", "chang"],
                        "description": "ชื่อเพลง: twinkle / happy_birthday / chang(เพลงช้าง)",
                    }
                },
                "required": [],
            },
        },
    },
]


def _parse_args(arguments) -> dict:
    """arguments อาจมาเป็น dict หรือ str(JSON) — แปลงให้เป็น dict เสมอ"""
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str) and arguments.strip():
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            return {}
    return {}


def execute(robot, name: str, arguments=None) -> str:
    """เรียกท่าทางบน robot ตาม tool call → คืนข้อความผลลัพธ์ (ภาษาไทยสั้น ๆ)"""
    args = _parse_args(arguments)

    def _clamp_times(default: int, lo: int = 1, hi: int = 6) -> int:
        try:
            return max(lo, min(int(args.get("times", default)), hi))
        except (TypeError, ValueError):
            return default

    try:
        if name == "wave":
            robot.wave()
            return "โบกมือทักทายแล้ว"
        if name == "dance":
            robot.dance()
            return "เต้นแล้ว"
        if name == "nod":
            robot.nod(_clamp_times(3, 1, 4))
            return "พยักหน้าแล้ว"
        if name == "shake_head":
            robot.shake_head(_clamp_times(2, 1, 5))
            return "ส่ายหัวแล้ว"
        if name == "head_tilt":
            side = 1 if args.get("side") == 1 else -1
            robot.head_tilt(side)
            return "เอียงหัวแล้ว"
        if name == "bow":
            robot.bow()
            return "โค้งคำนับแล้ว"
        if name == "happy":
            robot.happy()
            return "ทำท่าดีใจแล้ว"
        if name == "look_around":
            robot.look_around()
            return "มองไปรอบ ๆ แล้ว"
        if name == "turn":
            side = -1 if str(args.get("side", "right")).lower().startswith(("l", "ซ")) else 1
            robot.turn(side)
            return "หมุนลำตัวแล้ว"
        if name == "random_cute":
            robot.random_cute()
            return "ทำท่าทางน่ารักแล้ว"
        if name == "sing":
            from src.song import sing

            melody = args.get("melody") or "twinkle"
            sing(robot, melody=melody)
            return "ร้องเพลงแล้ว"
        return f"ไม่มีท่าทางชื่อ {name}"
    except Exception as exc:  # noqa: BLE001 — tool ต้องไม่ทำให้ loop ตาย
        return f"ทำท่า {name} ไม่สำเร็จ: {exc}"
