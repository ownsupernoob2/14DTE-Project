# ui/menu.py
import pygame
from config import *
from utils.fonts import get_font

class GlobalMenu:
    def __init__(self, width, height, main_app):
        self.width = width
        self.height = height
        self.app = main_app # Reference to main app to trigger actions
        
        self.active = False
        self.anim_y = -400
        
        self.font_header = get_font(32, bold=True)
        self.font_item = get_font(22)
        
        self.current_screen = "main" # main, widgets, themes
        
        self.main_options = [
            {"label": "Toggle Background", "action": "toggle_bg"},
            {"label": "Add Widgets", "action": "open_widgets"},
            {"label": "Manage Users", "action": "open_users"},
            {"label": "Exit", "action": "close"}
        ]
        
        self.widget_options = [
            {"label": "Clock", "action": "add_widget", "data": "clock"},
            {"label": "Weather", "action": "add_widget", "data": "weather"},
            {"label": "Calendar", "action": "add_widget", "data": "calendar"},
            {"label": "Voice Assistant", "action": "add_widget", "data": "voice"},
            {"label": "Stocks", "action": "add_widget", "data": "crypto"},
            {"label": "News", "action": "add_widget", "data": "news"},
            {"label": "System", "action": "add_widget", "data": "system"},
            {"label": "< Back", "action": "back_main"}
        ]
        
        self.users_options = []

    def get_users_options(self):
        options = []

        # If an unknown user is detected, ONLY show the add user option
        if hasattr(self.app, 'unknown_user_detected') and self.app.unknown_user_detected:
            unknown_user = self.app.unknown_user_detected
            options.append({"label": f"Add User: {unknown_user}", "action": "add_unknown_user", "data": unknown_user})
            options.append({"label": "< Back", "action": "back_main"})
            return options  # Return early, don't show other options

        # If a user is logged in, show user-specific options
        if hasattr(self.app, 'current_user_name') and self.app.current_user_name and self.app.current_user_name != "default_user":
            user_name = self.app.current_user_name
            options.append({"label": f"User: {user_name}", "action": "user_info", "data": user_name})

            # Check if calendar is authenticated
            import os
            token_file = f'google_auth/tokens/{user_name}_token.json'
            calendar_enabled = os.path.exists(token_file)
            options.append({
                "label": f"Calendar: {'Enabled' if calendar_enabled else 'Disabled'}",
                "action": "toggle_calendar",
                "data": user_name
            })

            options.append({"label": "Reset Widget Positions", "action": "reset_widgets", "data": user_name})
            options.append({"label": "Delete My Account", "action": "delete_user", "data": user_name})
        else:
            # No user logged in - show general options
            options.append({"label": "Add User", "action": "add_user"})

            # Show all users for admin operations
            import os
            if os.path.exists('dataset'):
                users = [d for d in os.listdir('dataset') if os.path.isdir(os.path.join('dataset', d))]
                if users:
                    options.append({"label": "--- All Users ---", "action": "none"})
                    for user in sorted(users):
                        options.append({"label": f"Auth Calendar {user}", "action": "auth_calendar", "data": user})
                        options.append({"label": f"Delete {user}", "action": "delete_user", "data": user})

        options.append({"label": "< Back", "action": "back_main"})
        return options
        
        self.rects = []

    def draw(self, screen, hand_pos):
        # Animation
        target_y = self.height // 2 if self.active else -400
        self.anim_y += (target_y - self.anim_y) * 0.2
        
        if self.anim_y < -350: return

        # Darken Background
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        screen.blit(overlay, (0,0))

        # Panel
        menu_w, menu_h = 500, 450
        cx, cy = self.width // 2, int(self.anim_y)
        menu_rect = pygame.Rect(cx - menu_w//2, cy - menu_h//2, menu_w, menu_h)
        
        pygame.draw.rect(screen, (30, 30, 35), menu_rect, border_radius=20)
        pygame.draw.rect(screen, (255, 255, 255, 20), menu_rect, 1, border_radius=20)
        
        # Header
        title_map = {"main": "Settings", "widgets": "Add Widget", "users": "Manage Users"}
        title_txt = title_map.get(self.current_screen, "Menu")
        
        header = self.font_header.render(title_txt, True, COLOR_WHITE)
        screen.blit(header, (cx - header.get_width()//2, cy - menu_h//2 + 30))

        # Separator
        pygame.draw.line(screen, (255, 255, 255, 50), 
                         (menu_rect.left + 30, cy - menu_h//2 + 80), 
                         (menu_rect.right - 30, cy - menu_h//2 + 80))

        # List Options
        if self.current_screen == 'main':
            options = self.main_options
        elif self.current_screen == 'widgets':
            options = self.widget_options
        elif self.current_screen == 'users':
            options = self.users_options
        else:
            options = []
        self.rects = []
        y_off = 100
        
        for opt in options:
            row_rect = pygame.Rect(menu_rect.left + 40, cy - menu_h//2 + y_off, menu_w - 80, 50)
            self.rects.append({"rect": row_rect, "opt": opt})
            
            # Hover visual
            is_hover = row_rect.collidepoint(hand_pos[0], hand_pos[1])
            col = (255, 255, 255, 30) if is_hover else (60, 60, 60)
            
            pygame.draw.rect(screen, col, row_rect, border_radius=10)
            
            lbl = self.font_item.render(opt['label'], True, COLOR_WHITE)
            screen.blit(lbl, (row_rect.centerx - lbl.get_width()//2, row_rect.centery - lbl.get_height()//2))
            
            y_off += 60

    def handle_click(self, x, y):
        if not self.active: return False
        
        for item in self.rects:
            if item['rect'].collidepoint(x, y):
                action = item['opt']['action']
                data = item['opt'].get('data')
                
                if action == "close":
                    self.active = False
                elif action == "open_widgets":
                    self.current_screen = "widgets"
                elif action == "open_users":
                    self.current_screen = "users"
                    self.users_options = self.get_users_options()
                elif action == "back_main":
                    self.current_screen = "main"
                elif action == "toggle_bg":
                    self.app.toggle_bg()
                elif action == "create_user":
                    self.active = False # Close menu
                    self.app.start_user_creation() # Trigger keyboard
                elif action == "add_user":
                    self.active = False
                    self.app.start_user_creation()
                elif action == "delete_user":
                    self.app.delete_user(data)
                    self.users_options = self.get_users_options()
                elif action == "auth_calendar":
                    self.app.auth_calendar(data)
                    self.active = False
                elif action == "toggle_calendar":
                    self.app.toggle_calendar(data)
                    self.users_options = self.get_users_options()
                elif action == "reset_widgets":
                    self.app.reset_widgets(data)
                    self.active = False
                elif action == "user_info":
                    # Just informational, no action needed
                    pass
                elif action == "add_unknown_user":
                    self.app.add_unknown_user(data)
                    self.active = False
                elif action == "none":
                    # Separator, no action
                    pass
                elif action == "add_widget":
                    self.app.add_widget(data)
                    self.active = False
                
                return True
        return False
