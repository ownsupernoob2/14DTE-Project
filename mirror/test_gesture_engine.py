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
    SCROLL_DEADZONE, HEARTBEAT_SEC, POSITION_QUANTUM,
    classify_region,
)


class _P:
    """Stand-in for a mediapipe NormalizedLandmark."""

    def __init__(self, x, y, z=0.0):
        self.x, self.y, self.z = x, y, z


def make_hand(px, py, closed=False, pinch=False):
    """21 landmarks whose palm centre is exactly (px, py).

    closed=True tucks the finger tips below their knuckles (no scroll control);
    pinch=True brings the thumb tip onto the index tip.
    """
    lm = [_P(px, py) for _ in range(21)]
    tip_y = py + 0.1 if closed else py - 0.1
    for tip in (8, 12, 16, 20):
        lm[tip] = _P(px, tip_y)
    # Thumb tip: on the index tip for a pinch, well clear of it otherwise.
    lm[4] = _P(px + 0.02, tip_y) if pinch else _P(px + 0.3, py)
    return lm


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


class TestScroll(unittest.TestCase):
    def setUp(self):
        self.e = StubEngine()

    def test_first_frame_only_anchors(self):
        # Arriving in a region must not emit a jump the size of the hand's entry.
        self.assertIsNone(self.e.process_landmarks(make_hand(0.2, 0.5), 1000.0))
        self.assertTrue(self.e.engaged)

    def test_open_palm_down_scrolls_down(self):
        self.e.process_landmarks(make_hand(0.2, 0.5), 1000.0)
        event = self.e.process_landmarks(make_hand(0.2, 0.56), 1000.1)
        self.assertEqual(event, "scroll")
        self.assertGreater(self.e.scroll_delta, 0)

    def test_open_palm_up_scrolls_up(self):
        self.e.process_landmarks(make_hand(0.2, 0.5), 1000.0)
        event = self.e.process_landmarks(make_hand(0.2, 0.44), 1000.1)
        self.assertEqual(event, "scroll")
        self.assertLess(self.e.scroll_delta, 0)

    def test_jitter_inside_deadzone_does_not_scroll(self):
        self.e.process_landmarks(make_hand(0.2, 0.5), 1000.0)
        tiny = SCROLL_DEADZONE / 2
        event = self.e.process_landmarks(make_hand(0.2, 0.5 + tiny), 1000.1)
        self.assertIsNone(event)
        self.assertEqual(self.e.scroll_delta, 0)

    def test_closed_hand_does_not_scroll(self):
        # A hand just resting or gesturing at someone shouldn't move the list.
        self.e.process_landmarks(make_hand(0.2, 0.5, closed=True), 1000.0)
        event = self.e.process_landmarks(make_hand(0.2, 0.7, closed=True), 1000.1)
        self.assertIsNone(event)
        self.assertFalse(self.e.engaged)

    def test_region_change_reanchors(self):
        # Sweeping across columns must not dump one huge scroll into the new one.
        self.e.process_landmarks(make_hand(0.2, 0.2), 1000.0)
        event = self.e.process_landmarks(make_hand(0.5, 0.9), 1000.1)
        self.assertIsNone(event)
        self.assertEqual(self.e.region, REGION_CENTER)

    def test_scroll_is_clamped(self):
        self.e.process_landmarks(make_hand(0.2, 0.05), 1000.0)
        self.e.process_landmarks(make_hand(0.2, 0.95), 1000.1)
        self.assertLessEqual(abs(self.e.scroll_delta), gesture_engine.SCROLL_MAX_PX)


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
        self.assertIsNone(self.e.process_landmarks(make_hand(0.8, 0.5), 1000.0))
        event = self.e.process_landmarks(make_hand(0.8, 0.5), 1000.0 + RIGHT_DWELL_SEC + 0.05)
        self.assertEqual(event, "enter_right")
        # Leaving the hand there must not re-trigger the peek every frame.
        for i in range(5):
            self.assertIsNone(self.e.process_landmarks(make_hand(0.8, 0.5), 1001.0 + i * 0.1))

    def test_passing_through_quickly_does_not_fire(self):
        self.e.process_landmarks(make_hand(0.8, 0.5), 1000.0)
        event = self.e.process_landmarks(make_hand(0.8, 0.5), 1000.0 + RIGHT_DWELL_SEC / 2)
        self.assertIsNone(event)

    def test_leaving_and_returning_rearms(self):
        self.e.process_landmarks(make_hand(0.8, 0.5), 1000.0)
        self.assertEqual(
            self.e.process_landmarks(make_hand(0.8, 0.5), 1000.5), "enter_right"
        )
        self.e.process_landmarks(make_hand(0.2, 0.5), 1001.0)   # back to notices
        self.e.process_landmarks(make_hand(0.8, 0.5), 1002.0)   # returns to right
        self.assertEqual(
            self.e.process_landmarks(make_hand(0.8, 0.5), 1002.5), "enter_right"
        )

    def test_hand_lost_rearms(self):
        self.e.process_landmarks(make_hand(0.8, 0.5), 1000.0)
        self.e.process_landmarks(make_hand(0.8, 0.5), 1000.5)
        self.assertFalse(self.e.right_armed)
        self.assertTrue(self.e.mark_absent(1000.5 + HAND_LOST_SEC + 0.1))
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
        self.assertFalse(self.e.engaged)

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
        self.e.process_landmarks(make_hand(0.8, 0.2), 1000.0)
        self.e.write_status()
        before = self._read()['seq']
        self.e.process_landmarks(make_hand(0.8, 0.2 + POSITION_QUANTUM / 8), 1000.1)
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
        camera, _ = gesture_engine.parse_args(['--rpi'])
        self.assertEqual(camera, gesture_engine.RPI_CAMERA)

    def test_a_webcam_index_comes_back_as_an_int(self):
        camera, _ = gesture_engine.parse_args(['--camera-id', '4'])
        self.assertEqual(camera, 4)

    def test_the_default_is_the_first_webcam(self):
        camera, _ = gesture_engine.parse_args([])
        self.assertEqual(camera, 0)

    def test_exiting_with_the_parent_is_opt_in(self):
        # Run by hand from a terminal, stdin is the keyboard and reading it would
        # block forever; only the mirror, which supplies a pipe, asks for this.
        self.assertFalse(gesture_engine.parse_args([])[1])
        self.assertTrue(gesture_engine.parse_args(['--exit-with-parent'])[1])


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
