import pygame
import time
from datetime import datetime, timezone
from .base_widget import Widget
from utils.fonts import get_font
from .style import font_size, COLOR_TEXT

REF_W, REF_H = 220, 200


def _parse_iso(dt_str):
    if not dt_str:
        return None
    try:
        dt_str = dt_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc).timestamp()
        return dt.timestamp()
    except Exception:
        return None


class NoteWidget(Widget):
    """Plain note text matching web readonly .widget-note-view."""

    def __init__(self, x, y, w, h, data=None):
        super().__init__(x, y, w, h, "", chromeless=True)
        if isinstance(data, dict):
            self.text = data.get('text', '') or ''
            self.expire_at = _parse_iso(data.get('expireAt'))
        elif isinstance(data, str):
            self.text = data or ''
            self.expire_at = None
        else:
            self.text = ''
            self.expire_at = None

    def _is_expired(self):
        return self.expire_at is not None and time.time() >= self.expire_at

    def _minutes_left(self):
        if self.expire_at is None:
            return None
        diff = self.expire_at - time.time()
        return 0 if diff <= 0 else int(diff / 60) + 1

    def update(self, scroll_y=0):
        pass

    def draw(self, surface, font_title, font_content, scroll_y=0):
        if self._is_expired():
            return

        rx = self.rect.x
        ry = self.rect.y - scroll_y
        pad = 4
        max_w = self.rect.w - pad * 2
        line_h = int(font_size(14, self.rect.w, self.rect.h, REF_W, REF_H) * 1.5)
        font_body = get_font(font_size(14, self.rect.w, self.rect.h, REF_W, REF_H))
        font_warn = get_font(font_size(11, self.rect.w, self.rect.h, REF_W, REF_H), bold=True)

        text = self.text if self.text else 'No note written.'
        y = ry + pad
        max_y = ry + self.rect.h - pad
        mins_left = self._minutes_left()
        if mins_left is not None and mins_left <= 10:
            max_y -= line_h

        for paragraph in text.split('\n'):
            line = ''
            for word in paragraph.split():
                test = (line + ' ' + word).strip()
                if font_body.size(test)[0] > max_w:
                    if line:
                        if y + line_h > max_y:
                            return
                        surface.blit(font_body.render(line, True, COLOR_TEXT), (rx + pad, y))
                        y += line_h
                    line = word
                else:
                    line = test
            if line and y + line_h <= max_y:
                surface.blit(font_body.render(line, True, COLOR_TEXT), (rx + pad, y))
                y += line_h

        if mins_left is not None and mins_left <= 10:
            badge_color = (239, 68, 68) if mins_left <= 2 else (251, 191, 36)
            badge_text = f"Expires in {mins_left} min" if mins_left > 0 else "Expired"
            badge_surf = font_warn.render(badge_text, True, badge_color)
            surface.blit(badge_surf, (rx + pad, ry + self.rect.h - pad - badge_surf.get_height()))
