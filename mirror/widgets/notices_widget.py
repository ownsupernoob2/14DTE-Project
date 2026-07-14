# mirror/widgets/notices_widget.py
import threading
import time
import requests
import re
from datetime import datetime
from html.parser import HTMLParser

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QWidget, QSizePolicy, QStackedWidget
)
from PyQt6.QtCore import Qt, QTimer, QMovie
from PyQt6.QtGui import QFont, QFontDatabase


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
        return dt.strftime('%d %b, %I:%M %p').lstrip('0')
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Category colour palette
# ─────────────────────────────────────────────────────────────────────────────

CAT_COLORS = {
    'General':       '#94a3b8',
    'Sports':        '#22c55e',
    'Meetings':      '#8b5cf6',
    'Academic':      '#3b82f6',
    'Careers':       '#fbbf24',
    'Arts & Culture': '#f43f5e',
    'Service':       '#14b8a6',
}

CAT_PILL_STYLES = {
    'General':       ('rgba(148,163,184,0.18)', '#cbd5e1'),
    'Sports':        ('rgba(34,197,94,0.18)',   '#4ade80'),
    'Meetings':      ('rgba(139,92,246,0.18)',  '#a78bfa'),
    'Academic':      ('rgba(59,130,246,0.18)',  '#60a5fa'),
    'Careers':       ('rgba(251,191,36,0.18)',  '#fde047'),
    'Arts & Culture':('rgba(244,63,94,0.18)',   '#fb7185'),
    'Service':       ('rgba(20,184,166,0.18)',  '#2dd4bf'),
}

FONT_FAMILY = 'Hanken Grotesk'


# ─────────────────────────────────────────────────────────────────────────────
# Individual notice card page
# ─────────────────────────────────────────────────────────────────────────────

def _make_card_widget(notice, urgent=False):
    """Build a single notice card as a QWidget (used in the stacked pager)."""
    category = notice.get('category', 'General')
    is_urgent = urgent or notice.get('importance', 'normal') == 'high'

    pill_bg, pill_fg = CAT_PILL_STYLES.get(
        category, ('rgba(148,163,184,0.18)', '#cbd5e1')
    )
    accent = '#ef4444' if is_urgent else CAT_COLORS.get(category, '#94a3b8')

    card = QFrame()
    card.setObjectName('NoticeCard')
    card.setStyleSheet(f"""
        #NoticeCard {{
            background-color: transparent;
            border: none;
            border-left: 3px solid {accent};
            border-radius: 0px;
        }}
    """)

    lay = QVBoxLayout(card)
    lay.setContentsMargins(18, 14, 18, 14)
    lay.setSpacing(8)

    # ── Badge row ──────────────────────────────────────────────────────────
    badge_row = QHBoxLayout()
    badge_row.setSpacing(8)

    cat_badge = QLabel(category)
    cat_badge.setStyleSheet(
        f'font-family: "{FONT_FAMILY}"; font-size: 11px; font-weight: 700; '
        f'color: {pill_fg}; background-color: {pill_bg}; '
        f'border-radius: 6px; padding: 3px 10px; border: none;'
    )
    badge_row.addWidget(cat_badge)

    if is_urgent:
        urg_badge = QLabel('URGENT')
        urg_badge.setStyleSheet(
            f'font-family: "{FONT_FAMILY}"; font-size: 11px; font-weight: 700; '
            'color: #f87171; background-color: rgba(239,68,68,0.18); '
            'border-radius: 6px; padding: 3px 10px; border: none;'
        )
        badge_row.addWidget(urg_badge)

    badge_row.addStretch()
    lay.addLayout(badge_row)

    # ── Title ──────────────────────────────────────────────────────────────
    title_lbl = QLabel(notice.get('title', ''))
    title_lbl.setWordWrap(True)
    title_lbl.setStyleSheet(
        f'font-family: "{FONT_FAMILY}"; font-size: 20px; font-weight: 700; '
        'color: #f8fafc; background: transparent; border: none; line-height: 1.3;'
    )
    lay.addWidget(title_lbl)

    # ── Date / location chips ──────────────────────────────────────────────
    details = extract_details(notice.get('notice', ''))
    chips_to_show = []
    if details.get('date'):
        chips_to_show.append(f"Date: {details['date']}")
    if details.get('location'):
        chips_to_show.append(f"Where: {details['location']}")

    if chips_to_show:
        chip_row = QHBoxLayout()
        chip_row.setSpacing(8)
        for text in chips_to_show:
            chip = QLabel(text)
            chip.setStyleSheet(
                f'font-family: "{FONT_FAMILY}"; font-size: 11px; font-weight: 600; '
                'color: #c084fc; background: transparent; border: none;'
            )
            chip_row.addWidget(chip)
        chip_row.addStretch()
        lay.addLayout(chip_row)

    # ── Body text ─────────────────────────────────────────────────────────
    body_text = strip_html(notice.get('notice', ''))
    if body_text:
        # Truncate to ~4 lines worth
        if len(body_text) > 320:
            body_text = body_text[:320].rsplit(' ', 1)[0] + '…'
        body_lbl = QLabel(body_text)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(
            f'font-family: "{FONT_FAMILY}"; font-size: 13px; color: #94a3b8; '
            'background: transparent; border: none; line-height: 1.5;'
        )
        lay.addWidget(body_lbl)

    # ── Contact ────────────────────────────────────────────────────────────
    if notice.get('contact'):
        contact_lbl = QLabel(f"✦ Contact: {notice['contact']}")
        contact_lbl.setStyleSheet(
            f'font-family: "{FONT_FAMILY}"; font-size: 11px; color: #64748b; '
            'background: transparent; border: none;'
        )
        lay.addWidget(contact_lbl)

    lay.addStretch()
    return card


# ─────────────────────────────────────────────────────────────────────────────
# NoticesWidget — paginated (one notice visible at a time)
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
        self._page = 0          # current notice index
        self._filtered = []     # cached filtered list
        self._auto_advance_paused_until = time.time() + 6.0

        # ── Frame style ──────────────────────────────────────────────────
        self.setObjectName('NoticesWidget')
        self.setStyleSheet("""
            #NoticesWidget {
                background-color: rgba(13, 18, 30, 200);
                border: none;
                border-radius: 16px;
            }
        """)

        # ── Root layout ──────────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ───────────────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet('background: transparent;')
        hdr_lay = QHBoxLayout(header)
        hdr_lay.setContentsMargins(18, 14, 18, 6)
        hdr_lay.setSpacing(8)

        self.title_label = QLabel('Notices')
        self.title_label.setStyleSheet(
            f'font-family: "{FONT_FAMILY}"; font-size: 20px; font-weight: 700; '
            'color: #a5b4fc; letter-spacing: 0.3px; background: transparent; border: none;'
        )

        self.page_label = QLabel('')
        self.page_label.setStyleSheet(
            f'font-family: "{FONT_FAMILY}"; font-size: 11px; color: rgba(255,255,255,40); '
            'background: transparent; border: none;'
        )
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        hdr_lay.addWidget(self.title_label)
        hdr_lay.addStretch()
        hdr_lay.addWidget(self.page_label)
        root.addWidget(header)

        # ── Fetched-at label ─────────────────────────────────────────────
        self.fetched_at_label = QLabel('')
        self.fetched_at_label.setStyleSheet(
            f'font-family: "{FONT_FAMILY}"; font-size: 10px; color: rgba(255,255,255,45); '
            'padding: 0 18px 4px; background: transparent; border: none;'
        )
        self.fetched_at_label.setVisible(False)
        root.addWidget(self.fetched_at_label)

        # ── Divider ──────────────────────────────────────────────────────
        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet('background: rgba(255,255,255,0.07); margin: 0;')
        root.addWidget(div)

        # ── Stacked widget (one card visible at a time) ───────────────────
        self.stack = QStackedWidget()
        self.stack.setStyleSheet('background: transparent;')
        root.addWidget(self.stack, 1)

        # ── Dot indicator ────────────────────────────────────────────────
        self.dot_row = QWidget()
        self.dot_row.setStyleSheet('background: transparent;')
        dot_lay = QHBoxLayout(self.dot_row)
        dot_lay.setContentsMargins(16, 6, 16, 6)
        dot_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dot_lay = dot_lay
        root.addWidget(self.dot_row)

        # ── Gesture footer ───────────────────────────────────────────────
        self.gesture_footer = QWidget()
        self.gesture_footer.setStyleSheet('background: transparent;')
        foot_lay = QVBoxLayout(self.gesture_footer)
        foot_lay.setContentsMargins(16, 8, 16, 18)
        foot_lay.setSpacing(4)
        foot_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # GIF label — large placeholder for gesture animation
        # To use: movie = QMovie('path/to/gesture_left.gif')
        #          self.gif_label.setMovie(movie); movie.start()
        self.gif_label = QLabel()
        self.gif_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gif_label.setMinimumHeight(100)
        self.gif_label.setMaximumHeight(120)
        self.gif_label.setStyleSheet('background: transparent; border: none;')
        foot_lay.addWidget(self.gif_label)

        gesture_lbl = QLabel('Swipe left for more')
        gesture_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gesture_lbl.setStyleSheet(
            f'font-family: "{FONT_FAMILY}"; font-size: 12px; font-weight: 600; '
            'color: rgba(148,163,184,0.65); letter-spacing: 1px; '
            'background: transparent; border: none;'
        )
        foot_lay.addWidget(gesture_lbl)

        root.addWidget(self.gesture_footer)

        # ── Timers ───────────────────────────────────────────────────────
        self.fetch_timer = QTimer(self)
        self.fetch_timer.timeout.connect(self._start_fetch)
        self.fetch_timer.start(600_000)

        # Auto-advance to next notice every ~8 seconds
        self._advance_timer = QTimer(self)
        self._advance_timer.timeout.connect(self._auto_advance)
        self._advance_timer.start(8000)

        self._start_fetch()

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def scroll_by_pixels(self, delta_y):
        """Gesture scroll: positive = go to next notice, negative = previous."""
        if delta_y > 0:
            self._go_next()
        else:
            self._go_prev()
        self._auto_advance_paused_until = time.time() + 8.0

    def apply_theme(self, primary_color, secondary_color, font_family):
        self.update_ui()

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
    # Dot indicator helpers
    # ──────────────────────────────────────────────────────────────────────

    def _rebuild_dots(self, count, current):
        # Clear existing dots
        while self.dot_lay.count():
            item = self.dot_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        max_dots = 7
        for i in range(min(count, max_dots)):
            dot = QLabel()
            is_active = (i == current) or (i == max_dots - 1 and current >= max_dots - 1)
            if is_active:
                dot.setFixedSize(20, 6)
                dot.setStyleSheet(
                    'background: rgba(165,180,252,0.85); border-radius: 3px; border: none;'
                )
            else:
                dot.setFixedSize(6, 6)
                dot.setStyleSheet(
                    'background: rgba(255,255,255,0.2); border-radius: 3px; border: none;'
                )
            self.dot_lay.addWidget(dot)

    # ──────────────────────────────────────────────────────────────────────
    # UI update
    # ──────────────────────────────────────────────────────────────────────

    def update_ui(self):
        # Clear stack
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()

        with self._lock:
            filtered = [n for n in self.notices if self._passes_filter(n)]
            filtered.sort(key=lambda n: n.get('importance', 'normal') != 'high')
            error_msg = self.error_msg
            fetched_at = self.fetched_at

        self._filtered = filtered

        label_text = format_fetched_at(fetched_at)
        if label_text:
            self.fetched_at_label.setText(f'Updated: {label_text}')
            self.fetched_at_label.setVisible(True)
        else:
            self.fetched_at_label.setVisible(False)

        if not filtered:
            msg = error_msg or 'No notices available today.'
            lbl = QLabel(msg)
            lbl.setStyleSheet(
                f'font-family: "{FONT_FAMILY}"; font-size: 14px; '
                'color: rgba(255,255,255,150); padding: 30px; '
                'background: transparent; border: none;'
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            self.stack.addWidget(lbl)
            self.page_label.setText('')
            self._rebuild_dots(0, 0)
            return

        # Clamp page
        self._page = max(0, min(self._page, len(filtered) - 1))

        # Build all card pages
        for notice in filtered:
            card = _make_card_widget(notice)
            self.stack.addWidget(card)

        self.stack.setCurrentIndex(self._page)
        self.page_label.setText(f'{self._page + 1} / {len(filtered)}')
        self._rebuild_dots(len(filtered), self._page)

        self._auto_advance_paused_until = time.time() + 6.0

    # ──────────────────────────────────────────────────────────────────────
    # Pagination
    # ──────────────────────────────────────────────────────────────────────

    def _go_next(self):
        if not self._filtered:
            return
        self._page = (self._page + 1) % len(self._filtered)
        self.stack.setCurrentIndex(self._page)
        self.page_label.setText(f'{self._page + 1} / {len(self._filtered)}')
        self._rebuild_dots(len(self._filtered), self._page)

    def _go_prev(self):
        if not self._filtered:
            return
        self._page = (self._page - 1) % len(self._filtered)
        self.stack.setCurrentIndex(self._page)
        self.page_label.setText(f'{self._page + 1} / {len(self._filtered)}')
        self._rebuild_dots(len(self._filtered), self._page)

    def _auto_advance(self):
        if time.time() < self._auto_advance_paused_until:
            return
        if not self._filtered:
            return
        self._go_next()
