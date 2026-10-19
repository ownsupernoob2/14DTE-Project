#!/usr/bin/env python3
"""
check_gesture_setup.py — Diagnostic utility for Smart Mirror gesture tracking.

Run this script on any Raspberry Pi (or PC) to test dependencies, model files,
virtual camera loopback, and live hand tracking:

    python check_gesture_setup.py
    python check_gesture_setup.py --live
    python check_gesture_setup.py --camera /dev/video10
"""

import os
import re
import sys
import time
import platform
import subprocess

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
WARN = "\033[93m[WARN]\033[0m"
INFO = "\033[94m[INFO]\033[0m"

# Windows cmd doesn't enable ANSI colors unless configured; fallback cleanly if needed
if os.name == 'nt':
    try:
        os.system('')
    except Exception:
        PASS, FAIL, WARN, INFO = "[PASS]", "[FAIL]", "[WARN]", "[INFO]"

print("=" * 65)
print("  Smart Mirror — Hand Gesture Diagnostic & Verification Tool")
print("=" * 65)

failures = []
warnings = []

# ── 1. Python & System Architecture ──────────────────────────────────────────
py_ver = sys.version_info
arch = platform.machine()
os_name = platform.system()
print(f"\n{INFO} System: {os_name} {platform.release()} ({arch})")
print(f"{INFO} Python: {sys.executable} (version {py_ver.major}.{py_ver.minor}.{py_ver.micro})")

if py_ver < (3, 10):
    print(f"{FAIL} Python version is {py_ver.major}.{py_ver.minor}. MediaPipe requires Python >= 3.10.")
    failures.append("Upgrade Python to 3.10 or 3.11.")
else:
    print(f"{PASS} Python version is supported ({py_ver.major}.{py_ver.minor}).")

if os_name == "Linux" and ("arm" in arch or "aarch" in arch):
    if "64" not in arch and "aarch64" not in arch:
        print(f"{FAIL} Detected 32-bit ARM architecture ({arch}).")
        print("       MediaPipe official pre-built wheels require a 64-bit OS (aarch64).")
        print("       Please flash 64-bit Raspberry Pi OS.")
        failures.append("Raspberry Pi OS 64-bit (aarch64) is required for MediaPipe.")
    else:
        print(f"{PASS} 64-bit ARM architecture confirmed ({arch}).")

# ── 2. Check mediapipe import ────────────────────────────────────────────────
print("\nChecking MediaPipe library...")
try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    mp_version = getattr(mp, '__version__', 'unknown')
    print(f"{PASS} mediapipe is installed (v{mp_version}).")
except ImportError as e:
    print(f"{FAIL} mediapipe is NOT installed in this Python environment: {e}")
    print("       To fix: run:")
    print("           pip install \"mediapipe>=0.10.0,<=0.10.18\"")
    failures.append("mediapipe missing — install with: pip install 'mediapipe>=0.10.0,<=0.10.18'")
    mp = None

# ── 3. Check OpenCV ──────────────────────────────────────────────────────────
print("\nChecking OpenCV library...")
try:
    import cv2
    cv_ver = cv2.__version__
    print(f"{PASS} OpenCV (cv2) is installed (v{cv_ver}).")
except ImportError as e:
    print(f"{FAIL} OpenCV (cv2) is NOT installed: {e}")
    print("       To fix: sudo apt install python3-opencv  OR  pip install opencv-python")
    failures.append("OpenCV missing — install with: sudo apt install python3-opencv")
    cv2 = None

# ── 4. Check gesture_recognizer.task model ───────────────────────────────────
print("\nChecking gesture_recognizer.task model...")
model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gesture_recognizer.task")
if not os.path.exists(model_path):
    print(f"{FAIL} Model file missing at: {model_path}")
    print("       To fix: wget -O gesture_recognizer.task https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task")
    failures.append("Missing gesture_recognizer.task")
else:
    size_mb = os.path.getsize(model_path) / (1024 * 1024)
    if size_mb < 1.0:
        print(f"{FAIL} Model file exists but is unexpectedly small ({size_mb:.2f} MB). It may be corrupted.")
        failures.append("Corrupted gesture_recognizer.task")
    else:
        print(f"{PASS} Model file found ({size_mb:.2f} MB) at: {model_path}")

        # Try initializing GestureRecognizer
        if mp is not None:
            try:
                options = mp_vision.GestureRecognizerOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=model_path),
                    running_mode=mp_vision.RunningMode.VIDEO,
                    num_hands=2,
                    min_hand_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
                test_tracker = mp_vision.GestureRecognizer.create_from_options(options)
                test_tracker.close()
                print(f"{PASS} Successfully initialized MediaPipe GestureRecognizer with model.")
            except Exception as e:
                print(f"{FAIL} Failed to create GestureRecognizer: {e}")
                failures.append(f"GestureRecognizer initialization failed: {e}")

# ── 5. Check IPC Status File Permissions ─────────────────────────────────────
print("\nChecking IPC Status File (/tmp/gesture_status.json)...")
tmp_dir = os.environ.get("TEMP", os.environ.get("TMP", "/tmp"))
status_file = os.path.join(tmp_dir, "gesture_status.json")
try:
    test_file = f"{status_file}.test.{os.getpid()}"
    with open(test_file, "w") as f:
        f.write('{"test": true}')
    os.replace(test_file, f"{test_file}.renamed")
    if os.path.exists(f"{test_file}.renamed"):
        os.remove(f"{test_file}.renamed")
    print(f"{PASS} Atomic file write/replace verified in {tmp_dir}.")
except Exception as e:
    print(f"{FAIL} Cannot write to temp directory {tmp_dir}: {e}")
    failures.append(f"Temp directory permission error: {e}")

# ── 6. Check Camera Pipeline & Devices ───────────────────────────────────────
print("\nChecking Camera Pipeline & Devices...")
is_rpi = (os_name == "Linux" and ("arm" in arch or "aarch" in arch or os.path.exists("/dev/video10")))

camera_arg = None
for i, arg in enumerate(sys.argv):
    if arg == "--camera" and i + 1 < len(sys.argv):
        camera_arg = sys.argv[i + 1]

if camera_arg is not None:
    target_camera = int(camera_arg) if camera_arg.isdigit() else camera_arg
elif is_rpi:
    target_camera = "/dev/video10"
else:
    target_camera = 0

print(f"{INFO} Target camera: {target_camera}")

if is_rpi:
    if os.path.exists("/dev/video10"):
        print(f"{PASS} Virtual camera device /dev/video10 exists.")
    else:
        print(f"{WARN} /dev/video10 does not exist yet.")
        print("       (This device is created by start_smart_mirror.sh using v4l2loopback).")
        warnings.append("/dev/video10 virtual camera not found. Run start_smart_mirror.sh first.")

    # Check for rpicam-vid and ffmpeg processes
    try:
        ps_out = subprocess.check_output(["ps", "aux"], text=True)
        if "rpicam-vid" in ps_out:
            print(f"{PASS} rpicam-vid process is running.")
        else:
            print(f"{WARN} rpicam-vid is not currently running.")
        if "ffmpeg" in ps_out and "video10" in ps_out:
            print(f"{PASS} ffmpeg loopback pipe to /dev/video10 is running.")
        else:
            print(f"{WARN} ffmpeg /dev/video10 feed is not currently running.")
        if "face_recognize" in ps_out:
            print(f"{INFO} face_recognize daemon is currently running.")
        if "gesture_engine" in ps_out:
            print(f"{INFO} gesture_engine daemon is currently running.")
    except Exception:
        pass

def _parse_camera_target(target):
    if isinstance(target, int):
        return target
    if isinstance(target, str):
        target_str = target.strip()
        m = re.match(r'^/dev/video(\d+)$', target_str)
        if m:
            return int(m.group(1))
        if target_str.isdigit():
            return int(target_str)
    return target


def _try_open_capture(target):
    idx = _parse_camera_target(target)
    if isinstance(idx, int):
        if sys.platform == 'win32':
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            if cap.isOpened():
                return cap
            cap.release()
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                return cap
            cap.release()
        else:
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if cap.isOpened():
                return cap
            cap.release()
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                return cap
            cap.release()
    if isinstance(target, str):
        cap = cv2.VideoCapture(target)
        if cap.isOpened():
            return cap
        cap.release()
    return None


# Try opening camera if cv2 is available
if cv2 is not None:
    print(f"\nTesting camera capture on {target_camera!r}...")
    try:
        cap = _try_open_capture(target_camera)
        if cap is None:
            cap = cv2.VideoCapture(target_camera)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        opened = cap.isOpened()
        if not opened:
            print(f"{WARN} Could not open camera {target_camera!r}.")
            print("       If on Raspberry Pi, make sure start_smart_mirror.sh is running the camera pipeline.")
            warnings.append(f"Could not open camera {target_camera!r}")
        else:
            ret, frame = cap.read()
            if ret and frame is not None:
                h, w = frame.shape[:2]
                print(f"{PASS} Camera captured a valid frame ({w}x{h}).")

                # Test MediaPipe on real captured frame
                if mp is not None and os.path.exists(model_path):
                    try:
                        options = mp_vision.GestureRecognizerOptions(
                            base_options=mp_python.BaseOptions(model_asset_path=model_path),
                            running_mode=mp_vision.RunningMode.VIDEO,
                            num_hands=2,
                        )
                        tracker = mp_vision.GestureRecognizer.create_from_options(options)
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                        res = tracker.recognize_for_video(mp_image, int(time.time() * 1000))
                        tracker.close()
                        detected_count = len(res.hand_landmarks) if res.hand_landmarks else 0
                        print(f"{PASS} Full pipeline test passed! (Frame processed cleanly, detected {detected_count} hand(s)).")
                    except Exception as e:
                        print(f"{FAIL} MediaPipe failed to process camera frame: {e}")
                        failures.append(f"MediaPipe frame processing error: {e}")
            else:
                print(f"{WARN} Camera opened, but failed to read a frame.")
                warnings.append("Camera returned empty frame")
        cap.release()
    except Exception as e:
        print(f"{WARN} Exception when opening camera: {e}")
        warnings.append(f"Camera open exception: {e}")

# ── 7. Optional Live Gesture Tracking ────────────────────────────────────────
live_requested = ("--live" in sys.argv)
if live_requested and cv2 is not None and mp is not None and os.path.exists(model_path):
    print("\n" + "=" * 65)
    print("  Starting 10-Second Live Tracking Test (Wave your hand!)...")
    print("=" * 65)
    try:
        cap = _try_open_capture(target_camera)
        if cap is None:
            cap = cv2.VideoCapture(target_camera)
        options = mp_vision.GestureRecognizerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model_path),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=2,
        )
        tracker = mp_vision.GestureRecognizer.create_from_options(options)
        start_t = time.time()
        last_ms = -1
        while time.time() - start_t < 10.0:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.03)
                continue
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            now_ms = max(int((time.time() - start_t) * 1000), last_ms + 1)
            last_ms = now_ms
            res = tracker.recognize_for_video(mp_image, now_ms)
            if res.hand_landmarks:
                lm = res.hand_landmarks[0]
                hx = lm[0].x
                hy = lm[0].y
                side = "LEFT (Notices)" if hx < 0.50 else ("RIGHT (Timetable)" if hx > 0.62 else "CENTER")
                print(f"  [LIVE] Hand tracked! pos=({hx:.2f}, {hy:.2f}) -> Region: {side}")
            else:
                print("  [LIVE] Waiting for hand...", end="\r")
            time.sleep(0.05)
        cap.release()
        tracker.close()
        print("\n[LIVE] Test finished.")
    except Exception as e:
        print(f"[LIVE] Error during live tracking: {e}")

# ── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("  DIAGNOSTIC SUMMARY")
print("=" * 65)

if not failures:
    print(f"\n{PASS} All core prerequisites are satisfied!")
    if warnings:
        print(f"\n{WARN} Non-critical warnings observed:")
        for w in warnings:
            print(f"       - {w}")
    print("\nNext step: Run './start_smart_mirror.sh' on the Raspberry Pi.")
    print("To inspect gesture logs anytime: cat mirror/gesture_daemon.log")
    sys.exit(0)
else:
    print(f"\n{FAIL} Found {len(failures)} blocking issue(s):")
    for f in failures:
        print(f"       - {f}")
    print("\nPlease resolve the issues above and run check_gesture_setup.py again.")
    sys.exit(1)
