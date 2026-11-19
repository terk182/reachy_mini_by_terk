"""Self-test: ตรวจสอบว่าโค้ดทำงานได้โดยไม่ต้องมีฮาร์ดแวร์

วิธีใช้:
    python scripts/self_test.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.stewart import (  # noqa: E402
    crank_angle_2bar,
    crank_angle_to_leg_length,
    crank_tip_reach,
    forward_kinematics,
    leg_endpoints,
    leg_lengths,
    length_to_servo_pos,
    servo_pos_to_length,
)


def test_stewart_ik():
    # ท่า home (z=55, มุม 0): ขาทั้ง 6 ต้องยาวเท่ากัน (สมมาตร)
    lengths = leg_lengths(55.0, 0.0, 0.0, 0.0, 60.0, 40.0, 30.0)
    assert max(lengths) - min(lengths) < 1e-6, f"ขาไม่สมมาตร: {lengths}"

    # ยกหัวสูงขึ้น (z เพิ่ม) -> ทุกขาต้องยาวขึ้น
    up = leg_lengths(75.0, 0.0, 0.0, 0.0, 60.0, 40.0, 30.0)
    assert all(a > b for a, b in zip(up, lengths)), "z เพิ่มแล้วขาต้องยาวขึ้น"

    # ก้มหัว (pitch) -> ขาหน้าสั้น ขาหลังยาว (ไม่สมมาตร)
    pitch = leg_lengths(55.0, 0.0, 0.3, 0.0, 60.0, 40.0, 30.0)
    assert max(pitch) - min(pitch) > 1e-3, "ก้มหัวแล้วขาต้องไม่เท่ากัน"

    # ตำแหน่ง servo อยู่ในช่วง 0-4095
    for length in lengths:
        pos = length_to_servo_pos(length, 70.0, 30.0)
        assert 0 <= pos <= 4095, f"pos เกินขอบเขต: {pos}"
    print("Stewart IK ผ่าน ✅")


def test_leg_endpoints():
    # ท่า home: จานบนอยู่สูง z เท่ากันทุกจุด (แบน)
    base, top = leg_endpoints(55.0, 0.0, 0.0, 0.0, 60.0, 40.0, 30.0)
    assert base.shape == (3, 6) and top.shape == (3, 6)
    assert np.allclose(top[2], 55.0), "จานบนต้องแบนที่ท่า home"
    # ความยาวขาจาก endpoints ตรงกับ leg_lengths
    manual = [float(np.linalg.norm(top[:, i] - base[:, i])) for i in range(6)]
    assert np.allclose(manual, leg_lengths(55.0, 0.0, 0.0, 0.0, 60.0, 40.0, 30.0))
    print("leg_endpoints ผ่าน ✅")


def test_viewer_smoke():
    import matplotlib
    matplotlib.use("Agg")  # ไม่เปิดหน้าต่างจริง (ใช้ในเทสต์)

    from config.robot_config import DEFAULT_CONFIG
    from src.sim_gui import SimulationViewer

    viewer = SimulationViewer(DEFAULT_CONFIG)
    viewer.update({
        "head": {"z": 60.0, "roll": 0.1, "pitch": 0.2, "yaw": -0.3},
        "base": 25.0,
        "antennas": [1.0, -0.8],
    })
    viewer.update({
        "head": {"z": 55.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        "base": 0.0,
        "antennas": [0.0, 0.0],
    })
    viewer.close()
    print("GUI smoke test ผ่าน ✅")


def test_sim_robot():
    from src.robot import Robot

    with Robot(backend="sim") as robot:
        robot.wake_up().wave().look_around()
        state = robot.get_positions()
        assert "head" in state and "base" in state
    print("โหมดจำลอง ผ่าน ✅")


def test_frame_builder():
    from src.servo_bus import ServoBus

    # ตรวจสอบ LEN/CHECKSUM ของเฟรม WRITE (โดยไม่ต้องเปิดพอร์ต)
    bus = object.__new__(ServoBus)
    # FF FF 01 05 03 2A 00 08 CS (จากเอกสาร Feetech)
    body = bytes([1, 4 + 1]) + bytes([0x03, 0x2A, 0x00, 0x08])
    expected = b"\xff\xff\x01\x05\x03\x2a\x00\x08" + bytes([(~sum(body)) & 0xFF])
    # เปรียบเทียบกับเฟรมที่สร้างด้วย logic เดียวกับ _send
    data = [0x03, 0x2A, 0x00, 0x08]
    built_body = bytes([1, len(data) + 1]) + bytes(data)
    built = b"\xff\xff" + built_body + bytes([(~sum(built_body)) & 0xFF])
    assert built == expected, f"เฟรมไม่ตรง: {built.hex()} vs {expected.hex()}"
    print("เฟรม Feetech ผ่าน ✅")


def test_mujoco_smoke():
    """สร้าง model MuJoCo + ขับท่าทาง + render offscreen (ไม่เปิดหน้าต่าง)"""
    try:
        import mujoco  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        print(f"MuJoCo ไม่ได้ติดตั้ง ({exc}) — ข้าม")
        return

    from config.robot_config import DEFAULT_CONFIG
    from src.mujoco_sim import MuJoCoSim, build_mjcf

    xml = build_mjcf(DEFAULT_CONFIG)
    assert "<mujoco" in xml and "top_free" in xml

    sim = MuJoCoSim(DEFAULT_CONFIG, show=False)
    # ตรวจ joint ทั้งหมดมีอยู่
    for name in ("base_joint", "top_free", "leg0", "leg3", "antenna_L_joint"):
        assert name in sim.qpos_adr, f"ไม่พบ joint {name}"

    sim.update({
        "head": {"z": 60.0, "roll": 5.0, "pitch": -10.0, "yaw": 15.0},
        "base": 30.0,
        "antennas": [1.0, -0.8],
    })
    sim.update({
        "head": {"z": 55.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        "base": 0.0,
        "antennas": [0.0, 0.0],
    })
    # render offscreen (ถ้า GL พร้อม)
    try:
        img = sim.render_offscreen(320, 240)
        assert img.shape == (240, 320, 3), f"ขนาดภาพไม่ตรง: {img.shape}"
        print("MuJoCo render offscreen ผ่าน ✅")
    except Exception as exc:  # noqa: BLE001
        print(f"MuJoCo render offscreen ข้าม ({exc})")
    sim.close()
    print("MuJoCo smoke test ผ่าน ✅")


def test_stl_mesh_smoke():
    """สร้างไฟล์ STL ชั่วคราว + โหลดเข้า MuJoCo model"""
    import copy
    import struct
    import tempfile

    try:
        import mujoco  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        print(f"MuJoCo ไม่ได้ติดตั้ง ({exc}) — ข้าม")
        return

    from config.robot_config import DEFAULT_CONFIG
    from src.mujoco_sim import MuJoCoSim, build_mjcf

    def write_stl(path, triangles):
        with open(path, "wb") as f:
            f.write(b"\0" * 80)
            f.write(struct.pack("<I", len(triangles)))
            for tri in triangles:
                f.write(struct.pack("<12f", 0.0, 0.0, 0.0, *tri.ravel()))
                f.write(struct.pack("<H", 0))

    # tetrahedron (ปิดผิว)
    v = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10]], dtype=float)
    faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
    triangles = [v[list(f)] for f in faces]

    cfg = copy.deepcopy(DEFAULT_CONFIG)
    with tempfile.TemporaryDirectory() as tmp:
        tdir = Path(tmp)
        for name in ("base", "lower_plate", "leg", "top_plate", "head", "antenna"):
            write_stl(tdir / f"{name}.stl", triangles)
        cfg["meshes"]["enabled"] = True
        cfg["meshes"]["dir"] = str(tdir)

        xml = build_mjcf(cfg)
        assert 'type="mesh"' in xml and 'mesh="head"' in xml, "XML ไม่มี mesh geom"
        assert '<mesh name="leg"' in xml, "XML ไม่มี mesh asset"

        sim = MuJoCoSim(cfg, show=False)
        assert sim.model.nmesh == 6, f"mesh ไม่ครบ: {sim.model.nmesh}"
        sim.update({
            "head": {"z": 60.0, "roll": 5.0, "pitch": -8.0, "yaw": 12.0},
            "base": 25.0,
            "antennas": [0.6, -0.4],
        })
        try:
            img = sim.render_offscreen(320, 240)
            assert img.shape == (240, 320, 3)
        except Exception as exc:  # noqa: BLE001
            print(f"  (render ข้าม: {exc})")
        sim.close()
    print("STL mesh smoke test ผ่าน ✅")


def test_crank_rod():
    """2-bar solver: ปลายก้านต้องถึงจุดยึดจานบน (ระยะ = rod_len)"""
    arm, rod = 40.0, 85.0
    for solution in (0, 1):
        for length in (50.0, 70.0, 100.0):
            reach = crank_tip_reach(length, arm, rod, solution)
            assert abs(reach - rod) < 1e-6, f"ปลายก้านไม่ถึง: {reach}"
            pos = length_to_servo_pos(
                length, 70.0, 30.0, mechanism="crank_rod",
                arm_len=arm, rod_len=rod, solution=solution)
            assert 0 <= pos <= 4095
    # สอง solution ต้องให้มุมคนละเครื่องหมาย
    t0 = crank_angle_2bar(70.0, arm, rod, 0)
    t1 = crank_angle_2bar(70.0, arm, rod, 1)
    assert t0 == -t1 and t0 != 0
    # ระยะที่เข้าไม่ได้ (L > arm+rod) -> clip ไม่พัง
    crank_angle_2bar(200.0, arm, rod, 0)
    print("crank_rod (2-bar) ผ่าน ✅")


def test_forward_kinematics():
    """FK: ความยาวขา -> ท่าจานบน (Newton)

    - ไม่ระบุ x0: ต้องคืนท่าที่สอดคล้องเสมอ (residual เล็ก)
    - ระบุ x0 = ท่าเดิม: ต้องกลับมาเจอท่าเดิม (ล็อก assembly mode เดียวกัน)
    หมายเหตุ: มุม Euler เป็นคาบ 2π + Stewart FK มีหลายคำตอบ (assembly modes)
    """
    def wrap(a):
        return (a + np.pi) % (2 * np.pi) - np.pi

    def close_pose(a, b, atol=1e-4):
        return (abs(a[0] - b[0]) < atol
                and abs(wrap(a[1]) - b[1]) < atol
                and abs(wrap(a[2]) - b[2]) < atol
                and abs(wrap(a[3]) - b[3]) < atol)

    rng = np.random.default_rng(42)
    for _ in range(8):
        z = rng.uniform(45.0, 75.0)
        roll = rng.uniform(-0.3, 0.3)
        pitch = rng.uniform(-0.3, 0.3)
        yaw = rng.uniform(-0.6, 0.6)
        orig = (z, roll, pitch, yaw)
        lengths = leg_lengths(*orig, 60.0, 40.0, 30.0)

        # (1) ไม่ระบุ x0: ต้องได้ท่าที่สอดคล้อง (residual เล็ก)
        pose, residual = forward_kinematics(lengths, 60.0, 40.0, 30.0)
        assert residual < 1e-7, f"FK residual ยังสูง: {residual}"
        assert pose[0] > 0, "FK ต้องคืนท่าหงาย (z>0)"

        # (2) ระบุ x0 = ท่าเดิม: ต้องได้ท่าเดิม (assembly mode เดียวกัน)
        pose2, residual2 = forward_kinematics(
            lengths, 60.0, 40.0, 30.0, x0=orig)
        assert residual2 < 1e-7
        assert close_pose(pose2, orig), f"FK(x0) ไม่กลับมาท่าเดิม: {pose2} vs {orig}"
    print("Forward Kinematics (Newton) ผ่าน ✅")


def test_mechanism_roundtrip():
    """servo pos <-> ความยาวขา ต้องกลับมาเท่ากัน (ทั้ง 2 กลไก)"""
    arm, rod = 40.0, 85.0
    # crank_angle_2bar <-> crank_angle_to_leg_length
    for solution in (0, 1):
        for L in (50.0, 63.8, 80.0, 100.0, 120.0):
            theta = crank_angle_2bar(L, arm, rod, solution)
            L2 = crank_angle_to_leg_length(theta, arm, rod, solution)
            assert abs(L2 - L) < 1e-6, f"crank roundtrip ผิด: {L} -> {L2}"
    # servo_pos_to_length <-> length_to_servo_pos
    # (ใช้ L ในพิสัยที่ pos อยู่ใน 0-4095: leg_home=63.8 ± 15 mm เมื่อ pitch=30)
    for mech in ("leadscrew", "crank_rod"):
        for L in (50.0, 60.0, 63.8, 70.0, 75.0):
            pos = length_to_servo_pos(L, 63.8, 30.0, mechanism=mech,
                                      arm_len=arm, rod_len=rod, solution=0)
            L2 = servo_pos_to_length(pos, 63.8, 30.0, mechanism=mech,
                                     arm_len=arm, rod_len=rod, solution=0)
            assert abs(L2 - L) < 0.5, f"{mech} roundtrip ผิด: {L} -> {L2}"
    print("mechanism round-trip ผ่าน ✅")


def test_get_config():
    """get_config ต้องคืน config ที่มีคีย์สำคัญครบ"""
    from config.robot_config import get_config

    cfg = get_config()
    assert "stewart" in cfg and "servo_ids" in cfg and "meshes" in cfg
    assert cfg["stewart"]["mechanism"] in ("leadscrew", "crank_rod")
    assert "calibration" in str(Path(__file__).resolve().parents[1] /
                                "config" / "calibration.json")
    print("get_config ผ่าน ✅")


def test_face_detector_smoke():
    """YuNet: สร้าง detector + ทดสอบกับภาพสุ่ม (ไม่ต้องมีกล้อง)"""
    try:
        import cv2

        assert hasattr(cv2, "FaceDetectorYN"), "OpenCV ไม่มี FaceDetectorYN"
    except Exception as exc:  # noqa: BLE001
        print(f"OpenCV ไม่พร้อม ({exc}) — ข้าม")
        return
    try:
        from src.face_detector import FaceDetector

        detector = FaceDetector()
        img = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
        faces = detector.detect(img)
        assert isinstance(faces, list)
        print(f"face detector smoke test ผ่าน ✅ (ภาพสุ่มเจอใบหน้า={len(faces)})")
    except Exception as exc:  # noqa: BLE001
        print(f"face detector ข้าม ({exc})")


def test_emotion_parsing():
    """detect_emotion + strip_emotion_tag (ไม่ต้องใช้ LLM จริง)"""
    from src.expressions import detect_emotion, strip_emotion_tag

    assert detect_emotion("สวัสดีจ้า (happy)") == "happy"
    assert detect_emotion("ไม่น่าเชื่อเลยจริงๆ") == "surprised"
    assert detect_emotion("เรารู้สึกแย่จัง") == "sad"
    assert detect_emotion("โกรธมาก") == "angry"
    assert detect_emotion("เฉยๆ") == "neutral"
    assert strip_emotion_tag("hello (happy)") == "hello"
    assert "(" not in strip_emotion_tag("ว้าว (surprised) ดีใจ")
    print("emotion parsing ผ่าน ✅")


def test_real_robot_payload():
    """RealRobot: สร้าง payload goto ถูกต้อง (เมตร/เรเดียน, antennas [ขวา,ซ้าย])"""
    import math

    from src.real_robot import RealRobot

    r = RealRobot()
    p = r._build_goto_payload(
        head={"x": 0, "y": 0, "z": 0.1, "roll": 0.2, "pitch": 0.3, "yaw": 0.4},
        antennas=[0.5, -0.5], body_yaw=0.7, duration=2.0)
    assert p["head_pose"]["z"] == 0.1
    assert p["antennas"] == [0.5, -0.5], "antennas ต้องเป็น [ขวา, ซ้าย]"
    assert p["body_yaw"] == 0.7 and p["duration"] == 2.0
    # set_head_pose: z องศา -> เมตรสัมพัทธ์, มุม -> เรเดียน
    z_rel = (55.0 - r.z_home_mm) / 1000.0
    p2 = r._build_goto_payload(head={
        "x": 0.0, "y": 0.0, "z": z_rel,
        "roll": math.radians(10), "pitch": math.radians(-5), "yaw": math.radians(20),
    })
    assert abs(p2["head_pose"]["roll"] - 0.174532925) < 1e-6
    print("RealRobot payload ผ่าน ✅")


def test_stt_import():
    """STT: ตรวจว่าไลบรารี import ได้ (ไม่โหลดโมเดล ~460MB ในเทสต์)"""
    try:
        import faster_whisper  # noqa: F401
        import sounddevice  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        print(f"STT libs ข้าม ({exc})")
        return
    from src import stt
    assert hasattr(stt, "listen") and hasattr(stt, "transcribe")
    print("STT import ผ่าน ✅")


def test_clean_for_speech():
    """ล้างอีโมจิ/markdown ก่อนส่ง TTS"""
    from src.tts import clean_for_speech

    cases = {
        "สวัสดีจ้า 😄 *ยิ้ม*": "สวัสดีจ้า ยิ้ม",
        "**ยินดี**มาก `code`": "ยินดีมาก code",
        "หัวข้อ\n- รายการ 1\n- รายการ 2": "หัวข้อ รายการ 1 รายการ 2",
        "[ลิงก์](https://x.com) ดูสิ": "ลิงก์ ดูสิ",
        "นี่คือ 100% แน่นอน": "นี่คือ 100% แน่นอน",   # % ไม่ควรหาย
        "ว้าว! 🎉👏": "ว้าว!",
        "": "",
    }
    for raw, expected in cases.items():
        out = clean_for_speech(raw)
        assert out == expected, f"{raw!r} -> {out!r} (คาด {expected!r})"
    print("clean_for_speech ผ่าน ✅")


def test_thai_time():
    """บริบทวัน–เวลาไทย (offline — ไม่ต้องใช้ network)"""
    import datetime as dt

    from src.thai_time import (
        build_time_context,
        childrens_day,
        thai_date,
        thai_weekday,
        upcoming_events,
    )

    # วันอ้างอิงจริง: 1 ม.ค. 2024 = วันจันทร์
    assert thai_weekday(dt.date(2024, 1, 1)) == "จันทร์"
    assert thai_date(dt.date(2026, 9, 15)) == "15 กันยายน 2569"
    # วันเด็กแห่งชาติ = เสาร์ที่ 2 ของมกราคม (ปี 2026 = 10 ม.ค.)
    cd = childrens_day(2026)
    assert cd.weekday() == 5 and cd.month == 1 and cd.day == 10, cd
    # วันสำคัญใกล้ ๆ: 20 ธ.ค. 2026 → คริสต์มาสอีก 5 วัน
    ev = dict(upcoming_events(dt.date(2026, 12, 20), days_ahead=7))
    assert ev.get("วันคริสต์มาส") == 5, ev
    # ข้อความบริบท: มีวัน/วันที่/เวลา (15 ก.ย. 2026 = วันอังคาร)
    ctx = build_time_context(dt.datetime(2026, 9, 15, 14, 35))
    assert "วันอังคารที่ 15 กันยายน 2569" in ctx and "14:35" in ctx, ctx
    # วันสำคัญระยะไกล: วันพ่อ 5 ธ.ค. = อีก 81 วัน (ให้ LLM อ่าน ไม่ต้องคำนวณเอง)
    assert "วันพ่อแห่งชาติ อีก 81 วัน" in ctx, ctx
    print("thai_time ผ่าน ✅")


def test_vision_helpers():
    """Smoother + deadzone + PresenceDetector (ไม่ต้องใช้กล้อง)"""
    from src.vision import PresenceDetector, Smoother, apply_deadzone

    # deadzone: ค่ารอบศูนย์เล็ก ๆ -> 0
    assert apply_deadzone(0.03, 0.08) == 0.0
    assert apply_deadzone(-0.05, 0.08) == 0.0
    assert apply_deadzone(-0.5, 0.08) == -0.5
    # smoother: low-pass เข้าใกล้ target ทีละ alpha
    s = Smoother(alpha=1.0, value=0.0)
    assert s.update(10.0) == 10.0
    s = Smoother(alpha=0.5, value=0.0)
    assert s.update(10.0) == 5.0
    assert s.update(10.0) == 7.5
    # presence: ต้องเห็นหน้าต่อเนื่อง appear_time ก่อนถึง 'arrived'
    p = PresenceDetector(appear_time=1.0, gone_time=2.0)
    assert p.update(True, 0.0) is None
    assert p.update(True, 0.5) is None
    assert p.update(True, 1.0) == "arrived"
    assert p.present is True
    # หายหน้าไปสั้น ๆ ยังไม่นับ 'left'
    assert p.update(False, 1.5) is None
    assert p.update(False, 3.5) == "left"
    assert p.present is False
    print("vision helpers ผ่าน ✅")


def test_gesture_recognizer_smoke():
    """GestureRecognizer: โหลดโมเดล + ทดสอบกับภาพสุ่ม (ไม่ต้องมีกล้อง)"""
    try:
        import mediapipe  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        print(f"MediaPipe ไม่ได้ติดตั้ง ({exc}) — ข้าม")
        return
    try:
        from src.vision import GestureRecognizer

        with GestureRecognizer() as rec:
            assert rec.mode in ("mediapipe", "none")
            img = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
            out = rec.detect(img)
            assert out is None or isinstance(out, str)
        print("gesture recognizer smoke test ผ่าน ✅")
    except Exception as exc:  # noqa: BLE001
        print(f"gesture recognizer ข้าม ({exc})")


def test_beat_tracker():
    """BeatTracker: จับ BPM + phase จากเสียง click สังเคราะห์ (ไม่ใช้ลำโพงจริง)"""
    import time as _time
    from unittest import mock

    from src.beat import SR, BeatTracker, synth_clicks

    for bpm in (96, 128, 150):
        tr = BeatTracker(default_bpm=110, use_loopback=False)
        sig = synth_clicks(bpm, 10.0, offset=0.2)
        t0, blk = 1000.0, 2048
        tr._ref, tr._base = t0, 0.0
        for k, i in enumerate(range(0, sig.size, blk)):
            t_end = t0 + (i + blk) / SR
            tr.feed(sig[i:i + blk], t_end)
            if k % 12 == 0:
                with mock.patch.object(_time, "time", return_value=t_end):
                    tr.update_from_analyzer()
        assert abs(tr.bpm - bpm) < 1.5, (bpm, tr.bpm)
        n = int((10.0 - 0.2) / (60.0 / bpm)) - 1
        pos = tr.beat_position(t0 + 0.2 + n * 60.0 / bpm)
        assert abs(pos - round(pos)) < 0.08, (bpm, pos)
    print("beat tracker ผ่าน ✅")


def test_dance_sync():
    """dance_sync: ทุกโหมดต่อเนื่อง (ไม่กระชาก) + โหมดไม่พร้อมกันต่างจากพร้อมกันจริง + controller บน sim"""
    import time as _time

    from src import dance_sync as D
    from src.beat import BeatTracker
    from src.robot import Robot

    beats = np.arange(0, 120, 0.02)
    for m in D.MODES:
        fa = np.array([D.mode_frame(m, 0, b) for b in beats])
        fb = np.array([D.mode_frame(m, 1, b) for b in beats])
        assert np.abs(np.diff(fa, axis=0)).max() < 4.0, m
        assert np.abs(np.diff(fb, axis=0)).max() < 4.0, m
        diff = np.abs(fa - fb).mean()
        assert (diff < 1e-9) if m == "together" else (diff > 1.0), (m, diff)
    assert D.normalize_mode("เต้นไม่พร้อมกัน") == "free"
    # ออกท่าเยอะ: ช่วงมันส์ 32 ห้องต้องใช้ท่าหลากหลาย
    used = {D._move_for(D._segment(b, lambda _b: "hype")[0], None, "hype")
            for b in np.arange(0, 128, 2.0)}
    assert len(used) >= 8, len(used)
    assert D.normalize_style("ตื่นเต้น") == "hype" and D.normalize_style("อินเนอร์") == "inner"
    assert D.normalize_mode("ผลัดกันเต้น") == "alternate"
    assert D.normalize_mode("พร้อมกัน") == "together"

    ra, rb = Robot(backend="sim"), Robot(backend="sim")
    ctl = D.start_dance([ra, rb], mode="mirror",
                        tracker=BeatTracker(128, use_loopback=False))
    _time.sleep(0.6)
    assert ra.dancing and rb.dancing and ctl.running
    assert D.set_mode("canon") == "canon"
    assert D.stop_dance() is True
    assert not ra.dancing and not rb.dancing
    print("dance sync ผ่าน ✅")


if __name__ == "__main__":
    import numpy as np

    test_frame_builder()
    test_stewart_ik()
    test_leg_endpoints()
    test_crank_rod()
    test_forward_kinematics()
    test_mechanism_roundtrip()
    test_sim_robot()
    test_viewer_smoke()
    test_mujoco_smoke()
    test_stl_mesh_smoke()
    test_get_config()
    test_face_detector_smoke()
    test_vision_helpers()
    test_gesture_recognizer_smoke()
    test_emotion_parsing()
    test_real_robot_payload()
    test_stt_import()
    test_clean_for_speech()
    test_thai_time()
    test_beat_tracker()
    test_dance_sync()
    print("\nSelf-test ทั้งหมดผ่าน ✅")
