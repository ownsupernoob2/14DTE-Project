"""Offline tests for what the timetable shows in a break and after school.

In interval, lunch and after school the big card leads with the next lesson and
the row under it shows the one after, instead of "Morning Interval" / "Go Home".
Runs headless (offscreen Qt) with no network: no user is set, so nothing is
fetched, and the clock is faked.

Run from the mirror/ directory:  python -m unittest tests.test_timetable_breaks
"""

import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication

from widgets import timetable_widget as tw

app = QApplication.instance() or QApplication([])

# A real-looking day for student 23143: Thursday 29 Oct 2026, with lunch between
# period 4 and 5, then the same shape on Friday and the Monday after.
DAY = [
    ("08:40", "09:00", "Group (TCR)", "B2"),
    ("09:00", "10:00", "12GEO (3)", "24"),
    ("10:00", "11:00", "12TEC (4)", "T2"),
    ("11:25", "12:25", "12BUS (5)", "B10"),
    ("12:25", "13:25", "12PHY (6)", "B1"),
    ("14:00", "15:00", "12MAT (1)", "A4"),
]


def lessons(date):
    return [{"date": date, "startTime": s, "endTime": e, "summary": name, "location": room,
             "description": "", "isNow": False, "isDone": False}
            for s, e, name, room in DAY]


def all_week(include_next_week=True):
    periods = lessons("2026-10-29") + lessons("2026-10-30")
    if include_next_week:
        periods += lessons("2026-11-02")
    return periods


class Widget:
    """A TimetableWidget at a fixed time, holding the given periods."""

    def __init__(self, when, periods):
        class FakeDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(*when)

        self._real = tw.datetime
        tw.datetime = FakeDateTime
        self.w = tw.TimetableWidget(user_id='')      # no user: never fetches
        self.w.periods = periods
        self.w.status = 'ok'
        self.w.update_ui()

    def close(self):
        tw.datetime = self._real
        self.w.fetch_timer.stop()
        self.w.tick_timer.stop()

    @property
    def headings(self):
        return [k.text() for k in self.w._detail_keys]


class TimetableBreakTests(unittest.TestCase):
    def show(self, when, periods):
        view = Widget(when, periods)
        self.addCleanup(view.close)
        return view

    def test_interval_leads_with_the_lesson_after_it_then_the_one_after_that(self):
        v = self.show((2026, 10, 29, 11, 10), all_week())
        w = v.w
        self.assertEqual(w.eyebrow_lbl.text(), "INTERVAL · UP NEXT")
        self.assertEqual(w.subject_lbl.text(), "12BUS (5)")
        self.assertEqual(w.room_v.text(), "B10")
        self.assertEqual(w.ends_v.text(), "11:25am")
        self.assertEqual(v.headings, ["ROOM", "STARTS", "IN"])
        self.assertEqual(w.left_v.text(), "15m")
        self.assertEqual(w.next_eyebrow.text(), "THEN")
        self.assertEqual(w.next_subj_lbl.text(), "12PHY (6)")
        self.assertNotIn("Interval", w.subject_lbl.text())

    def test_lunch_leads_with_period_5_and_then_tomorrows_first_lesson(self):
        v = self.show((2026, 10, 29, 13, 30), all_week())
        w = v.w
        self.assertEqual(w.eyebrow_lbl.text(), "LUNCH · UP NEXT")
        self.assertEqual(w.subject_lbl.text(), "12MAT (1)")
        self.assertEqual(w.left_v.text(), "30m")
        self.assertEqual(w.next_eyebrow.text(), "THEN")
        self.assertEqual(w.next_subj_lbl.text(), "Group (TCR)")
        self.assertIn("Tomorrow", w.next_meta_lbl.text())

    def test_after_school_leads_with_tomorrows_first_two_lessons(self):
        v = self.show((2026, 10, 29, 15, 30), all_week())
        w = v.w
        self.assertEqual(w.eyebrow_lbl.text(), "AFTER SCHOOL · UP NEXT")
        self.assertEqual(w.subject_lbl.text(), "Group (TCR)")
        self.assertEqual(v.headings, ["ROOM", "STARTS", "DAY"])
        self.assertEqual(w.ends_v.text(), "8:40am")
        self.assertEqual(w.left_v.text(), "Tomorrow")
        self.assertEqual(w.next_subj_lbl.text(), "12GEO (3)")
        self.assertNotIn("Go Home", w.subject_lbl.text())

    def test_friday_after_school_looks_to_monday(self):
        v = self.show((2026, 10, 30, 15, 30), all_week())
        w = v.w
        self.assertEqual(w.subject_lbl.text(), "Group (TCR)")
        self.assertEqual(w.left_v.text(), "Monday")
        self.assertEqual(w.next_subj_lbl.text(), "12GEO (3)")
        self.assertIn("Monday", w.next_meta_lbl.text())

    def test_without_later_days_after_school_falls_back_to_go_home(self):
        today_only = lessons("2026-10-29")
        v = self.show((2026, 10, 29, 15, 30), today_only)
        self.assertEqual(v.w.subject_lbl.text(), "Go Home")

    def test_a_lesson_in_progress_looks_as_it_did(self):
        v = self.show((2026, 10, 29, 12, 30), all_week())
        w = v.w
        self.assertEqual(w.eyebrow_lbl.text(), "CURRENT CLASS")
        self.assertEqual(w.subject_lbl.text(), "12PHY (6)")
        self.assertEqual(v.headings, ["ROOM", "ENDS", "LEFT"])
        self.assertEqual(w.next_eyebrow.text(), "NEXT")
        self.assertEqual(w.next_subj_lbl.text(), "12MAT (1)")

    def test_headings_reset_after_a_break(self):
        v = self.show((2026, 10, 29, 13, 30), all_week())
        self.assertEqual(v.headings, ["ROOM", "STARTS", "IN"])
        tw.datetime.now = classmethod(lambda cls, tz=None: cls(2026, 10, 29, 14, 30))
        v.w.update_ui()
        self.assertEqual(v.headings, ["ROOM", "ENDS", "LEFT"])
        self.assertEqual(v.w.eyebrow_lbl.text(), "CURRENT CLASS")


if __name__ == '__main__':
    unittest.main()
