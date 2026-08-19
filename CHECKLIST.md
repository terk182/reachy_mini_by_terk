# 📋 CHECKLIST — สร้าง Reachy Mini DIY (STS3215)

รายการเช็คลิสต์สำหรับสร้างหุ่นทั้งหมด ติ๊กทีละขั้น

## 🏗️ ระยะ 0 — Software (ทำได้เลย ไม่ต้องมีชิ้นส่วน)
- [ ] `.venv\Scripts\python.exe scripts\self_test.py` ผ่านทั้งหมด
- [ ] `python scripts\run_simulation.py --hold` — เห็นหุ่น DIY ใน MuJoCo 3D
- [ ] `reachy_mini_env\Scripts\python.exe scripts\run_real_sim.py --hold` — เห็นโมเดลแท้
- [ ] `python scripts\demo_hand_tracking.py --gui` — กล้องติดตามมือ
- [ ] `python scripts\demo_face_tracking.py --gui` — กล้องติดตามใบหน้า
- [ ] `python scripts\chat_gui.py --real` — คุยกับหุ่น (LLM + ท่าทาง + เสียง)

## 🛒 ระยะ 1 — ซื้อชิ้นส่วน
### มอเตอร์/อิเล็กทรอนิกส์
- [ ] **STS3215 × 9** (หัว 6 + ฐาน 1 + เสาอากาศ 2) — 7.4V 19kg·cm
- [ ] **USB-TTL half-duplex** (CH340/CP2102 ที่ต่อ RX ได้!) — ต่อ RPi ↔ มอเตอร์
- [ ] **2S LiPo 7.4V** (หรือ SMPS 7.4V) + ขั้ว/ฟิวส์
- [ ] สาย Dupont + สายไฟสำหรับ bus + ตัวต้านทาน (ถ้าต้อง)
- [ ] แหล่งจ่าย/สาย 5V สำหรับ RPi 5

### ชิ้นส่วนกลไก (print/ซื้อ)
- [ ] จานล่าง Stewart (R=38) + ฐาน
- [ ] จานบน Stewart (R=30) + ตัวหัว
- [ ] แขนหมุน (crank) 40mm × 6 — ใช้ `crank_arm.stl` หรือ servo horn โลหะ
- [ ] ก้านต่อ (rod) 85mm × 6 + หัวบอล/ตลับลูกปืน — ใช้ `rod.stl`
- [ ] bracket ยึดมอเตอร์ + ตัวยึดกล้อง/เสาอากาศ
- [ ] สกรู M2.5/M3, แบริ่ง, น็อต

> 💡 ไฟล์ STL ตัวอย่างอยู่ใน `models/stl/` (สร้างด้วย
> `python scripts\generate_sample_stls.py`)

## 🔧 ระยะ 2 — ตั้ง ID มอเตอร์ (ทีละตัวเท่านั้น!)
- [ ] `python scripts\scan_servos.py` — เจอ ID 1
- [ ] ตั้ง ID: head = 1-6, base = 7, antennas = 8, 9
  ```
  python scripts\set_servo_id.py --old 1 --new 1   # ทีละตัว!
  python scripts\set_servo_id.py --old 1 --new 2
  ...
  ```
- [ ] `python scripts\test_servos.py 1 2 3 4 5 6 7 8 9` — sweep ครบ

## 🔌 ระยะ 3 — เดินสายไฟ
- [ ] ไฟ 7.4V → มอเตอร์ทุกตัว (VCC/GND) — **แยกจาก logic 5V ของ RPi**
- [ ] Bus TTL: Signal ต่อ USB-TTL (RX ผ่านไดโอดเพื่ออ่าน feedback)
- [ ] ตรวจแรงดันมอเตอร์ (ServoBus.get_voltage)

## 🧠 ระยะ 4 — ประกอบ + calibrate
- [ ] ประกอบหัว Stewart (จานล่าง + แขน + ก้าน + จานบน)
- [ ] ประกอบฐานหมุน + เสาอากาศ + กล้อง
- [ ] จัดหัวให้ท่า home (ระดับ, สูง z_home≈70mm)
- [ ] `python scripts\calibrate.py --hardware` — อ่านตำแหน่ง home จริง (leg_home_pos)
- [ ] `python scripts\calibrate.py --verify --hardware` — error ต้องต่ำ
  - ถ้า error มุมสูง → ตรวจสอบค่า base_radius/top_radius/arm_len/rod_len ใน config

## 🚀 ระยะ 5 — ทดสอบเต็มระบบ
- [ ] `python scripts\demo_wave.py --hardware` — ทักทาย
- [ ] `python scripts\demo_hand_tracking.py --hardware` — ไล่ตามมือ
- [ ] `python scripts\demo_face_tracking.py --hardware` — ไล่ตามใบหน้า
- [ ] `python scripts\chat_gui.py --hardware` — คุย + พูด + ขยับ

## 📌 หมายเหตุสำคัญ
- STS3215 เป็น **half-duplex** — USB-TTL ต้องต่อ RX ถึงจะอ่าน feedback ได้
  (สั่งอย่างเดียวต่อแค่ TX ได้)
- `config\calibration.json` ห้ามแก้มือ — ใช้ `scripts\calibrate.py`
- ถ้าอยากใช้กลไกแบบ lead screw แทน crank-rod → ตั้ง `stewart.mechanism="leadscrew"` + ปรับ `pitch`
