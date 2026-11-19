# -*- coding: utf-8 -*-
"""เล่นเพลงจากโฟลเดอร์ local — ใช้กับ tool calling ของหุ่น

⚠️ โปรเจกต์นี้ **ไม่แจกไฟล์เพลง** (ลิขสิทธิ์) — ผู้ใช้ต้องวางไฟล์ที่ได้มาถูกต้องเองที่
    media/music/   เช่น  media/music/เขาคือพี่แอ็ด - คาราบาว.mp3

ฟังก์ชันหลัก
    list_tracks()        -> list[Path] ไฟล์เพลงทั้งหมด
    find_track(query)    -> Path | None  ค้นหาชื่อไฟล์แบบ fuzzy (ไทย/อังกฤษ)
    play(query, block)   -> (ok, ข้อความ)  เล่นเพลง (หยุดได้ด้วย stop())
    stop()               -> หยุดเพลงที่กำลังเล่น

ใช้ ffplay (มากับ ffmpeg) เพื่อให้ "หยุดกลางเพลง" ได้จริง — ถ้าไม่มี ffplay
จะ fallback ไป playsound3 (หยุดไม่ได้)
"""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "media" / "music"
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".wma"}

_proc: subprocess.Popen | None = None
_lock = threading.Lock()

# คำพ้องที่มักถูกเรียกต่างกัน → ใช้ค้นเพิ่ม
ALIASES = {
    "เขาคือพี่แอ็ด": ["khao khue phi aed", "khaokhuephiaed", "พี่แอ็ด", "phi aed", "carabao", "คาราบาว"],
    "คาราบาว": ["carabao"],
}


def list_tracks() -> list[Path]:
    """ไฟล์เพลงทั้งหมดใน media/music (เรียงตามชื่อ)"""
    if not MUSIC_DIR.is_dir():
        return []
    return sorted(
        (p for p in MUSIC_DIR.iterdir()
         if p.is_file() and p.suffix.lower() in AUDIO_EXT),
        key=lambda p: p.name.lower(),
    )


def _norm(text: str) -> str:
    """ทำให้เทียบง่าย: ตัวพิมพ์เล็ก ตัดช่องว่าง/ขีด/จุด"""
    keep = []
    for ch in text.lower():
        if ch.isalnum():
            keep.append(ch)
    return "".join(keep)


def find_track(query: str) -> Path | None:
    """ค้นหาไฟล์เพลงจากคำค้น (fuzzy — ไม่สนช่องว่าง/ขีด/ตัวพิมพ์)

    ลำดับการจับคู่: ชื่อไฟล์ตรงเป๊ะ → มีคำค้นอยู่ในชื่อ → ทุกคำของคำค้นอยู่ในชื่อ
    → คำพ้อง (ALIASES) → คะแนนคำร่วมสูงสุด
    """
    tracks = list_tracks()
    if not tracks or not query:
        return None
    q = _norm(query)
    names = {p: _norm(p.stem) for p in tracks}

    for p, n in names.items():
        if n == q:
            return p
    for p, n in names.items():
        if q in n:
            return p

    tokens = [_norm(t) for t in str(query).replace("-", " ").split() if _norm(t)]
    if tokens:
        for p, n in names.items():
            if all(t in n for t in tokens):
                return p

    for alias_key, alias_list in ALIASES.items():
        if _norm(alias_key) in q or any(_norm(a) in q for a in alias_list):
            for p, n in names.items():
                if any(_norm(a) in n for a in alias_list) or _norm(alias_key) in n:
                    return p

    if tokens:  # คะแนนคำร่วม
        best, best_score = None, 0
        for p, n in names.items():
            score = sum(1 for t in tokens if t and t in n)
            if score > best_score:
                best, best_score = p, score
        if best is not None:
            return best
    return None


def _ffplay() -> str | None:
    return shutil.which("ffplay")


def play(query: str = "", block: bool = True,
         path: Path | None = None) -> tuple[bool, str]:
    """เล่นเพลง (block=True = รอจนจบ) — คืน (สำเร็จ, ข้อความ)"""
    global _proc
    track = Path(path) if path else find_track(query)
    if track is None or not track.exists():
        have = ", ".join(p.stem for p in list_tracks()[:8]) or "(ยังไม่มีไฟล์)"
        return False, (f"ไม่พบเพลง '{query}' — วางไฟล์ไว้ที่ media/music/ "
                       f"แล้วลองใหม่ · ที่มีอยู่: {have}")

    stop()
    ff = _ffplay()
    if ff:
        with _lock:
            _proc = subprocess.Popen(
                [ff, "-nodisp", "-autoexit", "-loglevel", "quiet", str(track)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        if block:
            try:
                _proc.wait()
            except KeyboardInterrupt:
                stop()
        return True, f"เปิดเพลง {track.stem}"

    # fallback: playsound3 (หยุดกลางเพลงไม่ได้)
    from src.tts import play_file
    if block:
        play_file(str(track), block=True)
    else:
        threading.Thread(target=play_file, args=(str(track),), daemon=True).start()
    return True, f"เปิดเพลง {track.stem}"


def stop() -> None:
    """หยุดเพลงที่กำลังเล่นอยู่"""
    global _proc
    with _lock:
        if _proc is not None and _proc.poll() is None:
            try:
                _proc.terminate()
                _proc.wait(timeout=2)
            except Exception:  # noqa: BLE001
                pass
        _proc = None


def is_playing() -> bool:
    return _proc is not None and _proc.poll() is None


def play_async(query: str = "", path: Path | None = None) -> tuple[bool, str]:
    """เล่นเพลงแบบไม่บล็อก (คืนทันที) — ใช้กับ tool calling"""
    return play(query, block=False, path=path)


def wait(seconds: float | None = None) -> None:
    """รอเพลงจบ (ถ้าไม่ระบุเวลา = รอจนจบ)"""
    if _proc is None:
        return
    if seconds is None:
        try:
            _proc.wait()
        except KeyboardInterrupt:
            stop()
    else:
        time.sleep(seconds)


# ---------------------------------------------------------------- YouTube
# เปิดผ่าน browser → เล่นใน player ของ YouTube (ไม่ต้องโหลด/เก็บไฟล์เอง)
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")          # video id ของ YouTube


def youtube_url(query: str) -> str:
    """คำค้น/ลิงก์ → URL ของ YouTube ที่เปิดได้เลย

    - ลิงก์เต็ม (http…)            → ใช้ตามนั้น
    - video id 11 ตัวอักษร         → watch?v=<id>
    - ข้อความอื่น                    → หน้าผลการค้นหา
    """
    q = (query or "").strip()
    if not q:
        return "https://www.youtube.com/"
    if _URL_RE.match(q):
        return q
    if _ID_RE.match(q):
        return f"https://www.youtube.com/watch?v={q}"
    return "https://www.youtube.com/results?search_query=" + quote_plus(q)


def open_youtube(query: str = "") -> tuple[bool, str]:
    """เปิด YouTube ใน browser (เล่นผ่านเว็บ) — คืน (สำเร็จ, ข้อความ)"""
    url = youtube_url(query)
    try:
        ok = webbrowser.open(url, new=2)
    except Exception as exc:  # noqa: BLE001
        return False, f"เปิด browser ไม่สำเร็จ: {exc}"
    if not ok:
        return False, f"เปิด browser ไม่ได้ — ลิงก์: {url}"
    global _youtube_playing
    _youtube_playing = True
    if _URL_RE.match((query or "").strip()) or _ID_RE.match((query or "").strip()):
        return True, f"เปิด YouTube: {url}"
    return True, f"เปิด YouTube ค้นหา: {query}"


_youtube_playing = False      # เราเปิด YouTube ไว้และยังไม่ได้สั่ง pause


def media_play_pause() -> bool:
    """กดปุ่ม media Play/Pause ของ Windows (browser ที่เล่น YouTube อยู่จะหยุด/เล่นต่อ)"""
    try:
        import ctypes

        vk = 0xB3                                     # VK_MEDIA_PLAY_PAUSE
        user32 = ctypes.windll.user32
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)               # KEYEVENTF_KEYUP
        return True
    except Exception:  # noqa: BLE001 — ไม่ใช่ Windows
        return False


def pause_youtube() -> bool:
    """หยุด YouTube ที่เราเปิดไว้ (ส่ง media key ครั้งเดียว — กันกดซ้ำแล้วกลับมาเล่น)"""
    global _youtube_playing
    if not _youtube_playing:
        return False
    _youtube_playing = False
    return media_play_pause()


def youtube_search_music(query: str) -> str:
    """ลิงก์ YouTube Music (ตัวเลือกเสริม)"""
    return "https://music.youtube.com/search?q=" + quote_plus(query or "")
