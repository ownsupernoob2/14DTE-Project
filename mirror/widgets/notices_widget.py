# mirror/widgets/notices_widget.py
import threading
import time
import requests
import re
from datetime import datetime
from html.parser import HTMLParser

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QWidget, QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont


# ─────────────────────────────────────────────────────────────────────────────
# HTML helpers
# ─────────────────────────────────────────────────────────────────────────────

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
    time_m = re.search(r'\b\d{1,2}([:.]?\d{2})?\s*(am|pm)\b', text, re.I) \
             or re.search(r'\b\d{1,2}:\d{2}\b', text)
    room_m = (
        re.search(r'\b(Room|Rm|Classroom)\s+([A-Za-z0-9-]+)\b', text, re.I)
        or re.search(
            r'\b(Library|Auditorium|Hall|Gymnasium|Gym|Main Field|Pool|'
            r'Music Suite|Performing Arts Centre|PAC)\b', text, re.I
        )
    )
    if date_m:
        details['date'] = date_m.group(0).strip()
    if time_m:
        details['time'] = time_m.group(0).strip()
    if room_m:
        details['location'] = room_m.group(0).strip()
    return details


def format_fetched_at(iso_str):
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime('%a, %d %b, %I:%M %p').lstrip('0')
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Notice Card matching the web UI
# ─────────────────────────────────────────────────────────────────────────────

def _make_notice_card(notice):
    """Build a single notice card QFrame matching the web screenshot."""
    category = notice.get('category', 'General')
    is_urgent = notice.get('importance', 'normal') == 'high'
    is_medium = category in ['Academic', 'Sports', 'Arts & Culture', 'Careers', 'Meetings']

    if is_urgent:
        border_color = '#ff4d4d'
        meta_color = '#ff4d4d'
    elif is_medium:
        border_color = '#ffb020'
        meta_color = '#ffb020'
    else:
        border_color = '#3a3a3a'
        meta_color = '#8f8f8f'

    details = extract_details(notice.get('notice', ''))
    date_str = details.get('date', '')
    if not date_str:
        date_str = datetime.now().strftime('%d %B %Y')

    card = QFrame()
    card.setObjectName('NoticeCard')
    card.setStyleSheet(f"""
        #NoticeCard {{
            background-color: #0a0a0a;
            border: none;
            border-left: 3px solid {border_color};
            border-radius: 0px;
        }}
    """)

    lay = QVBoxLayout(card)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(4)

    # ── Meta row: CATEGORY · DATE ─────────────────────────────────────────
    meta_tag = f"URGENT · {date_str.upper()}" if is_urgent else f"{category.upper()} · {date_str.upper()}"
    meta_lbl = QLabel(meta_tag)
    meta_lbl.setStyleSheet(
        f"font-family: 'Consolas', 'SFMono-Regular', 'Segoe UI', monospace; "
        f"font-size: 11px; font-weight: 700; color: {meta_color}; "
        f"letter-spacing: 0.5px; background: transparent; border: none;"
    )
    lay.addWidget(meta_lbl)

    # ── Title ──────────────────────────────────────────────────────────────
    title_text = notice.get('title', category)
    title_lbl = QLabel(title_text)
    title_lbl.setWordWrap(True)
    title_lbl.setStyleSheet(
        "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 18px; font-weight: 700; "
        "color: #ffffff; background: transparent; border: none; line-height: 1.2;"
    )
    lay.addWidget(title_lbl)

    # ── Body text preview ──────────────────────────────────────────────────
    body_text = strip_html(notice.get('notice', ''))
    if body_text:
        if len(body_text) > 180:
            body_text = body_text[:180].rsplit(' ', 1)[0] + '…'
        body_lbl = QLabel(body_text)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 13px; color: #d0d0d0; "
            "background: transparent; border: none; line-height: 1.4;"
        )
        lay.addWidget(body_lbl)

    # ── Contact (if present) ───────────────────────────────────────────────
    contact = notice.get('contact', '').strip()
    if contact:
        contact_lbl = QLabel(f"See {contact}")
        contact_lbl.setStyleSheet(
            "font-family: 'Consolas', 'SFMono-Regular', 'Segoe UI', monospace; "
            "font-size: 11px; color: #8f8f8f; background: transparent; border: none; margin-top: 2px;"
        )
        lay.addWidget(contact_lbl)

    return card


# ─────────────────────────────────────────────────────────────────────────────
# NoticesWidget (Left column panel matching web screenshot)
# ─────────────────────────────────────────────────────────────────────────────

class NoticesWidget(QFrame):
    def __init__(self, x=0, y=0, w=100, h=100,
                 api_url='https://api.smartmirror.me',
                 keyword_filter='', scroll_speed=0.5,
                 year_filter='All', cat_filters=None,
                 parent=None):
        super().__init__(parent)
        self.setGeometry(x, y, w, h)
        self.api_url = api_url
        self.keyword_filter = keyword_filter.strip().lower() if keyword_filter else ''
        self.scroll_speed = float(scroll_speed) if scroll_speed else 0.5
        self.year_filter = year_filter
        self.cat_filters = cat_filters
        self.notices = []
        self.fetched_at = None
        self.error_msg = ''
        self._lock = threading.Lock()
        self._filtered = []

        # Auto scroll state
        self._auto_scroll_paused_until = time.time() + 4.0
        self._hold_bottom_until = 0.0

        # ── Frame style ──────────────────────────────────────────────────
        self.setObjectName('NoticesWidget')
        self.setStyleSheet("""
            #NoticesWidget {
                background-color: #000000;
                border: none;
                border-right: 1px solid #1c1c1c;
            }
        """)

        # ── Root layout ──────────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # ── Header row ───────────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet('background: transparent;')
        hdr_lay = QHBoxLayout(header)
        hdr_lay.setContentsMargins(0, 0, 0, 4)
        hdr_lay.setSpacing(10)

        # Left: "Notices" + "Updated ..."
        self.title_label = QLabel('Notices')
        self.title_label.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 22px; font-weight: 700; "
            "color: #ffffff; letter-spacing: 0.2px; background: transparent; border: none;"
        )
        hdr_lay.addWidget(self.title_label)

        self.fetched_at_label = QLabel('')
        self.fetched_at_label.setStyleSheet(
            "font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 11px; "
            "color: #8f8f8f; background: transparent; border: none;"
        )
        self.fetched_at_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        hdr_lay.addWidget(self.fetched_at_label)

        hdr_lay.addStretch(1)

        # Right: "1 today"
        self.count_label = QLabel('')
        self.count_label.setStyleSheet(
            "font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 13px; "
            "color: #d0d0d0; background: transparent; border: none;"
        )
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hdr_lay.addWidget(self.count_label)

        root.addWidget(header)

        # ── Divider line ─────────────────────────────────────────────────
        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet('background: #1c1c1c; margin-bottom: 4px;')
        root.addWidget(div)

        # ── Scroll Area for cards ────────────────────────────────────────
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_lay = QVBoxLayout(self.cards_container)
        self.cards_lay.setContentsMargins(0, 4, 0, 4)
        self.cards_lay.setSpacing(12)
        self.cards_lay.addStretch(1)

        self.scroll_area.setWidget(self.cards_container)
        root.addWidget(self.scroll_area, 1)

        # ── Timers ───────────────────────────────────────────────────────
        self.fetch_timer = QTimer(self)
        self.fetch_timer.timeout.connect(self._start_fetch)
        self.fetch_timer.start(600_000)

        # Auto-scroll ticker (every 30ms)
        self.scroll_timer = QTimer(self)
        self.scroll_timer.timeout.connect(self._auto_scroll_tick)
        self.scroll_timer.start(30)

        self._start_fetch()

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def scroll_by_pixels(self, delta_y):
        """Manual scroll (e.g. from hand gesture)."""
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.value() + int(delta_y))
        self._auto_scroll_paused_until = time.time() + 6.0

    def apply_theme(self, primary_color, secondary_color, font_family):
        pass

    # ──────────────────────────────────────────────────────────────────────
    # Fetch
    # ──────────────────────────────────────────────────────────────────────

    def _start_fetch(self):
        threading.Thread(target=self._fetch_notices, daemon=True).start()

    def _fetch_notices(self):
        try:
            res = requests.get(f'{self.api_url}/api/notices', timeout=10)
            res.raise_for_status()
            data = res.json()
            if isinstance(data, list):
                notices = data
                fetched_at = None
            else:
                notices = data.get('notices', [])
                fetched_at = data.get('fetchedAt', None)
            with self._lock:
                self.notices = notices
                self.fetched_at = fetched_at
                self.error_msg = ''
        except Exception as e:
            print(f'[NoticesWidget] fetch error: {e}')
            with self._lock:
                self.error_msg = 'No notices available'
                self.notices = []
                self.fetched_at = None
        QTimer.singleShot(0, self.update_ui)

    # ──────────────────────────────────────────────────────────────────────
    # Filtering
    # ──────────────────────────────────────────────────────────────────────

    def _passes_filter(self, notice):
        if self.year_filter and self.year_filter != 'All':
            target_years = (notice.get('targetYears')
                            or notice.get('target_years') or ['All'])
            if not isinstance(target_years, list):
                target_years = [target_years]
            if 'All' not in [str(y) for y in target_years] \
                    and self.year_filter not in [str(y) for y in target_years]:
                return False

        if self.cat_filters is not None:
            if notice.get('category', 'General') not in self.cat_filters:
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

    # ──────────────────────────────────────────────────────────────────────
    # UI update
    # ──────────────────────────────────────────────────────────────────────

    def update_ui(self):
        # Clear existing cards
        while self.cards_lay.count():
            item = self.cards_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        with self._lock:
            filtered = [n for n in self.notices if self._passes_filter(n)]
            filtered.sort(key=lambda n: n.get('importance', 'normal') != 'high')
            error_msg = self.error_msg
            fetched_at = self.fetched_at

        self._filtered = filtered

        # Update header labels
        label_text = format_fetched_at(fetched_at)
        if label_text:
            self.fetched_at_label.setText(f"Updated {label_text}")
            self.fetched_at_label.setVisible(True)
        else:
            self.fetched_at_label.setVisible(False)

        count_text = f"{len(filtered)} today" if filtered else "0 today"
        self.count_label.setText(count_text)

        if not filtered:
            msg = error_msg or 'No notices available today.'
            lbl = QLabel(msg)
            lbl.setStyleSheet(
                "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 14px; "
                "color: #8f8f8f; padding: 40px 20px; font-style: italic;"
                "background: transparent; border: none;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            self.cards_lay.addWidget(lbl)
            self.cards_lay.addStretch(1)
            return

        # Add cards
        for notice in filtered:
            card = _make_notice_card(notice)
            self.cards_lay.addWidget(card)

        self.cards_lay.addStretch(1)
        self._auto_scroll_paused_until = time.time() + 4.0

    # ──────────────────────────────────────────────────────────────────────
    # Auto scroll loop
    # ──────────────────────────────────────────────────────────────────────

    def _auto_scroll_tick(self):
        now = time.time()
        if now < self._auto_scroll_paused_until:
            return

        sb = self.scroll_area.verticalScrollBar()
        max_val = sb.maximum()
        if max_val <= 0:
            return

        cur_val = sb.value()
        if cur_val >= max_val - 1:
            if self._hold_bottom_until == 0.0:
                self._hold_bottom_until = now + 2.0
            elif now >= self._hold_bottom_until:
                sb.setValue(0)
                self._hold_bottom_until = 0.0
                self._auto_scroll_paused_until = now + 4.0
        else:
            sb.setValue(cur_val + 1)

