# Reachy Mini DIY — Development Guide for AI Agents

คู่มือสำหรับ AI coding agent (Copilot, Claude Code, Cursor, Codex) ที่จะช่วยพัฒนา
โปรเจกต์หุ่นยนต์ Reachy Mini แบบ DIY

## ⚡️ โปรเจกต์นี้คืออะไร

หุ่นยนต์ **Reachy Mini แบบ DIY** สร้างจาก:
- **Raspberry Pi 5** — สมอง
- **USB Camera** — ตา (OpenCV + MediaPipe)
- **มอเตอร์ STS3215** (Feetech, 7.4V, 19kg·cm) — กล้ามเนื้อ 9 ตัว
- สื่อสารผ่าน Feetech serial bus (half-duplex TTL) ผ่าน USB-TTL adapter

> ⚠️ ต่างจาก Reachy Mini ของแท้ (Dynamixel + บอร์ดทางการ) — โค้ดนี้ควบคุม STS3215
> โดยตรง ไม่ใช้ daemon ทางการสำหรับฮาร์ดแวร์

---

## 📁 โครงสร้างโปรเจกต์

```
Reachy Mini/
├── config/
│   ├── robot_config.py      # ค่าตั้งค่าเริ่มต้น + get_config()/save_calibration()
│   └── calibration.json     # ⚠️ ค่าจาก calibrate (ห้ามแก้มือ — ใช้ scripts/calibrate.py)
├── src/
│   ├── servo_bus.py         # ไดรเวอร์ Feetech STS3215 (protocol + sync write + read)
│   ├── stewart.py           # Stewart platform 6-DOF: IK (leadscrew/crank_rod) + FK
│   ├── robot.py             # ชั้นควบคุมระดับสูง Robot (backend: sim / hardware)
│   ├── sim_robot.py         # หุ่นจำลอง (text log)
│   ├── mujoco_sim.py        # จำลองหุ่น DIY ใน MuJoCo (GUI 3D, รองรับ STL mesh)
│   ├── sim_gui.py           # GUI 3D แบบ matplotlib (สำรอง)
│   ├── camera.py            # อ่าน USB camera
│   ├── vision.py            # ติดตามมือ (MediaPipe / fallback skin)
│   ├── beat.py              # จับจังหวะเพลงจากเสียงลำโพง (loopback → BPM + phase)
│   └── dance_sync.py        # เต้นตามจังหวะ หลายหุ่น/หลายโหมด (together/alternate/canon/mirror/free/show)
├── scripts/
│   ├── self_test.py         # ตรวจสอบโค้ดทั้งหมด (รันก่อนส่งงานเสมอ!)
│   ├── calibrate.py         # calibrate อัตโนมัติ (geometric/zero/verify)
│   ├── scan_servos.py       # สแกนหา ID มอเตอร์
│   ├── set_servo_id.py      # ตั้ง ID มอเตอร์
│   ├── test_servos.py       # ทดสอบมอเตอร์ (sweep + read)
│   ├── demo_wave.py         # สาธิตทักทาย
│   ├── demo_hand_tracking.py# ติดตามมือด้วยกล้อง USB
│   ├── two_robots_music_dance.py # 2 หุ่นเต้นตามเพลง YouTube (ฟังจังหวะจากลำโพง)
│   ├── run_simulation.py    # เปิด MuJoCo sim
│   └── generate_sample_stls.py  # สร้าง STL ตัวอย่าง
├── models/stl/              # ไฟล์ STL ชิ้นส่วน (ใช้ใน MuJoCo sim)
├── third_party/             # reference ทางการ (reachy_mini, reachy_description)
├── .venv/                   # Python 3.14 — dependencies ของโปรเจกต์ DIY
└── reachy_mini_env/         # Python 3.12 — official SDK (reachy-mini[mujoco]) แยกต่างหาก
```

---

## 🐍 สภาพแวดล้อม (สำคัญมาก!)

| venv | Python | ใช้ทำอะไร | รันยังไง |
|------|--------|-----------|---------|
| `.venv` | 3.14 | **โปรเจกต์ DIY นี้** (numpy, pyserial, opencv, mujoco, mediapipe) | `.venv\Scripts\python.exe` |
| `reachy_mini_env` | 3.12 | official SDK `reachy-mini[mujoco]` (sim หุ่นแท้) | `reachy_mini_env\Scripts\python.exe` |

> ⚠️ **`python` ใน PowerShell terminal = system Python 3.14 ที่ไม่มีแพ็กเกจ!**
> ต้องเรียกด้วย `.venv\Scripts\python.exe` เสมอ (หรือ activate .venv ก่อน)
>
> ⚠️ PowerShell: ถ้า path มีช่องว่าง ใช้ `& "path\python.exe" script.py`
> (quoting path โดยไม่มี `&` จะเกิด ParserError)

---

## 🎯 API หลัก

```python
from src.robot import Robot

# โหมดจำลอง (มี GUI 3D MuJoCo)
with Robot(backend="sim", gui="mujoco") as robot:   # gui: False / "mujoco" / "matplotlib"
    robot.wake_up()
    robot.wave()
    robot.look_around()

# หุ่นจริง
with Robot(backend="hardware", port=None) as robot:  # port=None = auto-detect
    robot.set_head_pose(z=60, roll=10, pitch=-15, yaw=20, duration=1.0)  # z=mm, มุม=องศา
    robot.set_base(30)             # หมุนตัว (องศา)
    robot.set_antennas(1.0, -1.0)  # เสาอากาศ (เรเดียน)
    robot.get_positions()
```

### ชั้นล่าง (ถ้าต้องการควบคุมละเอียด)
```python
from src.servo_bus import ServoBus   # Feetech protocol
bus = ServoBus()
bus.ping(1); bus.set_position(1, 2048, speed=1000); bus.get_position(1)
bus.sync_set_position([(1, 1024), (2, 3072)])   # ขยับพร้อมกัน
```

### Stewart platform (src/stewart.py)
- `leg_endpoints(z, roll, pitch, yaw, ...)` — IK เชิงเรขาคณิต (จุดขา 6 ขา)
- `leg_lengths(...)` — ความยาวขา 6 ขา
- `length_to_servo_pos(...)` — ความยาว → servo pos ตาม `mechanism`
- กลไก 2 แบบ: `"leadscrew"` (สกรู, เส้นตรง) | `"crank_rod"` (แขน+ก้าน, 2-bar + solution 0/1)
- `forward_kinematics(lengths, ..., x0=...)` — FK (Newton) ⚠️ มีหลายคำตอบ ควรระบุ x0
- `servo_pos_to_length(...)` — inverse สำหรับ calibrate

---

## ⚙️ ระบบ config (ห้ามลืม!)

```python
from config.robot_config import get_config, save_calibration

cfg = get_config()   # DEFAULT_CONFIG + ผสาน calibration.json อัตโนมัติ
```

**กฎ:**
- ✅ ใช้ `get_config()` ในโค้ดที่ต้องการค่าล่าสุด (Robot ทำแล้ว)
- ❌ **ห้ามแก้ `config/calibration.json` ด้วยมือ** — ใช้ `scripts/calibrate.py`
- ค่า calibration: `leg_home`, `leg_home_pos` (ตำแหน่ง home ต่อขา)
- `servo_ids`: head=[1..6], base=7, antennas=[8,9]
- safety limits อยู่ใน `config["limits"]` — ฟังก์ชัน Robot clamp ให้แล้ว

---

## 🧪 วิธีทดสอบ (ทำเสมอหลังแก้โค้ด!)

```powershell
.venv\Scripts\python.exe scripts\self_test.py
```
มี test: frame Feetech, IK, FK, crank_rod round-trip, mechanism round-trip, sim,
MuJoCo (render offscreen), STL mesh, get_config — ต้องผ่านทั้งหมดก่อนสรุปงาน

---

## 🚀 วิธีรัน/สาธิต

```powershell
.venv\Scripts\python.exe scripts\run_simulation.py --hold   # MuJoCo 3D (ค้างหน้าต่าง)
.venv\Scripts\python.exe scripts\demo_wave.py               # ทักทาย (sim + GUI)
.venv\Scripts\python.exe scripts\demo_hand_tracking.py      # กล้อง USB + หุ่น
.venv\Scripts\python.exe scripts\calibrate.py               # calibrate geometric
.venv\Scripts\python.exe scripts\calibrate.py --hardware    # + zero (ต้องมีหุ่น)

# --- community app (Reachy ทางการ) บนหุ่น STS3215 ---
reachy_mini_env\Scripts\reachy-mini-daemon.exe --sts3215 --no-media
#   - ถ้าไม่ต่อ USB-TTL → dry-run (เหมือน sim, ไม่ขยับจริง)
#   - ถ้าต่อแล้ว → ขับ STS3215 จริงอัตโนมัติ (ผ่าน backend ใน third_party)
#   - แล้วใช้ SDK / install app ผ่าน http://127.0.0.1:8000/docs ได้เลย
```

> ⚠️ `reachy_mini_env` ติดตั้งแบบ **editable** ชี้ไป `third_party/reachy_mini/src` แล้ว
> — การแก้ backend ใน third_party มีผลทันที (backend ของเราอยู่ที่
> `third_party/.../daemon/backend/sts3215/`)

---

## 📌 กฎสำหรับ Agent

1. **เขียน `plan.md` ก่อน** งานใหญ่ (หลายไฟล์/ฟีเจอร์ใหม่) — ถามคำถามผู้ใช้ก่อนเขียนโค้ด
2. **รัน `self_test.py` ให้ผ่าน** ก่อนสรุปว่าจบงาน
3. **ภาษา**: โค้ดคอมเมนต์/docstring เป็นภาษาไทย (ตามโปรเจกต์) — คำตอบกับผู้ใช้เป็นภาษาไทย
4. **อย่าแตะ** `calibration.json`, `third_party/`, `reachy_mini_env/` โดยไม่จำเป็น
   (ยกเว้น: `third_party/.../daemon/backend/sts3215/` = backend ที่เราเขียนเอง — แก้ได้)
5. **หุ่น DIY ควบคุมผ่าน `src/servo_bus.py` + `src/robot.py`** (STS3215) —
   อย่าใช้ daemon ทางการโดยตรง **ยกเว้น** community app ที่ใช้ `--sts3215`
   (backend เราแปล official pose → STS3215 ให้แล้ว)
6. ถ้างานเกี่ยวกับการเคลื่อนไหวหัว ให้ใช้ `src/robot.py` / `src/stewart.py` — อย่าเขียน IK ซ้ำ
7. `requirements.txt` = core deps, `requirements-vision.txt` = mediapipe (optional)

---

## 🛠️ หมายเหตุฮาร์ดแวร์

- STS3215 เป็น **half-duplex** — USB-TTL ต้องต่อ RX (ผ่านไดโอด) ถึงจะอ่าน feedback ได้
- Baudrate default = 1,000,000
- ไฟ 7.4V (2S LiPo) แยกจาก logic 5V ของ RPi
- ยังไม่มีชิ้นส่วนจริง — งานส่วนใหญ่ตอนนี้เป็น sim/software (ระยะ 0-1)
