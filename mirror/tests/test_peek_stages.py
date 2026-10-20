"""Tests for timetable/kings week switch, pinch-drag gestures, indicator bar, and state transitions.

Run from the mirror/ directory:  python -m unittest test_peek_stages
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('MIRROR_SCREENSAVER_SYNC', '0')

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
    for extra in (mirror._timetable_anim, getattr(mirror, '_kings_anim', None),
                  mirror._anim_in, mirror._anim_out, mirror._demo_anim):
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
    for anim in (mirror._timetable_anim, mirror._anim_in, mirror._anim_out, mirror._demo_anim,
                 mirror._idle_demo_anim):
        if anim is not None:
            anim.stop()
    for decoder in (mirror.demo_movie, getattr(mirror, 'idle_demo_movie', None)):
        if decoder is not None:
            decoder.shutdown()
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


def centre_of(mirror, widget):
    """hand_x / hand_y pointing at the middle of `widget` as drawn."""
    pos = widget.mapTo(mirror.central_widget, widget.rect().center())
    return pos.x() / mirror.width(), pos.y() / mirror.height()


class TestKingsWeekExpandsOnTap(unittest.TestCase):
    def setUp(self):
        self.mirror = make_mirror()
        self.mirror._show_timetable(animate=False, is_initial_split=True)
        app.processEvents()

    def tearDown(self):
        close_mirror(self.mirror)

    def test_tapping_kings_week_in_the_split_view_expands_it(self):
        x, y = centre_of(self.mirror, self.mirror.kings_widget)
        self.mirror._handle_gesture(gesture(region='right', event='tap', x=x, y=y))
        settle(self.mirror)
        self.assertTrue(self.mirror._timetable_slid_away)
        self.assertEqual(self.mirror.kings_widget.geometry().top(), 0)
        self.assertEqual(self.mirror.kings_widget.height(), self.mirror.right_stack_container.height())

    def test_tapping_the_timetable_half_does_not(self):
        x, y = centre_of(self.mirror, self.mirror.timetable_widget)
        self.mirror._handle_gesture(gesture(region='right', event='tap', x=x, y=y))
        settle(self.mirror)
        self.assertFalse(self.mirror._timetable_slid_away)

    def test_the_guest_screen_expands_the_same_way(self):
        m = self.mirror
        m._transitioning = True
        m._last_state = 'guest'
        m._trigger_transition('guest', '', {'config': {}})
        settle(m)
        self.assertFalse(m._guest_card_slid_away)
        x, y = centre_of(m, m.guest_kings_widget)
        m._handle_gesture(gesture(region='right', event='tap', x=x, y=y))
        if m._guest_card_anim is not None:
            m._guest_card_anim.setCurrentTime(m._guest_card_anim.duration())
        app.processEvents()
        self.assertTrue(m._guest_card_slid_away)


class TestTutorialBackdrop(unittest.TestCase):
    def setUp(self):
        self.mirror = make_mirror()

    def tearDown(self):
        close_mirror(self.mirror)

    def test_the_tutorial_plays_over_a_blur_of_the_screen(self):
        self.mirror._show_gesture_scrim()
        backdrop = self.mirror.gesture_demo_overlay._backdrop
        self.assertIsNotNone(backdrop)
        self.assertEqual((backdrop.width(), backdrop.height()),
                         (self.mirror.central_widget.width(), self.mirror.central_widget.height()))
        settle(self.mirror)
        self.mirror._fade_out_gesture_scrim()
        settle(self.mirror)
        self.assertFalse(self.mirror.gesture_demo_overlay.isVisible())
        self.assertIsNone(self.mirror.gesture_demo_overlay._backdrop)


class TestIdleAttractLoop(unittest.TestCase):
    def setUp(self):
        self.mirror = make_mirror()
        self.mirror.user_container.hide()
        self.mirror._last_state = 'idle'
        self.mirror._last_presence_time = 0.0
        if self.mirror.idle_demo is None:
            self.skipTest('assets/gesture_demo.mp4 missing')

    def tearDown(self):
        close_mirror(self.mirror)

    def _finish_fade(self):
        anim = self.mirror._idle_demo_anim
        anim.setCurrentTime(anim.duration())
        app.processEvents()

    def test_an_empty_mirror_plays_the_demo_full_screen(self):
        self.mirror._update_idle_demo()
        demo = self.mirror.idle_demo
        self.assertEqual(self.mirror._idle_demo_phase, 'playing')
        self.assertTrue(demo.isVisible())
        self.assertEqual(demo.geometry(), self.mirror.central_widget.rect())
        self._finish_fade()
        self.assertEqual(demo.effect.opacity(), 1.0)

    def test_at_the_end_it_fades_out_waits_in_black_then_fades_back_in(self):
        self.mirror._update_idle_demo()
        self._finish_fade()
        self.mirror._on_idle_demo_finished()
        self.assertEqual(self.mirror._idle_demo_phase, 'ending')
        self.assertEqual(self.mirror._idle_demo_anim.duration(), 500)       # 0.5 s fade out
        self._finish_fade()
        self.assertEqual(self.mirror._idle_demo_phase, 'gap')               # black screen
        self.assertEqual(self.mirror.idle_demo.effect.opacity(), 0.0)
        self.assertEqual(self.mirror._idle_gap_timer.interval(), 5000)
        self.assertTrue(self.mirror._idle_gap_timer.isActive())
        self.mirror._idle_gap_timer.stop()
        self.mirror._end_idle_gap()
        self.assertEqual(self.mirror._idle_demo_phase, 'playing')
        self.assertEqual(self.mirror._idle_demo_anim.duration(), 500)       # 0.5 s fade in
        self._finish_fade()
        self.assertEqual(self.mirror.idle_demo.effect.opacity(), 1.0)

    def test_someone_arriving_during_the_black_pause_cancels_it(self):
        self.mirror._update_idle_demo()
        self._finish_fade()
        self.mirror._on_idle_demo_finished()
        self._finish_fade()
        self.mirror._handle_gesture(gesture(present=True))
        self.assertEqual(self.mirror._idle_demo_phase, 'off')
        self.assertFalse(self.mirror._idle_gap_timer.isActive())
        self.assertFalse(self.mirror.idle_demo.isVisible())

    def test_a_hand_even_briefly_fades_it_away_and_it_stays_away(self):
        self.mirror._update_idle_demo()
        self._finish_fade()
        self.mirror._handle_gesture(gesture(present=True))
        self.assertEqual(self.mirror._idle_demo_phase, 'leaving')
        self._finish_fade()
        self.assertEqual(self.mirror._idle_demo_phase, 'off')
        self.assertFalse(self.mirror.idle_demo.isVisible())
        self.mirror._update_idle_demo()                 # hand gone, but only just
        self.assertEqual(self.mirror._idle_demo_phase, 'off')

    def test_a_face_seen_between_polls_still_counts(self):
        self.mirror._update_idle_demo()
        import json, time
        with open(smp.FACE_DATA_FILE, 'w') as f:
            json.dump({'state': 'idle', 'detected': False, 'last_face_time': time.time() - 0.3,
                       'timestamp': time.time()}, f)
        self.mirror._update_inputs()
        self.assertEqual(self.mirror._idle_demo_phase, 'leaving')

    def test_it_comes_back_once_nobody_has_been_seen_for_a_while(self):
        import time
        self.mirror._last_presence_time = time.time() - smp.IDLE_DEMO_RESUME_SEC - 0.1
        self.mirror._update_idle_demo()
        self.assertEqual(self.mirror._idle_demo_phase, 'playing')

    def test_it_never_plays_over_a_signed_in_user(self):
        self.mirror._last_state = 'user'
        self.mirror._update_idle_demo()
        self.assertEqual(self.mirror._idle_demo_phase, 'off')


class TestMirrorNotice(unittest.TestCase):
    def setUp(self):
        self.mirror = make_mirror()

    def tearDown(self):
        close_mirror(self.mirror)

    def test_the_notice_shows_for_users_and_guests_styled_by_level(self):
        m = self.mirror
        m._update_banner({"message": "Fire drill at 2pm", "level": "urgent"})
        self.assertTrue(m.banner_frame.isVisible())
        self.assertEqual(m.tag_lbl.text(), "URGENT")
        self.assertEqual(m.banner_label.text(), "Fire drill at 2pm")
        self.assertGreaterEqual(m.user_container.y(), m.banner_frame.geometry().bottom())  # no overlap

        m._transitioning = True
        m._last_state = 'guest'
        m._trigger_transition('guest', '', {'config': {}})
        settle(m)
        self.assertTrue(m.banner_frame.isVisible())

        m._update_banner({"message": "Library closed", "level": "warning"})
        self.assertEqual(m.tag_lbl.text(), "WARNING")

    def test_it_is_hidden_while_the_mirror_is_idle_and_when_cleared(self):
        m = self.mirror
        m._update_banner({"message": "Hello", "level": "notice"})
        m._transitioning = True
        m._last_state = 'idle'
        m._trigger_transition('idle', 'idle', {})
        self.assertFalse(m.banner_frame.isVisible())
        m._last_state = 'user'
        m._refresh_banner()
        self.assertTrue(m.banner_frame.isVisible())
        m._update_banner({"message": "", "level": "notice"})
        self.assertFalse(m.banner_frame.isVisible())
