import unittest
from unittest.mock import patch

import telemetry
from telemetry import TelemetryTracker


def offline_tracker():
    t = TelemetryTracker(api_url="http://test.invalid")
    t._last_cfg_check = float("inf")      # never ask the server for a variant
    return t


def finish(tracker, seconds=5.0):
    """End the visit as if it lasted `seconds`, returning the payload sent."""
    tracker.current_session["_start_time"] -= seconds
    with patch.object(telemetry.requests, "post") as post, \
            patch.object(telemetry.threading, "Thread") as thread:
        post.return_value.status_code = 200
        tracker.end_session()
        if not thread.called:
            return None
        target = thread.call_args.kwargs["target"]
        args = thread.call_args.kwargs["args"]
        with patch.object(tracker, "_flush_offline_buffer"):
            target(*args)
        return post.call_args.kwargs["json"]


class TestTelemetry(unittest.TestCase):
    def test_variants_alternate_without_a_server(self):
        t = offline_tracker()
        v1 = t.start_session("guest")
        v2 = t.start_session("guest")
        self.assertNotEqual(v1, v2)

    def test_moving_a_hand_is_not_a_tap(self):
        # The old tracker counted every hand movement as a tap, which made the
        # gesture adoption rate meaningless.
        t = offline_tracker()
        t.start_session("guest")
        for _ in range(20):
            t.record_hand_seen()
        t.record_gesture("motion")
        s = t.current_session
        self.assertTrue(s["hand_seen"])
        self.assertFalse(s["has_gesture"])
        self.assertEqual(s["gesture_tap_count"], 0)

    def test_deliberate_gestures_are_counted(self):
        t = offline_tracker()
        t.start_session("guest")
        t.record_gesture("scroll")
        t.record_gesture("fling")
        t.record_gesture("tap")
        s = t.current_session
        self.assertTrue(s["has_gesture"])
        self.assertGreater(s["time_to_first_gesture_sec"], 0)
        self.assertEqual((s["gesture_scroll_count"], s["gesture_tap_count"]), (2, 1))

    def test_dwell_completed_and_abandoned(self):
        t = offline_tracker()
        t.start_session("user", "face", user_id="u1")
        t.record_dwell_progress(0.4)
        t.record_dwell_progress(0.1)          # gave up
        t.record_dwell_progress(0.5)
        t.record_timetable_toggle()           # held it to the end
        s = t.current_session
        self.assertEqual((s["dwell_abandoned_count"], s["dwell_completed_count"], s["timetable_toggle_count"]), (1, 1, 1))
        self.assertTrue(s["has_gesture"])

    def test_notices_and_articles_are_counted_separately(self):
        t = offline_tracker()
        t.start_session("guest")
        t.record_modal_open("notice")
        t.record_modal_close()
        t.record_modal_open("article")
        t.record_kings_expand()
        t.record_tutorial_shown()
        t.record_tutorial_dismissed()
        s = t.current_session
        self.assertEqual((s["notice_opens"], s["article_modal_opens"], s["kings_expands"]), (1, 1, 1))
        self.assertEqual((s["tutorial_shown"], s["tutorial_dismissed"]), (1, 1))

    def test_a_guest_who_signs_in_records_who_and_how_long_it_took(self):
        t = offline_tracker()
        t.start_session("guest", "presence", from_screensaver=True, screensaver_mode="slideshow")
        t.current_session["_start_time"] -= 3
        t.update_auth_method("barcode", user_id="auth0|kid")
        payload = finish(t)
        self.assertEqual(payload["session_type"], "user")
        self.assertEqual(payload["user_id"], "auth0|kid")
        self.assertGreaterEqual(payload["time_to_auth_sec"], 3)
        self.assertTrue(payload["from_screensaver"])
        self.assertEqual(payload["screensaver_mode"], "slideshow")
        self.assertIn("mirror_id", payload)
        self.assertFalse(any(k.startswith("_") for k in payload))

    def test_guests_are_never_linked_to_a_user(self):
        t = offline_tracker()
        t.start_session("guest", user_id="auth0|someone")
        self.assertIsNone(t.current_session["user_id"])

    def test_sub_second_flickers_are_dropped(self):
        t = offline_tracker()
        t.start_session("guest")
        self.assertIsNone(finish(t, seconds=0.2))


if __name__ == "__main__":
    unittest.main()
