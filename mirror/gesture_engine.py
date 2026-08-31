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

Holding thumb and index together becomes a click-and-drag: move the held hand
to scroll and release it after a short, still click to select. Holding an open
hand at the far-left edge peeks the timetable, which then slides left to reveal
the King's Week grid underneath it.

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

    Which side of the frame your left hand lands on depends entirely on where the
    camera physically sits, and no default is right for every rig. A camera
    mounted in the mirror looking back at the student needs the flip: it sees the
    student the way another person would, so their left hand arrives on the right
    of the frame, and mirroring puts it back under the panel on their left.

    The Pi is that case, so it flips. A desktop rig is a phone or webcam on a
    stand pointing from wherever there was room, which is as often reversed as
    not — this one was — so it does not, and `GESTURE_FLIP=1` turns it back on.
    """
    env = os.environ.get("GESTURE_FLIP")
    if env is not None:
        return env not in ("0", "false", "False", "no", "off", "")
    return sys.platform.startswith("linux")

# ── Region boundaries ────────────────────────────────────────────────────────
# Left half (x < 0.50) is the notices column; right side (x > 0.62) is the peek.
REGION_LEFT_EDGE  = 0.50
REGION_RIGHT_EDGE = 0.62

REGION_LEFT   = "left"
REGION_CENTER = "center"
REGION_RIGHT  = "right"

# ── Tuning ───────────────────────────────────────────────────────────────────
# A pinch is measured as a *fraction of the hand's own size*, never as a raw
# normalised distance. Landmarks are fractions of the frame, so a hand at arm's
# length is numerically tiny: a fixed threshold of 0.06 meant a distant hand read
# as permanently pinched and a hand close to the camera could never pinch at all.
# Dividing by the palm makes the test the same at any distance.
#
# Two thresholds, not one: fingers hovering right on the boundary would otherwise
# chatter between pinched and open several times a second, firing a burst of
# taps. You have to close to ENTER and open past EXIT to let go.
PINCH_ENTER_RATIO  = 0.55   # thumb-index gap / palm size to start a pinch
PINCH_EXIT_RATIO   = 0.75   # and to release it again
MIN_PALM_SIZE      = 0.02   # below this the hand is too far away to trust

TAP_MAX_SEC        = 0.6    # pinch held longer than this is a hold, not a tap
TAP_COOLDOWN_SEC   = 0.6    # ignore repeat taps inside this window
SCROLL_DEADZONE    = 0.012  # ignore palm jitter below this normalised movement
SCROLL_GAIN        = 900.0  # normalised palm movement → scroll pixels
SCROLL_MAX_PX      = 90     # clamp one frame's scroll so a fast wave can't jump
RIGHT_DWELL_SEC    = 0.45   # deliberate edge hold before opening the side panel
LEFT_EDGE_TRIGGER  = 0.08   # far-left hold opens the timetable / King's Week panel
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

        self.engaged = False          # thumb+index held → drag scroll is active
        self.scroll_anchor_y = None
        self.scroll_delta = 0
        self.drag_moved = False

        self.pinch_start = None       # when the current pinch began
        self.last_tap_time = None     # None = no tap yet, so no cooldown to serve

        self.left_since = None        # when the palm reached the far-left edge
        self.left_armed = True        # re-arms once the hand leaves that edge

        self.seq = 0
        self.last_write = 0.0
        self.last_payload = None

        # The scratch file is per-engine. Two daemons sharing one name is not a
        # hypothetical: orphaned copies pile up from earlier launches, and they
        # would each create, then replace, then find the other had already moved
        # the same .tmp — reported as a stream of WinError 5 / WinError 32. The
        # published file is still shared, which is fine: os.replace is atomic, so
        # a reader always sees one whole payload from one of the writers.
        self._tmp_file = f"{GESTURE_STATUS_FILE}.{os.getpid()}.{id(self):x}.tmp"

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

    def _distance(self, p1, p2):
        """Distance between two landmarks in square units.

        x is a fraction of the frame width and y a fraction of its height, so on
        a 640x480 frame one unit of x is not one unit of y and a diagonal comes
        out wrong. Scaling x by the aspect ratio fixes that. z is left out
        entirely: MediaPipe's depth is relative to the wrist, on its own scale,
        and noisy enough to swamp a thumb-to-index measurement.
        """
        dx = (p1.x - p2.x) * self.frame_aspect
        dy = p1.y - p2.y
        return math.sqrt(dx * dx + dy * dy)

    def _palm_size(self, lm):
        """A distance-invariant scale for the hand: wrist → middle-finger MCP.

        Both are on the palm, so curling or splaying the fingers does not change
        it — unlike anything measured to a fingertip.
        """
        return self._distance(lm[0], lm[9])

    def is_pinching(self, lm):
        """True while the thumb and index finger are touching — the 'click'.

        Ratio, not raw distance, and hysteresis so a gap hovering on the
        threshold does not rattle out a stream of taps.
        """
        palm = self._palm_size(lm)
        if palm < MIN_PALM_SIZE:
            # Too far away (or a bad detection) for the ratio to mean anything.
            return False
        ratio = self._distance(lm[4], lm[8]) / palm
        threshold = PINCH_EXIT_RATIO if self.pinch_start is not None else PINCH_ENTER_RATIO
        return ratio < threshold

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

        # Leaving the far-left edge re-arms the deliberate panel reveal.
        if x > LEFT_EDGE_TRIGGER:
            self.left_since = None
            self.left_armed = True

        pinched = self.is_pinching(lm)
        event = None

        # ── Click / drag: hold thumb and index together, then move ───────────
        # This is intentionally a direct drag rather than a stream of loose
        # open-palm scroll ticks: every frame moves the target by the distance
        # the held hand actually travelled, so a student can drag through an
        # entire list without waiting for any easing or auto-scroll pause.
        if pinched:
            if self.pinch_start is None:
                self.pinch_start = now
                self.engaged = True
                self.drag_moved = False
                self.scroll_anchor_y = y
            elif not region_changed:
                dy = y - self.scroll_anchor_y
                if abs(dy) > SCROLL_DEADZONE:
                    # This is a content drag, not a mouse-wheel gesture: pull
                    # your held hand down and the list follows it down.
                    delta = int(max(-SCROLL_MAX_PX,
                                    min(SCROLL_MAX_PX, -dy * SCROLL_GAIN)))
                    if delta != 0:
                        self.scroll_anchor_y = y
                        self.drag_moved = True
                        self.scroll_delta = delta
                        return "scroll"
        else:
            if self.pinch_start is not None:
                held = now - self.pinch_start
                self.pinch_start = None
                was_drag = self.drag_moved
                self.engaged = False
                self.drag_moved = False
                self.scroll_anchor_y = None
                cooled = (self.last_tap_time is None
                          or now - self.last_tap_time > TAP_COOLDOWN_SEC)
                if not was_drag and held <= TAP_MAX_SEC and cooled:
                    self.last_tap_time = now
                    event = "tap"

        # ── Timetable reveal: deliberate far-left open-hand hold ─────────────
        if x <= LEFT_EDGE_TRIGGER and not pinched and event is None:
            if self.left_since is None:
                self.left_since = now
            elif self.left_armed and now - self.left_since >= RIGHT_DWELL_SEC:
                self.left_armed = False
                event = "enter_left"

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
        self.drag_moved = False
        self.left_since = None
        self.left_armed = True
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
        # Include interaction state as well as position. In particular, the
        # first pinched frame has no scroll event by design, but the UI needs to
        # receive it to establish the drag's starting position.
        edge_hold = self._edge_hold_progress(now)
        payload = (self.present, self.region, event, self._quantised_position(),
                   self.engaged, int(edge_hold * 12))
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
            # The UI uses this absolute position while a pinch is held, rather
            # than adding only the last camera-frame delta it happened to read.
            # That makes a drag retain its full distance even though Qt polls
            # this file more slowly than MediaPipe produces frames.
            "dragging":     self.engaged,
            "edge_hold":    edge_hold,
            "seq":          self.seq,
            "timestamp":    now,
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

    def _edge_hold_progress(self, now):
        """0..1 progress for the visible far-left reveal indicator."""
        if self.left_since is None or self.hand_x > LEFT_EDGE_TRIGGER:
            return 0.0
        return round(min(1.0, max(0.0, (now - self.left_since) / RIGHT_DWELL_SEC)), 3)

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
