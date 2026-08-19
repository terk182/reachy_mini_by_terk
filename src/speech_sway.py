"""Audio-reactive head sway — พอร์ตจาก official Reachy Mini (`motion/speech_tapper.py`)

วิเคราะห์ PCM เสียงพูด → สร้าง offset 6 แกนต่อ hop (50ms) ให้หัวส่าย/พยักตามจังหวะ
และความดังของเสียงจริง (VAD + loudness envelope) — เนียนกว่า sine ง่าย ๆ มาก

ใช้กับหุ่น DIY (nod_axis="roll", หน้า=+Y):
    official pitch (ก้ม/เงย) → DIY roll
    official roll (เอียง)     → DIY pitch
    official yaw              → DIY yaw

ไม่ต้องพึ่ง GStreamer — ใช้แค่ numpy + math (+ miniaudio สำหรับ decode MP3)
"""
from __future__ import annotations

import math

import numpy as np

# ---------------------------------------------------------------------------
# Tunables (เหมือน official reachy_mini/motion/speech_tapper.py)
# ---------------------------------------------------------------------------
FRAME_MS = 20
HOP_MS = 50
SWAY_MASTER = 1.5
SENS_DB_OFFSET = 4.0
VAD_DB_ON = -35.0
VAD_DB_OFF = -45.0
VAD_ATTACK_MS = 40
VAD_RELEASE_MS = 250
ENV_FOLLOW_GAIN = 0.65

SWAY_F_PITCH = 2.2
SWAY_A_PITCH_DEG = 9.0     # เดิม 4.5 — ขยายให้เห็นชัด (nod)
SWAY_F_YAW = 0.6
SWAY_A_YAW_DEG = 10.0
SWAY_F_ROLL = 1.3
SWAY_A_ROLL_DEG = 4.5      # เดิม 2.25 — ขยาย (tilt)
SWAY_F_X = 0.35
SWAY_A_X_MM = 4.5
SWAY_F_Y = 0.45
SWAY_A_Y_MM = 3.75
SWAY_F_Z = 0.25
SWAY_A_Z_MM = 2.25

SWAY_DB_LOW = -46.0
SWAY_DB_HIGH = -18.0
LOUDNESS_GAMMA = 0.9
SWAY_ATTACK_MS = 50
SWAY_RELEASE_MS = 250

ATTACK_FR = max(1, int(VAD_ATTACK_MS / HOP_MS))
RELEASE_FR = max(1, int(VAD_RELEASE_MS / HOP_MS))
SWAY_ATTACK_FR = max(1, int(SWAY_ATTACK_MS / HOP_MS))
SWAY_RELEASE_FR = max(1, int(SWAY_RELEASE_MS / HOP_MS))


def _rms_dbfs(x: np.ndarray) -> float:
    """RMS ใน dBFS ของ float32 mono [-1,1]"""
    x = x.astype(np.float32, copy=False)
    rms = np.sqrt(np.mean(x * x, dtype=np.float32) + 1e-12, dtype=np.float32)
    return float(20.0 * math.log10(float(rms) + 1e-12))


def _loudness_gain(db: float, offset: float = SENS_DB_OFFSET) -> float:
    """Normalize dB → [0,1] ด้วย gamma"""
    t = (db + offset - SWAY_DB_LOW) / (SWAY_DB_HIGH - SWAY_DB_LOW)
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    return t ** LOUDNESS_GAMMA if LOUDNESS_GAMMA != 1.0 else t


class SwayRollRT:
    """Feed PCM float32 mono → คืน list ของ sway dict (1 ตัวต่อ HOP_MS)"""

    def __init__(self, rng_seed: int = 7, sample_rate: int = 16000):
        self._seed = int(rng_seed)
        self.sample_rate = int(sample_rate)
        self.frame = int(self.sample_rate * FRAME_MS / 1000)
        self.hop = int(self.sample_rate * HOP_MS / 1000)
        self.samples: np.ndarray = np.zeros(0, dtype=np.float32)
        self.carry: np.ndarray = np.zeros(0, dtype=np.float32)

        self.vad_on = False
        self.vad_above = 0
        self.vad_below = 0

        self.sway_env = 0.0
        self.sway_up = 0
        self.sway_down = 0

        rng = np.random.default_rng(self._seed)
        self.phase_pitch = float(rng.random() * 2 * math.pi)
        self.phase_yaw = float(rng.random() * 2 * math.pi)
        self.phase_roll = float(rng.random() * 2 * math.pi)
        self.phase_x = float(rng.random() * 2 * math.pi)
        self.phase_y = float(rng.random() * 2 * math.pi)
        self.phase_z = float(rng.random() * 2 * math.pi)
        self.t = 0.0

    def reset(self) -> None:
        self.samples = np.zeros(0, dtype=np.float32)
        self.carry = np.zeros(0, dtype=np.float32)
        self.vad_on = False
        self.vad_above = 0
        self.vad_below = 0
        self.sway_env = 0.0
        self.sway_up = 0
        self.sway_down = 0
        self.t = 0.0

    def feed(self, pcm: np.ndarray) -> list[dict]:
        """ป้อน PCM float32 mono (N,) → list ของ sway dict ต่อ hop"""
        if pcm.size == 0:
            return []

        if self.carry.size:
            self.carry = np.concatenate([self.carry, pcm])
        else:
            self.carry = pcm

        out: list[dict] = []

        while self.carry.size >= self.hop:
            hop = self.carry[: self.hop]
            self.carry = self.carry[self.hop:]

            if self.samples.size:
                self.samples = np.concatenate([self.samples, hop])[-self.frame:]
            else:
                self.samples = hop[-self.frame:].copy()
            if self.samples.size < self.frame:
                self.t += HOP_MS / 1000.0
                continue

            frame = self.samples
            db = _rms_dbfs(frame)

            # VAD + hysteresis (attack/release)
            if db >= VAD_DB_ON:
                self.vad_above += 1
                self.vad_below = 0
                if not self.vad_on and self.vad_above >= ATTACK_FR:
                    self.vad_on = True
            elif db <= VAD_DB_OFF:
                self.vad_below += 1
                self.vad_above = 0
                if self.vad_on and self.vad_below >= RELEASE_FR:
                    self.vad_on = False

            if self.vad_on:
                self.sway_up = min(SWAY_ATTACK_FR, self.sway_up + 1)
                self.sway_down = 0
            else:
                self.sway_down = min(SWAY_RELEASE_FR, self.sway_down + 1)
                self.sway_up = 0

            up = self.sway_up / SWAY_ATTACK_FR
            down = 1.0 - (self.sway_down / SWAY_RELEASE_FR)
            target = up if self.vad_on else down
            self.sway_env += ENV_FOLLOW_GAIN * (target - self.sway_env)
            if self.sway_env < 0.0:
                self.sway_env = 0.0
            elif self.sway_env > 1.0:
                self.sway_env = 1.0

            loud = _loudness_gain(db) * SWAY_MASTER
            env = self.sway_env
            self.t += HOP_MS / 1000.0

            pitch = (
                math.radians(SWAY_A_PITCH_DEG)
                * loud * env
                * math.sin(2 * math.pi * SWAY_F_PITCH * self.t + self.phase_pitch)
            )
            yaw = (
                math.radians(SWAY_A_YAW_DEG)
                * loud * env
                * math.sin(2 * math.pi * SWAY_F_YAW * self.t + self.phase_yaw)
            )
            roll = (
                math.radians(SWAY_A_ROLL_DEG)
                * loud * env
                * math.sin(2 * math.pi * SWAY_F_ROLL * self.t + self.phase_roll)
            )
            x_mm = SWAY_A_X_MM * loud * env * math.sin(2 * math.pi * SWAY_F_X * self.t + self.phase_x)
            y_mm = SWAY_A_Y_MM * loud * env * math.sin(2 * math.pi * SWAY_F_Y * self.t + self.phase_y)
            z_mm = SWAY_A_Z_MM * loud * env * math.sin(2 * math.pi * SWAY_F_Z * self.t + self.phase_z)

            out.append({
                "pitch_rad": pitch,
                "yaw_rad": yaw,
                "roll_rad": roll,
                "x_mm": x_mm,
                "y_mm": y_mm,
                "z_mm": z_mm,
            })

        return out


# ---------------------------------------------------------------------------
# decode + precompute
# ---------------------------------------------------------------------------
def decode_mp3(path: str, target_sr: int = 16000) -> tuple[np.ndarray, int]:
    """MP3 → float32 mono PCM (target_sr) ใช้ miniaudio (built-in decoder)"""
    import miniaudio

    dec = miniaudio.decode_file(
        path,
        nchannels=1,
        sample_rate=target_sr,
        output_format=miniaudio.SampleFormat.FLOAT32,
    )
    return np.frombuffer(dec.samples, dtype=np.float32), int(dec.sample_rate)


def compute_offsets(pcm: np.ndarray, sample_rate: int = 16000) -> list[dict]:
    """feed PCM ทั้งหมด → list ของ sway dict (1 ตัวต่อ HOP_MS)"""
    rt = SwayRollRT(sample_rate=sample_rate)
    return rt.feed(np.asarray(pcm, dtype=np.float32))


def sway_to_pose(sway: dict, nod_axis: str = "roll") -> dict:
    """แปลง sway dict → kwargs สำหรับ robot.set_head_pose (มุมเป็นองศา)

    DIY (หน้า=+Y, nod_axis="roll"): official pitch → roll (ก้ม/เงย), roll → pitch (เอียง)
        — ไม่ส่ง yaw เพราะ Stewart yaw เสื่อมเมื่อจานอยู่ตรง (ดู robot.py look_around)
    official (หน้า=+X, nod_axis="pitch"): ใช้ตรง ๆ (มี neck yaw จริง)
    """
    nod = math.degrees(sway["pitch_rad"])    # official pitch = ก้ม/เงย
    tilt = math.degrees(sway["roll_rad"])    # official roll = เอียง
    if nod_axis == "roll":
        return {"roll": nod, "pitch": tilt}
    return {"pitch": nod, "roll": tilt, "yaw": math.degrees(sway["yaw_rad"])}
