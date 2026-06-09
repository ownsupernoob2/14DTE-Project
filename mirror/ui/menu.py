# ui/menu.py
import pygame
from config import *
from utils.fonts import get_font


class GlobalMenu:
    def __init__(self, width, height, main_app):
        self.width = width
        self.height = height
        self.app = main_app
        self.active = False
        self.anim_y = -400
        self.font_header = get_font(32, bold=True)
        self.font_item = get_font(22)
        self.current_screen = "main"
        self.rects = []
        self.main_options = [
            {"label": "Toggle Background", "action": "toggle_bg"},
            {"label": "Add Widgets", "action": "open_widgets"},
            {"label": "Exit", "action": "close"},
        ]
        self.widget_options = [
            {"label": "Clock", "action": "add_widget", "data": "clock"},
            {"label": "Notices", "action": "add_widget", "data": "notices"},
            {"label": "Timetable", "action": "add_widget", "data": "timetable"},
            {"label": "Note", "action": "add_widget", "data": "note"},
            {"label": "< Back", "action": "back_main"},
        ]

    def draw(self, screen, hand_pos):
        target_y = self.height // 2 if self.active else -400
        self.anim_y += (target_y - self.anim_y) * 0.2
        if self.anim_y < -350:
            return
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        screen.blit(overlay, (0, 0))
        menu_w, menu_h = 500, 400
        cx, cy = self.width // 2, int(self.anim_y)
        menu_rect = pygame.Rect(cx - menu_w // 2, cy - menu_h // 2, menu_w, menu_h)
        pygame.draw.rect(screen, (30, 30, 35), menu_rect, border_radius=20)
        pygame.draw.rect(screen, (255, 255, 255, 20), menu_rect, 1, border_radius=20)
        title_map = {"main": "Settings", "widgets": "Add Widget"}
        header = self.font_header.render(title_map.get(self.current_screen, "Menu"), True, COLOR_WHITE)
        screen.blit(header, (cx - header.get_width() // 2, cy - menu_h // 2 + 30))
        pygame.draw.line(screen, (255, 255, 255, 50),
                         (menu_rect.left + 30, cy - menu_h // 2 + 80),
                         (menu_rect.right - 30, cy - menu_h // 2 + 80))
        options = self.main_options if self.current_screen == 'main' else self.widget_options
        self.rects = []
        y_off = 100
        for opt in options:
            row_rect = pygame.Rect(menu_rect.left + 40, cy - menu_h // 2 + y_off, menu_w - 80, 50)
            self.rects.append({"rect": row_rect, "opt": opt})
            is_hover = row_rect.collidepoint(hand_pos[0], hand_pos[1])
            col = (255, 255, 255, 30) if is_hover else (60, 60, 60)
            pygame.draw.rect(screen, col, row_rect, border_radius=10)
            lbl = self.font_item.render(opt['label'], True, COLOR_WHITE)
            screen.blit(lbl, (row_rect.centerx - lbl.get_width() // 2, row_rect.centery - lbl.get_height() // 2))
            y_off += 60

    def handle_click(self, x, y):
        if not self.active:
            return False
        for item in self.rects:
            if item['rect'].collidepoint(x, y):
                action = item['opt']['action']
                data = item['opt'].get('data')
                if action == "close":
                    self.active = False
                elif action == "open_widgets":
                    self.current_screen = "widgets"
                elif action == "back_main":
                    self.current_screen = "main"
                elif action == "toggle_bg":
                    self.app.toggle_bg()
                elif action == "add_widget":
                    self.app.add_widget(data)
                    self.active = False
                return True
        return False
