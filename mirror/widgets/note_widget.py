import pygame
import time
from datetime import datetime, timezone
from .base_widget import Widget
from utils.fonts import get_font

COLOR_WHITE = (255, 255, 255)
COLOR_WARNING = (251, 191, 36)
COLOR_EXPIRED = (239, 68, 68)


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
    def __init__(self, x, y, w, h, data=None):
        super().__init__(x, y, w, h, "")
        if isinstance(data, dict):
            self.text = data.get('text', '') or ''
            self.expire_at = _parse_iso(data.get('expireAt'))
        elif isinstance(data, str):
            self.text = data or ''
            self.expire_at = None
        else:
            self.text = ''
            self.expire_at = None
        self.font_title = get_font(13, bold=True)
        self.font_body = get_font(14)
        self.font_warn = get_font(11, bold=True)

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
        rw = self.rect.w
        rh = self.rect.h
        glass = pygame.Surface((rw, rh), pygame.SRCALPHA)
        glass.fill((20, 20, 35, 210))
        surface.blit(glass, (rx, ry))
        pygame.draw.rect(surface, (255, 255, 255, 40), (rx, ry, rw, rh), 1, border_radius=12)
        header_h = 28
        header_surf = pygame.Surface((rw, header_h), pygame.SRCALPHA)
        header_surf.fill((99, 102, 241, 60))
        surface.blit(header_surf, (rx, ry))
        label = self.font_title.render('Note', True, (200, 200, 220))
        surface.blit(label, (rx + 12, ry + (header_h - label.get_height()) // 2))
        pad = 12
        text_x = rx + pad
        text_y = ry + header_h + pad
        max_w = rw - pad * 2
        max_y = ry + rh - pad
        mins_left = self._minutes_left()
        if mins_left is not None and mins_left <= 10:
            max_y -= 20
        text = self.text if self.text else 'No note written.'
        line = ''
        for word in text.split():
            test_line = line + (' ' if line else '') + word
            if self.font_body.size(test_line)[0] > max_w:
                if text_y + self.font_body.get_height() > max_y:
                    break
                surface.blit(self.font_body.render(line, True, COLOR_WHITE), (text_x, text_y))
                text_y += self.font_body.get_height() + 3
                line = word
            else:
                line = test_line
        if line and text_y + self.font_body.get_height() <= max_y:
            surface.blit(self.font_body.render(line, True, COLOR_WHITE), (text_x, text_y))
        if mins_left is not None and mins_left <= 10:
            badge_color = COLOR_EXPIRED if mins_left <= 2 else COLOR_WARNING
            badge_text = f"Expires in {mins_left} min" if mins_left > 0 else "Expired"
            badge_surf = self.font_warn.render(badge_text, True, badge_color)
            surface.blit(badge_surf, (rx + pad, ry + rh - pad - badge_surf.get_height()))
