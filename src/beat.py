# -*- coding: utf-8 -*-
"""จับจังหวะเพลง (beat tracking) จากเสียงที่ออกลำโพงจริง

ใช้ WASAPI loopback (ไลบรารี `soundcard`) → ได้ยินทุกเสียงที่เครื่องเล่นอยู่
(เช่น YouTube ใน browser) โดยไม่ต้องรู้ว่าเพลงอะไร

ขั้นตอน
    เสียง → onset strength (spectral flux) → BPM (autocorrelation + prior ~120)
    → phase (comb filter หาตำแหน่ง beat ล่าสุด) → นาฬิกาจังหวะแบบ PLL (ไม่กระโดด)

ใช้งาน
    tracker = BeatTracker()
    tracker.start()
    b = tracker.beat_position()   # เลขจังหวะต่อเนื่อง (float) — 3.0 = ตรงจังหวะที่ 3 พอดี
    tracker.bpm, tracker.audible, tracker.intensity
    tracker.stop()

ถ้าไม่มี soundcard / เปิด loopback ไม่ได้ → เดินจังหวะเองที่ default_bpm (หุ่นยังเต้นได้)
"""

from __future__ import annotations

import threading
import time
from collections import deque

import numpy as np

SR = 48000          # sample rate ที่ขอจาก loopback
HOP = 512           # ~10.7 ms ต่อเฟรม onset
WIN = 1024
FPS = SR / HOP      # เฟรม onset ต่อวินาที (~93.75)
BPM_MIN, BPM_MAX = 70.0, 180.0
SILENCE_RMS = 2e-3  # ต่ำกว่านี้ถือว่าเงียบ
LOUD_FLOOR = 0.08    # RMS ~1 วินาทีของเพลงที่ "ดังเต็มที่" ขั้นต่ำ (YouTube ปกติ ~0.1-0.2)


def _log(msg: str) -> None:
    """print ที่ไม่พังบน console ที่ไม่รองรับ emoji/ไทย (เช่น cp874)"""
    try:
        print(msg)
    except UnicodeEncodeError:
        import sys
        enc = sys.stdout.encoding or "ascii"
        print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))


class OnsetAnalyzer:
    """แปลงเสียง → onset envelope + ประมาณ BPM/phase (ไม่ผูกกับอุปกรณ์ — ทดสอบได้)"""

    def __init__(self, sr: int = SR, history_s: float = 6.0):
        self.sr = sr
        self.fps = sr / HOP
        self._window = np.hanning(WIN).astype(np.float32)
        self._tail = np.zeros(0, dtype=np.float32)
        self._prev_mag = None
        n = int(history_s * self.fps)
        self.env: deque[float] = deque(maxlen=n)     # onset strength
        self.times: deque[float] = deque(maxlen=n)   # เวลา (วินาที) ของแต่ละเฟรม
        self.rms = 0.0
        self.last_flux = 0.0      # onset แรงสุดของบล็อกล่าสุด (ใช้ทำ accent ตามกลอง)

    def feed(self, mono: np.ndarray, t_end: float) -> None:
        """ป้อนเสียง mono (float) ที่ "จบ" ที่เวลา t_end (วินาที)"""
        mono = np.asarray(mono, dtype=np.float32).ravel()
        if mono.size:
            self.rms = float(np.sqrt(np.mean(mono * mono)))
        self.last_flux = 0.0
        buf = np.concatenate([self._tail, mono])
        n_frames = (buf.size - WIN) // HOP + 1 if buf.size >= WIN else 0
        for i in range(n_frames):
            seg = buf[i * HOP:i * HOP + WIN] * self._window
            mag = np.log1p(100.0 * np.abs(np.fft.rfft(seg)))
            if self._prev_mag is None:
                flux = 0.0
            else:
                flux = float(np.maximum(mag - self._prev_mag, 0.0).sum())
            self._prev_mag = mag
            # เวลาของเฟรมนี้ = เวลาของตัวอย่างกลางหน้าต่าง
            end_idx = i * HOP + WIN // 2
            t = t_end - (buf.size - end_idx) / self.sr
            self.env.append(flux)
            self.last_flux = max(self.last_flux, flux)
            self.times.append(t)
        keep = buf.size - n_frames * HOP
        self._tail = buf[-keep:] if keep > 0 else np.zeros(0, dtype=np.float32)

    # ---------- วิเคราะห์ ----------
    def _clean_env(self) -> np.ndarray:
        e = np.asarray(self.env, dtype=np.float64)
        if e.size < 8:
            return e
        k = max(3, int(self.fps * 0.25))
        local = np.convolve(e, np.ones(k) / k, mode="same")
        e = np.maximum(e - local, 0.0)
        # เบลอเล็กน้อย — ให้ยอด acf กว้างขึ้น คาบที่เป็นเศษเฟรม (เช่น 37.5) ไม่แพ้คาบจำนวนเต็ม
        g = np.exp(-0.5 * (np.arange(-4, 5) / 1.5) ** 2)
        e = np.convolve(e, g / g.sum(), mode="same")
        s = e.std()
        return e / s if s > 1e-9 else e

    def estimate_tempo(self) -> tuple[float, float] | None:
        """คืน (bpm, ความมั่นใจ 0-1) หรือ None ถ้าข้อมูลยังไม่พอ"""
        e = self._clean_env()
        if e.size < self.fps * 3:
            return None
        e = e - e.mean()
        n = e.size
        acf = np.correlate(e, e, mode="full")[n - 1:]
        if acf[0] <= 1e-9:
            return None
        acf = acf / acf[0]
        lo = int(np.floor(60.0 * self.fps / BPM_MAX))
        hi = int(np.ceil(60.0 * self.fps / BPM_MIN))
        hi = min(hi, n - 2)
        if hi <= lo + 2:
            return None
        lags = np.arange(lo, hi + 1)
        bpms = 60.0 * self.fps / lags
        # prior แบบ log-gaussian รอบ 120 BPM — แก้ปัญหาเลือกครึ่ง/สองเท่า
        prior = np.exp(-0.5 * (np.log2(bpms / 120.0) / 0.9) ** 2)
        # รวม harmonic (2 เท่าของ lag) ช่วยยืนยันคาบที่ถูก
        acf2 = np.array([acf[min(2 * L, n - 1)] for L in lags])
        score = (acf[lags] + 0.5 * acf2) * prior
        i = int(np.argmax(score))
        lag = float(lags[i])
        if 0 < i < len(lags) - 1:     # parabolic interpolation
            a, b, c = score[i - 1], score[i], score[i + 1]
            den = a - 2 * b + c
            if abs(den) > 1e-12:
                lag += 0.5 * (a - c) / den
        conf = float(np.clip(acf[lags[i]], 0.0, 1.0))
        return 60.0 * self.fps / lag, conf

    def last_beat_time(self, bpm: float) -> float | None:
        """หาเวลาของ beat ล่าสุด (comb filter ตามคาบของ bpm)"""
        e = self._clean_env()
        n = e.size
        if n < self.fps * 2:
            return None
        period = 60.0 * self.fps / bpm
        n_beats = int((n - 1) / period)
        if n_beats < 2:
            return None
        best_phi, best = 0, -1.0
        for phi in range(int(period)):
            idx = (n - 1 - phi - np.round(np.arange(n_beats) * period)).astype(int)
            idx = idx[idx >= 0]
            # beat ใหม่ ๆ มีน้ำหนักมากกว่า
            w = np.linspace(1.0, 0.5, idx.size)
            s = float((e[idx] * w).sum())
            if s > best:
                best, best_phi = s, phi
        times = list(self.times)
        return times[n - 1 - best_phi]


class BeatTracker:
    """นาฬิกาจังหวะที่ล็อกกับเพลงที่กำลังเล่น (thread แยก)"""

    def __init__(self, default_bpm: float = 120.0, update_s: float = 0.5,
                 use_loopback: bool = True):
        self.default_bpm = float(default_bpm)
        self.update_s = update_s
        self.use_loopback = use_loopback
        self.analyzer = OnsetAnalyzer()
        self.available = False          # จับเสียง loopback ได้จริงไหม
        self.confidence = 0.0
        self.last_sound = 0.0           # เวลาล่าสุดที่ได้ยินเสียง (time.time())
        self.first_sound = 0.0
        self.intensity = 0.0            # ความดังเทียบช่วงล่าสุด 0..1
        self.accent = 0.0               # ความแรงของเสียงกลอง/onset ล่าสุด 0..1
        self._peak_flux = 1e-3
        self._peak_rms = LOUD_FLOOR
        self._ms = 0.0                  # mean-square แบบ EMA ~1 วินาที (ความดังช่วงนี้)
        self._period = 60.0 / self.default_bpm
        self._ref = time.time()         # เวลาของ beat อ้างอิง
        self._base = 0.0                # เลขจังหวะ ณ _ref
        self._pending = None            # (bpm, จำนวนครั้งที่เจอติดกัน) — กันเปลี่ยนจังหวะมั่ว
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------- นาฬิกาจังหวะ ----------
    @property
    def bpm(self) -> float:
        return 60.0 / self._period

    @property
    def audible(self) -> bool:
        """ได้ยินเสียงใน 1.5 วินาทีที่ผ่านมาไหม"""
        return self.last_sound > 0 and (time.time() - self.last_sound) < 1.5

    def beat_position(self, t: float | None = None) -> float:
        """เลขจังหวะต่อเนื่อง ณ เวลา t (ค่าจำนวนเต็ม = ลงจังหวะพอดี)"""
        t = time.time() if t is None else t
        with self._lock:
            return self._base + (t - self._ref) / self._period

    def _set_tempo(self, bpm: float) -> None:
        """เปลี่ยนคาบโดยเลข beat ไม่กระโดด (ย้าย ref มาที่ปัจจุบันก่อน)"""
        now = time.time()
        self._base += (now - self._ref) / self._period
        self._ref = now
        self._period = 60.0 / bpm

    def _correct_phase(self, beat_t: float, gain: float = 0.35) -> None:
        """PLL: ดึงจังหวะเข้าหา beat ที่วัดได้ทีละนิด"""
        pos = self._base + (beat_t - self._ref) / self._period
        err = pos - round(pos)               # -0.5..0.5 จังหวะ
        self._base -= gain * err

    def update_from_analyzer(self) -> None:
        """ประมาณ tempo/phase ใหม่จากเสียงที่สะสม (เรียกทุก ~0.5 วินาที)"""
        est = self.analyzer.estimate_tempo()
        if est is None:
            return
        bpm, conf = est
        self.confidence = conf
        if conf < 0.08:
            return
        with self._lock:
            cur = self.bpm
            ratio = bpm / cur
            if abs(ratio - 1.0) < 0.04:
                self._set_tempo(cur + 0.3 * (bpm - cur))      # ปรับละเอียด
                self._pending = None
            else:
                # จังหวะต่างมาก → ต้องเจอซ้ำก่อนเปลี่ยน (หรือยังไม่เคยล็อก)
                # สองเท่า/ครึ่งหนึ่ง (เช่น 92↔182) มักเป็นการนับ hi-hat แทนกลอง →
                # ต้องยืนยันนานกว่ามาก (~4 วินาที) กันหุ่นเต้นเร็วขึ้นเท่าตัวกะทันหัน
                octave = min(abs(ratio - 2.0), abs(ratio - 0.5)) < 0.08
                need = 8 if octave else 2
                p = self._pending
                if p and abs(p[0] / bpm - 1.0) < 0.04:
                    self._pending = (bpm, p[1] + 1)
                else:
                    self._pending = (bpm, 1)
                if self._pending[1] >= need or self.first_sound == 0.0:
                    self._set_tempo(bpm)
                    self._pending = None
            bt = self.analyzer.last_beat_time(self.bpm)
            if bt is not None:
                self._correct_phase(bt)

    def feed(self, mono: np.ndarray, t_end: float) -> None:
        """ป้อนเสียงเข้าตัววิเคราะห์ (ใช้ทั้งจาก loopback และในการทดสอบ)"""
        self.analyzer.feed(mono, t_end)
        rms = self.analyzer.rms
        # ความดังเฉลี่ย ~1 วินาที เทียบยอดที่ค่อย ๆ ลด (~1 นาที) — มีพื้นขั้นต่ำ
        # (intro เบา ๆ จะไม่ถูกนับว่าดังสุดเพียงเพราะยังไม่เคยได้ยินท่อนดัง)
        dur = max(np.asarray(mono).size / self.analyzer.sr, 1e-3)
        self._ms += (rms * rms - self._ms) * min(1.0, dur / 1.0)
        loud = float(np.sqrt(self._ms))
        self._peak_rms = max(loud, LOUD_FLOOR, self._peak_rms * (1.0 - dur / 60.0))
        self.intensity = float(np.clip(loud / self._peak_rms, 0.0, 1.0))
        flux = self.analyzer.last_flux
        self._peak_flux = max(flux, self._peak_flux * 0.998)
        rel = flux / self._peak_flux if self._peak_flux > 1e-6 else 0.0
        self.accent = float(np.clip((rel - 0.4) / 0.6, 0.0, 1.0)) if rms > SILENCE_RMS else 0.0
        if rms > SILENCE_RMS:
            self.last_sound = t_end
            if self.first_sound == 0.0:
                self.first_sound = t_end

    # ---------- thread ----------
    def start(self) -> "BeatTracker":
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self._ref = time.time()
        self._base = 0.0
        self._thread = threading.Thread(target=self._run, daemon=True, name="BeatTracker")
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None

    def _open_loopback(self):
        import soundcard as sc

        # soundcard init COM เฉพาะ thread ที่ import ครั้งแรก — thread นี้ต้อง init เอง
        # (เรียกหลัง import: ถ้า init แล้วจะได้ S_FALSE เฉย ๆ ไม่เป็นไร)
        try:
            import ctypes

            ctypes.windll.ole32.CoInitializeEx(None, 0)    # COINIT_MULTITHREADED
        except Exception:  # noqa: BLE001 — ไม่ใช่ Windows
            pass
        spk = sc.default_speaker()
        mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
        return mic, spk.name

    def _run(self) -> None:
        if not self.use_loopback:
            self._idle_loop()
            return
        try:
            mic, name = self._open_loopback()
            with mic.recorder(samplerate=SR, channels=2, blocksize=HOP * 2) as rec:
                self.available = True
                _log(f"[Beat] 🎧 ฟังเสียงจากลำโพง: {name}")
                last_update = time.time()
                while not self._stop.is_set():
                    data = rec.record(numframes=HOP * 4)       # ~43 ms
                    now = time.time()
                    mono = data.mean(axis=1) if data.ndim == 2 else data
                    self.feed(mono, now)
                    if now - last_update >= self.update_s:
                        last_update = now
                        self.update_from_analyzer()
        except Exception as exc:  # noqa: BLE001 — ไม่มีอุปกรณ์ → เดินจังหวะเอง
            self.available = False
            _log(f"[Beat] ⚠️ ฟังเสียงลำโพงไม่ได้ ({exc}) — ใช้จังหวะคงที่ "
                  f"{self.default_bpm:.0f} BPM")
            self._idle_loop()

    def _idle_loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(0.2)


def synth_clicks(bpm: float, seconds: float, sr: int = SR,
                 offset: float = 0.0) -> np.ndarray:
    """สร้างเสียงกลอง (click) ตามจังหวะ — ใช้ทดสอบ"""
    n = int(seconds * sr)
    out = np.random.default_rng(0).normal(0, 0.002, n).astype(np.float32)
    period = 60.0 / bpm
    t = offset
    click_len = int(0.03 * sr)
    env = np.exp(-np.linspace(0, 8, click_len)).astype(np.float32)
    tone = np.sin(2 * np.pi * 120 * np.arange(click_len) / sr).astype(np.float32)
    noise = np.random.default_rng(1).normal(0, 1, click_len).astype(np.float32)
    click = (0.6 * tone + 0.4 * noise) * env
    while t < seconds:
        i = int(t * sr)
        j = min(n, i + click_len)
        out[i:j] += click[:j - i]
        t += period
    return out
