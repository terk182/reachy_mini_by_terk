"""สองหุ่นปรึกษากันก่อนตอบ (Two-robot consult)

ลำดับการทำงาน:
  1) หุ่น A ร่างคำตอบ (ยังไม่พูด — ใน GUI ใช้ LLM หลักที่มี tool calling)
  2) หุ่น B (persona คนละชุด system prompt) อ่าน [คำถาม + ร่างของ A]
     → เขียน "ข้อเสริม" 1-2 ประโยค (ห้ามซ้ำร่าง)
  3) ผู้เรียกนำไปใช้ต่อ: A พูดคำตอบ → B พูดข้อเสริม (ผลัดกัน)

ใช้ร่วมกับ scripts/app_gui.py (โหมด --robot-b) หรือทดสอบเดี่ยวด้วย
scripts/two_robot_consult_test.py
"""

from __future__ import annotations

from dataclasses import dataclass

from src.llm import OllamaClient


@dataclass
class ConsultResult:
    """ผลการปรึกษา: ร่างคำตอบของ A + ข้อเสริมของ B (ยังมีแท็กอารมณ์อยู่)"""

    a_draft: str
    b_note: str


def _plain_history(history, limit: int = 6) -> list[dict]:
    """กรองเฉพาะ user/assistant (ตัด tool messages ที่ client B ไม่เข้าใจ)"""
    out: list[dict] = []
    for msg in history or []:
        role = msg.get("role")
        if role in ("user", "assistant"):
            out.append({"role": role, "content": msg.get("content", "")})
    return out[-limit:]


class TwoRobotConsultant:
    """ประสานการ 'ปรึกษากัน' ระหว่าง LLM สอง persona (A = หุ่นหลัก, B = หุ่นคู่)"""

    def __init__(self, llm_a: OllamaClient, llm_b: OllamaClient,
                 name_a: str = "พี่ทด", name_b: str = "น้องนุ"):
        self.llm_a = llm_a
        self.llm_b = llm_b
        self.name_a = name_a
        self.name_b = name_b

    # ---------- โหมด CLI/ทดสอบ (A ร่างเอง ไม่มี tool) ----------
    def consult(self, user_text: str, history=None) -> ConsultResult:
        msgs = _plain_history(history) + [{"role": "user", "content": user_text}]
        a_draft = (self.llm_a.chat(msgs) or "").strip()
        b_note = self.review(user_text, a_draft, history)
        return ConsultResult(a_draft=a_draft, b_note=b_note)

    # ---------- โหมด GUI (A ตอบแล้ว → B เสริมก่อนใครพูด) ----------
    def review(self, user_text: str, a_answer: str, history=None) -> str:
        """ให้ B อ่าน [คำถาม + คำตอบของ A] แล้วเขียนข้อเสริมสั้น ๆ

        คืนข้อความของ B (ยังมีแท็กอารมณ์) — ผู้เรียกใช้ detect_emotion/strip ต่อ
        """
        prompt = (
            f"คำถามของผู้ใช้: {str(user_text).strip()}\n\n"
            f"คำตอบของ{self.name_a}: {str(a_answer).strip()}\n\n"
            f"จงเขียนข้อเสริมของ{self.name_b} 1-2 ประโยค "
            "(ข้อมูลเพิ่ม/คำแนะนำ/ความคิดเห็นที่เป็นประโยชน์) "
            "ห้ามทวนซ้ำคำตอบเดิม แล้วปิดท้ายด้วยแท็กอารมณ์ในวงเล็บ "
            "เลือกจาก (happy) (sad) (angry) (surprised) (neutral)"
        )
        msgs = _plain_history(history, limit=4) + [{"role": "user", "content": prompt}]
        return (self.llm_b.chat(msgs) or "").strip()
