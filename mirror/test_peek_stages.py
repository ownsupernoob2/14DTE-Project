"""Smoke tests for the right-side peek: timetable first, King's Week under it.

These drive the real gesture handler with synthetic payloads — the same dicts
gesture_engine.py publishes — so the two-stage reveal, the box locking and the
article modal are all exercised through the paths the mirror actually uses.

Headless (offscreen Qt) and offline: requests is stubbed out before the window
is built, so nothing here touches the network.

Run from the mirror/ directory:  python -m unittest test_peek_stages
"""

import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import requests

from PyQt6.QtWidgets import QApplication


class _EmptyResponse:
    """Every fetch comes back with nothing, so each widget shows its empty state."""

    status_code = 200
    text = ''

    @staticmethod
    def json():
        return {}

    @staticmethod
    def raise_for_status():
        pass


# Patched before smart_mirror_pro is imported so no constructor can slip a real
# request out. Every widget shares this one requests module.
requests.get = lambda *a, **k: _EmptyResponse()
requests.post = lambda *a, **k: _EmptyResponse()

import smart_mirror_pro as smp
from widgets import kings_week_widget as kw

# Card art would otherwise start a download thread per box.
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


def gesture(region='right', event=None, x=0.8, y=0.5, delta=0, present=True):
    """One frame of published gesture state."""
    return {
        'present':      present,
        'region':       region,
        'event':        event,
        'hand_x':       x,
        'hand_y':       y,
        'scroll_delta': delta,
        'seq':          1,
        'timestamp':    1.0,
    }


def settle(mirror):
    """Jump every peek animation straight to its end.

    The geometry assertions want the finished layout, and running the animations
    also runs their finished handlers — which is where the panel actually hides.
    """
    anims = list(mirror._stage_anims or ())
    for extra in (mirror._peek_anim, mirror._anim_in, mirror._anim_out):
        if extra is not None:
            anims.append(extra)
    if mirror.kings_panel is not None:
        anims.extend(mirror.kings_panel.modal._anim or ())
    for anim in anims:
        anim.setCurrentTime(anim.duration())
    app.processEvents()


def fire(timer):
    """Make a pending single-shot timer go off now."""
    timer.stop()
    timer.timeout.emit()
    app.processEvents()


def make_mirror(articles=9):
    mirror = smp.SmartMirrorPro()
    # Nothing may poll in the background while a test is stepping through state.
    mirror.poll_timer.stop()
    mirror.gesture_timer.stop()
    mirror.banner_timer.stop()

    mirror.resize(1280, 800)
    mirror.show()
    # The gesture handler ignores everything while the mirror is idle, so put a
    # recognised student on screen.
    mirror._last_state = 'user'
    mirror.current_user_id = 'u1'
    mirror._apply_user_layout(mirror.width(), mirror.height())
    mirror.user_container.show()
    app.processEvents()

    mirror._articles = [article(i) for i in range(articles)]
    return mirror


def close_mirror(mirror):
    for timer in (mirror.poll_timer, mirror.gesture_timer, mirror.banner_timer,
                  mirror.peek_timer, mirror.kings_idle_timer):
        timer.stop()
    # Nothing may still be animating when the widgets go away, and deleteLater
    # only runs on the next pass of the event loop — otherwise the window is
    # destroyed somewhere in the middle of the next test.
    mirror._stop_anims(*(mirror._stage_anims or ()),
                       mirror._peek_anim, mirror._anim_in, mirror._anim_out)
    if mirror.kings_panel is not None:
        mirror.kings_panel.reset_gesture_state()
    mirror.hide()
    mirror.deleteLater()
    app.processEvents()


def reveal(mirror):
    """Dwell on the right: the timetable slides in, King's Week waits below."""
    mirror._handle_gesture(gesture(event='enter_right'))
    settle(mirror)
    return mirror


def promote(mirror):
    """Then scroll down, which slides the timetable away."""
    mirror._handle_gesture(gesture(event='scroll', delta=45))
    settle(mirror)
    mirror.kings_panel.set_articles(mirror._articles)
    mirror.kings_panel.grid_container.layout().activate()
    app.processEvents()
    return mirror.kings_panel


class TestReveal(unittest.TestCase):
    def setUp(self):
        self.mirror = make_mirror()

    def tearDown(self):
        close_mirror(self.mirror)

    def test_nothing_happens_while_the_mirror_is_idle(self):
        self.mirror._last_state = 'idle'
        self.mirror._handle_gesture(gesture(event='enter_right'))
        self.assertFalse(self.mirror._peek_visible)
        self.assertIsNone(self.mirror.peek_container)

    def test_dwell_slides_the_panel_in_from_off_screen(self):
        reveal(self.mirror)
        self.assertTrue(self.mirror._peek_visible)
        self.assertTrue(self.mirror.peek_container.isVisible())
        anim = self.mirror._peek_anim
        self.assertGreaterEqual(anim.startValue().left(), self.mirror.width())
        self.assertEqual(self.mirror.peek_container.geometry(),
                         self.mirror._peek_geometry())

    def test_kings_week_sits_directly_below_the_timetable(self):
        reveal(self.mirror)
        self.assertEqual(self.mirror._peek_stage, smp.PEEK_STAGE_TIMETABLE)
        sched = self.mirror.peek_panel.geometry()
        kings = self.mirror.kings_panel.geometry()
        self.assertEqual(sched.top(), 0)
        self.assertEqual(kings.top(), sched.top() + sched.height())
        self.assertEqual(kings.top() + kings.height(),
                         self.mirror.peek_container.height())
        self.assertGreater(kings.height(), 0, "King's Week must be visible below")

    def test_a_second_dwell_only_buys_more_time(self):
        reveal(self.mirror)
        container = self.mirror.peek_container
        reveal(self.mirror)
        self.assertIs(self.mirror.peek_container, container)
        self.assertEqual(self.mirror._peek_stage, smp.PEEK_STAGE_TIMETABLE)
        self.assertTrue(self.mirror.peek_timer.isActive())

    def test_a_hand_on_the_right_keeps_the_panel_alive(self):
        reveal(self.mirror)
        self.mirror.kings_idle_timer.stop()
        self.mirror._handle_gesture(gesture())          # no event, just present
        self.assertTrue(self.mirror.kings_idle_timer.isActive())

    def test_the_left_region_never_touches_the_peek(self):
        reveal(self.mirror)
        stage = self.mirror._peek_stage
        self.mirror._handle_gesture(gesture(region='left', event='scroll', x=0.2, delta=60))
        self.assertEqual(self.mirror._peek_stage, stage)


class TestPromotion(unittest.TestCase):
    def setUp(self):
        self.mirror = make_mirror()
        reveal(self.mirror)

    def tearDown(self):
        close_mirror(self.mirror)

    def test_scrolling_down_hands_the_column_to_kings_week(self):
        promote(self.mirror)
        self.assertEqual(self.mirror._peek_stage, smp.PEEK_STAGE_KINGS)
        container = self.mirror.peek_container
        # The timetable is parked off the container's right edge...
        self.assertGreaterEqual(self.mirror.peek_panel.x(), container.width())
        # ...and King's Week has the whole panel.
        self.assertEqual(self.mirror.kings_panel.geometry(), container.rect())

    def test_scrolling_up_does_not_promote(self):
        self.mirror._handle_gesture(gesture(event='scroll', delta=-45))
        self.assertEqual(self.mirror._peek_stage, smp.PEEK_STAGE_TIMETABLE)

    def test_waiting_promotes_on_its_own(self):
        self.assertTrue(self.mirror.peek_timer.isActive())
        fire(self.mirror.peek_timer)
        self.assertEqual(self.mirror._peek_stage, smp.PEEK_STAGE_KINGS)

    def test_promotion_stops_the_countdown(self):
        promote(self.mirror)
        self.assertFalse(self.mirror.peek_timer.isActive())
        self.assertTrue(self.mirror.kings_idle_timer.isActive())

    def test_scrolling_up_off_the_top_brings_the_timetable_back(self):
        kings = promote(self.mirror)
        self.assertTrue(kings.at_top())
        self.mirror._handle_gesture(gesture(event='scroll', delta=-45))
        settle(self.mirror)
        self.assertEqual(self.mirror._peek_stage, smp.PEEK_STAGE_TIMETABLE)
        self.assertEqual(self.mirror.peek_panel.geometry().top(), 0)
        self.assertTrue(self.mirror.peek_timer.isActive())

    def test_scrolling_mid_grid_scrolls_instead_of_demoting(self):
        kings = promote(self.mirror)
        kings.scroll_by_pixels(80)
        self.assertGreater(kings.scroll_area.verticalScrollBar().value(), 0)
        self.mirror._handle_gesture(gesture(event='scroll', delta=-20))
        self.assertEqual(self.mirror._peek_stage, smp.PEEK_STAGE_KINGS)


class TestBoxesAndModal(unittest.TestCase):
    def setUp(self):
        self.mirror = make_mirror()
        reveal(self.mirror)
        self.kings = promote(self.mirror)

    def tearDown(self):
        close_mirror(self.mirror)

    def test_the_grid_lights_up_only_once_it_owns_the_column(self):
        self.assertTrue(self.kings._gesture_active)
        self.mirror._handle_gesture(gesture(region='left', x=0.2))
        self.assertFalse(self.kings._gesture_active)

    def test_the_palm_position_picks_a_box(self):
        self.mirror._handle_gesture(gesture(y=0.05))
        top = self.kings.selected_index
        self.mirror._handle_gesture(gesture(y=0.95))
        bottom = self.kings.selected_index
        self.assertEqual(top, 0, 'the top of the panel is the feature story')
        self.assertGreater(bottom, top, 'lower down the panel is a later box')

    def test_selection_is_always_locked_onto_a_box(self):
        for y in (0.0, 0.17, 0.33, 0.5, 0.68, 0.84, 1.0):
            self.mirror._handle_gesture(gesture(y=y))
            self.assertTrue(any(c.selected for c in self.kings.cards),
                            f"nothing selected at y={y}")

    def test_tap_opens_the_selected_story(self):
        self.mirror._handle_gesture(gesture(y=0.05))
        self.mirror._handle_gesture(gesture(event='tap', y=0.05))
        self.assertTrue(self.kings.modal_open)
        self.assertEqual(self.kings.modal.title_lbl.text(), 'Story 0')

    def test_a_drifting_hand_does_not_reshuffle_behind_the_modal(self):
        self.mirror._handle_gesture(gesture(y=0.5))
        picked = self.kings.selected_index
        self.mirror._handle_gesture(gesture(event='tap', y=0.5))
        self.mirror._handle_gesture(gesture(y=0.05))
        self.assertEqual(self.kings.selected_index, picked)

    def test_scroll_reaches_the_article_not_the_grid(self):
        self.mirror._handle_gesture(gesture(event='tap'))
        grid_before = self.kings.scroll_area.verticalScrollBar().value()
        self.mirror._handle_gesture(gesture(event='scroll', delta=60))
        self.assertEqual(self.kings.scroll_area.verticalScrollBar().value(),
                         grid_before)

    def test_tapping_again_closes_the_story(self):
        self.mirror._handle_gesture(gesture(event='tap'))
        self.assertTrue(self.kings.modal_open)
        self.mirror._handle_gesture(gesture(event='tap'))
        self.assertFalse(self.kings.modal_open)
        settle(self.mirror)
        self.assertFalse(self.kings.modal.isVisible())


class TestDismissal(unittest.TestCase):
    def setUp(self):
        self.mirror = make_mirror()

    def tearDown(self):
        close_mirror(self.mirror)

    def test_tap_dismisses_the_timetable_stage(self):
        reveal(self.mirror)
        self.mirror._handle_gesture(gesture(event='tap'))
        settle(self.mirror)
        self.assertFalse(self.mirror._peek_visible)
        self.assertFalse(self.mirror.peek_container.isVisible())

    def test_going_idle_on_the_right_hides_the_panel(self):
        reveal(self.mirror)
        kings = promote(self.mirror)
        self.mirror._handle_gesture(gesture(event='tap'))
        self.assertTrue(kings.modal_open)

        fire(self.mirror.kings_idle_timer)
        settle(self.mirror)

        self.assertFalse(self.mirror._peek_visible)
        self.assertFalse(kings.modal_open)
        self.assertFalse(self.mirror.peek_container.isVisible())

    def test_the_next_peek_starts_on_the_timetable_again(self):
        reveal(self.mirror)
        promote(self.mirror)
        fire(self.mirror.kings_idle_timer)
        settle(self.mirror)

        reveal(self.mirror)
        self.assertEqual(self.mirror._peek_stage, smp.PEEK_STAGE_TIMETABLE)
        self.assertEqual(self.mirror.peek_panel.geometry().top(), 0)
        self.assertEqual(self.mirror.kings_panel.geometry().top(),
                         self.mirror.peek_panel.height())
        self.assertEqual(self.mirror.kings_panel.selected_index, 0)

    def test_a_new_student_does_not_inherit_the_peek(self):
        reveal(self.mirror)
        kings = promote(self.mirror)
        self.mirror._handle_gesture(gesture(event='tap'))

        self.mirror._trigger_transition('user', 'u2', {'config': {}})
        settle(self.mirror)

        self.assertFalse(self.mirror._peek_visible)
        self.assertFalse(self.mirror.peek_container.isVisible())
        self.assertFalse(kings.modal_open)
        self.assertEqual(self.mirror._peek_stage, smp.PEEK_STAGE_TIMETABLE)

    def test_hiding_twice_is_harmless(self):
        reveal(self.mirror)
        self.mirror._hide_timetable_peek(animate=False)
        self.mirror._hide_timetable_peek(animate=False)
        self.assertFalse(self.mirror._peek_visible)


class TestGesturePolling(unittest.TestCase):
    """The file hand-off between gesture_engine.py and the mirror."""

    def setUp(self):
        self.mirror = make_mirror()
        self.tmp = os.path.join(
            os.environ.get('TEMP', os.environ.get('TMP', '/tmp')),
            'gesture_status.json'
        )
        self._saved = None
        if os.path.exists(self.tmp):
            with open(self.tmp) as f:
                self._saved = f.read()

    def tearDown(self):
        close_mirror(self.mirror)
        # Leave a real engine's status file exactly as it was found.
        if self._saved is not None:
            with open(self.tmp, 'w') as f:
                f.write(self._saved)
        elif os.path.exists(self.tmp):
            os.remove(self.tmp)

    def _publish(self, payload):
        import json
        with open(self.tmp, 'w') as f:
            json.dump(payload, f)

    def test_a_published_dwell_reveals_the_panel(self):
        payload = gesture(event='enter_right')
        payload['timestamp'] = self.mirror.last_gesture_timestamp + 10.0
        self._publish(payload)
        self.mirror._poll_gestures()
        settle(self.mirror)
        self.assertTrue(self.mirror._peek_visible)

    def test_a_stale_timestamp_is_ignored(self):
        payload = gesture(event='enter_right')
        payload['timestamp'] = 5.0
        self.mirror.last_gesture_timestamp = 99.0
        self._publish(payload)
        self.mirror._poll_gestures()
        self.assertFalse(self.mirror._peek_visible)

    def test_a_corrupt_status_file_is_survivable(self):
        with open(self.tmp, 'w') as f:
            f.write('{ not json')
        self.mirror._poll_gestures()      # must not raise
        self.assertFalse(self.mirror._peek_visible)


if __name__ == '__main__':
    unittest.main()
