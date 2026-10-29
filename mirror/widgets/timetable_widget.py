# mirror/widgets/timetable_widget.py
import threading
import time
import requests
from datetime import datetime
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from config import mirror_headers


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

    # King's High School bell schedule (minutes since midnight)
    # Grouptime  08:40 - 09:00
    # Period 1   09:00 - 10:00
    # Period 2   10:00 - 11:00
    # Interval   11:00 - 11:25
    # Period 3   11:25 - 12:25
    # Period 4   12:25 - 13:25
    # Lunch      13:25 - 14:00
    # Period 5   14:00 - 15:05
    INTERVAL_START = 11 * 60          # 660 mins  11:00am
    INTERVAL_END   = 11 * 60 + 25     # 685 mins  11:25am
    LUNCH_START    = 13 * 60 + 25     # 805 mins  1:25pm
    LUNCH_END      = 14 * 60          # 840 mins  2:00pm
    SCHOOL_END     = 15 * 60 + 5      # 905 mins  3:05pm

    fetched = pyqtSignal()
    RETRY_MS = 15000                  # after a failed fetch, try again this soon

    def __init__(self, parent=None, api_url='https://api.smartmirror.me', user_id=''):
        super().__init__(parent)
        self.setObjectName("TimetableWidget")
        self.setStyleSheet("background-color: #000000; border: none;")
        self.api_url = api_url
        self.user_id = user_id
        self.periods = []
        # loading | ok | not_linked | error — what to say when there are no periods
        self.status = 'loading'
        self._fetch_gen = 0
        self._lock = threading.Lock()
        self.fetched.connect(self._on_fetched)
        self._retry = QTimer(self)
        self._retry.setSingleShot(True)
        self._retry.timeout.connect(self._start_fetch)

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

    TIGHT_H = 360   # below this (the compact view at 720p) drop the room/ends/left row

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 40, 0, 20)
        lay.setSpacing(24)
        self._lay = lay

        # ── PREVIOUS COMPLETED PERIODS BLOCK (Full mode) ─────────────────
        self.prev_box = QWidget(self)
        self.prev_box.setStyleSheet("background: transparent;")
        self.prev_lay = QVBoxLayout(self.prev_box)
        self.prev_lay.setContentsMargins(0, 0, 0, 4)
        self.prev_lay.setSpacing(8)
        self.prev_box.hide()
        lay.addWidget(self.prev_box)

        # ── CURRENT CLASS BLOCK ──────────────────────────────────────────
        current_box = QWidget(self)
        current_box.setStyleSheet("background: transparent;")
        self.current_box = current_box
        c_lay = QVBoxLayout(current_box)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(8)

        self.eyebrow_lbl = QLabel("CURRENT CLASS", current_box)
        self.eyebrow_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.eyebrow_lbl.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 16px; font-weight: 800; "
            "letter-spacing: 2px; color: #38bdf8; text-transform: uppercase;"
        )
        c_lay.addWidget(self.eyebrow_lbl)

        self.subject_lbl = QLabel("13DTE (4)", current_box)
        self.subject_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.subject_lbl.setWordWrap(True)
        self.subject_lbl.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 64px; font-weight: 800; "
            "color: #ffffff; line-height: 1.0; margin: 0; padding: 0;"
        )
        c_lay.addWidget(self.subject_lbl)

        # Details Row (ROOM, ENDS, LEFT)
        details_row = QHBoxLayout()
        details_row.setContentsMargins(0, 12, 0, 0)
        details_row.setSpacing(24)

        # Room
        room_box = QVBoxLayout()
        room_box.setSpacing(4)
        r_k = QLabel("ROOM", current_box)
        self._detail_keys = [r_k]
        r_k.setAlignment(Qt.AlignmentFlag.AlignLeft)
        r_k.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 16px; font-weight: 700; color: #cbd5e1; letter-spacing: 1px;")
        self.room_v = QLabel("T5", current_box)
        self.room_v.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.room_v.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 32px; font-weight: 800; color: #ffffff;")
        room_box.addWidget(r_k)
        room_box.addWidget(self.room_v)
        details_row.addLayout(room_box)

        # Ends
        ends_box = QVBoxLayout()
        ends_box.setSpacing(4)
        e_k = QLabel("ENDS", current_box)
        self._detail_keys.append(e_k)
        e_k.setAlignment(Qt.AlignmentFlag.AlignLeft)
        e_k.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 16px; font-weight: 700; color: #cbd5e1; letter-spacing: 1px;")
        self.ends_v = QLabel("10:00am", current_box)
        self.ends_v.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.ends_v.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 32px; font-weight: 800; color: #ffffff;")
        ends_box.addWidget(e_k)
        ends_box.addWidget(self.ends_v)
        details_row.addLayout(ends_box)

        # Left
        left_box = QVBoxLayout()
        left_box.setSpacing(4)
        l_k = QLabel("LEFT", current_box)
        self._detail_keys.append(l_k)
        l_k.setAlignment(Qt.AlignmentFlag.AlignLeft)
        l_k.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 16px; font-weight: 700; color: #cbd5e1; letter-spacing: 1px;")
        self.left_v = QLabel("68m", current_box)
        self.left_v.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.left_v.setStyleSheet("font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 32px; font-weight: 800; color: #ffffff;")
        left_box.addWidget(l_k)
        left_box.addWidget(self.left_v)
        details_row.addLayout(left_box)

        details_row.addStretch(1)
        c_lay.addLayout(details_row)
        lay.addWidget(current_box)

        # ── NEXT CLASS BLOCK (Compact Mode) ──────────────────────────────
        self.next_box = QFrame(self)
        self.next_box.setObjectName("NextBlock")
        self.next_box.setStyleSheet("""
            #NextBlock {
                border-top: 1px solid #1c1c1c;
                padding-top: 24px;
                background: transparent;
            }
        """)
        n_lay = QHBoxLayout(self.next_box)
        n_lay.setContentsMargins(0, 16, 0, 0)
        n_lay.setSpacing(28)

        self.next_eyebrow = QLabel("NEXT", self.next_box)
        self.next_eyebrow.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 16px; font-weight: 800; "
            "letter-spacing: 2px; color: #cbd5e1; text-transform: uppercase;"
        )
        n_lay.addWidget(self.next_eyebrow)

        self.next_subj_lbl = QLabel("13DVC (5)", self.next_box)
        self.next_subj_lbl.setWordWrap(True)
        self.next_subj_lbl.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 32px; font-weight: 800; color: #ffffff;")
        n_lay.addWidget(self.next_subj_lbl)

        self.next_meta_lbl = QLabel("T1 · 10:00am", self.next_box)
        self.next_meta_lbl.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 18px; font-weight: 600; color: #f1f5f9;")
        n_lay.addWidget(self.next_meta_lbl)

        n_lay.addStretch(1)
        lay.addWidget(self.next_box)

        # ── FULL SCHEDULE BLOCK (Full Mode) ──────────────────────────────
        self.schedule_box = QWidget(self)
        self.schedule_box.setStyleSheet("background: transparent;")
        self.schedule_lay = QVBoxLayout(self.schedule_box)
        self.schedule_lay.setContentsMargins(0, 8, 0, 0)
        self.schedule_lay.setSpacing(14)
        self.schedule_box.hide()
        lay.addWidget(self.schedule_box)

        lay.addStretch(1)
        self.mode = 'compact'

    def set_mode(self, mode):
        """Switch between 'compact'/'current_next' (hero + next) and 'full'/'all_today' (all periods)."""
        if mode in ('full', 'all_today'):
            self.mode = 'full'
            self.next_box.hide()
            self.schedule_box.show()
        else:
            self.mode = 'compact'
            self.prev_box.hide()
            self.next_box.show()
            self.schedule_box.hide()
        self._apply_tightness()
        self.update_ui()

    def set_layout_mode(self, mode):
        self.set_mode(mode)

    def toggle_layout_mode(self):
        new_mode = 'compact' if self.mode == 'full' else 'full'
        self.set_mode(new_mode)
        return new_mode

    def set_user_id(self, user_id):
        if self.user_id != user_id:
            self.user_id = user_id
            with self._lock:
                self.periods = []         # never show the last person's classes
            self.status = 'loading'
            self.update_ui()
            self._start_fetch()

    def _start_fetch(self):
        self._retry.stop()
        if not self.user_id:
            return                        # guests have no timetable
        self._fetch_gen += 1
        threading.Thread(target=self._fetch_data, args=(self.user_id, self._fetch_gen),
                         daemon=True).start()

    def _fetch_data(self, user_id, gen):
        status, periods = 'error', None
        try:
            res = requests.get(f"{self.api_url}/api/timetable", params={'user_id': user_id},
                               headers=mirror_headers(), timeout=20)
            if res.status_code == 200:
                data = res.json()
                periods = data.get('periods', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                status = 'ok'
            elif res.status_code == 404:
                status = 'not_linked'
                periods = []
            else:
                print(f"[TIMETABLE] HTTP {res.status_code} for {user_id}: {res.text[:120]}", flush=True)
        except Exception as e:
            print(f"[TIMETABLE] Fetch failed for {user_id}: {e}", flush=True)
        if gen != self._fetch_gen:
            return                        # someone else is at the mirror now
        with self._lock:
            if periods is not None:
                self.periods = periods
            self.status = status
        self.fetched.emit()

    def _on_fetched(self):
        if self.status == 'error':
            self._retry.start(self.RETRY_MS)
        self.update_ui()

    def _tight(self):
        return self.mode == 'compact' and 0 < self.height() < self.TIGHT_H

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_tightness()
        self.update_ui()

    def _apply_tightness(self):
        # At 1280x720 the compact view is ~240 px tall but its contents need
        # ~360: Qt squeezed the class name to nothing. When short, use tight
        # spacing and keep just the class name and what's next.
        tight = self._tight()
        self._lay.setContentsMargins(0, 8 if tight else 40, 0, 4 if tight else 20)
        self._lay.setSpacing(8 if tight else 24)

    def _set_detail_labels(self, room, ends, left):
        """Rename the three small headings (ROOM / ENDS / LEFT, or STARTS / IN in a break)."""
        for w, text in zip(self._detail_keys, (room, ends, left)):
            w.setText(text)

    def _show_details(self, shown):
        shown = shown and not self._tight()
        for w in self._detail_keys + [self.room_v, self.ends_v, self.left_v]:
            w.setVisible(shown)

    def update_ui(self):
        with self._lock:
            periods = list(self.periods)

        all_periods = periods             # this week and next, for what's coming after today
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        now_minutes = now.hour * 60 + now.minute

        def _get_period_date(p):
            """Return YYYY-MM-DD for a period, preferring an explicit 'date' key."""
            d = p.get('date') or p.get('Date')
            if d:
                return str(d)[:10]
            # Fall back to parsing ISO datetime in startTime / dtstart
            raw = p.get('startTime') or p.get('dtstart') or p.get('start') or ''
            if 'T' in str(raw):
                return str(raw)[:10]
            return today_str  # unknown date -- assume today

        # ── FILTER: only today's periods ────────────────────────────────
        periods = [p for p in periods if _get_period_date(p) == today_str]

        def _calc_period_info(p):
            raw_start = p.get('startTime') or p.get('start') or p.get('dtstart')
            raw_end   = p.get('endTime')   or p.get('end')   or p.get('dtend')
            start_p = _parse_time(raw_start)
            end_p   = _parse_time(raw_end)

            is_done = False
            is_now  = False
            remaining_mins = 0

            if start_p and end_p:
                start_m = start_p[0] * 60 + start_p[1]
                end_m   = end_p[0]   * 60 + end_p[1]
                if now_minutes >= end_m:
                    is_done = True
                elif start_m <= now_minutes < end_m:
                    is_now = True
                    remaining_mins = max(0, end_m - now_minutes)
                else:
                    remaining_mins = max(0, end_m - now_minutes)
            else:
                is_done = p.get('isDone', False)
                is_now  = p.get('isNow',  False)

            return {
                'raw': p,
                'is_done': is_done,
                'is_now':  is_now,
                'remaining_mins': remaining_mins,
                'start_formatted': _format_time_12h(raw_start),
                'end_formatted':   _format_time_12h(raw_end),
            }

        processed = [_calc_period_info(p) for p in periods]

        # School-over: all today's classes finished OR past 3:05pm with no upcoming
        all_done     = bool(processed) and all(pi['is_done'] for pi in processed)
        no_upcoming  = not any(not pi['is_done'] for pi in processed)
        school_over  = all_done or (no_upcoming and now_minutes >= self.SCHOOL_END and self.status == 'ok')

        current_info = next((pi for pi in processed if pi['is_now']), None) or \
                       next((pi for pi in processed if not pi['is_done']), None) or \
                       (processed[0] if processed else None)

        is_interval = (self.INTERVAL_START <= now_minutes < self.INTERVAL_END)
        is_lunch    = (self.LUNCH_START    <= now_minutes < self.LUNCH_END)

        # In a break the student knows it's a break: lead with what's on next and
        # then what's after that, and only mention the break in the small label.
        # Only on a day with lessons, so a weekend isn't "after school".
        break_kind = None
        if processed:
            if is_interval:
                break_kind = "INTERVAL"
            elif is_lunch:
                break_kind = "LUNCH"
            elif school_over:
                break_kind = "AFTER SCHOOL"

        def _coming(p, start_formatted, day):
            return {
                'subj':  p.get('subject') or p.get('summary') or '--',
                'room':  p.get('room') or p.get('location') or '--',
                'start': start_formatted if start_formatted != '--' else '',
                'day':   day,
                'start_m': (lambda t: t[0] * 60 + t[1] if t else None)(
                    _parse_time(p.get('startTime') or p.get('start') or p.get('dtstart'))),
            }

        def _day_label(date_str):
            try:
                day = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                return ''
            if (day.date() - now.date()).days == 1:
                return "Tomorrow"
            return day.strftime('%A')

        coming = []
        if break_kind:
            # What's left today, then the following school days (the server sends
            # this week and next, so a Friday afternoon still has a Monday).
            for pi in processed:
                if not pi['is_done']:
                    coming.append(_coming(pi['raw'], pi['start_formatted'], ''))
            later = sorted((p for p in all_periods if _get_period_date(p) > today_str),
                           key=lambda p: (_get_period_date(p), str(p.get('startTime') or '')))
            for p in later:
                coming.append(_coming(p, _format_time_12h(p.get('startTime') or p.get('start')),
                                      _day_label(_get_period_date(p))))
            coming = coming[:2]
        break_view = bool(break_kind and coming)

        # ── Populate hero block ──────────────────────────────────────────
        if not break_view:
            self._set_detail_labels("ROOM", "ENDS", "LEFT")
        if break_view:
            up = coming[0]
            amber = "#4ade80" if break_kind == "AFTER SCHOOL" else "#f59e0b"
            self.eyebrow_lbl.setText(f"{break_kind} · UP NEXT")
            self.eyebrow_lbl.setStyleSheet(
                "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 16px; font-weight: 800; "
                f"letter-spacing: 2px; color: {amber}; text-transform: uppercase;"
            )
            self.subject_lbl.setStyleSheet(
                "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 64px; font-weight: 800; "
                "color: #ffffff; line-height: 1.0; margin: 0; padding: 0;"
            )
            self.subject_lbl.setText(up['subj'])
            self.room_v.setText(up['room'])
            self.ends_v.setText(up['start'] or '--')
            if up['day'] or up['start_m'] is None:
                third_key, third = "DAY", up['day'] or '--'
            else:
                third_key, third = "IN", f"{max(1, up['start_m'] - now_minutes)}m"
            self._set_detail_labels("ROOM", "STARTS", third_key)
            self.left_v.setText(third)
            self.left_v.setStyleSheet("font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 32px; font-weight: 800; color: #ffffff;")
        elif school_over and not is_interval and not is_lunch:
            # All of today's classes are done
            self.eyebrow_lbl.setText("SCHOOL DAY COMPLETE")
            self.eyebrow_lbl.setStyleSheet(
                "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 16px; font-weight: 800; "
                "letter-spacing: 2px; color: #4ade80; text-transform: uppercase;"
            )
            self.subject_lbl.setText("Go Home")
            self.subject_lbl.setStyleSheet(
                "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 64px; font-weight: 800; "
                "color: #4ade80; line-height: 1.0; margin: 0; padding: 0;"
            )
            self.room_v.setText("--")
            self.ends_v.setText("--")
            self.left_v.setText("--")
            self.left_v.setStyleSheet("font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 32px; font-weight: 800; color: #4ade80;")
        elif is_interval:
            self.subject_lbl.setStyleSheet(
                "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 64px; font-weight: 800; "
                "color: #ffffff; line-height: 1.0; margin: 0; padding: 0;"
            )
            self.eyebrow_lbl.setText("INTERVAL")
            self.eyebrow_lbl.setStyleSheet(
                "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 16px; font-weight: 800; "
                "letter-spacing: 2px; color: #f59e0b; text-transform: uppercase;"
            )
            self.subject_lbl.setText("Morning Interval")
            self.room_v.setText("Campus")
            self.ends_v.setText("11:25am")
            rem_break = max(1, self.INTERVAL_END - now_minutes)
            self.left_v.setText(f"{rem_break}m")
            self.left_v.setStyleSheet("font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 32px; font-weight: 800; color: #f59e0b;")
        elif is_lunch:
            self.subject_lbl.setStyleSheet(
                "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 64px; font-weight: 800; "
                "color: #ffffff; line-height: 1.0; margin: 0; padding: 0;"
            )
            self.eyebrow_lbl.setText("LUNCH BREAK")
            self.eyebrow_lbl.setStyleSheet(
                "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 16px; font-weight: 800; "
                "letter-spacing: 2px; color: #f59e0b; text-transform: uppercase;"
            )
            self.subject_lbl.setText("Lunch Break")
            self.room_v.setText("Courtyard")
            self.ends_v.setText("2:00pm")
            rem_break = max(1, self.LUNCH_END - now_minutes)
            self.left_v.setText(f"{rem_break}m")
            self.left_v.setStyleSheet("font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 32px; font-weight: 800; color: #f59e0b;")
        elif current_info:
            self.subject_lbl.setStyleSheet(
                "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 64px; font-weight: 800; "
                "color: #ffffff; line-height: 1.0; margin: 0; padding: 0;"
            )
            self.eyebrow_lbl.setText("CURRENT CLASS")
            self.eyebrow_lbl.setStyleSheet(
                "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 16px; font-weight: 800; "
                "letter-spacing: 2px; color: #38bdf8; text-transform: uppercase;"
            )
            p = current_info['raw']
            subj = p.get('subject') or p.get('summary') or '13DTE (4)'
            room = p.get('room') or p.get('location') or 'T5'
            ends = current_info['end_formatted'] if current_info['end_formatted'] != '--' else '3:05pm'
            rem  = current_info['remaining_mins'] if current_info['remaining_mins'] > 0 else 0

            self.subject_lbl.setText(subj)
            self.room_v.setText(room)
            self.ends_v.setText(ends)
            self.left_v.setText(f"{rem}m")
            if rem <= 5:
                self.left_v.setStyleSheet("font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 32px; font-weight: 800; color: #ff4d4d;")
            else:
                self.left_v.setStyleSheet("font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 32px; font-weight: 800; color: #ffffff;")
        else:
            # No data yet -- show placeholders
            self.subject_lbl.setStyleSheet(
                "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 64px; font-weight: 800; "
                "color: #ffffff; line-height: 1.0; margin: 0; padding: 0;"
            )
            self.eyebrow_lbl.setText("CURRENT CLASS")
            self.eyebrow_lbl.setStyleSheet(
                "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 16px; font-weight: 800; "
                "letter-spacing: 2px; color: #38bdf8; text-transform: uppercase;"
            )
            # No class to show: say why, rather than a row of dashes.
            self.eyebrow_lbl.setText("TIMETABLE" if self.status != 'ok' else "TODAY")
            self.subject_lbl.setText({
                'loading': "Loading…",
                'not_linked': "Not linked yet",
                'error': "Can't load right now",
            }.get(self.status, "No classes today"))
        self._show_details(break_view or is_interval or is_lunch or (bool(current_info) and not school_over))

        # ── Next class (Compact Mode) ────────────────────────────────────
        next_info = next((pi for pi in processed if pi != current_info and not pi['is_done']), None)
        self.next_eyebrow.setText("THEN" if break_view else "NEXT")
        if break_view:
            # The hero already shows what's next, so this row is the one after it.
            then = coming[1] if len(coming) > 1 else None
            if then:
                where = " · ".join(x for x in (then['day'], then['room'], then['start']) if x)
                self.next_subj_lbl.setText(then['subj'])
                self.next_meta_lbl.setText(where)
            else:
                self.next_subj_lbl.setText("")
                self.next_meta_lbl.setText("")
        elif next_info:
            np = next_info['raw']
            n_subj = np.get('subject') or np.get('summary') or '--'
            n_room = np.get('room') or np.get('location') or '--'
            n_time = next_info['start_formatted'] if next_info['start_formatted'] != '--' else ''
            self.next_subj_lbl.setText(n_subj)
            self.next_meta_lbl.setText(f"{n_room} · {n_time}")
        elif school_over:
            self.next_subj_lbl.setText("See you tomorrow")
            self.next_meta_lbl.setText("")
        else:
            self.next_subj_lbl.setText({
                'not_linked': "Link your student ID at smartmirror.me",
                'error': "Trying again shortly",
            }.get(self.status, ""))
            self.next_meta_lbl.setText("")

        # ── Clear and rebuild prev / schedule lists ──────────────────────
        while self.prev_lay.count():
            item = self.prev_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        while self.schedule_lay.count():
            item = self.schedule_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self.mode == 'full':
            # Previous periods completed earlier today
            prev_periods = [pi for pi in processed if pi.get('is_done') and pi != current_info]
            if prev_periods:
                hdr = QLabel("COMPLETED EARLIER TODAY", self.prev_box)
                hdr.setStyleSheet(
                    "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 13px; font-weight: 800; "
                    "letter-spacing: 2px; color: #64748b; text-transform: uppercase;"
                )
                self.prev_lay.addWidget(hdr)

                for pi in prev_periods:
                    raw = pi['raw']
                    subj  = raw.get('subject') or raw.get('summary') or 'Class'
                    room  = raw.get('room') or raw.get('location') or '--'
                    t_str = pi['start_formatted'] if pi['start_formatted'] != '--' else ''
                    end_str = f" · ended {pi['end_formatted']}" if pi['end_formatted'] != '--' else ""

                    row_w = QWidget(self.prev_box)
                    row_w.setStyleSheet("background: transparent;")
                    r_lay = QHBoxLayout(row_w)
                    r_lay.setContentsMargins(0, 2, 0, 2)
                    r_lay.setSpacing(20)

                    lbl_t = QLabel(t_str, row_w)
                    lbl_t.setFixedWidth(64)
                    lbl_t.setStyleSheet(
                        "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 13px; font-weight: 700; "
                        "color: #64748b; text-transform: uppercase; letter-spacing: 1px;"
                    )
                    r_lay.addWidget(lbl_t)

                    lbl_s = QLabel(subj, row_w)
                    lbl_s.setStyleSheet(
                        "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 22px; font-weight: 700; "
                        "color: #64748b; text-decoration: line-through;"
                    )
                    r_lay.addWidget(lbl_s)

                    lbl_m = QLabel(f"{room}{end_str}", row_w)
                    lbl_m.setStyleSheet(
                        "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 15px; font-weight: 600; color: #475569;"
                    )
                    r_lay.addWidget(lbl_m)
                    r_lay.addStretch(1)
                    self.prev_lay.addWidget(row_w)

                self.prev_box.show()
            else:
                self.prev_box.hide()

            # Next and subsequent periods of today
            sched_periods = [pi for pi in processed if pi != current_info and not pi.get('is_done')]

            if sched_periods:
                divider = QWidget()
                divider.setFixedHeight(1)
                divider.setStyleSheet("background: #1c1c1c; margin: 4px 0;")
                self.schedule_lay.addWidget(divider)

                for idx, pi in enumerate(sched_periods):
                    raw    = pi['raw']
                    first_label = "THEN" if break_view else "NEXT"   # the hero is already "up next" in a break
                    p_label = first_label if idx == 0 else (raw.get('period') or pi['start_formatted'])
                    subj   = raw.get('subject') or raw.get('summary') or f"Period {idx + 1}"
                    room   = raw.get('room') or raw.get('location') or "--"
                    t_str  = pi['start_formatted'] if pi['start_formatted'] != '--' else ""

                    row_widget = QWidget(self.schedule_box)
                    row_widget.setStyleSheet("background: transparent;")
                    r_lay = QHBoxLayout(row_widget)
                    r_lay.setContentsMargins(0, 4, 0, 4)
                    r_lay.setSpacing(24)

                    lbl_tag = QLabel(p_label, row_widget)
                    lbl_tag.setFixedWidth(64)
                    tag_color = "#38bdf8" if idx == 0 else "#cbd5e1"
                    lbl_tag.setStyleSheet(
                        f"font-family: 'Segoe UI', system-ui, sans-serif; font-size: 15px; font-weight: 800; "
                        f"letter-spacing: 2px; color: {tag_color}; text-transform: uppercase;"
                    )
                    r_lay.addWidget(lbl_tag)

                    lbl_subj = QLabel(subj, row_widget)
                    lbl_subj.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 28px; font-weight: 700; color: #ffffff;")
                    r_lay.addWidget(lbl_subj)

                    lbl_meta = QLabel(f"{room} · {t_str}", row_widget)
                    lbl_meta.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 18px; font-weight: 600; color: #e2e8f0;")
                    r_lay.addWidget(lbl_meta)

                    r_lay.addStretch(1)
                    self.schedule_lay.addWidget(row_widget)

            elif school_over:
                # Show "go home" in schedule pane too
                go_lbl = QLabel("All done for today. See you tomorrow.", self.schedule_box)
                go_lbl.setStyleSheet(
                    "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 20px; "
                    "font-weight: 600; color: #4ade80;"
                )
                self.schedule_lay.addWidget(go_lbl)
        else:
            self.prev_box.hide()
