r"""ทดสอบการเชื่อมต่อ AI services (LLM + STT)

ตรวจว่า Ollama (LLM) และ STT server ภายนอก ใช้ได้ไหม — อ่านค่าจาก config
(รวม local_config.json ที่ชี้ไป GPU server)

วิธีใช้:
    .venv\Scripts\python.exe scripts\test_ai.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.robot_config import get_config  # noqa: E402
from src.llm import OllamaClient  # noqa: E402


def test_llm(cfg) -> bool:
    import time

    llm = cfg["llm"]
    print(f"[LLM] url   = {llm['url']}")
    print(f"[LLM] model = {llm['model']}")
    if not OllamaClient(url=llm["url"]).ping():
        print("  ❌ Ollama server ติดต่อไม่ได้ (เปิด: ollama serve บนเครื่องนั้น)")
        return False
    client = OllamaClient(
        url=llm["url"], model=llm["model"],
        system_prompt=llm.get("system_prompt"),
        temperature=llm.get("temperature", 0.7),
        timeout=llm.get("timeout", 120.0),
        num_predict=llm.get("num_predict"),
        max_history=llm.get("max_history"),
        think=llm.get("think", False),
        keep_alive=llm.get("keep_alive", "30m"),
    )
    models = client.list_models()
    print(f"  ✅ server พร้อม, มีโมเดล: {models}")
    if llm["model"] not in models:
        print(f"  ⚠️ ยังไม่มีโมเดล {llm['model']} — pull: ollama pull {llm['model']}")
        return False

    t0 = time.time()
    reply = client.chat([{"role": "user", "content": "ตอบแค่คำว่า ok"}])
    print(f"  ✅ ตอบได้ ({time.time()-t0:.1f}s): {reply[:60]!r}")

    # ทดสอบสตรีม (วัด first-token latency)
    t0 = time.time()
    first = None
    acc = []
    for chunk in client.chat_stream([{"role": "user", "content": "ตอบแค่คำว่า ok"}]):
        if first is None:
            first = time.time() - t0
        acc.append(chunk)
    joined = "".join(acc)
    print(f"  ✅ stream: first-token {first:.1f}s, total "
          f"{time.time()-t0:.1f}s -> {joined[:40]!r}")
    return True


def test_stt(cfg) -> bool:
    stt = cfg["stt"]
    stt_url = stt.get("stt_url")
    if not stt_url:
        print("[STT] ไม่ได้ตั้ง stt_url — จะใช้ whisper local (device="
              f"{stt.get('device')})")
        return True
    print(f"[STT] stt_url = {stt_url}")
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(stt_url.rstrip("/") + "/health",
                                    timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        print(f"  ✅ health: {data}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  ❌ ติดต่อ STT server ไม่ได้: {exc}")
        return False


def main():
    cfg = get_config()
    print("=" * 50)
    ok_llm = test_llm(cfg)
    print("=" * 50)
    ok_stt = test_stt(cfg)
    print("=" * 50)
    if ok_llm and ok_stt:
        print("✅ AI services พร้อมใช้งาน")
    else:
        print("⚠️ มี service ยังไม่พร้อม — ดูข้อความข้างบน")


if __name__ == "__main__":
    main()
