# Plan: รัน community app (Reachy Mini ทางการ) บนหุ่น DIY STS3215

## เป้าหมาย
ให้ community app จาก HuggingFace Spaces (ระบบ App ของ Reachy Mini ทางการ)
รันบนหุ่น DIY ที่ใช้มอเตอร์ **STS3215** ได้ โดยไม่ต้องเขียน app ใหม่

## หลักการ (สำคัญ)
- community app = subprocess ที่ใช้ `reachy_mini` SDK client คุยกับ daemon
  ผ่าน network (REST + WebSocket) — **app ไม่รู้ว่าเบื้องหลังเป็นมอเตอร์อะไร**
- ดังนั้นวิธีที่ถูก = ให้ **official daemon รันด้วย backend ตัวใหม่**
  (`STS3215Backend`) ที่แปลคำสั่ง head/antenna/body_yaw → STS3215 จริง
  (ผ่าน `src/servo_bus.py` + `src/stewart.py`)

## ขั้นตอน

1. **สร้าง backend ใหม่**
   - `third_party/reachy_mini/src/reachy_mini/daemon/backend/sts3215/backend.py`
   - `class STS3215Backend(MockupSimBackend)` — ลอกโครงจาก `MockupSimBackend`
     (มัน implement abstract methods + run loop + state ครบแล้ว)
   - override จุดที่ต้องต่อฮาร์ดแวร์:
     - `run()` → ส่ง target joint positions ไปมอเตอร์จริงทุก control tick
     - `get_present_head_joint_positions()` / `get_present_antenna_joint_positions()` → อ่านค่าจริง
     - `set_motor_control_mode()` → เปิด/ปิด torque switch
     - `close()` → ปิด serial bus

2. **map เรขาคณิต (สำคัญสุด)**
   - official head joint = `[neck_yaw, orbita x 6]` (เรเดียน) — 6 ค่า orbita
     คือมุมแขน crank (arm 40mm + rod 85mm เท่ากับของเราเป๊ะ)
   - แปลง: orbita angle → ความยาวขา (`crank_angle_to_leg_length`)
     → servo pos (`length_to_servo_pos`, solution ต่อขา)
   - body_yaw → servo base (ID 7)
   - ⚠️ ต้อง calibrate จุดศูนย์มุม orbita ↔ servo pos 2048 (ทำกับหุ่นจริง)

3. **แพทช์ daemon ให้เลือก backend ใหม่**
   - `daemon.py::_setup_backend` เพิ่ม branch (flag ใหม่ เช่น `--sts3215`)
   - import `STS3215Backend`

4. **ทำให้ import `src/` ได้จาก reachy_mini_env (Python 3.12)**
   - `src/servo_bus.py` + `src/stewart.py` ใช้แค่ numpy + pyserial → ใช้ได้ทั้ง 2 env
   - เพิ่ม `d:\Reachy Mini` ลง `sys.path` ใน backend

5. **ทดสอบ**
   - รัน daemon แบบ `--sts3215` → SDK client/ReachyMini เชื่อมต่อได้
   - รัน `test_control_loop.py` ต่อหุ่นจริง
   - install + start community app (เช่น app ขยับหัว/อารมณ์) → ขยับจริง

## ขอบเขตที่ควรรู้ (ข้อจำกัด)
- ✅ **ใช้ได้**: app ขยับหัว/ตัว/เสาอากาศ/อารมณ์ (motion) ทั้งหมด
- ⚠️ **บางส่วน**: app ที่ใช้กล้อง/เสียง — official ใช้กล้อง/ไมค์ของตัวเอง
  (gstreamer/USB ต่างกัน) อาจต้อง setup เพิ่ม
- ❌ **แตะไม่ได้**: เรา**ไม่แก้** daemon ทางการของ Reachy จริง (แค่เพิ่ม backend)

## ไฟล์ที่เกี่ยวข้อง
- `third_party/reachy_mini/src/reachy_mini/daemon/backend/sts3215/backend.py` (ใหม่)
- `third_party/reachy_mini/src/reachy_mini/daemon/daemon.py` (แก้ branch เลือก backend)
- `src/servo_bus.py`, `src/stewart.py` (ใช้เดิม ไม่แก้)
- `scripts/test_control_loop.py` (ใช้ทดสอบ)
