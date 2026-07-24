# mirror/widgets/timetable_widget.py
import threading
import time
import requests
from datetime import datetime
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont


class TimetableWidget(QFrame):
    """Class focus widget matching new-style.html (CURRENT CLASS hero + details + NEXT class block)."""

    def __init__(self, parent=None, api_url='https://api.smartmirror.me', user_id='', view_mode='today', subject_filter=''):
        super().__init__(parent)
        self.setObjectName("TimetableWidget")
        self.setStyleSheet("background: transparent; border: none;")
        self.api_url = api_url
        self.user_id = user_id
        self.view_mode = view_mode
        self.subject_filter = subject_filter
        self.periods = []
        self._lock = threading.Lock()

        self._build_ui()
        self._start_fetch()

        self.fetch_timer = QTimer(self)
        self.fetch_timer.timeout.connect(self._start_fetch)
        self.fetch_timer.start(300000)

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 10)
        lay.setSpacing(24)

        # ── CURRENT CLASS BLOCK ──────────────────────────────────────────
        current_box = QWidget(self)
        current_box.setStyleSheet("background: transparent;")
        c_lay = QVBoxLayout(current_box)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(8)

        self.eyebrow_lbl = QLabel("CURRENT CLASS", current_box)
        self.eyebrow_lbl.setStyleSheet(
            "font-family: 'Segoe UI', sans-serif; font-size: 14px; font-weight: 700; "
            "letter-spacing: 2px; color: #4fc3ff; text-transform: uppercase;"
        )
        c_lay.addWidget(self.eyebrow_lbl)

        self.subject_lbl = QLabel("13DTE", current_box)
        self.subject_lbl.setStyleSheet(
            "font-family: 'Segoe UI', sans-serif; font-size: 90px; font-weight: 700; "
            "color: #ffffff; line-height: 0.95; margin: 0;"
        )
        c_lay.addWidget(self.subject_lbl)

        # Details Row (ROOM, ENDS, LEFT)
        details_row = QHBoxLayout()
        details_row.setContentsMargins(0, 10, 0, 0)
        details_row.setSpacing(36)

        # Room
        room_box = QVBoxLayout()
        r_k = QLabel("ROOM", current_box)
        r_k.setStyleSheet("font-family: 'Segoe UI', sans-serif; font-size: 13px; color: #d0d0d0; letter-spacing: 1px;")
        self.room_v = QLabel("T5", current_box)
        self.room_v.setStyleSheet("font-family: 'Segoe UI', sans-serif; font-size: 28px; font-weight: 700; color: #ffffff;")
        room_box.addWidget(r_k)
        room_box.addWidget(self.room_v)
        details_row.addLayout(room_box)

        # Ends
        ends_box = QVBoxLayout()
        e_k = QLabel("ENDS", current_box)
        e_k.setStyleSheet("font-family: 'Segoe UI', sans-serif; font-size: 13px; color: #d0d0d0; letter-spacing: 1px;")
        self.ends_v = QLabel("1:00pm", current_box)
        self.ends_v.setStyleSheet("font-family: 'Segoe UI', sans-serif; font-size: 28px; font-weight: 700; color: #ffffff;")
        ends_box.addWidget(e_k)
        ends_box.addWidget(self.ends_v)
        details_row.addLayout(ends_box)

        # Left
        left_box = QVBoxLayout()
        l_k = QLabel("LEFT", current_box)
        l_k.setStyleSheet("font-family: 'Segoe UI', sans-serif; font-size: 13px; color: #d0d0d0; letter-spacing: 1px;")
        self.left_v = QLabel("19m", current_box)
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
                padding-top: 20px;
                background: transparent;
            }
        """)
        n_lay = QHBoxLayout(next_box)
        n_lay.setContentsMargins(0, 16, 0, 0)
        n_lay.setSpacing(16)

        next_eyebrow = QLabel("NEXT", next_box)
        next_eyebrow.setStyleSheet(
            "font-family: 'Segoe UI', sans-serif; font-size: 14px; font-weight: 700; "
            "letter-spacing: 2px; color: #8f8f8f; text-transform: uppercase;"
        )
        n_lay.addWidget(next_eyebrow)

        next_info_box = QVBoxLayout()
        self.next_subj_lbl = QLabel("13PHY", next_box)
        self.next_subj_lbl.setStyleSheet("font-family: 'Segoe UI', sans-serif; font-size: 36px; font-weight: 700; color: #ffffff;")
        self.next_meta_lbl = QLabel("Lab 4 · 1:00pm", next_box)
        self.next_meta_lbl.setStyleSheet("font-family: 'Segoe UI', sans-serif; font-size: 15px; color: #d0d0d0;")

        next_info_box.addWidget(self.next_subj_lbl)
        next_info_box.addWidget(self.next_meta_lbl)
        n_lay.addLayout(next_info_box, 1)

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

        current = next((p for p in periods if p.get('isNow')), None) or next((p for p in periods if not p.get('isDone')), None)
        next_p = next((p for p in periods if p != current and not p.get('isDone')), None)

        if current:
            self.subject_lbl.setText(current.get('subject', current.get('summary', '13DTE')))
            self.room_v.setText(current.get('room', current.get('location', 'T5')))
            self.ends_v.setText(current.get('endTime', current.get('end', '1:00pm')))
        else:
            self.subject_lbl.setText("13DTE")
            self.room_v.setText("T5")
            self.ends_v.setText("1:00pm")

        if next_p:
            self.next_subj_lbl.setText(next_p.get('subject', next_p.get('summary', '13PHY')))
            loc = next_p.get('room', next_p.get('location', 'Lab 4'))
            time_str = next_p.get('startTime', next_p.get('start', '1:00pm'))
            self.next_meta_lbl.setText(f"{loc} · {time_str}")
        else:
            self.next_subj_lbl.setText("13PHY")
            self.next_meta_lbl.setText("Lab 4 · 1:00pm")

