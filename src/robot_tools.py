"""Function calling — ให้ LLM สั่งท่าทางหุ่นเองได้ (Ollama tools format)

LLM (gemma4) ตัดสินใจเองว่าเมื่อไหร่ควรโบกมือ/เต้น/พยักหน้า แล้วเรียก tool
ที่นี่มี 2 ส่วน:
  TOOLS   — นิยาม tool ส่งให้ Ollama (OpenAI-compatible)
  execute — แปลง tool call → เรียกเมธอดใน Robot จริง
"""

from __future__ import annotations

import json
import re

_TOOL_NAMES: set[str] = set()   # เติมหลังนิยาม TOOLS ด้านล่าง

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
    {
        "type": "function",
        "function": {
            "name": "play_music",
            "description": (
                "เปิดเพลงจากเครื่อง (โฟลเดอร์ media/music) — ใช้เมื่อผู้ใช้ขอให้เปิดเพลง "
                "เช่น 'เปิดเพลงเขาคือพี่แอ็ดของคาราบาว'. ถ้าไม่เจอไฟล์จะบอกว่าต้องวางไฟล์ที่ไหน"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "ชื่อเพลง หรือ ศิลปิน เช่น 'เขาคือพี่แอ็ด คาราบาว'",
                    },
                    "dance": {
                        "type": "boolean",
                        "description": "เต้นตามจังหวะเพลงด้วยหรือไม่ (default true)",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["together", "alternate", "canon", "mirror", "free", "show"],
                        "description": (
                            "แบบการเต้นของหุ่น 2 ตัว: together=เต้นพร้อมกัน, "
                            "alternate=ผลัดกันเต้น, canon=เหลื่อมจังหวะ (ตัวที่ 2 ช้ากว่า 1 จังหวะ), "
                            "mirror=กระจกเงา, free=ต่างคนต่างเต้น/ไม่พร้อมกัน, "
                            "show=โชว์วนทุกแบบ (default together)"
                        ),
                    },
                    "style": {
                        "type": "string",
                        "enum": ["auto", "hype", "inner"],
                        "description": (
                            "อารมณ์การเต้น: auto=ตามความดังเพลง (เบาก็อินเนอร์ ดังก็มันส์), "
                            "hype=ตื่นเต้นจัดเต็มตลอด, inner=อินเนอร์ ซึ้ง ๆ โยกช้า (default auto)"
                        ),
                    },
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "play_youtube",
            "description": (
                "เปิดเพลง/วิดีโอบน YouTube ผ่าน browser แล้วหุ่นเต้นตามจังหวะเพลงจริง "
                "จนกว่าจะสั่ง stop_music — ใช้เมื่อผู้ใช้บอกชื่อเพลง/ศิลปิน หรือส่งลิงก์ "
                "YouTube มาให้ เช่น 'เปิด https://youtu.be/xxx แล้วเต้นผลัดกัน'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "ชื่อเพลง/ศิลปิน หรือลิงก์ YouTube หรือ video id",
                    },
                    "dance": {
                        "type": "boolean",
                        "description": "เต้นตามจังหวะเพลงด้วยหรือไม่ (default true)",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["together", "alternate", "canon", "mirror", "free", "show"],
                        "description": (
                            "แบบการเต้นของหุ่น 2 ตัว: together=เต้นพร้อมกัน, "
                            "alternate=ผลัดกันเต้น, canon=เหลื่อมจังหวะ (ตัวที่ 2 ช้ากว่า 1 จังหวะ), "
                            "mirror=กระจกเงา, free=ต่างคนต่างเต้น/ไม่พร้อมกัน, "
                            "show=โชว์วนทุกแบบ (default together)"
                        ),
                    },
                    "style": {
                        "type": "string",
                        "enum": ["auto", "hype", "inner"],
                        "description": (
                            "อารมณ์การเต้น: auto=ตามความดังเพลง (เบาก็อินเนอร์ ดังก็มันส์), "
                            "hype=ตื่นเต้นจัดเต็มตลอด, inner=อินเนอร์ ซึ้ง ๆ โยกช้า (default auto)"
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_music",
            "description": "หยุดเพลงที่กำลังเล่นอยู่ (รวม YouTube) และหยุดเต้น",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_dance_mode",
            "description": (
                "เปลี่ยนแบบ/อารมณ์การเต้นระหว่างที่เพลงเล่นอยู่ เช่น 'เปลี่ยนเป็นผลัดกันเต้น' "
                "'เต้นไม่พร้อมกัน' 'เต้นให้ตื่นเต้นกว่านี้' 'อินเนอร์หน่อย' "
                "— ถ้ายังไม่ได้เต้นจะเริ่มเต้นตามเสียงที่ได้ยิน"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["together", "alternate", "canon", "mirror", "free", "show"],
                        "description": (
                            "แบบการเต้นของหุ่น 2 ตัว: together=เต้นพร้อมกัน, "
                            "alternate=ผลัดกันเต้น, canon=เหลื่อมจังหวะ (ตัวที่ 2 ช้ากว่า 1 จังหวะ), "
                            "mirror=กระจกเงา, free=ต่างคนต่างเต้น/ไม่พร้อมกัน, "
                            "show=โชว์วนทุกแบบ (default together)"
                        ),
                    },
                    "style": {
                        "type": "string",
                        "enum": ["auto", "hype", "inner"],
                        "description": (
                            "อารมณ์การเต้น: auto=ตามความดังเพลง (เบาก็อินเนอร์ ดังก็มันส์), "
                            "hype=ตื่นเต้นจัดเต็มตลอด, inner=อินเนอร์ ซึ้ง ๆ โยกช้า (default auto)"
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sway",
            "description": "ส่ายเอว/โยกตัวซ้ายขวานุ่ม ๆ ช้า ๆ",
            "parameters": {
                "type": "object",
                "properties": {
                    "times": {"type": "integer", "description": "จำนวนรอบ 1-4 (default 3)"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "excited",
            "description": "ตื่นเต้น — ตัวสั่นเล็กน้อยเร็ว ๆ + กระพือเสา",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stretch",
            "description": "ยืดตัว — ยกตัวสูง กางเสา แล้วย่อลง",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sleep",
            "description": "ท่าหลับ — ก้มหัว เสาหุบ ค้างสักพัก แล้วตื่น",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lean",
            "description": "โน้มตัวไปข้างหน้า-ถอยหลัง",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cheer",
            "description": "เชียร์/ไชโย — ชูเสาขึ้นเด้งตัว",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "headbang",
            "description": "ร็อค/เฮดแบง — โหม่งหัวขึ้นลงเร็ว ๆ แบบเมทัล",
            "parameters": {
                "type": "object",
                "properties": {
                    "times": {"type": "integer", "description": "จำนวนรอบ 2-12 (default 8)"}
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


_TOOL_NAMES = {t["function"]["name"] for t in TOOLS}


def as_text_tool_call(content) -> tuple[str, dict] | None:
    """โมเดลเล็กบางตัวตอบ "ชื่อ tool" เป็นข้อความแทน tool_call — แกะให้เป็น (name, args)

    รองรับ:  "stop_music" · "stop_music()" · 'play_youtube {"query": "..."}'
    คืน None ถ้าไม่ใช่ชื่อ tool ที่รู้จัก
    """
    text = (content or "").strip().strip("` \n\"'")
    if not text:
        return None
    if text in _TOOL_NAMES:
        return text, {}
    m = re.match(r"^([a-zA-Z_]+)\s*\(?\s*(\{.*\})?\s*\)?$", text, re.S)
    if not m or m.group(1) not in _TOOL_NAMES:
        return None
    return m.group(1), _parse_args(m.group(2) or "")


def _start_music_dance(robot, partner, mode, style=None) -> str:
    """เริ่มเต้นตามจังหวะเพลง (หุ่นหลัก + หุ่นคู่ถ้ามี) — คืนข้อความสั้น ๆ"""
    from src import dance_sync

    robots = [r for r in (robot, partner) if r is not None]
    names = []
    for i, r in enumerate(robots):
        cfg = getattr(r, "config", {}) or {}
        sec = "robot" if i == 0 else "robot_b"
        names.append((cfg.get(sec) or {}).get("name") or ("พี่ทด", "น้องนุ")[min(i, 1)])
    ctl = dance_sync.start_dance(robots, mode=mode, names=names, style=style)
    feel = dance_sync.STYLE_TH[ctl.style]
    if len(robots) == 1:
        return f"เต้นตามจังหวะเพลงอยู่ ({feel})"
    return f"ทั้งสองตัวเต้นแบบ{dance_sync.MODE_TH[ctl.mode]} ({feel})"


def execute(robot, name: str, arguments=None, partner=None) -> str:
    """เรียกท่าทางบน robot ตาม tool call → คืนข้อความผลลัพธ์ (ภาษาไทยสั้น ๆ)

    partner: หุ่นตัวที่ 2 (โหมดหุ่นคู่) — ใช้กับการเต้นตามเพลง
    """
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
        if name == "play_music":
            from src import music

            title = str(args.get("title") or args.get("query") or "").strip()
            ok, msg = music.play_async(title)
            if not ok:
                # ไม่มีไฟล์ → ถ้าเป็นเพลงที่มีเมโลดี้ในเครื่อง (twinkle/chang/...) ให้ร้องแทน
                try:
                    from src.song import MELODIES, sing

                    low = title.lower()
                    match = next((m for m in MELODIES
                                  if m.lower() in low or low in m.lower()), None)
                    if match:
                        sing(robot, melody=match)
                        return f"ไม่พบไฟล์เพลง {title} — ร้องเมโลดี้ '{match}' ให้แทน"
                except Exception:  # noqa: BLE001 — ร้องไม่ได้ก็รายงานตามจริง
                    pass
                return msg
            if args.get("dance", True) is not False:
                try:
                    msg += " · " + _start_music_dance(robot, partner, args.get("mode"), args.get("style"))
                except Exception as exc:  # noqa: BLE001 — เต้นไม่ได้ เพลงยังเล่น
                    msg += f" (เต้นไม่ได้: {exc})"
            return msg
        if name == "stop_music":
            from src import music

            from src import dance_sync

            music.stop()
            paused = music.pause_youtube()
            danced = dance_sync.stop_dance()
            extra = " · หยุด YouTube" if paused else ""
            extra += " · หยุดเต้น" if danced else ""
            return "หยุดเพลงแล้ว" + extra
        if name == "set_dance_mode":
            from src import dance_sync

            ctl = dance_sync.current()
            if ctl is None:
                return "เริ่มเต้นตามเสียงที่ได้ยิน · " + _start_music_dance(
                    robot, partner, args.get("mode") or "together", args.get("style"))
            parts = []
            if args.get("mode"):
                parts.append("แบบ" + dance_sync.MODE_TH[ctl.set_mode(args["mode"])])
            if args.get("style"):
                parts.append(dance_sync.STYLE_TH[ctl.set_style(args["style"])])
            return ("เปลี่ยนเป็นเต้น" + " ".join(parts) + "แล้ว") if parts else "เต้นอยู่แล้วจ้า"
        if name == "play_youtube":
            from src import music

            query = str(args.get("query") or args.get("title") or "").strip()
            ok, msg = music.open_youtube(query)
            if ok and args.get("dance", True) is not False:
                try:
                    msg += " · " + _start_music_dance(robot, partner, args.get("mode"), args.get("style"))
                except Exception as exc:  # noqa: BLE001
                    msg += f" (เต้นไม่ได้: {exc})"
            return msg
        if name == "sway":
            robot.sway(_clamp_times(3, 1, 4))
            return "ส่ายเอวแล้ว"
        if name == "excited":
            robot.excited()
            return "ตื่นเต้นแล้ว"
        if name == "stretch":
            robot.stretch()
            return "ยืดตัวแล้ว"
        if name == "sleep":
            robot.sleep_pose()
            return "หลับไปแป๊บ แล้วตื่นแล้ว"
        if name == "lean":
            robot.lean()
            return "โน้มตัวแล้ว"
        if name == "cheer":
            robot.cheer()
            return "เชียร์แล้ว ไชโย!"
        if name == "headbang":
            robot.headbang(_clamp_times(8, 2, 12))
            return "จัดไป! เฮดแบงแล้ว"
        return f"ไม่มีท่าทางชื่อ {name}"
    except Exception as exc:  # noqa: BLE001 — tool ต้องไม่ทำให้ loop ตาย
        return f"ทำท่า {name} ไม่สำเร็จ: {exc}"
