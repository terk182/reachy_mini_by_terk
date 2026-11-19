# -*- coding: utf-8 -*-
"""ทดสอบ tool calling เรื่องเพลงแบบ end-to-end (LLM จริง → เรียก tool → ทำจริง)

    .venv\\Scripts\\python.exe scripts\\test_music_tool.py
    .venv\\Scripts\\python\\python.exe scripts\\test_music_tool.py "เปิดเพลงช้างในยูทูปหน่อย"
    .venv\\Scripts\\python.exe scripts\\test_music_tool.py --no-exec   # ดูแค่ว่า LLM เลือก tool อะไร
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.robot_config import get_config  # noqa: E402
from src.llm import OllamaClient  # noqa: E402
from src.robot import Robot  # noqa: E402
from src.robot_tools import TOOLS, execute  # noqa: E402
from src.robot_tools import as_text_tool_call  # noqa: E402

MUSIC_TOOLS = {"play_music", "play_youtube", "stop_music", "sing", "set_dance_mode"}


def main():
    ap = argparse.ArgumentParser(description="ทดสอบ tool calling เพลง")
    ap.add_argument("question", nargs="?",
                    default="เปิดเพลงเขาคือพี่แอ็ดของคาราบาวใน YouTube ให้หน่อย")
    ap.add_argument("--no-exec", action="store_true", help="ไม่ต้องรัน tool จริง")
    args = ap.parse_args()

    cfg = get_config()
    llm_cfg = cfg["llm"]
    llm = OllamaClient(
        url=llm_cfg["url"], model=llm_cfg["model"], api_key=llm_cfg.get("api_key"),
        system_prompt=llm_cfg.get("system_prompt"),
        temperature=llm_cfg.get("temperature", 0.7),
        timeout=llm_cfg.get("timeout", 25.0),
        num_predict=llm_cfg.get("num_predict"),
        max_history=llm_cfg.get("max_history"),
        think=llm_cfg.get("think", False),
        keep_alive=llm_cfg.get("keep_alive", "m"),
    )

    print(f"❓ {args.question}")
    history = [{"role": "user", "content": args.question}]
    msg = llm.chat_tools(history, TOOLS, system_prompt=llm_cfg.get("system_prompt"))
    calls = msg.get("tool_calls") or []
    if not calls:
        parsed = as_text_tool_call(msg.get("content"))
        if parsed:
            name, targs = parsed
            print(f"   (แกะ tool จากข้อความ: {name})")
            calls = [{"function": {"name": name, "arguments": targs}}]
            msg["tool_calls"] = calls
            msg["content"] = ""
    names = [(c.get("function") or {}).get("name") for c in calls]
    print(f"🧠 LLM เลือก tool: {names or '(ไม่มี — ตอบเป็นข้อความ)'}")
    if not calls:
        print(f"   ข้อความ: {(msg.get('content') or '').strip()}")
        return 0

    robot = Robot(backend="sim")
    try:
        for c in calls:
            fn = c.get("function") or {}
            name = fn.get("name", "")
            if name not in MUSIC_TOOLS:
                print(f"⚠️ {name} ไม่ใช่ tool เพลง — ข้าม")
                continue
            if args.no_exec:
                print(f"   {name} args={fn.get('arguments')} (ไม่รันจริง)")
                continue
            result = execute(robot, name, fn.get("arguments", {}))
            print(f"   ▶ {name} -> {result}")
            history.append(msg)
            history.append({"role": "tool", "tool_name": name, "content": result})

        if not args.no_exec and len(history) > 1:
            final = llm.chat_tools(history, None, system_prompt=llm_cfg.get("system_prompt"))
            print(f"💬 ตอบกลับ: {(final.get('content') or '').strip()}")
    finally:
        robot.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
