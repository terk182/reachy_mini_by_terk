"""STT — ฟังเสียงจากไมค์แล้วแปลงเป็นข้อความ (faster-whisper)

สองโหมด:
1. local  : รัน whisper ในเครื่องนี้ (device="auto" = ลอง cuda ก่อน ตก cpu อัตโนมัติ)
2. remote : ส่ง WAV ไปเครื่อง GPU ผ่าน stt_url (เช่น http://<IP_GPU>:8000)

protocol remote (ตาม ai_assistant.md §6.2):
    POST {stt_url}/transcribe   body = WAV bytes (Content-Type: audio/wav)
    ตอบ: JSON {"text": "..."} หรือข้อความล้วน
"""
from __future__ import annotations

import io
import json
import threading
import time
import urllib.error
import urllib.request
import wave
from collections import deque
from typing import List, Optional, Tuple

import numpy as np

# keyword ไมค์ USB cam — ใช้ auto-detect ตาม ai_assistant.md
# ⚠️ "desktop microphone" ต้องมาก่อน "lifecam": MME entry ของ LifeCam (index 1)
# มีชื่อตัด 31 ตัวอักษรไม่มีคำว่า "LifeCam" แต่ให้เสียงดังชัด
# ส่วน DirectSound entry (index 6) มีคำว่า "LifeCam" แต่เงียบมาก (bug ที่เคยเจอ)
_MIC_KEYWORDS: Tuple[str, ...] = ("desktop microphone", "lifecam", "camera", "webcam", "cam")

# RMS ต่ำกว่านี้ถือว่าเงียบ (ไม่ส่งไป whisper ประหยัดเวลา)
_SILENCE_RMS = 0.004

_model = None        # cache WhisperModel — โหลดครั้งเดียว อย่าโหลดใหม่ทุกรอบ
_model_key: tuple = ()

# ประโยคทีวีที่ whisper ชอบ "เดา" เมื่อเสียงเบา/ไม่ชัด (เจอจริงคืน 16/9: ×10 ครั้ง)
_HALLUCINATIONS = ("โปรดติดตามตอนต่อไป", "ขอบคุณที่รับชม", "ขอบคุณครับที่รับชม")


def looks_like_hallucination(text: str, clip_rms: float) -> bool:
    """เสียงเบา + ถอดได้วลีทีวี = น่าจะ hallucination ไม่ใช่คำพูดจริง

    เคสจริง 1: คลิปเงียบ ๆ (rms 0.034) → whisper เดา "โปรดติดตามตอนต่อไป"
    เคสจริง 2 (2026-09-17 01:13): คลิป 1.9s เสียงรบกวนต่อเนื่อง — เกตเดิมเช็ค rms
      *หลัง normalize* (ขยายทุกคลิปให้ peak=0.6) → คลิปนี้กลายเป็น 0.106 แล้วหลุด
      → แก้: (ก) ถ้า *ทั้ง utterance* คือวลีทีวีเป๊ะ ๆ (ไม่มีคำอื่น) ตัดทิ้งทันที
        ไม่ว่าดังแค่ไหน และ (ข) ผู้เรียกต้องส่ง rms ของ "คลิปดิบ" ก่อน normalize
    """
    t = (text or "").replace(" ", "").strip("!?….")
    if not t:
        return False
    phrases = [h.replace(" ", "") for h in _HALLUCINATIONS]
    if t in phrases:        # ทั้งประโยคคือวลีทีวีเป๊ะ ๆ — ไม่ใช่คำสั่งผู้ใช้แน่นอน
        return True
    if clip_rms > 0.06:     # ดังพอ = อาจพูดจริง (ยอมให้ผ่านบ้าง)
        return False
    return any(h in t for h in phrases)


# ---------------- ไมค์ ----------------
def list_mics(only_microphones: bool = True) -> List[Tuple[int, str]]:
    """รายชื่อ input device: [(index, ชื่อ), ...]

    only_microphones=True (ค่าเริ่มต้น) — แสดงเฉพาะอุปกรณ์ที่เป็นไมค์จริง
    ตัดตัวหลอกที่ไม่ใช่ไมค์: Microsoft Sound Mapper / Primary Sound Capture Driver /
    Stereo Mix (loopback) / PC Speaker ฯลฯ
    ถ้ากรองแล้วไม่เหลือเลย (เครื่องที่ชื่อไมค์ไม่มีคำว่า microphone) → คืนทั้งหมด
    """
    import sounddevice as sd
    items = [
        (i, d["name"])
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]
    if only_microphones:
        filtered = [(i, n) for i, n in items if "microphone" in n.lower()]
        return filtered or items
    return items


def auto_detect_mic(keywords: Tuple[str, ...] = _MIC_KEYWORDS) -> Optional[int]:
    """หาไมค์ USB cam (lifecam/camera/webcam/cam) → index

    ไม่เจอ cam mic → ใช้ input device ตัวแรก; ไม่มีเลย → None
    """
    mics = list_mics()
    for kw in keywords:
        for idx, name in mics:
            if kw in name.lower():
                return idx
    return mics[0][0] if mics else None


def resolve_mic(mic=None) -> Optional[int]:
    """แปลงค่า mic → index ของ sounddevice

    mic: None = auto-detect | int = index ตรงๆ | str = ชื่อที่ตรงบางส่วน
    """
    if isinstance(mic, int):
        return mic
    if isinstance(mic, str):
        low = mic.lower()
        # จับคู่ทีเดียวเรียงตาม index: ชื่อเต็ม/ชื่อตัดสั้น (MME) ต้องเจอ index 1 ก่อน index 6
        for idx, name in list_mics():
            n = name.lower().strip()
            if low in n or (len(n) >= 10 and n in low):
                return idx
    return auto_detect_mic()


# ---------------- บันทึกเสียง ----------------
class _SpeechGate:
    """ตัวตัดสิน early-stop: เมื่อไหร่ควรหยุดฟัง (แยกมาให้เทสต์ได้โดยไม่ต้องมีไมค์)

    - เงียบตั้งแต่ต้นครบ tail_silence → หยุด (ไม่มีคนพูด)
    - พูดแล้วเงียบต่อเนื่องครบ tail_silence → หยุด (พูดจบ)
    """

    def __init__(self, tail_silence: float, speech_threshold: float, samplerate: int):
        self.need_quiet = int(tail_silence * samplerate)
        self.speech_threshold = speech_threshold
        self.has_speech = False
        self.quiet = 0  # จำนวนตัวอย่างที่เงียบติดต่อกันล่าสุด

    def feed(self, chunk: np.ndarray) -> bool:
        """ป้อน chunk (float32 1-D) → True ถ้าควรหยุดฟัง"""
        rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
        if rms > self.speech_threshold:
            self.has_speech = True
            self.quiet = 0
        else:
            self.quiet += chunk.size
        return self.quiet >= self.need_quiet


def record(duration: float = 4.0, samplerate: int = 16000, mic=None,
           early_stop: bool = True, tail_silence: float = 0.6,
           speech_threshold: float = 0.01, chunk: float = 0.15,
           stop_event=None) -> np.ndarray:
    """อัดเสียงสูงสุด duration วินาที → np.float32 mono (ค่า -1..1)

    early_stop=True: หยุดทันทีที่พูดจบ (เงียบต่อเนื่อง tail_silence วินาที)
    หรือเงียบตั้งแต่ต้น — ไม่ต้องรอครบ duration ทำให้ตอบสนองเร็วขึ้นมาก
    stop_event: ถ้าถูก set กลางคัน → เลิกอัดเร็ว (ใช้ขัดจังหวะเมื่อมีท่ามือ/คนมา)
    """
    import sounddevice as sd
    idx = resolve_mic(mic)
    if idx is None:
        raise RuntimeError("ไม่พบไมค์ — เชื่อมต่อไมค์หรือระบุ mic=<index> เอง")

    if not early_stop:
        audio = sd.rec(
            int(duration * samplerate),
            samplerate=samplerate,
            channels=1,
            dtype="float32",
            device=idx,
        )
        sd.wait()
        return audio[:, 0]

    gate = _SpeechGate(tail_silence, speech_threshold, samplerate)
    frames: List[np.ndarray] = []

    def callback(indata, frame_count, time_info, status):
        mono = indata[:, 0].copy()
        frames.append(mono)
        if gate.feed(mono):
            raise sd.CallbackStop

    blocksize = max(1, int(chunk * samplerate))
    with sd.InputStream(samplerate=samplerate, channels=1, dtype="float32",
                        device=idx, blocksize=blocksize, callback=callback) as stream:
        deadline = time.time() + duration + 0.5  # กันพลาดกรณีสุดวิสัย
        while stream.active and time.time() < deadline:
            if stop_event is not None and stop_event.is_set():
                break  # ถูกขัดจังหวะ (มีท่ามือ/คนมา) → ปล่อยไมค์เร็ว
            sd.sleep(50)
    return np.concatenate(frames) if frames else np.zeros(0, dtype=np.float32)


def is_silence(audio: np.ndarray, threshold: float = _SILENCE_RMS) -> bool:
    """เช็คว่า audio เงียบ (RMS < threshold) หรือเปล่า — audio ว่างถือว่าเงียบ"""
    if audio.size == 0:
        return True
    return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2))) < threshold


def normalize(audio: np.ndarray, target_peak: float = 0.6) -> np.ndarray:
    """ขยายเสียงที่เบาให้ดังขึ้น (ช่วย whisper ฟังชัดขึ้นมากกับไมค์ระยะไกล)

    - ถ้าเงียบเกิน (peak < 0.01) → ไม่แตะ (ไม่อยากขยายเสียงรบกวนจน STT จับผิด)
    - ถ้าดังอยู่แล้ว (peak >= target) → คงเดิม
    """
    if audio.size == 0:
        return audio
    peak = float(np.max(np.abs(audio)))
    if peak < 0.01 or peak >= target_peak:
        return audio
    return (audio * (target_peak / peak)).astype(np.float32)


# ---------------- WAV (สำหรับ remote) ----------------
def audio_to_wav_bytes(audio: np.ndarray, samplerate: int = 16000) -> bytes:
    """np.float32 → WAV bytes (PCM int16 mono)"""
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(samplerate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def transcribe_remote(wav_bytes: bytes, stt_url: str, timeout: float = 8.0,
                      api_key: str | None = None) -> str:
    """ส่ง WAV ไป STT server บนเครื่อง GPU → ข้อความ

    timeout สั้น (8 วิ) — server ปกติ large-v3/cuda transcribe 4 วิเสียงใน <1 วิ
    ถ้าเกิน = เน็ตหลุด/เครื่อง GPU ล่ม → fallback local ไว ไม่ค้าง 60 วิ
    """
    url = f"{stt_url.rstrip('/')}/transcribe"
    headers = {"Content-Type": "audio/wav"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        url,
        data=wav_bytes,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.URLError as e:
        raise RuntimeError(f"ติดต่อ STT server ไม่ได้ ({url}): {e}") from e
    try:
        return str(json.loads(body).get("text", "")).strip()
    except json.JSONDecodeError:
        return body.strip()  # server อาจตอบข้อความตรงๆ


# ---------------- whisper (local) ----------------
def _setup_cuda_dlls() -> None:
    """เพิ่มโฟลเดอร์ bin ของ nvidia pip wheels เข้า DLL search path

    ctranslate2 (CUDA 12 build) ต้องการ cublas64_12.dll / cudnn64_9.dll —
    ติดตั้งผ่าน: pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
    """
    try:
        import os
        import site
        dirs = []
        for site_dir in site.getsitepackages():
            for pkg in ("nvidia/cublas/bin", "nvidia/cudnn/bin", "nvidia/cuda_runtime/bin"):
                d = os.path.join(site_dir, pkg)
                if os.path.isdir(d):
                    dirs.append(d)
        for d in dirs:
            os.add_dll_directory(d)
        if dirs:  # ctranslate2 โหลดผ่าน LoadLibrary มาตรฐาน → ต้องมีใน PATH ด้วย
            os.environ["PATH"] = os.pathsep.join(dirs + [os.environ.get("PATH", "")])
    except Exception:
        pass


def _load_model(model: str, device: str):
    """โหลด WhisperModel (cache ตาม (model, device))"""
    global _model, _model_key
    key = (model, device)
    if _model is None or _model_key != key:
        _setup_cuda_dlls()  # ต้องเรียกก่อน import faster_whisper/ctranslate2
        from faster_whisper import WhisperModel
        compute = "int8_float16" if device == "cuda" else "int8"
        _model = WhisperModel(model, device=device, compute_type=compute)
        _model_key = key
    return _model


def _transcribe_with(audio: np.ndarray, model: str, device: str, language: str) -> str:
    """รัน whisper ด้วย device ที่ระบุ (ไม่ fallback)"""
    m = _load_model(model, device)
    try:
        segments, _info = m.transcribe(
            audio, language=language, beam_size=5, vad_filter=True,
            hotwords="พี่ทด น้องนุ", condition_on_previous_text=False)
    except TypeError:  # faster-whisper เก่าไม่รู้จัก hotwords
        segments, _info = m.transcribe(audio, language=language, beam_size=5,
                                       vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()


def transcribe(audio: np.ndarray, model: str = "base", device: str = "auto",
               language: str = "th") -> str:
    """แปลง audio → ข้อความ

    device="auto": ลอง cuda ก่อน ถ้าล้มเหลว (โหลดไม่ขึ้น / transcribe พัง
    เช่น cuDNN ไม่ตรงตาม ai_assistant.md §7) → ตก cpu อัตโนมัติ
    """
    if device == "auto":
        try:
            return _transcribe_with(audio, model, "cuda", language)
        except Exception as e:
            print(f"[STT] cuda ใช้ไม่ได้ ({e}) — ใช้ CPU แทน")
            return _transcribe_with(audio, model, "cpu", language)
    return _transcribe_with(audio, model, device, language)


# ---------------- ฟัง + แปลง (ตัวหลัก) ----------------
def listen(duration: float = 4.0, mic=None, stt_url: Optional[str] = None,
           samplerate: int = 16000, model: str = "base", device: str = "auto",
           language: str = "th", early_stop: bool = True,
           tail_silence: float = 0.6, speech_threshold: float = 0.01,
           report_heard: bool = False, stt_api_key: str | None = None,
           stop_event=None, save_debug: str | None = None):
    """ฟังหนึ่งรอบ → ข้อความ (คืน "" ถ้าเงียบ/ไม่ได้ยิน)

    stt_url: ถ้ากำหนด → ส่ง audio ไปเครื่อง GPU แทนการรัน whisper ในเครื่องนี้
    early_stop: หยุดฟังทันทีที่พูดจบ (เร็วขึ้น) — ดู record()
    stop_event: ถ้าถูก set กลางคัน → เลิกฟังรอบนี้ (ดู record())
    report_heard: True → คืน (text, heard) โดย heard=True หมายถึง "มีเสียงแต่ฟังไม่ออก"
                  (ใช้แยกกรณีเงียบสนิท vs ได้ยินเสียงรบกวน — สำหรับ idle/fallback)
    save_debug: path ของไฟล์ .wav — บันทึกเสียงที่อัดไว้เพื่อตรวจย้อนหลัง
    """
    audio = record(duration=duration, samplerate=samplerate, mic=mic,
                   early_stop=early_stop, tail_silence=tail_silence,
                   speech_threshold=speech_threshold, stop_event=stop_event)
    heard = not is_silence(audio)
    if not heard:
        return ("", False) if report_heard else ""
    audio = normalize(audio)   # ขยายเสียงเบาให้ whisper ฟังชัดขึ้น
    if save_debug:
        try:
            import os
            os.makedirs(os.path.dirname(save_debug) or ".", exist_ok=True)
            with open(save_debug, "wb") as fh:
                fh.write(audio_to_wav_bytes(audio, samplerate))
            print(f"[STT] บันทึกเสียงตรวจสอบ: {save_debug}")
        except OSError as exc:
            print(f"[STT] บันทึกไฟล์เสียงไม่ได้: {exc}")
    if stt_url:
        text = transcribe_remote(audio_to_wav_bytes(audio, samplerate), stt_url,
                                 api_key=stt_api_key)
    else:
        text = transcribe(audio, model=model, device=device, language=language)
    return (text, True) if report_heard else text


# ---------------- ฟังต่อเนื่อง (always-on) ----------------
class ContinuousMic:
    """ไมค์แบบ "เปิดค้าง" — พูดเมื่อไหร่ก็ได้ ไม่มีช่วงหูดับ

    ทำไมต้องมี: record()/listen() เปิด-ปิดไมค์เป็นรอบ → ถ้าผู้ใช้เริ่มพูด
    ตอนไมค์ปิด (ระหว่างส่ง STT / รอ LLM / หุ่นกำลังพูด) ต้นประโยคจะหายไป
    ทำให้ STT ถอดเพี้ยน ("มันไม่ใช่สิ่งที่ฉันพูด")

    วิธีใช้:
        mic = ContinuousMic(mic=7); mic.start()
        clip = mic.read_utterance(timeout=0.3)   # None = ยังไม่มีใครพูดจบ
        mic.mute = True   # ขณะหุ่นพูด → ทิ้งเสียงทั้งหมด (กันหุ่นฟังเสียงตัวเอง)
    """

    def __init__(self, mic=None, samplerate: int = 16000, chunk: float = 0.05,
                 preroll: float = 0.6, tail_silence: float = 1.2,
                 speech_threshold: float = 0.025, max_utterance: float = 12.0,
                 min_voice: float = 0.15):
        self.mic = mic
        self.samplerate = samplerate
        self.chunk = chunk
        self.preroll = preroll              # เก็บเสียงย้อนหลังกี่วิ (กันพลาดต้นประโยค)
        self.tail_silence = tail_silence    # เงียบต่อเนื่องเท่านี้ = พูดจบ
        self.speech_threshold = speech_threshold
        self.max_utterance = max_utterance
        self.min_voice = min_voice          # ★ ต้องเสียงดังต่อเนื่องเท่านี้ก่อนนับว่า "พูด"
        self.mute = False                   # True = ทิ้งเสียง (เช่น ขณะหุ่นพูด)

        self._stream = None
        self._buf: deque = deque()          # ring ของ chunk ล่าสุด (preroll)
        self._utt: List[np.ndarray] = []
        self._recording = False
        self._quiet = 0.0
        self._voice_run = 0.0               # ระยะเวลาเสียงดังต่อเนื่องล่าสุด (นับแบบรั่ว)
        self._event = threading.Event()
        self._result: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._calibrating = False           # กำลังวัดเสียงรบกวนห้อง
        self._noise: List[float] = []
        self._last_cb = 0.0                 # เวลา callback ล่าสุด (เช็คสตรีมตายเงียบ)
        self._sig_peak = 0.0                # peak สูงสุดในหน้าต่างป์จจุบัน (ตรวจสตรีมแจกแต่เงียบ)
        self._sig_window = 0.0              # เวลาเริ่มหน้าต่างวัดสัญญาณ
        self._rms_peak = 0.0                # RMS chunk สูงสุดในหน้าต่าง (ค่าเดียวกับที่ gate ใช้)
        self._last_rms = 0.0                # 📊 RMS ล่าสุดสด ๆ — ให้ GUI วาด VU meter
        self._last_pk = 0.0                 # 📊 peak ล่าสุดสด ๆ (เส้น peak-hold บน VU)

    # ---------- lifecycle ----------
    def start(self):
        import sounddevice as sd

        idx = resolve_mic(self.mic)
        if idx is None:
            raise RuntimeError("ไม่พบไมค์ — เชื่อมต่อไมค์หรือระบุ mic=<index>")
        self._stream = sd.InputStream(
            samplerate=self.samplerate, channels=1, dtype="float32", device=idx,
            blocksize=int(self.chunk * self.samplerate), callback=self._callback,
        )
        self._stream.start()
        self._last_cb = time.time()
        self._sig_peak = 0.0
        self._sig_window = time.time()
        self._rms_peak = 0.0
        self._last_rms = 0.0
        self._last_pk = 0.0

    def stop(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

    def ensure_alive(self, stale_after: float = 2.0) -> bool:
        """ถ้า stream ผิดปกติ (ตายเงียบ / ส่งแต่ศูนย์เป๊ะ) → เปิดใหม่

        กัน 2 เคสที่เจอจริง:
          1. ไม่มี callback เลย (PortAudio สตรีมตาย) — ห้องเงียบปกติยังมี callback ตลอด
          2. callback มาปกติแต่ค่าทุกอย่างเป็นศูนย์เป๊ะ (ถูกโปรแกรมอื่นแย่งไมค์ — เกิดกับ LifeCam)
             (ไมค์จริงในห้องเงียบ ๆ ยังมี self-noise ~0.003 ขึ้นไป)
        """
        now = time.time()
        if now - self._sig_window >= 5.0:   # หมุนหน้าต่างวัดสัญญาณทุก 5 วิ
            self._sig_peak = 0.0
            self._rms_peak = 0.0
            self._sig_window = now
        no_cb = (now - self._last_cb) > stale_after
        dead_quiet = (self._sig_peak < 5e-4
                      and (now - self._sig_window) > 2.0
                      and not no_cb)
        if not (no_cb or dead_quiet):
            return False
        try:
            self.stop()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.2)
        self.start()
        print("[STT] ♻️ ไมค์ส่งสัญญาณผิดปกติ — เปิดสตรีมใหม่แล้ว")
        return True

    def calibrate(self, seconds: float = 1.0) -> float:
        """วัดเสียงรบกวนห้อง ~seconds วิ แล้วตั้ง speech_threshold อัตโนมัติ

        ทำไม: ไมค์แต่ละตัว/แต่ละห้องมี noise floor ต่างกันมาก (0.005–0.03)
        เกณฑ์คงที่จึงหูหนวก（ไม่ตอบ）หรือหูไวเกิน（เก็บเสียงลม/ทีวีเป็นคำพูด）
        ตั้ง threshold = noise × 1.8 (จำกัดไม่เกิน 0.04) — เรียกหลัง start()

        ⚠️ เพดาน 0.04 เพราะเสียงพูดจริงผ่านไมค์ระยะไกล (LifeCam) ราว RMS 0.03-0.07
        — ถ้าตั้งสูงกว่านี้ (เคยถึง 0.05-0.08) หุ่นจะ "หูหนวก" ต่อเสียงคนพูด
        """
        self._noise = []
        self._calibrating = True
        deadline = time.time() + seconds
        while time.time() < deadline:
            time.sleep(0.05)
        self._calibrating = False
        if self._noise:
            # ใช้เปอร์เซ็นไทล์ที่ 30 (ไม่ใช่ median) — กันเสียงพูด/เสียงกระตุกช่วง
            # เปิดแอปหลอกให้เกณฑ์สูงเกิน (เจอจริง: เห็น 0.0275 ชั่วขณะ → เกณฑ์ 0.04 → หูหนวก)
            noise = float(np.percentile(self._noise, 30))
            # ⚠️ ตัวคูณ/เพดานต้องไม่สูงเกินเสียงพูดจริง — เคยตั้ง noise×3 เพดาน 0.05
            #    แต่เสียงพูดระยะไกลของ LifeCam มี RMS ~0.03 → เสียงคนผ่านไม่ถึงเกณฑ์!
            self.speech_threshold = min(max(noise * 1.8, self.speech_threshold), 0.04)
            print(f"[STT] ปรับเกณฑ์: เสียงรบกวน={noise:.4f} "
                  f"→ speech_threshold={self.speech_threshold:.4f}")
        return self.speech_threshold

    # ---------- audio thread ----------
    def _callback(self, indata, frames, _time_info, _status):
        self._last_cb = time.time()
        mono = indata[:, 0].copy()
        pk = float(np.abs(mono).max())
        if pk > self._sig_peak:
            self._sig_peak = pk
        rms = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2)))
        self._last_rms = rms        # 📊 ค่าดิบล่าสุด (VU meter ใน GUI อ่านค่านี้)
        self._last_pk = pk          # 📊 peak ของ chunk นี้ (เส้น peak-hold)
        if rms > self._rms_peak:
            self._rms_peak = rms
        if self._calibrating:
            self._noise.append(rms)
            return
        if self.mute:
            self._reset(keep_buf=False)
            return

        if not self._recording:
            self._buf.append(mono)
            keep = int(self.preroll * self.samplerate)
            total = sum(len(c) for c in self._buf)
            while len(self._buf) > 1 and total - len(self._buf[0]) >= keep:
                total -= len(self._buf.popleft())
            if rms > self.speech_threshold:
                self._voice_run += frames / self.samplerate
            else:
                # ลดลงแทนการรีเซ็ต — ทน "จังหวะหยุดสั้น ๆ ระหว่างคำ" แต่กันเสียงกระตุกครั้งเดียว
                self._voice_run = max(0.0, self._voice_run - frames / self.samplerate)
            # ★ ต้องดังต่อเนื่อง (สุทธิ) min_voice วิก่อน — เสียงกระตุกสั้น ๆ (จานกระแทก/ทีวี)
            #   จะไม่เริ่มบันทึก → ลดคลิปปลอมที่ STT ถอดได้ความว่างเปล่า
            if self._voice_run >= self.min_voice:
                self._recording = True
                self._utt = list(self._buf)   # ★ ต้นประโยคอยู่ใน preroll แล้ว
                self._buf.clear()
                self._quiet = 0.0
                self._voice_run = 0.0
            return

        self._utt.append(mono)
        self._quiet = 0.0 if rms > self.speech_threshold else self._quiet + frames / self.samplerate
        length = sum(len(c) for c in self._utt) / self.samplerate
        if self._quiet >= self.tail_silence or length >= self.max_utterance:
            clip = np.concatenate(self._utt)
            self._reset()
            with self._lock:
                self._result = clip
            self._event.set()

    def _reset(self, keep_buf: bool = True):
        self._recording = False
        self._quiet = 0.0
        self._voice_run = 0.0
        self._utt = []
        if not keep_buf:
            self._buf.clear()

    # ---------- consumer ----------
    def read_utterance(self, timeout: Optional[float] = None) -> Optional[np.ndarray]:
        """รอจนมีคนพูดจบ → คืนคลิปเสียง (None = ยังไม่มีภายใน timeout)"""
        if not self._event.wait(timeout):
            return None
        self._event.clear()
        with self._lock:
            clip, self._result = self._result, None
        return clip
