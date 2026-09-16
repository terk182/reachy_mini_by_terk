# 📦 Packaging — สร้าง ReachyAssistant.exe

เอกสารสำหรับ **ผู้พัฒนา** (วิธีใช้สำหรับผู้รับไฟล์อยู่ใน `HOWTO.txt`
ซึ่ง build script จะคัดลอกไปไว้ข้าง exe ให้อัตโนมัติ)

## วิธี build

```powershell
# 1) ติดตั้งเครื่องมือ build (ครั้งแรกครั้งเดียว)
.venv\Scripts\python.exe -m pip install -r requirements-build.txt

# 2) build (one-folder — ค่าเริ่มต้น)
.venv\Scripts\python.exe scripts\build_exe.py --clean

# ทางเลือก
.venv\Scripts\python.exe scripts\build_exe.py --zip       # + ไฟล์ zip แจก
.venv\Scripts\python.exe scripts\build_exe.py --windowed  # ซ่อน console
.venv\Scripts\python.exe scripts\build_exe.py --onefile   # ไฟล์เดียว (เปิดช้า)
```

ผลลัพธ์: `dist/ReachyAssistant/ReachyAssistant.exe` (~224 MB, build ~50 วิ บนเครื่อง dev)

## ทดสอบหลัง build (ไม่ต้องเปิด GUI)

```powershell
dist\ReachyAssistant\ReachyAssistant.exe --list-cameras
dist\ReachyAssistant\ReachyAssistant.exe --list-mics
dist\ReachyAssistant\ReachyAssistant.exe --smoke 3                                    # กล้อง 3 วิ
dist\ReachyAssistant\ReachyAssistant.exe --smoke 2 --camera none --smoke-ask "สวัสดี"  # แชท
```

## สิ่งที่รวม / ไม่รวม

| รวม ✅ | ไม่รวม ❌ (ตัดเพื่อลดขนาด) |
|--------|----------------------------|
| GUI แชท+กล้อง (`scripts/app_gui.py`) | MuJoCo 3D (`mujoco`, `mujoco_sim`, `sim_gui`) |
| ควบคุมหุ่น sim/hardware (`src/robot.py`, `servo_bus`) | matplotlib |
| TTS: gTTS, edge-tts, pyttsx3, playsound3 | MediaPipe (ท่ามือ/ท่าทางจากกล้อง) |
| STT **remote** ผ่าน `stt_url` | faster-whisper (whisper local บนเครื่อง) |
| ตรวจจับใบหน้า YuNet (`src/face_detection_yunet_2023mar.onnx`) | รายการอื่นใน `scripts/` เช่น demo/เกม |
| เลือกกล้อง/ไมค์ (sounddevice + PortAudio) | |

> หมายเหตุ: โมดูลที่ import แบบ lazy (gtts/pyttsx3/playsound3/sounddevice/miniaudio)
> ต้องระบุ `--hidden-import` ใน `scripts/build_exe.py` — ถ้าเพิ่ม dependency
> แบบ lazy ใหม่ในอนาคต **ต้องเพิ่มใน `HIDDEN_IMPORTS` ด้วย** ไม่งั้น exe จะ error ตอนใช้ฟีเจอร์นั้น

## ไฟล์ config ในตัวแจก

| ค่า | ตำแหน่งในโฟลเดอร์แจก | หมายเหตุ |
|-----|----------------------|----------|
| LLM/STT URL + api_key | `_internal/config/local_config.json` | ผู้รับแก้เองหลังแตกไฟล์ |
| ไมค์ที่เลือกในแอป | เขียนกลับไฟล์เดียวกันอัตโนมัติ | `save_local_config({"stt": {"mic": ...}})` |
| calibration | `_internal/config/calibration.json` | ใช้กับโหมด `--hardware` |

## ข้อจำกัดที่รู้อยู่

- **ไม่ cross-compile**: exe นี้ build บน Windows x64 → ใช้ได้กับ Windows x64 เท่านั้น (Raspberry Pi ต้อง build บน Pi)
- ครั้งแรกที่เปิด แอปจะสตาร์ทช้า (แตกไฟล์ + โหลด DLL) ~5-10 วิ
- ไม่ได้ code-sign → Windows SmartScreen จะเตือน (กด More info → Run anyway)
- แชร์ผ่าน zip: ใช้ `--zip` เพื่อได้ `dist/ReachyAssistant_<วันที่>.zip`
