# mirror/widgets/notices_widget.py
import threading
import time
import requests
import re
from html.parser import HTMLParser
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from .base_widget import Widget

class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        s = data.strip()
        if s:
            self.parts.append(s)

    def get_text(self):
        return ' '.join(self.parts)

def strip_html(html_text):
    if not html_text:
        return ''
    try:
        p = _HTMLTextExtractor()
        p.feed(html_text)
        return p.get_text()
    except Exception:
        return re.sub(r'<[^>]+>', ' ', html_text).strip()

def extract_details(html):
    details = {}
    if not html:
        return details
    text = strip_html(html)
    date_m = re.search(
        r'\b\d{1,2}(st|nd|rd|th)?\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*(\s+\d{4})?\b',
        text, re.I,
    ) or re.search(r'\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b', text, re.I)
    time_m = re.search(r'\b\d{1,2}([:.]?\d{2})?\s*(am|pm)\b', text, re.I) or re.search(r'\b\d{1,2}:\d{2}\b', text)
    room_m = (
        re.search(r'\b(Room|Rm|Classroom)\s+([A-Za-z0-9-]+)\b', text, re.I)
        or re.search(r'\b(Library|Auditorium|Hall|Gymnasium|Gym|Main Field|Pool|Music Suite|Performing Arts Centre|PAC)\b', text, re.I)
    )
    if date_m:
        details['date'] = date_m.group(0).strip()
    if time_m:
        details['time'] = time_m.group(0).strip()
    if room_m:
        details['location'] = room_m.group(0).strip()
    return details

class NoticesWidget(Widget):
    def __init__(self, x, y, w, h, api_url='https://api.smartmirror.me',
                 keyword_filter='', scroll_speed=0.5,
                 year_filter='All', cat_filters=None):
        super().__init__(x, y, w, h, "", chromeless=True)
        self.api_url = api_url
        self.keyword_filter = keyword_filter.strip().lower() if keyword_filter else ''
        self.scroll_speed = float(scroll_speed) if scroll_speed else 0.5
        self.year_filter = year_filter
        self.cat_filters = cat_filters
        self.notices = []
        self.error_msg = ""
        self._lock = threading.Lock()
        
        self.setup_ui_elements()
        self._scroll_paused_until = time.time() + 4.0
        self._start_fetch()

    def setup_ui_elements(self):
        # We enforce a clean layout regardless of main_layout orientation
        self.container_layout = QVBoxLayout()
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(6)
        
        # Header layout
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(14, 8, 14, 4)
        self.title_label = QLabel("DAILY NOTICES", self)
        self.title_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #e6e6e6; letter-spacing: 2px;")
        
        self.count_label = QLabel("0 notices", self)
        self.count_label.setStyleSheet("font-size: 12px; color: #666666;")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.count_label)
        self.container_layout.addLayout(header_layout)
        
        # Separator line
        self.sep_line = QFrame(self)
        self.sep_line.setFrameShape(QFrame.Shape.HLine)
        self.sep_line.setStyleSheet("background-color: rgba(255, 255, 255, 18); max-height: 1px; border: none;")
        self.container_layout.addWidget(self.sep_line)
        
        # Scroll Area
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(14, 8, 14, 8)
        self.content_layout.setSpacing(10)
        
        self.scroll_area.setWidget(self.content_widget)
        self.container_layout.addWidget(self.scroll_area)
        
        self.main_layout.addLayout(self.container_layout)
        
        # Timers
        self.fetch_timer = QTimer(self)
        self.fetch_timer.timeout.connect(self._start_fetch)
        self.fetch_timer.start(600000) # every 10 min
        
        self.scroll_timer = QTimer(self)
        self.scroll_timer.timeout.connect(self._auto_scroll)
        self.scroll_timer.start(25)

    def scroll_by_pixels(self, delta_y):
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.value() + delta_y)
        self._scroll_paused_until = time.time() + 5.0

    def on_orientation_changed(self):
        # When orientation is changed, re-setup layout and rebuild the UI
        self.setup_ui_elements()
        self.update_ui()

    def apply_theme(self, primary_color, secondary_color, font_family):
        super().apply_theme(primary_color, secondary_color, font_family)
        font = QFont(font_family)
        if hasattr(self, 'count_label'):
            self.count_label.setFont(font)
        self.update_ui()

    def _start_fetch(self):
        threading.Thread(target=self._fetch_notices, daemon=True).start()
        
    def _fetch_notices(self):
        try:
            res = requests.get(f"{self.api_url}/api/notices", timeout=10)
            res.raise_for_status()
            notices = res.json()
            with self._lock:
                self.notices = notices if isinstance(notices, list) else notices.get('notices', [])
                self.error_msg = ""
        except Exception as e:
            print(f"[NoticesWidget] Failed to fetch notices: {e}")
            with self._lock:
                self.error_msg = "No notices available"
                self.notices = []
        QTimer.singleShot(0, self.update_ui)
        
    def _passes_filter(self, notice):
        if self.year_filter and self.year_filter != 'All':
            target_years = notice.get('targetYears') or notice.get('target_years') or ['All']
            if not isinstance(target_years, list):
                target_years = [target_years]
            target_years_str = [str(y) for y in target_years]
            if 'All' not in target_years_str and self.year_filter not in target_years_str:
                return False

        if self.cat_filters is not None:
            category = notice.get('category', 'General')
            if category not in self.cat_filters:
                return False

        if not self.keyword_filter:
            return True
        haystack = ' '.join([
            notice.get('title', ''),
            notice.get('category', ''),
            notice.get('contact', ''),
            strip_html(notice.get('notice', '')),
        ]).lower()
        return self.keyword_filter in haystack

    def update_ui(self):
        while self.content_layout.count():
            child = self.content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        with self._lock:
            filtered = [n for n in self.notices if self._passes_filter(n)]
            filtered.sort(key=lambda n: (n.get('importance', 'normal') != 'high'))
            error_msg = self.error_msg
            
        self.count_label.setText(f"{len(filtered)} notice{'s' if len(filtered) != 1 else ''}")
        
        if not filtered:
            msg = error_msg or "No notices available today."
            lbl = QLabel(msg, self)
            lbl.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 180); padding: 10px;")
            self.content_layout.addWidget(lbl)
            return
            
        for notice in filtered:
            card = QFrame()
            card.setObjectName("NoticeCard")
            
            category = notice.get('category', 'General')
            is_urgent = notice.get('importance', 'normal') == 'high'
            
            cat_cols = {
                'General': '#94a3b8', 'Sports': '#22c55e', 'Meetings': '#8b5cf6',
                'Academic': '#3b82f6', 'Careers': '#fbbf24', 'Arts & Culture': '#f43f5e',
                'Service': '#14b8a6'
            }
            border_color = '#ef4444' if is_urgent else cat_cols.get(category, '#94a3b8')
            
            card.setStyleSheet(f"""
                #NoticeCard {{
                    background-color: rgba(255, 255, 255, 6);
                    border: 1px solid rgba(255, 255, 255, 18);
                    border-left: 3px solid {border_color};
                    border-radius: 10px;
                }}
            """)
            
            # Setup horizontal layout for notices in horizontal widgets, stack vertically in vertical widgets
            if self.orientation == "horizontal":
                card_layout = QHBoxLayout(card)
                card_layout.setContentsMargins(12, 12, 12, 12)
                card_layout.setSpacing(14)
                
                # Left side badge + title details
                left_side = QWidget()
                left_layout = QVBoxLayout(left_side)
                left_layout.setContentsMargins(0, 0, 0, 0)
                left_layout.setSpacing(4)
                
                badge_lbl = QLabel("URGENT" if is_urgent else category.upper())
                badge_lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {'#fca5a5' if is_urgent else border_color};")
                left_layout.addWidget(badge_lbl)
                
                title_lbl = QLabel(notice.get('title', ''))
                title_lbl.setWordWrap(True)
                title_lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {'#fca5a5' if is_urgent else '#f2f2f2'};")
                left_layout.addWidget(title_lbl)
                
                # Details chip if present
                details = extract_details(notice.get('notice', ''))
                if details:
                    det_row = QHBoxLayout()
                    det_row.setSpacing(6)
                    for label, key in [('Date', 'date'), ('Time', 'time'), ('Where', 'location')]:
                        if details.get(key):
                            chip = QLabel(f"{label}: {details[key]}")
                            chip.setStyleSheet("""
                                font-size: 10px;
                                color: #bfbfbf;
                                background-color: rgba(255, 255, 255, 15);
                                border-radius: 8px;
                                padding: 2px 6px;
                            """)
                            det_row.addWidget(chip)
                    det_row.addStretch()
                    left_layout.addLayout(det_row)
                
                card_layout.addWidget(left_side, 1)
                
                # Right side body description
                body_lbl = QLabel(strip_html(notice.get('notice', '')))
                body_lbl.setWordWrap(True)
                body_lbl.setStyleSheet("font-size: 12px; color: #b8b8b8; line-height: 1.4;")
                card_layout.addWidget(body_lbl, 1)
                
            else:
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(12, 12, 12, 12)
                card_layout.setSpacing(6)
                
                row = QHBoxLayout()
                badge_lbl = QLabel("URGENT" if is_urgent else category.upper())
                badge_lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {'#fca5a5' if is_urgent else border_color};")
                row.addWidget(badge_lbl)
                
                years = notice.get('targetYears', ['All'])
                years_str = "Y" + ", Y".join([str(y) for y in years]) if 'All' not in years else "All"
                years_lbl = QLabel(years_str)
                years_lbl.setStyleSheet("font-size: 10px; color: #666666;")
                years_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
                row.addWidget(years_lbl)
                card_layout.addLayout(row)
                
                title_lbl = QLabel(notice.get('title', ''))
                title_lbl.setWordWrap(True)
                title_lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {'#fca5a5' if is_urgent else '#f2f2f2'};")
                card_layout.addWidget(title_lbl)
                
                details = extract_details(notice.get('notice', ''))
                if details:
                    det_row = QHBoxLayout()
                    det_row.setSpacing(6)
                    for label, key in [('Date', 'date'), ('Time', 'time'), ('Where', 'location')]:
                        if details.get(key):
                            chip = QLabel(f"{label}: {details[key]}")
                            chip.setStyleSheet("""
                                font-size: 10px;
                                color: #bfbfbf;
                                background-color: rgba(255, 255, 255, 15);
                                border-radius: 8px;
                                padding: 2px 6px;
                            """)
                            det_row.addWidget(chip)
                    det_row.addStretch()
                    card_layout.addLayout(det_row)
                    
                body_lbl = QLabel(strip_html(notice.get('notice', '')))
                body_lbl.setWordWrap(True)
                body_lbl.setStyleSheet("font-size: 12px; color: #b8b8b8; line-height: 1.4;")
                card_layout.addWidget(body_lbl)
                
                if notice.get('contact'):
                    contact_lbl = QLabel(f"Contact: {notice['contact']}")
                    contact_lbl.setStyleSheet("font-size: 11px; color: #666666;")
                    card_layout.addWidget(contact_lbl)
                    
            self.content_layout.addWidget(card)
            
        self._scroll_paused_until = time.time() + 4.0
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
            self._scroll_paused_until = now + 2.0
        else:
            bar.setValue(new_val)
