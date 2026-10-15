# mirror/telemetry.py
"""
Telemetry & A/B testing client for the smart mirror.

Tracks session duration, authentication method, hands-free gesture adoption,
and timetable dwell discovery across Variant A (Control) and Variant B (Treatment).
Flushes summaries asynchronously to POST /api/analytics/events on the Go server,
with offline local buffering in case of network drops.
"""

import json
import os
import threading
import time
import uuid

import requests

TELEMETRY_BUFFER_FILE = os.path.join(
    os.environ.get("TEMP", os.environ.get("TMP", "/tmp")),
    "smartmirror_telemetry_buffer.json"
)


class TelemetryTracker:
    def __init__(self, api_url="https://api.smartmirror.me"):
        self.api_url = api_url.rstrip("/")
        self.current_session = None
        self._lock = threading.Lock()
        self._session_counter = 0

    def start_session(self, session_type="guest", auth_method="none", variant=None):
        """Begin tracking a session. Assigns A/B variant if not provided."""
        with self._lock:
            if self.current_session is not None:
                self._finalize_current_session_locked()

            self._session_counter += 1
            # Deterministic 50/50 A/B split: alternate between A and B
            if variant not in ("A", "B"):
                variant = "B" if (self._session_counter % 2 == 0) else "A"

            now = time.time()
            self.current_session = {
                "session_id": f"sess-{uuid.uuid4().hex[:12]}",
                "client_timestamp": now,
                "variant": variant,
                "session_type": session_type,
                "auth_method": auth_method,
                "start_time": now,
                "duration_sec": 0.0,
                "has_gesture": False,
                "time_to_first_gesture_sec": 0.0,
                "gesture_scroll_count": 0,
                "gesture_tap_count": 0,
                "timetable_toggle_count": 0,
                "dwell_completed_count": 0,
                "dwell_abandoned_count": 0,
                "article_modal_opens": 0,
                "modal_read_time_sec": 0.0,
                "_modal_open_start": None,
                "_dwell_started": False,
            }
            return self.current_session["variant"]

    @property
    def current_variant(self):
        with self._lock:
            if self.current_session:
                return self.current_session.get("variant", "A")
            return "A"

    def record_gesture(self, event_type, delta=0, region=None, **kwargs):
        with self._lock:
            if not self.current_session:
                return
            now = time.time()
            if not self.current_session["has_gesture"]:
                self.current_session["has_gesture"] = True
                self.current_session["time_to_first_gesture_sec"] = round(
                    max(0.1, now - self.current_session["start_time"]), 2
                )

            if event_type in ("scroll", "fling"):
                self.current_session["gesture_scroll_count"] += 1
            elif event_type in ("tap", "click"):
                self.current_session["gesture_tap_count"] += 1

    def record_dwell_progress(self, progress):
        with self._lock:
            if not self.current_session:
                return
            if progress >= 0.25 and not self.current_session.get("_dwell_started", False):
                self.current_session["_dwell_started"] = True
            elif progress < 0.15 and self.current_session.get("_dwell_started", False):
                self.current_session["_dwell_started"] = False
                self.current_session["dwell_abandoned_count"] += 1

    def record_timetable_toggle(self):
        with self._lock:
            if not self.current_session:
                return
            self.current_session["_dwell_started"] = False
            self.current_session["timetable_toggle_count"] += 1
            self.current_session["dwell_completed_count"] += 1

    def record_modal_open(self):
        with self._lock:
            if not self.current_session:
                return
            self.current_session["article_modal_opens"] += 1
            self.current_session["_modal_open_start"] = time.time()

    def record_modal_close(self):
        with self._lock:
            if not self.current_session:
                return
            start = self.current_session.get("_modal_open_start")
            if start:
                self.current_session["modal_read_time_sec"] += round(
                    time.time() - start, 2
                )
                self.current_session["_modal_open_start"] = None

    def end_session(self):
        """End and flush current session asynchronously."""
        payload = None
        with self._lock:
            payload = self._finalize_current_session_locked()
        if payload:
            threading.Thread(
                target=self._flush_payload, args=(payload,), daemon=True
            ).start()

    def _finalize_current_session_locked(self):
        if not self.current_session:
            return None
        now = time.time()
        sess = self.current_session
        self.current_session = None

        if sess.get("_modal_open_start"):
            sess["modal_read_time_sec"] += round(now - sess["_modal_open_start"], 2)

        sess["duration_sec"] = round(now - sess["start_time"], 2)
        sess.pop("start_time", None)
        sess.pop("_modal_open_start", None)
        sess.pop("_dwell_started", None)

        # Filter out sub-second flickers / false camera triggers
        if sess["duration_sec"] < 1.0:
            return None
        return sess

    def _flush_payload(self, payload):
        sent = False
        endpoints = [
            f"{self.api_url}/api/analytics/events",
            "http://localhost:8080/api/analytics/events",
            "http://127.0.0.1:8080/api/analytics/events",
        ]

        for ep in endpoints:
            try:
                res = requests.post(ep, json=payload, timeout=3)
                if res.status_code == 200:
                    sent = True
                    break
            except Exception:
                pass

        if not sent:
            try:
                buffer = []
                if os.path.exists(TELEMETRY_BUFFER_FILE):
                    with open(TELEMETRY_BUFFER_FILE, "r") as f:
                        buffer = json.load(f)
                buffer.append(payload)
                if len(buffer) > 200:
                    buffer = buffer[-200:]
                with open(TELEMETRY_BUFFER_FILE, "w") as f:
                    json.dump(buffer, f)
            except Exception:
                pass
        else:
            self._flush_offline_buffer()

    def _flush_offline_buffer(self):
        if not os.path.exists(TELEMETRY_BUFFER_FILE):
            return
        try:
            with open(TELEMETRY_BUFFER_FILE, "r") as f:
                buffer = json.load(f)
            if not buffer:
                return
            remaining = []
            for item in buffer:
                ok = False
                for ep in [f"{self.api_url}/api/analytics/events", "http://localhost:8080/api/analytics/events"]:
                    try:
                        res = requests.post(ep, json=item, timeout=2)
                        if res.status_code == 200:
                            ok = True
                            break
                    except Exception:
                        pass
                if not ok:
                    remaining.append(item)
            if remaining:
                with open(TELEMETRY_BUFFER_FILE, "w") as f:
                    json.dump(remaining, f)
            else:
                os.remove(TELEMETRY_BUFFER_FILE)
        except Exception:
            pass
