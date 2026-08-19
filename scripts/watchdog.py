r"""Watchdog — รัน voice assistant แล้ว restart เองถ้าตาย (สำหรับงานจัดแสดง)

รัน:
    .venv\Scripts\python.exe -X utf8 scripts\watchdog.py --hardware

พฤติกรรม:
  - assistant จบปกติ (Ctrl+C / พูด 'หยุด') → หยุด ไม่ restart
  - assistant ตายเอง (crash, exit != 0) → รอ 3 วิ แล้วรันใหม่ (backoff ถึง 30 วิ)
  - ตายเร็วติดกัน 3 ครั้ง (เช่น COM3 ถูกยึด) → หยุด ไม่วน restart ไปตลอด
  - กด Ctrl+C ตัว watchdog → หยุดทั้งหมด

กันรันซ้ำ: ใช้ lock file (config/watchdog.lock) — ดับเบิลคลิก 2 ครั้งจะรันแค่ตัวเดียว
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

LOCK_FILE = os.path.join("config", "watchdog.lock")


def _pid_alive(pid: int) -> bool:
    """เช็คว่า process ยังอยู่ไหม (Windows)"""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_lock() -> bool:
    """จองสิทธิ์รันตัวเดียว — คืน False ถ้ามี watchdog ตัวอื่นรันอยู่แล้ว"""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, encoding="utf-8") as f:
                pid = int(f.read().strip())
            if _pid_alive(pid):
                print(f"[watchdog] มี watchdog ตัวอื่นรันอยู่แล้ว (PID {pid}) — ออก")
                return False
        except (ValueError, OSError):
            pass  # lock เก่าพัง → เขียนทับได้
    try:
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return True
    except OSError as exc:
        print(f"[watchdog] เขียน lock ไม่ได้: {exc}")
        return False


def release_lock() -> None:
    """ลบ lock (เฉพาะถ้าเป็นของตัวเรา)"""
    try:
        if os.path.exists(LOCK_FILE):
            with open(LOCK_FILE, encoding="utf-8") as f:
                if f.read().strip() == str(os.getpid()):
                    os.remove(LOCK_FILE)
    except OSError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-restart voice assistant")
    parser.add_argument("--hardware", action="store_true", help="ใช้หุ่นจริง (STS3215)")
    parser.add_argument("--real", action="store_true", help="ใช้ official daemon")
    parser.add_argument("--no-gui", action="store_true", help="sim: ไม่เปิด MuJoCo")
    parser.add_argument("--model", default=None)
    parser.add_argument("--mic", default=None)
    parser.add_argument("--duration", type=float, default=4.0)
    parser.add_argument("--max-restarts", type=int, default=0,
                        help="จำกัดจำนวน restart (0 = ไม่จำกัด)")
    args = parser.parse_args()

    if not acquire_lock():
        sys.exit(0)

    restarts = 0
    fast_fails = 0
    backoff = 3.0
    try:
        while True:
            cmd = [sys.executable, "-X", "utf8", "scripts/voice_assistant.py"]
            if args.hardware:
                cmd.append("--hardware")
            if args.real:
                cmd.append("--real")
            if args.no_gui:
                cmd.append("--no-gui")
            if args.model:
                cmd += ["--model", args.model]
            if args.mic:
                cmd += ["--mic", args.mic]
            cmd += ["--duration", str(args.duration)]

            print(f"[watchdog] เริ่ม: {' '.join(cmd)}")
            start = time.time()
            try:
                code = subprocess.call(cmd)
            except KeyboardInterrupt:
                print("\n[watchdog] หยุด (Ctrl+C)")
                break
            elapsed = time.time() - start

            if code == 0:
                print("[watchdog] จบปกติ — หยุด")
                break

            # ตายเร็วเกินไป (เช่น COM3 ถูกยึด / โมเดลไม่มี) → กัน restart วนไม่รู้จบ
            if elapsed < 10.0:
                fast_fails += 1
            else:
                fast_fails = 0
            if fast_fails >= 3:
                print("[watchdog] ตายเร็วติดกัน 3 ครั้ง — น่าจะมีปัญหา (COM3 ถูกยึด?) "
                      "หยุดรัน")
                break

            restarts += 1
            if args.max_restarts and restarts >= args.max_restarts:
                print(f"[watchdog] รีสตาร์ทครบ {args.max_restarts} ครั้ง — หยุด")
                break
            print(f"[watchdog] ออกด้วย code {code} → รีสตาร์ทใน {backoff:.0f} วิ "
                  f"(ครั้งที่ {restarts})")
            time.sleep(backoff)
            backoff = min(backoff * 2.0, 30.0)
    finally:
        release_lock()


if __name__ == "__main__":
    main()
