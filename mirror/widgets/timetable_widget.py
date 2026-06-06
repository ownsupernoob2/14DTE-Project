# widgets/timetable_widget.py
# Timetable widget - shows today's schedule from ICS via API

import pygame
import threading
import time
import requests
import json
from datetime import datetime
from .base_widget import Widget
from utils.fonts import get_font
from config import *


# Cyan glow for "now" cards
COLOR_NOW_BORDER = (0, 255, 255)
COLOR_NOW_LABEL = (0, 255, 255)
CARD_HEIGHT = 50
CARD_GAP = 8
CARD_RADIUS = 8


class TimetableWidget(Widget):
    """Widget displaying today's class timetable as period cards."""

    def __init__(self, x, y, w, h, user_id='', api_url='https://api.smartmirror.me', view_mode='today'):
        super().__init__(x, y, w, h, "Timetable")
        self.api_url = api_url
        self.user_id = user_id
        self.view_mode = view_mode
        self.periods = []          # list of period dicts
        self.error_msg = ""
        self.last_update = 0
        self.update_interval = 300  # 5 minutes
        self._lock = threading.Lock()

        # Fonts
        self.font_time = get_font(12)           # Time range
        self.font_subject = get_font(16, bold=True)  # Subject name
        self.font_location = get_font(11)       # Location badge
        self.font_now = get_font(10, bold=True) # "NOW" label

        # Kick off initial fetch
        self._start_fetch()

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def set_user_id(self, user_id):
        """Update the user ID and trigger a re-fetch."""
        if self.user_id != user_id:
            self.user_id = user_id
            self.last_update = 0
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
        threading.Thread(target=self._fetch_timetable, daemon=True).start()

    def _fetch_timetable(self):
        try:
            url = f"{self.api_url}/api/timetable"
            params = {}
            if self.user_id:
                params['user_id'] = self.user_id
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Extract periods and viewMode dynamically from response
            periods = data.get('periods', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            view_mode = data.get('viewMode', self.view_mode) if isinstance(data, dict) else self.view_mode
            
            with self._lock:
                self.periods = periods
                self.view_mode = view_mode
                self.error_msg = ""
                self.needs_redraw = True
        except Exception as e:
            print(f"[TimetableWidget] Failed to fetch timetable: {e}")
            with self._lock:
                self.error_msg = "No classes today"
                self.periods = []
                self.needs_redraw = True

    # ------------------------------------------------------------------ #
    #  Draw                                                                #
    # ------------------------------------------------------------------ #

    def draw(self, surface, font_title, font_content, scroll_y=0):
        # Draw widget background + title via base class
        super().draw(surface, font_title, font_content, scroll_y)

        if self.needs_redraw:
            self._render_content()
            self.needs_redraw = False

        if self.content_surface:
            draw_y = self.rect.y - scroll_y
            surface.blit(self.content_surface, (self.rect.x + 20, draw_y + 50))

    def _render_content(self):
        """Build the content surface from periods based on view_mode."""
        with self._lock:
            periods = list(self.periods)
            view_mode = self.view_mode
            error_msg = self.error_msg

        content_w = self.rect.w - 40
        content_h = self.rect.h - 55

        self.content_surface = pygame.Surface((content_w, content_h), pygame.SRCALPHA)

        today_str = datetime.now().strftime('%Y-%m-%d')
        today_periods = [p for p in periods if p.get('date', today_str) == today_str]

        visible_periods = []
        if view_mode == 'week':
            visible_periods = periods
        elif view_mode == 'next':
            now_period = next((p for p in today_periods if p.get('isNow')), None)
            if now_period:
                visible_periods = [now_period]
            else:
                next_period = next((p for p in today_periods if not p.get('isDone')), None)
                visible_periods = [next_period] if next_period else []
        elif view_mode == 'remaining':
            visible_periods = [p for p in today_periods if not p.get('isDone')]
        else: # 'today'
            visible_periods = today_periods

        if not visible_periods:
            msg = error_msg if error_msg else "No classes today"
            msg_surf = self.font_subject.render(msg, True, COLOR_TEXT_DIM)
            tx = (content_w - msg_surf.get_width()) // 2
            ty = (content_h - msg_surf.get_height()) // 2
            self.content_surface.blit(msg_surf, (tx, ty))
            return

        y = 0
        for period in visible_periods:
            if y + CARD_HEIGHT > content_h:
                break  # No more space

            is_now = bool(period.get('isNow', False))
            is_done = bool(period.get('isDone', False))

            self._draw_period_card(
                surf=self.content_surface,
                period=period,
                y=y,
                card_w=content_w,
                is_now=is_now,
                is_done=is_done,
                show_day_prefix=(view_mode == 'week')
            )
            y += CARD_HEIGHT + CARD_GAP

    def _draw_period_card(self, surf, period, y, card_w, is_now, is_done, show_day_prefix=False):
        """Draw a single period card onto surf at vertical position y."""

        # --- Card background ---
        card_color = (40, 44, 52, 255)
        card_surf = pygame.Surface((card_w, CARD_HEIGHT), pygame.SRCALPHA)
        pygame.draw.rect(card_surf, card_color, card_surf.get_rect(), border_radius=CARD_RADIUS)

        # Reduce opacity for done periods
        if is_done:
            card_surf.set_alpha(120)

        # Cyan left border glow for current period
        if is_now:
            border_rect = pygame.Rect(0, 0, 4, CARD_HEIGHT)
            pygame.draw.rect(card_surf, COLOR_NOW_BORDER, border_rect,
                             border_top_left_radius=CARD_RADIUS,
                             border_bottom_left_radius=CARD_RADIUS)

        # --- Time range (left side, dimmed) ---
        start_time = period.get('startTime', period.get('start', ''))
        end_time = period.get('endTime', period.get('end', ''))
        if start_time and end_time:
            time_str = f"{start_time} - {end_time}"
        elif start_time:
            time_str = start_time
        else:
            time_str = ""

        # Prefix day name if week view
        if show_day_prefix and period.get('date'):
            try:
                dt = datetime.strptime(period.get('date'), '%Y-%m-%d')
                day_name = dt.strftime('%a') # "Mon", "Tue", etc.
                time_str = f"{day_name} {time_str}"
            except:
                pass

        if time_str:
            time_surf = self.font_time.render(time_str, True, COLOR_TEXT_DIM)
            time_x = 10 if not is_now else 14
            card_surf.blit(time_surf, (time_x, 8))

        # --- Subject name (center) ---
        subject = period.get('subject', period.get('summary', period.get('title', period.get('name', 'Unknown'))))
        subj_surf = self.font_subject.render(subject, True, COLOR_WHITE)
        # Center vertically at bottom half of card
        subj_y = CARD_HEIGHT // 2
        subj_x = 10 if not is_now else 14
        card_surf.blit(subj_surf, (subj_x, subj_y))

        # --- Location badge (right side) ---
        location = period.get('location', period.get('room', ''))
        if location:
            loc_surf = self.font_location.render(location, True, COLOR_ACCENT)
            loc_x = card_w - loc_surf.get_width() - 10
            loc_y = (CARD_HEIGHT - loc_surf.get_height()) // 2
            card_surf.blit(loc_surf, (loc_x, loc_y))

        # --- "NOW" label (top-right for active period) ---
        if is_now:
            now_surf = self.font_now.render("NOW", True, COLOR_NOW_LABEL)
            now_x = card_w - now_surf.get_width() - 10
            card_surf.blit(now_surf, (now_x, 6))

        surf.blit(card_surf, (0, y))
