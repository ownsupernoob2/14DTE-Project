# mirror/gesture_engine.py
"""
Region-based hand gesture engine for the smart mirror.

The mirror has no touchscreen and no cursor, so this does not emulate a mouse.
Instead the screen is split into the same columns the UI uses, and whichever
region your hand is generally in is the region you are interacting with:

    left   (x < 0.34)  → the notices column
    center               nothing (a neutral resting area)
    right  (x > 0.62)  → the timetable peek

Within a region an open palm engages control: moving it up and down scrolls,
and a quick pinch is a tap. Dwelling in the right region peeks the timetable,
which then slides away to reveal the King's Week grid underneath it.

State is published to a JSON file that smart_mirror_pro.py polls, so the
vision work stays out of the Qt event loop.
"""

import argparse
import json
import math
import os
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

# ── Region boundaries ────────────────────────────────────────────────────────
# Left half (x < 0.50) is the notices column; right side (x > 0.62) is the peek.
REGION_LEFT_EDGE  = 0.50
REGION_RIGHT_EDGE = 0.62

REGION_LEFT   = "left"
REGION_CENTER = "center"
REGION_RIGHT  = "right"

# ── Tuning ───────────────────────────────────────────────────────────────────
PINCH_DIST         = 0.06   # normalised thumb-tip → index-tip distance
TAP_MAX_SEC        = 0.5    # pinch held longer than this is a hold, not a tap
TAP_COOLDOWN_SEC   = 0.6    # ignore repeat taps inside this window
SCROLL_DEADZONE    = 0.012  # ignore palm jitter below this normalised movement
SCROLL_GAIN        = 900.0  # normalised palm movement → scroll pixels
SCROLL_MAX_PX      = 90     # clamp one frame's scroll so a fast wave can't jump
RIGHT_DWELL_SEC    = 0.45   # palm must settle in the right region before peeking
HEARTBEAT_SEC      = 0.5    # republish presence at least this often
HAND_LOST_SEC      = 0.4    # no landmarks for this long → hand is gone

# The King's Week grid picks a box from the published palm position, so a move
# has to be published even when nothing else about the state changed. Rounding
# to a coarse cell keeps that from becoming a write on every single frame — and
# it is the same coarseness that makes the grid snap cleanly from box to box
# instead of hovering between two of them.
POSITION_QUANTUM   = 1.0 / 24


def classify_region(x):
    if x < REGION_LEFT_EDGE:
        return REGION_LEFT
    if x > REGION_RIGHT_EDGE:
        return REGION_RIGHT
    return REGION_CENTER


class GestureEngine:
    def __init__(self, camera_id=0):
        self.camera_id = camera_id
        self.running = False
        self.tracker = None
        self._init_tracker()

        # ── Tracking state ───────────────────────────────────────────────────
        self.present = False
        self.region = None
        self.hand_x = 0.0
        self.hand_y = 0.0
        self.last_seen = 0.0

        self.engaged = False          # open palm → scroll control active
        self.scroll_anchor_y = None
        self.scroll_delta = 0

        self.pinch_start = None       # when the current pinch began
        self.last_tap_time = None     # None = no tap yet, so no cooldown to serve

        self.right_since = None       # when the palm entered the right region
        self.right_armed = True       # re-arms once the hand leaves the right

        self.seq = 0
        self.last_write = 0.0
        self.last_payload = None

    def _init_tracker(self):
        """Build the MediaPipe hand tracker. Overridden in tests.

        This uses the Tasks API rather than the old `mp.solutions.hands`, which
        no longer exists: mediapipe 1.x dropped the Solutions package entirely,
        so `mp.solutions` raises AttributeError and took the whole daemon down
        with it. Tasks has been available since 0.10, so there is one code path.
        """
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
                num_hands=1,
                min_hand_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self.tracker = mp_vision.GestureRecognizer.create_from_options(options)
        except Exception as e:
            print(f"[GESTURE] Could not start the hand tracker: {e}")

    # ── Geometry helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _distance(p1, p2):
        return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2 + (p1.z - p2.z) ** 2)

    @staticmethod
    def _palm_center(lm):
        """Average the wrist and the four finger MCPs.

        Steadier than any single landmark: finger tips swing wildly while the
        palm stays put, and region classification needs to not flicker.
        """
        pts = [lm[0], lm[5], lm[9], lm[13], lm[17]]
        return (sum(p.x for p in pts) / len(pts),
                sum(p.y for p in pts) / len(pts))

    @staticmethod
    def _extended_fingers(lm):
        """Count index/middle/ring/pinky tips sitting above their knuckles."""
        pairs = ((8, 5), (12, 9), (16, 13), (20, 17))
        return sum(1 for tip, mcp in pairs if lm[tip].y < lm[mcp].y)

    # ── Per-frame analysis ───────────────────────────────────────────────────

    def process_landmarks(self, lm, now):
        """Update state from one hand and return an event name, or None."""
        self.scroll_delta = 0
        x, y = self._palm_center(lm)
        self.hand_x, self.hand_y = x, y
        self.present = True
        self.last_seen = now

        new_region = classify_region(x)
        region_changed = (new_region != self.region)
        self.region = new_region

        # Leaving the right region re-arms the timetable peek.
        if new_region != REGION_RIGHT:
            self.right_since = None
            self.right_armed = True

        pinched = self._distance(lm[4], lm[8]) < PINCH_DIST
        fingers = self._extended_fingers(lm)
        open_palm = fingers >= 3 and not pinched

        event = None

        # ── Tap: a short pinch, released ─────────────────────────────────────
        if pinched:
            if self.pinch_start is None:
                self.pinch_start = now
        else:
            if self.pinch_start is not None:
                held = now - self.pinch_start
                self.pinch_start = None
                cooled = (self.last_tap_time is None
                          or now - self.last_tap_time > TAP_COOLDOWN_SEC)
                if held <= TAP_MAX_SEC and cooled:
                    self.last_tap_time = now
                    event = "tap"

        # ── Scroll: track the palm while an open hand is engaged ──────────────
        if open_palm:
            if not self.engaged or region_changed:
                # Re-anchor on engage and on region change so crossing columns
                # never emits one huge jump.
                self.engaged = True
                self.scroll_anchor_y = y
            elif event is None:
                dy = y - self.scroll_anchor_y
                if abs(dy) > SCROLL_DEADZONE:
                    # Hand down (y increases) scrolls content down.
                    delta = int(max(-SCROLL_MAX_PX,
                                    min(SCROLL_MAX_PX, dy * SCROLL_GAIN)))
                    if delta != 0:
                        self.scroll_anchor_y = y
                        self.scroll_delta = delta
                        return "scroll"
        else:
            self.engaged = False
            self.scroll_anchor_y = None

        # ── Timetable peek: settle in the right region ────────────────────────
        if new_region == REGION_RIGHT and event is None:
            if self.right_since is None:
                self.right_since = now
            elif self.right_armed and now - self.right_since >= RIGHT_DWELL_SEC:
                self.right_armed = False
                event = "enter_right"

        return event

    def mark_absent(self, now):
        """Clear per-hand state once the hand has been gone long enough."""
        if not self.present:
            return False
        if now - self.last_seen < HAND_LOST_SEC:
            return False
        self.present = False
        self.region = None
        self.engaged = False
        self.scroll_anchor_y = None
        self.pinch_start = None
        self.right_since = None
        self.right_armed = True
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
        payload = (self.present, self.region, event, self._quantised_position())
        if (not force and event is None
                and payload == self.last_payload
                and now - self.last_write < HEARTBEAT_SEC):
            return

        self.seq += 1
        self.last_payload = payload
        self.last_write = now

        data = {
            "present":      self.present,
            "region":       self.region,
            "hand_x":       round(self.hand_x, 4),
            "hand_y":       round(self.hand_y, 4),
            "event":        event,
            "scroll_delta": scroll_delta,
            "seq":          self.seq,
            "timestamp":    now,
        }
        try:
            tmp = GESTURE_STATUS_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, GESTURE_STATUS_FILE)
        except Exception as e:
            print(f"[GESTURE] Error writing status: {e}")

    # ── Main loop ────────────────────────────────────────────────────────────

    def run(self):
        self.running = True

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
              f"Regions: left<{REGION_LEFT_EDGE} right>{REGION_RIGHT_EDGE}")
        start = time.time()
        last_stamp_ms = -1
        try:
            while self.running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.03)
                    continue

                # Flip so landmark x matches what the student sees on the mirror.
                frame = cv2.flip(frame, 1)
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
                    event = self.process_landmarks(results.hand_landmarks[0], now)
                    self.write_status(event, self.scroll_delta)
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
    args = parser.parse_args(argv)
    return RPI_CAMERA if args.rpi else args.camera_id


if __name__ == "__main__":
    GestureEngine(parse_args()).run()
