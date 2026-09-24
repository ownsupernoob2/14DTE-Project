"""Tests for timetable/kings week switch, pinch-drag gestures, indicator bar, and state transitions.

Run from the mirror/ directory:  python -m unittest test_peek_stages
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import requests

from PyQt6.QtWidgets import QApplication


class _EmptyResponse:
    status_code = 200
    text = ''

    @staticmethod
    def json():
        return {}

    @staticmethod
    def raise_for_status():
        pass


requests.get = lambda *a, **k: _EmptyResponse()
requests.post = lambda *a, **k: _EmptyResponse()

import smart_mirror_pro as smp
from widgets import kings_week_widget as kw

kw._ImageStore.request = lambda self, url: None

app = QApplication.instance() or QApplication([])


def article(n):
    return {
        'id':            f'a{n}',
        'title':         f'Story {n}',
        'summary':       f'Summary for story {n}.',
        'body':          f'Body of story {n}.',
        'author':        'Reporter',
        'date':          '21 Aug 2026',
        'link':          f'https://hail.to/kings-high-school/article/a{n}',
        'imageUrl':      '',
        'largeImageUrl': '',
        'images':        [],
    }


def gesture(region='right', event=None, x=0.85, y=0.5, delta=0, present=True, right_dwell=0.0):
    return {
        'present':              present,
        'region':               region,
        'event':                event,
        'hand_x':               x,
        'hand_y':               y,
        'scroll_delta':         delta,
        'right_dwell_progress': right_dwell,
        'pinched':              False,
        'seq':                  1,
        'timestamp':            1.0,
    }


def settle(mirror):
    anims = []
    for extra in (mirror._timetable_anim, mirror._anim_in, mirror._anim_out, mirror._demo_anim):
        if extra is not None:
            anims.append(extra)
    if mirror.kings_widget is not None:
        anims.extend(mirror.kings_widget.modal._anim or ())
    for anim in anims:
        anim.setCurrentTime(anim.duration())
    app.processEvents()


def fire(timer):
    timer.stop()
    timer.timeout.emit()
    app.processEvents()


def make_mirror(articles=9):
    smp.FACE_DATA_FILE = os.path.join(tempfile.gettempdir(), f'mock_face_status_{os.getpid()}.json')
    if os.path.exists(smp.FACE_DATA_FILE):
        try:
            os.remove(smp.FACE_DATA_FILE)
        except OSError:
            pass
    mirror = smp.SmartMirrorPro()
    mirror.poll_timer.stop()
    mirror.gesture_timer.stop()
    mirror.banner_timer.stop()

    mirror.resize(1280, 800)
    mirror.show()
    mirror._last_state = 'user'
    mirror.current_user_id = 'u1'
    mirror._apply_user_layout(mirror.width(), mirror.height())
    mirror.user_container.show()
    app.processEvents()

    mirror._articles = [article(i) for i in range(articles)]
    return mirror


def close_mirror(mirror):
    for timer in (mirror.poll_timer, mirror.gesture_timer, mirror.banner_timer,
                  mirror.timetable_display_timer, mirror._momentum_timer):
        timer.stop()
    for anim in (mirror._timetable_anim, mirror._anim_in, mirror._anim_out, mirror._demo_anim):
        if anim is not None:
            anim.stop()
    if mirror.kings_widget is not None:
        mirror.kings_widget.reset_gesture_state()
    mirror.hide()
    mirror.deleteLater()
    app.processEvents()


class TestTimetableKingsWeekSwitch(unittest.TestCase):
    def setUp(self):
        self.mirror = make_mirror()

    def tearDown(self):
        close_mirror(self.mirror)

    def test_timetable_starts_on_top_when_user_shows(self):
        self.mirror._show_timetable(animate=False)
        self.assertFalse(self.mirror._timetable_slid_away)
        self.assertTrue(self.mirror.timetable_widget.isVisible())
        self.assertEqual(self.mirror.timetable_widget.x(), 0)

    def test_timetable_slides_out_to_left_after_timer(self):
        self.mirror._show_timetable(animate=False)
        self.assertTrue(self.mirror.timetable_display_timer.isActive())
        fire(self.mirror.timetable_display_timer)
        settle(self.mirror)
        self.assertTrue(self.mirror._timetable_slid_away)
        self.assertLess(self.mirror.timetable_widget.y(), 0)

    def test_right_dwell_fills_indicator_bar_and_reshows_timetable(self):
        # Timetable slides out
        self.mirror._slide_timetable_out(animate=False)
        self.assertTrue(self.mirror._timetable_slid_away)

        # Holding hand on top-right shows horizontal indicator bar progress
        self.mirror._handle_gesture(gesture(region='right', right_dwell=0.5))
        self.assertTrue(self.mirror.indicator_bar.isVisible())
        self.assertGreater(self.mirror.indicator_fill.width(), 0)

        # Completion of right dwell triggers enter_right and reshows timetable
        self.mirror._handle_gesture(gesture(region='right', event='enter_right', right_dwell=1.0))
        settle(self.mirror)
        self.assertFalse(self.mirror._timetable_slid_away)
        self.assertEqual(self.mirror.timetable_widget.y(), 0)
        self.assertTrue(self.mirror.timetable_display_timer.isActive())


class TestGuestRegistrationScreen(unittest.TestCase):
    def setUp(self):
        self.mirror = make_mirror()

    def tearDown(self):
        close_mirror(self.mirror)

    def test_guest_screen_shows_registration_prompt(self):
        self.mirror._transitioning = True
        self.mirror._last_state = 'guest'
        self.mirror._trigger_transition('guest', '', {'config': {}})
        settle(self.mirror)
        self.assertTrue(self.mirror.guest_container.isVisible())
        self.assertTrue(self.mirror.guest_register_card.isVisible())

    def test_inactivity_darkened_overlay_shows_after_timeout(self):
        self.mirror._last_activity_time = 0.0
        self.mirror._update_inputs()
        self.assertTrue(self.mirror.gesture_demo_overlay.isVisible())


class TestPinchDragAndMomentum(unittest.TestCase):
    def setUp(self):
        self.mirror = make_mirror()

    def tearDown(self):
        close_mirror(self.mirror)

    def test_drag_scroll_moves_notices(self):
        self.mirror.notices_widget.cards_container.setFixedHeight(2000)
        app.processEvents()
        sb = self.mirror.notices_widget.scroll_area.verticalScrollBar()
        initial_val = sb.value()
        self.mirror._handle_gesture(gesture(region='left', event='scroll', delta=30))
        new_val = sb.value()
        self.assertEqual(new_val, initial_val + 30)

    def test_fling_starts_momentum(self):
        self.mirror._handle_gesture(gesture(region='left', event='fling', delta=40))
        self.assertTrue(self.mirror._momentum_timer.isActive())
        self.assertGreater(self.mirror._momentum_velocity, 0)
        # Advance momentum tick
        self.mirror._momentum_tick()
        self.assertLess(self.mirror._momentum_velocity, 40.0)


class TestStateTransition(unittest.TestCase):
    def setUp(self):
        self.mirror = make_mirror()

    def tearDown(self):
        close_mirror(self.mirror)

    def _transition(self, state, user_id='u2'):
        self.mirror._transitioning = True
        self.mirror._last_state = state
        self.mirror._trigger_transition(state, user_id, {'config': {}})

    def _opacity(self, widget):
        effect = widget.graphicsEffect()
        return 1.0 if effect is None else effect.opacity()

    def test_the_screen_never_goes_dark_between_states(self):
        self._transition('guest')
        self.assertIsNotNone(self.mirror._anim_in)
        self.mirror._anim_in.setCurrentTime(self.mirror._anim_in.duration() // 2)
        app.processEvents()

        self.assertTrue(self.mirror.user_container.isVisible())
        self.assertEqual(self._opacity(self.mirror.user_container), 1.0)
        self.assertTrue(self.mirror.guest_container.isVisible())
        self.assertGreater(self._opacity(self.mirror.guest_container), 0.0)

    def test_one_crossing_is_one_animation(self):
        self.mirror._anim_out = None
        self._transition('guest')
        self.assertIsNone(self.mirror._anim_out)

    def test_the_old_screen_is_retired_once_the_new_one_has_arrived(self):
        self._transition('guest')
        settle(self.mirror)
        self.assertFalse(self.mirror.user_container.isVisible())
        self.assertTrue(self.mirror.guest_container.isVisible())
        self.assertEqual(self._opacity(self.mirror.guest_container), 1.0)
        self.assertFalse(self.mirror._transitioning)

    def test_the_arriving_screen_dissolves_in_over_the_departing_one(self):
        self._transition('guest')
        children = self.mirror.central_widget.children()
        self.assertLess(children.index(self.mirror.user_container),
                        children.index(self.mirror.guest_container))

    def test_the_banner_and_status_dot_stay_on_top(self):
        self._transition('guest')
        children = self.mirror.central_widget.children()
        self.assertLess(children.index(self.mirror.guest_container),
                        children.index(self.mirror.status_dot))

    def test_idle_fades_to_black_and_clears_both_screens(self):
        self._transition('idle')
        self.assertIsNotNone(self.mirror._anim_out)
        settle(self.mirror)
        self.assertFalse(self.mirror.user_container.isVisible())
        self.assertFalse(self.mirror.guest_container.isVisible())
