"""ไดรเวอร์ Feetech STS3215 (serial bus servo) ผ่าน pyserial

โปรโตคอล: Feetech serial bus (half-duplex TTL)
  ส่ง:   FF FF [ID] [LEN] [INST] [ADDR] [DATA...] [CHECKSUM]
  LEN = จำนวนไบต์ของ INST+ADDR+DATA (นับต่อจากช่อง LEN)
  CHECKSUM = ~(ID+LEN+INST+ADDR+DATA) & 0xFF

⚠️ STS3215 เป็น half-duplex — ต้องใช้ USB-TTL แบบ half-duplex (หรือต่อ RX ผ่านไดโอด)
จึงจะอ่าน feedback กลับมาได้ (สั่งเขียนอย่างเดียวใช้แค่ TX ได้)
"""

from __future__ import annotations

import os
import sys
import threading
import time

import serial

# --- คำสั่ง (instruction) ---
PING = 0x01
READ = 0x02
WRITE = 0x03
ACTION = 0x05
SYNC_WRITE = 0x83

# --- รีจิสเตอร์ STS3215 (ตาม datasheet) ---
REG_ID = 0x05              # EEPROM: servo ID
REG_BAUD = 0x06            # EEPROM: baud rate
REG_TORQUE_ENABLE = 0x28   # 40: เปิด/ปิดแรงบิด (0=limp, 1=hold)
REG_ACCELERATION = 0x29    # 41: 0-254
REG_GOAL_POSITION = 0x2A   # 42: ตำแหน่งเป้าหมาย (0-4095)
REG_GOAL_TIME = 0x2C       # 44: เวลาถึงเป้า (ms)
REG_GOAL_SPEED = 0x2E      # 46: ความเร็ว (0=เร็วสุด)
REG_TORQUE_LIMIT = 0x30    # 48: จำกัดแรงบิด (0-1000)
REG_PRESENT_POS = 0x38     # 56: ตำแหน่งปัจจุบัน
REG_PRESENT_SPEED = 0x3A   # 58: ความเร็วปัจจุบัน
REG_PRESENT_LOAD = 0x3C    # 60: แรงบิดปัจจุบัน
REG_PRESENT_VOLTAGE = 0x3E # 62: แรงดัน (×0.1V)
REG_PRESENT_TEMP = 0x3F    # 63: อุณหภูมิ (°C)
REG_LOCK = 0x37            # 55: EEPROM lock (0=ปลดล็อก, 1=ล็อก)

# ตาราง baud rate (ค่า register 0x06 -> baud) ตาม datasheet STS3215
# 0=1M, 1=500K, 2=250K, 3=128K, 4=115200, 5=76800, 6=57600, 7=38400
BAUD_TABLE = {
    0: 1_000_000,
    1: 500_000,
    2: 250_000,
    3: 128_000,
    4: 115_200,
    5: 76_800,
    6: 57_600,
    7: 38_400,
}

POS_MIN, POS_MAX = 0, 4095
POS_CENTER = 2048


def _auto_port() -> str:
    """ค้นหาพอร์ตอนุกรมอัตโนมัติ (Windows: COMx, Linux: /dev/ttyUSB0)"""
    if sys.platform.startswith("win"):
        import serial.tools.list_ports as list_ports

        ports = list(list_ports.comports())
        if not ports:
            raise OSError("ไม่พบพอร์ตอนุกรม (COM) — ตรวจสอบ USB-TTL adapter")
        return ports[0].device
    for p in ("/dev/ttyUSB0", "/dev/ttyACM0", "/dev/ttyAMA0", "/dev/ttyS0"):
        if os.path.exists(p):
            return p
    raise OSError("ไม่พบพอร์ตอนุกรม — ตรวจสอบ USB-TTL adapter บน Raspberry Pi")


def _auto_port_or_none() -> str | None:
    """เหมือน _auto_port() แต่คืน None ถ้าไม่เจอ (ใช้ตอน reconnect กัน loop ตาย)"""
    try:
        return _auto_port()
    except OSError:
        return None


def list_serial_ports():
    """รายการพอร์ตอนุกรมที่มีอยู่: [(device, description), ...]"""
    import serial.tools.list_ports as list_ports

    return [(p.device, p.description or "") for p in list_ports.comports()]


class ServoBus:
    """จัดการมอเตอร์ STS3215 บน bus หนึ่งเส้น"""

    def __init__(self, port=None, baudrate=1_000_000, timeout=0.05):
        self.port = port or _auto_port()
        self.baudrate = baudrate
        self.timeout = timeout
        self._open()
        self._torque_on: set[int] = set()  # servo ที่เปิด torque แล้ว
        self._lock = threading.Lock()      # กัน thread แย่ง serial
        self._last_reconnect = 0.0         # เวลาลองเชื่อมใหม่ครั้งล่าสุด
        self.reconnect_cooldown = 2.0      # วิ — คั่นการลองเชื่อมใหม่ (กัน log spam)
        print(f"[ServoBus] เปิดพอร์ต {self.port} @ {baudrate} baud")

    def _open(self):
        """เปิด serial (เรียกซ้ำได้ตอน reconnect)

        write_timeout จำเป็น: ถ้าอุปกรณ์ค้าง (USB wedged) ser.write() แบบ
        ไม่มี timeout จะบล็อกตลอดกาล — ล็อกบัสจะค้างทั้งระบบแบบไม่มี error
        """
        self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout,
                                 write_timeout=0.3)

    def _reopen_unlocked(self) -> bool:
        """ปิดแล้วเปิดพอร์ตใหม่ (ต้องถือ self._lock อยู่) — คืน True ถ้าสำเร็จ

        USB-TTL หลุดชั่วคราวบน Windows → WriteFile 'Access is denied'
        ลองพอร์ตเดิมก่อน แล้วค่อย auto-detect (พอร์ตอาจเปลี่ยนเลข เช่น COM3→COM5)

        มี cooldown: ถ้ายังไม่ถึง 2 วิ นับจากครั้งก่อน จะข้ามไปเลย (คืน False เงียบ ๆ)
        เพื่อไม่ให้เขียนซ้ำทุก 50ms แล้ว log เต็มจอตอน sway
        """
        now = time.time()
        if now - self._last_reconnect < self.reconnect_cooldown:
            return False
        self._last_reconnect = now
        try:
            self.ser.close()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.3)
        candidates = [self.port, _auto_port_or_none()]
        for port in dict.fromkeys(p for p in candidates if p):
            try:
                self.ser = serial.Serial(port, self.baudrate, timeout=self.timeout,
                                         write_timeout=0.3)
                self.port = port
                self._torque_on.clear()  # หลังหลุด อาจต้องเปิด torque ใหม่
                self._last_reconnect = 0.0  # สำเร็จแล้ว — หลุดใหม่ให้ลองใหม่ได้ทันที
                print(f"[ServoBus] เชื่อมต่อใหม่สำเร็จ: {port}")
                return True
            except Exception:  # noqa: BLE001
                continue
        print("[ServoBus] เชื่อมต่อใหม่ไม่สำเร็จ — ตรวจสาย USB / ไฟเลี้ยง servo")
        return False

    def reconnect(self) -> bool:
        """เปิดพอร์ตใหม่ (public API) — คืน True ถ้าสำเร็จ"""
        with self._lock:
            return self._reopen_unlocked()

    # ---------- ระดับเฟรม ----------
    def _send(self, servo_id, data, read_response=False, timeout=0.1):
        """data = [INST, ADDR, params...] (ไม่รวม ID/LEN/CHECKSUM)"""
        with self._lock:  # กันหลาย thread เขียน/อ่านพอร์ตพร้อมกัน
            body = bytes([servo_id, len(data) + 1]) + bytes(data)
            packet = b"\xff\xff" + body + bytes([(~sum(body)) & 0xFF])
            try:
                self.ser.reset_input_buffer()  # ล้าง response ค้างเก่า
                self.ser.write(packet)
            except (serial.SerialException, OSError) as exc:
                # USB หลุดชั่วคราว → ลองเปิดพอร์ตใหม่ 1 ครั้งแล้วเขียนซ้ำ
                print(f"[ServoBus] เขียนพอร์ตพลาด ({exc}) — ลองเชื่อมต่อใหม่")
                if not self._reopen_unlocked():
                    raise
                self.ser.reset_input_buffer()
                self.ser.write(packet)
            if read_response:
                return self._read_response(servo_id, timeout=timeout)
            return None

    def _read_response(self, servo_id, timeout=0.1):
        """อ่าน response: FF FF ID LEN ERROR [PARAMS...] CHECKSUM

        LEN = จำนวนไบต์ถัดจากช่อง LEN (ERROR + params + checksum)
        """
        self.ser.timeout = timeout
        header = self.ser.read(4)
        if len(header) < 4 or header[0] != 0xFF or header[1] != 0xFF:
            return None
        rid, length = header[2], header[3]
        rest = self.ser.read(length)  # ERROR + params + checksum
        if len(rest) < length:
            return None
        return {
            "id": rid,
            "error": rest[0],                    # ไบต์แรก = error/status (0=OK)
            "params": list(rest[1:length - 1]),  # ข้อมูล (ตัด error + checksum)
        }

    # ---------- คำสั่งพื้นฐาน ----------
    def ping(self, servo_id, timeout=0.05) -> bool:
        resp = self._send(servo_id, [PING], read_response=True, timeout=timeout)
        if resp is None:
            return False
        return resp["error"] == 0

    def health_check(self, servo_id=1, tries=2) -> bool:
        """ping servo — คืน False ถ้าไม่ตอบ (พอร์ต zombie/หลุดหลัง USB re-enumerate)

        สำคัญ: บน Windows หลัง USB re-enumerate บางครั้ง handle เก่ารับ write ได้
        (ไม่ error) แต่ข้อมูลไปไม่ถึง servo → ดูเหมือน "หุ่นไม่ขยับ" ทั้งที่ไม่มี exception
        วิธีเดียวที่จะรู้คือ read/ping กลับ — ใช้ใน Robot.check_connection()
        """
        for _ in range(tries):
            try:
                if self.ping(servo_id, timeout=0.06):
                    return True
            except (serial.SerialException, OSError):
                return False
        return False

    def read(self, servo_id, addr, n=1):
        resp = self._send(servo_id, [READ, addr, n], read_response=True)
        if resp is None or resp["error"] != 0:
            return None
        return list(resp["params"])

    def write(self, servo_id, addr, data, read_response=False):
        return self._send(servo_id, [WRITE, addr] + list(data),
                          read_response=read_response)

    def sync_write(self, addr, data_len, entries):
        """entries = [(servo_id, [byte...]), ...] — เขียนหลายตัวพร้อมกัน

        frame: FF FF FE LEN 0x83 [ADDR] [DATA_LEN] [ID1 DATA...] ... CHK
        """
        params = [addr, data_len]
        for sid, data in entries:
            params += [sid] + list(data)
        self._send(0xFE, [SYNC_WRITE] + params)

    # ---------- คำสั่งระดับมอเตอร์ ----------
    def set_torque(self, servo_id, on: bool):
        """เปิด/ปิดแรงบิด (torque enable ที่ 0x28)"""
        self.write(servo_id, REG_TORQUE_ENABLE, [1 if on else 0])
        if on:
            self._torque_on.add(servo_id)
        else:
            self._torque_on.discard(servo_id)

    def _ensure_torque(self, servo_id):
        """เปิด torque ถ้ายังไม่เปิด (เปิดครั้งเดียวพอ — เขียนซ้ำทำให้ servo ลืม goal)"""
        if servo_id not in self._torque_on:
            self.set_torque(servo_id, True)
            time.sleep(0.1)  # รอ servo เปิด torque ก่อนสั่งตำแหน่ง

    def set_position(self, servo_id, pos, speed=1000, acc=0):
        """สั่งตำแหน่ง pos (0-4095) ด้วยความเร็ว speed (0=เร็วสุด, 1-4095=จำกัด)

        เขียนรวม packet เดียวแบบ WritePosEx ของ SDK ทางการ:
        [acc, posL, posH, timeL=0, timeH=0, speedL, speedH] เริ่มที่ ACC (0x29)
        """
        pos = max(POS_MIN, min(POS_MAX, int(pos)))
        speed = max(0, min(4095, int(speed)))
        acc = max(0, min(254, int(acc)))
        self._ensure_torque(servo_id)
        self.write(servo_id, REG_ACCELERATION, [
            acc, pos & 0xFF, (pos >> 8) & 0xFF, 0, 0,
            speed & 0xFF, (speed >> 8) & 0xFF,
        ])

    def sync_set_position(self, targets, speed=1000, acc=0):
        """targets = [(servo_id, pos), ...] — ขยับพร้อมกัน (sync write)"""
        speed = max(0, min(4095, int(speed)))
        acc = max(0, min(254, int(acc)))
        entries = []
        for sid, pos in targets:
            pos = max(POS_MIN, min(POS_MAX, int(pos)))
            entries.append((sid, [
                acc, pos & 0xFF, (pos >> 8) & 0xFF, 0, 0,
                speed & 0xFF, (speed >> 8) & 0xFF,
            ]))
            self._ensure_torque(sid)
        self.sync_write(REG_ACCELERATION, 7, entries)

    def get_position(self, servo_id):
        data = self.read(servo_id, REG_PRESENT_POS, 2)
        if data is None:
            return None
        return data[0] | (data[1] << 8)

    def get_load(self, servo_id):
        """อ่านแรงบิดปัจจุบัน (0-4095; >2048 = ทิศตรงข้าม)"""
        data = self.read(servo_id, REG_PRESENT_LOAD, 2)
        if data is None:
            return None
        return data[0] | (data[1] << 8)

    def get_voltage(self, servo_id):
        data = self.read(servo_id, REG_PRESENT_VOLTAGE, 1)
        return data[0] / 10.0 if data else None

    def set_id(self, servo_id, new_id):
        """เปลี่ยน ID (EEPROM) — ⚠️ ตัวเดียวบน bus + ถอดปลั๊ก-เสียบใหม่หลังตั้ง

        ต้องปิด torque + ปลดล็อก EEPROM ก่อนเขียน ไม่งั้นเขียนไม่ติด
        """
        self.set_torque(servo_id, False)       # ปิด torque ก่อนเขียน EEPROM
        time.sleep(0.1)
        self.write(servo_id, REG_LOCK, [0])    # ปลดล็อก EEPROM
        time.sleep(0.05)
        self.write(servo_id, REG_ID, [new_id]) # เขียน ID ใหม่
        time.sleep(0.2)                        # รอ EEPROM เขียนเสร็จ

    def set_baud(self, servo_id, baud_reg):
        """เปลี่ยน baud rate ของมอเตอร์ (ดู BAUD_TABLE)"""
        self.write(servo_id, REG_BAUD, [baud_reg])

    def close(self):
        self.ser.close()

    # ---------- ตัวช่วยแปลงค่า ----------
    @staticmethod
    def deg_to_pos(angle_deg: float) -> int:
        """มุมองศา (0-360) -> ตำแหน่ง servo (0-4095)"""
        return int(round(angle_deg * 4096.0 / 360.0)) % 4096

    @staticmethod
    def pos_to_deg(pos: int) -> float:
        return (pos % 4096) * 360.0 / 4096.0
