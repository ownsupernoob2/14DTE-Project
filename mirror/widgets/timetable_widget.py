# widgets/timetable_widget.py
# Timetable — mirror mode matching web .timetable-period-card layout

import pygame
import threading
import time
import requests
from datetime import datetime
from .base_widget import Widget
from utils.fonts import get_font
from .style import font_size, COLOR_WHITE, COLOR_TEXT_DIM, COLOR_CYAN, COLOR_CYAN_BORDER, COLOR_BLUE_LOC

REF_W, REF_H = 360, 320
CARD_GAP = 8
SCROLL_SPEED = 0.4
SCROLL_INTERVAL_MS = 30
HOLD_MS = 3000


class TimetableWidget(Widget):
    def __init__(self, x, y, w, h, user_id='', api_url='https://api.smartmirror.me',
                 view_mode='today', subject_filter=''):
        super().__init__(x, y, w, h, "", chromeless=True)
        self.api_url = api_url
        self.user_id = user_id
        self.view_mode = view_mode
        self.subject_filter = subject_filter.strip().lower() if subject_filter else ''
        self.periods = []
        self.error_msg = ""
        self.last_update = 0
        self.update_interval = 300
        self._lock = threading.Lock()
        self.scroll_offset = 0.0
        self.content_height = 0
        self.content_surface = None
        self.needs_redraw = True
        self._scroll_paused_until = time.time() + HOLD_MS / 1000.0
        self._last_scroll_tick = time.time()
        self._start_fetch()

    def set_user_id(self, user_id):
        if self.user_id != user_id:
            self.user_id = user_id
            self.last_update = 0
            self._start_fetch()

    def update(self, scroll_y=0):
        super().update(scroll_y)
        if time.time() - self.last_update > self.update_interval:
            self._start_fetch()
            self.last_update = time.time()
        self._auto_scroll()

    def _auto_scroll(self):
        now = time.time()
        if now < self._scroll_paused_until:
            return
        view_h = max(1, self.rect.h - 8)
        max_offset = max(0, self.content_height - view_h)
        if max_offset <= 0:
            return
        dt_ms = (now - self._last_scroll_tick) * 1000.0
        self._last_scroll_tick = now
        self.scroll_offset += SCROLL_SPEED * (dt_ms / SCROLL_INTERVAL_MS)
        if self.scroll_offset >= max_offset:
            self.scroll_offset = 0.0
            self._scroll_paused_until = now + HOLD_MS / 1000.0

    def _start_fetch(self):
        threading.Thread(target=self._fetch_timetable, daemon=True).start()

    def _fetch_timetable(self):
        try:
            params = {'user_id': self.user_id} if self.user_id else {}
            res = requests.get(f"{self.api_url}/api/timetable", params=params, timeout=10)
            res.raise_for_status()
            data = res.json()
            periods = data.get('periods', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            view_mode = data.get('viewMode', self.view_mode) if isinstance(data, dict) else self.view_mode
            with self._lock:
                self.periods = periods
                self.view_mode = view_mode
                self.error_msg = ""
                self.needs_redraw = True
                self.scroll_offset = 0.0
                self._scroll_paused_until = time.time() + HOLD_MS / 1000.0
        except Exception as e:
            print(f"[TimetableWidget] Failed to fetch timetable: {e}")
            with self._lock:
                self.error_msg = "No classes today"
                self.periods = []
                self.needs_redraw = True

    def _scale(self):
        return font_size(14, self.rect.w, self.rect.h, REF_W, REF_H) / 14.0

    def _visible_periods(self):
        with self._lock:
            periods = list(self.periods)
            view_mode = self.view_mode
            error_msg = self.error_msg
        today_str = datetime.now().strftime('%Y-%m-%d')
        today_periods = [p for p in periods if p.get('date', today_str) == today_str]
        if view_mode == 'week':
            visible = periods
        elif view_mode == 'next':
            now_p = next((p for p in today_periods if p.get('isNow')), None)
            visible = [now_p] if now_p else ([next((p for p in today_periods if not p.get('isDone')), None)] or [])
            visible = [p for p in visible if p]
        elif view_mode == 'remaining':
            visible = [p for p in today_periods if not p.get('isDone')]
        else:
            visible = today_periods
        if self.subject_filter:
            kw = self.subject_filter
            visible = [
                p for p in visible
                if kw in (p.get('subject', p.get('summary', p.get('title', '')))).lower()
                or kw in (p.get('location', p.get('room', ''))).lower()
            ]
        return visible, error_msg

    def draw(self, surface, font_title, font_content, scroll_y=0):
        rx = self.rect.x
        ry = self.rect.y - scroll_y
        rw = self.rect.w
        rh = self.rect.h
        sc = self._scale()

        font_time = get_font(max(9, int(11 * sc)), bold=True)
        font_subject = get_font(max(11, int(13 * sc)), bold=True)
        font_loc = get_font(max(9, int(11 * sc)))
        font_now = get_font(max(8, int(10 * sc)), bold=True)

        visible, error_msg = self._visible_periods()
        clip_w = rw - 8
        clip_h = rh - 8

        if self.needs_redraw or self.content_surface is None:
            self._render_cards(visible, error_msg, clip_w, font_time, font_subject, font_loc, font_now, sc)
            self.needs_redraw = False

        if self.content_surface:
            clip = pygame.Surface((clip_w, max(1, clip_h)), pygame.SRCALPHA)
            clip.blit(self.content_surface, (0, -int(self.scroll_offset)))
            surface.blit(clip, (rx + 4, ry + 4))

    def _render_cards(self, periods, error_msg, width, font_time, font_subject, font_loc, font_now, sc):
        card_h = max(44, int(48 * sc))
        if not periods:
            msg = error_msg or "No classes today"
            self.content_surface = pygame.Surface((width, 60), pygame.SRCALPHA)
            msg_s = font_subject.render(msg, True, COLOR_TEXT_DIM)
            self.content_surface.blit(msg_s, ((width - msg_s.get_width()) // 2, 20))
            self.content_height = 60
            return

        total_h = 0
        cards = []
        for period in periods:
            card = pygame.Surface((width, card_h), pygame.SRCALPHA)
            is_now = bool(period.get('isNow', False))
            is_done = bool(period.get('isDone', False))

            bg = (6, 182, 212, 13) if is_now else (255, 255, 255, 5)
            border = COLOR_CYAN_BORDER if is_now else (255, 255, 255, 18)
            pygame.draw.rect(card, bg, card.get_rect(), border_radius=12)
            pygame.draw.rect(card, border, card.get_rect(), 1, border_radius=12)
            if is_now:
                glow = pygame.Surface((width, card_h), pygame.SRCALPHA)
                pygame.draw.rect(glow, (6, 182, 212, 38), glow.get_rect(), border_radius=12)
                card.blit(glow, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

            start = period.get('startTime', period.get('start', ''))
            end = period.get('endTime', period.get('end', ''))
            time_str = f"{start} – {end}" if start and end else (start or '')
            subject = period.get('subject', period.get('summary', period.get('title', period.get('name', 'Period'))))
            location = period.get('location', period.get('room', ''))

            x = 12
            if time_str:
                time_s = font_time.render(time_str, True, COLOR_TEXT_DIM)
                card.blit(time_s, (x, (card_h - time_s.get_height()) // 2))
                x += time_s.get_width() + 12

            subj_color = (102, 102, 102) if is_done else COLOR_WHITE
            max_subj_w = width - x - 120
            subject_display = subject
            subj_s = font_subject.render(subject_display, True, subj_color)
            while subj_s.get_width() > max_subj_w and len(subject_display) > 3:
                subject_display = subject_display[:-4] + '…'
                subj_s = font_subject.render(subject_display, True, subj_color)
            if is_done:
                pygame.draw.line(card, subj_color, (x, card_h // 2), (x + subj_s.get_width(), card_h // 2), 1)
            card.blit(subj_s, (x, (card_h - subj_s.get_height()) // 2))

            right_x = width - 10
            if is_now:
                now_s = font_now.render("IN PROGRESS", True, COLOR_CYAN)
                now_w = now_s.get_width() + 14
                now_rect = pygame.Rect(right_x - now_w, (card_h - now_s.get_height() - 8) // 2, now_w, now_s.get_height() + 8)
                pygame.draw.rect(card, (6, 182, 212, 38), now_rect, border_radius=6)
                pygame.draw.rect(card, (6, 182, 212, 89), now_rect, 1, border_radius=6)
                card.blit(now_s, (now_rect.x + 7, now_rect.y + 4))
                right_x = now_rect.x - 8

            if location:
                loc_s = font_loc.render(location, True, COLOR_BLUE_LOC)
                loc_w = loc_s.get_width() + 12
                loc_rect = pygame.Rect(right_x - loc_w, (card_h - loc_s.get_height() - 8) // 2, loc_w, loc_s.get_height() + 8)
                pygame.draw.rect(card, (59, 130, 246, 25), loc_rect, border_radius=6)
                pygame.draw.rect(card, (59, 130, 246, 51), loc_rect, 1, border_radius=6)
                card.blit(loc_s, (loc_rect.x + 6, loc_rect.y + 4))

            if is_done:
                card.set_alpha(102)
            cards.append(card)
            total_h += card_h + CARD_GAP

        self.content_height = total_h
        self.content_surface = pygame.Surface((width, total_h), pygame.SRCALPHA)
        y = 0
        for card in cards:
            self.content_surface.blit(card, (0, y))
            y += card.get_height() + CARD_GAP
