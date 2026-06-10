import pygame
from datetime import datetime
from .base_widget import Widget
from utils.fonts import get_font
from .style import font_size, COLOR_WHITE, COLOR_TEXT_DIM

REF_W, REF_H = 220, 100


class ClockWidget(Widget):
    """Centered clock matching web .widget-clock (large time + dim date below)."""

    def __init__(self, x, y, w, h):
        super().__init__(x, y, w, h, "", chromeless=True)
        self.last_minute = ""

    def _fonts(self):
        s = font_size(14, self.rect.w, self.rect.h, REF_W, REF_H)
        return (
            get_font(int(s * 2.4), bold=True),
            get_font(int(s * 0.8)),
        )

    def update(self, scroll_y=0):
        super().update(scroll_y)
        now = datetime.now()
        minute_key = now.strftime("%H:%M")
        if minute_key != self.last_minute:
            self.last_minute = minute_key
            self.needs_redraw = True

    def draw(self, surface, font_title, font_content, scroll_y=0):
        now = datetime.now()
        time_part = now.strftime("%I:%M").lstrip("0")
        ampm = now.strftime("%p").lower()
        time_str = f"{time_part} {ampm}"
        date_str = now.strftime("%A, %d %B")

        font_time, font_date = self._fonts()
        time_surf = font_time.render(time_str, True, COLOR_WHITE)
        date_surf = font_date.render(date_str, True, COLOR_TEXT_DIM)

        rx = self.rect.x
        ry = self.rect.y - scroll_y
        cx = rx + self.rect.w // 2
        cy = ry + self.rect.h // 2

        time_y = cy - (time_surf.get_height() + date_surf.get_height() + 6) // 2
        surface.blit(time_surf, (cx - time_surf.get_width() // 2, time_y))
        surface.blit(
            date_surf,
            (cx - date_surf.get_width() // 2, time_y + time_surf.get_height() + 6),
        )
