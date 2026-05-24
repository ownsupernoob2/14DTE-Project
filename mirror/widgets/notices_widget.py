# widgets/notices_widget.py
# Daily Notices widget - fetches from API and renders category groups

import pygame
import threading
import time
import requests
import json
from .base_widget import Widget
from utils.fonts import get_font
from config import *


SCROLL_STEP = 30  # pixels per scroll click


class NoticesWidget(Widget):
    """Widget displaying daily notices grouped by category."""

    def __init__(self, x, y, w, h, api_url='https://api.smartmirror.me'):
        super().__init__(x, y, w, h, "Notices")
        self.api_url = api_url
        self.notices = []          # list of dicts: {category, text}
        self.error_msg = ""
        self.scroll_offset = 0
        self.last_update = 0
        self.update_interval = 600  # 10 minutes
        self._lock = threading.Lock()

        # Fonts
        self.font_category = get_font(12, bold=True)   # Category header
        self.font_notice = get_font(14)                 # Notice text

        # Kick off initial fetch
        self._start_fetch()

    # ------------------------------------------------------------------ #
    #  Update / Fetch                                                      #
    # ------------------------------------------------------------------ #

    def update(self, scroll_y=0):
        super().update(scroll_y)
        current_time = time.time()
        if current_time - self.last_update > self.update_interval:
            self._start_fetch()
            self.last_update = current_time

    def _start_fetch(self):
        threading.Thread(target=self._fetch_notices, daemon=True).start()

    def _fetch_notices(self):
        try:
            response = requests.get(f"{self.api_url}/api/notices", timeout=10)
            response.raise_for_status()
            data = response.json()
            # Expect a list of dicts with 'category' and 'text' keys
            notices = data if isinstance(data, list) else data.get('notices', [])
            with self._lock:
                self.notices = notices
                self.error_msg = ""
                self.needs_redraw = True
        except Exception as e:
            print(f"[NoticesWidget] Failed to fetch notices: {e}")
            with self._lock:
                self.error_msg = "No notices available"
                self.notices = []
                self.needs_redraw = True

    # ------------------------------------------------------------------ #
    #  Click / Scroll                                                      #
    # ------------------------------------------------------------------ #

    def handle_click(self, x, y, scroll_y=0):
        """Advance scroll offset by one step each click inside widget area."""
        adj_y = y + scroll_y
        if not self.rect.collidepoint(x, adj_y):
            return False
        self.scroll_offset += SCROLL_STEP
        # Clamp to content height; reset to 0 if overshot
        max_offset = max(0, self._content_height() - (self.rect.h - 60))
        if self.scroll_offset > max_offset:
            self.scroll_offset = 0
        self.needs_redraw = True
        return True

    def _content_height(self):
        """Estimate total rendered content height for scroll clamping."""
        with self._lock:
            notices = list(self.notices)
        if not notices:
            return 0
        # Group by category then count lines
        groups = self._group_by_category(notices)
        wrap_width = self.rect.w - 40
        total_h = 0
        for category, items in groups.items():
            total_h += 20  # category header
            total_h += 4   # gap below header
            for text in items:
                lines = self._wrap_text(self.font_notice, text, wrap_width)
                total_h += len(lines) * 18 + 6
        return total_h

    # ------------------------------------------------------------------ #
    #  Draw                                                                #
    # ------------------------------------------------------------------ #

    def draw(self, surface, font_title, font_content, scroll_y=0):
        # Draw widget background + title via base class
        super().draw(surface, font_title, font_content, scroll_y)

        if self.needs_redraw:
            self._render_content()
            self.needs_redraw = False

        # Blit content surface at scroll position
        if self.content_surface:
            draw_y = self.rect.y - scroll_y
            # We need to clip the content inside the widget body
            content_y = draw_y + 50  # below title area
            clip_h = self.rect.h - 55
            if clip_h <= 0:
                return
            # Create a clipping surface
            clip_surf = pygame.Surface((self.rect.w - 40, clip_h), pygame.SRCALPHA)
            clip_surf.blit(self.content_surface, (0, -self.scroll_offset))
            surface.blit(clip_surf, (self.rect.x + 20, content_y))

    def _render_content(self):
        """Render the full (unclipped) content surface."""
        wrap_width = self.rect.w - 40
        # Build content
        with self._lock:
            notices = list(self.notices)
            error_msg = self.error_msg

        if not notices:
            msg = error_msg if error_msg else "No notices available"
            self.content_surface = pygame.Surface((wrap_width, 40), pygame.SRCALPHA)
            txt_surf = self.font_notice.render(msg, True, COLOR_TEXT_DIM)
            self.content_surface.blit(txt_surf, (0, 10))
            return

        groups = self._group_by_category(notices)

        # Calculate total height first
        total_h = 0
        for category, items in groups.items():
            total_h += 20 + 4  # category label + gap
            for text in items:
                lines = self._wrap_text(self.font_notice, text, wrap_width)
                total_h += len(lines) * 18 + 6

        content_h = max(total_h, 40)
        self.content_surface = pygame.Surface((wrap_width, content_h), pygame.SRCALPHA)

        y = 0
        for category, items in groups.items():
            # --- Category header ---
            cat_surf = self.font_category.render(category.upper(), True, COLOR_ACCENT)
            self.content_surface.blit(cat_surf, (0, y))
            y += 20 + 4

            # --- Notices under this category ---
            for text in items:
                lines = self._wrap_text(self.font_notice, text, wrap_width)
                for line in lines:
                    line_surf = self.font_notice.render(line, True, COLOR_WHITE)
                    self.content_surface.blit(line_surf, (8, y))
                    y += 18
                y += 6  # gap between notices

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _group_by_category(notices):
        """Return an ordered dict of category -> [text, ...] from notice list."""
        groups = {}
        for item in notices:
            category = item.get('category', 'General')
            text = item.get('text', item.get('message', str(item)))
            if category not in groups:
                groups[category] = []
            groups[category].append(text)
        return groups

    @staticmethod
    def _wrap_text(font, text, max_width):
        """Word-wrap text to fit within max_width pixels. Returns list of lines."""
        words = text.split(' ')
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
