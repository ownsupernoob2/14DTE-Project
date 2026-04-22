# widgets/weather_widget.py
# Weather widget displaying current temperature

import pygame
from .base_widget import Widget
from utils.fonts import get_font
from config import *

class WeatherWidget(Widget):
    """Widget displaying current weather temperature."""

    def __init__(self, x, y, w, h):
        """Initialize the weather widget.

        Args:
            x, y: Position coordinates
            w, h: Width and height
        """
        super().__init__(x, y, w, h, "Weather")
        self.temp = "72°"  # Default temperature
        self.needs_redraw = True
        self.font_big = get_font(60)  # Large temperature display

    def update(self, scroll_y=0):
        """Update the widget (weather data would be fetched here in a real implementation)."""
        super().update(scroll_y)
        # In a real implementation, you would fetch weather data here
        # For now, we just use a static temperature

    def draw(self, surface, font_title, font_content, scroll_y=0):
        """Draw the weather widget with temperature display."""
        # Call parent draw for background and title
        super().draw(surface, font_title, font_content, scroll_y)

        # Draw temperature if content needs updating
        if self.needs_redraw:
            self.content_surface = pygame.Surface((self.rect.w - 40, self.rect.h - 60), pygame.SRCALPHA)
            temp_surf = self.font_big.render(self.temp, True, COLOR_WHITE)
            self.content_surface.blit(temp_surf, (0, 0))
            self.needs_redraw = False

    def set_temperature(self, temp):
        """Update the displayed temperature.

        Args:
            temp: Temperature string (e.g., "72°", "15°C")
        """
        if self.temp != temp:
            self.temp = temp
            self.needs_redraw = True
