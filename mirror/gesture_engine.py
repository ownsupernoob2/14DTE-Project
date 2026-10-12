# mirror/gesture_engine.py
"""
Region-based hand gesture engine for the smart mirror.

The mirror has no touchscreen and no cursor, so this does not emulate a mouse.
Instead the screen is split into the same columns the UI uses, and whichever
region your hand is generally in is the region you are interacting with:

    left   (x < 0.50)  → the notices column, drawn on the left of the screen
    center               nothing (a neutral resting area)
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
import sys
import threading
import time

import cv2

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
# working directory, because the mirror spawns this daemon and the shell it was
# launched from could be anywhere. setup_venv.bat / setup.sh download it.
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "gesture_recognizer.task")

# The Pi reads the v4l2loopback device that start_smart_mirror.sh feeds, so the
# face daemon and this one can share the single camera module.
RPI_CAMERA = "/dev/video10"


def default_flip():
    """Whether to mirror the frame, unless told otherwise.

    For a smart mirror looking back at the student, mirroring is essential:
    the user's left hand arrives on the camera's right side, so horizontal mirroring
    puts it under the left panel where the user is physically pointing.
    Default is True on all platforms unless explicitly disabled via GESTURE_FLIP=0.
    """
    env = os.environ.get("GESTURE_FLIP")
    if env is not None:
        return env not in ("0", "false", "False", "no", "off", "")
    return True

# ── Region boundaries ────────────────────────────────────────────────────────
# Left half (x < 0.50) is the notices column; right side (x > 0.62) is the peek.
REGION_LEFT_EDGE  = 0.50
REGION_RIGHT_EDGE = 0.62

REGION_LEFT   = "left"
REGION_CENTER = "center"
REGION_RIGHT  = "right"

# ── Tuning ───────────────────────────────────────────────────────────────────
PINCH_ENTER_RATIO  = 0.55   # thumb-index gap / palm size to start a pinch
PINCH_EXIT_RATIO   = 0.75   # and to release it again
MIN_PALM_SIZE      = 0.02   # below this the hand is too far away to trust

TAP_MAX_SEC        = 0.65   # pinch held up to 0.65s without drag is a tap
TAP_COOLDOWN_SEC   = 0.35   # ignore repeat taps inside this window
DRAG_TAP_THRESHOLD = 0.025  # movement threshold during pinch to distinguish tap vs drag
DRAG_SCROLL_GAIN   = 1100.0 # movement -> scroll pixels
DRAG_DEADZONE      = 0.003  # ignore minute jitter below this
FLING_VELOCITY_SCALE = 600.0 # release velocity multiplier for inertia fling

TOP_RIGHT_X        = 0.62   # top-right quadrant dwell threshold (hand must be clearly in right half)
TOP_RIGHT_Y        = 0.18   # top-right height limit (palm must be raised high up near top edge <= 0.18)
RIGHT_FAR_EDGE     = 0.62   # right region dwell threshold (top-right only)
RIGHT_DWELL_SEC    = 1.6    # hold hand in top-right region for 1.6s to toggle timetable / kings week
HEARTBEAT_SEC      = 0.5    # republish presence at least this often
HAND_LOST_SEC      = 0.4    # no landmarks for this long → hand is gone

POSITION_QUANTUM   = 1.0 / 24


def classify_region(x):
    if x < REGION_LEFT_EDGE:
        return REGION_LEFT
    if x > REGION_RIGHT_EDGE:
        return REGION_RIGHT
    return REGION_CENTER


class GestureEngine:
    def __init__(self, camera_id=0, flip=True):
        self.camera_id = camera_id
        self.flip = flip
        self.running = False
        self.tracker = None
        self._init_tracker()

        # Landmark x is a fraction of the frame width and y of its height, so
        # measuring a diagonal needs the aspect ratio. Set from the first real
        # frame; 1.0 until then, which is also what synthetic test hands assume.
        self.frame_aspect = 1.0

        # ── Tracking state ───────────────────────────────────────────────────
        self.present = False
        self.region = None
        self.hand_x = 0.0
        self.hand_y = 0.0
        self.last_seen = 0.0

        self.pinched = False
        self.pinch_start = None       # when the current pinch began
        self.drag_start_y = None
        self.last_drag_y = None
        self.drag_dist = 0.0
        self.drag_velocity = 0.0
        self.last_frame_time = 0.0
        self.scroll_delta = 0

        self.last_tap_time = None     # None = no tap yet, so no cooldown to serve

        self.right_since = None       # when the palm entered the far-right region
        self.right_armed = True       # re-arms once the hand leaves the far-right
        self.right_dwell_progress = 0.0

        self.seq = 0
        self.last_write = 0.0
        self.last_payload = None

        self._tmp_file = f"{GESTURE_STATUS_FILE}.{os.getpid()}.{id(self):x}.tmp"

    def _init_tracker(self):
        """Build the MediaPipe hand tracker. Overridden in tests."""
        if mp is None:
            print("[GESTURE] mediapipe not installed — gesture control disabled.")
            return
        if not os.path.exists(MODEL_PATH):
            print(f"[GESTURE] Missing {os.path.basename(MODEL_PATH)} — run "
                  f"setup_venv.bat (Windows) or setup.sh (Pi) to download it. "
                  f"Gesture control disabled.")
            return
        try:
            options = mp_vision.GestureRecognizerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
                running_mode=mp_vision.RunningMode.VIDEO,
                num_hands=2,
                min_hand_detection_confidence=0.5,
                min_tracking_confidence=0.5,
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
        """True if the back of the hand faces the camera, rather than the palm.

        Calculates the z-component of the palm normal using wrist (0),
        middle knuckle (9), index knuckle (5), and pinky knuckle (17).
        When the palmar surface faces the camera, the cross product is positive;
        when the dorsal/backhand surface faces the camera, it is negative.
        When the camera frame is horizontally flipped (mirror mode), the
        x-coordinates are reflected, so the parity is corrected.
        """
        if not lm or len(lm) < 18:
            return False
        # Vector u: wrist (0) -> middle MCP (9)
        ux = lm[9].x - lm[0].x
        uy = lm[9].y - lm[0].y

        # Vector v across knuckles
        is_right = (handedness == 'Right')
        if is_right:
            # Index (5) -> Pinky (17)
            vx = lm[17].x - lm[5].x
            vy = lm[17].y - lm[5].y
        else:
            # Pinky (17) -> Index (5)
            vx = lm[5].x - lm[17].x
            vy = lm[5].y - lm[17].y

        # 2D cross product: ux * vy - uy * vx
        # Positive = palm facing camera; Negative = back of hand facing camera
        nz = ux * vy - uy * vx
        if flip:
            nz = -nz
        return nz < -0.01

    def select_best_hand(self, hand_landmarks_list, handedness_list=None):
        """Pick the clearest and closest hand facing the camera, ignoring backhands.

        Applies temporal continuity to prevent rapid flip-flopping between hands,
        and rejects resting hands near the bottom frame border.
        Returns (landmarks, handedness_name) or (None, None).
        """
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

            # Ignore backhands
            if self.is_backhand(lm, h_name, flip=getattr(self, 'flip', False)):
                continue

            # Ignore hands at the very bottom edge (e.g. resting on desk or lap)
            cx, cy = self._palm_center(lm)
            if cy > 0.88:
                continue

            # Palm size reflects closeness to camera (larger = closer)
            size = self._palm_size(lm)
            if size < MIN_PALM_SIZE:
                continue

            # Composite metric: closest (size) and clearest (detection confidence)
            composite_score = size * (h_score ** 0.5)

            # Continuity bonus: if already tracking a hand, prefer candidate near current position
            if self.present:
                dist = math.hypot((cx - self.hand_x) * self.frame_aspect, cy - self.hand_y)
                if dist < 0.28:
                    composite_score *= 1.4

            candidates.append((composite_score, lm, h_name))

        if not candidates:
            return None, None

        # Sort descending by composite score: highest closeness & clarity wins
        candidates.sort(key=lambda c: c[0], reverse=True)
        return candidates[0][1], candidates[0][2]

    def is_pinching(self, lm):
        """True while the thumb and index finger are touching — the 'click'."""
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

    @staticmethod
    def _extended_fingers(lm):
        pairs = ((8, 5), (12, 9), (16, 13), (20, 17))
        return sum(1 for tip, mcp in pairs if lm[tip].y < lm[mcp].y)

    # ── Per-frame analysis ───────────────────────────────────────────────────

    def process_landmarks(self, lm, now):
        """Update state from one hand and return an event name, or None."""
        self.scroll_delta = 0
        x, y = self._palm_center(lm)
        if self.present:
            self.hand_x = 0.70 * x + 0.30 * self.hand_x
            self.hand_y = 0.70 * y + 0.30 * self.hand_y
        else:
            self.hand_x, self.hand_y = x, y
        self.present = True
        self.last_seen = now

        new_region = classify_region(x)
        self.region = new_region

        pinched = self.is_pinching(lm)
        self.pinched = pinched
        event = None

        # ── Edge Dwell Progress (Top-Right Arm / Palm Quadrant ONLY) ─────
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
                    # Allow continuous re-arming if user keeps hand in zone
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
                # Start dragging / pinch
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

                # Only engage scrolling if movement has exceeded the intentional drag threshold
                if self.drag_dist > DRAG_TAP_THRESHOLD and abs(dy) > DRAG_DEADZONE:
                    delta = int(-dy * DRAG_SCROLL_GAIN)
                    if delta != 0:
                        self.had_scroll = True
                        self.scroll_delta = max(-80, min(80, delta))
                        if event is None:
                            event = "scroll"
        else:
            if self.pinch_start is not None:
                held = now - self.pinch_start
                was_drag = (self.drag_dist > DRAG_TAP_THRESHOLD) or getattr(self, 'had_scroll', False)
                released_velocity = self.drag_velocity

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
                        self.scroll_delta = max(-350, min(350, fling_delta))
                        event = "fling"

        return event

    def mark_absent(self, now):
        """Clear per-hand state once the hand has been gone long enough."""
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
        self.right_since = None
        self.right_armed = True
        self.right_dwell_progress = 0.0
        return True

    # ── Publishing ───────────────────────────────────────────────────────────

    def _quantised_position(self):
        """The palm position rounded to a grid cell, or None with no hand."""
        if not self.present:
            return None
        return (int(self.hand_x / POSITION_QUANTUM),
                int(self.hand_y / POSITION_QUANTUM))

    def write_status(self, event=None, scroll_delta=0, force=False):
        """Publish state, skipping writes that would tell the mirror nothing new."""
        now = time.time()
        payload = (self.present, self.region, event, self._quantised_position(), self.pinched, round(self.right_dwell_progress, 2))
        if (not force and event is None
                and payload == self.last_payload
                and now - self.last_write < HEARTBEAT_SEC):
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
            "scroll_delta":         scroll_delta,
            "seq":                  self.seq,
            "timestamp":            now,
        }
        try:
            with open(self._tmp_file, "w") as f:
                json.dump(data, f)
            # The mirror briefly holds a read handle on the target, and on
            # Windows os.replace() onto an open file raises PermissionError, so
            # a frame is occasionally dropped rather than published. Retry
            # briefly; the next frame is only 30ms away, so never block long.
            for attempt in range(3):
                try:
                    os.replace(self._tmp_file, GESTURE_STATUS_FILE)
                    break
                except PermissionError:
                    if attempt == 2:
                        raise
                    time.sleep(0.005)
        except Exception as e:
            print(f"[GESTURE] Error writing status: {e}")

    # ── Main loop ────────────────────────────────────────────────────────────

    def watch_parent(self):
        """Stop the loop when the parent closes our stdin.

        The mirror hands us a pipe and dies with it. A pipe is better than
        anything pid-based here: the OS closes the write end however the mirror
        goes away — clean exit, Ctrl-C, taskkill, closed terminal — so we always
        find out, and there is no pid to reuse and mistakenly kill. Without this,
        every non-graceful mirror exit left a daemon running; they piled up and
        fought over the status file.
        """
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

        cap = cv2.VideoCapture(self.camera_id)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        if not cap.isOpened():
            print(f"[GESTURE] Could not open camera {self.camera_id!r}. "
                  f"Another process may already have it — exiting.")
            cap.release()
            return

        print(f"[GESTURE] Running on camera {self.camera_id}. "
              f"Regions: left<{REGION_LEFT_EDGE} right>{REGION_RIGHT_EDGE}.")
        # Spelt out because it is the one setting nothing can work out for itself,
        # and the symptom — the panel on your left answering to your other hand —
        # looks like a bug in the gesture code rather than a camera placement.
        print(f"[GESTURE] Horizontal flip: {'on' if self.flip else 'off'}. "
              f"The notices panel is drawn on the left of the screen; if it only "
              f"answers to your other hand, set GESTURE_FLIP="
              f"{'0' if self.flip else '1'} and restart.")
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

                # VIDEO mode rejects a timestamp that does not advance, and two
                # frames can easily land inside the same millisecond.
                stamp_ms = max(int((time.time() - start) * 1000),
                               last_stamp_ms + 1)
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
                    print(f"[GESTURE] {event} region={self.region} "
                          f"delta={self.scroll_delta}")
        except KeyboardInterrupt:
            pass
        finally:
            cap.release()
            self.tracker.close()


def parse_args(argv=None):
    """Camera selection, matching face_recognize.py's flags."""
    parser = argparse.ArgumentParser(
        description="Smart Mirror — Region-based Hand Gesture Daemon")
    parser.add_argument('--rpi', action='store_true',
                        help=f"Raspberry Pi mode: read from {RPI_CAMERA}")
    parser.add_argument('--camera-id', default=0, type=int,
                        help="Desktop webcam index (default 0)")
    parser.add_argument('--exit-with-parent', action='store_true',
                        help="Exit when stdin closes. The mirror passes this so "
                             "the daemon cannot outlive it; leave it off when "
                             "running by hand from a terminal.")
    flip = parser.add_mutually_exclusive_group()
    flip.add_argument('--flip', dest='flip', action='store_true', default=None,
                      help="Mirror the frame horizontally: for a camera mounted "
                           "in the mirror facing the student, so the panel on "
                           "your left answers to the hand on your left.")
    flip.add_argument('--no-flip', dest='flip', action='store_false',
                      help="Do not mirror. Use when the camera is not facing the "
                           "student from behind the screen — a phone on a stand, "
                           "say — and the sides come out crossed.")
    args = parser.parse_args(argv)
    camera = RPI_CAMERA if args.rpi else args.camera_id
    flip_frame = default_flip() if args.flip is None else args.flip
    return camera, args.exit_with_parent, flip_frame


if __name__ == "__main__":
    camera, exit_with_parent, flip_frame = parse_args()
    GestureEngine(camera, flip=flip_frame).run(exit_with_parent=exit_with_parent)
