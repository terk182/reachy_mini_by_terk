"""เทียบผล STT ระหว่าง 2 เซิร์ฟเวอร์ (เช่น large-v3 เดิม vs โมเดลไทยใหม่)
บนไฟล์เสียงที่บันทึกไว้ — ใช้ตัดสินใจก่อนสลับโมเดลจริง

วิธีใช้ (บนเครื่อง GPU หรือเครื่องหุ่นก็ได้):
    python compare_stt.py --dir cache/stt_debug --a http://127.0.0.1:8000 --b http://127.0.0.1:8001
    python compare_stt.py --dir cache/stt_debug --a http://127.0.0.1:8000 --b http://127.0.0.1:8001 \
        --key rk-xxxxxxxx --last 10
"""
import argparse
import json
import pathlib
import time
import urllib.request


def transcribe(path: pathlib.Path, url: str, key: str | None, timeout: float = 30.0):
    """ส่งไฟล์ WAV ไป /transcribe → (ข้อความ, เวลา)"""
    headers = {"Content-Type": "audio/wav"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(f"{url.rstrip('/')}/transcribe",
                                 data=path.read_bytes(), headers=headers, method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return str(json.loads(body).get("text", "")).strip(), time.time() - t0


def main() -> None:
    p = argparse.ArgumentParser(description="เทียบผล STT ระหว่าง 2 เซิร์ฟเวอร์")
    p.add_argument("--dir", required=True, help="โฟลเดอร์ไฟล์ .wav (เช่น cache/stt_debug)")
    p.add_argument("--a", required=True, help="URL เซิร์ฟเวอร์ A (โมเดลเดิม)")
    p.add_argument("--b", required=True, help="URL เซิร์ฟเวอร์ B (โมเดลใหม่)")
    p.add_argument("--key", default=None, help="api_key (ถ้ามี)")
    p.add_argument("--last", type=int, default=0, help="เอาแค่ N ไฟล์ใหม่สุด (0=ทั้งหมด)")
    args = p.parse_args()

    files = sorted(pathlib.Path(args.dir).glob("*.wav"))
    if args.last:
        files = files[-args.last:]
    if not files:
        print("ไม่พบไฟล์ .wav ในโฟลเดอร์")
        return

    for f in files:
        try:
            ta, dta = transcribe(f, args.a, args.key)
        except Exception as exc:  # noqa: BLE001
            ta, dta = f"ERROR: {exc}", 0.0
        try:
            tb, dtb = transcribe(f, args.b, args.key)
        except Exception as exc:  # noqa: BLE001
            tb, dtb = f"ERROR: {exc}", 0.0
        print(f"== {f.name} ==")
        print(f"  A ({dta:4.1f}s): {ta!r}")
        print(f"  B ({dtb:4.1f}s): {tb!r}")


if __name__ == "__main__":
    main()
