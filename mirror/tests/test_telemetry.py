import unittest
from unittest.mock import patch, MagicMock
from mirror.telemetry import TelemetryTracker


class TestTelemetry(unittest.TestCase):
    def test_session_lifecycle_and_ab_assignment(self):
        tracker = TelemetryTracker(api_url="http://localhost:8080")
        v1 = tracker.start_session(session_type="guest", auth_method="none")
        self.assertIn(v1, ("A", "B"))
        self.assertIsNotNone(tracker.current_session)
        self.assertEqual(tracker.current_session["session_type"], "guest")
        self.assertEqual(tracker.current_session["auth_method"], "none")
        self.assertFalse(tracker.current_session["has_gesture"])

        tracker.record_gesture("scroll", 40)
        self.assertTrue(tracker.current_session["has_gesture"])
        self.assertEqual(tracker.current_session["gesture_scroll_count"], 1)

        tracker.record_dwell_progress(0.4)
        self.assertTrue(tracker.current_session["_dwell_started"])

        tracker.record_timetable_toggle()
        self.assertEqual(tracker.current_session["timetable_toggle_count"], 1)
        self.assertEqual(tracker.current_session["dwell_completed_count"], 1)

        tracker.record_modal_open()
        self.assertEqual(tracker.current_session["article_modal_opens"], 1)
        tracker.record_modal_close()

        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            # Force duration >= 1.0s so finalize doesn't discard it
            tracker.current_session["start_time"] -= 2.0
            tracker.end_session()
            self.assertIsNone(tracker.current_session)

        # Next session should alternate variant
        v2 = tracker.start_session(session_type="user", auth_method="face")
        self.assertNotEqual(v1, v2)
        self.assertEqual(tracker.current_session["session_type"], "user")
        self.assertEqual(tracker.current_session["auth_method"], "face")


if __name__ == "__main__":
    unittest.main()
