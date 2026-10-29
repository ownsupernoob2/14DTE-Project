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
    DRAG_TAP_THRESHOLD, classify_region, default_flip,
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


def full_frame_reach(test):
    """Map the whole camera image to the screen, so positions read back as given."""
    saved = (gesture_engine.REACH_X0, gesture_engine.REACH_X1, gesture_engine.REACH_Y0, gesture_engine.REACH_Y1)
    gesture_engine.REACH_X0, gesture_engine.REACH_X1, gesture_engine.REACH_Y0, gesture_engine.REACH_Y1 = 0.0, 1.0, 0.0, 1.0

    def restore():
        (gesture_engine.REACH_X0, gesture_engine.REACH_X1,
         gesture_engine.REACH_Y0, gesture_engine.REACH_Y1) = saved
    test.addCleanup(restore)


class StubEngine(GestureEngine):
    def _init_tracker(self):
        self.fixed_box = True       # most tests read positions back through the one fixed box
        pass  # no mediapipe, no camera


class FloatingStub(StubEngine):
    """As the mirror runs: the reach box is centred on the hand, then follows it."""
    def _init_tracker(self):
        self.fixed_box = False


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
        self.e.process_landmarks(make_hand(0.85, 0.12, pinch=False), 1000.0)
        self.assertEqual(self.e.right_dwell_progress, 0.0)
        self.e.process_landmarks(make_hand(0.85, 0.12, pinch=False), 1000.0 + RIGHT_DWELL_SEC / 2)
        self.assertAlmostEqual(self.e.right_dwell_progress, 0.5, places=2)
        event = self.e.process_landmarks(make_hand(0.85, 0.12, pinch=False), 1000.0 + RIGHT_DWELL_SEC + 0.05)
        self.assertEqual(event, "enter_right")
        self.assertEqual(self.e.right_dwell_progress, 1.0)


class TestClickReliability(unittest.TestCase):
    """A pinch someone means as a click must register as one."""

    def setUp(self):
        self.e = StubEngine()

    def pinch(self, ys, step=1 / 16):
        t, events = 1000.0, []
        self.e.process_landmarks(make_hand(0.2, 0.5), t)
        for y in ys:
            t += step
            events.append(self.e.process_landmarks(make_hand(0.2, y, pinch=True), t))
        t += step
        events.append(self.e.process_landmarks(make_hand(0.2, ys[-1]), t))
        return [e for e in events if e]

    def test_a_pinch_with_normal_hand_wobble_still_clicks(self):
        wobble = [0.5 + (0.006 if i % 2 else -0.006) for i in range(8)]   # 0.5 s of jitter
        self.assertEqual(self.pinch(wobble), ["tap"])

    def test_a_slower_half_second_pinch_clicks(self):
        self.assertEqual(self.pinch([0.5] * 8), ["tap"])                  # 0.5 s held

    def test_a_pinch_held_too_long_is_not_a_click(self):
        self.assertEqual(self.pinch([0.5] * 14), [])                      # ~0.9 s

    def test_a_real_drag_scrolls_and_never_clicks(self):
        events = self.pinch([0.5, 0.48, 0.45, 0.42, 0.39, 0.36])
        self.assertIn("scroll", events)
        self.assertNotIn("tap", events)

    def test_the_first_scroll_carries_the_travel_that_started_it(self):
        self.e.process_landmarks(make_hand(0.2, 0.5, pinch=True), 1000.0)
        self.e.process_landmarks(make_hand(0.2, 0.47, pinch=True), 1000.06)   # under threshold
        self.e.process_landmarks(make_hand(0.2, 0.45, pinch=True), 1000.12)   # crosses it
        # 0.05 of travel so far, not just the last 0.02.
        self.assertGreater(self.e.scroll_delta, int(0.04 * gesture_engine.DRAG_SCROLL_GAIN))


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
        for i in range(6):
            wobble = self._hand_with_gap_ratio(PINCH_ENTER_RATIO - 0.01 * (i % 2))
            self.assertIsNone(self.e.process_landmarks(wobble, t + 0.02 * (i + 1)))
        self.assertEqual(self.e.process_landmarks(make_hand(0.2, 0.5), t + 0.3), "tap")

    def test_parting_the_fingers_slightly_lets_go(self):
        # People found they had to open their hand wide before a pinch let go.
        # After a firm pinch, a small parting releases it (and clicks).
        t = 1000.0
        self.e.process_landmarks(self._hand_with_gap_ratio(0.12), t)
        self.e.process_landmarks(self._hand_with_gap_ratio(0.14), t + 0.05)
        self.assertEqual(self.e.process_landmarks(self._hand_with_gap_ratio(0.29), t + 0.1), "tap")

    def test_a_loose_pinch_still_has_room_to_wobble(self):
        t = 1000.0
        self.e.process_landmarks(self._hand_with_gap_ratio(0.25), t)
        self.assertIsNone(self.e.process_landmarks(self._hand_with_gap_ratio(0.33), t + 0.05))
        self.assertTrue(self.e.pinched)
        self.assertEqual(self.e.process_landmarks(self._hand_with_gap_ratio(0.40), t + 0.1), "tap")

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
        self.assertIsNone(self.e.process_landmarks(make_hand(0.85, 0.12), 1000.0))
        event = self.e.process_landmarks(make_hand(0.85, 0.12), 1000.0 + RIGHT_DWELL_SEC + 0.05)
        self.assertEqual(event, "enter_right")
        # Leaving the hand there must not re-trigger the peek every frame.
        for i in range(5):
            self.assertIsNone(self.e.process_landmarks(make_hand(0.85, 0.12), 1002.0 + i * 0.1))

    def test_passing_through_quickly_does_not_fire(self):
        self.e.process_landmarks(make_hand(0.85, 0.12), 1000.0)
        event = self.e.process_landmarks(make_hand(0.85, 0.12), 1000.0 + RIGHT_DWELL_SEC / 2)
        self.assertIsNone(event)

    def test_leaving_and_returning_rearms(self):
        self.e.process_landmarks(make_hand(0.85, 0.12), 1000.0)
        self.assertEqual(
            self.e.process_landmarks(make_hand(0.85, 0.12), 1000.0 + RIGHT_DWELL_SEC + 0.05), "enter_right"
        )
        self.e.process_landmarks(make_hand(0.2, 0.5), 1002.0)   # back to notices
        self.e.process_landmarks(make_hand(0.85, 0.12), 1003.0)   # returns to right
        self.assertEqual(
            self.e.process_landmarks(make_hand(0.85, 0.12), 1003.0 + RIGHT_DWELL_SEC + 0.05), "enter_right"
        )

    def test_hand_lost_rearms(self):
        self.e.process_landmarks(make_hand(0.85, 0.12), 1000.0)
        self.e.process_landmarks(make_hand(0.85, 0.12), 1000.0 + RIGHT_DWELL_SEC + 0.05)
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
        self.e.process_landmarks(make_hand(0.85, 0.12), 1000.0)
        self.e.process_landmarks(make_hand(0.85, 0.12), 1000.0 + RIGHT_DWELL_SEC + 0.05)
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
        full_frame_reach(self)
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, 'gesture_status.json')
        self._orig = gesture_engine.GESTURE_STATUS_FILE
        gesture_engine.GESTURE_STATUS_FILE = self.path
        # The file is a fallback, normally refreshed only every half second;
        # these tests are about what is published, so write every change.
        self._every = gesture_engine.STATUS_FILE_EVERY
        gesture_engine.STATUS_FILE_EVERY = 0.0
        self.e = StubEngine()

    def tearDown(self):
        gesture_engine.GESTURE_STATUS_FILE = self._orig
        gesture_engine.STATUS_FILE_EVERY = self._every

    def test_the_file_is_only_refreshed_now_and_then(self):
        gesture_engine.STATUS_FILE_EVERY = 60.0
        self.e.process_landmarks(make_hand(0.2, 0.5), 1000.0)
        self.e.write_status(force=True)
        first = self._read()['seq']
        self.e.process_landmarks(make_hand(0.8, 0.5), 1000.1)
        self.e.write_status()                       # sent over UDP, not to disk
        self.assertEqual(self._read()['seq'], first)
        self.e.write_status(event="tap")            # events always reach the file
        self.assertEqual(self._read()['event'], "tap")

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
        real = gesture_engine.MODEL_PATH, gesture_engine.LANDMARKER_PATH
        missing = os.path.join(tempfile.gettempdir(), 'definitely-not-a-model.task')
        gesture_engine.MODEL_PATH = gesture_engine.LANDMARKER_PATH = missing
        try:
            engine = GestureEngine()      # must not raise
            self.assertIsNone(engine.tracker)
        finally:
            gesture_engine.MODEL_PATH, gesture_engine.LANDMARKER_PATH = real

    def test_the_hand_landmarker_is_preferred(self):
        if gesture_engine.mp is None or not os.path.exists(gesture_engine.LANDMARKER_PATH):
            self.skipTest('mediapipe or hand_landmarker.task missing')
        engine = GestureEngine()
        try:
            self.assertEqual(type(engine.tracker).__name__, 'HandLandmarker')
        finally:
            engine.tracker.close()


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

    def test_parse_camera_target(self):
        self.assertEqual(gesture_engine._parse_camera_target("/dev/video10"), 10)
        self.assertEqual(gesture_engine._parse_camera_target("/dev/video0"), 0)
        self.assertEqual(gesture_engine._parse_camera_target(4), 4)
        self.assertEqual(gesture_engine._parse_camera_target("4"), 4)
        self.assertEqual(gesture_engine._parse_camera_target("rtsp://stream"), "rtsp://stream")


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

    def test_default_flip_defaults_to_true(self):
        # By default, frame mirroring is enabled so moving hand left moves left on the mirror screen.
        self.assertTrue(default_flip())

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


class _Cat:
    """Stand-in for a mediapipe handedness Category."""

    def __init__(self, name, score=0.95):
        self.category_name = name
        self.score = score


def backhand_of(hand):
    """The same hand turned round: index and pinky knuckles swap sides."""
    back = list(hand)
    back[5], back[17] = _P(hand[17].x, hand[17].y), _P(hand[5].x, hand[5].y)
    return back


def mirrored(hand):
    return [_P(1.0 - p.x, p.y, p.z) for p in hand]


class TestBackhand(unittest.TestCase):
    # make_hand's geometry is a palm when MediaPipe labels the hand 'Left'.

    def test_a_palm_is_not_a_backhand(self):
        self.assertFalse(GestureEngine.is_backhand(make_hand(0.3, 0.5), 'Left'))

    def test_the_back_of_the_hand_is(self):
        self.assertTrue(GestureEngine.is_backhand(backhand_of(make_hand(0.3, 0.5)), 'Left'))

    def test_left_hands_are_judged_the_other_way_round(self):
        left_palm = mirrored(make_hand(0.3, 0.5))
        self.assertFalse(GestureEngine.is_backhand(left_palm, 'Right'))
        self.assertTrue(GestureEngine.is_backhand(backhand_of(left_palm), 'Right'))

    def test_mirroring_the_frame_does_not_change_the_answer(self):
        # Flipping the image flips both the geometry and MediaPipe's label.
        palm, back = make_hand(0.3, 0.5), backhand_of(make_hand(0.3, 0.5))
        self.assertFalse(GestureEngine.is_backhand(mirrored(palm), 'Right'))
        self.assertTrue(GestureEngine.is_backhand(mirrored(back), 'Right'))

    def test_an_unsure_label_never_rejects_a_hand(self):
        back = backhand_of(make_hand(0.3, 0.5))
        self.assertFalse(GestureEngine.is_backhand(back, 'Left', label_score=0.4))

    def test_facing_is_a_signed_fraction(self):
        self.assertGreater(GestureEngine.palm_facing(make_hand(0.3, 0.5), 'Left'), 0.5)
        self.assertLess(GestureEngine.palm_facing(backhand_of(make_hand(0.3, 0.5)), 'Left'), -0.5)


class TestHandSelection(unittest.TestCase):
    def setUp(self):
        self.e = StubEngine()

    def test_a_backhand_is_never_chosen(self):
        far_palm = make_hand(0.3, 0.5, scale=0.10)
        close_back = backhand_of(make_hand(0.6, 0.5, scale=0.25))
        best, _ = self.e.select_best_hand([close_back, far_palm], [[_Cat('Left')], [_Cat('Left')]])
        self.assertIs(best, far_palm)

    def test_the_closest_palm_wins(self):
        far, close = make_hand(0.3, 0.5, scale=0.10), make_hand(0.6, 0.5, scale=0.25)
        best, _ = self.e.select_best_hand([far, close], [[_Cat('Left')], [_Cat('Left')]])
        self.assertIs(best, close)

    def test_a_hand_cut_off_by_the_frame_edge_loses_to_a_whole_one(self):
        cut = make_hand(0.97, 0.5, scale=0.20)        # half of it is off the right edge
        whole = make_hand(0.4, 0.5, scale=0.18)
        best, _ = self.e.select_best_hand([cut, whole], [[_Cat('Left')], [_Cat('Left')]])
        self.assertIs(best, whole)

    def test_the_hand_in_control_keeps_it_against_a_similar_one(self):
        mine = make_hand(0.3, 0.5, scale=0.18)
        self.e.process_landmarks(mine, 1000.0)
        other = make_hand(0.7, 0.5, scale=0.19)       # a touch bigger, but not clearly
        best, _ = self.e.select_best_hand([other, mine], [[_Cat('Left')], [_Cat('Left')]])
        self.assertIs(best, mine)

    def test_a_hand_without_a_label_is_never_rejected(self):
        back = backhand_of(make_hand(0.3, 0.5))
        self.assertFalse(GestureEngine.is_backhand(back, None))
        best, _ = self.e.select_best_hand([back])
        self.assertIs(best, back)

    def test_nothing_usable_returns_none(self):
        self.assertEqual(self.e.select_best_hand([]), (None, None))
        tiny = make_hand(0.3, 0.5, scale=MIN_PALM_SIZE / 2)
        self.assertEqual(self.e.select_best_hand([tiny]), (None, None))


class TestCursorSmoothing(unittest.TestCase):
    def setUp(self):
        full_frame_reach(self)

    def test_a_resting_hand_is_steady(self):
        e = StubEngine()
        t = 1000.0
        xs = []
        for i in range(60):
            jitter = 0.004 if i % 2 else -0.004         # landmark noise at rest
            e.process_landmarks(make_hand(0.4 + jitter, 0.5), t)
            xs.append(e.hand_x)
            t += 1 / 16
        settled = xs[20:]
        self.assertLess(max(settled) - min(settled), 0.004)   # well under the raw 0.008 swing

    def test_a_fast_move_is_followed_without_lag(self):
        e = StubEngine()
        t = 1000.0
        for _ in range(10):
            e.process_landmarks(make_hand(0.2, 0.5), t)
            t += 1 / 16
        for i in range(1, 9):                           # ~1 screen width per second
            e.process_landmarks(make_hand(0.2 + i * 0.06, 0.5), t)
            t += 1 / 16
        self.assertGreater(e.hand_x, 0.2 + 8 * 0.06 - 0.06)    # within one frame's travel

    def test_losing_the_hand_restarts_the_filter(self):
        e = StubEngine()
        e.process_landmarks(make_hand(0.2, 0.5), 1000.0)
        e.mark_absent(1000.0 + HAND_LOST_SEC + 0.1)
        e.process_landmarks(make_hand(0.8, 0.5), 1001.0)
        self.assertAlmostEqual(e.hand_x, 0.8, places=3)       # no glide from the old spot


if __name__ == '__main__':
    unittest.main()


class TestEngagement(unittest.TestCase):
    """Only a hand held up like the demo takes control; scratching your head doesn't."""

    def setUp(self):
        self.e = StubEngine()

    def test_an_open_palm_engages_after_a_moment(self):
        hand = make_hand(0.5, 0.5)
        self.assertFalse(self.e.update_engagement(hand, None, 1000.0))
        self.assertTrue(self.e.update_engagement(hand, None, 1000.0 + gesture_engine.ENGAGE_SEC))

    def test_a_curled_hand_never_engages(self):
        fist = make_hand(0.5, 0.5, closed=True)
        for i in range(10):
            self.assertFalse(self.e.update_engagement(fist, None, 1000.0 + 0.05 * i))

    def test_once_engaged_any_shape_keeps_control_until_the_hand_is_lost(self):
        self.e.update_engagement(make_hand(0.5, 0.5), None, 1000.0)
        self.e.update_engagement(make_hand(0.5, 0.5), None, 1000.2)
        self.assertTrue(self.e.update_engagement(make_hand(0.5, 0.5, closed=True), None, 1000.3))
        self.e.present, self.e.last_seen = True, 1000.3
        self.e.mark_absent(1000.3 + gesture_engine.HAND_LOST_SEC + 0.01)
        self.assertFalse(self.e.engaged)

    def test_a_hand_too_close_is_flagged(self):
        big = make_hand(0.5, 0.5, scale=0.5)
        self.e.update_too_close(big, 1000.0)
        self.assertFalse(self.e.too_close)
        self.e.update_too_close(big, 1000.0 + gesture_engine.TOO_CLOSE_SEC)
        self.assertTrue(self.e.too_close)
        self.e.update_too_close(make_hand(0.5, 0.5), 1001.0)
        self.assertFalse(self.e.too_close)


class TestEngagementThroughTheFrameLoop(unittest.TestCase):
    """The real per-frame path: a held-up hand takes control after a few frames.

    (A bug reset the engage timer on every frame a hand was not yet in control,
    so no hand ever took control on the Pi.)
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = gesture_engine.GESTURE_STATUS_FILE
        gesture_engine.GESTURE_STATUS_FILE = os.path.join(self.tmp, 'g.json')
        self.e = StubEngine()

    def tearDown(self):
        gesture_engine.GESTURE_STATUS_FILE = self._orig

    def test_a_held_up_hand_takes_control_within_a_few_frames(self):
        hand = make_hand(0.4, 0.5)
        t = 1000.0
        for i in range(6):                         # ~20 fps
            self.e.step(hand, None, t + 0.05 * i)
        self.assertTrue(self.e.engaged)
        self.assertTrue(self.e.present)

    def test_a_curled_hand_never_does(self):
        fist = make_hand(0.4, 0.5, closed=True)
        for i in range(20):
            self.e.step(fist, None, 1000.0 + 0.05 * i)
        self.assertFalse(self.e.engaged)
        self.assertFalse(self.e.present)

    def test_control_ends_once_the_hand_is_gone(self):
        hand = make_hand(0.4, 0.5)
        for i in range(6):
            self.e.step(hand, None, 1000.0 + 0.05 * i)
        for i in range(20):
            self.e.step(None, None, 1000.5 + 0.05 * i)
        self.assertFalse(self.e.engaged)
        self.assertFalse(self.e.present)

    def test_a_pinch_after_taking_control_still_clicks(self):
        t = 1000.0
        for i in range(6):
            self.e.step(make_hand(0.4, 0.5), None, t + 0.05 * i)
        self.e.step(make_hand(0.4, 0.5, pinch=True), None, t + 0.35)
        self.assertEqual(self.e.step(make_hand(0.4, 0.5), None, t + 0.5), "tap")


class TestTapPosition(unittest.TestCase):
    """A tap reports where its pinch began: the hand drifts while the fingers part."""

    def test_the_tap_carries_the_pinch_start(self):
        e = StubEngine()
        t = 1000.0
        e.process_landmarks(make_hand(0.30, 0.50), t)
        e.process_landmarks(make_hand(0.30, 0.50, pinch=True), t + 0.05)
        start = (e.hand_x, e.hand_y)
        e.process_landmarks(make_hand(0.31, 0.51, pinch=True), t + 0.15)   # a small drift
        self.assertEqual(e.process_landmarks(make_hand(0.33, 0.52), t + 0.25), "tap")
        self.assertEqual(e.tap_at, start)


class TestReach(unittest.TestCase):
    """A small, low box of the camera image covers the whole screen."""

    def test_the_box_corners_reach_the_screen_corners(self):
        x0, x1, y0, y1 = (gesture_engine.REACH_X0, gesture_engine.REACH_X1,
                          gesture_engine.REACH_Y0, gesture_engine.REACH_Y1)
        self.assertEqual(gesture_engine.to_screen(x0, y0), (0.0, 0.0))
        self.assertEqual(gesture_engine.to_screen(x1, y1), (1.0, 1.0))

    def test_outside_the_box_stays_on_screen(self):
        self.assertEqual(gesture_engine.to_screen(0.0, 0.0), (0.0, 0.0))
        self.assertEqual(gesture_engine.to_screen(1.0, 1.0), (1.0, 1.0))

    def test_a_small_movement_moves_the_cursor_further(self):
        e = StubEngine()
        e.process_landmarks(make_hand(0.45, 0.5), 1000.0)
        a = e.hand_x
        e = StubEngine()
        e.process_landmarks(make_hand(0.55, 0.5), 1000.0)
        self.assertGreater(e.hand_x - a, 0.15)      # 10% of the camera, over 15% of the screen

    def test_a_drag_scrolls_as_far_as_before(self):
        # Scrolling is judged on the camera position, so it is not sped up.
        e = StubEngine()
        e.process_landmarks(make_hand(0.5, 0.5, pinch=True), 1000.0)
        e.process_landmarks(make_hand(0.5, 0.5 + DRAG_TAP_THRESHOLD * 0.8, pinch=True), 1000.05)
        self.assertEqual(e.scroll_delta, 0)

    def test_the_box_can_be_set_from_the_environment(self):
        os.environ["GESTURE_REACH"] = "0.1,0.9,0.2,0.8"
        self.addCleanup(os.environ.pop, "GESTURE_REACH")
        self.assertEqual(gesture_engine._reach_box(), (0.1, 0.9, 0.2, 0.8))
        os.environ["GESTURE_REACH"] = "nonsense"
        self.assertEqual(gesture_engine._reach_box(), (0.22, 0.78, 0.25, 0.75))
