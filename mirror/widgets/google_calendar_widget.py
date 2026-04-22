# widgets/google_calendar_widget.py
import time
import pygame
import datetime
from .base_widget import Widget
from utils.fonts import get_font
from config import *

# Define local colors if not in config
COLOR_EVENT_BG = (40, 44, 52)      # Dark grey for card background
COLOR_ACCENT = (100, 149, 237)     # Cornflower blue for date ribbon
COLOR_TIME = (170, 170, 170)       # Dim grey for time
COLOR_TODAY = (255, 99, 71)        # Tomato red for "Today" events

class GoogleCalendarWidget(Widget):
    """Widget displaying upcoming Google Calendar events with a modern card layout."""

    def __init__(self, x, y, w, h, user_name=""):
        super().__init__(x, y, w, h, "Calendar")
        self.user_name = user_name
        self.events = []
        self.last_update = 0
        self.update_interval = 300
        
        # Fonts
        self.font_day = get_font(22, bold=True)    # For "26"
        self.font_month = get_font(10, bold=True)  # For "JAN"
        self.font_title = get_font(18)             # For Event Title
        self.font_time = get_font(14)              # For "2:00 PM"
        
        self.needs_redraw = True

    def update(self, scroll_y=0):
        super().update(scroll_y)
        current_time = time.time()
        if current_time - self.last_update > self.update_interval:
            self.fetch_events()
            self.last_update = current_time
            self.needs_redraw = True

    def fetch_events(self):
        if not self.user_name:
            self.events = []
            return
        try:
            from google_calendar import get_calendar_events
            # Fetch a few more than needed to ensure we fill the space
            self.events = get_calendar_events(self.user_name, max_results=6)
        except Exception as e:
            print(f"Error fetching calendar: {e}")
            self.events = []

    def _parse_google_date(self, start_obj):
        """Helper to parse Google date dicts into usable datetime objects."""
        # Check for 'dateTime' (specific time) or 'date' (all day)
        raw_date = start_obj.get('dateTime', start_obj.get('date'))
        
        # Handle 'Z' UTC indicator or offsets if necessary for basic parsing
        # Simple truncation for ISO format compatibility
        if 'T' in raw_date:
            date_str = raw_date.split('+')[0].replace('Z', '')
            dt_obj = datetime.datetime.fromisoformat(date_str)
            is_all_day = False
        else:
            dt_obj = datetime.datetime.strptime(raw_date, "%Y-%m-%d")
            is_all_day = True
            
        return dt_obj, is_all_day

    def draw(self, surface, font_title, font_content, scroll_y=0):
        super().draw(surface, font_title, font_content, scroll_y)

        if self.needs_redraw:
            # Create content surface
            self.content_surface = pygame.Surface((self.rect.w - 30, self.rect.h - 50), pygame.SRCALPHA)
            
            if not self.events:
                self._draw_empty_state()
            else:
                self._draw_event_list()
                
            self.needs_redraw = False

    def _draw_empty_state(self):
        msg = "No upcoming events" if self.user_name else "No user selected"
        text_surf = self.font_time.render(msg, True, COLOR_TEXT_DIM)
        # Center the text
        tx = (self.content_surface.get_width() - text_surf.get_width()) // 2
        ty = (self.content_surface.get_height() - text_surf.get_height()) // 2
        self.content_surface.blit(text_surf, (tx, ty))

    def _draw_event_list(self):
        y_offset = 0
        card_height = 50
        gap = 10
        card_width = self.content_surface.get_width()

        today = datetime.datetime.now().date()

        for event in self.events[:5]:
            start_data = event['start']
            dt_obj, is_all_day = self._parse_google_date(start_data)
            summary = event.get('summary', 'No Title')

            # --- 1. Draw Card Background ---
            card_rect = pygame.Rect(0, y_offset, card_width, card_height)
            pygame.draw.rect(self.content_surface, COLOR_EVENT_BG, card_rect, border_radius=8)

            # --- 2. Draw Date Ribbon (Left Side) ---
            # Check if event is today for special coloring
            is_today = dt_obj.date() == today
            ribbon_color = COLOR_TODAY if is_today else COLOR_ACCENT

            # Background for date
            date_box_w = 50
            date_box_rect = pygame.Rect(0, y_offset, date_box_w, card_height)
            pygame.draw.rect(self.content_surface, ribbon_color, date_box_rect, border_top_left_radius=8, border_bottom_left_radius=8)

            # Day Number (e.g., "26")
            day_str = str(dt_obj.day)
            day_surf = self.font_day.render(day_str, True, COLOR_WHITE)
            day_x = date_box_w/2 - day_surf.get_width()/2
            self.content_surface.blit(day_surf, (day_x, y_offset + 5))

            # Month Name (e.g., "JAN")
            month_str = dt_obj.strftime("%b").upper()
            month_surf = self.font_month.render(month_str, True, (240, 240, 240))
            month_x = date_box_w/2 - month_surf.get_width()/2
            self.content_surface.blit(month_surf, (month_x, y_offset + 30))

            # --- 3. Draw Event Details (Right Side) ---
            text_x = date_box_w + 10
            
            # Title
            # Simple truncation logic
            max_title_width = card_width - text_x - 10
            title_surf = self.font_title.render(summary, True, COLOR_WHITE)
            
            # If title is too long, crop it (basic implementation)
            if title_surf.get_width() > max_title_width:
                # Re-render with fewer chars roughly
                avg_char_w = 10 
                max_chars = int(max_title_width / avg_char_w)
                title_surf = self.font_title.render(summary[:max_chars] + "...", True, COLOR_WHITE)
            
            self.content_surface.blit(title_surf, (text_x, y_offset + 5))

            # Time
            if is_all_day:
                time_str = "All Day"
            else:
                time_str = dt_obj.strftime("%I:%M %p").lstrip('0') # 2:00 PM
            
            time_surf = self.font_time.render(time_str, True, COLOR_TIME)
            self.content_surface.blit(time_surf, (text_x, y_offset + 28))

            y_offset += card_height + gap

    def set_user(self, user_name):
        if self.user_name != user_name:
            self.user_name = user_name
            self.fetch_events()
            self.needs_redraw = True