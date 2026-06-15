import argparse
import base64
import cv2
import json
import os
import time
import requests
import numpy as np
import threading

from config import FACE_DATA_FILE, VISION_FILE

API_URL             = os.environ.get('API_URL', 'https://api.smartmirror.me')
IDLE_TIMEOUT_SEC    = float(os.environ.get('FACE_IDLE_TIMEOUT_SEC', '15.0'))  # No face → IDLE after 15s
GUEST_GRACE_SEC     = float(os.environ.get('FACE_GUEST_GRACE_SEC',   '4.0'))  # Unrecognised → GUEST after 4s
API_POLL_INTERVAL   = float(os.environ.get('FACE_API_POLL_SEC',      '1.0'))  # Poll every 1s when face present
API_POLL_RECOGNISED = float(os.environ.get('FACE_API_POLL_REC_SEC',  '5.0'))  # Poll every 5s when already recognised
HEARTBEAT_INTERVAL  = float(os.environ.get('FACE_HEARTBEAT_SEC',     '3.0'))  # Heartbeat when no face

# ── Mirror display states ───────────────────────────────────────────────────
STATE_IDLE  = "idle"   # No face present / timed out
STATE_GUEST = "guest"  # Unrecognised face confirmed (after grace period)
STATE_USER  = "user"   # Recognised registered user

# ── API thread lock ──────────────────────────────────────────────────────────
api_lock = threading.Lock()
api_busy = False


def verify_face_worker(b64_img, on_result):
    """Background thread: POST image to verify-face.
    Calls on_result(user_id, widgets, recognised) on 200,
    or on_result(None, [], False) on 401 (face found but not recognised),
    or on_result(None, [], None) on no-face / error (None = unknown).
    """
    global api_busy
    try:
        res = requests.post(
            f"{API_URL}/api/verify-face",
            json={"image": f"data:image/jpeg;base64,{b64_img}"},
            timeout=5,
        )
        if res.status_code == 200:
            data    = res.json()
            user_id = data.get("user_id", "idle")
            widgets = data.get("widgets", [])
            rec     = bool(user_id and user_id not in ("", "idle"))
            print(f"[API] 200 — user_id={user_id!r}, recognised={rec}, widgets={len(widgets)}")
            on_result(user_id, widgets, rec)
        elif res.status_code == 401:
            # Server found a face but couldn't match it
            body = {}
            try:
                body = res.json()
            except Exception:
                pass
            no_face = body.get("error", "").lower().startswith("no face")
            if no_face:
                print(f"[API] 401 — no face in frame")
                on_result(None, [], None)      # genuinely no face
            else:
                print(f"[API] 401 — face present but unrecognised")
                on_result(None, [], False)     # face found, not matched
        else:
            print(f"[API] {res.status_code} — treating as no-face")
            on_result(None, [], None)
    except Exception as e:
        print(f"[API] Request error: {e}")
        on_result(None, [], None)
    finally:
        with api_lock:
            api_busy = False


def main():
    global api_busy

    parser = argparse.ArgumentParser(description="Smart Mirror Camera Simulator")
    parser.add_argument('--camera-id', default=0, type=int,
                        help="Webcam index to try first (default 0)")
    parser.add_argument('--no-preview', action='store_true',
                        help="Disable preview window")
    parser.add_argument('--mock', action='store_true',
                        help="Force mock mode (no webcam)")
    args = parser.parse_args()

    print("==========================================================")
    print("Smart Mirror Camera & Face Simulator starting...")
    print(f"FACE_DATA_FILE: {FACE_DATA_FILE}")
    print(f"VISION_FILE:    {VISION_FILE}")
    print("==========================================================")

    # ── Haar face cascade ────────────────────────────────────────────────────
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    )

    # ── Camera helper ────────────────────────────────────────────────────────
    def open_camera(idx):
        if os.name == 'nt':
            return cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        return cv2.VideoCapture(idx)

    cap = None
    if not args.mock:
        print(f"[INFO] Attempting to open Camera ID: {args.camera_id}...")
        cap = open_camera(args.camera_id)
        ret, test = (cap.read() if cap.isOpened() else (False, None))
        if cap.isOpened() and ret and test is not None:
            print(f"[SUCCESS] Camera {args.camera_id} is working.")
        else:
            if cap:
                cap.release()
            cap = None
            print("[INFO] Scanning other camera indices (0-9)...")
            for i in range(10):
                if i == args.camera_id:
                    continue
                t = open_camera(i)
                if t.isOpened():
                    r, f = t.read()
                    if r and f is not None:
                        cap = t
                        args.camera_id = i
                        print(f"[SUCCESS] Found working camera at index {i}.")
                        break
                t.release()

        if cap is None:
            print("[WARNING] No working camera found. Falling back to mock mode.")
            args.mock = True
        else:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    print("\n[CONTROLS]")
    print("  'f' — toggle mock face login (instant USER layout)")
    print("  'm' — toggle horizontal mirror of preview")
    print("  'q' — quit\n")

    # ── Shared API result (written by background thread, read by main) ────────
    result_lock = threading.Lock()
    pending_result = {
        "user_id":  None,
        "widgets":  [],
        "rec":      None,   # True=recognised, False=face but unknown, None=no-face/error
        "fresh":    False,
    }

    def on_api_result(user_id, widgets, rec):
        with result_lock:
            pending_result["user_id"] = user_id
            pending_result["widgets"] = list(widgets)
            pending_result["rec"]     = rec
            pending_result["fresh"]   = True

    # ── Main state ───────────────────────────────────────────────────────────
    state               = STATE_IDLE
    session_user_id     = None      # current USER's id
    session_user_name   = None
    session_widgets     = []

    # Timing
    last_face_time      = 0.0   # last time Haar detected a face
    last_api_call       = 0.0
    last_heartbeat      = 0.0
    unrecognised_since  = None  # monotonic time when unrecognised streak started (NEVER reset by flicker)

    mock_face_active = False
    mirror_feed      = True
    detected         = False
    faces_count      = 0
    frame_counter    = 0

    if not args.no_preview:
        cv2.namedWindow("Smart Mirror Camera Simulator")

    try:
        while True:
            now = time.time()

            # ── Grab frame ───────────────────────────────────────────────────
            frame = None
            if not args.mock and cap is not None:
                ret, frame = cap.read()
                if not ret:
                    frame = None

            if frame is None:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, "NO CAMERA / MOCK ACTIVE", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            frame_counter += 1

            # Persist frame for AI vision
            if not args.mock and frame_counter % 5 == 0:
                try:
                    cv2.imwrite(VISION_FILE, frame)
                except Exception:
                    pass

            # ── Haar face detection (every 3rd frame) ─────────────────────
            if not args.mock and frame_counter % 3 == 0:
                small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
                gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.1, 4)
                detected    = len(faces) > 0
                faces_count = len(faces)
                for (x, y, w, h) in faces:
                    cv2.rectangle(frame, (x*2, y*2), ((x+w)*2, (y+h)*2), (255, 165, 0), 2)

            if mock_face_active:
                detected    = True
                faces_count = max(1, faces_count)

            if detected:
                last_face_time = now

            # ── Handle pending API result ─────────────────────────────────
            fresh = False
            with result_lock:
                if pending_result["fresh"]:
                    fresh = True
                    p_user_id = pending_result["user_id"]
                    p_widgets = pending_result["widgets"]
                    p_rec     = pending_result["rec"]
                    pending_result["fresh"] = False

            if fresh and not mock_face_active:
                if p_rec is True:
                    # ── Recognised → USER state ──────────────────────────
                    # Always switch immediately — registered user takes priority
                    # and a new recognised user overrides the old one.
                    if state != STATE_USER or session_user_id != p_user_id:
                        print(f"[STATE] {state.upper()} → USER  (user={p_user_id})")
                    state              = STATE_USER
                    session_user_id    = p_user_id
                    session_user_name  = p_user_id   # server may enrich this later
                    session_widgets    = p_widgets
                    unrecognised_since = None         # clear unrecognised streak

                elif p_rec is False:
                    # ── Face found but NOT recognised ────────────────────
                    if state == STATE_USER:
                        # Registered user still present — hold the USER state.
                        # The 401-unrecognised might be a bad frame angle.
                        # We only leave USER when no face at all for IDLE_TIMEOUT.
                        pass
                    else:
                        # In IDLE or GUEST: start (or continue) unrecognised streak.
                        if unrecognised_since is None:
                            unrecognised_since = now
                            print(f"[STATE] Unrecognised face detected — grace timer started")

                # p_rec is None → no face / error → do nothing (timers handle cleanup)

            # ── Fire API call ─────────────────────────────────────────────
            should_call = False
            poll = API_POLL_RECOGNISED if state == STATE_USER else API_POLL_INTERVAL
            if detected and now - last_api_call >= poll:
                should_call = True
            elif not detected and now - last_heartbeat >= HEARTBEAT_INTERVAL:
                should_call = True

            if mock_face_active:
                # Inject mock USER directly — don't hit the network
                state             = STATE_USER
                session_user_id   = "developer_user"
                session_user_name = "developer_user"
                session_widgets   = [
                    {"type": "clock"}, {"type": "weather"},
                    {"type": "timetable"}, {"type": "notices"}, {"type": "note"},
                ]
                unrecognised_since = None

            elif should_call and not args.mock:
                with api_lock:
                    busy = api_busy
                if not busy:
                    last_api_call  = now
                    last_heartbeat = now
                    with api_lock:
                        api_busy = True
                    _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    b64   = base64.b64encode(buf).decode('utf-8')
                    t = threading.Thread(target=verify_face_worker,
                                         args=(b64, on_api_result), daemon=True)
                    t.start()

            # ── State transitions driven by timers ────────────────────────

            # IDLE: no face for IDLE_TIMEOUT — clear everything
            no_face_duration = now - last_face_time if last_face_time > 0 else float('inf')
            if no_face_duration >= IDLE_TIMEOUT_SEC and not mock_face_active:
                if state != STATE_IDLE:
                    print(f"[STATE] {state.upper()} → IDLE  (no face for {no_face_duration:.1f}s)")
                state              = STATE_IDLE
                session_user_id    = None
                session_user_name  = None
                session_widgets    = []
                unrecognised_since = None

            # GUEST: unrecognised streak exceeds grace period
            if (unrecognised_since is not None
                    and now - unrecognised_since >= GUEST_GRACE_SEC
                    and state != STATE_USER   # registered user takes priority
                    and state != STATE_IDLE   # no-face already handled above
                    and not mock_face_active):
                if state != STATE_GUEST:
                    print(f"[STATE] {state.upper()} → GUEST  (unrecognised for {now - unrecognised_since:.1f}s)")
                state = STATE_GUEST

            # ── Build face_status.json ────────────────────────────────────
            is_recognised = (state == STATE_USER)
            in_grace      = (unrecognised_since is not None and
                             now - unrecognised_since < GUEST_GRACE_SEC and
                             state != STATE_USER)

            face_data = {
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
            try:
                tmp = FACE_DATA_FILE + '.tmp'
                with open(tmp, 'w') as f:
                    json.dump(face_data, f)
                os.replace(tmp, FACE_DATA_FILE)
            except Exception:
                pass

            # ── Preview window ─────────────────────────────────────────────
            if not args.no_preview:
                preview = cv2.flip(frame, 1) if mirror_feed else frame.copy()

                # Status indicator: green=USER, orange=grace/guest, dark=idle
                if state == STATE_USER:
                    dot_col = (0, 255, 0)
                    state_txt = f"USER: {session_user_id}"
                elif state == STATE_GUEST:
                    dot_col = (0, 165, 255)
                    state_txt = "GUEST"
                elif in_grace:
                    dot_col = (0, 140, 255)
                    grace_left = GUEST_GRACE_SEC - (now - unrecognised_since)
                    state_txt = f"GRACE ({grace_left:.1f}s)"
                else:
                    dot_col = (80, 80, 80)
                    state_txt = "IDLE"

                cv2.circle(preview, (620, 15), 8, dot_col, -1)
                cv2.putText(preview, state_txt,
                            (15, 415), cv2.FONT_HERSHEY_SIMPLEX, 0.55, dot_col, 2)
                cv2.putText(preview, f"Mirrored: {mirror_feed} [M]  Mock USER: [F]  Quit: [Q]",
                            (15, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (255, 255, 255), 1)

                cv2.imshow("Smart Mirror Camera Simulator", preview)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('f'):
                    mock_face_active = not mock_face_active
                    if not mock_face_active:
                        # Revert to IDLE on deactivate
                        state              = STATE_IDLE
                        session_user_id    = None
                        session_user_name  = None
                        session_widgets    = []
                        unrecognised_since = None
                        last_face_time     = 0.0
                    print(f"[SIMULATOR] Mock USER: {mock_face_active}")
                elif key == ord('m'):
                    mirror_feed = not mirror_feed
                    print(f"[SIMULATOR] Mirror: {mirror_feed}")
            else:
                time.sleep(0.03)

    except KeyboardInterrupt:
        pass
    finally:
        print("[INFO] Shutting down simulator...")
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
