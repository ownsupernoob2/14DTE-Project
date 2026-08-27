# mirror/widgets/schedule_peek_widget.py
"""
Full-day timetable panel used by the right-side gesture peek.

The always-on TimetableWidget only shows the current and next class. When the
student's hand moves to the right of the mirror, this slides in over the top
with the whole day, then slides back out. It is only on screen for a few
seconds, so it renders whatever is cached immediately and refreshes in the
background rather than blocking on the network.
"""

import threading
from datetime import datetime

import requests
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer

from .timetable_widget import _parse_time, _format_time_12h

ACCENT = '#4fc3ff'


def _row(period, state):
    """Build one period row. state is 'done', 'now' or 'upcoming'."""
    if state == 'now':
        edge, time_col, subj_col, room_col = ACCENT, ACCENT, '#ffffff', '#d0d0d0'
    elif state == 'done':
        edge, time_col, subj_col, room_col = '#1c1c1c', '#5a5a5a', '#5a5a5a', '#4a4a4a'
    else:
        edge, time_col, subj_col, room_col = '#2a2a2a', '#8f8f8f', '#ffffff', '#8f8f8f'

    row = QFrame()
    row.setObjectName('PeekRow')
    row.setStyleSheet(f"""
        #PeekRow {{
            background: transparent;
            border: none;
            border-left: 2px solid {edge};
        }}
    """)

    lay = QHBoxLayout(row)
    lay.setContentsMargins(12, 8, 8, 8)
    lay.setSpacing(16)

    raw_start = period.get('startTime') or period.get('start') or period.get('dtstart')
    raw_end = period.get('endTime') or period.get('end') or period.get('dtend')
    span = f"{_format_time_12h(raw_start)}–{_format_time_12h(raw_end)}"

    time_lbl = QLabel(span)
    time_lbl.setFixedWidth(150)
    time_lbl.setStyleSheet(
        f"font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 14px; "
        f"color: {time_col}; background: transparent; border: none;"
    )
    lay.addWidget(time_lbl)

    subj = period.get('subject') or period.get('summary') or '—'
    subj_lbl = QLabel(subj)
    subj_lbl.setStyleSheet(
        f"font-family: 'Segoe UI', system-ui, sans-serif; font-size: 20px; "
        f"font-weight: 700; color: {subj_col}; background: transparent; border: none;"
    )
    lay.addWidget(subj_lbl, 1)

    room = period.get('room') or period.get('location') or ''
    if room:
        room_lbl = QLabel(room)
        room_lbl.setStyleSheet(
            f"font-family: 'Segoe UI', system-ui, sans-serif; font-size: 15px; "
            f"color: {room_col}; background: transparent; border: none;"
        )
        room_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(room_lbl)

    return row


class SchedulePeekWidget(QFrame):
    def __init__(self, parent=None, api_url='https://api.smartmirror.me', user_id=''):
        super().__init__(parent)
        self.api_url = api_url
        self.user_id = user_id
        self.periods = []
        self._lock = threading.Lock()

        self.setObjectName('SchedulePeek')
        self.setStyleSheet("""
            #SchedulePeek {
                background-color: #050505;
                border: none;
                border-left: 1px solid #2a2a2a;
            }
        """)

        self._build_ui()
        self.refresh()

    # ── Build ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(10)

        hdr = QHBoxLayout()
        hdr.setSpacing(12)

        eyebrow = QLabel("TODAY'S TIMETABLE")
        eyebrow.setStyleSheet(
            f"font-family: 'Segoe UI', system-ui, sans-serif; font-size: 13px; "
            f"font-weight: 700; letter-spacing: 2px; color: {ACCENT}; "
            f"background: transparent; border: none;"
        )
        hdr.addWidget(eyebrow)
        hdr.addStretch(1)

        self.date_lbl = QLabel('')
        self.date_lbl.setStyleSheet(
            "font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 12px; "
            "color: #8f8f8f; background: transparent; border: none;"
        )
        hdr.addWidget(self.date_lbl)
        root.addLayout(hdr)

        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet('background: #1c1c1c;')
        root.addWidget(div)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet('background: transparent; border: none;')

        self.rows_container = QWidget()
        self.rows_container.setStyleSheet('background: transparent;')
        self.rows_lay = QVBoxLayout(self.rows_container)
        self.rows_lay.setContentsMargins(0, 6, 0, 6)
        self.rows_lay.setSpacing(6)
        self.rows_lay.addStretch(1)

        self.scroll_area.setWidget(self.rows_container)
        root.addWidget(self.scroll_area, 1)

    # ── Public API ────────────────────────────────────────────────────────

    def set_user_id(self, user_id):
        """Point the panel at a user. Returns True if a refresh was started."""
        if self.user_id != user_id:
            self.user_id = user_id
            with self._lock:
                self.periods = []
            self.refresh()
            return True
        return False

    def refresh(self):
        threading.Thread(target=self._fetch_data, daemon=True).start()

    # ── Fetch ─────────────────────────────────────────────────────────────

    def _fetch_data(self):
        try:
            params = {'user_id': self.user_id} if self.user_id else {}
            res = requests.get(f'{self.api_url}/api/timetable', params=params, timeout=8)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict):
                    periods = data.get('periods', [])
                elif isinstance(data, list):
                    periods = data
                else:
                    periods = []
                with self._lock:
                    self.periods = periods
        except Exception as e:
            print(f'[SchedulePeek] fetch error: {e}')
        QTimer.singleShot(0, self.update_ui)

    # ── Render ────────────────────────────────────────────────────────────

    def update_ui(self):
        while self.rows_lay.count():
            item = self.rows_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        with self._lock:
            periods = list(self.periods)

        now = datetime.now()
        self.date_lbl.setText(now.strftime('%a %d %b').upper())
        now_minutes = now.hour * 60 + now.minute

        if not periods:
            lbl = QLabel('No timetable for today.')
            lbl.setStyleSheet(
                "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 15px; "
                "color: #8f8f8f; font-style: italic; padding: 30px 0; "
                "background: transparent; border: none;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.rows_lay.addWidget(lbl)
            self.rows_lay.addStretch(1)
            return

        current_row = None
        for p in periods:
            start_p = _parse_time(p.get('startTime') or p.get('start') or p.get('dtstart'))
            end_p = _parse_time(p.get('endTime') or p.get('end') or p.get('dtend'))

            state = 'upcoming'
            if start_p and end_p:
                start_m = start_p[0] * 60 + start_p[1]
                end_m = end_p[0] * 60 + end_p[1]
                if now_minutes >= end_m:
                    state = 'done'
                elif start_m <= now_minutes < end_m:
                    state = 'now'
            elif p.get('isNow'):
                state = 'now'
            elif p.get('isDone'):
                state = 'done'

            row = _row(p, state)
            self.rows_lay.addWidget(row)
            if state == 'now':
                current_row = row

        self.rows_lay.addStretch(1)

        # Bring the current class into view — the panel is only up for a few
        # seconds, so the student should not have to hunt for it.
        if current_row is not None:
            QTimer.singleShot(0, lambda: self._reveal(current_row))

    def _reveal(self, row):
        # A re-render between scheduling and firing deletes the row's C++ object.
        try:
            self.scroll_area.ensureWidgetVisible(row, 0, 60)
        except RuntimeError:
            pass
