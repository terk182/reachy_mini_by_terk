# 🤖 Reachy Mini DIY — สร้างจากศูนย์ด้วย Raspberry Pi 5 + USB Camera + STS3215

โปรเจกต์โค้ดควบคุมหุ่นยนต์ **Reachy Mini แบบ DIY** โดยใช้ชิ้นส่วนที่คุณมี:

- **Raspberry Pi 5** — สมองของหุ่น
- **USB Camera** — ตา (OpenCV + MediaPipe)
- **มอเตอร์ STS3215** (Feetech, 7.4V, 19 kg·cm) — กล้ามเนื้อ 9 ตัว

> ⚠️ หุ่นตัวนี้เป็น "Reachy-Mini-inspired" — ใช้ไฟล์ 3D ของทางการไม่ได้ และควบคุม
> มอเตอร์ด้วย Feetech protocol เอง (ไม่ใช้ daemon ทางการ) เพราะใช้ STS3215 + USB-TTL

---

## 🎯 ภาพรวม

| ส่วน | เทคโนโลยี |
|------|-----------|
| มอเตอร์ | STS3215 ×9 (หัว 6 + ฐาน 1 + เสาอากาศ 2) |
| การสื่อสาร | Feetech serial bus (half-duplex TTL) ผ่าน USB-TTL adapter |
| กล้อง | USB Camera + OpenCV + MediaPipe (hand tracking) |
| ภาษา | Python 3.10–3.12 |

### โครงสร้างมอเตอร์ (10 DOF)
- **หัว**: Stewart platform 6-DOF → STS3215 ID 1–6 (ขา 6 ขา)
- **ตัว**: หมุนซ้าย/ขวา → STS3215 ID 7
- **เสาอากาศ**: 2 ตัว → STS3215 ID 8, 9

---

## 📁 โครงสร้างโปรเจกต์

```
Reachy Mini/
├── config/
│   └── robot_config.py      # ตั้งค่า: ID มอเตอร์, เรขาคณิต, ขีดจำกัด
├── src/
│   ├── servo_bus.py         # ไดรเวอร์ Feetech STS3215 (protocol + sync write)
│   ├── stewart.py           # Stewart platform 6-DOF (Inverse Kinematics)
│   ├── robot.py             # ชั้นควบคุมระดับสูง (sim / hardware)
│   ├── sim_robot.py         # หุ่นยนต์จำลอง (ไม่ต้องมีฮาร์ดแวร์)
│   ├── mujoco_sim.py        # จำลองหุ่น DIY ใน MuJoCo (GUI 3D โต้ตอบได้)
│   ├── sim_gui.py           # GUI 3D แบบ matplotlib (ทางเลือกสำรอง)
│   ├── camera.py            # อ่าน USB camera
│   ├── vision.py            # ติดตามมือ (MediaPipe / fallback skin detection)
│   └── face_detector.py     # ติดตามใบหน้า (YuNet / OpenCV FaceDetectorYN)
├── scripts/
│   ├── scan_servos.py       # สแกนหา ID มอเตอร์
│   ├── set_servo_id.py      # ตั้ง ID มอเตอร์
│   ├── test_servos.py       # ทดสอบมอเตอร์ (sweep + อ่าน feedback)
│   ├── calibrate.py         # calibrate อัตโนมัติ (leg_home / leg_home_pos)
│   ├── demo_wave.py         # สาธิต: ทักทาย
│   ├── demo_hand_tracking.py# สาธิต: ติดตามมือด้วยกล้อง USB
│   ├── demo_face_tracking.py# สาธิต: ติดตามใบหน้าด้วยกล้อง USB
│   ├── run_simulation.py    # รันโหมดจำลอง (MuJoCo 3D)
│   └── self_test.py         # ตรวจสอบโค้ด (ไม่ต้องใช้ฮาร์ดแวร์)
├── models/
│   └── stl/                 # วางไฟล์ .stl ชิ้นส่วน (ใช้ใน MuJoCo sim)
├── requirements.txt
├── requirements-vision.txt
└── README.md
```

---

## 🚀 เริ่มใช้งาน

### 1. ติดตั้ง dependencies

```powershell
# Windows (เครื่องพัฒนา)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# ตัวเลือก: hand tracking แบบ MediaPipe (แนะนำ)
pip install -r requirements-vision.txt
```

```bash
# Raspberry Pi 5 (Linux)
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. ทดสอบโดยไม่ต้องมีฮาร์ดแวร์

```powershell
python scripts/self_test.py          # ตรวจสอบโค้ดทั้งหมด
python scripts/run_simulation.py     # ดูท่าทางจำลองใน MuJoCo 3D (default)
python scripts/run_simulation.py --gui-type matplotlib   # ใช้ matplotlib แทน
python scripts/run_simulation.py --no-gui   # แบบ text อย่างเดียว
python scripts/demo_wave.py          # โหมดจำลอง + MuJoCo 3D
```

### 3. ต่อฮาร์ดแวร์จริง

```powershell
# 1) สแกนหามอเตอร์
python scripts/scan_servos.py

# 2) ตั้ง ID ให้แต่ละตัว (ทีละตัวเท่านั้น!) เช่น
python scripts/set_servo_id.py --old 1 --new 1
python scripts/set_servo_id.py --old 1 --new 2

# 3) ทดสอบมอเตอร์
python scripts/test_servos.py 1 2 3 4 5 6 7 8 9

# 4) รันท่าทางจริง
python scripts/demo_wave.py --hardware

# 5) ติดตามมือด้วยกล้อง USB
python scripts/demo_hand_tracking.py --hardware --camera 0

# 6) ติดตามใบหน้าด้วยกล้อง USB (YuNet)
python scripts/demo_face_tracking.py --gui        # โหมดจำลอง + MuJoCo 3D
python scripts/demo_face_tracking.py --real       # โมเดล Reachy Mini แท้ (official daemon)
python scripts/demo_face_tracking.py --hardware   # หุ่นจริง
```

---

## 🔌 การเดินสายไฟ

```
STS3215 (3 สาย):
  🔴 VCC   → 7.4V (2S LiPo หรือ SMPS)   ← แยกจ่ายจาก logic
  ⚫ GND   → GND ร่วม
  ⚪ Signal → TX ของ USB-TTL (half-duplex)

Raspberry Pi 5 ──USB── [USB-TTL CH340/CP2102] ──Signal──┐
                                                       ├── มอเตอร์ ID 1..9
7.4V 2S LiPo ────────────── VCC / GND ─────────────────┘   (ต่ออนุกรม TTL bus)
```

> ⚠️ **Half-duplex**: STS3215 ใช้สายเดียวทั้งส่ง/รับ — USB-TTL ทั่วไปที่ต่อแค่ TX จะ
> **สั่งงานได้แต่ read feedback ไม่ได้** ต้องใช้บอร์ด half-duplex หรือต่อ RX ผ่านไดโอด
> (โค้ดสั่งเขียนทำงานได้ทุกกรณี — scan/read feedback ต้องมี RX)

### Baudrate
- default ของ STS3215 = **1,000,000** (ตรงกับค่าใน `robot_config.py`)
- ถ้าเปลี่ยนบอดของมอเตอร์: ใช้ `ServoBus.set_baud()` + แก้ค่าใน config

---

## 🧠 วิธีควบคุมโค้ด

```python
from src.robot import Robot

# โหมดจำลอง (ไม่ต้องมีหุ่น)
with Robot(backend="sim") as robot:
    robot.wake_up()
    robot.wave()
    robot.look_around()

# หุ่นจริง
with Robot(backend="hardware") as robot:
    robot.set_head_pose(z=60, roll=10, pitch=-15, yaw=20, duration=1.0)
    robot.set_base(30)            # หมุนตัว 30°
    robot.set_antennas(1.0, -1.0) # เสาอากาศ [ซ้าย, ขวา]
```

### Stewart platform (หัว 6 DOF)
- `StewartHead.set_pose(z, roll, pitch, yaw)` — คำนวณ IK ให้ความยาวขา 6 ขา
- ใช้ **sync write** ขยับ 6 มอเตอร์พร้อมกัน
- กลไกขา 2 แบบ (`stewart.mechanism` ใน config):
  - `"leadscrew"`: ขา = สกรู (ความยาว ∝ มุมมอเตอร์)
  - `"crank_rod"`: ขา = แขนหมุน + ก้านต่อ (แบบ Reachy ทางการ) — แก้ 2-bar triangle
    มี 2 คำตอบต่อขา เลือกด้วย `stewart.solution` (0/1)
- มี **FK** (`forward_kinematics`) สำหรับตรวจสอบ/calibrate: ความยาวขา -> ท่าหัว
  (Newton; ⚠️ Stewart FK มีหลายคำตอบ — ระบุ `x0` เพื่อล็อกท่าเดิม)
- ค่าเรขาคณิต (`base_radius`, `top_radius`, `leg_home`, `pitch`) ต้อง **calibrate ตามหุ่นจริง**
  ใน `config/robot_config.py`

### Calibrate อัตโนมัติ (scripts/calibrate.py)

```powershell
python scripts/calibrate.py                        # 1) geometric: คำนวณ leg_home จากเรขาคณิต
python scripts/calibrate.py --hardware             # 2) + zero: อ่านตำแหน่ง home จริง (จัดหัวให้ท่า home ก่อน)
python scripts/calibrate.py --verify --hardware    # 3) verify: สั่งท่า->อ่านกลับ->FK ตรวจสอบความแม่นยำ
```

| ขั้น | ทำอะไร | ต้องมีหุ่น |
|-----|--------|-----------|
| **geometric** | คำนวณ `leg_home` = ความยาวขาที่ท่า home (จากเรขาคณิต) | ❌ |
| **zero** | อ่านตำแหน่งมอเตอร์จริงตอนท่า home → บันทึก `leg_home_pos` (center เฉพาะขา) | ✅ |
| **verify** | สั่งท่า → อ่านกลับ → แปลงเป็นความยาว → FK → เปรียบเทียบ + รายงานความคลาดเคลื่อน | ✅ |

> ค่าที่ได้บันทึกใน `config/calibration.json` และโปรแกรมใช้ต่ออัตโนมัติ

### มอเตอร์โดยตรง (ชั้นล่าง)
```python
from src.servo_bus import ServoBus

bus = ServoBus()                 # auto-detect พอร์ต
bus.ping(1)                      # True/False
bus.set_position(1, 2048, speed=1000)   # กลางรอบ
bus.get_position(1)              # อ่าน feedback (ต้องมี RX)
bus.sync_set_position([(1, 1024), (2, 3072)])  # ขยับพร้อมกัน
bus.close()
```

---

## ⚙️ การตั้งค่า (config/robot_config.py)

ค่าที่ calibrate แล้วจะถูกบันทึกใน `config/calibration.json` และผสานทับอัตโนมัติ
(ผ่าน `get_config()`) — ใช้ `python scripts/calibrate.py` สร้างให้

| ค่า | ความหมาย |
|-----|---------|
| `port` | พอร์ตอนุกรม (`None` = auto-detect) |
| `baudrate` | 1,000,000 (default STS3215) |
| `servo_ids` | ID ของมอเตอร์แต่ละส่วน |
| `stewart.base_radius` | รัศมีจานล่าง (mm) |
| `stewart.top_radius` | รัศมีจานบน (mm) |
| `stewart.leg_home` | ความยาวขาที่ servo กลางรอบ (mm) |
| `stewart.pitch` | lead screw pitch (mm/รอบ) |
| `stewart.mechanism` | กลไกขา: `"leadscrew"` (สกรู) หรือ `"crank_rod"` (แขน+ก้าน แบบทางการ) |
| `stewart.arm_len` / `rod_len` | ความยาวแขนหมุน / ก้านต่อ (mm) — ใช้กับ `crank_rod` |
| `stewart.solution` | คำตอบศอกต่อขา (0=+, 1=−) — ใช้กับ `crank_rod` |
| `limits` | ขีดจำกัดความปลอดภัยของแต่ละแกน |

---

## 📌 หมายเหตุ

- **MuJoCo 3D (default)**: `src/mujoco_sim.py` สร้าง MJCF model ของหุ่น DIY เราเอง
  (ฐานหมุน + Stewart platform 6 ขา + หัว + เสาอากาศ) แล้วขับด้วย IK จริงจาก
  `stewart.py` เปิดหน้าต่างโต้ตอบได้ (ลากหมุน / scroll ซูม) ผ่าน `mujoco.viewer`
  - ถ้า `mujoco.viewer` เปิดไม่ได้ (เช่น ไม่มี GPU/GL) จะ fallback เป็น headless อัตโนมัติ
- **STL mesh (ใส่ชิ้นส่วนจริง)**: วางไฟล์ `.stl` ของชิ้นส่วน 3D print ลงใน
  `models/stl/` แล้วตั้ง `meshes.enabled = True` ใน `config/robot_config.py`
  — MuJoCo จะแสดงชิ้นส่วนจริงของคุณแทนรูปทรงพื้นฐาน
  (รายละเอียด coordinate frame ของแต่ละชิ้นดูใน `models/stl/README.md`)
- **matplotlib 3D (สำรอง)**: `--gui-type matplotlib` ใช้ได้ถ้าไม่อยากพึ่ง MuJoCo
- **Face detection**: `src/face_detector.py` ใช้ YuNet (OpenCV FaceDetectorYN) — โหลดโมเดล
  ~350KB อัตโนมัติครั้งแรก ไม่ต้องติดตั้งแพ็กเกจเพิ่ม เปิด demo ได้ด้วย
  `python scripts/demo_face_tracking.py` (หุ่นหันหน้าไปทางใบหน้า)
- **STT (พูดกับหุ่น)**: กดปุ่ม 🎤 ใน `chat_gui.py` แล้วพูดภาษาไทย -> แปลงเป็นข้อความ
  ด้วย faster-whisper (local, ใช้ GPU ถ้ามี) -> ส่งเข้า LLM
  ตั้งค่าได้ใน `config` ส่วน `stt` (model/duration/ภาษา)
- **Official simulation (MuJoCo)**: อยากเห็นโมเดล Reachy Mini ของแท้ 3D สวยๆ ใช้
  แพ็กเกจทางการได้: `pip install "reachy-mini[mujoco]"` แล้วรัน `reachy-mini-daemon --sim`
  (เป็นโมเดลของแท้ — ใช้สำหรับศึกษา/พัฒนาแอปเท่านั้น ไม่เกี่ยวกับมอเตอร์ DIY)
  - `src/real_robot.py` ขับโมเดลแท้ผ่าน REST API — ใช้ `--real` ใน demo/chat ได้
    (ต้องรัน official daemon ก่อน: `reachy_mini_env\Scripts\reachy-mini-daemon.exe --sim`)
- **license**: ไฟล์ดีไซน์ฮาร์ดแวร์ทางการเป็น CC BY-SA-NC (ห้ามใช้เชิงพาณิชย์) — โค้ดใน
  โปรเจกต์นี้เขียนใหม่เองทั้งหมด
- มีคำถามเพิ่มเติม: Discord community ของ Pollen Robotics
  https://discord.gg/2bAhWfXme9
