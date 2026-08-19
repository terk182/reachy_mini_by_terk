# 🤖 AI Assistant (Voice) — สถาปัตยกรรม + การ Deploy ไปเครื่อง GPU

เอกสารสำหรับ agent/AI ที่จะมาทำงานต่อ: เข้าใจโครงสร้าง voice assistant ของ Reachy Mini DIY
และวิธีแยก LLM/STT/TTS ไปรันบนเครื่องอื่นที่มี GPU

> สรุปสั้น: assistant = ฟังเสียง (STT) → LLM ตอบ → ตรวจจับอารมณ์ → หุ่นขยับ + พูด (TTS)
> วนลูปต่อเนื่อง จนกว่าผู้ใช้พูด "หยุด"

---

## 1. ภาพรวม

```
[ไมค์] → STT (faster-whisper) → ข้อความ
                                    ↓
                              LLM (Ollama) → ข้อความตอบ + แท็กอารมณ์ (happy)
                                    ↓
                ┌───────────────────┼───────────────────┐
                ↓                                       ↓
   TTS (edge-tts/gTTS) พูดเสียง           apply_emotion() ขยับหุ่นตามอารมณ์
```

- ไมค์ที่ใช้: auto-detect USB cam mic (keyword: `lifecam`/`camera`/`webcam`/`cam`)
- หุ่นที่ควบคุม: `Robot` (DIY STS3215) หรือ `RealRobot` (โมเดล Reachy Mini แท้ผ่าน official daemon)

---

## 2. องค์ประกอบ + ไฟล์

| ส่วน | ไฟล์ | หมายเหตุ |
|------|------|---------|
| LLM client | `src/llm.py` | `OllamaClient` — HTTP ไป Ollama (`/api/chat`, `/api/tags`) |
| STT | `src/stt.py` | faster-whisper **in-process** (ยังไม่ใช่ service) |
| TTS | `src/tts.py` | `speak()` / `clean_for_speech()` — ลอง edge-tts → gTTS |
| อารมณ์ → ท่าทาง | `src/expressions.py` | `detect_emotion` / `strip_emotion_tag` / `apply_emotion` |
| หุ่น DIY | `src/robot.py` | `Robot(backend="sim"/"hardware")` |
| หุ่นแท้ (official) | `src/real_robot.py` | `RealRobot()` → REST `http://localhost:8000` |
| Scripts | `scripts/voice_assistant.py` | **ตัวหลัก** voice loop ต่อเนื่อง |
| | `scripts/chat_gui.py` | chat GUI (พิมพ์ + 🎤) |
| | `scripts/pose_gui.py` | GUI ปุ่มท่าทาง |
| | `scripts/demo_face_tracking.py` | ติดตามใบหน้า |
| Config | `config/robot_config.py` | section `llm`, `stt` |

---

## 3. Config ที่เกี่ยวข้อง (`config/robot_config.py`)

```python
"llm": {
    "url": "http://localhost:11434",   # ← เปลี่ยนเป็น IP เครื่อง GPU เพื่อ offload
    "model": "qwen2.5:3b",            # เครื่อง GPU แรง ใช้ 7b ได้
    "system_prompt": "... (happy) ...",
    "temperature": 0.7,
},
"stt": {
    "model": "base",      # faster-whisper: tiny/base/small/medium/large
    "device": "auto",     # cuda → cpu fallback อัตโนมัติ
    "language": "th",
    "duration": 4.0,      # วินาทีที่ฟังต่อรอบ
    "samplerate": 16000,
},
```

---

## 4. ⚠️ Convention สำคัญ: `nod_axis` (ก้ม/เงยใช้แกนไหน)

หุ่น 2 ตัวมีทิศหน้าไม่เหมือนกัน:

| คลาส | หน้า | ก้ม/เงย (nod) | เอียงซ้าย/ขวา | nod_axis |
|------|------|---------------|---------------|----------|
| `Robot` (DIY STS3215) | +Y | `roll` | `pitch` | `"roll"` |
| `RealRobot` (official) | +X | `pitch` | `roll` | `"pitch"` |

`apply_emotion()` อ่าน `robot.nod_axis` แล้วยิง `set_head_pose(**{axis: deg})` ให้เอง —
**อย่า hardcode roll/pitch ลงในโค้ดท่าทาง**

---

## 5. วิธีรัน

```powershell
# voice assistant — หุ่น DIY (sim MuJoCo 3D)
.venv\Scripts\python.exe scripts\voice_assistant.py

# voice assistant — โมเดล Reachy Mini แท้ (ต้องรัน official daemon ก่อน)
reachy_mini_env\Scripts\reachy-mini-daemon.exe --sim --scene minimal   # terminal แยก
.venv\Scripts\python.exe scripts\voice_assistant.py --real

# voice assistant — หุ่นจริง STS3215
.venv\Scripts\python.exe scripts\voice_assistant.py --hardware

# เลือกไมค์
.venv\Scripts\python.exe scripts\voice_assistant.py --list-mics
.venv\Scripts\python.exe scripts\voice_assistant.py --mic LifeCam
.venv\Scripts\python.exe scripts\voice_assistant.py --mic 12
```

---

## 6. Deploy ไปเครื่อง GPU (แยก AI ออกจากเครื่องหุ่น)

### 6.1 LLM (Ollama) — ง่ายสุด คุ้มสุด

Ollama เป็น HTTP อยู่แล้ว แค่ย้าย server:

```powershell
# ── บนเครื่อง GPU ──
set OLLAMA_HOST=0.0.0.0          # ให้รับ request จากเครื่องอื่น
ollama serve
ollama pull qwen2.5:7b           # เครื่อง GPU ใช้โมเดลใหญ่ได้
```

```python
# ── บนเครื่องหุ่น: config/robot_config.py ──
"llm": {
    "url": "http://<IP_GPU>:11434",   # ← เปลี่ยนตรงนี้
    "model": "qwen2.5:7b",
    ...
}
```

> firewall: เปิด port 11434 (TCP) บนเครื่อง GPU

### 6.2 STT (faster-whisper) — ต้อง wrap เป็น service

ตอนนี้ `src/stt.py` รัน whisper **ในเครื่องเดียวกับตัวหุ่น** (in-process)
ถ้าต้องการ offload:

1. **เครื่อง GPU**: รัน `faster-whisper-server` (FastAPI wrapper, ใช้ CUDA)
   หรือเขียน service เล็กๆ ที่รับ audio bytes → คืน text
2. **เครื่องหุ่น**: แก้ `src/stt.py` ให้มี "remote mode" —
   `listen(..., stt_url="http://<IP_GPU>:8000")` ส่ง audio ไปแทนการรัน local

*จุดแก้ใน `src/stt.py`: `record()` + `transcribe()` + `listen()` (เพิ่ม `stt_url` param)*

### 6.3 TTS — ไม่ต้องย้าย

`edge-tts`/`gTTS` ใช้ internet อยู่แล้ว (remote โดยธรรมชาติ)
ถ้า offline → ตก `pyttsx3` (local, เสียงไทยคุณภาพต่ำ)

---

## 7. ปัญหา GPU ที่เจอบนเครื่องปัจจุบัน (laptop)

- **NVIDIA RTX 4050 (6GB)** มี แต่ใช้ CUDA ไม่ได้:
  1. `ctranslate2` (whisper): `get_cuda_device_count()==1` แต่ `transcribe()` บน CUDA
     ล้มเหลว → fallback CPU (`[STT] cuda ใช้ไม่ได้ ... ใช้ CPU แทน`)
     สาเหตุเบื้องต้น: cuDNN/cuBLAS เวอร์ชันไม่ตรงกับ ctranslate2
  2. `Ollama`: log "GPU discovery watchdog timed out" / "could not determine compute
     capability" → รัน CPU (แต่ qwen2.5:3b บน CPU ก็ 20-67 token/s พอใช้)
- AMD Radeon 740M (iGPU): driver เก่า ใช้ GPU inference ไม่ได้

→ การ offload ไปเครื่อง GPU ดี แก้ทั้งสองปัญหานี้ในคราวเดียว

---

## 8. Loop หลักของ voice_assistant.py (pseudocode)

```python
robot = RealRobot() if --real else Robot(backend=..., gui=...)
while True:
    text = listen(duration=4, mic=mic_idx)      # STT (คืน "" ถ้าเงียบ)
    if not text: continue
    if any(w in text for w in STOP_WORDS): break   # "หยุด"
    reply = llm.chat(history)                    # LLM
    emotion = detect_emotion(reply)              # "(happy)" แท็กหรือ keyword
    apply_emotion(robot, emotion)                # ขยับ (ใช้ robot.nod_axis)
    speak(strip_emotion_tag(reply))              # TTS
```

---

## 9. Dependencies (Python 3.14 `.venv`)

- LLM: ใช้ urllib มาตรฐาน (ไม่ต้องติดตั้ง) — แต่ต้องมี **Ollama** server
- STT: `faster-whisper`, `sounddevice`, `numpy`
- TTS: `edge-tts` / `gTTS` / `pyttsx3` (ไล่ fallback)
- หุ่น: `src/robot.py` (pyserial) / `src/real_robot.py` (urllib)
