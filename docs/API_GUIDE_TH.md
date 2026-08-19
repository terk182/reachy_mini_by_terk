# 📚 คู่มือการใช้งาน API — Reachy Mini DIY (STS3215)

คู่มือภาษาไทยสำหรับควบคุมหุ่น Reachy Mini DIY (มอเตอร์ Feetech STS3215)
ครอบคลุม 3 ชั้น API + ตัวอย่างครบวงจร

---

## 1. ภาพรวม — API มี 3 ชั้น

```
┌─────────────────────────────────────────────────────┐
│ ชั้น 3: Daemon REST API (HTTP :8000)                │ ← community app / SDK / browser
├─────────────────────────────────────────────────────┤
│ ชั้น 2: Python API (Robot / RealRobot)              │ ← โค้ด Python ของเรา
├─────────────────────────────────────────────────────┤
│ ชั้น 1: ServoBus (Feetech protocol, พอร์ต COM3)      │ ← คุยกับมอเตอร์โดยตรง
└─────────────────────────────────────────────────────┘
```

| ชั้น | ไฟล์/ที่มา | ใช้เมื่อ |
|------|-----------|---------|
| 1. ServoBus | `src/servo_bus.py` | ควบคุมมอเตอร์รายตัว (test/setup) |
| 2. Python API | `src/robot.py`, `src/real_robot.py` | เขียนโปรแกรมควบคุมหุ่น |
| 3. REST API | daemon (`reachy-mini-daemon.exe`) | community app, ควบคุมผ่าน network |

---

## 2. การเปิด daemon

### 2.1 หุ่นจริง STS3215 (backend ของเรา)
```powershell
cd "d:\Reachy Mini"
reachy_mini_env\Scripts\reachy-mini-daemon.exe --sts3215 --no-media
```
- `--sts3215` = ใช้ backend ขับ STS3215 (ของเรา)
- `--no-media` = ปิดกล้อง/เสียง (เฟส 2 ค่อยเปิด)
- ดู log: `[STS3215] hardware พร้อม (port=COM3)` = เชื่อมมอเตอร์สำเร็จ

### 2.2 โหมดจำลอง (หุ่นแท้ MuJoCo)
```powershell
reachy_mini_env\Scripts\reachy-mini-daemon.exe --sim --scene minimal
```

### 2.3 ตรวจว่า daemon พร้อม
- Swagger UI: **http://127.0.0.1:8000/docs** (กด Try it out ได้เลย)
- Health check: `GET /docs` ต้องตอบ 200 (⚠️ ไม่ใช่ `/api`)

---

## 3. Daemon REST API (ชั้น 3)

URL พื้นฐาน: `http://127.0.0.1:8000`

### 3.1 สั่งเคลื่อนไหว — `POST /api/move/goto`

```json
{
  "head_pose": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0.26, "yaw": 0.35},
  "antennas": [0.8, -0.8],
  "body_yaw": 0.52,
  "duration": 1.5,
  "interpolation": "minjerk"
}
```

| ฟิลด์ | หน่วย | ความหมาย |
|-------|-------|---------|
| `head_pose.x/y/z` | **เมตร** | ตำแหน่งหัว (z=0 คือท่า home) |
| `head_pose.roll/pitch/yaw` | **เรเดียน** | มุมหัว |
| `antennas` | เรเดียน `[ขวา, ซ้าย]` | เสาอากาศ |
| `body_yaw` | เรเดียน | หมุนตัว |
| `duration` | วินาที | เวลาเคลื่อนที่ |
| `interpolation` | — | `minjerk` (เนียน) / `linear` |

**ตัวอย่าง PowerShell:**
```powershell
$H = 'http://127.0.0.1:8000'
$b = @{ head_pose = @{x=0;y=0;z=0;roll=0;pitch=0.26;yaw=0.35};
        antennas = @(0.8,-0.8); body_yaw = 0.52;
        duration = 1.5; interpolation = 'minjerk' } | ConvertTo-Json
Invoke-RestMethod -Uri "$H/api/move/goto" -Method Post -ContentType 'application/json' -Body $b
```

### 3.2 ท่าทางสำเร็จรูป
```powershell
# ตื่น
Invoke-RestMethod -Uri "$H/api/move/play/wake_up" -Method Post -ContentType 'application/json' -Body '{}'
# นอน
Invoke-RestMethod -Uri "$H/api/move/play/goto_sleep" -Method Post -ContentType 'application/json' -Body '{}'
```

### 3.3 อ่านสถานะปัจจุบัน
```powershell
# ท่าหัว (เมตร/เรเดียน)
Invoke-RestMethod -Uri "$H/api/state/present_head_pose" -Method Get
# -> {x, y, z, roll, pitch, yaw}

# หมุนตัว (เรเดียน)
Invoke-RestMethod -Uri "$H/api/state/present_body_yaw" -Method Get

# เสาอากาศ [ขวา, ซ้าย] เรเดียน
Invoke-RestMethod -Uri "$H/api/state/present_antenna_joint_positions" -Method Get
```

### 3.4 Community app
```powershell
# รายชื่อแอป
Invoke-RestMethod -Uri "$H/api/apps/list-available" -Method Get
# ติดตั้ง (body = ข้อมูลแอปจาก list-available)
Invoke-RestMethod -Uri "$H/api/apps/install" -Method Post -ContentType 'application/json' -Body $appInfo
# เริ่มรันแอป
Invoke-RestMethod -Uri "$H/api/apps/start-app/wake_me_up" -Method Post -ContentType 'application/json' -Body '{}'
# หยุดแอปปัจจุบัน
Invoke-RestMethod -Uri "$H/api/apps/stop-current-app" -Method Post -ContentType 'application/json' -Body '{}'
```

### 3.5 สรุป endpoint สำคัญ

| Method | Path | หน้าที่ |
|--------|------|---------|
| POST | `/api/move/goto` | เคลื่อนไหว |
| POST | `/api/move/play/wake_up` | ตื่น |
| POST | `/api/move/play/goto_sleep` | นอน |
| GET | `/api/state/present_head_pose` | อ่านท่าหัว |
| GET | `/api/state/present_body_yaw` | อ่านมุมหมุนตัว |
| GET | `/api/state/present_antenna_joint_positions` | อ่านเสาอากาศ |
| GET | `/api/apps/list-available` | รายชื่อแอป |
| POST | `/api/apps/install` | ติดตั้งแอป |
| POST | `/api/apps/start-app/{name}` | เริ่มแอป |
| POST | `/api/apps/stop-current-app` | หยุดแอป |
| GET | `/docs` | Swagger UI |

---

## 4. Python API (ชั้น 2)

### 4.1 `RealRobot` — ควบคุมผ่าน daemon (หุ่นจริง/sim)

```python
from src.real_robot import RealRobot

with RealRobot() as r:
    r.wake_up()
    r.set_head_pose(z=70, roll=10, pitch=-15, yaw=20)  # z=mm, มุม=องศา
    r.set_base(30)               # หมุนตัว องศา
    r.set_antennas(0.8, -0.8)    # เรเดียน (ซ้าย, ขวา)
    r.wave()
    r.look_around()
```

| เมธอด | พารามิเตอร์ | หน่วย |
|-------|------------|-------|
| `set_head_pose(z, roll, pitch, yaw, duration)` | z สัมพัทธ์ home | mm / องศา |
| `set_base(angle_deg, duration)` | มุมหมุนตัว | องศา |
| `set_antennas(left, right, duration)` | เสาอากาศ | เรเดียน |
| `goto(head, antennas, body_yaw, duration, interpolation)` | ส่ง raw | เมตร/เรเดียน |
| `wake_up()` / `goto_sleep()` / `wave()` / `look_around()` | — | — |

### 4.2 `Robot` — ควบคุม STS3215 โดยตรง (ไม่ผ่าน daemon)

```python
from src.robot import Robot

# หุ่นจริง (port=None = auto-detect COM)
with Robot(backend="hardware", port=None) as robot:
    robot.wake_up()
    robot.set_head_pose(z=70, roll=10, pitch=-15, yaw=20)  # z=mm, มุม=องศา
    robot.set_base(30)             # องศา
    robot.set_antennas(1.0, -1.0)  # เรเดียน
    robot.wave()
    print(robot.get_positions())   # อ่านตำแหน่งมอเตอร์ทั้งหมด

# โหมดจำลอง (มี GUI 3D MuJoCo)
with Robot(backend="sim", gui="mujoco") as robot:
    robot.wave()
```

### 4.3 ความต่าง Robot vs RealRobot

| | `Robot` (DIY) | `RealRobot` (daemon) |
|---|---|---|
| คุยกับ | STS3215 โดยตรง (ServoBus) | official daemon (HTTP) |
| ใช้เมื่อ | ควบคุมหุ่น DIY เอง | community app / ผ่าน daemon |
| ต้องเปิด daemon | ❌ ไม่ต้อง | ✅ ต้อง |

---

## 5. ServoBus API (ชั้น 1 — ระดับมอเตอร์)

```python
from src.servo_bus import ServoBus

bus = ServoBus()                 # port=None = auto-detect COM3
bus.ping(1)                      # True/False — มอเตอร์ ID 1 ตอบไหม
bus.set_position(1, 2048, speed=1000)   # สั่งตำแหน่ง (0-4095)
bus.get_position(1)              # อ่านตำแหน่ง (0-4095)
bus.get_load(1)                  # อ่านแรงบิด
bus.get_voltage(1)               # อ่านแรงดัน (V)
bus.set_torque(1, True)          # เปิดแรงบิด (hold)
bus.set_torque(1, False)         # ปิด (limp)
bus.set_id(1, 2)                 # เปลี่ยน ID (ตัวเดียวบนบัส!)
bus.sync_set_position([(1, 1024), (2, 3072)], speed=1000)  # ขยับพร้อมกัน
bus.deg_to_pos(180.0)            # องศา -> ตำแหน่ง
bus.close()
```

**ค่าตำแหน่ง:** `0–4095` = `0°–360°`, กลาง = `2048`
**speed:** `0` = เร็วสุด, `1–4095` = จำกัดความเร็ว

---

## 6. หน่วย/หลักการสำคัญ

| เรื่อง | ค่า |
|-------|-----|
| ตำแหน่ง servo | 0–4095 (2048 = กึ่งกลาง) |
| REST `head_pose` | เมตร + เรเดียน (z=0 = home) |
| Python `set_head_pose` | mm + องศา |
| `antennas` ใน REST | `[ขวา, ซ้าย]` เรเดียน |
| `set_antennas()` ใน Python | `(ซ้าย, ขวา)` เรเดียน |
| Baudrate | 1,000,000 |
| Servo ID | head=1–6, base=7, antennas=8–9 |
| ไฟมอเตอร์ | 7.4V (แยกจาก 5V logic) |

---

## 7. ตัวอย่างครบวงจร

### 7.1 ส่งท่า + อ่านค่ากลับ (PowerShell)
```powershell
$H = 'http://127.0.0.1:8000'
# ก้มหัว 15° + เอียง 20° + หมุนตัว 30°
$b = @{ head_pose = @{x=0;y=0;z=0;roll=0;pitch=[math]::PI/12;yaw=[math]::PI/9};
        body_yaw=[math]::PI/6; duration=1.5; interpolation='minjerk' } | ConvertTo-Json
Invoke-RestMethod -Uri "$H/api/move/goto" -Method Post -ContentType 'application/json' -Body $b
Start-Sleep -Seconds 2
Invoke-RestMethod -Uri "$H/api/state/present_head_pose" -Method Get
```

### 7.2 สุ่มท่าทางวนลูป (Python)
```python
from src.real_robot import RealRobot
import random

r = RealRobot()
for _ in range(20):
    r.set_head_pose(
        z=random.uniform(58, 82),
        roll=random.uniform(-30, 30),
        pitch=random.uniform(-30, 30),
        yaw=random.uniform(-60, 60),
        duration=0.8)
```

### 7.3 สคริปต์สำเร็จรูปในโปรเจกต์
```powershell
.venv\Scripts\python.exe scripts\demo_wave.py              # ทักทาย (sim)
.venv\Scripts\python.exe scripts\demo_hand_tracking.py     # ไล่ตามมือ (USB cam)
.venv\Scripts\python.exe scripts\demo_face_tracking.py     # ไล่ตามหน้า
.venv\Scripts\python.exe scripts\demo_random.py --real     # สุ่มท่าทาง (ผ่าน daemon)
.venv\Scripts\python.exe scripts\test_control_loop.py      # ทดสอบ control loop
.venv\Scripts\python.exe scripts\servo_setup_gui.py        # GUI setup servo
.venv\Scripts\python.exe scripts\chat_gui.py --real        # แชท + ขยับ (LLM)
```

---

## 8. แก้ปัญหาเบื้องต้น

| อาการ | สาเหตุ/วิธีแก้ |
|-------|---------------|
| `Access is denied` ตอนเปิด COM3 | มีโปรแกรมอื่นถือพอร์ต → ปิด GUI/daemon ก่อน |
| scan เจอ 0 ตัว | ไฟ 7.4V ยังไม่เข้า / สาย Data ผิด / baud ไม่ตรง |
| scan เจอ ID ปลอมหลายตัว | หลาย servo ยัง ID ซ้ำกัน → ตั้ง ID ทีละตัว |
| daemon `dry-run` | ไม่เจอ COM/motor → เช็คสาย/ไฟ + ปิด GUI |
| เขียน position แล้วไม่ขยับ | ต้องเปิด torque ก่อน + เขียน packet รวม (WritePosEx style) |
| terminal พิมพ์ ✅ ไม่ได้ | `chcp 65001` ก่อนรัน หรือ `$env:PYTHONUTF8=1` |

---

## 9. ไฟล์อ้างอิงในโปรเจกต์

- `src/servo_bus.py` — ไดรเวอร์ Feetech STS3215 (ชั้น 1)
- `src/robot.py` — Robot หุ่น DIY (ชั้น 2)
- `src/real_robot.py` — RealRobot ผ่าน daemon (ชั้น 2)
- `src/stewart.py` — IK/FK Stewart platform
- `third_party/reachy_mini/src/reachy_mini/daemon/...` — official daemon + backend STS3215 ของเรา
- `config/robot_config.py` — ค่าตั้งค่า + servo_ids + limits
- `docs/wiring_and_ids.html` — แผนผังตำแหน่ง ID + การเดินสาย
