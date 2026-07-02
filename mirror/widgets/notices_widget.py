# mirror/widgets/notices_widget.py
import threading
import time
import requests
import re
from datetime import datetime
from html.parser import HTMLParser

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QWidget, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer, QSize
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


def format_fetched_at(iso_str):
    """Parse ISO8601 timestamp and return human-readable string like 'Tue 1 Jul, 11:33 AM'."""
    if not iso_str:
        return None
    try:
        # Handle offset-aware ISO strings (Python 3.7+ fromisoformat handles most cases)
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime('%-d %b, %I:%M %p').lstrip('0') if hasattr(dt, 'strftime') else None
    except Exception:
        return None


# Category color accents (border-left color)
CAT_COLORS = {
    'General':       '#94a3b8',
    'Sports':        '#22c55e',
    'Meetings':      '#8b5cf6',
    'Academic':      '#3b82f6',
    'Careers':       '#fbbf24',
    'Arts & Culture': '#f43f5e',
    'Service':       '#14b8a6',
}

# Widget width threshold for 2-column layout (pixels)
TWO_COL_MIN_WIDTH = 600


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
        self.fetched_at = None
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
        self.title_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #e6e6e6; letter-spacing: 2px;"
        )

        self.count_label = QLabel("0 notices", self)
        self.count_label.setStyleSheet("font-size: 14px; color: #666666;")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.count_label)
        self.container_layout.addLayout(header_layout)

        # Last-updated label
        self.fetched_at_label = QLabel("", self)
        self.fetched_at_label.setStyleSheet(
            "font-size: 12px; color: rgba(255,255,255,80); padding: 0 14px 4px;"
        )
        self.fetched_at_label.setVisible(False)
        self.container_layout.addWidget(self.fetched_at_label)
        
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
        self.content_layout.setSpacing(8)

        self.scroll_area.setWidget(self.content_widget)
        self.container_layout.addWidget(self.scroll_area)
        
        self.main_layout.addLayout(self.container_layout)

        # Timers
        self.fetch_timer = QTimer(self)
        self.fetch_timer.timeout.connect(self._start_fetch)
        self.fetch_timer.start(600_000)  # every 10 min

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
            data = res.json()
            # Handle both {fetchedAt, notices:[]} wrapper and legacy bare array
            if isinstance(data, list):
                notices = data
                fetched_at = None
            else:
                notices = data.get('notices', [])
                fetched_at = data.get('fetchedAt', None)
            with self._lock:
                self.notices = notices
                self.fetched_at = fetched_at
                self.error_msg = ""
        except Exception as e:
            print(f"[NoticesWidget] Failed to fetch notices: {e}")
            with self._lock:
                self.error_msg = "No notices available"
                self.notices = []
                self.fetched_at = None
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

    def _build_card(self, notice, urgent=False):
        category = notice.get('category', 'General')
        is_urgent = urgent or notice.get('importance', 'normal') == 'high'
        border_color = '#ef4444' if is_urgent else CAT_COLORS.get(category, '#94a3b8')

        card = QFrame()
        card.setObjectName("NoticeCard")
        if is_urgent:
            card.setStyleSheet(f"""
                #NoticeCard {{
                    background-color: rgba(239, 68, 68, 0.07);
                    border: 1px solid rgba(239, 68, 68, 0.18);
                    border-left: 4px solid {border_color};
                    border-radius: 10px;
                }}
            """)
        else:
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
            card_layout.setContentsMargins(12 if not is_urgent else 14, 12 if not is_urgent else 14, 12, 10)
            card_layout.setSpacing(6 if not is_urgent else 8)
            
            row = QHBoxLayout()
            badge_lbl = QLabel("URGENT" if is_urgent else category.upper())
            badge_lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {'#fca5a5' if is_urgent else border_color};")
            row.addWidget(badge_lbl)
            
            years = notice.get('targetYears', ['All'])
            years_str = "Y" + ", Y".join([str(y) for y in years]) if 'All' not in years else "All"
            years_lbl = QLabel(years_str)
            years_lbl.setStyleSheet("font-size: 12px; color: #666666;")
            years_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(years_lbl)
            card_layout.addLayout(row)
            
            title_lbl = QLabel(notice.get('title', ''))
            title_lbl.setWordWrap(True)
            title_lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {'#fca5a5' if is_urgent else '#f2f2f2'};")
            card_layout.addWidget(title_lbl)
            
            details = extract_details(notice.get('notice', ''))
            if details:
                det_row = QHBoxLayout()
                det_row.setSpacing(6)
                for label, key in [('Date', 'date'), ('Time', 'time'), ('Where', 'location')]:
                    if details.get(key):
                        chip = QLabel(f"{label}: {details[key]}")
                        chip.setStyleSheet("""
                            font-size: 12px;
                            color: #bfbfbf;
                            background-color: rgba(255, 255, 255, 15);
                            border-radius: 8px;
                            padding: 3px 8px;
                        """)
                        det_row.addWidget(chip)
                det_row.addStretch()
                card_layout.addLayout(det_row)
                
            body_lbl = QLabel(strip_html(notice.get('notice', '')))
            body_lbl.setWordWrap(True)
            body_lbl.setStyleSheet("font-size: 14px; color: #b8b8b8; line-height: 1.4;")
            card_layout.addWidget(body_lbl)
            
            if notice.get('contact'):
                contact_lbl = QLabel(f"Contact: {notice['contact']}")
                contact_lbl.setStyleSheet("font-size: 13px; color: #666666;")
                card_layout.addWidget(contact_lbl)
                
        return card

    def update_ui(self):
        # Clear existing content
        while self.content_layout.count():
            child = self.content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        with self._lock:
            filtered = [n for n in self.notices if self._passes_filter(n)]
            filtered.sort(key=lambda n: (n.get('importance', 'normal') != 'high'))
            error_msg = self.error_msg
            fetched_at = self.fetched_at

        self.count_label.setText(f"{len(filtered)} notice{'s' if len(filtered) != 1 else ''}")

        # Last-updated label
        label_text = format_fetched_at(fetched_at)
        if label_text:
            self.fetched_at_label.setText(f"Updated: {label_text}")
            self.fetched_at_label.setVisible(True)
        else:
            self.fetched_at_label.setVisible(False)

        if not filtered:
            msg = error_msg or "No notices available today."
            lbl = QLabel(msg, self)
            lbl.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 180); padding: 10px;")
            self.content_layout.addWidget(lbl)
            return

        urgent = [n for n in filtered if n.get('importance', 'normal') == 'high']
        normal = [n for n in filtered if n.get('importance', 'normal') != 'high']

        # Determine if we should use 2-column layout
        widget_width = self.width()
        use_two_col = widget_width >= TWO_COL_MIN_WIDTH and len(normal) >= 2

        # Urgent notices — always full-width at the top
        for notice in urgent:
            card = self._build_card(notice, urgent=True)
            self.content_layout.addWidget(card)

        if urgent and normal:
            # Small spacer between urgent and normal section
            spacer_line = QFrame()
            spacer_line.setFrameShape(QFrame.Shape.HLine)
            spacer_line.setStyleSheet("background: rgba(255,255,255,12); max-height: 1px; border: none; margin: 2px 0;")
            self.content_layout.addWidget(spacer_line)

        # Normal notices — 2-col grid or single column
        if use_two_col:
            grid_widget = QWidget()
            grid_widget.setStyleSheet("background: transparent;")
            grid = QGridLayout(grid_widget)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(8)
            for i, notice in enumerate(normal):
                card = self._build_card(notice)
                grid.addWidget(card, i // 2, i % 2)
            # Distribute columns equally
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            self.content_layout.addWidget(grid_widget)
        else:
            for notice in normal:
                card = self._build_card(notice)
                self.content_layout.addWidget(card)

        self.content_layout.addStretch()

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
