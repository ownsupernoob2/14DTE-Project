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
import sys
import threading
import time

import cv2
import requests
import numpy as np
import face_recognition
try:
    import faiss
except ImportError:
    faiss = None

from config import FACE_DATA_FILE, VISION_FILE
from timing_config import (
    IDLE_TIMEOUT_SEC,
    GUEST_GRACE_SEC,
    API_POLL_INTERVAL,
    API_POLL_GUEST,
    API_POLL_RECOGNISED,
    HEARTBEAT_INTERVAL,
)

# ── Constants ────────────────────────────────────────────────────────────────
API_URL = os.environ.get('API_URL', 'https://api.smartmirror.me')

STATE_IDLE  = "idle"
STATE_GUEST = "guest"
STATE_USER  = "user"

# ── Thread safety for the background API call ────────────────────────────────
api_lock = threading.Lock()
api_busy = False


ENCODINGS_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exported_encodings.json")

faiss_index = None
numpy_vectors = None
user_map = []
index_loaded = False


def download_and_load_index():
    global faiss_index, numpy_vectors, user_map, index_loaded
    print("[FAISS] Downloading vector encodings and user map from server...")
    try:
        res = requests.get(f"{API_URL}/api/download-index", timeout=10)
        if res.status_code == 200:
            data = res.json()
            with open(ENCODINGS_JSON_PATH, 'w') as f:
                json.dump(data, f)
            print("[FAISS] Vector encodings updated from server successfully.")
        else:
            print(f"[FAISS] Server returned status code {res.status_code}. Using local cache.")
    except Exception as e:
        print(f"[FAISS] Failed to download encodings: {e}. Using local cache.")

    # Load from local cache if it exists, and build FAISS index locally in RAM
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


def verify_face_worker(frame, on_result):
    """
    Background thread: Perform face verification natively in RAM using FAISS
    (or NumPy fallback) and local face encodings, then query the Go server using the
    lightweight user_id to fetch the widgets.
    """
    global api_busy, faiss_index, numpy_vectors, user_map, index_loaded
    try:
        # Ensure index is loaded
        if not index_loaded:
            download_and_load_index()

        if (faiss_index is None and numpy_vectors is None) or not user_map:
            print("[FAISS] No local index/map loaded. Cannot perform matching.")
            on_result(None, [], None)
            return

        # Find face encodings using face_recognition
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        encodings = face_recognition.face_encodings(rgb_frame)

        if not encodings:
            print("[FAISS] No face detected in frame.")
            on_result(None, [], None)
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
            res = requests.post(
                f"{API_URL}/api/verify-face",
                json={"user_id": matched_user_id},
                timeout=5,
            )
            if res.status_code == 200:
                data = res.json()
                user_id = data.get("user_id", "idle")
                widgets = data.get("widgets", [])
                rec = bool(user_id and user_id not in ("", "idle"))
                on_result(user_id, widgets, rec)
            else:
                print(f"[API] Failed to fetch widgets: status={res.status_code}")
                on_result(None, [], False)
        else:
            print("[FAISS] Face present but unrecognised.")
            on_result(None, [], False)

    except Exception as e:
        print(f"[FAISS] Error during local verification: {e}")
        on_result(None, [], None)
    finally:
        with api_lock:
            api_busy = False


def open_camera(rpi_mode: bool, camera_id: int) -> cv2.VideoCapture:
    """
    Open the right camera source.

    --rpi   → /dev/video10  (the v4l2loopback virtual device fed by rpicam-vid)
    default → webcam index  (camera_id, e.g. 4 on the dev Windows machine)
    """
    if rpi_mode:
        device = "/dev/video10"
        print(f"[CAMERA] RPi mode — opening {device}")
        cap = cv2.VideoCapture(device)
    else:
        if os.name == 'nt':
            cap = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(camera_id)
        print(f"[CAMERA] Desktop mode — opening camera index {camera_id}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        print(f"[ERROR] Could not open camera.")
        sys.exit(1)

    print("[CAMERA] Opened successfully.")
    return cap


def write_face_status(state, detected, faces_count,
                      session_user_id, session_user_name,
                      session_widgets, in_grace):
    """Atomically write the state JSON consumed by smart_mirror_pro.py.

    The .tmp file is placed in the same directory as the target so that
    os.replace() never crosses a filesystem boundary (which causes WinError 5
    when antivirus or another process briefly holds the handle).
    """
    is_recognised = (state == STATE_USER)
    data = {
        "state":      state,
        "detected":   detected,
        "recognized": is_recognised,
        "confidence": 1.0 if is_recognised else 0.0,
        "count":      faces_count,
        "user_id":    session_user_id   or "idle",
        "user_name":  session_user_name or "idle",
        "timestamp":  time.time(),
        "widgets":    session_widgets if is_recognised else [],
        "in_grace":   in_grace,
    }
    # Keep .tmp in same directory as the target so os.replace() is atomic
    # on every platform and never triggers a cross-device / access-denied error.
    target_dir = os.path.dirname(os.path.abspath(FACE_DATA_FILE))
    tmp = os.path.join(target_dir, 'face_status.tmp')
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


def main():
    parser = argparse.ArgumentParser(description="Smart Mirror — Face Recognition Daemon")
    parser.add_argument('--rpi',       action='store_true',
                        help="Raspberry Pi mode: read from /dev/video10 (v4l2loopback)")
    parser.add_argument('--camera-id', default=4, type=int,
                        help="Webcam index for desktop/dev mode (default: 4)")
    args = parser.parse_args()

    print("=" * 60)
    print("Smart Mirror — Face Recognition Daemon")
    print(f"  Mode       : {'Raspberry Pi (rpicam → /dev/video10)' if args.rpi else f'Desktop (camera {args.camera_id})'}")
    print(f"  API        : {API_URL}")
    print(f"  IDLE after : {IDLE_TIMEOUT_SEC}s  |  GUEST grace: {GUEST_GRACE_SEC}s")
    print(f"  Poll IDLE  : {API_POLL_INTERVAL}s  |  GUEST: {API_POLL_GUEST}s  |  USER: {API_POLL_RECOGNISED}s")
    print(f"  Status file: {FACE_DATA_FILE}")
    print("=" * 60)

    cap = open_camera(args.rpi, args.camera_id)

    # Download and load FAISS index and user map at startup
    download_and_load_index()

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    )

    # ── Shared API result (written by background thread, read by main loop) ──
    global api_busy
    result_lock    = threading.Lock()
    pending_result = {"user_id": None, "widgets": [], "rec": None, "fresh": False}

    def on_api_result(user_id, widgets, rec):
        with result_lock:
            pending_result["user_id"] = user_id
            pending_result["widgets"] = list(widgets)
            pending_result["rec"]     = rec
            pending_result["fresh"]   = True

    # ── State ────────────────────────────────────────────────────────────────
    state              = STATE_IDLE
    session_user_id    = None
    session_user_name  = None
    session_widgets    = []

    last_face_time     = 0.0
    last_api_call      = 0.0
    last_heartbeat     = 0.0
    unrecognised_since = None   # when the unrecognised streak started

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

            # ── Consume pending API result ───────────────────────────────────
            with result_lock:
                fresh = pending_result["fresh"]
                if fresh:
                    p_user_id = pending_result["user_id"]
                    p_widgets = pending_result["widgets"]
                    p_rec     = pending_result["rec"]
                    pending_result["fresh"] = False

            if fresh:
                if p_rec is True:
                    # Recognised → USER state (always immediate)
                    if state != STATE_USER or session_user_id != p_user_id:
                        print(f"[STATE] {state.upper()} -> USER  (user={p_user_id})")
                    state             = STATE_USER
                    session_user_id   = p_user_id
                    session_user_name = p_user_id
                    session_widgets   = p_widgets
                    unrecognised_since = None

                elif p_rec is False:
                    # Face found but not recognised — start/maintain grace timer
                    if unrecognised_since is None:
                        unrecognised_since = now
                        print(f"[STATE] Unrecognised face -- grace timer started "
                              f"({GUEST_GRACE_SEC}s)")

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
                    busy = api_busy
                if not busy:
                    last_api_call  = now
                    last_heartbeat = now
                    with api_lock:
                        api_busy = True
                    # Pass a copy of the frame to perform face recognition
                    frame_copy = frame.copy()
                    t = threading.Thread(target=verify_face_worker,
                                         args=(frame_copy, on_api_result), daemon=True)
                    t.start()

            # ── Timer-driven state transitions ───────────────────────────────

            # No face for IDLE_TIMEOUT_SEC → go IDLE
            no_face_duration = (now - last_face_time) if last_face_time > 0 else float('inf')
            if no_face_duration >= IDLE_TIMEOUT_SEC:
                if state != STATE_IDLE:
                    print(f"[STATE] {state.upper()} -> IDLE  "
                          f"(no face for {no_face_duration:.1f}s)")
                state             = STATE_IDLE
                session_user_id   = None
                session_user_name = None
                session_widgets   = []
                unrecognised_since = None

            # Unrecognised for GUEST_GRACE_SEC → go GUEST
            if (unrecognised_since is not None
                    and now - unrecognised_since >= GUEST_GRACE_SEC):
                if state != STATE_GUEST:
                    print(f"[STATE] {state.upper()} -> GUEST  "
                          f"(unrecognised for {now - unrecognised_since:.1f}s)")
                    session_user_id   = None
                    session_user_name = None
                    session_widgets   = []
                state = STATE_GUEST
                unrecognised_since = None  # grace consumed; stay GUEST via state

            # ── Compute in_grace for the status dot ──────────────────────────
            in_grace = (unrecognised_since is not None
                        and now - unrecognised_since < GUEST_GRACE_SEC
                        and state != STATE_USER)

            # ── Write status JSON ────────────────────────────────────────────
            write_face_status(state, detected, faces_count,
                              session_user_id, session_user_name,
                              session_widgets, in_grace)

            # ── Periodic console log ─────────────────────────────────────────
            if frame_counter % 90 == 0:
                print(f"[INFO] state={state}  detected={detected}  "
                      f"user={session_user_id}  widgets={len(session_widgets)}")

    except KeyboardInterrupt:
        print("\n[INFO] Shutting down.")
    finally:
        cap.release()


if __name__ == '__main__':
    main()
