"""The reach box that follows the hand, and the "keep your palm open" hint.

No camera and no mediapipe: synthetic landmarks go straight into the engine.

Run from the mirror/ directory:  python -m unittest tests.test_gesture_box_and_palm
"""

import json
import os
import tempfile
import unittest

import gesture_engine
from gesture_engine import HAND_LOST_SEC
from tests.test_gesture_engine import FloatingStub, StubEngine, make_hand


class TestFloatingBox(unittest.TestCase):
    """The reach box is centred on the hand that takes control, then follows it."""

    def setUp(self):
        self.e = FloatingStub()
        self.w = gesture_engine.REACH_X1 - gesture_engine.REACH_X0
        self.h = gesture_engine.REACH_Y1 - gesture_engine.REACH_Y0

    def test_the_hand_that_takes_control_starts_in_the_middle_of_the_screen(self):
        for x, y in ((0.5, 0.5), (0.4, 0.45), (0.6, 0.55)):
            e = FloatingStub()
            e.process_landmarks(make_hand(x, y), 1000.0)
            self.assertAlmostEqual(e.hand_x, 0.5, places=1)
            self.assertAlmostEqual(e.hand_y, 0.5, places=1)

    def test_all_of_the_screen_is_reachable_from_where_the_hand_started(self):
        self.e.process_landmarks(make_hand(0.5, 0.5), 1000.0)
        x0, y0 = self.e.box
        self.assertEqual(self.e.to_screen(x0, y0), (0.0, 0.0))
        self.assertEqual(self.e.to_screen(x0 + self.w, y0 + self.h), (1.0, 1.0))

    def test_a_hand_at_the_edge_gets_a_box_whose_edge_is_there(self):
        self.e.process_landmarks(make_hand(0.95, 0.5), 1000.0)
        self.assertAlmostEqual(self.e.box[0] + self.w, 1.0)      # the box stops at the picture's edge
        self.assertGreater(self.e.hand_x, 0.9)                   # and the cursor is at the screen's edge
        e = FloatingStub()
        e.process_landmarks(make_hand(0.05, 0.05), 1000.0)
        self.assertEqual(e.box, (0.0, 0.0))
        self.assertLessEqual(e.hand_x, 0.11)
        self.assertLessEqual(e.hand_y, 0.11)

    def test_the_box_stays_put_while_the_hand_roams_inside_it(self):
        self.e.process_landmarks(make_hand(0.5, 0.5), 1000.0)
        box = self.e.box
        for i, x in enumerate((0.42, 0.58, 0.45, 0.55)):
            self.e.process_landmarks(make_hand(x, 0.5), 1000.1 + 0.1 * i)
        self.assertEqual(self.e.box, box)

    def test_a_hand_just_past_the_edge_pins_the_cursor_there(self):
        self.e.process_landmarks(make_hand(0.5, 0.5), 1000.0)
        box = self.e.box
        near = box[0] + self.w + gesture_engine.BOX_FOLLOW_MARGIN / 2
        self.e.process_landmarks(make_hand(near, 0.5), 1000.1)
        self.assertEqual(self.e.box, box)
        self.assertAlmostEqual(self.e.hand_x, 1.0, places=1)

    def test_a_hand_pushed_well_past_the_edge_drags_the_box_along(self):
        self.e.process_landmarks(make_hand(0.5, 0.5), 1000.0)
        box = self.e.box
        far = box[0] + self.w + 0.10
        self.e.process_landmarks(make_hand(far, 0.5), 1000.1)
        self.assertGreater(self.e.box[0], box[0])
        # the hand is held just past the new edge, so coming back moves the cursor at once
        past = far - (self.e.box[0] + self.w)
        self.assertGreaterEqual(past, 0.0)
        self.assertLessEqual(past, gesture_engine.BOX_FOLLOW_MARGIN + 1e-9)

    def test_the_box_never_leaves_the_camera_picture(self):
        self.e.process_landmarks(make_hand(0.5, 0.5), 1000.0)
        moves = ((0.99, 0.5), (0.99, 0.99), (0.01, 0.99), (0.01, 0.01), (0.99, 0.01))
        for i, (x, y) in enumerate(moves):
            self.e.process_landmarks(make_hand(x, y), 1000.1 + 0.1 * i)
            x0, y0 = self.e.box
            self.assertGreaterEqual(x0, 0.0)
            self.assertGreaterEqual(y0, 0.0)
            self.assertLessEqual(x0 + self.w, 1.0 + 1e-9)
            self.assertLessEqual(y0 + self.h, 1.0 + 1e-9)

    def test_losing_the_hand_forgets_the_box(self):
        self.e.process_landmarks(make_hand(0.3, 0.4), 1000.0)
        self.assertIsNotNone(self.e.box)
        self.e.mark_absent(1000.0 + HAND_LOST_SEC + 0.1)
        self.assertIsNone(self.e.box)
        self.e.process_landmarks(make_hand(0.7, 0.6), 1002.0)
        self.assertAlmostEqual(self.e.hand_x, 0.5, places=1)     # a new hand starts in the middle again

    def test_the_old_fixed_box_can_still_be_asked_for(self):
        e = StubEngine()                  # fixed_box on
        e.process_landmarks(make_hand(0.5, 0.5), 1000.0)
        self.assertIsNone(e.box)
        expected = gesture_engine.to_screen(*e._palm_center(make_hand(0.5, 0.5)))
        self.assertEqual((e.hand_x, e.hand_y), expected)

    def test_a_hand_low_in_the_picture_is_not_picked(self):
        low = make_hand(0.5, gesture_engine.IGNORE_BELOW_Y + 0.05)
        self.assertEqual(self.e.select_best_hand([low]), (None, None))
        ok = make_hand(0.5, 0.6)
        self.assertIs(self.e.select_best_hand([ok])[0], ok)


class TestPalmHint(unittest.TestCase):
    """Say how to hold the hand when it is in view but not open."""

    def setUp(self):
        self.e = StubEngine()
        self.fist = make_hand(0.5, 0.5, closed=True)
        self.palm = make_hand(0.5, 0.5)

    def feed(self, lm, t0, secs, step=0.05):
        t = t0
        while t < t0 + secs:
            if lm is not None:
                self.e.update_engagement(lm, None, t)
            self.e.update_palm_hint(lm, None, t)
            t += step
        return t

    def test_no_hint_for_an_open_palm(self):
        self.feed(self.palm, 1000.0, 2.0)
        self.assertFalse(self.e.palm_hint)

    def test_fingers_folded_down_gets_a_hint_after_a_moment(self):
        self.e.update_palm_hint(self.fist, None, 1000.0)
        self.assertFalse(self.e.palm_hint)                      # not at the first glimpse
        self.feed(self.fist, 1000.0, gesture_engine.PALM_HINT_SEC + 0.2)
        self.assertTrue(self.e.palm_hint)

    def test_it_stays_up_briefly_then_clears_once_the_palm_is_open(self):
        t = self.feed(self.fist, 1000.0, 1.0)
        self.assertTrue(self.e.palm_hint)
        self.e.update_engagement(self.palm, None, t)
        self.e.update_palm_hint(self.palm, None, t + 0.1)
        self.assertTrue(self.e.palm_hint)                       # held, so it doesn't flicker
        self.e.update_palm_hint(self.palm, None, t + gesture_engine.PALM_HINT_HOLD_SEC + 0.3)
        self.assertFalse(self.e.palm_hint)

    def test_a_hand_already_in_control_with_fingers_down_still_gets_the_hint(self):
        self.e.update_engagement(self.palm, None, 1000.0)
        self.e.update_engagement(self.palm, None, 1000.2)
        self.assertTrue(self.e.engaged)
        self.feed(self.fist, 1001.0, 1.0)
        self.assertTrue(self.e.palm_hint)

    def test_a_real_pinch_with_the_other_fingers_up_is_fine(self):
        self.e.update_engagement(self.palm, None, 1000.0)
        self.e.update_engagement(self.palm, None, 1000.2)
        self.feed(make_hand(0.5, 0.5, pinch=True), 1001.0, 1.5)
        self.assertFalse(self.e.palm_hint)

    def test_no_hand_no_hint(self):
        self.feed(self.fist, 1000.0, 1.0)
        self.assertTrue(self.e.palm_hint)
        self.e.update_palm_hint(None, None, 1000.0 + 5.0)
        self.assertFalse(self.e.palm_hint)

    def test_the_back_of_a_hand_gets_the_hint_too(self):
        self.e._saw_backhand = True
        t = 1000.0
        while t < 1000.0 + gesture_engine.PALM_HINT_SEC + 0.2:
            self.e.update_palm_hint(None, None, t)
            t += 0.05
        self.assertTrue(self.e.palm_hint)

    def test_the_hint_is_published_to_the_mirror(self):
        sent = []

        class Sock:
            def sendto(self, data, addr):
                sent.append(json.loads(data))

        folder = tempfile.mkdtemp()
        self.e._udp_sock = Sock()
        self.e._tmp_file = os.path.join(folder, 'g.tmp')
        saved = gesture_engine.GESTURE_STATUS_FILE
        gesture_engine.GESTURE_STATUS_FILE = os.path.join(folder, 'g.json')
        self.addCleanup(setattr, gesture_engine, 'GESTURE_STATUS_FILE', saved)
        self.e.palm_hint = True
        self.e.write_status(force=True)
        self.assertTrue(sent[-1]['palm_hint'])
        self.e.palm_hint = False
        self.e.write_status(force=True)
        self.assertFalse(sent[-1]['palm_hint'])


class TestTooCloseBeforeControl(unittest.TestCase):
    """A hand pushed out towards the camera is flagged whether or not it is in control."""

    def setUp(self):
        self.e = StubEngine()
        self.e.write_status = lambda *a, **k: None

    def run_frames(self, lm, t0, secs, step=0.05):
        t = t0
        while t < t0 + secs:
            self.e.step(lm, None, t)
            t += step
        return t

    def test_a_big_hand_that_has_not_taken_control_is_still_flagged(self):
        fist = make_hand(0.5, 0.5, closed=True, scale=0.32)          # not held up open, and much too big
        self.run_frames(fist, 1000.0, gesture_engine.TOO_CLOSE_SEC + 0.3)
        self.assertFalse(self.e.engaged)
        self.assertTrue(self.e.too_close)

    def test_an_open_hand_at_a_normal_distance_is_not(self):
        t = self.run_frames(make_hand(0.5, 0.5), 1000.0, 2.0)
        self.assertTrue(self.e.engaged)
        self.assertFalse(self.e.too_close)

    def test_the_flag_clears_when_the_hand_goes(self):
        t = self.run_frames(make_hand(0.5, 0.5, scale=0.32), 1000.0, 1.0)
        self.assertTrue(self.e.too_close)
        self.run_frames(None, t + HAND_LOST_SEC + 0.1, 0.2)
        self.assertFalse(self.e.too_close)


class TestRaiseHint(unittest.TestCase):
    """A hand held so low it is cut off by the bottom of the camera picture."""

    def setUp(self):
        self.e = StubEngine()
        self.cut = make_hand(0.5, 0.80, scale=0.3)       # low, fingers off the bottom edge
        self.ok = make_hand(0.5, 0.4)

    def feed(self, lm, t0, secs, step=0.05):
        t = t0
        while t < t0 + secs:
            self.e.update_raise_hint(lm, t)
            t += step
        return t

    def test_a_cut_off_low_hand_gets_the_hint_after_a_moment(self):
        self.e.update_raise_hint(self.cut, 1000.0)
        self.assertFalse(self.e.raise_hint)
        self.feed(self.cut, 1000.0, gesture_engine.RAISE_HINT_SEC + 0.2)
        self.assertTrue(self.e.raise_hint)

    def test_a_hand_held_up_in_view_does_not(self):
        self.feed(self.ok, 1000.0, 2.0)
        self.assertFalse(self.e.raise_hint)

    def test_it_clears_once_the_hand_is_raised(self):
        t = self.feed(self.cut, 1000.0, 1.0)
        self.assertTrue(self.e.raise_hint)
        self.feed(self.ok, t, gesture_engine.RAISE_HINT_HOLD_SEC + 0.4)
        self.assertFalse(self.e.raise_hint)

    def test_a_hand_too_low_to_be_followed_still_asks_to_be_raised(self):
        low = make_hand(0.5, gesture_engine.IGNORE_BELOW_Y + 0.05)
        self.assertEqual(self.e.select_best_hand([low]), (None, None))
        t = 1000.0
        while t < 1000.0 + gesture_engine.RAISE_HINT_SEC + 0.2:
            self.e.update_raise_hint(None, t)
            t += 0.05
        self.assertTrue(self.e.raise_hint)
        self.e.select_best_hand([make_hand(0.5, 0.4)])
        self.e.update_raise_hint(None, 1010.0)
        self.assertFalse(self.e.raise_hint)

    def test_it_is_published(self):
        sent = []

        class Sock:
            def sendto(self, data, addr):
                sent.append(json.loads(data))

        folder = tempfile.mkdtemp()
        self.e._udp_sock = Sock()
        self.e._tmp_file = os.path.join(folder, 'g.tmp')
        saved = gesture_engine.GESTURE_STATUS_FILE
        gesture_engine.GESTURE_STATUS_FILE = os.path.join(folder, 'g.json')
        self.addCleanup(setattr, gesture_engine, 'GESTURE_STATUS_FILE', saved)
        self.e.raise_hint = True
        self.e.write_status(force=True)
        self.assertTrue(sent[-1]['raise_hint'])


if __name__ == '__main__':
    unittest.main()
