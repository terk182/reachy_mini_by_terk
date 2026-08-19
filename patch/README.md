# Patch: ขับ Reachy Mini SDK ด้วย STS3215 (หุ่น DIY)

โฟลเดอร์นี้เก็บ **"ส่วนที่เราแก้ official SDK"** (`pollen-robotics/reachy_mini`)
เพื่อให้ daemon ทางการขับมอเตอร์ **Feetech STS3215** ได้ (แทน Dynamixel)

ประกอบด้วย:
- `reachy_mini_sts3215.patch` — diff ที่แก้ไฟล์ทางการ 4 ไฟล์
- `backend/sts3215/` — backend ใหม่ของเรา (หัวใจหลัก)
- `app/static/` — ไฟล์ UI ที่เพิ่ม

## ขั้นตอนติดตั้ง (Windows)

```powershell
# 1) โคลน official SDK ลง third_party/
git clone https://github.com/pollen-robotics/reachy_mini.git third_party/reachy_mini
git clone https://github.com/pollen-robotics/reachy_description.git third_party/reachy_description

# 2) checkout commit ที่ patch อิง (กัน diff ไม่ตรง)
git -C third_party/reachy_mini checkout 05f0cd0

# 3) ใส่ไฟล์ใหม่ (backend + static)
Copy-Item -Recurse -Force patch\backend\sts3215 third_party\reachy_mini\src\reachy_mini\daemon\backend\
Copy-Item -Recurse -Force patch\app\static     third_party\reachy_mini\src\reachy_mini\daemon\app\

# 4) apply diff
git -C third_party/reachy_mini apply ..\..\patch\reachy_mini_sts3215.patch

# 5) สร้าง env Python 3.12 + ติดตั้ง editable
py -3.12 -m venv reachy_mini_env
reachy_mini_env\Scripts\pip install -e third_party/reachy_mini
```

## รัน

```powershell
reachy_mini_env\Scripts\reachy-mini-daemon.exe --sts3215 --no-media
#   - มี USB-TTL → ขับ STS3215 จริง
#   - ไม่มีพอร์ต → dry-run (ไม่ขยับจริง)
```

## License

- backend/STS3215 = โค้ดเรา (Apache 2.0 ตามโปรเจกต์)
- official SDK (`third_party/`) = Apache 2.0 (ซอฟต์แวร์), hardware design = CC BY-SA-NC
