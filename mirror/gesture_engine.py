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
# working directory. The plain hand landmarker is preferred: the gesture
# recognizer runs the same hand model plus a gesture classifier on every frame
# with a hand in it, and nothing here uses that classifier.
_HERE = os.path.dirname(os.path.abspath(__file__))
LANDMARKER_PATH = os.path.join(_HERE, "hand_landmarker.task")
MODEL_PATH = os.path.join(_HERE, "gesture_recognizer.task")

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
PINCH_EXIT_RATIO     = 0.36   # gap that always releases it (was 0.44: people
                              # had to open their fingers wide to let go)
PINCH_RELEASE_OPEN   = 0.12   # ...or opening this much from the tightest point
MIN_PALM_SIZE        = 0.02   # below this the hand is too far away to trust

TAP_MAX_SEC         = 0.65   # pinch held up to 0.65s without drag is a tap
TAP_COOLDOWN_SEC    = 0.35   # ignore repeat taps inside this window
DRAG_TAP_THRESHOLD = 0.040  # movement threshold during pinch to distinguish tap vs drag
DRAG_SCROLL_GAIN    = 1100.0 # movement -> scroll pixels
DRAG_DEADZONE       = 0.001  # smoothed movement below this per frame is not scrolled
FLING_VELOCITY_SCALE = 200.0 # release velocity multiplier for inertia fling
FLING_MIN_VELOCITY  = 0.25   # release speed (screen heights/s) that keeps a scroll gliding

TOP_RIGHT_X         = 0.62   # top-right quadrant dwell threshold
TOP_RIGHT_Y         = 0.18   # top-right height limit
RIGHT_DWELL_SEC     = 1.6    # hold hand in top-right region for 1.6s
HEARTBEAT_SEC       = 0.06   # publish UDP at least 16x/sec for smooth trail
HAND_LOST_SEC       = 0.4    # no landmarks for this long -> hand is gone

POSITION_QUANTUM    = 1.0 / 96

# Cursor smoothing (One Euro filter, positions in 0–1 screen units). A resting
# hand is smoothed down to MIN_CUTOFF Hz so landmark jitter disappears; the
# cutoff rises with speed (BETA), so a moving hand is followed with almost no
# lag. Raise MIN_CUTOFF for a twitchier cursor, BETA for less lag on fast moves.
CURSOR_MIN_CUTOFF   = 2.5   # was 1.2: slow, aiming movements lagged behind the
CURSOR_BETA         = 9.0   # hand. The magnet and sticky selection absorb the jitter.
CURSOR_D_CUTOFF     = 1.0

# Picking the hand to follow. A hand whose back faces the camera (by more than
# this fraction of a fully turned hand) is ignored, as long as MediaPipe is at
# least BACKHAND_MIN_LABEL_SCORE sure which hand it is.
BACKHAND_REJECT          = 0.25
BACKHAND_MIN_LABEL_SCORE = 0.6
CURRENT_HAND_BONUS       = 1.35   # stickiness, so two similar hands don't trade control

# Engaging. A hand only takes control once it is held up like the demo shows:
# palm to the camera, at least three fingers out (a pinch leaves three out).
# Scratching your head or pushing your hair back doesn't look like that, so it
# no longer moves the cursor. Once engaged, the hand keeps control until it is
# lost, whatever shape it makes.
ENGAGE_SEC          = 0.12    # presented this long (~3 frames) to take control
ENGAGE_MIN_FACING   = 0.15    # palm at least this square to the camera
ENGAGE_MIN_FINGERS  = 3

# Too close: past roughly half a metre the hand fills the frame and tracks badly.
TOO_CLOSE_PALM      = 0.24    # wrist→knuckle span as a share of the frame height
TOO_CLOSE_SEC       = 0.5

# Palm hint: a hand in view that isn't held up open (fingers curled, back to the
# camera, or a pinch with the other fingers folded down) for this long makes the
# mirror say how to hold it. It stays up a moment, so it doesn't flicker.
PALM_HINT_SEC       = 0.6
PALM_HINT_HOLD_SEC  = 1.2

# The reach box follows the hand (see GestureEngine.follow_box). The cursor sits
# on the screen edge while the hand is up to this far (a fraction of the camera
# picture) past the box edge; further than that, the box is dragged along.
BOX_FOLLOW_MARGIN   = 0.04
# GESTURE_FIXED_BOX=1 puts the box back where it was: the same place for every hand.
FIXED_BOX           = os.environ.get("GESTURE_FIXED_BOX", "") not in ("", "0", "false", "False", "no", "off")

# A hand lower than this in the camera picture (hanging by a side, or scanning a
# card at the bottom) is not one trying to use the mirror.
IGNORE_BELOW_Y      = 0.80

STATUS_FILE_EVERY   = 0.5     # the JSON file is only a fallback for UDP: rarely


class OneEuroFilter:
    """Speed-adaptive low-pass filter (Casiez et al., CHI 2012)."""

    def __init__(self, min_cutoff=CURSOR_MIN_CUTOFF, beta=CURSOR_BETA, d_cutoff=CURSOR_D_CUTOFF):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self):
        self._x = None
        self._dx = 0.0
        self._t = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        if self._x is None or self._t is None or t <= self._t:
            self._x, self._t = x, t
            return x
        dt = t - self._t
        self._t = t
        dx = (x - self._x) / dt
        self._dx += self._alpha(self.d_cutoff, dt) * (dx - self._dx)
        cutoff = self.min_cutoff + self.beta * abs(self._dx)
        self._x += self._alpha(cutoff, dt) * (x - self._x)
        return self._x


# ── Reach: the part of the camera image that covers the whole screen ─────────
# Only this box of the camera picture is stretched to the full screen, so a
# small hand movement crosses it and the arm can stay low and relaxed (testers'
# arms tired from reaching across the whole camera view). It sits low in the
# picture because the camera looks down from above the screen: the hand reaches
# the top of the screen at shoulder height. Override with
# GESTURE_REACH="x0,x1,y0,y1" (fractions of the camera image).
def _reach_box():
    try:
        x0, x1, y0, y1 = (float(v) for v in os.environ["GESTURE_REACH"].split(","))
        if 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1:
            return x0, x1, y0, y1
    except (KeyError, ValueError):
        pass
    return 0.22, 0.78, 0.25, 0.75

REACH_X0, REACH_X1, REACH_Y0, REACH_Y1 = _reach_box()

# The box is a size, not a place: when a hand takes control the box is centred on
# it, then follows it (GestureEngine.follow_box). REACH_X0.. are where it sits
# until then, and what to_screen() uses.


def to_screen(x, y):
    """A camera position (0-1) to a screen position (0-1), through the reach box."""
    sx = (x - REACH_X0) / (REACH_X1 - REACH_X0)
    sy = (y - REACH_Y0) / (REACH_Y1 - REACH_Y0)
    return min(1.0, max(0.0, sx)), min(1.0, max(0.0, sy))


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
        self.fixed_box = FIXED_BOX
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
        self._filter_x = OneEuroFilter()
        self._filter_y = OneEuroFilter()

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
        self.fps = 0.0               # smoothed processing rate, for the mirror's debug panel
        self.last_write = 0.0
        self.last_payload = None

        self._tmp_file = f"{GESTURE_STATUS_FILE}.{os.getpid()}.{id(self):x}.tmp"
        self._last_file_write = 0.0

        self.engaged = False
        self._engage_since = None
        self._hand_seen_at = 0.0     # any hand in view, in control or not
        self._last_engage_log = 0.0
        self.too_close = False
        self._close_since = None

        self.box = None              # (x0, y0) of the reach box in the camera picture, once a hand has one
        self.palm_hint = False       # a hand is in view but not held up open
        self._palm_bad_since = None
        self._palm_hint_until = 0.0
        self._saw_backhand = False

    def _init_tracker(self):
        """Build the MediaPipe hand tracker."""
        if mp is None:
            print("[GESTURE] mediapipe not installed — gesture control disabled.")
            return
        use_landmarker = os.path.exists(LANDMARKER_PATH)
        if not use_landmarker and not os.path.exists(MODEL_PATH):
            print("[GESTURE] Missing hand_landmarker.task (and gesture_recognizer.task). "
                  "Gesture control disabled.")
            return
        try:
            if use_landmarker:
                options = mp_vision.HandLandmarkerOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=LANDMARKER_PATH),
                    running_mode=mp_vision.RunningMode.VIDEO,
                    num_hands=1,
                    min_hand_detection_confidence=0.4,
                    min_hand_presence_confidence=0.4,
                    min_tracking_confidence=0.4,
                )
                landmarker = mp_vision.HandLandmarker.create_from_options(options)
                self._infer = landmarker.detect_for_video
                self.tracker = landmarker
                print("[GESTURE] Using the hand landmarker.", flush=True)
                return
            options = mp_vision.GestureRecognizerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
                running_mode=mp_vision.RunningMode.VIDEO,
                # One hand. Asked for two, MediaPipe runs its palm detector on
                # every frame while only one is visible (nearly always), which
                # cost ~20 ms a frame on the Pi. With one, a tracked hand skips it.
                num_hands=1,
                min_hand_detection_confidence=0.4,   # lower = fewer skipped frames
                min_tracking_confidence=0.4,          # lower = faster tracking recovery
            )
            self.tracker = mp_vision.GestureRecognizer.create_from_options(options)
            self._infer = self.tracker.recognize_for_video
            print("[GESTURE] Using the gesture recognizer (hand_landmarker.task not found).", flush=True)
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
    def palm_facing(lm, handedness='Right'):
        """How squarely the palm faces the camera: +1 palm on, -1 back on, ~0 side on.

        The wrist → middle-knuckle and index → pinky knuckle vectors span the
        palm; the sign of their cross product says which way it faces, and which
        sign means "palm" depends on whether it is a left or a right hand.
        MediaPipe labels hands from how they look in the image, so the label and
        the geometry swap together when the frame is mirrored — the answer is
        the same with or without --flip.
        """
        if not lm or len(lm) < 18:
            return 1.0
        ux, uy = lm[9].x - lm[0].x, lm[9].y - lm[0].y
        vx, vy = lm[17].x - lm[5].x, lm[17].y - lm[5].y
        cross = ux * vy - uy * vx
        span = math.hypot(ux, uy) * math.hypot(vx, vy)
        if span <= 1e-9:
            return 0.0
        facing = cross / span
        # Sign checked against the real camera: for a hand MediaPipe labels
        # 'Right', a negative cross product is the palm side.
        return -facing if handedness == 'Right' else facing

    @classmethod
    def is_backhand(cls, lm, handedness='Right', label_score=1.0):
        """True when the back of the hand faces the camera.

        Only trusted when MediaPipe is reasonably sure which hand it is looking
        at — with the label wrong the answer flips, and a real palm is worse to
        lose than a back of hand is to keep.
        """
        if handedness not in ('Left', 'Right') or label_score < BACKHAND_MIN_LABEL_SCORE:
            return False
        return cls.palm_facing(lm, handedness) < -BACKHAND_REJECT

    def fingers_out(self, lm):
        """How many of index..pinky are extended (tip further from the wrist than its middle joint)."""
        wrist = lm[0]
        out = 0
        for pip, tip in ((6, 8), (10, 12), (14, 16), (18, 20)):
            if self._distance(lm[tip], wrist) > 1.1 * self._distance(lm[pip], wrist):
                out += 1
        return out

    def is_presented(self, lm, handedness=None):
        """Held up to control the mirror: palm to the camera, fingers out."""
        if self._palm_size(lm) < MIN_PALM_SIZE:
            return False
        if handedness in ('Left', 'Right') and self.palm_facing(lm, handedness) < ENGAGE_MIN_FACING:
            return False
        return self.fingers_out(lm) >= ENGAGE_MIN_FINGERS

    def update_engagement(self, lm, handedness, now):
        """Whether this hand is in control (see ENGAGE_SEC)."""
        if self.engaged:
            return True
        if self.is_presented(lm, handedness):
            if self._engage_since is None:
                self._engage_since = now
            if now - self._engage_since >= ENGAGE_SEC:
                self.engaged = True
                self._engage_since = None
        else:
            self._engage_since = None
        return self.engaged

    def update_too_close(self, lm, now):
        if self._palm_size(lm) > TOO_CLOSE_PALM:
            if self._close_since is None:
                self._close_since = now
            self.too_close = now - self._close_since >= TOO_CLOSE_SEC
        else:
            self._close_since = None
            self.too_close = False

    @staticmethod
    def _in_frame(lm, margin=0.02):
        """Share of the 21 landmarks inside the frame — a cut-off hand tracks badly."""
        inside = sum(1 for p in lm if -margin <= p.x <= 1 + margin and -margin <= p.y <= 1 + margin)
        return inside / len(lm) if lm else 0.0

    # ── The reach box that follows the hand ──────────────────────────────────

    @staticmethod
    def _box_size():
        return REACH_X1 - REACH_X0, REACH_Y1 - REACH_Y0

    def follow_box(self, x, y):
        """Keep the reach box where this hand can use all of it.

        The first time a hand is in control the box is centred on it (kept inside
        the picture, so a hand at the edge gets a box whose edge is at the
        picture's edge). After that the box stays put while the hand roams in it;
        a hand pushed well past an edge (BOX_FOLLOW_MARGIN) drags that edge along.
        """
        if self.fixed_box:
            return
        w, h = self._box_size()
        if self.box is None:
            x0, y0 = x - w / 2, y - h / 2
        else:
            x0, y0 = self.box
            if x < x0 - BOX_FOLLOW_MARGIN:
                x0 = x + BOX_FOLLOW_MARGIN
            elif x > x0 + w + BOX_FOLLOW_MARGIN:
                x0 = x - w - BOX_FOLLOW_MARGIN
            if y < y0 - BOX_FOLLOW_MARGIN:
                y0 = y + BOX_FOLLOW_MARGIN
            elif y > y0 + h + BOX_FOLLOW_MARGIN:
                y0 = y - h - BOX_FOLLOW_MARGIN
        self.box = (min(max(x0, 0.0), 1.0 - w), min(max(y0, 0.0), 1.0 - h))

    def to_screen(self, x, y):
        """A camera position to a screen position, through this hand's box."""
        if self.box is None:
            return to_screen(x, y)
        w, h = self._box_size()
        sx = (x - self.box[0]) / w
        sy = (y - self.box[1]) / h
        return min(1.0, max(0.0, sx)), min(1.0, max(0.0, sy))

    # ── Telling people how to hold their hand ────────────────────────────────

    def update_palm_hint(self, lm, handedness, now):
        """Flag a hand that isn't open: fingers down, back to the camera, or a lone pinch.

        Before control, that is a hand that isn't presented. In control, it is
        one with fewer than three fingers out (a real pinch leaves three).
        lm None means no usable hand; only a back-of-hand sighting still counts.
        """
        bad = False
        if lm is not None:
            if self._palm_size(lm) >= MIN_PALM_SIZE:
                if self.engaged:
                    bad = self.fingers_out(lm) < ENGAGE_MIN_FINGERS
                else:
                    bad = not self.is_presented(lm, handedness)
        elif self._saw_backhand:
            bad = True
        if bad:
            if self._palm_bad_since is None:
                self._palm_bad_since = now
            if now - self._palm_bad_since >= PALM_HINT_SEC:
                self._palm_hint_until = now + PALM_HINT_HOLD_SEC
        else:
            self._palm_bad_since = None
        self.palm_hint = now < self._palm_hint_until

    def select_best_hand(self, hand_landmarks_list, handedness_list=None):
        """The clearest palm in view: big (close), facing the camera, fully in frame.

        Backs of hands are dropped, and the hand already in control keeps it
        unless another is clearly better, so control doesn't flicker between two
        similar hands.
        """
        self._saw_backhand = False
        if not hand_landmarks_list:
            return None, None

        candidates = []
        for idx, lm in enumerate(hand_landmarks_list):
            h_name = None            # unknown: never judged palm or back
            h_score = 1.0
            if handedness_list and idx < len(handedness_list) and handedness_list[idx]:
                cat = handedness_list[idx][0]
                h_name = getattr(cat, 'category_name', 'Right')
                h_score = getattr(cat, 'score', 1.0)

            if self.is_backhand(lm, h_name, h_score):
                self._saw_backhand = True
                continue

            raw_x, raw_y = self._palm_center(lm)
            cx, cy = self.to_screen(raw_x, raw_y)
            if raw_y > IGNORE_BELOW_Y:
                continue

            size = self._palm_size(lm)
            if size < MIN_PALM_SIZE:
                continue

            if h_name in ('Left', 'Right') and h_score >= BACKHAND_MIN_LABEL_SCORE:
                facing = max(0.0, self.palm_facing(lm, h_name))
            else:
                facing = 0.5
            score = size * (0.5 + 0.5 * facing) * (h_score ** 0.5) * self._in_frame(lm)

            if self.present:
                dist = math.hypot((cx - self.hand_x) * self.frame_aspect, cy - self.hand_y)
                if dist < 0.15:
                    score *= CURRENT_HAND_BONUS

            candidates.append((score, lm, h_name))

        if not candidates:
            return None, None
        self._saw_backhand = False      # a usable hand is in view: no need to ask for the palm

        candidates.sort(key=lambda c: c[0], reverse=True)
        return candidates[0][1], candidates[0][2]

    def is_pinching(self, lm):
        palm = self._palm_size(lm)
        if palm < MIN_PALM_SIZE:
            return False
        ratio = self._distance(lm[4], lm[8]) / palm
        if self.pinch_start is None:
            self.pinch_min_ratio = ratio
            return ratio < PINCH_ENTER_RATIO
        # Let go as soon as the fingers start to part. Someone who pinched
        # tightly releases at the enter threshold, not a wide-open hand; the
        # gap between enter and exit is kept small, just enough for jitter.
        self.pinch_min_ratio = min(getattr(self, 'pinch_min_ratio', ratio), ratio)
        release = min(PINCH_EXIT_RATIO, max(PINCH_ENTER_RATIO, self.pinch_min_ratio + PINCH_RELEASE_OPEN))
        return ratio < release

    @staticmethod
    def _palm_center(lm):
        pts = [lm[0], lm[5], lm[9], lm[13], lm[17]]
        return (sum(p.x for p in pts) / len(pts),
                sum(p.y for p in pts) / len(pts))

    # ── Per-frame analysis ───────────────────────────────────────────────────

    def process_landmarks(self, lm, now):
        self.scroll_delta = 0
        raw_x, raw_y = self._palm_center(lm)
        self.follow_box(raw_x, raw_y)
        x, y = self.to_screen(raw_x, raw_y)
        # The published cursor is filtered; region and dwell use the unfiltered
        # position so a gesture is judged on where the hand really is. Drags use
        # the camera position, so pinch wobble and scroll speed are unchanged.
        self.hand_x = self._filter_x(x, now)
        self.hand_y = self._filter_y(y, now)
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
        # Judged on how far the hand has got from where the pinch began.
        # Summing every frame-to-frame wobble (as this used to) let ordinary
        # landmark jitter add up to a "drag", and a click that was meant was
        # silently thrown away. The raw palm position is used, not the smoothed
        # cursor, so scrolling starts on the frame the hand moves; the mirror
        # smooths the scroll itself.
        sy = raw_y
        if pinched:
            if self.pinch_start is None:
                self.pinch_start = now
                self.pinch_at = (self.hand_x, self.hand_y)   # where they aimed
                self.drag_start_y = sy
                self.last_drag_y = sy
                self.drag_dist = 0.0
                self.drag_velocity = 0.0
                self.had_scroll = False
                self.last_frame_time = now
            else:
                dy = sy - self.last_drag_y
                dt = max(0.001, now - self.last_frame_time)
                self.last_frame_time = now
                self.drag_velocity = 0.6 * self.drag_velocity + 0.4 * (dy / dt)
                self.last_drag_y = sy
                self.drag_dist = max(self.drag_dist, abs(sy - self.drag_start_y))

                if self.drag_dist > DRAG_TAP_THRESHOLD:
                    # The first scroll includes the travel that crossed the
                    # threshold, so the content doesn't lag behind the hand.
                    move = dy if self.had_scroll else sy - self.drag_start_y
                    if abs(move) > DRAG_DEADZONE:
                        delta = int(round(-move * DRAG_SCROLL_GAIN))
                        if delta != 0:
                            self.had_scroll = True
                            self.scroll_delta = max(-300, min(300, delta))
                            if event is None:
                                event = "scroll"
        else:
            if self.pinch_start is not None:
                held = now - self.pinch_start
                released_velocity = self.drag_velocity   # capture before reset
                was_drag = (self.drag_dist > DRAG_TAP_THRESHOLD
                            or self.had_scroll
                            or held > TAP_MAX_SEC)

                self.pinch_start = None
                self.drag_start_y = None
                self.last_drag_y = None
                self.drag_dist = 0.0
                self.drag_velocity = 0.0
                had_scroll, self.had_scroll = self.had_scroll, False

                if not was_drag:
                    cooled = (self.last_tap_time is None
                              or now - self.last_tap_time > TAP_COOLDOWN_SEC)
                    if cooled:
                        self.last_tap_time = now
                        self.tap_at = getattr(self, 'pinch_at', (self.hand_x, self.hand_y))
                        if event is None:
                            event = "tap"
                elif had_scroll and abs(released_velocity) > FLING_MIN_VELOCITY:
                    if event is None:
                        fling_delta = int(-released_velocity * FLING_VELOCITY_SCALE)
                        self.scroll_delta = max(-500, min(500, fling_delta))
                        event = "fling"
        return event

    def step(self, lm, handedness, now):
        """One camera frame: the chosen hand (or None). Publishes, returns the event."""
        self.update_palm_hint(lm, handedness, now)
        if lm is not None:
            self._hand_seen_at = now
            if self.update_engagement(lm, handedness, now):
                self.update_too_close(lm, now)
                event = self.process_landmarks(lm, now)
                self.write_status(event, self.scroll_delta)
                return event
            if now - self._last_engage_log > 3.0:   # why a visible hand isn't in control
                self._last_engage_log = now
                facing = self.palm_facing(lm, handedness) if handedness in ('Left', 'Right') else None
                print(f"[GESTURE] Hand seen, not in control yet: fingers out {self.fingers_out(lm)}, "
                      f"palm facing {facing if facing is None else round(facing, 2)} ({handedness})", flush=True)
        became_absent = self.mark_absent(now)
        self.write_status(force=became_absent)
        return None

    def mark_absent(self, now):
        if not self.present:
            # A hand held up but not yet in control keeps its engage timer;
            # only forget it once no hand at all has been seen for a moment.
            # (Resetting it on every such frame meant no hand ever took control.)
            if now - max(self.last_seen, self._hand_seen_at) >= HAND_LOST_SEC:
                self.engaged = False
                self._engage_since = None
            return False
        if now - self.last_seen < HAND_LOST_SEC:
            return False
        self.present = False
        self.engaged = False
        self.box = None
        self._engage_since = None
        self.too_close = False
        self._close_since = None
        self.region = None
        self._filter_x.reset()
        self._filter_y.reset()
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

        payload = (self.present, self.region, event, self._quantised_position(), self.pinched,
                   round(self.right_dwell_progress, 2), self.too_close, self.palm_hint)
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
                        "too_close":            self.too_close,
                        "palm_hint":            self.palm_hint,
                        "event":                None,
                        "event_id":             getattr(self, '_event_id', 0),
                        "scroll_delta":         0,
                        "seq":                  self.seq,
                        "fps":                  round(self.fps, 1),
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
            "too_close":            self.too_close,
            "palm_hint":            self.palm_hint,
            "event":                event,
            # A tap acts where its pinch began, not where the hand drifted to.
            "tap_x":                round(self.tap_at[0], 4) if event == "tap" and getattr(self, 'tap_at', None) else None,
            "tap_y":                round(self.tap_at[1], 4) if event == "tap" and getattr(self, 'tap_at', None) else None,
            "event_id":             getattr(self, '_event_id', 0),
            "scroll_delta":         scroll_delta,
            "seq":                  self.seq,
            "fps":                  round(self.fps, 1),
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

        if not (force or event) and now - self._last_file_write < STATUS_FILE_EVERY:
            return
        self._last_file_write = now
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

        from loopback_capture import FFmpegPipeCapture, LatestFrameReader
        if not isinstance(cap, FFmpegPipeCapture):   # that one already keeps only the newest
            cap = LatestFrameReader(cap)

        start = time.time()
        last_stamp_ms = -1
        stats_since, stats_frames, stats_busy = time.time(), 0, 0.0
        stats_model, stats_hand = 0.0, 0
        last_frame_at = 0.0
        try:
            while self.running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue
                t_frame = time.time()
                if last_frame_at:
                    gap = t_frame - last_frame_at
                    if gap > 0:
                        self.fps = 0.9 * self.fps + 0.1 * (1.0 / gap) if self.fps else 1.0 / gap
                last_frame_at = t_frame

                if self.flip:
                    frame = cv2.flip(frame, 1)
                h, w = frame.shape[:2]
                self.frame_aspect = (w / h) if h else 1.0
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

                stamp_ms = max(int((time.time() - start) * 1000), last_stamp_ms + 1)
                last_stamp_ms = stamp_ms
                t_model = time.time()
                results = self._infer(image, stamp_ms)
                stats_model += time.time() - t_model
                stats_hand += 1 if results.hand_landmarks else 0

                now = time.time()
                self.scroll_delta = 0
                event = None

                best_lm, hand_name = None, None
                if results.hand_landmarks:
                    best_lm, hand_name = self.select_best_hand(
                        results.hand_landmarks, getattr(results, 'handedness', None)
                    )
                event = self.step(best_lm, hand_name, now)

                if event:
                    print(f"[GESTURE] {event} region={self.region} delta={self.scroll_delta}")

                stats_frames += 1
                stats_busy += time.time() - t_frame
                if t_frame - stats_since >= 10.0:
                    print(f"[GESTURE] {stats_frames / (t_frame - stats_since):.1f} fps, "
                          f"{1000 * stats_busy / stats_frames:.0f} ms per frame "
                          f"({1000 * stats_model / stats_frames:.0f} in the model), "
                          f"hand in view {100 * stats_hand / stats_frames:.0f}%", flush=True)
                    stats_since, stats_frames, stats_busy = t_frame, 0, 0.0
                    stats_model, stats_hand = 0.0, 0
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
