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
import time
import urllib.error
import urllib.request
import wave
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


# ---------------- ไมค์ ----------------
def list_mics() -> List[Tuple[int, str]]:
    """รายชื่อ input device: [(index, ชื่อ), ...]"""
    import sounddevice as sd
    return [
        (i, d["name"])
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]


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
        for idx, name in list_mics():
            if mic.lower() in name.lower():
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
           speech_threshold: float = 0.01, chunk: float = 0.15) -> np.ndarray:
    """อัดเสียงสูงสุด duration วินาที → np.float32 mono (ค่า -1..1)

    early_stop=True: หยุดทันทีที่พูดจบ (เงียบต่อเนื่อง tail_silence วินาที)
    หรือเงียบตั้งแต่ต้น — ไม่ต้องรอครบ duration ทำให้ตอบสนองเร็วขึ้นมาก
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
            sd.sleep(50)
    return np.concatenate(frames) if frames else np.zeros(0, dtype=np.float32)


def is_silence(audio: np.ndarray, threshold: float = _SILENCE_RMS) -> bool:
    """เช็คว่า audio เงียบ (RMS < threshold) หรือเปล่า — audio ว่างถือว่าเงียบ"""
    if audio.size == 0:
        return True
    return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2))) < threshold


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


def transcribe_remote(wav_bytes: bytes, stt_url: str, timeout: float = 8.0) -> str:
    """ส่ง WAV ไป STT server บนเครื่อง GPU → ข้อความ

    timeout สั้น (8 วิ) — server ปกติ large-v3/cuda transcribe 4 วิเสียงใน <1 วิ
    ถ้าเกิน = เน็ตหลุด/เครื่อง GPU ล่ม → fallback local ไว ไม่ค้าง 60 วิ
    """
    url = f"{stt_url.rstrip('/')}/transcribe"
    req = urllib.request.Request(
        url,
        data=wav_bytes,
        headers={"Content-Type": "audio/wav"},
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
    segments, _info = m.transcribe(audio, language=language, beam_size=5, vad_filter=True)
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
           report_heard: bool = False):
    """ฟังหนึ่งรอบ → ข้อความ (คืน "" ถ้าเงียบ/ไม่ได้ยิน)

    stt_url: ถ้ากำหนด → ส่ง audio ไปเครื่อง GPU แทนการรัน whisper ในเครื่องนี้
    early_stop: หยุดฟังทันทีที่พูดจบ (เร็วขึ้น) — ดู record()
    report_heard: True → คืน (text, heard) โดย heard=True หมายถึง "มีเสียงแต่ฟังไม่ออก"
                  (ใช้แยกกรณีเงียบสนิท vs ได้ยินเสียงรบกวน — สำหรับ idle/fallback)
    """
    audio = record(duration=duration, samplerate=samplerate, mic=mic,
                   early_stop=early_stop, tail_silence=tail_silence,
                   speech_threshold=speech_threshold)
    heard = not is_silence(audio)
    if not heard:
        return ("", False) if report_heard else ""
    if stt_url:
        text = transcribe_remote(audio_to_wav_bytes(audio, samplerate), stt_url)
    else:
        text = transcribe(audio, model=model, device=device, language=language)
    return (text, True) if report_heard else text
