"""Offline tests for the region-based gesture engine.

No camera and no mediapipe needed — the tracker is stubbed out and synthetic
landmark sets are fed straight into process_landmarks().

Run from the mirror/ directory:  python -m unittest test_gesture_engine
"""

import json
import os
import sys
import tempfile
import time
import unittest

import gesture_engine
from gesture_engine import (
    GestureEngine,
    REGION_LEFT, REGION_CENTER, REGION_RIGHT,
    RIGHT_DWELL_SEC, TAP_MAX_SEC, HAND_LOST_SEC,
    DRAG_DEADZONE, HEARTBEAT_SEC, POSITION_QUANTUM,
    PINCH_ENTER_RATIO, PINCH_EXIT_RATIO, MIN_PALM_SIZE,
    classify_region, default_flip,
)


class _P:
    """Stand-in for a mediapipe NormalizedLandmark."""

    def __init__(self, x, y, z=0.0):
        self.x, self.y, self.z = x, y, z


# `scale` is the wrist → middle-knuckle distance, which is exactly what the
# engine measures a pinch against, so it doubles as "how far away the hand is".
# 0.18 of the frame is about what MediaPipe reports for a hand held up at a
# mirror at a comfortable arm's length.
DEFAULT_SCALE = 0.18

# The palm, in units of `scale`, with the wrist at the origin and y negative
# upwards: wrist, then the index / middle / ring / pinky knuckles.
_MCP = {5: (-0.35, -0.95), 9: (0.0, -1.0), 13: (0.33, -0.95), 17: (0.62, -0.85)}

# Where the palm centre lands before re-centering, so make_hand can subtract it.
_CENTER = (sum(p[0] for p in [(0.0, 0.0)] + list(_MCP.values())) / 5,
           sum(p[1] for p in [(0.0, 0.0)] + list(_MCP.values())) / 5)


def make_hand(px, py, closed=False, pinch=False, scale=DEFAULT_SCALE):
    """21 landmarks for a hand of size `scale` whose palm centre is (px, py).

    closed=True tucks the finger tips below their knuckles (no scroll control);
    pinch=True brings the thumb tip onto the index tip.

    The hand has a real palm, and that is the point. The engine sizes a pinch as
    a fraction of the wrist → middle-knuckle distance, so the old fixture — every
    one of the 21 landmarks on a single point — had a palm of zero and could
    never pinch at all, no matter where the thumb was put.
    """
    pts = {0: (0.0, 0.0)}
    pts.update(_MCP)

    reach = -0.35 if closed else 0.9        # tip offset from its knuckle
    for mcp, tip in ((5, 8), (9, 12), (13, 16), (17, 20)):
        mx, my = _MCP[mcp]
        pts[tip] = (mx, my - reach)
        pts[mcp + 1] = (mx, my - reach / 3)          # PIP
        pts[mcp + 2] = (mx, my - reach * 2 / 3)      # DIP

    if pinch:
        # The index curls back to meet the thumb, which is what a hand actually
        # does — the thumb does not travel the whole way on its own.
        mx, my = _MCP[5]
        pts[8] = (mx, my - reach * 0.55)
        pts[4] = (pts[8][0] - 0.12, pts[8][1] + 0.09)
    else:
        pts[4] = (1.1, -0.4)

    # Thumb CMC / MCP / IP spaced along wrist → tip. Unused by the engine, but a
    # hand with three landmarks sitting on the wrist is a confusing fixture.
    for i, f in ((1, 0.25), (2, 0.55), (3, 0.8)):
        pts[i] = (pts[4][0] * f, pts[4][1] * f)

    cx, cy = _CENTER
    return [_P(px + (pts[i][0] - cx) * scale, py + (pts[i][1] - cy) * scale)
            for i in range(21)]


class StubEngine(GestureEngine):
    def _init_tracker(self):
        pass  # no mediapipe, no camera


class TestRegions(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(classify_region(0.0), REGION_LEFT)
        self.assertEqual(classify_region(0.33), REGION_LEFT)
        self.assertEqual(classify_region(0.5), REGION_CENTER)
        self.assertEqual(classify_region(0.7), REGION_RIGHT)
        self.assertEqual(classify_region(1.0), REGION_RIGHT)

    def test_palm_center_drives_region_not_fingertips(self):
        # Fingers pointing right from a left-side palm must not drag the region
        # across — that is the flicker the palm average exists to prevent.
        e = StubEngine()
        e.process_landmarks(make_hand(0.2, 0.5), now=1000.0)
        self.assertEqual(e.region, REGION_LEFT)


class TestPinchDrag(unittest.TestCase):
    def setUp(self):
        self.e = StubEngine()

    def test_pinch_starts_drag(self):
        self.assertIsNone(self.e.process_landmarks(make_hand(0.2, 0.5, pinch=True), 1000.0))
        self.assertTrue(self.e.pinched)

    def test_pinch_drag_down_scrolls_inverted(self):
        self.e.process_landmarks(make_hand(0.2, 0.5, pinch=True), 1000.0)
        event = self.e.process_landmarks(make_hand(0.2, 0.56, pinch=True), 1000.1)
        self.assertEqual(event, "scroll")
        self.assertLess(self.e.scroll_delta, 0)

    def test_pinch_drag_up_scrolls_inverted(self):
        self.e.process_landmarks(make_hand(0.2, 0.5, pinch=True), 1000.0)
        event = self.e.process_landmarks(make_hand(0.2, 0.44, pinch=True), 1000.1)
        self.assertEqual(event, "scroll")
        self.assertGreater(self.e.scroll_delta, 0)

    def test_unpinched_hand_does_not_scroll(self):
        self.e.process_landmarks(make_hand(0.2, 0.5, pinch=False), 1000.0)
        event = self.e.process_landmarks(make_hand(0.2, 0.7, pinch=False), 1000.1)
        self.assertIsNone(event)
        self.assertEqual(self.e.scroll_delta, 0)

    def test_quick_pinch_release_without_drag_is_tap(self):
        self.e.process_landmarks(make_hand(0.2, 0.5, pinch=True), 1000.0)
        event = self.e.process_landmarks(make_hand(0.2, 0.501, pinch=False), 1000.2)
        self.assertEqual(event, "tap")

    def test_right_dwell_progress_tracks_and_triggers_enter_right(self):
        self.e.process_landmarks(make_hand(0.85, 0.5, pinch=False), 1000.0)
        self.assertEqual(self.e.right_dwell_progress, 0.0)
        self.e.process_landmarks(make_hand(0.85, 0.5, pinch=False), 1000.5)
        self.assertAlmostEqual(self.e.right_dwell_progress, 0.5, places=2)
        event = self.e.process_landmarks(make_hand(0.85, 0.5, pinch=False), 1001.05)
        self.assertEqual(event, "enter_right")
        self.assertEqual(self.e.right_dwell_progress, 1.0)


class TestPinch(unittest.TestCase):
    """Thumb-to-index proximity — the click.

    This never worked in front of the mirror, and the reason was scale. The test
    used to be a fixed normalised distance, but a landmark is a fraction of the
    frame: a hand at arm's length is numerically small, so its thumb and index
    were always "close" and the mirror read a permanent pinch, while a hand near
    the camera could put its fingers together and never get under the threshold.
    Everything here is about the measurement being the same at any distance.
    """

    def setUp(self):
        self.e = StubEngine()

    def test_a_touching_thumb_and_index_is_a_pinch(self):
        self.assertTrue(self.e.is_pinching(make_hand(0.5, 0.5, pinch=True)))

    def test_an_open_hand_is_not(self):
        self.assertFalse(self.e.is_pinching(make_hand(0.5, 0.5)))

    def test_the_palm_measures_its_own_scale(self):
        # The pinch ratio divides by this, so it has to track the hand's size and
        # ignore what the fingers are doing.
        for scale in (0.06, 0.18, 0.45):
            for kwargs in ({}, {'closed': True}, {'pinch': True}):
                hand = make_hand(0.5, 0.5, scale=scale, **kwargs)
                self.assertAlmostEqual(self.e._palm_size(hand), scale, places=6)

    def test_pinching_works_at_every_distance(self):
        # A far hand (small in frame) and a near one (large) must behave the same.
        for scale in (0.05, 0.12, 0.3, 0.6):
            self.assertTrue(self.e.is_pinching(make_hand(0.5, 0.5, pinch=True,
                                                         scale=scale)),
                            f'a pinch at scale {scale} was missed')
            self.assertFalse(self.e.is_pinching(make_hand(0.5, 0.5, scale=scale)),
                             f'an open hand at scale {scale} read as pinched')

    def test_a_distant_hand_is_ignored_rather_than_guessed_at(self):
        # Below MIN_PALM_SIZE the landmarks are too coarse for the ratio to mean
        # anything, and a false click is worse than a missed one.
        tiny = MIN_PALM_SIZE / 2
        self.assertFalse(self.e.is_pinching(make_hand(0.5, 0.5, pinch=True,
                                                      scale=tiny)))

    def test_the_release_threshold_is_looser_than_the_grab(self):
        self.assertGreater(PINCH_EXIT_RATIO, PINCH_ENTER_RATIO)

    def test_a_gap_on_the_boundary_does_not_chatter(self):
        # Fingers held right at the threshold used to flap between pinched and
        # open several times a second, firing a burst of taps at whatever was
        # under the hand. Hysteresis means a gap between the two thresholds keeps
        # whichever state it is already in.
        between = (PINCH_ENTER_RATIO + PINCH_EXIT_RATIO) / 2
        borderline = self._hand_with_gap_ratio(between)

        self.assertFalse(self.e.is_pinching(borderline), 'closed a pinch too early')
        self.e.pinch_start = 1000.0                      # now mid-pinch
        self.assertTrue(self.e.is_pinching(borderline), 'released a pinch too early')

    def test_taps_survive_a_wobbling_gap(self):
        # The same thing end to end: one deliberate pinch that wobbles while held
        # is one tap, not a stream of them.
        t = 1000.0
        self.assertIsNone(self.e.process_landmarks(make_hand(0.2, 0.5, pinch=True), t))
        borderline = self._hand_with_gap_ratio(
            (PINCH_ENTER_RATIO + PINCH_EXIT_RATIO) / 2)
        for i in range(6):
            self.assertIsNone(self.e.process_landmarks(borderline, t + 0.02 * (i + 1)))
        self.assertEqual(self.e.process_landmarks(make_hand(0.2, 0.5), t + 0.3), "tap")

    def _hand_with_gap_ratio(self, ratio, scale=DEFAULT_SCALE):
        """A hand whose thumb-index gap is `ratio` of its palm, to the millimetre."""
        hand = make_hand(0.2, 0.5, pinch=True, scale=scale)
        index = hand[8]
        hand[4] = _P(index.x + ratio * scale, index.y)
        return hand


class TestDistance(unittest.TestCase):
    def test_the_frame_aspect_is_applied_to_x(self):
        # x is a fraction of the frame width and y of its height, so on a 640x480
        # frame a horizontal gap of 0.1 spans more pixels than a vertical one.
        # Ignoring that skewed every diagonal the pinch test measures.
        e = StubEngine()
        e.frame_aspect = 640 / 480
        horizontal = e._distance(_P(0.4, 0.5), _P(0.5, 0.5))
        vertical = e._distance(_P(0.5, 0.4), _P(0.5, 0.5))
        self.assertAlmostEqual(horizontal, 0.1 * 640 / 480, places=6)
        self.assertAlmostEqual(vertical, 0.1, places=6)

    def test_depth_is_left_out(self):
        # MediaPipe's z is wrist-relative, on its own scale, and noisy enough to
        # swamp a thumb-to-index gap.
        e = StubEngine()
        flat = e._distance(_P(0.4, 0.5, 0.0), _P(0.5, 0.5, 0.0))
        deep = e._distance(_P(0.4, 0.5, -0.9), _P(0.5, 0.5, 0.7))
        self.assertEqual(flat, deep)


class TestTap(unittest.TestCase):
    def setUp(self):
        self.e = StubEngine()

    def test_quick_pinch_and_release_taps(self):
        self.assertIsNone(self.e.process_landmarks(make_hand(0.2, 0.5, pinch=True), 1000.0))
        event = self.e.process_landmarks(make_hand(0.2, 0.5), 1000.2)
        self.assertEqual(event, "tap")

    def test_held_pinch_is_not_a_tap(self):
        self.e.process_landmarks(make_hand(0.2, 0.5, pinch=True), 1000.0)
        event = self.e.process_landmarks(make_hand(0.2, 0.5), 1000.0 + TAP_MAX_SEC + 0.3)
        self.assertIsNone(event)

    def test_second_tap_inside_cooldown_is_dropped(self):
        # Fingers wobbling apart and back must not read as two taps.
        self.e.process_landmarks(make_hand(0.2, 0.5, pinch=True), 1000.0)
        self.assertEqual(self.e.process_landmarks(make_hand(0.2, 0.5), 1000.2), "tap")
        self.e.process_landmarks(make_hand(0.2, 0.5, pinch=True), 1000.3)
        self.assertIsNone(self.e.process_landmarks(make_hand(0.2, 0.5), 1000.4))


class TestRightDwell(unittest.TestCase):
    def setUp(self):
        self.e = StubEngine()

    def test_dwell_fires_once(self):
        self.assertIsNone(self.e.process_landmarks(make_hand(0.85, 0.5), 1000.0))
        event = self.e.process_landmarks(make_hand(0.85, 0.5), 1000.0 + RIGHT_DWELL_SEC + 0.05)
        self.assertEqual(event, "enter_right")
        # Leaving the hand there must not re-trigger the peek every frame.
        for i in range(5):
            self.assertIsNone(self.e.process_landmarks(make_hand(0.85, 0.5), 1002.0 + i * 0.1))

    def test_passing_through_quickly_does_not_fire(self):
        self.e.process_landmarks(make_hand(0.85, 0.5), 1000.0)
        event = self.e.process_landmarks(make_hand(0.85, 0.5), 1000.0 + RIGHT_DWELL_SEC / 2)
        self.assertIsNone(event)

    def test_leaving_and_returning_rearms(self):
        self.e.process_landmarks(make_hand(0.85, 0.5), 1000.0)
        self.assertEqual(
            self.e.process_landmarks(make_hand(0.85, 0.5), 1000.0 + RIGHT_DWELL_SEC + 0.05), "enter_right"
        )
        self.e.process_landmarks(make_hand(0.2, 0.5), 1002.0)   # back to notices
        self.e.process_landmarks(make_hand(0.85, 0.5), 1003.0)   # returns to right
        self.assertEqual(
            self.e.process_landmarks(make_hand(0.85, 0.5), 1003.0 + RIGHT_DWELL_SEC + 0.05), "enter_right"
        )

    def test_hand_lost_rearms(self):
        self.e.process_landmarks(make_hand(0.85, 0.5), 1000.0)
        self.e.process_landmarks(make_hand(0.85, 0.5), 1000.0 + RIGHT_DWELL_SEC + 0.05)
        self.assertFalse(self.e.right_armed)
        self.assertTrue(self.e.mark_absent(1002.0 + HAND_LOST_SEC + 0.1))
        self.assertTrue(self.e.right_armed)


class TestAbsence(unittest.TestCase):
    def setUp(self):
        self.e = StubEngine()

    def test_brief_tracking_dropout_keeps_the_hand(self):
        # MediaPipe drops a frame now and then; that must not reset everything.
        self.e.process_landmarks(make_hand(0.2, 0.5), 1000.0)
        self.assertFalse(self.e.mark_absent(1000.0 + HAND_LOST_SEC / 2))
        self.assertTrue(self.e.present)
        self.assertEqual(self.e.region, REGION_LEFT)

    def test_sustained_absence_clears_state(self):
        self.e.process_landmarks(make_hand(0.2, 0.5), 1000.0)
        self.assertTrue(self.e.mark_absent(1000.0 + HAND_LOST_SEC + 0.1))
        self.assertFalse(self.e.present)
        self.assertIsNone(self.e.region)
        self.assertFalse(self.e.pinched)

    def test_absent_hand_resets_armed_state(self):
        # Trigger dwell, then drop the hand for long enough to lose it. When it
        # comes back it must be re-armed without having to leave the region.
        self.e.process_landmarks(make_hand(0.85, 0.5), 1000.0)
        self.e.process_landmarks(make_hand(0.85, 0.5), 1000.0 + RIGHT_DWELL_SEC + 0.05)
        self.assertFalse(self.e.right_armed)
        self.e.mark_absent(1002.0 + HAND_LOST_SEC + 0.1)
        self.assertTrue(self.e.right_armed)

    def test_absence_is_reported_once(self):
        self.e.process_landmarks(make_hand(0.2, 0.5), 1000.0)
        gone = 1000.0 + HAND_LOST_SEC + 0.1
        self.assertTrue(self.e.mark_absent(gone))
        self.assertFalse(self.e.mark_absent(gone + 1.0))


class TestStatusFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, 'gesture_status.json')
        self._orig = gesture_engine.GESTURE_STATUS_FILE
        gesture_engine.GESTURE_STATUS_FILE = self.path
        self.e = StubEngine()

    def tearDown(self):
        gesture_engine.GESTURE_STATUS_FILE = self._orig

    def _read(self):
        with open(self.path) as f:
            return json.load(f)

    def test_payload_shape(self):
        self.e.process_landmarks(make_hand(0.2, 0.6), 1000.0)
        self.e.write_status()
        data = self._read()
        self.assertTrue(data['present'])
        self.assertEqual(data['region'], REGION_LEFT)
        self.assertAlmostEqual(data['hand_x'], 0.2, places=3)
        self.assertAlmostEqual(data['hand_y'], 0.6, places=3)
        self.assertIsNone(data['event'])

    def test_unchanged_state_is_not_rewritten(self):
        # The mirror polls this file 10x a second; republishing an identical
        # state every frame is pure churn.
        self.e.process_landmarks(make_hand(0.2, 0.5), 1000.0)
        self.e.write_status()
        first_seq = self._read()['seq']
        self.e.write_status()
        self.assertEqual(self._read()['seq'], first_seq)

    def test_events_always_written(self):
        self.e.process_landmarks(make_hand(0.2, 0.5), 1000.0)
        self.e.write_status()
        before = self._read()['seq']
        self.e.write_status(event="tap")
        after = self._read()
        self.assertGreater(after['seq'], before)
        self.assertEqual(after['event'], "tap")

    def test_region_change_is_written(self):
        self.e.process_landmarks(make_hand(0.2, 0.5), 1000.0)
        self.e.write_status()
        before = self._read()['seq']
        self.e.process_landmarks(make_hand(0.8, 0.5), 1000.1)
        self.e.write_status()
        data = self._read()
        self.assertGreater(data['seq'], before)
        self.assertEqual(data['region'], REGION_RIGHT)

    def test_heartbeat_republishes_after_the_interval(self):
        self.e.process_landmarks(make_hand(0.2, 0.5), 1000.0)
        self.e.write_status()
        before = self._read()['seq']
        self.e.last_write -= (HEARTBEAT_SEC + 0.1)
        self.e.write_status()
        self.assertGreater(self._read()['seq'], before)

    def test_timestamp_advances(self):
        # smart_mirror_pro gates on a strictly increasing timestamp.
        self.e.process_landmarks(make_hand(0.2, 0.5), 1000.0)
        self.e.write_status(event="tap")
        t1 = self._read()['timestamp']
        self.e.write_status(event="tap")
        self.assertGreaterEqual(self._read()['timestamp'], t1)

    def test_moving_a_whole_cell_is_published(self):
        # The King's Week grid picks a box from hand_y, so a real move has to
        # reach the mirror without waiting for the heartbeat.
        self.e.process_landmarks(make_hand(0.8, 0.2), 1000.0)
        self.e.write_status()
        before = self._read()
        self.e.process_landmarks(make_hand(0.8, 0.2 + POSITION_QUANTUM * 2), 1000.1)
        self.e.write_status()
        after = self._read()
        self.assertGreater(after['seq'], before['seq'])
        self.assertGreater(after['hand_y'], before['hand_y'])

    def test_jitter_inside_one_cell_is_not_published(self):
        # Sub-cell wobble would otherwise rewrite the file on every frame.
        self.e.process_landmarks(make_hand(0.5, 0.2), 1000.0)
        self.e.write_status()
        before = self._read()['seq']
        self.e.process_landmarks(make_hand(0.5, 0.2 + POSITION_QUANTUM / 8), 1000.1)
        self.e.write_status()
        self.assertEqual(self._read()['seq'], before)


class TestConcurrentWriters(unittest.TestCase):
    """Two daemons publishing at once must not trip over each other.

    Orphaned daemons pile up in practice — the mirror spawns one per launch and
    only reaps it on a clean exit — and when they shared a single
    `gesture_status.json.tmp` the result was a steady stream of
    `WinError 5: Access is denied` as each replaced a scratch file the other had
    already moved. Every engine now writes its own, keyed by pid.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._orig = gesture_engine.GESTURE_STATUS_FILE
        gesture_engine.GESTURE_STATUS_FILE = os.path.join(self.dir,
                                                          'gesture_status.json')

    def tearDown(self):
        gesture_engine.GESTURE_STATUS_FILE = self._orig

    def test_two_engines_do_not_share_a_scratch_file(self):
        a, b = StubEngine(), StubEngine()
        # Same process, so the pid alone would collide — the name has to be
        # unique per engine, not merely per interpreter.
        self.assertNotEqual(a._tmp_file, b._tmp_file)

    def test_interleaved_writes_all_land(self):
        a, b = StubEngine(), StubEngine()
        a.process_landmarks(make_hand(0.2, 0.5), 1000.0)
        b.process_landmarks(make_hand(0.8, 0.5), 1000.0)

        # Interleave so each one's scratch file exists while the other replaces.
        for i in range(5):
            a.write_status(event='tap')
            b.write_status(event='tap')
            with open(gesture_engine.GESTURE_STATUS_FILE) as f:
                # Never a truncated or half-written payload, whoever won.
                self.assertIn(json.load(f)['region'],
                              (REGION_LEFT, REGION_RIGHT))

    def test_the_scratch_file_does_not_outlive_the_write(self):
        e = StubEngine()
        e.process_landmarks(make_hand(0.2, 0.5), 1000.0)
        e.write_status()
        self.assertFalse(os.path.exists(e._tmp_file),
                         'the scratch file should have been renamed away')


class TestTracker(unittest.TestCase):
    """The one part every other test stubs out: building the real tracker.

    Every test here overrides _init_tracker, so the daemon crashed on startup for
    a long time without a single failure — it used mediapipe's Solutions API,
    which 1.x removed, so `mp.solutions.hands` raised AttributeError before the
    camera was ever opened and nothing was ever published. Skipped rather than
    failed where mediapipe or the model file is absent, since the suite is meant
    to run without either.
    """

    def test_the_real_tracker_builds(self):
        if gesture_engine.mp is None:
            self.skipTest('mediapipe not installed')
        if not os.path.exists(gesture_engine.MODEL_PATH):
            self.skipTest(f'{gesture_engine.MODEL_PATH} not downloaded')

        engine = GestureEngine()          # not StubEngine — the real thing
        try:
            self.assertIsNotNone(
                engine.tracker,
                'the hand tracker did not build, so the daemon would exit at once'
            )
        finally:
            if engine.tracker is not None:
                engine.tracker.close()

    def test_a_missing_model_disables_gestures_without_raising(self):
        real = gesture_engine.MODEL_PATH
        gesture_engine.MODEL_PATH = os.path.join(tempfile.gettempdir(),
                                                 'definitely-not-a-model.task')
        try:
            engine = GestureEngine()      # must not raise
            self.assertIsNone(engine.tracker)
        finally:
            gesture_engine.MODEL_PATH = real


class TestCameraArgs(unittest.TestCase):
    """--rpi / --camera-id, matching face_recognize.py's flags."""

    def test_rpi_reads_the_loopback_device(self):
        camera = gesture_engine.parse_args(['--rpi'])[0]
        self.assertEqual(camera, gesture_engine.RPI_CAMERA)

    def test_a_webcam_index_comes_back_as_an_int(self):
        camera = gesture_engine.parse_args(['--camera-id', '4'])[0]
        self.assertEqual(camera, 4)

    def test_the_default_is_the_first_webcam(self):
        camera = gesture_engine.parse_args([])[0]
        self.assertEqual(camera, 0)

    def test_exiting_with_the_parent_is_opt_in(self):
        # Run by hand from a terminal, stdin is the keyboard and reading it would
        # block forever; only the mirror, which supplies a pipe, asks for this.
        self.assertFalse(gesture_engine.parse_args([])[1])
        self.assertTrue(gesture_engine.parse_args(['--exit-with-parent'])[1])


class TestFlip(unittest.TestCase):
    """Which physical side of you drives which panel.

    The panel is drawn at screen x=0 — the side on your left as you face the
    mirror — and it has to answer to the hand on your left. Whether that is a low
    or a high x in the camera frame depends entirely on where the camera sits, so
    this is a setting, not a constant: a camera mounted in the mirror sees you the
    way another person would and needs mirroring, a phone on a stand pointing in
    from somewhere else generally does not.
    """

    def setUp(self):
        self._env = os.environ.get('GESTURE_FLIP')
        os.environ.pop('GESTURE_FLIP', None)

    def tearDown(self):
        if self._env is None:
            os.environ.pop('GESTURE_FLIP', None)
        else:
            os.environ['GESTURE_FLIP'] = self._env

    def test_the_env_var_wins(self):
        for value in ('1', 'true', 'yes', 'on'):
            os.environ['GESTURE_FLIP'] = value
            self.assertTrue(default_flip(), value)
        for value in ('0', 'false', 'no', 'off', ''):
            os.environ['GESTURE_FLIP'] = value
            self.assertFalse(default_flip(), value)

    def test_the_pi_flips_and_the_desktop_does_not(self):
        # The Pi's camera is in the mirror facing the student; the dev rig's is a
        # webcam or phone pointing in from wherever there was room.
        self.assertEqual(default_flip(), sys.platform.startswith('linux'))

    def test_the_flags_override_the_default(self):
        self.assertTrue(gesture_engine.parse_args(['--flip'])[2])
        self.assertFalse(gesture_engine.parse_args(['--no-flip'])[2])

    def test_no_flag_falls_back_to_the_default(self):
        os.environ['GESTURE_FLIP'] = '1'
        self.assertTrue(gesture_engine.parse_args([])[2])
        os.environ['GESTURE_FLIP'] = '0'
        self.assertFalse(gesture_engine.parse_args([])[2])

    def test_the_engine_keeps_the_setting(self):
        self.assertFalse(StubEngine(0, flip=False).flip)
        self.assertTrue(StubEngine(0, flip=True).flip)


class TestParentWatch(unittest.TestCase):
    """The daemon must not outlive the mirror that spawned it.

    Orphans were the root cause of the WinError 5 flood: the mirror only reaped
    its child in a `finally` block, which a kill or a closed terminal skips, so
    a daemon was left behind on nearly every debugging run.
    """

    def test_closing_stdin_stops_the_loop(self):
        e = StubEngine()
        e.running = True
        r, w = os.pipe()
        orig = sys.stdin
        sys.stdin = os.fdopen(r)
        try:
            e.watch_parent()
            os.close(w)                      # the mirror going away
            for _ in range(200):             # up to 2s, normally instant
                if not e.running:
                    break
                time.sleep(0.01)
            self.assertFalse(e.running,
                             'the daemon kept running after the pipe closed')
        finally:
            sys.stdin.close()
            sys.stdin = orig

    def test_an_open_pipe_leaves_the_loop_alone(self):
        e = StubEngine()
        e.running = True
        r, w = os.pipe()
        orig = sys.stdin
        sys.stdin = os.fdopen(r)
        try:
            e.watch_parent()
            time.sleep(0.1)
            self.assertTrue(e.running, 'the daemon stopped while the mirror lived')
        finally:
            os.close(w)
            sys.stdin.close()
            sys.stdin = orig


if __name__ == '__main__':
    unittest.main()
