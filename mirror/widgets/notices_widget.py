# widgets/notices_widget.py
# Daily Notices widget - fetches from API and renders notices with category groups
# Supports: keyword_filter, scroll_speed from widget data

import pygame
import threading
import time
import requests
import re
from html.parser import HTMLParser
from .base_widget import Widget
from utils.fonts import get_font
from config import *


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        stripped = data.strip()
        if stripped:
            self.parts.append(stripped)

    def get_text(self):
        return ' '.join(self.parts)


def strip_html(html_text):
    if not html_text:
        return ''
    try:
        parser = _HTMLTextExtractor()
        parser.feed(html_text)
        return parser.get_text()
    except Exception:
        return re.sub(r'<[^>]+>', ' ', html_text).strip()


CATEGORY_COLORS = {
    'General':       (148, 163, 184),
    'Sports':        (34,  197, 94),
    'Meetings':      (139, 92,  246),
    'Academic':      (59,  130, 246),
    'Careers':       (251, 191, 36),
    'Arts & Culture':(244, 63,  94),
    'Service':       (20,  184, 166),
}

DEFAULT_ACCENT = (99, 102, 241)
URGENT_COLOR = (239, 68, 68)
SCROLL_STEP = 30
DEFAULT_SCROLL_SPEED = 0.5


class NoticesWidget(Widget):
    def __init__(self, x, y, w, h, api_url='https://api.smartmirror.me',
                 keyword_filter='', scroll_speed=DEFAULT_SCROLL_SPEED):
        super().__init__(x, y, w, h, "Daily Notices")
        self.api_url = api_url
        self.keyword_filter = keyword_filter.strip().lower() if keyword_filter else ''
        self.scroll_speed = float(scroll_speed) if scroll_speed else DEFAULT_SCROLL_SPEED
        self.notices = []
        self.error_msg = ""
        self.scroll_offset = 0
        self._auto_scroll_pos = 0.0
        self.last_update = 0
        self.update_interval = 600
        self._lock = threading.Lock()
        self.font_category = get_font(11, bold=True)
        self.font_title    = get_font(14, bold=True)
        self.font_notice   = get_font(12)
        self.font_badge    = get_font(10, bold=True)
        self._scroll_paused_until = time.time() + 4.0
        self._start_fetch()

    def set_filter(self, keyword_filter='', scroll_speed=None):
        self.keyword_filter = keyword_filter.strip().lower() if keyword_filter else ''
        if scroll_speed is not None:
            self.scroll_speed = float(scroll_speed)
        with self._lock:
            self.needs_redraw = True

    def update(self, scroll_y=0):
        super().update(scroll_y)
        if time.time() - self.last_update > self.update_interval:
            self._start_fetch()
            self.last_update = time.time()
        self._do_auto_scroll()

    def _do_auto_scroll(self):
        now = time.time()
        if now < self._scroll_paused_until:
            return
        content_h = self._content_height()
        view_h = self.rect.h - 55
        max_offset = max(0, content_h - view_h)
        if max_offset <= 0:
            return
        self._auto_scroll_pos += self.scroll_speed
        if self._auto_scroll_pos >= max_offset:
            self._auto_scroll_pos = 0.0
            self._scroll_paused_until = now + 4.0
        self.scroll_offset = int(self._auto_scroll_pos)
        self.needs_redraw = True

    def _start_fetch(self):
        threading.Thread(target=self._fetch_notices, daemon=True).start()

    def _fetch_notices(self):
        try:
            response = requests.get(f"{self.api_url}/api/notices", timeout=10)
            response.raise_for_status()
            data = response.json()
            notices = data if isinstance(data, list) else data.get('notices', [])
            with self._lock:
                self.notices = notices
                self.error_msg = ''
                self.needs_redraw = True
        except Exception as e:
            print(f"[NoticesWidget] Failed to fetch notices: {e}")
            with self._lock:
                self.error_msg = "No notices available"
                self.notices = []
                self.needs_redraw = True

    def handle_click(self, x, y, scroll_y=0):
        adj_y = y + scroll_y
        if not self.rect.collidepoint(x, adj_y):
            return False
        max_offset = max(0, self._content_height() - (self.rect.h - 60))
        self.scroll_offset = (self.scroll_offset + SCROLL_STEP) % (max_offset + 1) if max_offset > 0 else 0
        self._auto_scroll_pos = float(self.scroll_offset)
        self.needs_redraw = True
        return True

    def _content_height(self):
        with self._lock:
            notices = [n for n in self.notices if self._passes_filter(n)]
        if not notices:
            return 0
        wrap_width = self.rect.w - 40
        total_h = 0
        for notice in notices:
            total_h += 24 + 20
            body = strip_html(notice.get('notice', ''))
            lines = self._wrap_text(self.font_notice, body, wrap_width - 8)
            total_h += len(lines) * 17 + 12
        return total_h

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

    def draw(self, surface, font_title, font_content, scroll_y=0):
        super().draw(surface, font_title, font_content, scroll_y)
        if self.needs_redraw:
            self._render_content()
            self.needs_redraw = False
        if self.content_surface:
            draw_y = self.rect.y - scroll_y
            content_y = draw_y + 50
            clip_h = self.rect.h - 55
            if clip_h <= 0:
                return
            clip_surf = pygame.Surface((self.rect.w - 40, clip_h), pygame.SRCALPHA)
            clip_surf.blit(self.content_surface, (0, -self.scroll_offset))
            surface.blit(clip_surf, (self.rect.x + 20, content_y))

    def _render_content(self):
        wrap_width = self.rect.w - 40
        with self._lock:
            notices = [n for n in self.notices if self._passes_filter(n)]
            error_msg = self.error_msg
        if not notices:
            msg = error_msg if error_msg else "No notices available"
            self.content_surface = pygame.Surface((wrap_width, 40), pygame.SRCALPHA)
            txt_surf = self.font_notice.render(msg, True, COLOR_TEXT_DIM)
            self.content_surface.blit(txt_surf, (0, 10))
            return
        sorted_notices = sorted(notices, key=lambda n: (n.get('importance', 'normal') != 'high'))
        total_h = 0
        for notice in sorted_notices:
            total_h += 24 + 20
            body = strip_html(notice.get('notice', ''))
            lines = self._wrap_text(self.font_notice, body, wrap_width - 8)
            total_h += len(lines) * 17 + 12
        self.content_surface = pygame.Surface((wrap_width, max(total_h, 40)), pygame.SRCALPHA)
        y = 0
        for notice in sorted_notices:
            category = notice.get('category', 'General')
            title = notice.get('title', category + ' Notice')
            body = strip_html(notice.get('notice', ''))
            is_urgent = notice.get('importance', 'normal') == 'high'
            years = notice.get('targetYears', ['All'])
            accent = URGENT_COLOR if is_urgent else CATEGORY_COLORS.get(category, DEFAULT_ACCENT)
            badge_text = "URGENT" if is_urgent else category.upper()
            badge_color = URGENT_COLOR if is_urgent else accent
            badge_surf = self.font_badge.render(badge_text, True, badge_color)
            self.content_surface.blit(badge_surf, (6, y + 4))
            bx = wrap_width - 4
            for yr in reversed(years):
                yr_text = f"Y{yr}" if yr != 'All' else 'All'
                yr_surf = self.font_badge.render(yr_text, True, COLOR_TEXT_DIM)
                bx -= yr_surf.get_width() + 4
                self.content_surface.blit(yr_surf, (bx, y + 4))
            y += 24
            title_color = (255, 255, 255) if not is_urgent else (252, 165, 165)
            title_surf = self.font_title.render(title[:60], True, title_color)
            self.content_surface.blit(title_surf, (6, y))
            y += 20
            for line in self._wrap_text(self.font_notice, body, wrap_width - 8):
                line_surf = self.font_notice.render(line, True, COLOR_TEXT_DIM)
                self.content_surface.blit(line_surf, (8, y))
                y += 17
            pygame.draw.line(self.content_surface, (255, 255, 255, 20), (0, y + 4), (wrap_width, y + 4))
            y += 12

    @staticmethod
    def _wrap_text(font, text, max_width):
        if not text:
            return ['']
        words = text.split()
        lines = []
        current_line = ''
        for word in words:
            test_line = (current_line + ' ' + word).strip()
            if font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        return lines if lines else ['']
