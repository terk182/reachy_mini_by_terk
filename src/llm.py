"""OllamaClient — คุยกับ LLM ผ่าน Ollama HTTP API (urllib มาตรฐาน ไม่มี dependency)

ต้องมี Ollama server รันอยู่ (ค่าเริ่มต้น http://localhost:11434)
ดู ai_assistant.md §6.1 — ย้าย server ไปเครื่อง GPU ได้โดยเปลี่ยน "url"
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Iterable, Iterator, List, Tuple, Union

Message = Union[dict, Tuple[str, str]]  # {"role":..,"content":..} หรือ (role, content)


class OllamaError(RuntimeError):
    """เกิดข้อผิดพลาดตอนคุยกับ Ollama (server ไม่เปิด / ตอบกลับแปลกๆ)"""


class OllamaClient:
    """HTTP client ไป Ollama: GET /api/tags, POST /api/chat"""

    def __init__(
        self,
        url: str = "http://localhost:11434",
        model: str = "gemma4:12b",
        system_prompt: str = "",
        temperature: float = 0.7,
        timeout: float = 120.0,
        max_history: int | None = None,
        think: bool = False,
        num_predict: int | None = None,
        keep_alive: str = "30m",
    ):
        self.url = url.rstrip("/")
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.timeout = timeout
        self.max_history = max_history
        self.think = think          # False = ไม่คิดในใจก่อนตอบ (ตอบเร็วขึ้นมาก)
        self.num_predict = num_predict  # จำกัดจำนวน token ที่สร้าง
        self.keep_alive = keep_alive  # ค้างโมเดลใน VRAM: "30m"/"-1" ตลอด (ห้าม 0 = unload ทันที)

    # ---------- HTTP ภายใน ----------
    def _request(self, path: str, payload: dict) -> dict:
        """POST JSON → dict"""
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise OllamaError(f"ติดต่อ Ollama ไม่ได้ ({self.url}): {e}") from e
        except json.JSONDecodeError as e:
            raise OllamaError("Ollama ตอบกลับไม่ใช่ JSON") from e

    def _get(self, path: str) -> dict:
        """GET → dict"""
        req = urllib.request.Request(f"{self.url}{path}", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise OllamaError(f"ติดต่อ Ollama ไม่ได้ ({self.url}): {e}") from e

    # ---------- API สาธารณะ ----------
    def ping(self) -> bool:
        """เช็คว่า Ollama server เปิดอยู่ไหม (True/False ไม่ throw)"""
        try:
            self._get("/api/tags")
            return True
        except OllamaError:
            return False

    def list_models(self) -> List[str]:
        """รายชื่อโมเดลทั้งหมดที่ Ollama มี (GET /api/tags)"""
        data = self._get("/api/tags")
        return [m.get("name", "") for m in data.get("models", [])]

    @staticmethod
    def _normalize_history(history: Iterable[Message]) -> List[dict]:
        """history ในรูป dict/tuple → list[dict] มาตรฐาน

        เก็บ field เพิ่มที่ function calling ต้องใช้: tool_calls (assistant), tool_name (tool)
        """
        messages: List[dict] = []
        for item in history or []:
            if isinstance(item, dict):
                msg = {
                    "role": item.get("role", "user"),
                    "content": item.get("content", ""),
                }
                if item.get("tool_calls"):
                    msg["tool_calls"] = item["tool_calls"]
                if item.get("tool_name"):
                    msg["tool_name"] = item["tool_name"]
                messages.append(msg)
            else:
                role, content = item
                messages.append({"role": role, "content": content})
        return messages

    def _build_messages(self, history: Iterable[Message], system_prompt: str | None = None) -> List[dict]:
        """สร้าง list messages: [system] + ประวัติ (ตัดตาม max_history)"""
        messages: List[dict] = []
        sp = self.system_prompt if system_prompt is None else system_prompt
        if sp:
            messages.append({"role": "system", "content": sp})
        history_msgs = self._normalize_history(history)
        # จำกัดประวัติที่ส่งต่อรอบ — prompt eval น้อยลง ตอบเร็วขึ้น
        if self.max_history is not None and len(history_msgs) > self.max_history:
            history_msgs = history_msgs[-self.max_history:]
        messages += history_msgs
        return messages

    def _options(self) -> dict:
        """options ที่ส่งไป Ollama (temperature + num_predict ถ้าตั้ง)"""
        options: dict = {"temperature": self.temperature}
        if self.num_predict is not None:
            options["num_predict"] = self.num_predict
        return options

    def chat(self, history: Iterable[Message] = (), system_prompt: str | None = None) -> str:
        """ส่งประวัติสนทนา → ข้อความตอบ (POST /api/chat, stream=False)

        history: list ของ {"role": "user"/"assistant", "content": ...}
                 หรือ tuple (role, content)
        """
        data = self._request("/api/chat", {
            "model": self.model,
            "messages": self._build_messages(history, system_prompt),
            "stream": False,
            "think": self.think,
            "keep_alive": self.keep_alive,
            "options": self._options(),
        })
        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as e:
            raise OllamaError(f"Ollama ตอบกลับไม่ครบถ้วน: {data}") from e

    def chat_tools(
        self,
        history: Iterable[Message] = (),
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> dict:
        """เหมือน chat() แต่เปิด function calling (Ollama tools)

        คืน message dict เต็ม (มี "content" และ/หรือ "tool_calls")
        — ผู้เรียกต้องดูว่าเป็น tool_calls แล้วป้อนผลลัพธ์กลับมาด้วย role="tool"
        """
        payload = {
            "model": self.model,
            "messages": self._build_messages(history, system_prompt),
            "stream": False,
            "think": self.think,
            "keep_alive": self.keep_alive,
            "options": self._options(),
        }
        if tools:
            payload["tools"] = tools
        data = self._request("/api/chat", payload)
        try:
            return data.get("message") or {}
        except (AttributeError, TypeError):
            return {}

    def chat_stream(self, history: Iterable[Message] = (), system_prompt: str | None = None) -> Iterator[str]:
        """เหมือน chat() แต่ yield ข้อความทีละ chunk (stream=True)

        ใช้สำหรับเริ่มพูด (TTS) ก่อนที่ LLM จะตอบจบ — ลดความรู้สึกช้าลงมาก

            for chunk in llm.chat_stream(history):
                print(chunk, end="")
        """
        payload = {
            "model": self.model,
            "messages": self._build_messages(history, system_prompt),
            "stream": True,
            "think": self.think,
            "keep_alive": self.keep_alive,
            "options": self._options(),
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    if data.get("done"):
                        break
                    chunk = (data.get("message") or {}).get("content", "")
                    if chunk:
                        yield chunk
        except urllib.error.URLError as e:
            raise OllamaError(f"ติดต่อ Ollama ไม่ได้ ({self.url}): {e}") from e
