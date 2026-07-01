# mirror/widgets/timetable_widget.py
import threading
import time
import requests
from datetime import datetime
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QWidget
from PyQt6.QtCore import Qt, QTimer
from .base_widget import Widget

class TimetableWidget(Widget):
    def __init__(self, x, y, w, h, user_id='', api_url='https://api.smartmirror.me',
                 view_mode='today', subject_filter=''):
        super().__init__(x, y, w, h, "", chromeless=True)
        self.api_url = api_url
        self.user_id = user_id
        self.view_mode = view_mode
        self.subject_filter = subject_filter.strip().lower() if subject_filter else ''
        self.periods = []
        self.error_msg = ""
        self._lock = threading.Lock()
        
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.content_layout.setSpacing(8)
        
        self.scroll_area.setWidget(self.content_widget)
        self.main_layout.addWidget(self.scroll_area)
        
        # Timers
        self.fetch_timer = QTimer(self)
        self.fetch_timer.timeout.connect(self._start_fetch)
        self.fetch_timer.start(300000) # every 5 min
        
        self.scroll_timer = QTimer(self)
        self.scroll_timer.timeout.connect(self._auto_scroll)
        self.scroll_timer.start(30)
        
        self._scroll_paused_until = time.time() + 3.0
        
        self._start_fetch()
        
    def set_user_id(self, user_id):
        if self.user_id != user_id:
            self.user_id = user_id
            self._start_fetch()
            
    def _start_fetch(self):
        threading.Thread(target=self._fetch_timetable, daemon=True).start()
        
    def _fetch_timetable(self):
        try:
            params = {'user_id': self.user_id} if self.user_id else {}
            res = requests.get(f"{self.api_url}/api/timetable", params=params, timeout=10)
            res.raise_for_status()
            data = res.json()
            with self._lock:
                self.periods = data.get('periods', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                self.view_mode = data.get('viewMode', self.view_mode) if isinstance(data, dict) else self.view_mode
                self.error_msg = ""
        except Exception as e:
            print(f"[TimetableWidget] Failed to fetch timetable: {e}")
            with self._lock:
                self.error_msg = "No classes today"
                self.periods = []
        QTimer.singleShot(0, self.update_ui)
        
    def _visible_periods(self):
        with self._lock:
            periods = list(self.periods)
            view_mode = self.view_mode
        today_str = datetime.now().strftime('%Y-%m-%d')
        today_periods = [p for p in periods if p.get('date', today_str) == today_str]
        if view_mode == 'week':
            visible = periods
        elif view_mode == 'next':
            now_p = next((p for p in today_periods if p.get('isNow')), None)
            visible = [now_p] if now_p else ([next((p for p in today_periods if not p.get('isDone')), None)] or [])
            visible = [p for p in visible if p]
        elif view_mode == 'remaining':
            visible = [p for p in today_periods if not p.get('isDone')]
        else:
            visible = today_periods
        if self.subject_filter:
            kw = self.subject_filter
            visible = [
                p for p in visible
                if kw in (p.get('subject', p.get('summary', p.get('title', '')))).lower()
                or kw in (p.get('location', p.get('room', ''))).lower()
            ]
        return visible

    def update_ui(self):
        while self.content_layout.count():
            child = self.content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        visible = self._visible_periods()
        
        if not visible:
            lbl = QLabel(self.error_msg or "No classes today", self)
            lbl.setStyleSheet("font-size: 13px; color: rgba(255, 255, 255, 180); font-weight: bold;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.content_layout.addWidget(lbl)
            return
            
        groups = {}
        for p in visible:
            d = p.get('date', 'Today')
            if d not in groups:
                groups[d] = []
            groups[d].append(p)
            
        for dStr in sorted(groups.keys()):
            friendly_date = dStr
            if dStr != 'Today':
                try:
                    dt = datetime.strptime(dStr, '%Y-%m-%d')
                    friendly_date = dt.strftime('%A, %b %d')
                except Exception:
                    pass
            
            # Day header
            header_widget = QWidget()
            h_layout = QHBoxLayout(header_widget)
            h_layout.setContentsMargins(12, 4, 12, 4)
            lbl = QLabel(friendly_date.upper())
            lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #60a5fa;")
            h_layout.addWidget(lbl)
            
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setStyleSheet("background-color: rgba(255, 255, 255, 15); max-height: 1px; border: none;")
            h_layout.addWidget(line, 1)
            
            self.content_layout.addWidget(header_widget)
            
            for period in groups[dStr]:
                card = QFrame()
                card.setObjectName("PeriodCard")
                
                is_now = bool(period.get('isNow', False))
                is_done = bool(period.get('isDone', False))
                
                card.setStyleSheet(f"""
                    #PeriodCard {{
                        background-color: {'rgba(6, 182, 212, 13)' if is_now else 'rgba(255, 255, 255, 5)'};
                        border: 1px solid {'rgba(6, 182, 212, 128)' if is_now else 'rgba(255, 255, 255, 18)'};
                        border-radius: 12px;
                    }}
                """)
                if is_done:
                    card.setWindowOpacity(0.4)
                    
                card_layout = QHBoxLayout(card)
                card_layout.setContentsMargins(14, 12, 14, 12)
                
                start = period.get('startTime', period.get('start', ''))
                end = period.get('endTime', period.get('end', ''))
                time_lbl = QLabel(f"{start} – {end}" if start and end else (start or ''))
                time_lbl.setStyleSheet("font-size: 13px; color: rgba(255, 255, 255, 180); font-weight: bold;")
                card_layout.addWidget(time_lbl)
                
                subject = period.get('subject', period.get('summary', period.get('title', 'Period')))
                subj_lbl = QLabel(subject)
                subj_lbl.setWordWrap(True)
                subj_lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {'#666666' if is_done else '#ffffff'};")
                card_layout.addWidget(subj_lbl, 1)
                
                if period.get('location'):
                    loc_lbl = QLabel(period['location'])
                    loc_lbl.setStyleSheet("""
                        font-size: 13px;
                        color: #93c5fd;
                        background-color: rgba(59, 130, 246, 25);
                        border: 1px solid rgba(59, 130, 246, 51);
                        border-radius: 6px;
                        padding: 3px 8px;
                    """)
                    card_layout.addWidget(loc_lbl)
                    
                if is_now:
                    now_lbl = QLabel("IN PROGRESS")
                    now_lbl.setStyleSheet("""
                        font-size: 12px;
                        font-weight: bold;
                        color: #22d3ee;
                        background-color: rgba(6, 182, 212, 38);
                        border: 1px solid rgba(6, 182, 212, 89);
                        border-radius: 6px;
                        padding: 3px 8px;
                    """)
                    card_layout.addWidget(now_lbl)
                    
                self.content_layout.addWidget(card)
                
        self._scroll_paused_until = time.time() + 3.0
        self.scroll_area.verticalScrollBar().setValue(0)
        
    def _auto_scroll(self):
        now = time.time()
        if now < self._scroll_paused_until:
            return
        bar = self.scroll_area.verticalScrollBar()
        max_val = bar.maximum()
        if max_val <= 0:
            return
            
        new_val = bar.value() + 1
        if new_val >= max_val:
            bar.setValue(0)
            self._scroll_paused_until = now + 3.0
        else:
            bar.setValue(new_val)
