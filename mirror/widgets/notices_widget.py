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

class NoticeDetailModal(QFrame):
    """Full expanded notice modal with AI summary, key details, and full text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NoticeDetailModal")
        self.setStyleSheet("""
            #NoticeDetailModal {
                background-color: #07090e;
                border: 2px solid #38bdf8;
                border-radius: 14px;
            }
        """)
        self.hide()
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        # Header bar
        header = QHBoxLayout()
        self.badge_lbl = QLabel("GENERAL", self)
        self.badge_lbl.setStyleSheet(
            "font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 14px; font-weight: 800; "
            "color: #38bdf8; letter-spacing: 1.5px; background: rgba(56, 189, 248, 0.15); "
            "border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 6px; padding: 4px 10px;"
        )
        header.addWidget(self.badge_lbl)
        header.addStretch(1)

        close_hint = QLabel("TAP ANYWHERE TO CLOSE ✕", self)
        close_hint.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 13px; font-weight: 800; "
            "color: #cbd5e1; letter-spacing: 1px; background: transparent;"
        )
        header.addWidget(close_hint)
        root.addLayout(header)

        # Title
        self.title_lbl = QLabel("", self)
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 26px; font-weight: 800; "
            "color: #ffffff; line-height: 1.25;"
        )
        root.addWidget(self.title_lbl)

        # Metadata Row (Time, Location, Contact)
        self.meta_box = QWidget(self)
        self.meta_box.setStyleSheet("background: #0d131f; border-radius: 8px; border: 1px solid #1e293b;")
        m_lay = QHBoxLayout(self.meta_box)
        m_lay.setContentsMargins(14, 8, 14, 8)
        m_lay.setSpacing(18)

        self.loc_lbl = QLabel("", self.meta_box)
        self.loc_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #38bdf8;")
        m_lay.addWidget(self.loc_lbl)

        self.time_lbl = QLabel("", self.meta_box)
        self.time_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #cbd5e1;")
        m_lay.addWidget(self.time_lbl)

        self.contact_lbl = QLabel("", self.meta_box)
        self.contact_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #f59e0b;")
        m_lay.addWidget(self.contact_lbl)
        m_lay.addStretch(1)
        root.addWidget(self.meta_box)

        # AI Summary Callout Box
        self.summary_box = QWidget(self)
        self.summary_box.setStyleSheet("background: rgba(56, 189, 248, 0.08); border-radius: 8px; border-left: 4px solid #38bdf8;")
        s_lay = QVBoxLayout(self.summary_box)
        s_lay.setContentsMargins(14, 10, 14, 10)
        s_lay.setSpacing(4)
        s_title = QLabel("⚡ QUICK SUMMARY & ACTION ITEMS", self.summary_box)
        s_title.setStyleSheet("font-family: 'Consolas', monospace; font-size: 12px; font-weight: 800; color: #38bdf8; letter-spacing: 1px;")
        s_lay.addWidget(s_title)
        self.summary_text = QLabel("", self.summary_box)
        self.summary_text.setWordWrap(True)
        self.summary_text.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 15px; font-weight: 600; color: #e2e8f0; line-height: 1.4;")
        s_lay.addWidget(self.summary_text)
        root.addWidget(self.summary_box)

        # Full notice body scroll area
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.body_content = QLabel(self.scroll)
        self.body_content.setWordWrap(True)
        self.body_content.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 17px; font-weight: 500; color: #cbd5e1; line-height: 1.5; padding: 4px 0;")
        self.scroll.setWidget(self.body_content)
        root.addWidget(self.scroll, 1)

    def mousePressEvent(self, event):
        self.close_modal()
        event.accept()

    def set_notice(self, notice):
        category = notice.get('category', 'General')
        title = notice.get('title', category)
        raw_body = notice.get('notice', '')
        clean_body = strip_html(raw_body)
        details = extract_details(raw_body)

        self.badge_lbl.setText(category.upper())
        self.title_lbl.setText(title)

        loc = details.get('location') or 'Campus'
        date_time = details.get('time') or details.get('date') or 'Today'
        contact = notice.get('contact', '').strip() or 'Staff'

        self.loc_lbl.setText(f"📍 {loc}")
        self.time_lbl.setText(f"⏰ {date_time}")
        self.contact_lbl.setText(f"👤 {contact}")

        # Synthesize concise summary
        sentences = [s.strip() for s in re.split(r'[.!?\n]+', clean_body) if len(s.strip()) > 8]
        if sentences:
            summary_preview = sentences[0]
            if len(sentences) > 1 and len(summary_preview) < 70:
                summary_preview += f". {sentences[1]}"
            self.summary_text.setText(f"• {summary_preview}.")
            self.summary_box.show()
        else:
            self.summary_box.hide()

        self.body_content.setText(clean_body)

    def close_modal(self):
        self.hide()


class NoticeCard(QFrame):
    """Interactive notice card with hover/tap affordance opening NoticeDetailModal."""

    def __init__(self, notice, on_click=None, parent=None):
        super().__init__(parent)
        self.notice = notice
        self.on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName('NoticeCard')
        self._build_ui()

    def _build_ui(self):
        notice = self.notice
        category = notice.get('category', 'General')
        is_urgent = notice.get('importance', 'normal') == 'high'
        is_medium = category in ['Academic', 'Sports', 'Arts & Culture', 'Careers', 'Meetings']

        title = notice.get('title', category)
        body_raw = notice.get('notice', '')
        body_text = strip_html(body_raw)
        combined = f"{title} {body_text} {category}".lower()

        is_room_change = (
            'room change' in combined or
            'room changes' in combined or
            'relocated' in combined or
            'relocation' in combined or
            'class change' in combined or
            'moved to room' in combined or
            category.lower() in ('room change', 'room changes', 'relocations')
        )

        card_bg = '#0c0c0c'
        border_main = '#1a1a1a'

        if is_urgent:
            border_color = '#ff4d4d'
            meta_color = '#ff4d4d'
            prefix = 'URGENT'
        elif is_room_change:
            border_color = '#38bdf8'
            meta_color = '#38bdf8'
            prefix = 'ROOM CHANGE'
            card_bg = '#091524'
            border_main = '#1e3a5f'
        elif is_medium:
            border_color = '#ffb020'
            meta_color = '#ffb020'
            prefix = category.upper()
        else:
            border_color = '#475569'
            meta_color = '#cbd5e1'
            prefix = category.upper()

        details = extract_details(body_raw)
        date_str = details.get('date', '')
        if not date_str:
            date_str = datetime.now().strftime('%d %B %Y')

        loc_str = details.get('location', '')
        loc_part = f" · {loc_str.upper()}" if loc_str and is_room_change else ""

        self.setStyleSheet(f"""
            #NoticeCard {{
                background-color: {card_bg};
                border: 1px solid {border_main};
                border-left: 4px solid {border_color};
                border-radius: 4px;
            }}
            #NoticeCard:hover {{
                border-color: #38bdf8;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(8)

        # Meta row
        contact = notice.get('contact', '').strip()
        contact_part = f" · SEE {contact.upper()}" if contact else ""
        meta_tag = f"{prefix} · {date_str.upper()}{loc_part}{contact_part}"
        meta_lbl = QLabel(meta_tag, self)
        meta_lbl.setStyleSheet(
            f"font-family: 'Consolas', 'SFMono-Regular', 'Segoe UI', monospace; "
            f"font-size: 15px; font-weight: 800; color: {meta_color}; "
            f"letter-spacing: 1px; background: transparent; border: none;"
        )
        lay.addWidget(meta_lbl)

        # Title
        title_lbl = QLabel(title, self)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 26px; font-weight: 700; "
            "color: #ffffff; background: transparent; border: none; line-height: 1.25;"
        )
        lay.addWidget(title_lbl)

        # Body preview
        if body_text:
            if len(body_text) > 280:
                body_text = body_text[:280].rsplit(' ', 1)[0] + '…'
            body_lbl = QLabel(body_text, self)
            body_lbl.setWordWrap(True)
            body_lbl.setStyleSheet(
                "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 18px; font-weight: 500; "
                "color: #f1f5f9; background: transparent; border: none; line-height: 1.45;"
            )
            lay.addWidget(body_lbl)

        # Subtle tap-to-expand prompt footer
        footer = QHBoxLayout()
        footer.addStretch(1)
        expand_hint = QLabel("🔎 TAP TO EXPAND & SUMMARIZE", self)
        expand_hint.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 11px; font-weight: 700; "
            "color: #64748b; letter-spacing: 0.5px; background: transparent; border: none;"
        )
        footer.addWidget(expand_hint)
        lay.addLayout(footer)

    def mousePressEvent(self, event):
        if self.on_click:
            self.on_click(self.notice)
        super().mousePressEvent(event)


def _make_notice_card(notice, on_click=None):
    """Build a single notice card QFrame."""
    return NoticeCard(notice, on_click=on_click)


def _make_downtime_card(message='Server is experiencing downtime'):
    """Build a prominent, high-contrast downtime alert card matching NoticeCard style."""
    card = QFrame()
    card.setObjectName('NoticeCard')
    card.setStyleSheet("""
        #NoticeCard {
            background-color: #0c0c0c;
            border: 1px solid #2e1010;
            border-left: 5px solid #ef4444;
            border-radius: 4px;
        }
    """)

    lay = QVBoxLayout(card)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(10)

    meta_lbl = QLabel("STATUS · SYSTEM ALERT")
    meta_lbl.setStyleSheet(
        "font-family: 'Consolas', 'SFMono-Regular', monospace; "
        "font-size: 16px; font-weight: 800; color: #ef4444; "
        "letter-spacing: 1.5px; background: transparent; border: none;"
    )
    lay.addWidget(meta_lbl)

    title_lbl = QLabel(message)
    title_lbl.setWordWrap(True)
    title_lbl.setStyleSheet(
        "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 28px; font-weight: 800; "
        "color: #ffffff; background: transparent; border: none; line-height: 1.25;"
    )
    lay.addWidget(title_lbl)

    body_lbl = QLabel("School notices cannot be fetched right now.")
    body_lbl.setWordWrap(True)
    body_lbl.setStyleSheet(
        "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 18px; font-weight: 600; "
        "color: #cbd5e1; background: transparent; border: none; line-height: 1.45;"
    )
    lay.addWidget(body_lbl)

    return card


def _make_placeholder_card():
    """Build a skeleton notice card box to preserve layout and allow gesture scrolling."""
    card = QFrame()
    card.setObjectName('NoticeCard')
    card.setStyleSheet("""
        #NoticeCard {
            background-color: #0c0c0c;
            border: 1px solid #1a1a1a;
            border-left: 4px solid #334155;
            border-radius: 4px;
            min-height: 120px;
        }
    """)

    lay = QVBoxLayout(card)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(12)

    bar1 = QWidget()
    bar1.setFixedSize(140, 14)
    bar1.setStyleSheet("background-color: #1e293b; border-radius: 3px; border: none;")
    lay.addWidget(bar1)

    bar2 = QWidget()
    bar2.setFixedHeight(22)
    bar2.setStyleSheet("background-color: #242c3d; border-radius: 4px; border: none;")
    lay.addWidget(bar2)

    bar3 = QWidget()
    bar3.setFixedHeight(16)
    bar3.setStyleSheet("background-color: #1a2230; border-radius: 3px; border: none;")
    lay.addWidget(bar3)

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

        # Gesture state. A tap holds the list still indefinitely (so you can
        # finish reading a long notice); that is separate from the short
        # automatic pause a manual scroll gives you.
        self._scroll_paused = False
        self._gesture_active = False

        # ── Frame style ──────────────────────────────────────────────────
        self.setObjectName('NoticesWidget')
        self._apply_frame_style()

        # ── Root layout ──────────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # ── Header row ───────────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet('background: transparent;')
        hdr_lay = QHBoxLayout(header)
        hdr_lay.setContentsMargins(0, 0, 0, 4)
        hdr_lay.setSpacing(12)

        # Left: "Notices" + "Updated ..."
        self.title_label = QLabel('Notices')
        self.title_label.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 32px; font-weight: 800; "
            "color: #ffffff; letter-spacing: 0.2px; background: transparent; border: none;"
        )
        hdr_lay.addWidget(self.title_label)

        self.fetched_at_label = QLabel('')
        self.fetched_at_label.setStyleSheet(
            "font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 15px; font-weight: 600; "
            "color: #cbd5e1; background: transparent; border: none;"
        )
        self.fetched_at_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        hdr_lay.addWidget(self.fetched_at_label)

        hdr_lay.addStretch(1)

        # Right: "1 today"
        self.count_label = QLabel('')
        self.count_label.setStyleSheet(
            "font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 26px; font-weight: 800; "
            "color: #ffffff; background: transparent; border: none;"
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
        self.fetch_timer.start(15_000)

        # Auto-scroll ticker (every 30ms)
        self.scroll_timer = QTimer(self)
        self.scroll_timer.timeout.connect(self._auto_scroll_tick)
        self.scroll_timer.start(30)

        # Notice detail inspection modal overlay
        self.modal = NoticeDetailModal(self)

        self._start_fetch()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'modal') and self.modal is not None:
            self.modal.setGeometry(12, 12, max(100, self.width() - 24), max(100, self.height() - 24))

    def open_modal(self, notice):
        """Open detailed modal inspection with AI summary for selected notice."""
        if hasattr(self, 'modal') and self.modal is not None:
            self.modal.set_notice(notice)
            self.modal.setGeometry(12, 12, max(100, self.width() - 24), max(100, self.height() - 24))
            self.modal.show()
            self.modal.raise_()
            self._scroll_paused = True

    def close_modal(self):
        """Dismiss notice detail modal."""
        if hasattr(self, 'modal') and self.modal is not None:
            self.modal.close_modal()

    @property
    def modal_open(self):
        return hasattr(self, 'modal') and self.modal is not None and self.modal.isVisible()

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def scroll_by_pixels(self, delta_y):
        """Manual scroll clamping cleanly within scrollbar limits."""
        if self.modal_open:
            return
        sb = self.scroll_area.verticalScrollBar()
        cur = sb.value()
        self._auto_scroll_paused_until = time.time() + 10.0
        sb.setValue(cur + int(delta_y))

    @property
    def scroll_paused(self):
        return self._scroll_paused

    def toggle_scroll_pause(self):
        """Tap handler: close modal if open, else toggle pause/resume."""
        if self.modal_open:
            self.close_modal()
            return self._scroll_paused

        self._scroll_paused = not self._scroll_paused
        if not self._scroll_paused:
            # A beat before it starts moving again, so resuming isn't jarring.
            self._auto_scroll_paused_until = time.time() + 1.5
        # The border carries this — a tap has to give some feedback, or you
        # cannot tell whether it registered.
        self._apply_frame_style()
        return self._scroll_paused

    def set_gesture_active(self, active, variant='A'):
        """Show/hide the 'your hand is controlling this panel' affordance."""
        active = bool(active)
        self._variant = variant
        if active == self._gesture_active:
            return
        self._gesture_active = active
        self._apply_frame_style()

    def reset_gesture_state(self):
        """Forget tap-pause and affordance — the mirror changed who it's showing."""
        if self.modal_open:
            self.close_modal()
        self._scroll_paused = False
        self._variant = 'A'
        self.set_gesture_active(False)
        self._apply_frame_style()

    def _apply_frame_style(self):
        """The panel's border is the whole gesture affordance.

        Variant A: Bold, thick high-contrast highlight border (4px solid #38bdf8).
        Variant B: Crisp minimal border (2px solid rgba(255,255,255,0.8)) since on-screen cursor dot gives primary continuous feedback.
        """
        variant = getattr(self, '_variant', 'A')
        if self._scroll_paused or self._gesture_active:
            if variant == 'A':
                border = '4px solid #38bdf8'
            else:
                border = '2px solid rgba(255, 255, 255, 0.85)'
        else:
            border = '4px solid transparent' if variant == 'A' else '2px solid transparent'

        self.setStyleSheet(f"""
            #NoticesWidget {{
                background-color: #000000;
                border: {border};
                border-right: 1px solid #1c1c1c;
                border-radius: 6px;
            }}
        """)

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

            # Fetch remote notice configuration
            try:
                cfg_res = requests.get(f'{self.api_url}/api/notices/config', timeout=5)
                if cfg_res.status_code == 200:
                    cfg = cfg_res.json()
                    if isinstance(cfg, dict):
                        if 'yearFilter' in cfg:
                            self.year_filter = cfg['yearFilter']
                        if 'catFilters' in cfg and isinstance(cfg['catFilters'], list):
                            self.cat_filters = cfg['catFilters']
                        if 'catOrder' in cfg and isinstance(cfg['catOrder'], list):
                            self.cat_order = cfg['catOrder']
                        if 'className' in cfg:
                            self.class_name = str(cfg['className']).strip()
                        if 'keywordFilter' in cfg:
                            kf = cfg['keywordFilter']
                            if isinstance(kf, list):
                                self.keyword_filter = ','.join(kf)
                            else:
                                self.keyword_filter = str(kf or '').strip().lower()
            except Exception:
                pass

            with self._lock:
                self.notices = notices
                self.fetched_at = fetched_at
                self.error_msg = ''
        except Exception as e:
            print(f'[NoticesWidget] fetch error: {e}')
            with self._lock:
                self.error_msg = 'Server is experiencing downtime'
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

        if self.cat_filters is not None and len(self.cat_filters) > 0:
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
            cat_order_list = getattr(self, 'cat_order', [])
            user_cls = getattr(self, 'class_name', '').lower()

            def _priority(n):
                t_and_b = f"{n.get('title', '')} {strip_html(n.get('notice', ''))} {n.get('category', '')}".lower()
                is_urg = n.get('importance', 'normal') == 'high'
                is_rc = ('room change' in t_and_b or 'relocated' in t_and_b or
                         'relocation' in t_and_b or 'class change' in t_and_b or
                         'moved to room' in t_and_b or n.get('category', '').lower() in ('room change', 'room changes'))
                is_user_class = bool(user_cls and user_cls in t_and_b)

                if is_user_class or (is_urg and is_rc):
                    return (0, 0)
                if is_rc:
                    return (1, 0)
                if is_urg:
                    return (2, 0)

                cat = n.get('category', 'General')
                if cat_order_list and cat in cat_order_list:
                    return (3, cat_order_list.index(cat))
                if cat in ['Academic', 'Sports', 'Arts & Culture', 'Careers', 'Meetings']:
                    return (4, 0)
                return (5, 0)

            filtered.sort(key=_priority)
            error_msg = self.error_msg
            fetched_at = self.fetched_at

        self._filtered = filtered

        # Update header labels
        if error_msg:
            self.title_label.setText('Notices unavailable')
        else:
            self.title_label.setText('Notices')

        label_text = format_fetched_at(fetched_at)
        if label_text:
            self.fetched_at_label.setText(f"Updated {label_text}")
            self.fetched_at_label.setVisible(True)
        else:
            self.fetched_at_label.setVisible(False)

        count_text = f"{len(filtered)} today" if filtered else "0 today"
        self.count_label.setText(count_text)

        if not filtered:
            if error_msg:
                # Top downtime notice card in large bold typography
                self.cards_lay.addWidget(_make_downtime_card(error_msg))
            else:
                msg = 'No notices available today.'
                lbl = QLabel(msg)
                lbl.setStyleSheet(
                    "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 22px; font-weight: 700; "
                    "color: #cbd5e1; padding: 24px 12px; background: transparent; border: none;"
                )
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.cards_lay.addWidget(lbl)

            # Preserve skeleton placeholder cards so layout stays intact and scrollable
            for _ in range(3):
                self.cards_lay.addWidget(_make_placeholder_card())

            self.cards_lay.addStretch(1)
            self._auto_scroll_paused_until = time.time() + 4.0
            return

        # Add cards
        for notice in filtered:
            card = _make_notice_card(notice, on_click=self.open_modal)
            self.cards_lay.addWidget(card)

        self.cards_lay.addStretch(1)
        self._auto_scroll_paused_until = time.time() + 4.0

    # ──────────────────────────────────────────────────────────────────────
    # Auto scroll loop
    # ──────────────────────────────────────────────────────────────────────

    def _auto_scroll_tick(self):
        now = time.time()
        if self._scroll_paused or self._gesture_active or now < self._auto_scroll_paused_until:
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

