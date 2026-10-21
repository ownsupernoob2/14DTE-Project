# mirror/telemetry.py
"""
Session analytics and A/B variant assignment for the mirror.

One record per visit (from someone walking up to the mirror going idle again),
sent to POST /api/analytics/events when the visit ends. Records that can't be
sent are kept in a small local buffer and retried after the next success.

What counts as what:
  has_gesture    a deliberate control: scroll, tap, or holding a dwell
  hand_seen      a hand was tracked at all, deliberate or not
  scroll / tap   one per scroll or tap event
  notice/article opens and reading time, King's Week expands
  tutorial shown / dismissed (pinch-and-hold)
  practice (variant B): shown, completed or skipped, steps done, seconds spent
  after_teaser   the visit grew out of a brief encounter that got the teaser
  passerby       a record of its own: someone got the teaser and walked on
  from_screensaver  the visit interrupted the idle screensaver
"""

import json
import os
import threading
import time
import uuid

import requests

from config import MIRROR_ID, MIRROR_VERSION, mirror_headers

TELEMETRY_BUFFER_FILE = os.path.join(
    os.environ.get("TEMP", os.environ.get("TMP", "/tmp")),
    "smartmirror_telemetry_buffer.json"
)
BUFFER_LIMIT = 500


class TelemetryTracker:
    def __init__(self, api_url="https://api.smartmirror.me"):
        self.api_url = api_url.rstrip("/")
        self.current_session = None
        self._lock = threading.Lock()
        self._session_counter = 0
        self._last_cfg_check = 0.0
        self._cached_cfg_variant = None

    # ── Variant ──────────────────────────────────────────────────────────────

    def _get_config_variant(self):
        """The admin's chosen variant, as last fetched. Refreshed in the background:
        this is asked on the UI thread, which must never wait on the network."""
        now = time.time()
        if now - self._last_cfg_check >= 30:
            self._last_cfg_check = now
            threading.Thread(target=self._fetch_config_variant, daemon=True).start()
        return self._cached_cfg_variant

    def _fetch_config_variant(self):
        try:
            resp = requests.get(f"{self.api_url}/api/analytics/config", timeout=3)
            if resp.status_code == 200:
                active = resp.json().get("active_variant")
                if active in ("A", "B"):
                    self._cached_cfg_variant = active
        except Exception:
            pass

    def peek_variant(self):
        """The variant the next visit will get (the teaser shows before a visit starts)."""
        with self._lock:
            return self._get_config_variant() or ("B" if (self._session_counter + 1) % 2 == 0 else "A")

    @property
    def current_variant(self):
        with self._lock:
            return self.current_session.get("variant", "A") if self.current_session else "A"

    # ── Session lifecycle ────────────────────────────────────────────────────

    def start_session(self, session_type="guest", auth_method="presence", variant=None,
                      user_id=None, from_screensaver=False, screensaver_mode="", after_teaser=False):
        """Begin tracking a visit; returns its A/B variant."""
        with self._lock:
            if self.current_session is not None:
                self._finalize_current_session_locked()
            self._session_counter += 1
            if variant not in ("A", "B"):
                variant = self._get_config_variant() or ("B" if self._session_counter % 2 == 0 else "A")
            now = time.time()
            self.current_session = {
                "session_id": f"sess-{uuid.uuid4().hex[:12]}",
                "user_id": user_id if session_type == "user" else None,
                "mirror_id": MIRROR_ID,
                "mirror_version": MIRROR_VERSION,
                "client_timestamp": now,
                "variant": variant,
                "session_type": session_type,
                "auth_method": auth_method,
                "screensaver_mode": screensaver_mode or "",
                "from_screensaver": bool(from_screensaver),
                "time_to_auth_sec": 0.0 if session_type != "user" else 0.1,
                "duration_sec": 0.0,
                "has_gesture": False,
                "hand_seen": False,
                "time_to_first_gesture_sec": 0.0,
                "gesture_scroll_count": 0,
                "gesture_tap_count": 0,
                "timetable_toggle_count": 0,
                "dwell_completed_count": 0,
                "dwell_abandoned_count": 0,
                "article_modal_opens": 0,
                "notice_opens": 0,
                "modal_read_time_sec": 0.0,
                "kings_expands": 0,
                "tutorial_shown": 0,
                "tutorial_dismissed": 0,
                "practice_shown": 0,
                "practice_completed": 0,
                "practice_skipped": 0,
                "practice_steps": 0,
                "practice_sec": 0.0,
                "after_teaser": bool(after_teaser),
                "_start_time": now,
                "_modal_open_start": None,
                "_dwell_started": False,
            }
            return variant

    def update_auth_method(self, auth_method, user_id=None):
        """A guest visit became a signed-in one (face recognised or ID scanned)."""
        with self._lock:
            s = self.current_session
            if not s:
                return
            s["auth_method"] = auth_method
            if auth_method in ("barcode", "face"):
                if s["session_type"] != "user":
                    s["time_to_auth_sec"] = round(max(0.1, time.time() - s["_start_time"]), 2)
                s["session_type"] = "user"
                if user_id:
                    s["user_id"] = user_id

    def end_session(self):
        """End the visit and send it in the background."""
        with self._lock:
            payload = self._finalize_current_session_locked()
        if payload:
            threading.Thread(target=self._flush_payload, args=(payload,), daemon=True).start()

    # ── Events ───────────────────────────────────────────────────────────────

    def _mark_gesture_locked(self):
        s = self.current_session
        s["hand_seen"] = True
        if not s["has_gesture"]:
            s["has_gesture"] = True
            s["time_to_first_gesture_sec"] = round(max(0.1, time.time() - s["_start_time"]), 2)

    def record_gesture(self, event_type, region=None, **_):
        with self._lock:
            if not self.current_session:
                return
            if event_type in ("scroll", "fling"):
                self._mark_gesture_locked()
                self.current_session["gesture_scroll_count"] += 1
            elif event_type in ("tap", "click"):
                self._mark_gesture_locked()
                self.current_session["gesture_tap_count"] += 1

    def record_hand_seen(self):
        with self._lock:
            if self.current_session:
                self.current_session["hand_seen"] = True

    def record_dwell_progress(self, progress):
        with self._lock:
            s = self.current_session
            if not s:
                return
            if progress >= 0.25 and not s["_dwell_started"]:
                s["_dwell_started"] = True
                self._mark_gesture_locked()       # holding a dwell is deliberate
            elif progress < 0.15 and s["_dwell_started"]:
                s["_dwell_started"] = False
                s["dwell_abandoned_count"] += 1

    def record_timetable_toggle(self):
        with self._lock:
            s = self.current_session
            if not s:
                return
            self._mark_gesture_locked()
            s["_dwell_started"] = False
            s["timetable_toggle_count"] += 1
            s["dwell_completed_count"] += 1

    def record_modal_open(self, kind="article"):
        with self._lock:
            s = self.current_session
            if not s:
                return
            s["notice_opens" if kind == "notice" else "article_modal_opens"] += 1
            s["_modal_open_start"] = time.time()

    def record_modal_close(self):
        with self._lock:
            s = self.current_session
            if s and s.get("_modal_open_start"):
                s["modal_read_time_sec"] += round(time.time() - s["_modal_open_start"], 2)
                s["_modal_open_start"] = None

    def record_kings_expand(self):
        with self._lock:
            if self.current_session:
                self.current_session["kings_expands"] += 1

    def record_tutorial_shown(self):
        with self._lock:
            if self.current_session:
                self.current_session["tutorial_shown"] += 1

    def record_tutorial_dismissed(self):
        with self._lock:
            if self.current_session:
                self.current_session["tutorial_dismissed"] += 1

    def record_practice_shown(self):
        with self._lock:
            if self.current_session:
                self.current_session["practice_shown"] = 1

    def record_practice_ended(self, completed, steps, seconds):
        """The practice finished, or was skipped (held pinch) or cut short."""
        with self._lock:
            s = self.current_session
            if not s or not s["practice_shown"]:
                return
            s["practice_completed" if completed else "practice_skipped"] = 1
            s["practice_steps"] = int(steps)
            s["practice_sec"] = round(max(0.0, seconds), 2)

    def record_passerby(self, variant, seconds):
        """Someone got the brief-encounter teaser and left without a visit."""
        with self._lock:
            self._session_counter += 1
        payload = {
            "session_id": f"pass-{uuid.uuid4().hex[:12]}",
            "mirror_id": MIRROR_ID,
            "mirror_version": MIRROR_VERSION,
            "client_timestamp": time.time(),
            "variant": variant if variant in ("A", "B") else "A",
            "session_type": "passerby",
            "auth_method": "presence",
            "duration_sec": round(max(0.0, seconds), 2),
        }
        threading.Thread(target=self._flush_payload, args=(payload,), daemon=True).start()

    # ── Sending ──────────────────────────────────────────────────────────────

    def _finalize_current_session_locked(self):
        s, self.current_session = self.current_session, None
        if not s:
            return None
        now = time.time()
        if s.get("_modal_open_start"):
            s["modal_read_time_sec"] += round(now - s["_modal_open_start"], 2)
        s["duration_sec"] = round(now - s["_start_time"], 2)
        s["modal_read_time_sec"] = round(s["modal_read_time_sec"], 2)
        for key in [k for k in s if k.startswith("_")]:
            del s[key]
        if s["duration_sec"] < 1.0:          # a camera flicker, not a visit
            return None
        return s

    def _post(self, payload, timeout=3):
        try:
            res = requests.post(f"{self.api_url}/api/analytics/events", json=payload,
                                headers=mirror_headers(), timeout=timeout)
            return res.status_code == 200
        except Exception:
            return False

    def _flush_payload(self, payload):
        if self._post(payload):
            self._flush_offline_buffer()
            return
        try:
            buffer = []
            if os.path.exists(TELEMETRY_BUFFER_FILE):
                with open(TELEMETRY_BUFFER_FILE) as f:
                    buffer = json.load(f)
            buffer = (buffer + [payload])[-BUFFER_LIMIT:]
            with open(TELEMETRY_BUFFER_FILE, "w") as f:
                json.dump(buffer, f)
        except Exception:
            pass

    def _flush_offline_buffer(self):
        if not os.path.exists(TELEMETRY_BUFFER_FILE):
            return
        try:
            with open(TELEMETRY_BUFFER_FILE) as f:
                buffer = json.load(f)
            remaining = [item for item in buffer if not self._post(item, timeout=2)]
            if remaining:
                with open(TELEMETRY_BUFFER_FILE, "w") as f:
                    json.dump(remaining, f)
            else:
                os.remove(TELEMETRY_BUFFER_FILE)
        except Exception:
            pass
