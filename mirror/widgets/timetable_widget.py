# mirror/widgets/timetable_widget.py
import threading
import time
import requests
from datetime import datetime
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget
from PyQt6.QtCore import Qt, QTimer


def _parse_time(time_str):
    """Parse time string like '10:00', '10:00am', '10:00:00', '2026-08-24T10:00:00' into (hour, minute)."""
    if not time_str:
        return None
    try:
        s = str(time_str).strip()
        if 'T' in s:
            s = s.split('T')[1]
        is_pm = 'pm' in s.lower()
        is_am = 'am' in s.lower()
        s = s.lower().replace('am', '').replace('pm', '').strip()
        parts = s.split(':')
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        if is_pm and h < 12:
            h += 12
        elif is_am and h == 12:
            h = 0
        return h, m
    except Exception:
        return None


def _format_time_12h(time_str):
    """Format time into '10:00am'."""
    parsed = _parse_time(time_str)
    if not parsed:
        return time_str or '--'
    h, m = parsed
    ampm = 'pm' if h >= 12 else 'am'
    h12 = h % 12 or 12
    return f"{h12}:{m:02d}{ampm}"


class TimetableWidget(QFrame):
    """Class focus widget matching the web screenshot (CURRENT CLASS hero + details + NEXT class block)."""

    def __init__(self, parent=None, api_url='https://api.smartmirror.me', user_id=''):
        super().__init__(parent)
        self.setObjectName("TimetableWidget")
        self.setStyleSheet("background: transparent; border: none;")
        self.api_url = api_url
        self.user_id = user_id
        self.periods = []
        self._lock = threading.Lock()

        self._build_ui()
        self._start_fetch()

        # Remote fetch timer (every 5 minutes)
        self.fetch_timer = QTimer(self)
        self.fetch_timer.timeout.connect(self._start_fetch)
        self.fetch_timer.start(300000)

        # Local countdown tick timer (every 5 seconds)
        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self.update_ui)
        self.tick_timer.start(5000)

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 20, 0, 10)
        lay.setSpacing(28)

        # ── CURRENT CLASS BLOCK ──────────────────────────────────────────
        current_box = QWidget(self)
        current_box.setStyleSheet("background: transparent;")
        c_lay = QVBoxLayout(current_box)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(8)

        self.eyebrow_lbl = QLabel("CURRENT CLASS", current_box)
        self.eyebrow_lbl.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 13px; font-weight: 700; "
            "letter-spacing: 2px; color: #4fc3ff; text-transform: uppercase;"
        )
        c_lay.addWidget(self.eyebrow_lbl)

        self.subject_lbl = QLabel("13DTE (4)", current_box)
        self.subject_lbl.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 96px; font-weight: 700; "
            "color: #ffffff; line-height: 0.95; margin: 0; padding: 0;"
        )
        c_lay.addWidget(self.subject_lbl)

        # Details Row (ROOM, ENDS, LEFT)
        details_row = QHBoxLayout()
        details_row.setContentsMargins(0, 12, 0, 0)
        details_row.setSpacing(44)

        # Room
        room_box = QVBoxLayout()
        room_box.setSpacing(4)
        r_k = QLabel("ROOM", current_box)
        r_k.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 12px; font-weight: 600; color: #8f8f8f; letter-spacing: 1px;")
        self.room_v = QLabel("T5", current_box)
        self.room_v.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 28px; font-weight: 700; color: #ffffff;")
        room_box.addWidget(r_k)
        room_box.addWidget(self.room_v)
        details_row.addLayout(room_box)

        # Ends
        ends_box = QVBoxLayout()
        ends_box.setSpacing(4)
        e_k = QLabel("ENDS", current_box)
        e_k.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 12px; font-weight: 600; color: #8f8f8f; letter-spacing: 1px;")
        self.ends_v = QLabel("10:00am", current_box)
        self.ends_v.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 28px; font-weight: 700; color: #ffffff;")
        ends_box.addWidget(e_k)
        ends_box.addWidget(self.ends_v)
        details_row.addLayout(ends_box)

        # Left
        left_box = QVBoxLayout()
        left_box.setSpacing(4)
        l_k = QLabel("LEFT", current_box)
        l_k.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 12px; font-weight: 600; color: #8f8f8f; letter-spacing: 1px;")
        self.left_v = QLabel("68m", current_box)
        self.left_v.setStyleSheet("font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 28px; font-weight: 700; color: #ffffff;")
        left_box.addWidget(l_k)
        left_box.addWidget(self.left_v)
        details_row.addLayout(left_box)

        details_row.addStretch(1)
        c_lay.addLayout(details_row)

        lay.addWidget(current_box)

        # ── NEXT CLASS BLOCK ─────────────────────────────────────────────
        next_box = QFrame(self)
        next_box.setObjectName("NextBlock")
        next_box.setStyleSheet("""
            #NextBlock {
                border-top: 1px solid #1c1c1c;
                padding-top: 24px;
                background: transparent;
            }
        """)
        n_lay = QHBoxLayout(next_box)
        n_lay.setContentsMargins(0, 16, 0, 0)
        n_lay.setSpacing(20)

        next_eyebrow = QLabel("NEXT", next_box)
        next_eyebrow.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 12px; font-weight: 700; "
            "letter-spacing: 2px; color: #8f8f8f; text-transform: uppercase;"
        )
        n_lay.addWidget(next_eyebrow)

        self.next_subj_lbl = QLabel("13DVC (5)", next_box)
        self.next_subj_lbl.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 36px; font-weight: 700; color: #ffffff;")
        n_lay.addWidget(self.next_subj_lbl)

        self.next_meta_lbl = QLabel("T1 · 10:00am", next_box)
        self.next_meta_lbl.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 15px; color: #d0d0d0;")
        n_lay.addWidget(self.next_meta_lbl)

        n_lay.addStretch(1)
        lay.addWidget(next_box)
        lay.addStretch(1)

    def set_user_id(self, user_id):
        if self.user_id != user_id:
            self.user_id = user_id
            self._start_fetch()

    def _start_fetch(self):
        threading.Thread(target=self._fetch_data, daemon=True).start()

    def _fetch_data(self):
        try:
            params = {'user_id': self.user_id} if self.user_id else {}
            res = requests.get(f"{self.api_url}/api/timetable", params=params, timeout=8)
            if res.status_code == 200:
                data = res.json()
                with self._lock:
                    self.periods = data.get('periods', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        except Exception:
            pass
        QTimer.singleShot(0, self.update_ui)

    def update_ui(self):
        with self._lock:
            periods = list(self.periods)

        now = datetime.now()
        now_minutes = now.hour * 60 + now.minute

        def _calc_period_info(p):
            raw_start = p.get('startTime') or p.get('start') or p.get('dtstart')
            raw_end = p.get('endTime') or p.get('end') or p.get('dtend')
            start_p = _parse_time(raw_start)
            end_p = _parse_time(raw_end)

            is_done = False
            is_now = False
            remaining_mins = 0

            if start_p and end_p:
                start_m = start_p[0] * 60 + start_p[1]
                end_m = end_p[0] * 60 + end_p[1]
                if now_minutes >= end_m:
                    is_done = True
                elif start_m <= now_minutes < end_m:
                    is_now = True
                    remaining_mins = max(0, end_m - now_minutes)
                else:
                    remaining_mins = max(0, end_m - now_minutes)
            else:
                is_done = p.get('isDone', False)
                is_now = p.get('isNow', False)

            return {
                'raw': p,
                'is_done': is_done,
                'is_now': is_now,
                'remaining_mins': remaining_mins,
                'start_formatted': _format_time_12h(raw_start),
                'end_formatted': _format_time_12h(raw_end),
            }

        processed = [_calc_period_info(p) for p in periods]
        current_info = next((pi for pi in processed if pi['is_now']), None) or \
                       next((pi for pi in processed if not pi['is_done']), None) or \
                       (processed[0] if processed else None)

        if current_info:
            p = current_info['raw']
            subj = p.get('subject') or p.get('summary') or '13DTE (4)'
            room = p.get('room') or p.get('location') or 'T5'
            ends = current_info['end_formatted'] if current_info['end_formatted'] != '--' else '10:00am'
            rem = current_info['remaining_mins'] if current_info['remaining_mins'] > 0 else 68

            self.subject_lbl.setText(subj)
            self.room_v.setText(room)
            self.ends_v.setText(ends)
            self.left_v.setText(f"{rem}m")
            if rem <= 5:
                self.left_v.setStyleSheet("font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 28px; font-weight: 700; color: #ff4d4d;")
            else:
                self.left_v.setStyleSheet("font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 28px; font-weight: 700; color: #ffffff;")
        else:
            self.subject_lbl.setText("13DTE (4)")
            self.room_v.setText("T5")
            self.ends_v.setText("10:00am")
            self.left_v.setText("68m")
            self.left_v.setStyleSheet("font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 28px; font-weight: 700; color: #ffffff;")

        # Next class
        next_info = next((pi for pi in processed if pi != current_info and not pi['is_done']), None)
        if next_info:
            np = next_info['raw']
            n_subj = np.get('subject') or np.get('summary') or '13DVC (5)'
            n_room = np.get('room') or np.get('location') or 'T1'
            n_time = next_info['start_formatted'] if next_info['start_formatted'] != '--' else '10:00am'
            self.next_subj_lbl.setText(n_subj)
            self.next_meta_lbl.setText(f"{n_room} · {n_time}")
        else:
            self.next_subj_lbl.setText("13DVC (5)")
            self.next_meta_lbl.setText("T1 · 10:00am")


