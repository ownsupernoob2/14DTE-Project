import pygame
import threading
import time
import json
import os
import requests
import math
import random
from datetime import datetime
from config import *

# Load Modules
from ui.menu import GlobalMenu
from ui.keyboard import VirtualKeyboard
from ui.loading_screen import LoadingScreen
from utils.fonts import get_font
from widgets import Widget, ClockWidget, WeatherWidget, GoogleCalendarWidget, VoiceAssistantWidget, NoticesWidget, TimetableWidget, NoteWidget

API_URL = os.environ.get('API_URL', 'https://api.smartmirror.me')

class SmartMirrorPro:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.width, self.height = self.screen.get_size()
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()

        # Core Fonts
        self.font_title = get_font(16, bold=True)
        self.font_content = get_font(18)

        # Components
        self.menu = GlobalMenu(self.width, self.height, self)
        self.keyboard = VirtualKeyboard(self.width, self.height)
        self.loading_screen = LoadingScreen(self.width, self.height)
        
        # State
        self.show_background = True
        self.scroll_y = 0
        self.target_scroll_y = 0
        self.bg_image = None
        self.setup_background()
        
        # Hand / Input
        self.hand_x = self.width // 2
        self.hand_y = self.height // 2
        self.target_hand_x = self.width // 2
        self.target_hand_y = self.height // 2
        
        self.thumb_index_touch = False
        self.prev_touch = False
        self.last_tap = 0
        
        # User
        self.current_user_id = None
        self.current_user_name = ""
        self.face_detected = False
        self.face_confidence = 0.0
        
        # Widgets
        self.widgets = []
        self.load_widgets(["clock", "weather"]) # Default
        self.dragging_widget = None

    def setup_background(self):
        self.bg_image = pygame.Surface((self.width, self.height))
        self.bg_image.fill((0,0,0))

    def load_widgets(self, widget_list, user_name=""):
        self.widgets = []
        # Calculate standard default relative sizes based on mirror screen dimensions
        w_clock = int(0.25 * self.width)
        h_clock = int(0.18 * self.height)
        w_weather = int(0.20 * self.width)
        h_weather = int(0.18 * self.height)
        w_calendar = int(0.28 * self.width)
        h_calendar = int(0.28 * self.height)
        
        x = int(0.04 * self.width)
        y = int(0.04 * self.height)
        
        for name in widget_list:
            if name == "clock": 
                self.widgets.append(ClockWidget(x, y, w_clock, h_clock))
            if name == "weather": 
                self.widgets.append(WeatherWidget(x, y + h_clock + 20, w_weather, h_weather))
            if name == "calendar": 
                self.widgets.append(GoogleCalendarWidget(x + w_clock + 20, y + h_clock + 20, w_calendar, h_calendar, user_name))

    def apply_remote_widgets(self, remote_widgets):
        try:
            self.widgets = []
            user_name = self.current_user_name if self.current_user_name else ""
            
            if not remote_widgets:
                self.load_widgets(["clock", "weather"], user_name)
                return
            
            for wd in remote_widgets:
                x = wd.get('x', 5.0)
                y = wd.get('y', 5.0)
                w = wd.get('w')
                h = wd.get('h')
                wtype = wd.get('type', '').lower()
                
                # Check if coordinates are absolute (pixels) or relative (percentage 0-100)
                is_absolute = False
                if x > 100 or y > 100 or (w is not None and w > 100) or (h is not None and h > 100):
                    is_absolute = True
                
                if is_absolute:
                    x_pct = (x / 1280.0) * 100.0
                    y_pct = (y / 800.0) * 100.0
                    w_pct = (w / 1280.0) * 100.0 if w is not None else 18.0
                    h_pct = (h / 800.0) * 100.0 if h is not None else 13.0
                else:
                    x_pct = x
                    y_pct = y
                    w_pct = w if w is not None else 18.0
                    h_pct = h if h is not None else 13.0
                
                # Map percentages (0-100) to actual mirror window dimensions
                real_x = int((x_pct / 100.0) * self.width)
                real_y = int((y_pct / 100.0) * self.height)
                real_w = int((w_pct / 100.0) * self.width)
                real_h = int((h_pct / 100.0) * self.height)
                
                # Ensure minimum sizes to avoid completely collapsed widgets
                real_w = max(160, real_w)
                real_h = max(80, real_h)
                
                if wtype == 'clock' or wd.get('type') == 'ClockWidget':
                    self.widgets.append(ClockWidget(real_x, real_y, real_w, real_h))
                elif wtype == 'weather' or wd.get('type') == 'WeatherWidget':
                    self.widgets.append(WeatherWidget(real_x, real_y, real_w, real_h))
                elif wtype == 'calendar' or wd.get('type') == 'GoogleCalendarWidget':
                    self.widgets.append(GoogleCalendarWidget(real_x, real_y, real_w, real_h, user_name))
                elif wtype == 'notices' or wd.get('type') == 'DailyNoticesWidget':
                    self.widgets.append(NoticesWidget(real_x, real_y, real_w, real_h, API_URL))
                elif wtype == 'timetable' or wd.get('type') == 'TimetableWidget':
                    tw = TimetableWidget(real_x, real_y, real_w, real_h, self.current_user_id or '', API_URL)
                    self.widgets.append(tw)
                elif wtype == 'note':
                    note_data = wd.get('data', '') or ''
                    self.widgets.append(NoteWidget(real_x, real_y, real_w, real_h, note_data))
        except Exception as e:
            print(f"[ERROR] Failed to apply remote widgets: {e}")
            self.load_widgets(["clock", "weather"], self.current_user_name)

    # --- Actions called by Menu ---
    def toggle_bg(self):
        self.show_background = not self.show_background

    def save_profile(self, user_id):
        # We don't save to API from mirror right now, UI handles it
        pass

    def add_widget(self, widget_type):
        w_pct = 20.0
        h_pct = 15.0
        if widget_type == "calendar" or widget_type == "timetable":
            w_pct = 28.0
            h_pct = 28.0
        elif widget_type == "notices":
            w_pct = 32.0
            h_pct = 30.0
            
        real_w = int((w_pct / 100.0) * self.width)
        real_h = int((h_pct / 100.0) * self.height)
        
        x = int(0.05 * self.width)
        y = int(0.05 * self.height)
        
        for w in self.widgets:
            if w.rect.x + w.rect.w > x: x = w.rect.x + w.rect.w + 20
            if x + real_w > self.width:
                x = int(0.05 * self.width)
                y = w.rect.y + w.rect.h + 20
        
        if widget_type == "clock":
            self.widgets.append(ClockWidget(x, y, real_w, real_h))
        elif widget_type == "weather":
            self.widgets.append(WeatherWidget(x, y, real_w, real_h))
        elif widget_type == "calendar":
            self.widgets.append(GoogleCalendarWidget(x, y, real_w, real_h, self.current_user_name))
        elif widget_type == "voice":
            self.widgets.append(VoiceAssistantWidget(x, y, real_w, real_h))
        elif widget_type == "notices":
            self.widgets.append(NoticesWidget(x, y, real_w, real_h, API_URL))
        elif widget_type == "timetable":
            self.widgets.append(TimetableWidget(x, y, real_w, real_h, self.current_user_id or '', API_URL))
        elif widget_type == "note":
            self.widgets.append(NoteWidget(x, y, real_w, real_h))

    def reset_widgets(self, user_name):
        self.load_widgets(["clock", "weather", "calendar"], user_name)
        print(f"Widget positions reset for {user_name}")

    # --- Main Loop ---
    def run(self):
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: pygame.quit(); return

            self.update_inputs()

            # Render
            self.screen.fill(COLOR_BLACK)
            if self.show_background and self.bg_image:
                self.screen.blit(self.bg_image, (0,0))

            # Widgets
            for w in self.widgets:
                w.update(self.scroll_y)
                w.draw(self.screen, self.font_title, self.font_content, self.scroll_y)

            # Overlays
            if self.menu.active:
                self.menu.draw(self.screen, (self.hand_x, self.hand_y))

            if self.keyboard.active:
                self.keyboard.draw(self.screen)

            if self.loading_screen.active:
                self.loading_screen.update()
                self.loading_screen.draw(self.screen)

            # Cursor
            self.draw_cursor()
            
            pygame.display.flip()
            self.clock.tick(60)

    def update_inputs(self):
        if os.path.exists(HAND_DATA_FILE):
            try:
                with open(HAND_DATA_FILE, 'r') as f:
                    data = json.load(f)
                    
                    self.target_hand_x = int(data.get('hand_center_x', 320) * self.width / 640)
                    self.target_hand_y = int(data.get('hand_center_y', 240) * self.height / 480)
                    self.thumb_index_touch = data.get('thumb_index_touch', False)
                    
                    if self.thumb_index_touch and not self.prev_touch:
                         self.handle_click()
                    
                    if not self.thumb_index_touch and self.prev_touch:
                         if self.dragging_widget:
                            self.dragging_widget.handle_drag_end(self.width, self.height)
                            self.dragging_widget = None

                    self.prev_touch = self.thumb_index_touch
                    
                    if os.path.exists(FACE_DATA_FILE):
                        try:
                            with open(FACE_DATA_FILE) as f:
                                fdata = json.load(f)
                                new_user_id = fdata.get('user_id')
                                self.face_detected = fdata.get('detected', False)
                                self.face_confidence = fdata.get('confidence', 0.0)

                                if new_user_id != self.current_user_id:
                                    self.current_user_id = new_user_id
                                    self.current_user_name = fdata.get('user_name', '')

                                    if new_user_id and new_user_id != "idle":
                                        remote_widgets = fdata.get('widgets', [])
                                        self.apply_remote_widgets(remote_widgets)
                                        for w in self.widgets:
                                            if hasattr(w, 'set_user_id'):
                                                w.set_user_id(new_user_id)
                                    else:
                                        self.load_widgets(["clock", "weather"])
                        except: pass
            except: pass
            
        self.hand_x += (self.target_hand_x - self.hand_x) * 0.3
        self.hand_y += (self.target_hand_y - self.hand_y) * 0.3

        if self.dragging_widget:
            self.dragging_widget.handle_drag_update(self.hand_x, self.hand_y, self.scroll_y)

    def handle_click(self):
        if self.keyboard.active:
            if self.keyboard.handle_click(self.hand_x, self.hand_y): return
        
        if self.menu.active:
            if self.menu.handle_click(self.hand_x, self.hand_y): return
        
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
                self.widgets.remove(w); self.widgets.append(w)
                break
        
        if not self.dragging_widget and self.thumb_index_touch:
             if self.dragging_widget:
                 self.dragging_widget.handle_drag_end(self.width, self.height)
                 self.dragging_widget = None

    def draw_cursor(self):
         color = COLOR_ACCENT if self.thumb_index_touch else COLOR_WHITE
         pygame.draw.circle(self.screen, color, (int(self.hand_x), int(self.hand_y)), 10, 2)
         pygame.draw.circle(self.screen, color, (int(self.hand_x), int(self.hand_y)), 4)
         
         if not self.face_detected:
             dot_color = (255, 0, 0)
         elif self.face_confidence < 0.5:
             dot_color = (255, 165, 0)
         else:
             dot_color = (0, 255, 0)
         
         pygame.draw.circle(self.screen, dot_color, (self.width - 20, 20), 5)
         
         if self.face_detected and self.face_confidence >= 0.5 and self.current_user_id and self.current_user_id != "idle":
             display_text = self.current_user_name if self.current_user_name else self.current_user_id
             if self.current_user_name and self.current_user_name != "default_user":
                 display_text += f" ({self.current_user_id})"
             else:
                 display_text = self.current_user_id
             
             name_lbl = self.font_title.render(display_text, True, dot_color)
             self.screen.blit(name_lbl, (self.width - 30 - name_lbl.get_width(), 12))

if __name__ == '__main__':
    app = SmartMirrorPro()
    app.run()
