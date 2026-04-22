# widgets/clock_widget.py
# Clock widget displaying current time and date

import pygame
from datetime import datetime
from .base_widget import Widget
from utils.fonts import get_font
from config import *

class ClockWidget(Widget):
    """Widget displaying current time and date in a clean, modern format."""

    def __init__(self, x, y, w, h):
        """Initialize the clock widget.

        Args:
            x, y: Position coordinates
            w, h: Width and height
        """
        super().__init__(x, y, w, h, "")  # No title for clean look
        self.last_time = ""
        self.font_huge = get_font(100, bold=True)  # Large time display
        self.font_med = get_font(40)               # AM/PM
        self.font_small = get_font(24)             # Date

    def update(self, scroll_y=0):
        """Update the widget and check if time has changed."""
        super().update(scroll_y)
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        if current_time != self.last_time:
            self.last_time = current_time
            self.needs_redraw = True

    def draw(self, surface, font_title, font_content, scroll_y=0):
        """Draw the clock with time, AM/PM, and date."""
        # Create widget surface
        s = pygame.Surface((self.rect.w, self.rect.h), pygame.SRCALPHA)

        # Draw drag highlight if needed
        if self.dragging:
             pygame.draw.rect(s, (255, 255, 255, 50), s.get_rect(), 2, border_radius=15)

        now = datetime.now()
        time_str = now.strftime("%I:%M")  # 12-hour format without leading zero
        ampm_str = now.strftime("%p")     # AM/PM
        date_str = now.strftime("%A, %B %d")  # "Monday, January 26"

        # Render time (large, bold)
        time_surf = self.font_huge.render(time_str, True, COLOR_WHITE)
        s.blit(time_surf, (0, 0))

        # Render AM/PM (medium, offset from time)
        ampm_surf = self.font_med.render(ampm_str, True, COLOR_TEXT_DIM)
        s.blit(ampm_surf, (time_surf.get_width() + 15, 55))

        # Render date (small, below time)
        date_surf = self.font_small.render(date_str, True, COLOR_TEXT_DIM)
        s.blit(date_surf, (10, 110))

        # Blit to main surface
        draw_y = self.rect.y - scroll_y
        surface.blit(s, (self.rect.x, draw_y))
