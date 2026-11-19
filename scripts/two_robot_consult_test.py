"""ทดสอบการปรึกษากันของหุ่นคู่ (LLM จริง — ไม่ต้องมีหุ่น)

วิธีใช้:
    .venv\\Scripts\\python.exe scripts\\two_robot_consult_test.py
    .venv\\Scripts\\python.exe scripts\\two_robot_consult_test.py "คำถามของคุณ"
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.robot_config import get_config  # noqa: E402
from src.dual_llm import TwoRobotConsultant  # noqa: E402
from src.expressions import detect_emotion, strip_emotion_tag  # noqa: E402
from src.llm import OllamaClient  # noqa: E402


def _client(cfg, model, system_prompt, temperature, num_predict=None):
    llm = cfg["llm"]
    return OllamaClient(
        url=llm["url"], model=model, api_key=llm.get("api_key"),
        system_prompt=system_prompt, temperature=temperature,
        timeout=llm.get("timeout", 25.0), num_predict=num_predict,
        max_history=llm.get("max_history"), think=llm.get("think", False),
        keep_alive=llm.get("keep_alive", "m"),
    )


def main():
    question = (sys.argv[1] if len(sys.argv) > 1
                else "พี่ทดกับน้องนุช่วยแนะนำเมนูอาหารเช้าที่ทำง่าย ๆ ให้หน่อย")
    cfg = get_config()
    bcfg = cfg.get("robot_b", {})
    bllm = bcfg.get("llm", {})
    a_name = (cfg.get("robot") or {}).get("name", "พี่ทด")
    b_name = bcfg.get("name", "น้องนุ")

    llm_a = _client(cfg, cfg["llm"]["model"], cfg["llm"].get("system_prompt"),
                    cfg["llm"].get("temperature", 0.7),
                    cfg["llm"].get("num_predict"))
    llm_b = _client(cfg, bllm.get("model") or cfg["llm"]["model"],
                    bcfg.get("system_prompt"), bllm.get("temperature", 0.6),
                    bllm.get("num_predict", 160))

    print(f"❓ {question}\n")
    t0 = time.time()
    res = TwoRobotConsultant(llm_a, llm_b, name_a=a_name,
                             name_b=b_name).consult(question)
    dt = time.time() - t0

    a_text = strip_emotion_tag(res.a_draft).strip()
    b_text = strip_emotion_tag(res.b_note).strip()
    print(f"🐰 {a_name} (ร่าง) [อารมณ์: {detect_emotion(res.a_draft)}]")
    print(f"   {a_text}\n")
    print(f"🤖 {b_name} (เสริม) [อารมณ์: {detect_emotion(res.b_note)}]")
    print(f"   {b_text}\n")
    print(f"✅ consult OK — รวม {dt:.1f}s (2 LLM calls)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
