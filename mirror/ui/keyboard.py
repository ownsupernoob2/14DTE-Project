# ui/keyboard.py
import pygame
from config import *
from utils.fonts import get_font

class VirtualKeyboard:
    def __init__(self, screen_w, screen_h):
        self.active = False
        self.text_buffer = ""
        self.callback = None
        self.screen_w = screen_w
        self.screen_h = screen_h
        
        self.keys = [
            '1234567890',
            'QWERTYUIOP',
            'ASDFGHJKL',
            'ZXCVBNM'
        ]
        self.key_rects = []
        self.font = get_font(28)
        
        self.layout_keys()

    def layout_keys(self):
        key_w, key_h = 60, 60
        margin = 10
        start_y = self.screen_h // 2 + 50
        
        self.key_rects = []
        for i, row in enumerate(self.keys):
            row_w = len(row) * (key_w + margin) - margin
            start_x = (self.screen_w - row_w) // 2
            
            for j, char in enumerate(row):
                x = start_x + j * (key_w + margin)
                y = start_y + i * (key_h + margin)
                rect = pygame.Rect(x, y, key_w, key_h)
                self.key_rects.append({'char': char, 'rect': rect})
        
        # Add Space and Enter
        enter_rect = pygame.Rect(self.screen_w // 2 + 50, start_y + 4 * (key_h + margin), 150, 60)
        delete_rect = pygame.Rect(self.screen_w // 2 - 200, start_y + 4 * (key_h + margin), 150, 60)
        close_rect = pygame.Rect(self.screen_w // 2 + 250, start_y - 60, 50, 50) # Close button (X)

        self.key_rects.append({'char': 'ENTER', 'rect': enter_rect})
        self.key_rects.append({'char': 'DEL', 'rect': delete_rect})
        self.key_rects.append({'char': 'X', 'rect': close_rect})


    def open(self, callback, initial_text=""):
        self.active = True
        self.text_buffer = initial_text
        self.callback = callback

    def close(self):
        self.active = False
        self.callback = None

    def handle_click(self, x, y):
        if not self.active: return False
        
        for k in self.key_rects:
            if k['rect'].collidepoint(x, y):
                char = k['char']
                if char == 'DEL':
                    self.text_buffer = self.text_buffer[:-1]
                elif char == 'ENTER':
                    if self.callback: self.callback(self.text_buffer)
                    self.close()
                elif char == 'X':
                    self.close()
                else:
                    self.text_buffer += char
                return True
        return False

    def draw(self, screen):
        if not self.active: return
        
        # Overlay
        s = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        s.fill((0, 0, 0, 200))
        screen.blit(s, (0,0))
        
        # Input Box
        pygame.draw.rect(screen, (50, 50, 50), (self.screen_w//2 - 200, self.screen_h//2 - 50, 400, 60), border_radius=10)
        text = self.font.render(self.text_buffer + "|", True, COLOR_WHITE)
        screen.blit(text, (self.screen_w//2 - text.get_width()//2, self.screen_h//2 - 35))

        # Keys
        for k in self.key_rects:
            char = k['char']
            rect = k['rect']
            
            # Hover/Active Style can be done later with hand cursor pos
            color = (60, 60, 60)
            if char == 'ENTER': color = COLOR_ACCENT
            
            pygame.draw.rect(screen, color, rect, border_radius=8)
            label = self.font.render(char, True, COLOR_WHITE)
            screen.blit(label, (rect.centerx - label.get_width()//2, rect.centery - label.get_height()//2))
