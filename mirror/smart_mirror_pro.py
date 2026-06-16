import pygame
import time
import json
import os
from config import *

from ui.menu import GlobalMenu
from ui.keyboard import VirtualKeyboard
from ui.loading_screen import LoadingScreen
from utils.fonts import get_font
from widgets import (
    ClockWidget, WeatherWidget,
    NoticesWidget, TimetableWidget, NoteWidget,
)

API_URL = os.environ.get('API_URL', 'https://api.smartmirror.me')
REF_WIDTH = 1280
REF_HEIGHT = 800


def _widget_data(wd):
    data = wd.get('data', {}) or {}
    return data if isinstance(data, dict) else {}


class SmartMirrorPro:
    def __init__(self):
        pygame.init()
        windowed = os.environ.get('MIRROR_WINDOWED') == '1'
        if windowed:
            self.screen = pygame.display.set_mode((1280, 800))
            pygame.mouse.set_visible(True)
        else:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            pygame.mouse.set_visible(False)
        self.width, self.height = self.screen.get_size()
        self.clock = pygame.time.Clock()

        self.font_title = get_font(16, bold=True)
        self.font_content = get_font(18)

        self.menu = GlobalMenu(self.width, self.height, self)
        self.keyboard = VirtualKeyboard(self.width, self.height)
        self.loading_screen = LoadingScreen(self.width, self.height)

        self.show_background = True
        self.scroll_y = 0
        self.bg_image = None
        self.setup_background()

        self.hand_x = self.width // 2
        self.hand_y = self.height // 2
        self.target_hand_x = self.width // 2
        self.target_hand_y = self.height // 2
        self.thumb_index_touch = False
        self.prev_touch = False
        self.last_tap = 0

        self.current_user_id = None
        self.current_user_name = ""
        self.face_detected = False
        self.face_recognized = False
        self.face_confidence = 0.0
        self._last_state = None        # tracks last mirror state string
        self._last_user_id = None      # tracks last user_id to detect user switches

        self.widgets = []
        self.dragging_widget = None
        self.guest_notices = None

        # Transition and timing states
        self.in_grace = False
        self.guest_alpha = 0.0
        self.widgets_alpha = 255.0
        self.widgets_y_offset = 0.0
        self.guest_img = None
        self.guest_img_loaded = False

    def setup_background(self):
        self.bg_image = pygame.Surface((self.width, self.height))
        self.bg_image.fill((0, 0, 0))

    def clear_widgets(self):
        self.widgets = []
        self.dragging_widget = None

    def _layout_signature(self, fdata):
        return json.dumps({
            'state':   fdata.get('state', 'idle'),
            'user_id': fdata.get('user_id'),
            'widgets': fdata.get('widgets') or [],
        }, sort_keys=True)

    def _pct_to_pixels(self, wd):
        x = wd.get('x', 5.0)
        y = wd.get('y', 5.0)
        w = wd.get('w')
        h = wd.get('h')

        is_absolute = x > 100 or y > 100 or (w is not None and w > 100) or (h is not None and h > 100)
        if is_absolute:
            x_pct = (x / REF_WIDTH) * 100.0
            y_pct = (y / REF_HEIGHT) * 100.0
            w_pct = (w / REF_WIDTH) * 100.0 if w is not None else 18.0
            h_pct = (h / REF_HEIGHT) * 100.0 if h is not None else 13.0
        else:
            x_pct = x
            y_pct = y
            w_pct = w if w is not None else 18.0
            h_pct = h if h is not None else 13.0

        real_x = int((x_pct / 100.0) * self.width)
        real_y = int((y_pct / 100.0) * self.height)
        real_w = max(160, int((w_pct / 100.0) * self.width))
        real_h = max(80, int((h_pct / 100.0) * self.height))
        return real_x, real_y, real_w, real_h

    def apply_remote_widgets(self, remote_widgets):
        try:
            self.widgets = []
            self.dragging_widget = None
            if not remote_widgets:
                return

            for wd in remote_widgets:
                real_x, real_y, real_w, real_h = self._pct_to_pixels(wd)
                wtype = wd.get('type', '').lower()
                data = _widget_data(wd)

                if wtype == 'clock':
                    self.widgets.append(ClockWidget(real_x, real_y, real_w, real_h))
                elif wtype == 'weather':
                    self.widgets.append(WeatherWidget(real_x, real_y, real_w, real_h))
                elif wtype == 'notices':
                    kw = data.get('keyword_filter') or data.get('keywordFilter') or ''
                    speed = data.get('scroll_speed', data.get('scrollSpeed', 0.5))
                    year = data.get('year_filter') or data.get('yearFilter') or 'All'
                    cats = data.get('cat_filters') or data.get('catFilters') or None
                    self.widgets.append(NoticesWidget(real_x, real_y, real_w, real_h, API_URL, kw, speed, year, cats))
                elif wtype == 'timetable':
                    view_mode = data.get('viewMode', 'today')
                    subject = data.get('subject_filter') or data.get('subjectFilter') or ''
                    tw = TimetableWidget(
                        real_x, real_y, real_w, real_h,
                        self.current_user_id or '', API_URL,
                        view_mode=view_mode, subject_filter=subject,
                    )
                    self.widgets.append(tw)
                elif wtype == 'note':
                    note_data = wd.get('data', {}) or {}
                    self.widgets.append(NoteWidget(real_x, real_y, real_w, real_h, note_data))
        except Exception as e:
            print(f"[ERROR] Failed to apply remote widgets: {e}")
            self.clear_widgets()

    def toggle_bg(self):
        self.show_background = not self.show_background

    def add_widget(self, widget_type):
        w_pct, h_pct = 20.0, 15.0
        if widget_type == 'timetable':
            w_pct, h_pct = 28.0, 28.0
        elif widget_type == 'notices':
            w_pct, h_pct = 32.0, 30.0
        elif widget_type == 'note':
            w_pct, h_pct = 18.0, 16.0

        real_w = int((w_pct / 100.0) * self.width)
        real_h = int((h_pct / 100.0) * self.height)
        x = int(0.05 * self.width)
        y = int(0.05 * self.height)

        for w in self.widgets:
            if w.rect.x + w.rect.w > x:
                x = w.rect.x + w.rect.w + 20
            if x + real_w > self.width:
                x = int(0.05 * self.width)
                y = w.rect.y + w.rect.h + 20

        if widget_type == 'clock':
            self.widgets.append(ClockWidget(x, y, real_w, real_h))
        elif widget_type == 'notices':
            self.widgets.append(NoticesWidget(x, y, real_w, real_h, API_URL))
        elif widget_type == 'timetable':
            self.widgets.append(TimetableWidget(x, y, real_w, real_h, self.current_user_id or '', API_URL))
        elif widget_type == 'note':
            self.widgets.append(NoteWidget(x, y, real_w, real_h))

    def run(self):
        while True:
            now = time.time()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.thumb_index_touch = True
                        self.handle_click()
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
                        self.thumb_index_touch = False
                        if self.dragging_widget:
                            self.dragging_widget.handle_drag_end(self.width, self.height)
                            self.dragging_widget = None
                elif event.type == pygame.MOUSEMOTION:
                    self.target_hand_x, self.target_hand_y = event.pos

            self.update_inputs()
            self.screen.fill(COLOR_BLACK)
            if self.show_background and self.bg_image:
                self.screen.blit(self.bg_image, (0, 0))

            # ── Unrecognized Visitor Transition & Styling ─────────────────────
            # Lazy-load guest image asset if available
            if not self.guest_img_loaded:
                self.guest_img_loaded = True
                for ext in ['gif', 'png', 'jpg', 'jpeg']:
                    p = f"assets/guest.{ext}"
                    if os.path.exists(p):
                        try:
                            raw_img = pygame.image.load(p)
                            iw, ih = raw_img.get_size()
                            scale = min(260 / iw, 220 / ih)
                            self.guest_img = pygame.transform.smoothscale(raw_img, (int(iw * scale), int(ih * scale)))
                            break
                        except Exception as e:
                            print(f"[ERROR] Failed to load guest image: {e}")

            # Guest screen is driven purely by the simulator's state field
            show_guest = (self._last_state == 'guest')

            # Fade transition for guest layout
            if show_guest:
                self.guest_alpha = min(255.0, self.guest_alpha + 15.0)
            else:
                self.guest_alpha = max(0.0, self.guest_alpha - 15.0)

            if self.guest_alpha > 0:
                guest_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
                
                # Left notices
                if self.guest_notices is None:
                    w = self.width // 2 - 60
                    h = self.height - 120
                    self.guest_notices = NoticesWidget(40, 80, w, h, API_URL)
                self.guest_notices.update(0)
                self.guest_notices.draw(guest_surf, self.font_title, self.font_content, 0)

                # Right advertisement (No white background, no blue button, just clean text)
                rx = self.width // 2 + 20
                ry = 80
                rw = self.width // 2 - 60
                rh = self.height - 120

                card_rect = pygame.Rect(rx, ry, rw, rh)
                pygame.draw.rect(guest_surf, (255, 255, 255, 6), card_rect, border_radius=16)
                pygame.draw.rect(guest_surf, (255, 255, 255, 12), card_rect, 1, border_radius=16)

                font_large = get_font(32, bold=True)
                font_med = get_font(20)
                font_url = get_font(42, bold=True)

                title_lbl = font_large.render("New Visitor?", True, (240, 240, 240))
                desc_lbl1 = font_med.render("Scan your face to configure your", True, (160, 160, 160))
                desc_lbl2 = font_med.render("personalized smart mirror dashboard.", True, (160, 160, 160))

                cy = ry + 60
                guest_surf.blit(title_lbl, (rx + (rw - title_lbl.get_width()) // 2, cy))
                cy += title_lbl.get_height() + 20
                guest_surf.blit(desc_lbl1, (rx + (rw - desc_lbl1.get_width()) // 2, cy))
                guest_surf.blit(desc_lbl2, (rx + (rw - desc_lbl2.get_width()) // 2, cy + desc_lbl1.get_height() + 4))

                # Custom GIF/Image placeholder
                if self.guest_img:
                    ix = rx + (rw - self.guest_img.get_width()) // 2
                    iy = cy + desc_lbl2.get_height() + 30
                    guest_surf.blit(self.guest_img, (ix, iy))
                    cy = iy + self.guest_img.get_height() - 50
                else:
                    cy += 60

                # Big URL text
                cy += 80
                url_lbl = font_url.render("smartmirror.me", True, (96, 165, 250))
                guest_surf.blit(url_lbl, (rx + (rw - url_lbl.get_width()) // 2, cy))

                prompt_lbl = font_med.render("Sign up and register on the website", True, (120, 120, 120))
                guest_surf.blit(prompt_lbl, (rx + (rw - prompt_lbl.get_width()) // 2, cy + url_lbl.get_height() + 10))

                guest_surf.set_alpha(int(self.guest_alpha))
                self.screen.blit(guest_surf, (0, 0))

            # ── Normal User & Widget Transitions ──────────────────────────────
            if self.face_recognized and not show_guest:
                self.widgets_alpha = min(255.0, self.widgets_alpha + 18.0)
                self.widgets_y_offset = max(0.0, self.widgets_y_offset - 2.0)

                for w in self.widgets:
                    w.update(self.scroll_y)
                    if self.widgets_alpha < 255.0:
                        w_surf = pygame.Surface((w.rect.w, w.rect.h), pygame.SRCALPHA)
                        old_x, old_y = w.rect.x, w.rect.y
                        w.rect.x, w.rect.y = 0, 0
                        w.draw(w_surf, self.font_title, self.font_content, self.scroll_y)
                        w.rect.x, w.rect.y = old_x, old_y
                        w_surf.set_alpha(int(self.widgets_alpha))
                        self.screen.blit(w_surf, (w.rect.x, w.rect.y + int(self.widgets_y_offset)))
                    else:
                        w.draw(self.screen, self.font_title, self.font_content, self.scroll_y)

            if self.menu.active:
                self.menu.draw(self.screen, (self.hand_x, self.hand_y))
            if self.keyboard.active:
                self.keyboard.draw(self.screen)
            if self.loading_screen.active:
                self.loading_screen.update()
                self.loading_screen.draw(self.screen)

            self.draw_cursor()
            pygame.display.flip()
            self.clock.tick(60)

    def update_inputs(self):
        if os.path.exists(FACE_DATA_FILE):
            try:
                with open(FACE_DATA_FILE) as f:
                    fdata = json.load(f)

                self.face_detected   = fdata.get('detected', False)
                self.face_recognized = fdata.get('recognized', False)
                self.face_confidence = fdata.get('confidence', 0.0)
                self.in_grace        = fdata.get('in_grace', False)

                new_state   = fdata.get('state', 'idle')
                new_user_id = fdata.get('user_id', 'idle')
                layout_sig  = self._layout_signature(fdata)

                # Detect state changes OR user switches
                state_changed = (new_state != self._last_state)
                user_switched = (new_state == 'user' and new_user_id != self._last_user_id
                                 and new_user_id not in ('', 'idle'))

                if state_changed or user_switched:
                    self._last_state   = new_state
                    self._last_user_id = new_user_id
                    self.current_user_id   = new_user_id
                    self.current_user_name = fdata.get('user_name', '')

                    if new_state == 'user' and new_user_id not in ('', 'idle'):
                        self.apply_remote_widgets(fdata.get('widgets', []))
                        for w in self.widgets:
                            if hasattr(w, 'set_user_id'):
                                w.set_user_id(new_user_id)
                        # Smooth fade-in slide animation
                        self.widgets_alpha    = 0.0
                        self.widgets_y_offset = 30.0
                        # Reset guest screen immediately
                        self.guest_alpha = 0.0
                    else:
                        # idle or guest — clear user widgets
                        self.clear_widgets()
                        if new_state == 'guest':
                            # Reset guest notices so it re-fetches fresh content
                            self.guest_notices = None
            except Exception:
                pass

        # Align cursor instantly with mouse position
        self.hand_x = self.target_hand_x
        self.hand_y = self.target_hand_y

        if self.dragging_widget:
            self.dragging_widget.handle_drag_update(self.hand_x, self.hand_y, self.scroll_y)

    def handle_click(self):
        if self.keyboard.active:
            if self.keyboard.handle_click(self.hand_x, self.hand_y):
                return

        if self.menu.active:
            if self.menu.handle_click(self.hand_x, self.hand_y):
                return

        if time.time() - self.last_tap < 0.5:
            self.menu.active = not self.menu.active
            self.last_tap = 0
            return
        self.last_tap = time.time()

        for w in reversed(self.widgets):
            if hasattr(w, 'handle_click') and w.handle_click(self.hand_x, self.hand_y, self.scroll_y):
                return

        for w in reversed(self.widgets):
            if w.handle_drag_start(self.hand_x, self.hand_y, self.scroll_y):
                self.dragging_widget = w
                self.widgets.remove(w)
                self.widgets.append(w)
                break

    def draw_cursor(self):
        # Subtle status dot: green=user, orange=grace period checking, hidden otherwise
        if self.face_recognized:
            pygame.draw.circle(self.screen, (0, 200, 80), (self.width - 20, 20), 5)
        elif self.in_grace:
            # Orange dot = unrecognised face in grace period (checking if registered)
            pygame.draw.circle(self.screen, (255, 150, 0), (self.width - 20, 20), 5)


if __name__ == '__main__':
    SmartMirrorPro().run()
