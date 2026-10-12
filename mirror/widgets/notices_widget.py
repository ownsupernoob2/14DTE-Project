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
    """Build a single notice card QFrame matching the web screenshot (scaled up)."""
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

    card = QFrame()
    card.setObjectName('NoticeCard')
    card.setStyleSheet(f"""
        #NoticeCard {{
            background-color: {card_bg};
            border: 1px solid {border_main};
            border-left: 4px solid {border_color};
            border-radius: 4px;
        }}
    """)

    lay = QVBoxLayout(card)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(8)

    # ── Meta row: CATEGORY · DATE · SEE NAME · LOCATION ──────────────────
    contact = notice.get('contact', '').strip()
    contact_part = f" · SEE {contact.upper()}" if contact else ""
    meta_tag = f"{prefix} · {date_str.upper()}{loc_part}{contact_part}"
    meta_lbl = QLabel(meta_tag)
    meta_lbl.setStyleSheet(
        f"font-family: 'Consolas', 'SFMono-Regular', 'Segoe UI', monospace; "
        f"font-size: 15px; font-weight: 800; color: {meta_color}; "
        f"letter-spacing: 1px; background: transparent; border: none;"
    )
    lay.addWidget(meta_lbl)

    # ── Title ──────────────────────────────────────────────────────────────
    title_lbl = QLabel(title)
    title_lbl.setWordWrap(True)
    title_lbl.setStyleSheet(
        "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 26px; font-weight: 700; "
        "color: #ffffff; background: transparent; border: none; line-height: 1.25;"
    )
    lay.addWidget(title_lbl)

    # ── Body text preview ──────────────────────────────────────────────────
    body_text = strip_html(notice.get('notice', ''))
    if body_text:
        if len(body_text) > 280:
            body_text = body_text[:280].rsplit(' ', 1)[0] + '…'
        body_lbl = QLabel(body_text)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 18px; font-weight: 500; "
            "color: #f1f5f9; background: transparent; border: none; line-height: 1.45;"
        )
        lay.addWidget(body_lbl)

    return card


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

        self._start_fetch()

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def scroll_by_pixels(self, delta_y):
        """Manual scroll clamping cleanly within scrollbar limits."""
        sb = self.scroll_area.verticalScrollBar()
        cur = sb.value()
        self._auto_scroll_paused_until = time.time() + 10.0
        sb.setValue(cur + int(delta_y))

    @property
    def scroll_paused(self):
        return self._scroll_paused

    def toggle_scroll_pause(self):
        """Tap handler: hold the list still, or let it resume. Returns the new state."""
        self._scroll_paused = not self._scroll_paused
        if not self._scroll_paused:
            # A beat before it starts moving again, so resuming isn't jarring.
            self._auto_scroll_paused_until = time.time() + 1.5
        # The border carries this — a tap has to give some feedback, or you
        # cannot tell whether it registered.
        self._apply_frame_style()
        return self._scroll_paused

    def set_gesture_active(self, active):
        """Show/hide the 'your hand is controlling this panel' affordance."""
        active = bool(active)
        if active == self._gesture_active:
            return
        self._gesture_active = active
        self._apply_frame_style()

    def reset_gesture_state(self):
        """Forget tap-pause and affordance — the mirror changed who it's showing."""
        self._scroll_paused = False
        self.set_gesture_active(False)
        self._apply_frame_style()

    def _apply_frame_style(self):
        """The panel's border is the whole gesture affordance.

        Uses constant border width and solid black background so the inner
        content never shifts and background remains cleanly dark.
        Outline is clean white (#ffffff) when active or paused.
        """
        if self._scroll_paused or self._gesture_active:
            border = '2px solid #ffffff'
        else:
            border = '2px solid transparent'

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
            card = _make_notice_card(notice)
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

