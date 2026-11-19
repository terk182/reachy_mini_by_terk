"""TTS: ให้หุ่น "พูด" ข้อความ

- `clean_for_speech()`: ล้างอีโมจิ/markdown ก่อนส่ง TTS (ไม่อยากให้อ่าน '*', '#')
- `speak()`: พูดข้อความ (ล้างให้อัตโนมัติเสมอ)

ลำดับการลอง:
  1. gTTS      — Google TTS (internet) เสียงไทยดี เร็ว ~0.4s/ประโยค
  2. edge-tts  — Microsoft Edge neural (internet) — ⚠️ บนเน็ตบางเครือข่าย WSS ถูก block 403
  3. pyttsx3   — TTS offline (เสียงตามที่ติดตั้งใน Windows)
  4. ไม่มีเลย  -> คืน False (เงียบ)
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import threading

_engine = None  # pyttsx3 engine (สร้างครั้งเดียว)
_cache_lock = threading.Lock()  # กันสังเคราะห์ประโยคเดียวกันพร้อมกัน (prewarm vs main)

# 🎭 โปรไฟล์เสียงชาย/หญิง — gTTS มีเสียงไทยเสียงเดียว จึงใช้ ffmpeg เลื่อน pitch
#    (asetrate + atempo → ความถี่เปลี่ยน แต่ความยาวประโยคเท่าเดิม)
_VOICE_PITCH = {
    "male": 0.80,     # ลดความถี่ลง ~3.9 semitone → เสียงผู้ชาย
    "female": 1.06,   # เพิ่มเล็กน้อย → เสียงผู้หญิงใสขึ้น ต่างจากพี่ทดชัด
}


def _ffmpeg_exe() -> str | None:
    import shutil
    return shutil.which("ffmpeg")


def _probe_sample_rate(mp3: str) -> int:
    """อ่าน sample rate ของไฟล์เสียง (ffprobe) — ค่าเริ่มต้น 24000 (gTTS)"""
    import json
    import subprocess

    exe = _ffmpeg_exe()
    if not exe:
        return 24000
    probe = os.path.join(os.path.dirname(exe), "ffprobe.exe")
    if not os.path.exists(probe):
        probe = "ffprobe"
    try:
        out = subprocess.run(
            [probe, "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=sample_rate", "-of", "json", mp3],
            capture_output=True, text=True, timeout=15)
        return int(json.loads(out.stdout)["streams"][0]["sample_rate"])
    except Exception:  # noqa: BLE001
        return 24000


def _pitch_shift(mp3_in: str, mp3_out: str, factor: float) -> bool:
    """เลื่อน pitch โดยคงความยาวเสียง (ffmpeg asetrate + atempo) — คืน True ถ้าสำเร็จ"""
    import subprocess

    exe = _ffmpeg_exe()
    if not exe or factor == 1.0:
        return False
    sr = _probe_sample_rate(mp3_in)
    filt = (f"asetrate={sr * factor:.2f},aresample={sr},"
            f"atempo={1.0 / factor:.6f}")
    try:
        res = subprocess.run(
            [exe, "-y", "-hide_banner", "-loglevel", "error",
             "-i", mp3_in, "-af", filt, "-codec:a", "libmp3lame", "-q:a", "4",
             mp3_out],
            capture_output=True, text=True, timeout=60)
        return (res.returncode == 0 and os.path.exists(mp3_out)
                and os.path.getsize(mp3_out) > 0)
    except Exception as exc:  # noqa: BLE001
        print(f"[TTS] pitch shift ล้มเหลว ({exc})")
        return False

# ช่วง Unicode ของอีโมจิ/สัญลักษณ์ (กว้างพอสำหรับ emoji ทั่วไป)
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"   # pictographs / emoji / flags
    "\U0001F1E6-\U0001F1FF"   # ธงชาติ (regional indicators)
    "\U00002600-\U000027BF"   # สัญลักษณ์ + dingbats
    "\U00002B00-\U00002BFF"   # ลูกศรเสริม
    "\U0000FE0F"              # variation selector
    "\U00002190-\U000021FF"   # ลูกศร
    "]+"
)


def clean_for_speech(text: str) -> str:
    """ล้างอีโมจิ + markdown ก่อนส่ง TTS

    - แปลง [ข้อความ](url) -> ข้อความ
    - ลบเครื่องหมาย markdown: ** * _ ` ~~ # > [ ] { } \\
    - ลบหัวข้อ/รายการ (บรรทัดที่ขึ้นต้นด้วย #, -, *, ตัวเลข.)
    - ลบอีโมจิ
    - รวมช่องว่างซ้ำ
    """
    if not text:
        return text

    t = text
    # 1) ลิงก์ markdown [text](url) -> text
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    # 2) เครื่องหมาย markdown
    t = re.sub(r"[*_`~#>{}\[\]\\]", "", t)
    # 3) บรรทัดหัวเรื่อง (### ... / --- / ===)
    t = re.sub(r"^\s{0,3}(#{1,6}\s*|[-=]{3,})\s*", "", t, flags=re.MULTILINE)
    # 4) รายการ (- / * / + / 1. / 2))
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*\d+[.)]\s+", "", t, flags=re.MULTILINE)
    # 5) อีโมจิ
    t = _EMOJI_RE.sub("", t)
    # 6) เครื่องหมายที่ TTS ไม่ควรอ่าน (comma ตกค้างจาก LLM, เครื่องหมายคำพูด ฯลฯ)
    t = re.sub(r"[,;:()\"'«»‘’“”【】]|\.{2,}|[–—-]", " ", t)
    # 7) รวมช่องว่างซ้ำ
    t = re.sub(r"\s+", " ", t).strip()
    return t


def synthesize_to_file(text: str, lang: str = "th",
                       voice: str | None = None) -> str | None:
    """สังเคราะห์ข้อความ → ไฟล์ MP3 (gTTS) โดยไม่เล่น คืน path หรือ None

    voice: "male"/"female" = ปรับ pitch ด้วย ffmpeg (gTTS มีเสียงไทยเดียว)
    ใช้กับ speak_with_motion() — ต้องการไฟล์เสียงไป decode เป็น PCM
    แล้ววิเคราะห์จังหวะสำหรับขยับหัวตามเสียง
    """
    text = clean_for_speech(text or "")
    if not text:
        return None
    try:
        from gtts import gTTS

        fd, mp3 = tempfile.mkstemp(suffix=".mp3", prefix="reachy_tts_")
        os.close(fd)
        gTTS(text, lang=lang).save(mp3)
        factor = _VOICE_PITCH.get(voice or "", 1.0)
        if factor != 1.0:
            fd2, shifted = tempfile.mkstemp(suffix=".mp3", prefix="reachy_tts_v_")
            os.close(fd2)
            if _pitch_shift(mp3, shifted, factor):
                try:
                    os.remove(mp3)
                except OSError:
                    pass
                return shifted
            try:
                os.remove(shifted)
            except OSError:
                pass
        return mp3
    except Exception as exc:  # noqa: BLE001
        print(f"[TTS] สังเคราะห์ล้มเหลว ({exc})")
        return None


_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "cache", "tts")


def _cache_path(text: str, lang: str, voice: str | None = None) -> str:
    pitch = _VOICE_PITCH.get(voice or "", 1.0)
    key = hashlib.md5(
        f"{lang}|{voice or ''}|{pitch}|{text}".encode("utf-8")).hexdigest()
    return os.path.join(_CACHE_DIR, f"{key}.mp3")


def synthesize_to_file_cached(text: str, lang: str = "th",
                              voice: str | None = None) -> str | None:
    """เหมือน synthesize_to_file() แต่ cache ไว้ — เรียกซ้ำไม่ต้องต่อเน็ตใหม่

    voice: "male"/"female" — cache แยกตามเสียง (ประโยคเดียวกันเสียงต่างกันได้)
    """
    text = clean_for_speech(text or "")
    if not text:
        return None
    path = _cache_path(text, lang, voice)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path

    with _cache_lock:
        # double-check — thread อื่นอาจสังเคราะห์เสร็จระหว่างรอ lock
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
        try:
            from gtts import gTTS
            os.makedirs(_CACHE_DIR, exist_ok=True)
            # tmp ชื่อไม่ซ้ำ (tempfile.mkstemp) — กัน prewarm กับ main ชนกัน
            fd, tmp = tempfile.mkstemp(suffix=".mp3", dir=_CACHE_DIR)
            os.close(fd)
            gTTS(text, lang=lang).save(tmp)
            factor = _VOICE_PITCH.get(voice or "", 1.0)
            if factor != 1.0:
                fd2, shifted = tempfile.mkstemp(suffix=".mp3", dir=_CACHE_DIR)
                os.close(fd2)
                if _pitch_shift(tmp, shifted, factor):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                    tmp = shifted
                else:
                    try:
                        os.remove(shifted)
                    except OSError:
                        pass
            try:
                os.replace(tmp, path)
            except OSError as exc_lock:
                # ไฟล์ปลายทางกำลังถูกใช้ (เช่น เล่นอยู่) → ลบแล้วแทนที่ใหม่
                try:
                    os.remove(path)
                    os.replace(tmp, path)
                except OSError:
                    # ยัง lock อยู่ → คืนไฟล์ tmp ที่เพิ่งสร้าง (เล่นได้เลย คราวหน้าค่อย cache ใหม่)
                    print(f"[TTS] cache ถูก lock ({exc_lock}) — ใช้ไฟล์ชั่วคราวแทน")
                    return tmp
            return path
        except Exception as exc:  # noqa: BLE001
            print(f"[TTS] สังเคราะห์ล้มเหลว ({exc})")
            return None


def prewarm_phrases(texts, lang: str = "th", block: bool = False,
                    voice: str | None = None) -> None:
    """สังเคราะห์ล่วงหน้า (background) — กัน TTS latency หน่วงตอบแรก ๆ"""
    import threading

    def _run():
        for t in texts:
            synthesize_to_file_cached(t, lang, voice)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    if block:
        t.join()


def play_file(path: str, block: bool = True) -> bool:
    """เล่นไฟล์เสียง (mp3/wav) ด้วย playsound3"""
    try:
        from playsound3 import playsound
        playsound(path, block=block)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[TTS] เล่นเสียงล้มเหลว ({exc})")
        return False


def speak(text: str, lang="th-TH-PremierNeural", block=True,
          voice: str | None = None) -> bool:
    """พูดข้อความ คืน True ถ้าพูดได้ (ล้างอีโมจิ/markdown ให้อัตโนมัติ)

    voice: "male"/"female" = โปรไฟล์เสียงไทย (gTTS + ffmpeg pitch shift)
    """
    global _engine

    text = clean_for_speech(text or "")
    if not text:
        return False

    # 0) โปรไฟล์เสียงชาย/หญิง — เลือกเสียงได้แม้ edge-tts ล่ม (เน็ตบล็อก WSS)
    if voice in _VOICE_PITCH:
        mp3v = synthesize_to_file(text, lang.split("-")[0], voice)
        if mp3v and play_file(mp3v, block=block):
            return True

    # 1) gtts (Google TTS, internet, เสียงไทยดี + เร็ว)
    gtts_lang = lang.split("-")[0]  # "th-TH-PremierNeural" -> "th"
    mp3 = synthesize_to_file(text, gtts_lang)
    if mp3 and play_file(mp3, block=block):
        return True

    # 2) edge-tts (internet, เสียงไทยเนียน) — บางเครือข่าย WSS ถูก block 403
    try:
        import asyncio

        import edge_tts

        mp3 = os.path.join(tempfile.gettempdir(), "reachy_tts.mp3")
        asyncio.run(edge_tts.Communicate(text, lang).save(mp3))
        if play_file(mp3, block=block):
            return True
    except Exception as exc2:  # noqa: BLE001
        print(f"[TTS] edge-tts ล้มเหลว ({exc2}) -> ลอง pyttsx3")

    # 3) pyttsx3 (offline)
    try:
        import pyttsx3

        if _engine is None:
            _engine = pyttsx3.init()
        _engine.say(text)
        _engine.runAndWait()
        return True
    except Exception as exc3:  # noqa: BLE001
        print(f"[TTS] pyttsx3 ล้มเหลว ({exc3})")
        return False
