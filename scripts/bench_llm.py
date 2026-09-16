"""วัดความเร็ว LLM — เทียบกับค่าที่เคยบันทึกไว้ (ดู /memories/repo/debugging.md)

ตัวเลขในอดีต (ประโยคไทยคุยจริง):
  - gemma4:12b + prompt บีบ = 4.5-5.1s (ก่อนปรับ 11-20s)
  - qwen3.5:4b (2026-08-19) = 0.7-1.3s

วิธีใช้:
    .venv\\Scripts\\python.exe scripts\\bench_llm.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.robot_config import get_config  # noqa: E402
from src.llm import OllamaClient  # noqa: E402
from src.robot_tools import TOOLS  # noqa: E402

# ประโยคไทยแบบที่ใช้คุยจริง (ไม่ใช่ "say ok" ที่สั้นเกินไปจนไม่สะท้อนความจริง)
QUESTIONS = [
    "สวัสดีครับ แนะนำตัวสั้นๆ หน่อย",
    "วันนี้มีอะไรน่าสนุกบ้าง",
    "ช่วยบอกวิธีปลูกต้นไม้ให้ฟังหน่อย",
]

TOOL_QUESTION = "เต้นให้หน่อย"   # เส้นทางเดียวกับ voice_assistant (function calling)


def make_client() -> OllamaClient:
    """สร้าง client ด้วยค่า config ชุดเดียวกับ voice_assistant"""
    llm = get_config()["llm"]
    return OllamaClient(
        url=llm["url"], model=llm["model"],
        api_key=llm.get("api_key"),
        system_prompt=llm.get("system_prompt"),
        temperature=llm.get("temperature", 0.7),
        timeout=llm.get("timeout", 120.0),
        num_predict=llm.get("num_predict"),
        max_history=llm.get("max_history"),
        think=llm.get("think", False),
        keep_alive=llm.get("keep_alive", "30m"),
    )


def bench_chat(client: OllamaClient, question: str) -> float:
    """ถาม 1 ครั้ง (non-stream) → คืนเวลาที่ใช้ + พิมพ์ token/ความเร็ว"""
    # ใช้ _request ตรงๆ เพราะต้องได้ eval_count/eval_duration (chat() คืนแค่ข้อความ)
    t0 = time.time()
    data = client._request("/api/chat", {
        "model": client.model,
        "messages": client._build_messages([{"role": "user", "content": question}]),
        "stream": False,
        "think": client.think,
        "keep_alive": client.keep_alive,
        "options": client._options(),
    })
    dt = time.time() - t0
    content = (data.get("message") or {}).get("content", "")
    n = data.get("eval_count", 0)
    dur = data.get("eval_duration", 0) / 1e9  # ns → s
    rate = n / dur if dur > 0 else 0.0
    print(f"  {dt:5.2f}s | {n:3d} tok | {rate:4.0f} tok/s | {content.replace(chr(10), ' ')[:44]!r}")
    return dt


def bench_stream(client: OllamaClient, question: str) -> tuple[float, float]:
    """ถามแบบ stream → คืน (เวลาถึง token แรก, เวลาจบ)"""
    t0 = time.time()
    first = None
    for _ in client.chat_stream([{"role": "user", "content": question}]):
        if first is None:
            first = time.time() - t0
    return first or 0.0, time.time() - t0


def bench_tools(client: OllamaClient, question: str) -> float:
    """ถามแบบเปิด function calling (แบบที่ voice_assistant ทำ) → คืนเวลา"""
    t0 = time.time()
    msg = client.chat_tools([{"role": "user", "content": question}], tools=TOOLS)
    dt = time.time() - t0
    calls = [c.get("function", {}).get("name") for c in msg.get("tool_calls") or []]
    print(f"  {dt:5.2f}s | tool_calls={calls} | {(msg.get('content') or '')[:40]!r}")
    return dt


def main():
    client = make_client()
    print(f"model = {client.model} | url = {client.url}")
    if not client.ping():
        print("❌ LLM server ไม่พร้อม")
        return

    # warm-up: ครั้งแรกต้องโหลดโมเดลเข้า VRAM (5-7s) — ไม่นับเป็นความเร็วตอบจริง
    t0 = time.time()
    client.chat([{"role": "user", "content": "สวัสดี"}])
    print(f"warm-up (โหลดโมเดล) = {time.time() - t0:.2f}s\n")

    print("[chat] เวลาตอบเต็ม (non-stream):")
    times = [bench_chat(client, q) for q in QUESTIONS]
    print(f"  → เฉลี่ย {sum(times) / len(times):.2f}s (ต่ำสุด {min(times):.2f}s)\n")

    print("[stream] เวลาถึง token แรก (เริ่มพูดได้เร็วแค่ไหน):")
    for q in QUESTIONS[:2]:
        first, total = bench_stream(client, q)
        print(f"  first-token {first:.2f}s | จบ {total:.2f}s")

    print("\n[tools] function calling (แบบ voice_assistant):")
    bench_tools(client, TOOL_QUESTION)


if __name__ == "__main__":
    main()
