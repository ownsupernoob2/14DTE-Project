"""
face_recognize.py — Smart Mirror face recognition daemon.

Usage:
    Raspberry Pi:   python face_recognize.py --rpi
    Windows / dev:  python face_recognize.py --camera-id 4

The script reads frames from the camera, runs a lightweight Haar face
detector, and periodically sends a JPEG to the server's /api/verify-face
endpoint.  It implements the full 3-state machine:

    IDLE   — no face present (or timed-out)
    GUEST  — unrecognised face has been in frame for GUEST_GRACE_SEC
    USER   — a registered user was recognised

State + widget data is written atomically to FACE_DATA_FILE (usually
/tmp/face_status.json on Linux, %TEMP%/face_status.json on Windows)
so that smart_mirror_pro.py can pick it up.

All timing constants live in timing_config.py — edit them there.
"""

import argparse
import base64
import json
import os
import re
import sys
import threading
import time
try:
    import pytesseract
except ImportError:
    pytesseract = None

import cv2
import requests
import numpy as np
try:
    import face_recognition
except ImportError:
    class _DummyFaceRecognition:
        @staticmethod
        def face_locations(*args, **kwargs):
            return []
        @staticmethod
        def face_encodings(*args, **kwargs):
            return []
    face_recognition = _DummyFaceRecognition
try:
    import faiss
except ImportError:
    faiss = None


from barcode_reader import BarcodeReader
from config import FACE_DATA_FILE, VISION_FILE
from timing_config import (
    IDLE_TIMEOUT_SEC,
    GUEST_IDLE_TIMEOUT_SEC,
    GUEST_GRACE_SEC,
    USER_HOLD_SEC,
    API_POLL_INTERVAL,
    API_POLL_GUEST,
    API_POLL_RECOGNISED,
    HEARTBEAT_INTERVAL,
    BARCODE_SESSION_SEC,
    BARCODE_SCAN_EVERY_N_FRAMES,
)

# ── Constants ────────────────────────────────────────────────────────────────
API_URL = os.environ.get('API_URL', 'https://api.smartmirror.me')

STATE_IDLE  = "idle"
STATE_GUEST = "guest"
STATE_USER  = "user"

AUTH_FACE    = "face"
AUTH_BARCODE = "barcode"

# ── Thread safety for the background API call ────────────────────────────────
api_lock = threading.Lock()
api_state = {"busy": False}

# Separate flag: a barcode lookup must not be blocked by an in-flight face call.
barcode_lock = threading.Lock()
barcode_state = {"busy": False}

server_online = True




ENCODINGS_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exported_encodings.json")

faiss_index = None
numpy_vectors = None
user_map = []
index_loaded = False
server_online = True


def download_and_load_index():
    global faiss_index, numpy_vectors, user_map, index_loaded, server_online

    # 1. Load from local cache immediately so camera starts without network delay
    if os.path.exists(ENCODINGS_JSON_PATH):
        try:
            with open(ENCODINGS_JSON_PATH, 'r') as f:
                data = json.load(f)
            
            vectors = data.get("vectors", [])
            user_map = data.get("user_map", [])
            
            if vectors:
                numpy_vectors = np.array(vectors, dtype=np.float32)
                print(f"[FAISS] Loaded {len(numpy_vectors)} vectors into RAM.")
            else:
                numpy_vectors = None
                print("[FAISS] Encodings file is empty.")
            
            if faiss is not None:
                if vectors:
                    dimension = 128
                    faiss_index = faiss.IndexFlatL2(dimension)
                    vectors_arr = np.array(vectors, dtype=np.float32)
                    faiss_index.add(vectors_arr)
                    print(f"[FAISS] Compiled index locally in RAM with {faiss_index.ntotal} vectors.")
                else:
                    faiss_index = faiss.IndexFlatL2(128)
                    print("[FAISS] Encodings file is empty. Index left empty.")
            else:
                print("[FAISS] faiss module is not installed. Native matching in RAM is disabled (falling back to NumPy).")
            index_loaded = True
        except Exception as e:
            print(f"[FAISS] Error compiling local index: {e}")

    # 2. Attempt remote sync in background thread so offline server does not delay startup
    def _sync():
        global server_online
        try:
            res = requests.get(f"{API_URL}/api/download-index", timeout=3)
            if res.status_code == 200:
                data = res.json()
                with open(ENCODINGS_JSON_PATH, 'w') as f:
                    json.dump(data, f)
                server_online = True
            else:
                server_online = False
        except Exception:
            server_online = False

    threading.Thread(target=_sync, daemon=True).start()


# The Haar cascade the fallback uses. Built once and shared: loading the XML
# costs a few milliseconds, which is not something to pay on every frame.
_fallback_cascade = None


def _haar_locations(gray):
    """Haar face boxes in face_recognition's (top, right, bottom, left) order."""
    global _fallback_cascade
    if _fallback_cascade is None:
        _fallback_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
    boxes = _fallback_cascade.detectMultiScale(gray, 1.1, 4)
    return [(y, x + w, y + h, x) for (x, y, w, h) in boxes]


def locate_faces(rgb_frame):
    """Find faces, trying progressively more tolerant detectors.

    dlib's HOG detector — face_recognition's default — is strict about pose. It
    reads a known-good frontal portrait perfectly (7 faces in dlib's own test
    image) but returns nothing for a head tilted back, chin up, or eyes shut,
    which is exactly how somebody stands at a mirror. The Haar cascade in the
    capture loop is far more forgiving, so it would report `detected=True` while
    this path printed "No face detected in frame." and recognition never even
    started.

    So: HOG first, because its boxes frame a face the way the encoder was
    trained to expect; then HOG upsampled once, which catches a face that is
    simply small in frame; then Haar, which gets a usable box out of a pose
    dlib will not accept at all. Encodings from a Haar box are a little looser,
    so this is a last resort rather than the default.
    """
    locations = face_recognition.face_locations(rgb_frame)
    if locations:
        return locations, "hog"

    locations = face_recognition.face_locations(rgb_frame,
                                                number_of_times_to_upsample=1)
    if locations:
        return locations, "hog-upsampled"

    gray = cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2GRAY)
    locations = _haar_locations(gray)
    if locations:
        return locations, "haar"

    return [], "none"


def verify_face_worker(frame, on_result):
    """
    Background thread: Perform face verification natively in RAM using FAISS
    (or NumPy fallback) and local face encodings, then query the Go server using the
    lightweight user_id to fetch the widgets.
    """
    global faiss_index, numpy_vectors, user_map, index_loaded, server_online
    try:
        # Ensure index is loaded
        if not index_loaded:
            download_and_load_index()

        # Detect all face locations in the frame first
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations, detector = locate_faces(rgb_frame)
        total_faces = len(face_locations)

        if total_faces == 0:
            print("[FAISS] No face detected in frame.", flush=True)
            on_result(None, [], None, server_online)
            return

        if (faiss_index is None and numpy_vectors is None) or not user_map:
            print("[FAISS] No local index/map loaded. Face detected, falling back to guest mode.")
            # Face is present, but cannot match locally and server index is absent
            on_result(None, [], False, False)
            return

        if detector != "hog":
            # Worth saying out loud: a run that only ever matches via the
            # fallback means the strict detector is not seeing the student, and
            # the looser box may be costing match accuracy.
            print(f"[FAISS] Located the face with the {detector} fallback.")

        # Calculate bounding box area for each detected face
        areas = []
        for i, loc in enumerate(face_locations):
            top, right, bottom, left = loc
            area = (bottom - top) * (right - left)
            areas.append(area)
            print(f"[FAISS] Detected face {i+1}/{total_faces}: area={area}px (top={top}, right={right}, bottom={bottom}, left={left})")

        # Exclusively select the largest face (closest to the camera)
        largest_idx = int(np.argmax(areas))
        largest_location = face_locations[largest_idx]
        print(f"[FAISS] Selecting closest/largest face (index={largest_idx}, area={areas[largest_idx]}px) out of {total_faces} total faces.")

        # Compute encoding ONLY for the largest face
        encodings = face_recognition.face_encodings(rgb_frame, known_face_locations=[largest_location])
        if not encodings:
            print("[FAISS] Failed to compute encoding for the selected face.")
            on_result(None, [], False, server_online)
            return

        encoding = np.array(encodings[0], dtype=np.float32).reshape(1, -1)

        if faiss_index is not None:
            # Search index (1 nearest neighbor)
            distances, indices = faiss_index.search(encoding, 1)
            dist = float(distances[0][0])
            idx = int(indices[0][0])
            # L2 distance returned by FAISS is squared Euclidean distance.
            # The face distance threshold is usually 0.40 (Euclidean), so squared is 0.16.
            euclidean_dist = np.sqrt(dist) if dist >= 0 else 1.0
        else:
            # Fallback to pure NumPy distance calculation
            diffs = numpy_vectors - encoding
            dists = np.linalg.norm(diffs, axis=1)
            idx = int(np.argmin(dists))
            euclidean_dist = float(dists[idx])

        print(f"[FAISS] Match query: index_idx={idx}, distance={euclidean_dist:.4f}")

        if euclidean_dist < 0.40 and 0 <= idx < len(user_map):
            matched_user_id = user_map[idx]
            print(f"[FAISS] Match success: {matched_user_id}. Fetching widgets...")

            # Send lightweight text string (user_id) to fetch the student's widgets
            try:
                res = requests.post(
                    f"{API_URL}/api/verify-face",
                    json={"user_id": matched_user_id},
                    timeout=4,
                )
                if res.status_code == 200:
                    data = res.json()
                    user_id = data.get("user_id", "idle")
                    widgets = data.get("widgets", [])
                    rec = bool(user_id and user_id not in ("", "idle"))
                    on_result(user_id, widgets, rec, True)
                else:
                    print(f"[API] Failed to fetch widgets: status={res.status_code}")
                    on_result(None, [], False, False)
            except Exception as e:
                print(f"[API] Server connection failed while fetching widgets: {e}")
                # Server is down: face matched locally but server cannot supply widgets
                on_result(None, [], False, False)
        else:
            print("[FAISS] Face present but unrecognised.")
            on_result(None, [], False, server_online)

    except Exception as e:
        print(f"[FAISS] Error during local verification: {e}")
        on_result(None, [], False, False)
    finally:
        with api_lock:
            api_state["busy"] = False


def verify_barcode_worker(code, on_result):
    """Background thread: resolve a scanned student ID to a user + widgets.

    Mirrors verify_face_worker's contract so a successful scan feeds the same
    state machine a recognised face does.
    """
    try:
        res = requests.post(
            f"{API_URL}/api/verify-barcode",
            json={"barcode": code},
            timeout=4,
        )
        if res.status_code == 200:
            data = res.json()
            user_id = data.get("user_id", "")
            if user_id and user_id not in ("", "idle"):
                print(f"[BARCODE] Sign-in accepted for {user_id}")
                on_result(user_id, data.get("widgets", []), True, True)
                return
            print("[BARCODE] Server returned no usable user_id.")
        elif res.status_code == 404:
            print(f"[BARCODE] {code} is not linked to any account.")
        elif res.status_code == 429:
            print("[BARCODE] Rate limited by server — slow down scanning.")
        else:
            print(f"[BARCODE] Verify failed: status={res.status_code}")
        on_result(None, [], False, True)
    except Exception as e:
        print(f"[BARCODE] Verify error (server offline?): {e}")
        on_result(None, [], False, False)
    finally:
        with barcode_lock:
            barcode_state["busy"] = False


def _try_open_capture(target):
    """Open VideoCapture trying index or string path across backends."""
    idx = _parse_camera_target(target)

    # 1. On Windows: DirectShow
    if sys.platform == 'win32' and isinstance(idx, int):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if cap.isOpened():
            return cap
        cap.release()
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            return cap
        cap.release()
        return None

    # 2. On Linux:
    # Try V4L2 by device path first. On the Pi, OpenCV refuses the
    # v4l2loopback device by index ("can't open camera by index") but
    # opens /dev/video42 fine by path.
    if isinstance(target, str):
        cap = cv2.VideoCapture(target, cv2.CAP_V4L2)
        if cap.isOpened():
            return cap
        cap.release()

    # Then V4L2 by integer index
    if isinstance(idx, int):
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if cap.isOpened():
            return cap
        cap.release()

    # Try device string with default backend (e.g. GStreamer / FFmpeg)
    if isinstance(target, str):
        cap = cv2.VideoCapture(target)
        if cap.isOpened():
            return cap
        cap.release()

    # Try integer index with default backend
    if isinstance(idx, int):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            return cap
        cap.release()

    # OpenCV's V4L2 backend can refuse the Pi's v4l2loopback device even though
    # ffmpeg reads it fine, so fall back to reading it through ffmpeg.
    if sys.platform != 'win32' and isinstance(target, str) and target.startswith('/dev/video'):
        try:
            from loopback_capture import FFmpegPipeCapture
            cap = FFmpegPipeCapture(target)
            if cap.isOpened():
                print(f"[CAMERA] OpenCV could not open {target}; reading it through ffmpeg instead.", flush=True)
                return cap
            cap.release()
        except Exception as e:
            print(f"[CAMERA] ffmpeg fallback failed: {e}", flush=True)

    return None


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


def open_camera(rpi_mode: bool, camera_id: int) -> cv2.VideoCapture:
    if rpi_mode:
        target = os.environ.get("MIRROR_LOOPBACK_DEV", "/dev/video42")
    else:
        target = camera_id

    idx = _parse_camera_target(target)
    print(f"[CAMERA] Connecting to camera device {target} (index {idx})...", flush=True)

    max_attempts = 10 if rpi_mode else 3
    for attempt in range(1, max_attempts + 1):
        cap = _try_open_capture(target)

        if cap is not None and cap.isOpened():
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ret, frame = cap.read()
            if ret and frame is not None:
                print(f"[CAMERA] Successfully opened camera on attempt {attempt}.", flush=True)
                return cap
            cap.release()

        if attempt < max_attempts:
            time.sleep(1.0)

    print(f"[ERROR] Could not open camera {target} after {max_attempts} attempts.", flush=True)
    sys.exit(1)
    
def write_face_status(state, detected, faces_count,
                      session_user_id, session_user_name,
                      session_widgets, in_grace, auth_method=AUTH_FACE,
                      server_online=True):
    """Atomically write the state JSON consumed by smart_mirror_pro.py.

    The .tmp file is placed in the same directory as the target so that
    os.replace() never crosses a filesystem boundary (which causes WinError 5
    when antivirus or another process briefly holds the handle).
    """
    # ── Preserve active barcode session when barcode was scanned ─────────
    existing_is_barcode = False
    if os.path.exists(FACE_DATA_FILE):
        try:
            with open(FACE_DATA_FILE) as f:
                cur = json.load(f)
            # Hold active barcode login session for up to 300s
            if cur.get('auth_method') == 'barcode' and (time.time() - cur.get('timestamp', 0) < 300.0):
                existing_is_barcode = True
                if state in (STATE_IDLE, STATE_GUEST):
                    return
        except Exception:
            pass

    is_recognised = (state == STATE_USER)
    final_auth = "barcode" if existing_is_barcode else (auth_method if is_recognised else "")
    data = {
        "state":         state,
        "detected":      detected,
        "recognized":    is_recognised,
        "confidence":    1.0 if is_recognised else 0.0,
        "count":         faces_count,
        "user_id":       session_user_id   or "idle",
        "user_name":     session_user_name or "idle",
        "timestamp":     time.time(),
        "widgets":       session_widgets if is_recognised else [],
        "in_grace":      in_grace,
        # How this session was established, so the mirror can label it.
        "auth_method":   final_auth,
        "server_online": bool(server_online),
        "server_status": "online" if server_online else "offline",
    }
    # Keep .tmp in same directory as the target so os.replace() is atomic
    # on every platform and never triggers a cross-device / access-denied error.
    # The name carries the pid: two daemons left running from separate launches
    # would otherwise fight over one scratch file and both fail to publish.
    target_dir = os.path.dirname(os.path.abspath(FACE_DATA_FILE))
    tmp = os.path.join(target_dir, f'face_status.{os.getpid()}.tmp')
    try:
        with open(tmp, 'w') as f:
            json.dump(data, f)
        # Retry up to 3 times — on Windows, smart_mirror_pro.py briefly holds a
        # shared read handle on the target which can cause os.replace() to raise
        # PermissionError.  On Linux/Pi the first attempt always succeeds.
        for attempt in range(3):
            try:
                os.replace(tmp, FACE_DATA_FILE)
                break
            except PermissionError:
                if attempt < 2:
                    time.sleep(0.005)   # wait 5ms then retry
    except Exception as e:
        print(f"[ERROR] Writing face_status: {e}")


def watch_parent():
    """Stop the daemon when the parent mirror process closes our stdin."""
    def wait_for_eof():
        try:
            sys.stdin.read()
        except Exception:
            pass
        print("[FACE] Parent closed the pipe — exiting.")
        os._exit(0)

    threading.Thread(target=wait_for_eof, daemon=True).start()


def main():
    global server_online
    server_online = True

    parser = argparse.ArgumentParser(description="Smart Mirror — Face Recognition Daemon")
    parser.add_argument('--rpi',       action='store_true',
                        help="Raspberry Pi mode: read from /dev/video20 (v4l2loopback)")
    default_cam = int(os.environ.get('MIRROR_CAMERA_INDEX', '0'))
    parser.add_argument('--camera-id', default=default_cam, type=int,
                        help=f"Webcam index for desktop/dev mode (default: {default_cam})")
    parser.add_argument('--enable-camera-barcode', action='store_true',
                        help="Enable legacy camera frame student ID barcode sign-in")
    parser.add_argument('--no-barcode', action='store_true',
                        help="Disable student ID barcode sign-in")
    parser.add_argument('--exit-with-parent', action='store_true',
                        help="Exit when parent closes stdin pipe")
    args = parser.parse_args()

    if args.exit_with_parent:
        watch_parent()

    print("=" * 60)
    print("Smart Mirror — Face Recognition Daemon")
    print(f"  Mode       : {'Raspberry Pi (rpicam → loopback)' if args.rpi else f'Desktop (camera {args.camera_id})'}")
    print(f"  API        : {API_URL}")
    print(f"  IDLE after : {IDLE_TIMEOUT_SEC}s  |  GUEST grace: {GUEST_GRACE_SEC}s  "
          f"|  USER hold: {USER_HOLD_SEC}s")
    print(f"  Poll IDLE  : {API_POLL_INTERVAL}s  |  GUEST: {API_POLL_GUEST}s  |  USER: {API_POLL_RECOGNISED}s")
    print(f"  Status file: {FACE_DATA_FILE}")

    cap = open_camera(args.rpi, args.camera_id)

    # ── Barcode sign-in (camera decoding is off by default since physical scanner acts as keyboard) ──
    barcode_reader = None
    barcode_backend = 'disabled (using physical scanner input)'
    if args.enable_camera_barcode and not args.no_barcode:
        reader = BarcodeReader()
        if reader.available:
            barcode_reader = reader
            barcode_backend = reader.backend
    print(f"  Barcode    : {barcode_backend}")
    print("=" * 60)

    # Download and load FAISS index and user map at startup
    download_and_load_index()

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    )

    # ── Shared API result (written by background thread, read by main loop) ──
    result_lock    = threading.Lock()
    pending_result = {"user_id": None, "widgets": [], "rec": None, "server_online": True, "fresh": False}

    def on_api_result(user_id, widgets, rec, is_server_online=True):
        global server_online
        server_online = is_server_online
        with result_lock:
            pending_result["user_id"] = user_id
            pending_result["widgets"] = list(widgets)
            pending_result["rec"]     = rec
            pending_result["server_online"] = is_server_online
            pending_result["fresh"]   = True

    # ── Barcode result (separate slot so it cannot be lost to a face result) ──
    barcode_result = {"user_id": None, "widgets": [], "ok": False, "server_online": True, "fresh": False}

    def on_barcode_result(user_id, widgets, ok, is_server_online=True):
        global server_online
        server_online = is_server_online
        with result_lock:
            barcode_result["user_id"] = user_id
            barcode_result["widgets"] = list(widgets)
            barcode_result["ok"]      = bool(ok)
            barcode_result["server_online"] = is_server_online
            barcode_result["fresh"]   = True

    # ── State ────────────────────────────────────────────────────────────────
    state              = STATE_IDLE
    session_user_id    = None
    session_user_name  = None
    session_widgets    = []
    auth_method        = AUTH_FACE

    last_face_time     = 0.0
    last_api_call      = 0.0
    last_heartbeat     = 0.0
    last_server_check  = 0.0
    unrecognised_since = None   # when the unrecognised streak started
    barcode_until      = 0.0    # a scan holds the dashboard until this time

    detected           = False
    faces_count        = 0
    frame_counter      = 0

    try:
        while True:
            now = time.time()

            # ── Grab frame ───────────────────────────────────────────────────
            ret, frame = cap.read()
            if not ret or frame is None:
                print("[WARN] Frame grab failed — retrying...")
                time.sleep(0.1)
                continue

            frame_counter += 1

            # Save every 5th frame for the AI vision file (used by other tools)
            if frame_counter % 5 == 0:
                try:
                    cv2.imwrite(VISION_FILE, frame)
                except Exception:
                    pass

            # ── Haar face detection (every 3rd frame — reduces CPU load) ────
            if frame_counter % 3 == 0:
                small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
                gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.1, 4)
                detected    = len(faces) > 0
                faces_count = len(faces)

            if detected:
                last_face_time = now
                # Start grace timer as soon as a face appears in IDLE so guest mode activates
                # even if the server is offline or fails to recognize the user.
                if state == STATE_IDLE and unrecognised_since is None and not barcode_active:
                    unrecognised_since = now
                    print(f"[STATE] Face detected in IDLE -- grace timer started ({GUEST_GRACE_SEC}s)")
            else:
                if state == STATE_IDLE and unrecognised_since is not None:
                    # Dropped face before grace period elapsed; reset
                    unrecognised_since = None

            # ── Barcode scan ─────────────────────────────────────────────────
            if barcode_reader is not None and frame_counter % BARCODE_SCAN_EVERY_N_FRAMES == 0:
                code = barcode_reader.detect(frame)
                if code:
                    with barcode_lock:
                        bc_busy = barcode_state["busy"]
                    if bc_busy:
                        print(f"[BARCODE] Read {code} while a lookup was in flight — ignoring.")
                    else:
                        print(f"[BARCODE] Read {code} — verifying...")
                        with barcode_lock:
                            barcode_state["busy"] = True
                        threading.Thread(target=verify_barcode_worker,
                                         args=(code, on_barcode_result), daemon=True).start()

            # ── Consume pending barcode result ───────────────────────────────
            with result_lock:
                bc_fresh = barcode_result["fresh"]
                if bc_fresh:
                    bc_user_id = barcode_result["user_id"]
                    bc_widgets = barcode_result["widgets"]
                    bc_ok      = barcode_result["ok"]
                    if "server_online" in barcode_result:
                        server_online = barcode_result["server_online"]
                    barcode_result["fresh"] = False

            if bc_fresh and bc_ok and bc_user_id:
                if state != STATE_USER or session_user_id != bc_user_id:
                    print(f"[STATE] {state.upper()} -> USER  (barcode, user={bc_user_id})")
                state              = STATE_USER
                session_user_id    = bc_user_id
                session_user_name  = bc_user_id
                session_widgets    = bc_widgets
                auth_method        = AUTH_BARCODE
                unrecognised_since = None
                barcode_until      = now + BARCODE_SESSION_SEC

            barcode_active = now < barcode_until

            # ── Consume pending API result ───────────────────────────────────
            with result_lock:
                fresh = pending_result["fresh"]
                if fresh:
                    p_user_id       = pending_result["user_id"]
                    p_widgets       = pending_result["widgets"]
                    p_rec           = pending_result["rec"]
                    p_server_online = pending_result.get("server_online", True)
                    pending_result["fresh"] = False
                    server_online   = p_server_online

            if fresh:
                if p_rec is True:
                    # Recognised → USER state (always immediate)
                    if state != STATE_USER or session_user_id != p_user_id:
                        print(f"[STATE] {state.upper()} -> USER  (user={p_user_id})")
                    state             = STATE_USER
                    session_user_id   = p_user_id
                    session_user_name = p_user_id
                    session_widgets   = p_widgets
                    auth_method       = AUTH_FACE
                    unrecognised_since = None
                    # A face beats a stale barcode session for the same person.
                    barcode_until     = 0.0

                elif p_rec is False and not barcode_active:
                    # Face found but not recognised (or server down) — start/maintain grace timer.
                    # Skipped during a barcode session: the student already
                    # identified themselves, so an unrecognised face (theirs, or a
                    # passer-by behind them) must not demote them to GUEST.
                    if unrecognised_since is None:
                        unrecognised_since = now
                        window = USER_HOLD_SEC if state == STATE_USER else GUEST_GRACE_SEC
                        print(f"[STATE] Unrecognised face -- "
                              f"{'holding the signed-in student' if state == STATE_USER else 'grace timer started'} "
                              f"({window}s)")

                # p_rec is None → no face / error → let timers handle it

            # ── Fire API call ────────────────────────────────────────────────
            if state == STATE_USER:
                poll = API_POLL_RECOGNISED
            elif state == STATE_GUEST:
                poll = API_POLL_GUEST
            else:
                poll = API_POLL_INTERVAL

            should_call = (detected and now - last_api_call >= poll) or \
                          (not detected and now - last_heartbeat >= HEARTBEAT_INTERVAL)

            if should_call:
                with api_lock:
                    busy = api_state["busy"]
                if not busy:
                    last_api_call  = now
                    last_heartbeat = now
                    with api_lock:
                        api_state["busy"] = True
                    # Pass a copy of the frame to perform face recognition
                    frame_copy = frame.copy()
                    t = threading.Thread(target=verify_face_worker,
                                         args=(frame_copy, on_api_result), daemon=True)
                    t.start()

            # ── Periodic server health probe every 15s ───────────────────────
            if now - last_server_check >= 15.0:
                last_server_check = now
                def _check_health():
                    global server_online
                    try:
                        h = requests.get(f"{API_URL}/health", timeout=3)
                        server_online = (h.status_code == 200)
                    except Exception:
                        server_online = False
                threading.Thread(target=_check_health, daemon=True).start()

            # ── Timer-driven state transitions ───────────────────────────────
            # A live barcode session outranks the face timers: the student made a
            # deliberate gesture to sign in, so it holds for its full duration
            # even if they look away or their face is never recognised.

            # No face for timeout threshold (5s for guest, 30s for user) → go IDLE
            no_face_duration = (now - last_face_time) if last_face_time > 0 else float('inf')
            idle_thresh = GUEST_IDLE_TIMEOUT_SEC if state == STATE_GUEST else IDLE_TIMEOUT_SEC
            if no_face_duration >= idle_thresh and not barcode_active:
                if state != STATE_IDLE:
                    print(f"[STATE] {state.upper()} -> IDLE  "
                          f"(no face for {no_face_duration:.1f}s)")
                state             = STATE_IDLE
                session_user_id   = None
                session_user_name = None
                session_widgets   = []
                auth_method       = AUTH_FACE
                unrecognised_since = None

            # Unrecognised for long enough → go GUEST. A signed-in student gets
            # USER_HOLD_SEC rather than the much shorter GUEST_GRACE_SEC: they
            # have already been identified, so a failed match is far more likely
            # to be one bad frame than a different person.
            demote_after = USER_HOLD_SEC if state == STATE_USER else GUEST_GRACE_SEC
            if (unrecognised_since is not None
                    and now - unrecognised_since >= demote_after
                    and not barcode_active):
                if state != STATE_GUEST:
                    print(f"[STATE] {state.upper()} -> GUEST  "
                          f"(unrecognised for {now - unrecognised_since:.1f}s)")
                    session_user_id   = None
                    session_user_name = None
                    session_widgets   = []
                    auth_method       = AUTH_FACE
                state = STATE_GUEST
                unrecognised_since = None  # grace consumed; stay GUEST via state

            # Barcode session just lapsed with nothing else holding the screen →
            # drop straight back to IDLE so the next student starts clean.
            if (auth_method == AUTH_BARCODE and not barcode_active
                    and state == STATE_USER):
                print(f"[STATE] USER -> IDLE  (barcode session expired)")
                state             = STATE_IDLE
                session_user_id   = None
                session_user_name = None
                session_widgets   = []
                auth_method       = AUTH_FACE
                if barcode_reader is not None:
                    # Let the same card sign in again straight away.
                    barcode_reader.reset()

            # ── Compute in_grace for the status dot ──────────────────────────
            # Always the *guest* grace, never USER_HOLD_SEC: the dot means "an
            # unknown face is being given a moment to resolve". A signed-in
            # student holding through a bad frame is excluded by the state check
            # anyway, and their hold is long enough that a countdown dot would
            # just be a light left on.
            in_grace = (unrecognised_since is not None
                        and now - unrecognised_since < GUEST_GRACE_SEC
                        and state != STATE_USER)

            # ── Write status JSON ────────────────────────────────────────────
            write_face_status(state, detected, faces_count,
                              session_user_id, session_user_name,
                              session_widgets, in_grace, auth_method,
                              server_online=server_online)

            # ── Periodic console log ─────────────────────────────────────────
            if frame_counter % 90 == 0:
                print(f"[INFO] state={state}  detected={detected}  "
                      f"user={session_user_id}  via={auth_method}  "
                      f"widgets={len(session_widgets)}")

    except KeyboardInterrupt:
        print("\n[INFO] Shutting down.")
    finally:
        cap.release()


if __name__ == '__main__':
    main()
