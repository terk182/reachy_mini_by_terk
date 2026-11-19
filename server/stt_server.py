r"""STT server — faster-whisper large-v3 (รับ WAV int16 mono 16kHz → คืนข้อความ)

รันบนเครื่อง GPU (192.168.1.155) เพื่อรับงาน Speech-to-Text จากเครื่องหุ่น

Endpoint:
    GET  /health      -> {"ok": true, "model": "large-v3", "device": "cpu"}
    POST /transcribe  -> body = WAV (int16 mono 16kHz)  → {"text": "..."}

⚠️ ปัญหาที่เจอ (2026-08-17): RTX 5060 (Blackwell) + ctranslate2 รุ่นเก่า
   → โหลดโมเดลบน CUDA ได้ (/health บอก cuda) แต่ decode เสียงพูดจริง "ค้าง" ไม่ตอบ
   (sine/silence ผ่านเพราะไม่มี token ให้ decode)

ทางแก้ (เรียงตามที่ควรลอง):
   1) pip install --upgrade ctranslate2   # รองรับ Blackwell (sm_120)
   2) ถ้ายังค้าง: ลด compute_type เป็น int8 แทน float16
   3) กันเหนียว: server ตัวนี้ probe ก่อน — ถ้า CUDA decode ค้าง/พัง จะ fallback CPU อัตโนมัติ

วิธีรัน:
    pip install faster-whisper numpy
    .venv\Scripts\python.exe stt_server.py
"""
import io
import json
import os
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

MODEL_NAME = os.environ.get("STT_MODEL", "large-v3")
PORT = int(os.environ.get("STT_PORT", "8000"))
LANGUAGE = os.environ.get("STT_LANGUAGE", "th")
# คำเฉพาะของโปรเจกต์ — ช่วยให้ whisper สะกดถูก (เช่น "รีชชี่" ที่เคยถอดเป็น ริชิต/ลิเศษ)
# hotwords ต้องใช้ faster-whisper >= 1.0 (ถ้าเก่ากว่า โค้ดมี fallback ให้)
# ⚠️ เครื่องที่ deploy แล้ว: ตั้ง env STT_HOTWORDS="พี่ทด น้องนุ" แล้วรีสตาร์ทด้วย
HOTWORDS = os.environ.get("STT_HOTWORDS", "พี่ทด น้องนุ")

_model = None
_device = "cpu"


def _load_with_probe(model_name: str):
    """โหลด faster-whisper: ลอง CUDA ก่อน แล้ว probe decode จริง
    ถ้า decode ค้าง/พัง -> fallback CPU"""
    from faster_whisper import WhisperModel

    for device, compute in (("cuda", "float16"), ("cuda", "int8"), ("cpu", "int8")):
        try:
            print(f"[STT] โหลด {model_name} (device={device}, compute={compute}) ...")
            model = WhisperModel(model_name, device=device, compute_type=compute)
            print(f"[STT] probe decode (device={device}) ...")
            if _probe_decode(model):
                print(f"[STT] ✓ ใช้ {device}/{compute}")
                return model, device
            print(f"[STT] ✗ decode ค้าง/พังบน {device} -> ลองถัดไป")
        except Exception as exc:  # noqa: BLE001
            print(f"[STT] {device} โหลด/รันไม่ได้ ({exc}) -> ลองถัดไป")
    raise RuntimeError(f"โหลด {model_name} ไม่สำเร็จในทุก device")


def _probe_decode(model, timeout: float = 25.0) -> bool:
    """ทดสอบ decode จริงด้วยเสียง noise 1 วิ (มี token → ต้องเข้า decode จริง)"""
    audio = (np.random.default_rng(0).standard_normal(16000) * 0.1).astype(np.float32)
    ok = threading.Event()

    def run():
        try:
            segments, _info = model.transcribe(audio, language=LANGUAGE, beam_size=1)
            for _ in segments:  # กระตุ้น decode จริง
                pass
            ok.set()
        except Exception:  # noqa: BLE001
            pass

    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(timeout)
    return ok.is_set()


def get_model():
    global _model, _device
    if _model is None:
        _model, _device = _load_with_probe(MODEL_NAME)
    return _model, _device


def _read_wav(data: bytes):
    """อ่าน WAV bytes -> (audio float32, samplerate)"""
    with wave.open(io.BytesIO(data), "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        pcm = np.frombuffer(w.readframes(n), dtype=np.int16)
    audio = pcm.astype(np.float32) / 32768.0
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio, sr


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            model, device = get_model()
            self._send(200, {"ok": True, "model": MODEL_NAME, "device": device})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/transcribe":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            audio, sr = _read_wav(self.rfile.read(length))
            if sr != 16000:
                # resample แบบง่าย (linear) — ปกติ client ส่ง 16k อยู่แล้ว
                from numpy import interp
                x_old = np.linspace(0, 1, num=len(audio))
                x_new = np.linspace(0, 1, num=int(len(audio) * 16000 / sr))
                audio = interp(x_new, x_old, audio)
            model, _device = get_model()
            # condition_on_previous_text=False: ลดอาการพูดวนซ้ำ ("โอเค โอเค โอเค")
            # hotwords: บังคับคำศัพท์เฉพาะ (ชื่อหุ่น) — ช่วยมากกับคลิปสั้น
            kwargs = {"condition_on_previous_text": False}
            if HOTWORDS:
                kwargs["hotwords"] = HOTWORDS
            try:
                segments, _info = model.transcribe(
                    audio, language=LANGUAGE, beam_size=5, **kwargs)
            except TypeError:
                # faster-whisper เก่าไม่รู้จัก hotwords → ถอดแบบเดิม
                print("[STT] hotwords ไม่รองรับใน faster-whisper นี้ — ถอดแบบปกติ")
                segments, _info = model.transcribe(
                    audio, language=LANGUAGE, beam_size=5,
                    condition_on_previous_text=False)
            text = "".join(seg.text for seg in segments).strip()
            self._send(200, {"text": text})
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, fmt, *args):  # เงียบ log ให้อ่านง่าย
        pass


if __name__ == "__main__":
    t0 = time.time()
    model, device = get_model()
    print(f"[STT] พร้อม model={MODEL_NAME} device={device} ({time.time()-t0:.1f}s)")
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[STT] listening :{PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[STT] ปิด")
