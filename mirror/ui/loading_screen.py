# ui/loading_screen.py
# Loading screen for long-running operations

import pygame
import time
import math
from config import *
from utils.fonts import get_font

class LoadingScreen:
    """Loading screen overlay for long-running operations like face capture."""

    def __init__(self, screen_w, screen_h):
        self.active = False
        self.message = "Loading..."
        self.progress = 0.0  # 0.0 to 1.0
        self.start_time = 0
        self.screen_w = screen_w
        self.screen_h = screen_h

        self.font_title = get_font(32, bold=True)
        self.font_message = get_font(24)
        self.animation_angle = 0

    def show(self, message="Loading...", show_progress=False):
        """Show the loading screen with a message."""
        self.active = True
        self.message = message
        self.progress = 0.0
        self.start_time = time.time()
        self.show_progress_bar = show_progress

    def update_progress(self, progress):
        """Update the progress bar (0.0 to 1.0)."""
        self.progress = max(0.0, min(1.0, progress))

    def hide(self):
        """Hide the loading screen."""
        self.active = False

    def update(self):
        """Update animation."""
        if self.active:
            self.animation_angle += 0.1
            if self.animation_angle > 2 * math.pi:
                self.animation_angle = 0

    def draw(self, screen):
        """Draw the loading screen overlay."""
        if not self.active:
            return

        # Semi-transparent overlay
        overlay = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 220))
        screen.blit(overlay, (0, 0))

        # Center position
        center_x = self.screen_w // 2
        center_y = self.screen_h // 2

        # Loading spinner (animated circle)
        spinner_radius = 30
        spinner_center = (center_x, center_y - 50)

        # Draw spinner background
        pygame.draw.circle(screen, (60, 60, 60), spinner_center, spinner_radius)

        # Draw animated arc
        arc_rect = pygame.Rect(
            spinner_center[0] - spinner_radius,
            spinner_center[1] - spinner_radius,
            spinner_radius * 2,
            spinner_radius * 2
        )

        # Create a surface for the arc
        arc_surface = pygame.Surface((spinner_radius * 2, spinner_radius * 2), pygame.SRCALPHA)
        start_angle = self.animation_angle
        end_angle = self.animation_angle + math.pi * 1.5  # 270 degrees

        # Draw the arc
        pygame.draw.arc(arc_surface, COLOR_ACCENT, arc_surface.get_rect(), start_angle, end_angle, 4)

        screen.blit(arc_surface, arc_rect)

        # Message text
        message_surf = self.font_message.render(self.message, True, COLOR_WHITE)
        message_rect = message_surf.get_rect(center=(center_x, center_y + 20))
        screen.blit(message_surf, message_rect)

        # Progress bar if enabled
        if self.show_progress_bar:
            bar_width = 300
            bar_height = 20
            bar_x = center_x - bar_width // 2
            bar_y = center_y + 60

            # Background
            pygame.draw.rect(screen, (60, 60, 60), (bar_x, bar_y, bar_width, bar_height), border_radius=10)

            # Progress fill
            fill_width = int(bar_width * self.progress)
            if fill_width > 0:
                pygame.draw.rect(screen, COLOR_ACCENT, (bar_x, bar_y, fill_width, bar_height), border_radius=10)

            # Progress text
            progress_text = f"{int(self.progress * 100)}%"
            progress_surf = self.font_message.render(progress_text, True, COLOR_WHITE)
            progress_rect = progress_surf.get_rect(center=(center_x, bar_y + bar_height + 25))
            screen.blit(progress_surf, progress_rect)
