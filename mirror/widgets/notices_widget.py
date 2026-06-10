# widgets/notices_widget.py
# Daily Notices — mirror mode matching web .notices-mirror-* styles

import pygame
import threading
import time
import requests
import re
from html.parser import HTMLParser
from .base_widget import Widget
from utils.fonts import get_font
from .style import font_size, COLOR_WHITE, COLOR_TEXT_DIM, COLOR_TEXT_MUTED

REF_W, REF_H = 420, 340
SCROLL_INTERVAL_MS = 25
HOLD_TOP_MS = 4000
HOLD_BOTTOM_MS = 2000
DEFAULT_SCROLL_SPEED = 0.5

CATEGORY_COLORS = {
    'General':        ((148, 163, 184), (203, 213, 225)),
    'Sports':         ((34, 197, 94),   (134, 239, 172)),
    'Meetings':       ((139, 92, 246),  (196, 181, 253)),
    'Academic':       ((59, 130, 246),  (147, 197, 253)),
    'Careers':        ((251, 191, 36),  (253, 230, 138)),
    'Arts & Culture': ((244, 63, 94),   (253, 164, 175)),
    'Service':        ((20, 184, 166),  (94, 234, 212)),
}
URGENT_ACCENT = (239, 68, 68)


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
                 keyword_filter='', scroll_speed=DEFAULT_SCROLL_SPEED):
        super().__init__(x, y, w, h, "", chromeless=True)
        self.api_url = api_url
        self.keyword_filter = keyword_filter.strip().lower() if keyword_filter else ''
        self.scroll_speed = float(scroll_speed) if scroll_speed else DEFAULT_SCROLL_SPEED
        self.notices = []
        self.error_msg = ""
        self.scroll_offset = 0.0
        self.last_update = 0
        self.update_interval = 600
        self._lock = threading.Lock()
        self._scroll_paused_until = time.time() + HOLD_TOP_MS / 1000.0
        self._last_scroll_tick = time.time()
        self.content_surface = None
        self.content_height = 0
        self.needs_redraw = True
        self._start_fetch()

    def update(self, scroll_y=0):
        super().update(scroll_y)
        if time.time() - self.last_update > self.update_interval:
            self._start_fetch()
            self.last_update = time.time()
        self._auto_scroll()

    def _auto_scroll(self):
        now = time.time()
        if now < self._scroll_paused_until:
            return
        view_h = max(1, self.rect.h - self._header_h() - 14)
        max_offset = max(0, self.content_height - view_h)
        if max_offset <= 0:
            return
        dt_ms = (now - self._last_scroll_tick) * 1000.0
        self._last_scroll_tick = now
        ticks = dt_ms / SCROLL_INTERVAL_MS
        self.scroll_offset += self.scroll_speed * ticks
        if self.scroll_offset >= max_offset:
            self.scroll_offset = 0.0
            self._scroll_paused_until = now + HOLD_BOTTOM_MS / 1000.0

    def _header_h(self):
        return max(28, int(font_size(12, self.rect.w, self.rect.h, REF_W, REF_H) * 2.2))

    def _start_fetch(self):
        threading.Thread(target=self._fetch_notices, daemon=True).start()

    def _fetch_notices(self):
        try:
            res = requests.get(f"{self.api_url}/api/notices", timeout=10)
            res.raise_for_status()
            data = res.json()
            notices = data if isinstance(data, list) else data.get('notices', [])
            with self._lock:
                self.notices = notices
                self.error_msg = ''
                self.needs_redraw = True
                self._scroll_paused_until = time.time() + HOLD_TOP_MS / 1000.0
                self.scroll_offset = 0.0
        except Exception as e:
            print(f"[NoticesWidget] Failed to fetch notices: {e}")
            with self._lock:
                self.error_msg = "No notices available"
                self.notices = []
                self.needs_redraw = True

    def _passes_filter(self, notice):
        if not self.keyword_filter:
            return True
        haystack = ' '.join([
            notice.get('title', ''),
            notice.get('category', ''),
            notice.get('contact', ''),
            strip_html(notice.get('notice', '')),
        ]).lower()
        return self.keyword_filter in haystack

    def _scale(self):
        return font_size(14, self.rect.w, self.rect.h, REF_W, REF_H) / 14.0

    def draw(self, surface, font_title, font_content, scroll_y=0):
        rx = self.rect.x
        ry = self.rect.y - scroll_y
        rw = self.rect.w
        rh = self.rect.h
        sc = self._scale()

        font_header = get_font(max(10, int(12 * sc)), bold=True)
        font_count = get_font(max(8, int(10 * sc)))
        font_badge = get_font(max(8, int(10 * sc)), bold=True)
        font_title = get_font(max(11, int(13 * sc)), bold=True)
        font_body = get_font(max(9, int(11 * sc)))
        font_chip = get_font(max(8, int(10 * sc)), bold=True)

        header_h = self._header_h()
        pygame.draw.line(surface, (255, 255, 255, 18), (rx + 14, ry + header_h), (rx + rw - 14, ry + header_h))

        title_s = font_header.render("DAILY NOTICES", True, (230, 230, 230))
        surface.blit(title_s, (rx + 14, ry + 10))

        with self._lock:
            filtered = [n for n in self.notices if self._passes_filter(n)]
            filtered.sort(key=lambda n: (n.get('importance', 'normal') != 'high'))
            error_msg = self.error_msg

        count_text = f"{len(filtered)} notice{'s' if len(filtered) != 1 else ''}"
        count_s = font_count.render(count_text, True, COLOR_TEXT_MUTED)
        surface.blit(count_s, (rx + rw - 14 - count_s.get_width(), ry + 12))

        content_top = ry + header_h + 10
        content_h = rh - header_h - 24
        clip_w = rw - 28

        if self.needs_redraw or self.content_surface is None:
            self._render_content(filtered, error_msg, clip_w, font_badge, font_title, font_body, font_chip)
            self.needs_redraw = False

        if self.content_surface:
            clip = pygame.Surface((clip_w, max(1, content_h)), pygame.SRCALPHA)
            clip.blit(self.content_surface, (0, -int(self.scroll_offset)))
            surface.blit(clip, (rx + 14, content_top))

    def _render_content(self, notices, error_msg, width, font_badge, font_title, font_body, font_chip):
        if not notices:
            msg = error_msg or "No notices available today."
            self.content_surface = pygame.Surface((width, 40), pygame.SRCALPHA)
            self.content_surface.blit(font_body.render(msg, True, COLOR_TEXT_DIM), (0, 10))
            self.content_height = 40
            return

        gap = 10
        total_h = 0
        card_surfs = []

        for notice in notices:
            category = notice.get('category', 'General')
            is_urgent = notice.get('importance', 'normal') == 'high'
            accent, text_col = CATEGORY_COLORS.get(category, CATEGORY_COLORS['General'])
            if is_urgent:
                accent = URGENT_ACCENT
            title = notice.get('title', category + ' Notice')
            body = strip_html(notice.get('notice', ''))
            details = extract_details(notice.get('notice', ''))
            years = notice.get('targetYears', ['All'])
            contact = notice.get('contact', '')

            lines = self._wrap(font_body, body, width - 24)
            card_h = 10 + 18 + 20 + len(lines) * (font_body.get_height() + 3) + 8
            if details:
                card_h += 22
            if contact:
                card_h += 18

            card = pygame.Surface((width, card_h), pygame.SRCALPHA)
            pygame.draw.rect(card, (255, 255, 255, 6), card.get_rect(), border_radius=10)
            pygame.draw.rect(card, (255, 255, 255, 18), card.get_rect(), 1, border_radius=10)
            pygame.draw.rect(card, accent, pygame.Rect(0, 0, 3, card_h), border_top_left_radius=10, border_bottom_left_radius=10)

            y = 10
            badge_txt = "URGENT" if is_urgent else category.upper()
            badge_s = font_badge.render(badge_txt, True, text_col if not is_urgent else (252, 165, 165))
            card.blit(badge_s, (12, y))
            bx = width - 8
            for yr in reversed(years):
                yr_s = font_badge.render(f"Y{yr}" if yr != 'All' else 'All', True, COLOR_TEXT_MUTED)
                bx -= yr_s.get_width() + 4
                card.blit(yr_s, (bx, y + 1))
            y += 18

            title_color = (242, 242, 242) if not is_urgent else (252, 165, 165)
            card.blit(font_title.render(title[:70], True, title_color), (12, y))
            y += 20

            if details.get('date') or details.get('time') or details.get('location'):
                cx = 12
                for label, key in [('Date', 'date'), ('Time', 'time'), ('Where', 'location')]:
                    if details.get(key):
                        chip = f"{label}: {details[key]}"
                        chip_s = font_chip.render(chip, True, (191, 191, 191))
                        pygame.draw.rect(card, (255, 255, 255, 15), pygame.Rect(cx, y, chip_s.get_width() + 12, chip_s.get_height() + 4), border_radius=10)
                        card.blit(chip_s, (cx + 6, y + 2))
                        cx += chip_s.get_width() + 18
                y += 22

            for line in lines:
                card.blit(font_body.render(line, True, (184, 184, 184)), (12, y))
                y += font_body.get_height() + 3

            if contact:
                y += 4
                card.blit(font_body.render(f"Contact: {contact}", True, COLOR_TEXT_MUTED), (12, y))

            card_surfs.append(card)
            total_h += card_h + gap

        self.content_height = max(total_h, 40)
        self.content_surface = pygame.Surface((width, self.content_height), pygame.SRCALPHA)
        y = 0
        for card in card_surfs:
            self.content_surface.blit(card, (0, y))
            y += card.get_height() + gap

    @staticmethod
    def _wrap(font, text, max_width):
        if not text:
            return []
        words = text.split()
        lines, line = [], ''
        for word in words:
            test = (line + ' ' + word).strip()
            if font.size(test)[0] <= max_width:
                line = test
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
        return lines
