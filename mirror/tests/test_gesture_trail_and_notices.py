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

    def test_add_point_activates_and_tracks(self):
        self.trail.add_point(100, 200, pinched=False)
        self.assertFalse(self.trail.is_empty())
        self.assertTrue(self.trail.isVisible())
        self.assertEqual(len(self.trail._points), 1)

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

    def test_card_hover_and_select_border(self):
        card = self.notices.cards[0]
        # Resting state: 1px border on card, 3px only on :hover pseudo-state
        card.set_selected(False)
        self.assertIn("border: 1px solid", card.styleSheet())
        self.assertIn("#NoticeCard:hover", card.styleSheet())

        # Selected state: direct 3px solid #ffffff on #NoticeCard
        card.set_selected(True)
        self.assertIn("border: 3px solid #ffffff;", card.styleSheet())

    def test_select_at_point(self):
        self.notices.setGeometry(0, 0, 400, 600)
        selected = self.notices.select_at_point(0.25, 0.20)
        self.assertIsNotNone(selected)
        self.assertEqual(self.notices.selected_index, 0)
        self.assertIn("3px solid #ffffff", selected.styleSheet())

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
