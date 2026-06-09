# widgets/timetable_widget.py
# Timetable widget - shows today's schedule from ICS via API

import pygame
import threading
import time
import requests
from datetime import datetime
from .base_widget import Widget
from utils.fonts import get_font
from config import *

COLOR_NOW_BORDER = (0, 255, 255)
COLOR_NOW_LABEL = (0, 255, 255)
CARD_HEIGHT = 50
CARD_GAP = 8
CARD_RADIUS = 8


class TimetableWidget(Widget):
    def __init__(self, x, y, w, h, user_id='', api_url='https://api.smartmirror.me',
                 view_mode='today', subject_filter=''):
        super().__init__(x, y, w, h, "Timetable")
        self.api_url = api_url
        self.user_id = user_id
        self.view_mode = view_mode
        self.subject_filter = subject_filter.strip().lower() if subject_filter else ''
        self.periods = []
        self.error_msg = ""
        self.last_update = 0
        self.update_interval = 300
        self._lock = threading.Lock()
        self.font_time = get_font(12)
        self.font_subject = get_font(16, bold=True)
        self.font_location = get_font(11)
        self.font_now = get_font(10, bold=True)
        self._start_fetch()

    def set_user_id(self, user_id):
        if self.user_id != user_id:
            self.user_id = user_id
            self.last_update = 0
            self._start_fetch()

    def set_subject_filter(self, subject_filter):
        self.subject_filter = subject_filter.strip().lower() if subject_filter else ''
        with self._lock:
            self.needs_redraw = True

    def update(self, scroll_y=0):
        super().update(scroll_y)
        if time.time() - self.last_update > self.update_interval:
            self._start_fetch()
            self.last_update = time.time()

    def _start_fetch(self):
        threading.Thread(target=self._fetch_timetable, daemon=True).start()

    def _fetch_timetable(self):
        try:
            url = f"{self.api_url}/api/timetable"
            params = {'user_id': self.user_id} if self.user_id else {}
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
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

    def draw(self, surface, font_title, font_content, scroll_y=0):
        super().draw(surface, font_title, font_content, scroll_y)
        if self.needs_redraw:
            self._render_content()
            self.needs_redraw = False
        if self.content_surface:
            draw_y = self.rect.y - scroll_y
            surface.blit(self.content_surface, (self.rect.x + 20, draw_y + 50))

    def _render_content(self):
        with self._lock:
            periods = list(self.periods)
            view_mode = self.view_mode
            error_msg = self.error_msg
        content_w = self.rect.w - 40
        content_h = self.rect.h - 55
        self.content_surface = pygame.Surface((content_w, content_h), pygame.SRCALPHA)
        today_str = datetime.now().strftime('%Y-%m-%d')
        today_periods = [p for p in periods if p.get('date', today_str) == today_str]
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
        else:
            visible_periods = today_periods
        if self.subject_filter:
            kw = self.subject_filter
            visible_periods = [
                p for p in visible_periods
                if kw in (p.get('subject', p.get('summary', p.get('title', '')))).lower()
                or kw in (p.get('location', p.get('room', ''))).lower()
            ]
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
                break
            self._draw_period_card(
                self.content_surface, period, y, content_w,
                bool(period.get('isNow', False)),
                bool(period.get('isDone', False)),
                view_mode == 'week',
            )
            y += CARD_HEIGHT + CARD_GAP

    def _draw_period_card(self, surf, period, y, card_w, is_now, is_done, show_day_prefix=False):
        card_surf = pygame.Surface((card_w, CARD_HEIGHT), pygame.SRCALPHA)
        pygame.draw.rect(card_surf, (40, 44, 52, 255), card_surf.get_rect(), border_radius=CARD_RADIUS)
        if is_done:
            card_surf.set_alpha(120)
        if is_now:
            border_rect = pygame.Rect(0, 0, 4, CARD_HEIGHT)
            pygame.draw.rect(card_surf, COLOR_NOW_BORDER, border_rect,
                             border_top_left_radius=CARD_RADIUS,
                             border_bottom_left_radius=CARD_RADIUS)
        start_time = period.get('startTime', period.get('start', ''))
        end_time = period.get('endTime', period.get('end', ''))
        time_str = f"{start_time} - {end_time}" if start_time and end_time else (start_time or '')
        if show_day_prefix and period.get('date'):
            try:
                dt = datetime.strptime(period.get('date'), '%Y-%m-%d')
                time_str = f"{dt.strftime('%a')} {time_str}"
            except Exception:
                pass
        if time_str:
            time_surf = self.font_time.render(time_str, True, COLOR_TEXT_DIM)
            card_surf.blit(time_surf, (14 if is_now else 10, 8))
        subject = period.get('subject', period.get('summary', period.get('title', period.get('name', 'Unknown'))))
        subj_surf = self.font_subject.render(subject, True, COLOR_WHITE)
        card_surf.blit(subj_surf, (14 if is_now else 10, CARD_HEIGHT // 2))
        location = period.get('location', period.get('room', ''))
        if location:
            loc_surf = self.font_location.render(location, True, COLOR_ACCENT)
            card_surf.blit(loc_surf, (card_w - loc_surf.get_width() - 10, (CARD_HEIGHT - loc_surf.get_height()) // 2))
        if is_now:
            now_surf = self.font_now.render("NOW", True, COLOR_NOW_LABEL)
            card_surf.blit(now_surf, (card_w - now_surf.get_width() - 10, 6))
        surf.blit(card_surf, (0, y))
