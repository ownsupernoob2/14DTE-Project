# mirror/widgets/notices_widget.py
import threading
import time
import requests
import re
from datetime import datetime
from html.parser import HTMLParser

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QWidget, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRectF, QVariantAnimation, QEasingCurve
from PyQt6.QtGui import QPainter, QPen, QColor, QFont

NOTICE_CARD_RADIUS = 6
SELECT_BORDER_PX = 3.0     # same animated white border as the King's Week cards


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
    """Full expanded notice overlay showing clear large typography and full text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NoticeDetailModal")
        self.setStyleSheet("""
            #NoticeDetailModal {
                background-color: #111111;
                border: none;
                border-radius: 8px;
            }
        """)
        self.hide()
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(18)

        # Header bar
        header = QHBoxLayout()
        self.badge_lbl = QLabel("GENERAL", self)
        self.badge_lbl.setStyleSheet(
            "font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 15px; font-weight: 800; "
            "color: #ffffff; letter-spacing: 1.5px; background: rgba(255, 255, 255, 0.12); "
            "border: 1px solid rgba(255, 255, 255, 0.3); border-radius: 6px; padding: 6px 14px;"
        )
        header.addWidget(self.badge_lbl)
        header.addStretch(1)
        close_hint = QLabel("PINCH TO CLOSE", self)     # same as King's Week
        close_hint.setStyleSheet(
            "font-size: 15px; font-weight: 800; letter-spacing: 1.5px; "
            "color: #cbd5e1; background: transparent; border: none;"
        )
        header.addWidget(close_hint)
        root.addLayout(header)

        # Title
        self.title_lbl = QLabel("", self)
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 34px; font-weight: 800; "
            "color: #ffffff; line-height: 1.2;"
        )
        root.addWidget(self.title_lbl)

        # Metadata Row (Time, Location, Contact)
        self.meta_box = QWidget(self)
        self.meta_box.setStyleSheet("background: #181818; border-radius: 6px; border: 1px solid #2a2a2a;")
        m_lay = QHBoxLayout(self.meta_box)
        m_lay.setContentsMargins(16, 10, 16, 10)
        m_lay.setSpacing(20)

        self.loc_lbl = QLabel("", self.meta_box)
        self.loc_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
        m_lay.addWidget(self.loc_lbl)

        self.time_lbl = QLabel("", self.meta_box)
        self.time_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #cbd5e1;")
        m_lay.addWidget(self.time_lbl)

        self.contact_lbl = QLabel("", self.meta_box)
        self.contact_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #cbd5e1;")
        m_lay.addWidget(self.contact_lbl)
        m_lay.addStretch(1)
        root.addWidget(self.meta_box)

        # Full notice body scroll area
        self.scroll = QScrollArea(self)
        self.scroll_area = self.scroll      # the name the mirror's scroller looks for
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.body_content = QLabel(self.scroll)
        self.body_content.setWordWrap(True)
        self.body_content.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 24px; font-weight: 500; "
            "color: #f1f5f9; line-height: 1.5; padding: 12px 0;"
        )
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

        self.loc_lbl.setText(f"LOCATION: {loc.upper()}")
        self.time_lbl.setText(f"TIME: {date_time}")
        self.contact_lbl.setText(f"CONTACT: {contact.upper()}")

        self.body_content.setText(clean_body)

    def close_modal(self):
        self.hide()


class ReadMoreHint(QWidget):
    """The READ MORE hint, which slides in and fades up while its card is selected.

    Painted rather than laid out, so appearing never moves the text above it.
    """
    HEIGHT = 22
    SLIDE_PX = 14

    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._color = QColor(color)
        self._p = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.valueChanged.connect(self._on_value)

    @property
    def progress(self):
        return self._p

    def reveal(self, show):
        self._anim.stop()
        self._anim.setStartValue(self._p)
        self._anim.setEndValue(1.0 if show else 0.0)
        self._anim.setDuration(260 if show else 180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic if show else QEasingCurve.Type.InCubic)
        self._anim.start()

    def _on_value(self, v):
        self._p = float(v)
        self.update()

    def paintEvent(self, event):
        if self._p <= 0.01:
            return
        p = self._p
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont("Segoe UI")
        font.setPixelSize(15)
        font.setWeight(QFont.Weight.ExtraBold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.5)
        painter.setFont(font)
        color = QColor(self._color)
        color.setAlphaF(p)
        painter.setPen(color)
        slide = (1.0 - p) * self.SLIDE_PX
        # The arrow overshoots a little further than the text as it arrives.
        arrow_nudge = (1.0 - p) * self.SLIDE_PX * 1.6
        arrow_w = 18
        painter.drawText(QRectF(-slide, 0, self.width() - arrow_w, self.height()),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "READ MORE")
        painter.drawText(QRectF(self.width() - arrow_w - arrow_nudge, 0, arrow_w, self.height()),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "›")
        painter.end()


class NoticeCard(QFrame):
    """Interactive notice card with hover/tap affordance opening NoticeDetailModal."""

    def __init__(self, notice, on_click=None, parent=None):
        super().__init__(parent)
        self.notice = notice
        self.on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName('NoticeCard')

        # Animated border: lerps 0 -> 3px on select, back to 0 on deselect
        self._bw = 0.0
        self._bw_timer = QTimer(self)
        self._bw_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._bw_timer.setInterval(12)
        self._bw_timer.timeout.connect(self._tick_border)
        self._build_ui()

    def _build_ui(self):
        notice = self.notice
        category = notice.get('category', 'General')
        is_urgent = notice.get('importance', 'normal') == 'high'

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

        # Category colors — exact match with website CATEGORY_COLORS palette
        PALETTE = {
            'General':        '#94a3b8',   # slate
            'Sports':         '#22c55e',   # green
            'Meetings':       '#8b5cf6',   # violet
            'Academic':       '#3b82f6',   # blue
            'Careers':        '#fbbf24',   # amber
            'Arts & Culture': '#f43f5e',   # rose
        }

        card_bg = '#111111'

        if is_urgent:
            border_color = '#ef4444'   # red  (matches website urgent)
            meta_color = '#ef4444'
            prefix = 'URGENT'
        elif is_room_change:
            border_color = '#38bdf8'   # sky
            meta_color = '#38bdf8'
            prefix = 'ROOM CHANGE'
        elif category in PALETTE:
            border_color = PALETTE[category]
            meta_color = PALETTE[category]
            prefix = category.upper()
        else:
            border_color = '#94a3b8'   # slate fallback
            meta_color = '#cbd5e1'
            prefix = category.upper()

        details = extract_details(body_raw)
        date_str = details.get('date', '')
        if not date_str:
            date_str = datetime.now().strftime('%d %B %Y')

        loc_str = details.get('location', '')
        loc_part = f" · {loc_str.upper()}" if loc_str and is_room_change else ""

        self.card_bg = card_bg
        self.border_color = border_color
        self._selected = False
        self.setStyleSheet(f"""
            #NoticeCard {{
                background-color: {card_bg};
                border: none;
                border-left: 4px solid {border_color};
                border-radius: {NOTICE_CARD_RADIUS}px;
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

        # "READ MORE" appears only on the selected card (hand over it, or hover).
        self.read_more = ReadMoreHint(border_color, self)
        lay.addWidget(self.read_more)

    def set_selected(self, selected=True):
        # Called on every gesture packet, so it must be free when nothing changes.
        selected = bool(selected)
        if selected == self._selected:
            return
        self._selected = selected
        self._bw_timer.start()
        self.read_more.reveal(selected)

    @property
    def selected(self):
        return self._selected

    def _tick_border(self):
        target = SELECT_BORDER_PX if self._selected else 0.0
        self._bw += 0.28 * (target - self._bw)          # exponential lerp
        if abs(self._bw - target) < 0.08:
            self._bw = target
            self._bw_timer.stop()
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)                     # background + accent stripe
        if self._bw <= 0.15:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        inset = self._bw * 0.5
        alpha = int(255 * min(1.0, self._bw / SELECT_BORDER_PX))
        painter.setPen(QPen(QColor(255, 255, 255, alpha), self._bw))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(inset, inset, -inset, -inset),
                                NOTICE_CARD_RADIUS, NOTICE_CARD_RADIUS)
        painter.end()

    def enterEvent(self, event):
        self.set_selected(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.set_selected(False)
        super().leaveEvent(event)

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
        self.keyword_boosts = [k.strip() for k in self.keyword_filter.split(',') if k.strip()]
        self.scroll_speed = float(scroll_speed) if scroll_speed else 0.5
        self.year_filter = year_filter
        self.cat_filters = cat_filters
        self.notices = []
        self.cards = []
        self.selected_index = -1
        self.fetched_at = None
        self.error_msg = ''
        self._lock = threading.Lock()
        self._filtered = []

        # Auto scroll state
        self._auto_scroll_paused_until = time.time() + 4.0
        self._last_manual_scroll_time  = 0.0   # tracks last gesture/manual scroll for 10s idle
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
        # Opaque, so scrolling can shift already-drawn pixels instead of
        # repainting everything behind the cards on every frame.
        self.cards_container.setAutoFillBackground(True)
        pal = self.cards_container.palette()
        pal.setColor(self.cards_container.backgroundRole(), QColor(0, 0, 0))
        self.cards_container.setPalette(pal)
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
            self.modal.setGeometry(0, 0, self.width(), self.height())

    def open_modal(self, notice):
        """Open detailed modal inspection expanding across the full notices panel."""
        if hasattr(self, 'modal') and self.modal is not None:
            self.modal.set_notice(notice)
            self.modal.setGeometry(0, 0, self.width(), self.height())
            self.modal.show()
            self.modal.raise_()
            self._scroll_paused = True

    def close_modal(self):
        """Dismiss notice detail modal."""
        if hasattr(self, 'modal') and self.modal is not None:
            self.modal.close_modal()

    @property
    def modal_open(self):
        return hasattr(self, 'modal') and self.modal is not None and not self.modal.isHidden()

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def scroll_by_pixels(self, delta_y):
        """Manual gesture scroll — pauses auto-scroll for 10s from current position."""
        if self.modal_open:
            sb = self.modal.scroll_area.verticalScrollBar()   # a long notice's text
            sb.setValue(sb.value() + int(delta_y))
            return
        sb = self.scroll_area.verticalScrollBar()
        cur = sb.value()
        now = time.time()
        self._last_manual_scroll_time  = now
        self._auto_scroll_paused_until = now + 10.0   # short gate prevents jitter immediately after
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

    def clear_selection(self):
        self.selected_index = -1
        for card in getattr(self, 'cards', []):
            if hasattr(card, 'set_selected'):
                card.set_selected(False)

    def select_index(self, index):
        cards = getattr(self, 'cards', [])
        if not cards:
            return None
        index = max(0, min(len(cards) - 1, index))
        self.selected_index = index
        selected_card = None
        for i, card in enumerate(cards):
            is_sel = (i == index)
            if hasattr(card, 'set_selected'):
                card.set_selected(is_sel)
            if is_sel:
                selected_card = card
        return selected_card

    def select_at_point(self, x_frac, y_frac):
        """Map hand (x_frac, y_frac) into notices cards to highlight."""
        cards = getattr(self, 'cards', [])
        if not cards or self.modal_open:
            return None

        # Resolve viewport y relative to notices scroll area
        top_y = self.scroll_area.mapToGlobal(QPoint(0, 0)).y()
        win_h = self.window().height() if self.window() else 1080
        hand_global_y = int(y_frac * win_h)
        local_y = hand_global_y - top_y + self.scroll_area.verticalScrollBar().value()

        best_idx, min_dist = -1, float('inf')
        for idx, card in enumerate(cards):
            cy = card.y() + card.height() / 2
            dist = abs(cy - local_y)
            if dist < min_dist:
                min_dist = dist
                best_idx = idx

        if best_idx >= 0:
            return self.select_index(best_idx)
        return None

    def activate_selected(self):
        """Pinch or tap handler: open the selected card into NoticeDetailModal."""
        if self.modal_open:
            self.close_modal()
            return True

        cards = getattr(self, 'cards', [])
        if 0 <= self.selected_index < len(cards):
            card = cards[self.selected_index]
            if hasattr(card, 'notice') and card.notice:
                self.open_modal(card.notice)
                return True
        elif cards:
            card = cards[0]
            if hasattr(card, 'notice') and card.notice:
                self.open_modal(card.notice)
                return True
        return False

    def set_gesture_active(self, active, variant='A'):
        """Show/hide the 'your hand is controlling this panel' affordance."""
        active = bool(active)
        self._variant = variant
        if not active:
            self.clear_selection()
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
        """No frame outline -- border removed per user request."""
        self.setStyleSheet("""
            #NoticesWidget {
                background-color: #000000;
                border: none;
                border-radius: 6px;
            }
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
            if hasattr(res, 'raise_for_status'):
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
                                self.keyword_boosts = [str(x).strip().lower() for x in kf if str(x).strip()]
                                self.keyword_filter = ','.join(kf)
                            else:
                                self.keyword_filter = str(kf or '').strip().lower()
                                self.keyword_boosts = [k.strip() for k in self.keyword_filter.split(',') if k.strip()]
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

        # Keywords are boost priorities, not an exclusionary filter
        return True

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
            kw_boosts = getattr(self, 'keyword_boosts', [])

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

                for kw_idx, kw in enumerate(kw_boosts):
                    if kw and kw in t_and_b:
                        return (3, kw_idx)

                cat = n.get('category', 'General')
                if cat_order_list and cat in cat_order_list:
                    return (4, cat_order_list.index(cat))
                if cat in ['Academic', 'Sports', 'Arts & Culture', 'Careers', 'Meetings']:
                    return (5, 0)
                return (6, 0)

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
        self.cards = []
        for notice in filtered:
            card = _make_notice_card(notice, on_click=self.open_modal)
            self.cards.append(card)
            self.cards_lay.addWidget(card)

        self.cards_lay.addStretch(1)
        self._auto_scroll_paused_until = time.time() + 4.0

    # ──────────────────────────────────────────────────────────────────────
    # Auto scroll loop
    # ──────────────────────────────────────────────────────────────────────

    def _auto_scroll_tick(self):
        now = time.time()

        # Resume auto-scroll from current position if no manual scroll for 10s.
        # We never reset position here — just let the continuous ticker keep going
        # from wherever the user left it.
        idle_10s = (now - self._last_manual_scroll_time) >= 10.0
        if not idle_10s:
            return   # still within 10s of last manual scroll — stay paused

        if self._scroll_paused or self._gesture_active:
            return   # tap-paused or hand actively in region

        if now < self._auto_scroll_paused_until:
            return   # short post-scroll jitter gate

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

