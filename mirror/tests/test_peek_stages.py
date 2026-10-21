"""Tests for timetable/kings week switch, pinch-drag gestures, indicator bar, and state transitions.

Run from the mirror/ directory:  python -m unittest test_peek_stages
"""

import os
os.environ.setdefault('MIRROR_LOG_FORWARD', '0')
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('MIRROR_SCREENSAVER_SYNC', '0')

import requests

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF
import time


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
    mirror.gesture_receiver.stop()
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

    def _run_scroller(self, seconds):
        import time as _t
        end = _t.monotonic() + seconds
        while _t.monotonic() < end and self.mirror._momentum_timer.isActive():
            _t.sleep(0.016)
            self.mirror._momentum_tick()

    def test_drag_scroll_glides_the_notices_by_the_full_amount(self):
        self.mirror.notices_widget.cards_container.setFixedHeight(2000)
        app.processEvents()
        sb = self.mirror.notices_widget.scroll_area.verticalScrollBar()
        start = sb.value()
        self.mirror._handle_gesture(gesture(region='left', event='scroll', delta=30))
        self.assertLess(sb.value(), start + 30)              # not a jump...
        self.mirror._momentum_tick()
        self._run_scroller(0.6)
        self.assertEqual(sb.value(), start + 30)             # ...but it all arrives
        self.assertFalse(self.mirror._momentum_timer.isActive())

    def test_scroll_updates_glide_in_small_steps(self):
        self.mirror.notices_widget.cards_container.setFixedHeight(3000)
        app.processEvents()
        sb = self.mirror.notices_widget.scroll_area.verticalScrollBar()
        steps, last = [], sb.value()
        self.mirror._handle_gesture(gesture(region='left', event='scroll', delta=60))
        import time as _t
        for _ in range(12):
            _t.sleep(0.016)
            self.mirror._momentum_tick()
            steps.append(sb.value() - last)
            last = sb.value()
        self.assertTrue(all(st < 40 for st in steps))         # many small moves
        self.assertGreater(sum(1 for st in steps if st > 0), 4)

    def test_fling_coasts_and_slows_down(self):
        self.mirror.notices_widget.cards_container.setFixedHeight(5000)
        app.processEvents()
        sb = self.mirror.notices_widget.scroll_area.verticalScrollBar()
        start = sb.value()
        self.mirror._handle_gesture(gesture(region='left', event='fling', delta=40))
        self.assertTrue(self.mirror._momentum_timer.isActive())
        v0 = self.mirror._momentum_velocity
        self.assertGreater(v0, 0)
        import time as _t
        _t.sleep(0.05)
        self.mirror._momentum_tick()
        self.assertLess(self.mirror._momentum_velocity, v0)
        self._run_scroller(3.0)
        self.assertGreater(sb.value(), start + 200)
        self.assertFalse(self.mirror._momentum_timer.isActive())

    def test_grabbing_again_stops_a_fling(self):
        self.mirror.notices_widget.cards_container.setFixedHeight(5000)
        app.processEvents()
        self.mirror._handle_gesture(gesture(region='left', event='fling', delta=40))
        self.mirror._handle_gesture(gesture(region='left', event='scroll', delta=5))
        self.assertEqual(self.mirror._momentum_velocity, 0.0)


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


class TestTutorialOverlay(unittest.TestCase):
    def setUp(self):
        self.mirror = make_mirror()

    def tearDown(self):
        close_mirror(self.mirror)

    def test_the_tutorial_plays_over_a_dark_overlay_and_fades_away(self):
        self.mirror._show_gesture_scrim()
        settle(self.mirror)
        self.assertTrue(self.mirror.gesture_demo_overlay.isVisible())
        corner = self.mirror.gesture_demo_overlay.grab().toImage().pixelColor(2, 2)
        self.assertLess(corner.lightness(), 40)
        self.mirror._fade_out_gesture_scrim()
        settle(self.mirror)
        self.assertFalse(self.mirror.gesture_demo_overlay.isVisible())


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

    def test_a_long_notice_makes_the_banner_taller_without_overlap(self):
        m = self.mirror
        m._update_banner({"message": "Short", "level": "notice"})
        short = m.banner_frame.height()
        m._update_banner({"message": "Assembly has moved to the gym at eleven because of the rain. " * 3, "level": "warning"})
        self.assertGreater(m.banner_frame.height(), short)
        self.assertGreaterEqual(m.user_container.y(), m.banner_frame.geometry().bottom())


class TestGuestTutorialAndSignOut(unittest.TestCase):
    """People took the ID scanner for the only way in, and couldn't sign out."""

    def setUp(self):
        self.mirror = make_mirror()
        self.mirror.user_container.hide()
        self.mirror._last_state = 'idle'

    def tearDown(self):
        close_mirror(self.mirror)

    def _arrive_as_guest(self):
        m = self.mirror
        m._transitioning = True
        m._last_state = 'guest'
        m._trigger_transition('guest', '', {'config': {}})
        settle(m)
        m._transitioning = False

    def _wait(self, seconds):
        m = self.mirror
        m._last_activity_time -= seconds
        m._last_hand_time -= seconds
        m._update_inputs()
        settle(m)

    def test_the_demo_waits_before_covering_the_screen(self):
        m = self.mirror
        self._arrive_as_guest()
        self.assertFalse(m.gesture_demo_overlay.isVisible())
        self._wait(2)
        self.assertFalse(m.gesture_demo_overlay.isVisible())
        self._wait(4)
        self.assertTrue(m.gesture_demo_overlay.isVisible())
        self.assertTrue(m.guest_scan_callout.isVisible())
        self.assertTrue(m.guest_scan_callout.show_or)       # gesture OR scan
        self.assertEqual(m.demo_hold_lbl.text(), "HOLD PINCH TO EXIT")

    def test_a_raised_hand_holds_the_demo_off(self):
        m = self.mirror
        self._arrive_as_guest()
        m._last_activity_time -= 30
        m._handle_gesture(gesture(region='left', x=0.3))
        m._update_inputs()
        self.assertFalse(m.gesture_demo_overlay.isVisible())

    def test_scanning_drops_the_demo_and_it_returns_without_the_scanner(self):
        m = self.mirror
        self._arrive_as_guest()
        self._wait(6)
        self.assertTrue(m.gesture_demo_overlay.isVisible())

        smp.requests.post = lambda *a, **k: _EmptyResponse()
        m._on_barcode_scanned("NOTREAL1")
        settle(m)
        self.assertFalse(m.gesture_demo_overlay.isVisible())
        self.assertFalse(m.guest_scan_callout.isVisible())

        self._wait(6)
        self.assertTrue(m.gesture_demo_overlay.isVisible())
        self.assertFalse(m.guest_scan_callout.isVisible())

    def _sign_in(self, user='u1'):
        m = self.mirror
        m._on_barcode_verified(user, [], {}, True, 'CODE1')
        settle(m)
        m._transitioning = False
        m._position_sign_out()

    def test_the_sign_out_button_signs_out_with_a_pinch(self):
        m = self.mirror
        self._sign_in()
        self.assertTrue(m.sign_out_btn.isVisible())
        c = m.sign_out_btn.geometry().center()
        at = dict(x=c.x() / m.width(), y=c.y() / m.height(), region='left')
        m._handle_gesture(gesture(**at))
        self.assertTrue(m._sign_out_hover)
        m._last_rx_tap_time = 0.0
        m._handle_gesture(dict(gesture(event='tap', **at), event_id=7))
        self.assertNotEqual(m._last_state, 'user')
        self.assertIsNone(m.current_user_id)
        self.assertIn("Signed out", m.toast_lbl.text())

    def test_scanning_the_same_id_again_signs_out(self):
        m = self.mirror
        self._sign_in()
        m._on_barcode_verified('u1', [], {}, True, 'CODE1')
        self.assertNotEqual(m._last_state, 'user')

    def test_a_signed_out_face_does_not_sign_straight_back_in(self):
        import json, time as _t
        m = self.mirror
        self._sign_in()
        m.face_detected = True
        m.sign_out()
        settle(m)
        m._transitioning = False

        def daemon_sees(state, user, detected=True):
            with open(smp.FACE_DATA_FILE, 'w') as f:
                json.dump({'state': state, 'user_id': user, 'detected': detected,
                           'recognized': state == 'user', 'timestamp': _t.time()}, f)
            m._update_inputs()
            settle(m)
            m._transitioning = False

        daemon_sees('user', 'u1')
        self.assertNotEqual(m._last_state, 'user')
        # They walk away for a while; next time their face works again.
        daemon_sees('guest', 'guest', detected=False)
        m._signed_out_face_gone -= smp.SIGNED_OUT_FACE_HOLD_SEC + 1
        daemon_sees('guest', 'guest', detected=False)
        self.assertIsNone(m._signed_out_user)

    def test_pinching_the_timetable_arrow_opens_it(self):
        m = self.mirror
        self._sign_in()
        m._slide_timetable_out(animate=False)
        settle(m)
        self.assertTrue(m.edge_arrow_caption.isVisible())
        self.assertEqual(m.edge_arrow_caption.text(), "TIMETABLE")
        c = m.edge_arrow_label.geometry().center()
        m._last_rx_tap_time = 0.0
        m._handle_gesture(dict(gesture(event='tap', x=c.x() / m.width(), y=c.y() / m.height()),
                               event_id=9))
        self.assertFalse(m._timetable_slid_away)


class TestTimetableMessages(unittest.TestCase):
    def setUp(self):
        from widgets.timetable_widget import TimetableWidget
        self.tt = TimetableWidget(api_url='http://test')

    def tearDown(self):
        self.tt.deleteLater()

    def _load(self, status, periods=()):
        tt = self.tt
        tt.user_id = 'u1'
        tt._fetch_gen += 1
        tt.periods, tt.status = list(periods), status
        tt._on_fetched()

    def test_it_says_why_instead_of_dashes(self):
        import datetime as _dt
        from unittest import mock
        noon = _dt.datetime(2026, 10, 21, 12, 0)   # a class time, not interval or lunch
        with mock.patch('widgets.timetable_widget.datetime') as fake:
            fake.now.return_value = noon
            for status, words in (('not_linked', 'Not linked'), ('error', "Can't load"),
                                  ('loading', 'Loading')):
                self._load(status)
                self.assertIn(words, self.tt.subject_lbl.text())
                self.assertFalse(self.tt.room_v.isVisibleTo(self.tt))
        self.assertTrue(self.tt._retry.isActive())     # the error case tries again

    def test_a_new_person_never_sees_the_last_persons_classes(self):
        self.tt.periods = [{'summary': 'Old', 'startTime': '09:00', 'endTime': '10:00'}]
        self.tt.set_user_id('someone-else')
        self.assertNotIn('Old', [p.get('summary') for p in self.tt.periods])


class TestOverscroll(unittest.TestCase):
    """At the end of a list it stretches with resistance, then springs back."""

    def setUp(self):
        self.mirror = make_mirror()
        n = self.mirror.notices_widget
        n.cards_container.setFixedHeight(2000)
        app.processEvents()
        self.sb = n.scroll_area.verticalScrollBar()
        self.sb.setValue(0)
        self.content = n.scroll_area.widget()

    def tearDown(self):
        close_mirror(self.mirror)

    def _run(self, seconds):
        import time as _t
        end = _t.monotonic() + seconds
        while _t.monotonic() < end and self.mirror._momentum_timer.isActive():
            _t.sleep(0.016)
            self.mirror._momentum_tick()

    def _pull_up_while_pinched(self, px=-120):
        m = self.mirror
        held = dict(gesture(region='left', x=0.3), pinched=True)
        m._handle_gesture(held)
        m._handle_gesture(dict(held, event='scroll', scroll_delta=px))
        self._run(0.5)

    def test_pulling_past_the_top_stretches_with_resistance(self):
        m = self.mirror
        self._pull_up_while_pinched(-120)
        self.assertEqual(self.sb.value(), 0)
        self.assertLess(m._overscroll, -20)
        self.assertGreater(m._overscroll, -60)          # resisted: well under 120 px
        self.assertEqual(self.content.y(), int(round(-m._overscroll)))   # content pulled down
        self.assertTrue(m.overscroll_glow.isVisible())

    def test_it_holds_while_pinched_and_springs_back_on_release(self):
        m = self.mirror
        self._pull_up_while_pinched()
        stretched = m._overscroll
        self._run(0.3)
        self.assertEqual(m._overscroll, stretched)       # still held
        m._handle_gesture(gesture(region='left', x=0.3))  # fingers apart
        self._run(1.0)
        self.assertEqual(m._overscroll, 0.0)
        self.assertEqual(self.content.y(), 0)
        self.assertFalse(m.overscroll_glow.isVisible())
        self.assertFalse(m._momentum_timer.isActive())

    def test_moving_back_undoes_the_stretch_before_scrolling(self):
        m = self.mirror
        self._pull_up_while_pinched()
        held = dict(gesture(region='left', x=0.3), pinched=True)
        m._handle_gesture(dict(held, event='scroll', scroll_delta=200))
        self._run(0.6)
        self.assertEqual(m._overscroll, 0.0)
        self.assertGreater(self.sb.value(), 100)

    def test_the_middle_of_a_list_scrolls_normally(self):
        m = self.mirror
        self.sb.setValue(500)
        m._handle_gesture(gesture(region='left', event='scroll', delta=-40))
        self._run(0.6)
        self.assertEqual(self.sb.value(), 460)
        self.assertEqual(m._overscroll, 0.0)


class TestPracticeABTest(unittest.TestCase):
    """B: after the demo plays once, a short practice beside it. A: video only."""

    def setUp(self):
        self.mirror = make_mirror()
        m = self.mirror
        m.user_container.hide()
        m._last_state = 'idle'
        if m.demo_movie is None:
            self.skipTest('assets/gesture_demo.mp4 missing')

    def tearDown(self):
        close_mirror(self.mirror)

    def _arrive(self, variant):
        m = self.mirror
        m.telemetry.peek_variant = lambda: variant
        m.telemetry._get_config_variant = lambda: variant
        m._transitioning = True
        m._last_state = 'guest'
        m._trigger_transition('guest', '', {'config': {}})
        settle(m)
        m._transitioning = False
        self.assertEqual(m.current_variant, variant)
        m._show_gesture_scrim()
        settle(m)

    def _clip_ends(self):
        self.mirror._on_demo_looped()
        anim = self.mirror._practice_anim
        if anim is not None:
            anim.setCurrentTime(anim.duration())
        app.processEvents()

    def _hand_at(self, point, event=None, delta=0, eid=[100]):
        m = self.mirror
        g = m.practice_panel.mapTo(m.central_widget, point.toPoint())
        eid[0] += 1
        m._last_rx_tap_time = 0.0
        m._handle_gesture(dict(gesture(event=event, x=g.x() / m.width(), y=g.y() / m.height(), delta=delta),
                               event_id=eid[0]))

    def test_variant_a_keeps_just_the_video(self):
        self._arrive('A')
        self._clip_ends()
        self.assertIsNone(self.mirror._practice_state)
        self.assertFalse(self.mirror.practice_panel.isVisible())

    def test_variant_b_slides_the_video_aside_for_the_practice(self):
        m = self.mirror
        self._arrive('B')
        before = m.demo_surface.geometry()
        self._clip_ends()
        self.assertEqual(m._practice_state, 'active')
        self.assertTrue(m.practice_panel.isVisible())
        self.assertLess(m.demo_surface.geometry().right(), m.width() // 2)    # moved left
        self.assertLess(m.demo_surface.width(), before.width())
        self.assertGreater(m.practice_panel.x(), m.width() // 2)
        self.assertEqual(m.demo_hold_lbl.text(), "HOLD PINCH TO SKIP")

    def test_doing_the_practice_finishes_it_and_records_it(self):
        m = self.mirror
        self._arrive('B')
        self._clip_ends()
        pp = m.practice_panel
        for _ in range(pp.TAPS):
            self._hand_at(pp.dot_center())
            self._hand_at(pp.dot_center(), event='tap')
        self.assertEqual(pp.step, 1)
        self._hand_at(QPointF(pp.width() / 2, pp.height() / 2), event='scroll', delta=5000)
        self.assertEqual(pp.step, 2)
        s = m.telemetry.current_session
        self.assertEqual((s['practice_shown'], s['practice_completed'], s['practice_steps']), (1, 1, 2))

    def test_holding_a_pinch_skips_it(self):
        m = self.mirror
        self._arrive('B')
        self._clip_ends()
        m._demo_pinch_start = time.time() - 5
        m._demo_pinch_last = time.time()
        m._update_demo_hold(True)
        settle(m)
        self.assertFalse(m.gesture_demo_overlay.isVisible())
        s = m.telemetry.current_session
        self.assertEqual((s['practice_skipped'], s['practice_completed']), (1, 0))
        self.assertEqual(s['tutorial_dismissed'], 0)

    def test_dragging_the_list_does_not_count_as_holding_to_skip(self):
        m = self.mirror
        self._arrive('B')
        self._clip_ends()
        m._demo_pinch_start = time.time() - 0.9
        self._hand_at(QPointF(10, 200), event='scroll', delta=40)
        self.assertLess(m.demo_hold_fill.width(), m.demo_hold_bar.width() * 0.2)

    def test_it_is_offered_once_per_visit(self):
        m = self.mirror
        self._arrive('B')
        m._fade_out_gesture_scrim()
        settle(m)
        m._show_gesture_scrim()
        settle(m)
        self._clip_ends()
        self.assertNotEqual(m._practice_state, 'active')


class TestTeaserABTest(unittest.TestCase):
    """Someone passing by: A says STUDENT ID SCAN, B says STAND CLOSE TO INTERACT."""

    def setUp(self):
        self.mirror = make_mirror()
        self.mirror.user_container.hide()
        self.mirror._last_state = 'idle'
        self.sent = []
        self.mirror.telemetry.record_passerby = lambda v, sec: self.sent.append(v)

    def tearDown(self):
        close_mirror(self.mirror)

    def test_each_variant_has_its_own_hint(self):
        m = self.mirror
        m.telemetry.peek_variant = lambda: 'B'
        m._show_scan_callout()
        self.assertTrue(m.stand_close_hint.isVisible())
        self.assertFalse(m.guest_scan_callout.isVisible())
        mid = m.stand_close_hint.geometry().center().y()
        self.assertLess(abs(mid - m.height() // 2), 40)            # in the middle
        m._hide_scan_callout()
        m._teaser_shown_at = 0.0
        m.telemetry.peek_variant = lambda: 'A'
        m._show_scan_callout()
        self.assertTrue(m.guest_scan_callout.isVisible())
        self.assertFalse(m.stand_close_hint.isVisible())

    def test_walking_on_is_recorded_as_a_passer_by(self):
        m = self.mirror
        m.telemetry.peek_variant = lambda: 'B'
        m._show_scan_callout()
        m._teaser_last_seen -= smp.TEASER_VISIT_WINDOW_SEC + 1
        m._scan_tease_until = 0.0
        m._update_inputs()
        self.assertEqual(self.sent, ['B'])

    def test_a_visit_after_the_hint_keeps_its_variant(self):
        m = self.mirror
        m.telemetry.peek_variant = lambda: 'B'
        m.telemetry._get_config_variant = lambda: 'A'      # would otherwise say A
        m._show_scan_callout()
        m._transitioning = True
        m._last_state = 'guest'
        m._trigger_transition('guest', '', {'config': {}})
        settle(m)
        s = m.telemetry.current_session
        self.assertEqual(s['variant'], 'B')
        self.assertTrue(s['after_teaser'])
        self.assertEqual(self.sent, [])
