"""Offline tests for the exams the timetable shows when there is no class.

Headless (offscreen Qt), no network (no user is set, so nothing is fetched), and
the clock is faked, as in test_timetable_breaks.

Run from the mirror/ directory:  python -m unittest tests.test_exam_timetable
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

NOON_MON = (2026, 11, 9, 12, 0)        # Monday 9 November 2026


def exam(subject, date, start='', room='', length=0):
    return {"id": 1, "subject": subject, "date": date, "startTime": start,
            "durationMin": length, "room": room}


EXAMS = [
    exam("Physics", "2026-11-12", "09:30", "Hall", 180),
    exam("Calculus", "2026-11-10", "13:00", "Gym", 120),
    exam("English", "2026-11-12", "", "B4"),
    exam("Old exam", "2026-11-02", "09:00", "Hall"),
]

LESSON = {"date": "2026-11-09", "startTime": "12:25", "endTime": "13:25", "summary": "12PHY (6)",
          "location": "B1", "description": "", "isNow": False, "isDone": False}


class View:
    def __init__(self, when=NOON_MON, periods=(), exams=(), status='ok', mode=None):
        class FakeDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(*when)

        self._real = tw.datetime
        tw.datetime = FakeDateTime
        self.w = tw.TimetableWidget(user_id='')      # no user: never fetches
        if mode:
            self.w.set_mode(mode)
        self.w.periods, self.w.exams, self.w.status = list(periods), list(exams), status
        self.w.update_ui()

    def close(self):
        tw.datetime = self._real
        self.w.fetch_timer.stop()
        self.w.tick_timer.stop()

    @property
    def headings(self):
        return [k.text() for k in self.w._detail_keys]


class ExamTimetableTests(unittest.TestCase):
    def show(self, **kw):
        view = View(**kw)
        self.addCleanup(view.close)
        return view

    def test_with_no_class_the_next_exam_leads_and_the_one_after_follows(self):
        v = self.show(exams=EXAMS)
        w = v.w
        self.assertEqual(w.eyebrow_lbl.text(), "NEXT EXAM")
        self.assertEqual(w.subject_lbl.text(), "Calculus")
        self.assertEqual(v.headings, ["DATE", "STARTS", "ROOM"])
        self.assertEqual(w.room_v.text(), "Tue 10 Nov")
        self.assertEqual(w.ends_v.text(), "1:00pm")
        self.assertEqual(w.left_v.text(), "Gym")
        self.assertEqual(w.next_eyebrow.text(), "THEN")
        self.assertEqual(w.next_subj_lbl.text(), "Physics")
        self.assertIn("Thu 12 Nov", w.next_meta_lbl.text())
        self.assertIn("9:30am", w.next_meta_lbl.text())
        self.assertIn("Hall", w.next_meta_lbl.text())

    def test_past_exams_are_left_out(self):
        v = self.show(exams=EXAMS)
        shown = [v.w.subject_lbl.text(), v.w.next_subj_lbl.text()]
        self.assertNotIn("Old exam", shown)

    def test_an_exam_today_is_flagged_until_it_is_over(self):
        today = [exam("Maths", "2026-11-09", "13:00", "Hall", 90)]
        v = self.show(exams=today, when=(2026, 11, 9, 8, 0))
        self.assertEqual(v.w.eyebrow_lbl.text(), "EXAM TODAY")
        self.assertEqual(v.w.subject_lbl.text(), "Maths")
        v = self.show(exams=today, when=(2026, 11, 9, 14, 31))      # 13:00 + 90 min has passed
        self.assertNotEqual(v.w.subject_lbl.text(), "Maths")

    def test_an_exam_with_no_length_is_taken_to_last_two_hours(self):
        today = [exam("Maths", "2026-11-09", "10:00")]
        self.assertEqual(self.show(exams=today, when=(2026, 11, 9, 11, 59)).w.subject_lbl.text(), "Maths")
        self.assertNotEqual(self.show(exams=today, when=(2026, 11, 9, 12, 1)).w.subject_lbl.text(), "Maths")

    def test_an_exam_with_no_time_sorts_after_the_timed_ones_that_day(self):
        v = self.show(exams=[EXAMS[2], EXAMS[0]], when=(2026, 11, 11, 12, 0))
        self.assertEqual(v.w.subject_lbl.text(), "Physics")
        self.assertEqual(v.w.next_subj_lbl.text(), "English")
        self.assertIn("TBC", v.w.next_meta_lbl.text())

    def test_the_full_view_lists_the_rest(self):
        v = self.show(exams=EXAMS, mode='full')
        rows = []
        for i in range(v.w.schedule_lay.count()):
            item = v.w.schedule_lay.itemAt(i).widget()
            if item is not None and item.layout() is not None:
                rows.append([item.layout().itemAt(j).widget().text()
                             for j in range(item.layout().count()) if item.layout().itemAt(j).widget()])
        self.assertEqual(rows[0][:2], ["Thu 12 Nov", "Physics"])
        self.assertEqual(rows[1][1], "English")
        self.assertEqual(len(rows), 2)

    def test_a_day_with_classes_still_shows_the_classes(self):
        v = self.show(exams=EXAMS, periods=[LESSON])
        self.assertEqual(v.w.eyebrow_lbl.text(), "CURRENT CLASS")
        self.assertEqual(v.w.subject_lbl.text(), "12PHY (6)")

    def test_no_exams_still_says_no_classes(self):
        v = self.show(exams=[])
        self.assertEqual(v.w.subject_lbl.text(), "No classes today")

    def test_exams_show_for_someone_with_no_timetable_linked(self):
        v = self.show(exams=EXAMS, status='not_linked')
        self.assertEqual(v.w.subject_lbl.text(), "Calculus")

    def test_a_failed_fetch_does_not_pretend(self):
        v = self.show(exams=EXAMS, status='error')
        self.assertIn("Can't load", v.w.subject_lbl.text())

    def test_exams_with_odd_dates_are_ignored(self):
        v = self.show(exams=[exam("Bad", "someday"), exam("Good", "2026-11-10", "09:00")])
        self.assertEqual(v.w.subject_lbl.text(), "Good")

    def test_the_next_person_never_sees_the_last_persons_exams(self):
        v = self.show(exams=EXAMS)
        v.w.set_user_id('someone-else')
        self.assertEqual(v.w.exams, [])


class SwitchTests(unittest.TestCase):
    """CLASSES / EXAMS: the exams are the default with no class, and the student can flip."""

    def show(self, **kw):
        view = View(**kw)
        self.addCleanup(view.close)
        return view

    def test_the_switch_only_shows_when_there_are_exams(self):
        w = self.show(exams=[], periods=[LESSON]).w
        self.assertTrue(w.view_btn.isHidden())
        w = self.show(exams=EXAMS, periods=[LESSON]).w
        self.assertFalse(w.view_btn.isHidden())
        self.assertIn("EXAMS", w.view_btn.text())

    def test_a_day_with_classes_starts_on_the_classes(self):
        w = self.show(exams=EXAMS, periods=[LESSON]).w
        self.assertEqual(w.subject_lbl.text(), "12PHY (6)")

    def test_switching_to_exams_on_a_day_with_classes(self):
        v = self.show(exams=EXAMS, periods=[LESSON])
        v.w.toggle_view()
        self.assertEqual(v.w.eyebrow_lbl.text(), "NEXT EXAM")
        self.assertEqual(v.w.subject_lbl.text(), "Calculus")
        self.assertIn("CLASSES", v.w.view_btn.text())
        self.assertEqual(v.w.next_subj_lbl.text(), "Physics")

    def test_switching_back_to_the_classes(self):
        v = self.show(exams=EXAMS, periods=[LESSON])
        v.w.toggle_view()
        v.w.toggle_view()
        self.assertEqual(v.w.subject_lbl.text(), "12PHY (6)")

    def test_with_no_class_it_starts_on_exams_and_the_switch_goes_to_the_classes(self):
        v = self.show(exams=EXAMS)
        self.assertEqual(v.w.subject_lbl.text(), "Calculus")
        v.w.toggle_view()
        self.assertEqual(v.w.subject_lbl.text(), "No classes today")
        v.w.toggle_view()
        self.assertEqual(v.w.subject_lbl.text(), "Calculus")

    def test_the_full_view_follows_the_switch(self):
        v = self.show(exams=EXAMS, periods=[LESSON], mode='full')
        v.w.toggle_view()
        texts = []
        for i in range(v.w.schedule_lay.count()):
            item = v.w.schedule_lay.itemAt(i).widget()
            if item is not None and item.layout() is not None:
                texts += [item.layout().itemAt(j).widget().text()
                          for j in range(item.layout().count()) if item.layout().itemAt(j).widget()]
        self.assertIn("Physics", texts)
        self.assertNotIn("12PHY (6)", texts)

    def test_the_choice_does_not_carry_over_to_the_next_person(self):
        v = self.show(exams=EXAMS, periods=[LESSON])
        v.w.toggle_view()
        v.w.set_user_id('someone-else')
        self.assertEqual(v.w.view_pref, 'auto')

    def test_the_switch_can_be_found_for_the_hand(self):
        v = self.show(exams=EXAMS, periods=[LESSON])
        v.w.resize(800, 500)
        v.w.show()
        app.processEvents()
        r = v.w.view_switch_rect(v.w)
        self.assertFalse(r.isEmpty())
        self.assertGreater(r.width(), v.w.view_btn.width())      # padded: a hand is not a mouse
        v2 = self.show(exams=[], periods=[LESSON])
        v2.w.show()
        self.assertTrue(v2.w.view_switch_rect(v2.w).isEmpty())


if __name__ == '__main__':
    unittest.main()
