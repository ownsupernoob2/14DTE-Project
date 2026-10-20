import unittest
import os
import sys
import time

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor

# Ensure mirror/ is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from smart_mirror_pro import GestureTrailOverlay
from widgets.notices_widget import NoticesWidget, NoticeCard
from widgets.timetable_widget import TimetableWidget

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestGestureTrailOverlay(unittest.TestCase):
    def setUp(self):
        self.trail = GestureTrailOverlay()
        self.trail.resize(800, 600)

    def tearDown(self):
        self.trail.clear_trail()
        self.trail.deleteLater()

    def test_initial_state(self):
        self.assertTrue(self.trail.is_empty())
        self.assertFalse(self.trail.isVisible())

    def test_add_point_shows_the_cursor_where_the_hand_is(self):
        self.trail.add_point(100, 200, pinched=False)
        self.assertFalse(self.trail.is_empty())
        self.assertTrue(self.trail.isVisible())
        self.assertEqual(self.trail.head(), (100.0, 200.0))

    def _run(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            time.sleep(0.004)
            self.trail._tick()

    def test_the_cursor_glides_between_reports_instead_of_stepping(self):
        # A hand moving right at a steady 600 px/s, reported 16 times a second.
        x = 100.0
        for _ in range(4):
            self.trail.add_point(x, 300)
            self._run(1 / 16)
            x += 600 / 16
        before = self.trail.head()[0]
        self._run(0.03)                       # no new report yet
        self.assertGreater(self.trail.head()[0], before)

    def test_the_cursor_settles_on_a_still_hand(self):
        for _ in range(5):
            self.trail.add_point(400, 300)
            self._run(1 / 16)
        hx, hy = self.trail.head()
        self.assertAlmostEqual(hx, 400, delta=1.0)
        self.assertAlmostEqual(hy, 300, delta=1.0)

    def test_losing_the_hand_fades_the_cursor_away(self):
        self.trail.add_point(100, 100)
        self.trail.fade_out()
        self._run(0.4)
        self.assertTrue(self.trail.is_empty())
        self.assertFalse(self.trail.isVisible())

    def test_pinch_triggers_ripple(self):
        self.trail.add_point(100, 200, pinched=False)
        self.assertEqual(len(self.trail._ripples), 0)
        # Transition to pinched -> should trigger ripple
        self.trail.add_point(105, 205, pinched=True)
        self.assertEqual(len(self.trail._ripples), 1)
        self.assertEqual(self.trail._ripples[0][0], 105.0)
        self.assertEqual(self.trail._ripples[0][1], 205.0)

    def test_clear_trail(self):
        self.trail.add_point(100, 100, pinched=True)
        self.trail.clear_trail()
        self.assertTrue(self.trail.is_empty())
        self.assertEqual(len(self.trail._ripples), 0)
        self.assertFalse(self.trail.isVisible())

    def test_paint_event_does_not_crash(self):
        self.trail.add_point(100, 100, pinched=False)
        self.trail.add_point(120, 130, pinched=True)
        self.trail.repaint()


class TestNoticesCardPinchAndHighlight(unittest.TestCase):
    def setUp(self):
        self.notices = NoticesWidget(w=400, h=600)
        self.notices.notices = [
            {"id": "n1", "title": "Assembly Today", "category": "General", "notice": "In Hall at 9am"},
            {"id": "n2", "title": "Math Olympiad", "category": "Academic", "notice": "Room 4 at 1pm"},
        ]
        self.notices.update_ui()

    def tearDown(self):
        self.notices.deleteLater()

    def test_cards_registered(self):
        self.assertEqual(len(self.notices.cards), 2)

    def _settle_border(self, card):
        for _ in range(60):
            if not card._bw_timer.isActive():
                break
            card._tick_border()

    def test_selecting_a_card_animates_a_white_border_in_and_out(self):
        card = self.notices.cards[0]
        self.assertEqual(card._bw, 0.0)
        card.set_selected(True)
        self.assertTrue(card._bw_timer.isActive())
        card._tick_border()
        self.assertGreater(card._bw, 0.0)                 # growing, not snapped
        self.assertLess(card._bw, 3.0)
        self._settle_border(card)
        self.assertEqual(card._bw, 3.0)
        card.set_selected(False)
        self._settle_border(card)
        self.assertEqual(card._bw, 0.0)
        card.grab()                                       # paints without error

    def _finish_hint(self, card):
        card.read_more._anim.setCurrentTime(card.read_more._anim.duration())

    def test_read_more_only_shows_on_the_selected_card(self):
        a, b = self.notices.cards
        self.assertEqual(a.read_more.progress, 0.0)
        self.assertEqual(b.read_more.progress, 0.0)
        a.set_selected(True)
        self.assertTrue(a.read_more._anim.state() == a.read_more._anim.State.Running)
        self._finish_hint(a)
        self.assertEqual(a.read_more.progress, 1.0)
        self.assertEqual(b.read_more.progress, 0.0)          # others stay clear
        a.grab()                                             # paints without error
        a.set_selected(False)
        self._finish_hint(a)
        self.assertEqual(a.read_more.progress, 0.0)

    def test_the_hint_does_not_move_the_card_text(self):
        card = self.notices.cards[0]
        before = card.sizeHint()
        card.set_selected(True)
        self._finish_hint(card)
        self.assertEqual(card.sizeHint(), before)

    def test_reselecting_the_same_card_does_no_work(self):
        # select_at_point runs on every gesture packet; restyling every card each
        # time was a source of UI lag.
        card = self.notices.cards[0]
        card.set_selected(True)
        self._settle_border(card)
        style = card.styleSheet()
        card.set_selected(True)
        self.assertFalse(card._bw_timer.isActive())
        self.assertEqual(card.styleSheet(), style)

    def test_select_at_point(self):
        self.notices.setGeometry(0, 0, 400, 600)
        selected = self.notices.select_at_point(0.25, 0.20)
        self.assertIsNotNone(selected)
        self.assertEqual(self.notices.selected_index, 0)
        self.assertTrue(selected.selected)
        self.assertFalse(self.notices.cards[1].selected)

    def test_activate_selected_opens_and_closes_modal(self):
        self.notices.select_index(0)
        self.assertFalse(self.notices.modal_open)

        # Activate selected card
        res = self.notices.activate_selected()
        self.assertTrue(res)
        self.assertTrue(self.notices.modal_open)

        # Activating again closes modal
        res2 = self.notices.activate_selected()
        self.assertTrue(res2)
        self.assertFalse(self.notices.modal_open)


class TestTimetableBorders(unittest.TestCase):
    def test_no_random_border_around_timetable(self):
        tt = TimetableWidget()
        style = tt.styleSheet()
        self.assertIn("border: none;", style)
        self.assertNotIn("border: 4px solid #ffffff", style)
        tt.deleteLater()


if __name__ == '__main__':
    unittest.main()
