# ui/base_widget.py
import pygame
from config import *

class Widget:
    def __init__(self, x, y, w, h, title):
        self.rect = pygame.Rect(x, y, w, h)
        self.target_pos = [x, y]
        self.title = title
        self.dragging = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0
        self.content_surface = None
        self.needs_redraw = True
        self.alpha = 0
        
    def update(self, scroll_y=0):
        if not self.dragging:
            dx = self.target_pos[0] - self.rect.x
            dy = self.target_pos[1] - self.rect.y
            if abs(dx) > 1 or abs(dy) > 1:
                self.rect.x += dx * 0.2
                self.rect.y += dy * 0.2
            else:
                self.rect.x = self.target_pos[0]
                self.rect.y = self.target_pos[1]
        
        if self.alpha < 255:
            self.alpha = min(255, self.alpha + 5)

    def draw(self, surface, font_title, font_content, scroll_y=0):
        draw_y = self.rect.y - scroll_y
        if draw_y > surface.get_height() or draw_y + self.rect.h < 0:
            return

        s = pygame.Surface((self.rect.w, self.rect.h), pygame.SRCALPHA)
        bg_color = list(COLOR_BG_OVERLAY)
        bg_color[3] = int(bg_color[3] * (self.alpha / 255))
        pygame.draw.rect(s, bg_color, s.get_rect(), border_radius=15)
        
        if self.dragging:
            pygame.draw.rect(s, (255, 255, 255, 80), s.get_rect(), 1, border_radius=15)

        if self.title:
            title_surf = font_title.render(self.title.upper(), True, COLOR_TEXT_DIM)
            s.blit(title_surf, (20, 15))

        if self.content_surface:
            s.blit(self.content_surface, (20, 50))

        surface.blit(s, (self.rect.x, draw_y))

    def handle_drag_start(self, x, y, scroll_y=0):
        adj_y = y + scroll_y
        if self.rect.collidepoint(x, adj_y):
            self.dragging = True
            self.drag_offset_x = x - self.rect.x
            self.drag_offset_y = adj_y - self.rect.y
            return True
        return False

    def handle_drag_update(self, x, y, scroll_y=0):
        if self.dragging:
            self.rect.x = x - self.drag_offset_x
            self.rect.y = (y + scroll_y) - self.drag_offset_y
            self.target_pos = [self.rect.x, self.rect.y]

    def handle_drag_end(self, screen_w, screen_h):
        if self.dragging:
            self.dragging = False
            col_width = screen_w / GRID_COLS
            row_height = screen_h / GRID_ROWS
            col = round(self.rect.x / col_width)
            row = round(self.rect.y / row_height)
            col = max(0, min(col, GRID_COLS - 1))
            row = max(0, min(row, GRID_ROWS - 1))
            self.target_pos[0] = int(col * col_width + GRID_GAP)
            self.target_pos[1] = int(row * row_height + GRID_GAP)
