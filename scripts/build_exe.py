r"""สร้าง ReachyAssistant.exe (one-folder) ด้วย PyInstaller

ผลลัพธ์: dist/ReachyAssistant/ReachyAssistant.exe  (ซิปทั้งโฟลเดอร์แจกได้เลย)

สิ่งที่รวมไว้: GUI แชท+กล้อง (scripts/app_gui.py), ควบคุมหุ่น (sim/hardware),
             TTS (gTTS/edge-tts/pyttsx3), STT (**remote** ผ่าน stt_url),
             ตรวจจับใบหน้า YuNet, ตัวเลือกกล้อง/ไมค์
สิ่งที่ไม่รวม (ตัดออกเพื่อลดขนาด): MuJoCo 3D, matplotlib, MediaPipe,
             faster-whisper (whisper local) — ดู packaging/README.md

วิธีใช้:
    .venv\Scripts\python.exe scripts\build_exe.py              # build ปกติ
    .venv\Scripts\python.exe scripts\build_exe.py --zip        # build + ทำไฟล์ zip แจก
    .venv\Scripts\python.exe scripts\build_exe.py --onefile    # ไฟล์เดียว (เปิดช้ากว่า)
    .venv\Scripts\python.exe scripts\build_exe.py --windowed   # ซ่อนหน้าต่าง console
"""

import argparse
import datetime
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "ReachyAssistant"
HOWTO = ROOT / "packaging" / "HOWTO.txt"   # เอกสารแถมให้ผู้รับ

# โมดูลที่ "import แบบ lazy" (อยู่ในฟังก์ชัน) — PyInstaller มองไม่เห็น ต้องสั่งเพิ่มเอง
HIDDEN_IMPORTS = (
    "gtts",             # TTS หลัก (src/tts.py)
    "edge_tts",         # TTS ทางเลือก
    "pyttsx3",          # TTS ออฟไลน์ (Windows)
    "playsound3",       # เล่นไฟล์เสียง
    "sounddevice",      # ไมค์/ลำโพง
    "miniaudio",        # decode mp3 (speech_sway)
)

# แพ็กเกจใหญ่ที่โปรเจกต์ไม่ใช้ในตัวแจก → ตัดออก (ไม่งั้นไฟล์จะโต ~1GB)
EXCLUDES = (
    "mujoco", "mujoco_sim", "sim_gui", "matplotlib",
    "mediapipe", "faster_whisper", "ctranslate2", "torch", "av", "pandas", "scipy",
)

# ไฟล์ข้อมูลที่ต้องแนบไปด้วย (source ; dest ในโฟลเดอร์แอป)
DATAS = (
    ("config", "config"),                                     # calibration/local config
    ("src/face_detection_yunet_2023mar.onnx", "src"),         # โมเดลตรวจจับใบหน้า
)


def main() -> int:
    parser = argparse.ArgumentParser(description="build ReachyAssistant.exe (PyInstaller)")
    parser.add_argument("--onefile", action="store_true", help="รวมเป็นไฟล์เดียว (สตาร์ทช้ากว่า)")
    parser.add_argument("--windowed", action="store_true", help="ไม่แสดงหน้าต่าง console")
    parser.add_argument("--clean", action="store_true", help="ลบของเก่าก่อน build")
    parser.add_argument("--zip", action="store_true", help="ทำไฟล์ .zip สำหรับแจกหลัง build")
    args = parser.parse_args()

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("⚠️ ยังไม่มี PyInstaller — ติดตั้งก่อน:\n"
              "   .venv\\Scripts\\python.exe -m pip install -r requirements-build.txt")
        return 1

    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(ROOT / "scripts" / "app_gui.py"),
        "--name", NAME,
        "--noconfirm",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build" / "pyinstaller"),
        "--specpath", str(ROOT / "build"),
        "--onefile" if args.onefile else "--onedir",
        "--windowed" if args.windowed else "--console",
    ]
    for module in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", module]
    for module in EXCLUDES:
        cmd += ["--exclude-module", module]
    for src, dest in DATAS:
        cmd += ["--add-data", f"{ROOT / src}{';'}{dest}"]
    # เก็บข้อมูล/ไบนารีที่ผูกกับแพ็กเกจ (PortAudio ของ sounddevice, ตัวถอดรหัส miniaudio)
    cmd += ["--collect-all", "miniaudio", "--collect-all", "sounddevice"]
    cmd += ["--collect-submodules", "pyttsx3"]
    if args.clean:
        cmd.append("--clean")

    print("▶️  build:", " ".join(cmd[1:5]), "...\n")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"\n❌ build ไม่สำเร็จ (exit {result.returncode})")
        return result.returncode

    out = ROOT / "dist" / (f"{NAME}.exe" if args.onefile else NAME)
    size_mb = (out.stat().st_size if out.is_file()
               else sum(f.stat().st_size for f in out.rglob("*") if f.is_file())) / 1e6

    # คัดลอก HOWTO ให้ผู้รับ + ทำ zip ถ้าสั่ง
    if not args.onefile and HOWTO.exists():
        shutil.copy2(HOWTO, out / "HOWTO.txt")
    zip_path = None
    if args.zip:
        stamp = datetime.date.today().strftime("%Y%m%d")
        zip_path = shutil.make_archive(
            str(ROOT / "dist" / f"{NAME}_{stamp}"), "zip",
            root_dir=out.parent, base_dir=(out.name if out.is_dir() else out.name),
        )

    print(f"\n✅ build เสร็จใน {time.time() - t0:.0f} วิ")
    print(f"   ไฟล์: {out}")
    print(f"   ขนาด: {size_mb:.0f} MB")
    if zip_path:
        print(f"   zip แจก: {zip_path}")
    print(f"   ทดสอบ: {out / (NAME + '.exe') if out.is_dir() else out} --smoke 3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
