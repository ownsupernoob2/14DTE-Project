# mirror/gesture_engine.py
"""
Region-based hand gesture engine for the smart mirror.

The mirror has no touchscreen and no cursor, so this does not emulate a mouse.
Instead the screen is split into the same columns the UI uses, and whichever
region your hand is generally in is the region you are interacting with:

    left   (x < 0.50)  → the notices column, drawn on the left of the screen
    center             nothing (a neutral resting area)
    right  (x > 0.62)  → the timetable peek, drawn on the right

Which physical side of you that corresponds to depends on where the camera is
mounted; see default_flip().

Within a region an open palm engages control: moving it up and down scrolls, and
touching your thumb and index finger together is a click. Dwelling in the right
region peeks the timetable, which then slides away to reveal the King's Week grid
underneath it.

State is published to a JSON file that smart_mirror_pro.py polls, so the
vision work stays out of the Qt event loop.
"""

import argparse
import json
import math
import os
import re
import sys
import socket
import threading
import time

import cv2

GESTURE_UDP_PORT = 50123

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
except ImportError:
    mp = None

GESTURE_STATUS_FILE = os.path.join(
    os.environ.get("TEMP", os.environ.get("TMP", "/tmp")), "gesture_status.json"
)

# The hand tracker's weights. Resolved next to this file rather than against the
# working directory.
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "gesture_recognizer.task")

# The Pi reads its own v4l2loopback device that start_smart_mirror.sh feeds.
# v4l2loopback only lets one reader stream at a time, so the face daemon gets
# /dev/video42 and this daemon gets a second copy of the feed on /dev/video43.
RPI_CAMERA = (os.environ.get("MIRROR_GESTURE_DEV")
              or os.environ.get("MIRROR_LOOPBACK_DEV", "/dev/video43"))


def default_flip():
    """Whether to mirror the frame, unless told otherwise.

    Defaults to True so moving hand to user's left maps to mirror's left.
    Can be overridden via GESTURE_FLIP environment variable or --no-flip flag.
    """
    env = os.environ.get("GESTURE_FLIP")
    if env is not None:
        return env not in ("0", "false", "False", "no", "off", "")
    return True

# ── Region boundaries ────────────────────────────────────────────────────────
REGION_LEFT_EDGE  = 0.50
REGION_RIGHT_EDGE = 0.62

REGION_LEFT   = "left"
REGION_CENTER = "center"
REGION_RIGHT  = "right"

# ── Tuning ───────────────────────────────────────────────────────────────────
PINCH_ENTER_RATIO    = 0.28   # thumb-index gap / palm size to enter pinch
PINCH_EXIT_RATIO     = 0.44   # gap to release pinch (hysteresis)
MIN_PALM_SIZE        = 0.02   # below this the hand is too far away to trust

TAP_MAX_SEC         = 0.65   # pinch held up to 0.65s without drag is a tap
TAP_COOLDOWN_SEC    = 0.35   # ignore repeat taps inside this window
DRAG_TAP_THRESHOLD = 0.040  # movement threshold during pinch to distinguish tap vs drag
DRAG_SCROLL_GAIN    = 1100.0 # movement -> scroll pixels
DRAG_DEADZONE       = 0.003  # ignore minute jitter below this
FLING_VELOCITY_SCALE = 200.0 # release velocity multiplier for inertia fling
TAP_VELOCITY_MAX    = 0.08   # if release velocity > this, treat as drag (hand was moving)

TOP_RIGHT_X         = 0.62   # top-right quadrant dwell threshold
TOP_RIGHT_Y         = 0.18   # top-right height limit
RIGHT_DWELL_SEC     = 1.6    # hold hand in top-right region for 1.6s
HEARTBEAT_SEC       = 0.06   # publish UDP at least 16x/sec for smooth trail
HAND_LOST_SEC       = 0.4    # no landmarks for this long -> hand is gone

POSITION_QUANTUM    = 1.0 / 96


def classify_region(x):
    if x < REGION_LEFT_EDGE:
        return REGION_LEFT
    if x > REGION_RIGHT_EDGE:
        return REGION_RIGHT
    return REGION_CENTER


def _parse_camera_target(target):
    """Return integer index if target is an int or '/dev/videoN' / 'N', else raw target."""
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
    """Open VideoCapture trying index (with V4L2 / DirectShow) or string path."""
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

    # Try device string with default backend
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


class GestureEngine:
    def __init__(self, camera_id=0, flip=None):
        self.camera_id = camera_id
        self.flip = default_flip() if flip is None else flip
        self.running = False
        self.tracker = None
        self._init_tracker()

        self.frame_aspect = 1.0

        # ── Tracking state ───────────────────────────────────────────────────
        self.present = False
        self.region = None
        self.hand_x = 0.0
        self.hand_y = 0.0
        self.last_seen = 0.0

        self.pinched = False
        self.pinch_start = None
        self.drag_start_y = None
        self.last_drag_y = None
        self.drag_dist = 0.0
        self.drag_velocity = 0.0
        self.last_frame_time = 0.0
        self.scroll_delta = 0

        self.last_open_y = None
        self.last_open_t = 0.0
        self.open_swipe_velocity = 0.0

        self.last_tap_time = None     # None = no tap yet, so no cooldown to serve

        self.right_since = None
        self.right_armed = True
        self.right_dwell_progress = 0.0

        self.seq = 0
        self.last_write = 0.0
        self.last_payload = None

        self._tmp_file = f"{GESTURE_STATUS_FILE}.{os.getpid()}.{id(self):x}.tmp"

    def _init_tracker(self):
        """Build the MediaPipe hand tracker."""
        if mp is None:
            print("[GESTURE] mediapipe not installed — gesture control disabled.")
            return
        if not os.path.exists(MODEL_PATH):
            print(f"[GESTURE] Missing {os.path.basename(MODEL_PATH)} — download gesture_recognizer.task. "
                  f"Gesture control disabled.")
            return
        try:
            options = mp_vision.GestureRecognizerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
                running_mode=mp_vision.RunningMode.VIDEO,
                num_hands=2,
                min_hand_detection_confidence=0.4,   # lower = fewer skipped frames
                min_tracking_confidence=0.4,          # lower = faster tracking recovery
            )
            self.tracker = mp_vision.GestureRecognizer.create_from_options(options)
        except Exception as e:
            print(f"[GESTURE] Could not start the hand tracker: {e}")

    # ── Geometry helpers ─────────────────────────────────────────────────────

    def _distance(self, p1, p2):
        dx = (p1.x - p2.x) * self.frame_aspect
        dy = p1.y - p2.y
        return math.sqrt(dx * dx + dy * dy)

    def _palm_size(self, lm):
        return self._distance(lm[0], lm[9])

    @staticmethod
    def is_backhand(lm, handedness='Right', flip=False):
        """Reject backhand (knuckle-facing) views.

        MediaPipe handedness labels can be unreliable when the camera image is
        not mirrored (flip=False), so we compute nz for BOTH hand orientations
        and only reject if BOTH indicate a backhand.  This prevents false
        rejection of left-hand palm views.
        """
        if not lm or len(lm) < 18:
            return False
        ux = lm[9].x - lm[0].x
        uy = lm[9].y - lm[0].y

        # Cross-product assuming "Right" labelling (pinky-index vector)
        vx_r = lm[17].x - lm[5].x
        vy_r = lm[17].y - lm[5].y
        nz_r = ux * vy_r - uy * vx_r

        # Cross-product assuming "Left" labelling (index-pinky vector)
        vx_l = lm[5].x - lm[17].x
        vy_l = lm[5].y - lm[17].y
        nz_l = ux * vy_l - uy * vx_l

        if flip:
            nz_r = -nz_r
            nz_l = -nz_l

        # Use the signed value that matches the reported handedness for primary check
        is_right = (handedness == 'Right')
        nz_primary   = nz_r if is_right else nz_l
        nz_secondary = nz_l if is_right else nz_r

        # Only reject if BOTH orientations indicate backhand (very conservative)
        BACKHAND_THRESHOLD = -0.015
        return nz_primary < BACKHAND_THRESHOLD and nz_secondary < BACKHAND_THRESHOLD

    def select_best_hand(self, hand_landmarks_list, handedness_list=None):
        if not hand_landmarks_list:
            return None, None

        candidates = []
        for idx, lm in enumerate(hand_landmarks_list):
            h_name = 'Right'
            h_score = 1.0
            if handedness_list and idx < len(handedness_list) and handedness_list[idx]:
                cat = handedness_list[idx][0]
                h_name = getattr(cat, 'category_name', 'Right')
                h_score = getattr(cat, 'score', 1.0)

            if self.is_backhand(lm, h_name, flip=getattr(self, 'flip', False)):
                continue

            cx, cy = self._palm_center(lm)
            if cy > 0.88:
                continue

            size = self._palm_size(lm)
            if size < MIN_PALM_SIZE:
                continue

            composite_score = size * (h_score ** 0.5)

            if self.present:
                dist = math.hypot((cx - self.hand_x) * self.frame_aspect, cy - self.hand_y)
                if dist < 0.28:
                    composite_score *= 1.4

            candidates.append((composite_score, lm, h_name))

        if not candidates:
            return None, None

        candidates.sort(key=lambda c: c[0], reverse=True)
        return candidates[0][1], candidates[0][2]

    def is_pinching(self, lm):
        palm = self._palm_size(lm)
        if palm < MIN_PALM_SIZE:
            return False
        ratio = self._distance(lm[4], lm[8]) / palm
        threshold = PINCH_EXIT_RATIO if self.pinch_start is not None else PINCH_ENTER_RATIO
        return ratio < threshold

    @staticmethod
    def _palm_center(lm):
        pts = [lm[0], lm[5], lm[9], lm[13], lm[17]]
        return (sum(p.x for p in pts) / len(pts),
                sum(p.y for p in pts) / len(pts))

    # ── Per-frame analysis ───────────────────────────────────────────────────

    def process_landmarks(self, lm, now):
        self.scroll_delta = 0
        x, y = self._palm_center(lm)
        if self.present:
            # Faster tracking: 0.80/0.20 blend responds more quickly than 0.95/0.05
            self.hand_x = 0.80 * x + 0.20 * self.hand_x
            self.hand_y = 0.80 * y + 0.20 * self.hand_y
        else:
            self.hand_x, self.hand_y = x, y
        self.present = True
        self.last_seen = now

        new_region = classify_region(x)
        self.region = new_region

        pinched = self.is_pinching(lm)
        self.pinched = pinched
        event = None

        # ── Edge Dwell Progress ─────
        in_top_right = (x >= TOP_RIGHT_X and y <= TOP_RIGHT_Y)

        if in_top_right:
            self.dwell_side = 'top_right'
            if self.right_since is None:
                self.right_since = now
                self.right_dwell_progress = 0.0
            else:
                elapsed = now - self.right_since
                self.right_dwell_progress = min(1.0, elapsed / RIGHT_DWELL_SEC)
                if self.right_armed and elapsed >= RIGHT_DWELL_SEC:
                    self.right_armed = False
                    self._last_dwell_trigger = now
                    event = "enter_right"
                elif not self.right_armed and (now - getattr(self, '_last_dwell_trigger', 0)) > 1.8:
                    self.right_armed = True
                    self.right_since = now
        else:
            self.right_since = None
            self.right_armed = True
            self.right_dwell_progress = 0.0
            self.dwell_side = None

        # ── Pinch-and-drag scrolling & click/tap ─────────────────────────────
        if pinched:
            if self.pinch_start is None:
                self.pinch_start = now
                self.drag_start_y = y
                self.last_drag_y = y
                self.drag_dist = 0.0
                self.drag_velocity = 0.0
                self.had_scroll = False
                self.last_frame_time = now
            else:
                dy = y - self.last_drag_y
                dt = max(0.001, now - self.last_frame_time)
                self.last_frame_time = now

                instant_v = dy / dt
                self.drag_velocity = 0.7 * self.drag_velocity + 0.3 * instant_v
                self.drag_dist += abs(dy)
                self.last_drag_y = y

                if self.drag_dist > DRAG_TAP_THRESHOLD and abs(dy) > DRAG_DEADZONE:
                    delta = int(-dy * DRAG_SCROLL_GAIN)
                    if delta != 0:
                        self.had_scroll = True
                        self.scroll_delta = max(-200, min(200, delta))
                        if event is None:
                            event = "scroll"
        else:
            if self.pinch_start is not None:
                held = now - self.pinch_start
                # Consider it a drag if: meaningful distance moved, had_scroll was set,
                # OR the pinch was held long enough that it can't be a quick tap.
                # The held-time guard catches slow-release scrolls where drag_velocity
                # has decayed to near zero and had_scroll may not have been stamped.
                released_velocity = self.drag_velocity   # capture before reset
                was_drag = (
                    (self.drag_dist > DRAG_TAP_THRESHOLD)
                    or getattr(self, 'had_scroll', False)
                    or (held > TAP_MAX_SEC * 0.55)                   # held >~360ms = not a tap
                    or (abs(released_velocity) > TAP_VELOCITY_MAX)   # hand was moving = not a tap
                )

                self.pinch_start = None
                self.drag_start_y = None
                self.last_drag_y = None
                self.drag_dist = 0.0
                self.drag_velocity = 0.0
                self.had_scroll = False

                if not was_drag and held <= TAP_MAX_SEC:
                    cooled = (self.last_tap_time is None
                              or now - self.last_tap_time > TAP_COOLDOWN_SEC)
                    if cooled:
                        self.last_tap_time = now
                        if event is None:
                            event = "tap"
                elif was_drag and abs(released_velocity) > 0.15:
                    if event is None:
                        fling_delta = int(-released_velocity * FLING_VELOCITY_SCALE)
                        self.scroll_delta = max(-500, min(500, fling_delta))
                        event = "fling"

            pass
        return event

    def mark_absent(self, now):
        if not self.present:
            return False
        if now - self.last_seen < HAND_LOST_SEC:
            return False
        self.present = False
        self.region = None
        self.pinched = False
        self.pinch_start = None
        self.drag_start_y = None
        self.last_drag_y = None
        self.drag_dist = 0.0
        self.drag_velocity = 0.0
        self.last_open_y = None
        self.last_open_x = None
        self.open_swipe_velocity = 0.0
        self.open_wave_velocity = 0.0
        self.right_since = None
        self.right_armed = True
        self.right_dwell_progress = 0.0
        return True

    # ── Publishing ───────────────────────────────────────────────────────────

    def _quantised_position(self):
        if not self.present:
            return None
        return (int(self.hand_x / POSITION_QUANTUM),
                int(self.hand_y / POSITION_QUANTUM))

    def write_status(self, event=None, scroll_delta=0, force=False):
        now = time.time()
        if event:
            self._last_event_hold = event
            self._last_event_time = now
            self._last_event_delta = scroll_delta
            self._event_id = getattr(self, '_event_id', 0) + 1
        elif getattr(self, '_last_event_hold', None) and (now - getattr(self, '_last_event_time', 0) < 0.10):
            event = self._last_event_hold
            scroll_delta = getattr(self, '_last_event_delta', 0)
        else:
            self._last_event_hold = None

        payload = (self.present, self.region, event, self._quantised_position(), self.pinched, round(self.right_dwell_progress, 2))
        if (not force and event is None
                and payload == self.last_payload
                and now - self.last_write < HEARTBEAT_SEC):
            # Stream live coordinates over UDP for 60fps responsiveness without disk churn
            if self.present:
                try:
                    if not hasattr(self, '_udp_sock') or self._udp_sock is None:
                        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    live_data = {
                        "present":              self.present,
                        "region":               self.region,
                        "hand_x":               round(self.hand_x, 4),
                        "hand_y":               round(self.hand_y, 4),
                        "pinched":              self.pinched,
                        "right_dwell_progress": round(self.right_dwell_progress, 3),
                        "dwell_side":           getattr(self, 'dwell_side', None),
                        "event":                None,
                        "event_id":             getattr(self, '_event_id', 0),
                        "scroll_delta":         0,
                        "seq":                  self.seq,
                        "timestamp":            now,
                    }
                    self._udp_sock.sendto(json.dumps(live_data).encode('utf-8'), ("127.0.0.1", GESTURE_UDP_PORT))
                except Exception:
                    pass
            return

        self.seq += 1
        self.last_payload = payload
        self.last_write = now

        data = {
            "present":              self.present,
            "region":               self.region,
            "hand_x":               round(self.hand_x, 4),
            "hand_y":               round(self.hand_y, 4),
            "pinched":              self.pinched,
            "right_dwell_progress": round(self.right_dwell_progress, 3),
            "dwell_side":           getattr(self, 'dwell_side', None),
            "event":                event,
            "event_id":             getattr(self, '_event_id', 0),
            "scroll_delta":         scroll_delta,
            "seq":                  self.seq,
            "timestamp":            now,
        }

        # Send instant UDP notification to localhost (sub-millisecond latency, zero disk I/O)
        try:
            if not hasattr(self, '_udp_sock') or self._udp_sock is None:
                self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            payload_bytes = json.dumps(data).encode('utf-8')
            self._udp_sock.sendto(payload_bytes, ("127.0.0.1", GESTURE_UDP_PORT))
        except Exception:
            pass

        try:
            with open(self._tmp_file, "w") as f:
                json.dump(data, f)
            for attempt in range(3):
                try:
                    os.replace(self._tmp_file, GESTURE_STATUS_FILE)
                    break
                except PermissionError:
                    if attempt == 2:
                        try:
                            with open(GESTURE_STATUS_FILE, "w") as df:
                                json.dump(data, df)
                        except Exception:
                            pass
                    time.sleep(0.002)
        except Exception as e:
            pass

    # ── Main loop ────────────────────────────────────────────────────────────

    def watch_parent(self):
        def wait_for_eof():
            try:
                sys.stdin.read()
            except Exception:
                pass
            print("[GESTURE] Parent closed the pipe — exiting.")
            self.running = False

        threading.Thread(target=wait_for_eof, daemon=True).start()

    def run(self, exit_with_parent=False):
        self.running = True

        if exit_with_parent:
            self.watch_parent()

        if self.tracker is None:
            print("[GESTURE] No hand tracker — exiting.")
            return

        # Camera initialization with index parsing and retries for v4l2loopback
        max_attempts = 10 if (isinstance(self.camera_id, str) and "/dev/video" in self.camera_id) else 3
        cap = None
        for attempt in range(1, max_attempts + 1):
            cap = _try_open_capture(self.camera_id)
            if cap is not None and cap.isOpened():
                # On Windows desktop webcams, request MJPG for performance.
                # On Linux loopback (/dev/video*), DO NOT force MJPG because v4l2loopback
                # provides raw uncompressed frames (YUYV) from ffmpeg.
                is_linux_loopback = isinstance(self.camera_id, str) and "/dev/video" in self.camera_id
                if sys.platform == 'win32':
                    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
                elif not is_linux_loopback:
                    try:
                        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
                    except Exception:
                        pass
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if not is_linux_loopback:      # the loopback has a fixed size
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  480)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
                    cap.set(cv2.CAP_PROP_FPS, 30)

                ret, frame = cap.read()
                if ret and frame is not None:
                    break
                cap.release()
                cap = None

            if attempt < max_attempts:
                time.sleep(1.0)

        if cap is None or not cap.isOpened():
            print(f"[GESTURE] Could not open camera {self.camera_id!r}. Exiting.")
            if cap is not None:
                cap.release()
            return

        print(f"[GESTURE] Running on camera {self.camera_id}. "
              f"Regions: left<{REGION_LEFT_EDGE} right>{REGION_RIGHT_EDGE}.")
        print(f"[GESTURE] Horizontal flip: {'on' if self.flip else 'off'}.")

        start = time.time()
        last_stamp_ms = -1
        try:
            while self.running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.03)
                    continue

                if self.flip:
                    frame = cv2.flip(frame, 1)
                h, w = frame.shape[:2]
                self.frame_aspect = (w / h) if h else 1.0
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

                stamp_ms = max(int((time.time() - start) * 1000), last_stamp_ms + 1)
                last_stamp_ms = stamp_ms
                results = self.tracker.recognize_for_video(image, stamp_ms)

                now = time.time()
                self.scroll_delta = 0
                event = None

                if results.hand_landmarks:
                    best_lm, _ = self.select_best_hand(
                        results.hand_landmarks, getattr(results, 'handedness', None)
                    )
                    if best_lm is not None:
                        event = self.process_landmarks(best_lm, now)
                        self.write_status(event, self.scroll_delta)
                    else:
                        became_absent = self.mark_absent(now)
                        self.write_status(force=became_absent)
                else:
                    became_absent = self.mark_absent(now)
                    self.write_status(force=became_absent)

                if event:
                    print(f"[GESTURE] {event} region={self.region} delta={self.scroll_delta}")
        except KeyboardInterrupt:
            pass
        finally:
            cap.release()
            if hasattr(self, '_udp_sock') and self._udp_sock is not None:
                try:
                    self._udp_sock.close()
                except Exception:
                    pass
            if hasattr(self.tracker, 'close'):
                self.tracker.close()

    def __del__(self):
        if hasattr(self, '_udp_sock') and self._udp_sock is not None:
            try:
                self._udp_sock.close()
            except Exception:
                pass


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Smart Mirror — Region-based Hand Gesture Daemon")
    parser.add_argument('--rpi', action='store_true',
                        help=f"Raspberry Pi mode: read from loopback ({RPI_CAMERA})")
    parser.add_argument('--camera-id', default=0, type=int,
                        help="Desktop webcam index (default 0)")
    parser.add_argument('--exit-with-parent', action='store_true',
                        help="Exit when stdin closes.")
    flip = parser.add_mutually_exclusive_group()
    flip.add_argument('--flip', dest='flip', action='store_true', default=None,
                      help="Mirror the frame horizontally (default on).")
    flip.add_argument('--no-flip', dest='flip', action='store_false',
                      help="Do not mirror.")
    args = parser.parse_args(argv)
    if args.rpi:
        camera = RPI_CAMERA
    else:
        camera = args.camera_id
    flip_frame = default_flip() if args.flip is None else args.flip
    return camera, args.exit_with_parent, flip_frame


if __name__ == "__main__":
    camera, exit_with_parent, flip_frame = parse_args()
    GestureEngine(camera, flip=flip_frame).run(exit_with_parent=exit_with_parent)
