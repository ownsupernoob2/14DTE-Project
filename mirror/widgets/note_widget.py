import pygame
from .base_widget import Widget
from utils.fonts import get_font

COLOR_BG = (20, 20, 30)
COLOR_GLASS = (255, 255, 255, 18)
COLOR_BORDER = (255, 255, 255, 40)
COLOR_WHITE = (255, 255, 255)
COLOR_MUTED = (160, 160, 180)
COLOR_ACCENT = (99, 102, 241)


class NoteWidget(Widget):
    def __init__(self, x, y, w, h, data=''):
        super().__init__(x, y, w, h)
        self.data = data or ''
        self.font_title = get_font(13, bold=True)
        self.font_body = get_font(14)

    def update(self, scroll_y=0):
        pass

    def draw(self, surface, font_title, font_content, scroll_y=0):
        rx = self.rect.x
        ry = self.rect.y - scroll_y
        rw = self.rect.w
        rh = self.rect.h

        # Glass background panel
        glass = pygame.Surface((rw, rh), pygame.SRCALPHA)
        glass.fill((20, 20, 35, 210))
        surface.blit(glass, (rx, ry))

        # Border
        pygame.draw.rect(surface, (255, 255, 255, 40), (rx, ry, rw, rh), 1, border_radius=12)

        # Header bar
        header_h = 28
        header_surf = pygame.Surface((rw, header_h), pygame.SRCALPHA)
        header_surf.fill((99, 102, 241, 60))
        surface.blit(header_surf, (rx, ry))
        label = self.font_title.render('Note', True, (200, 200, 220))
        surface.blit(label, (rx + 12, ry + (header_h - label.get_height()) // 2))

        # Note body text with wrapping
        pad = 12
        text_x = rx + pad
        text_y = ry + header_h + pad
        max_w = rw - pad * 2
        max_y = ry + rh - pad

        text = self.data if self.data else 'No note set.'
        words = text.split()
        line = ''
        for word in words:
            test_line = line + (' ' if line else '') + word
            if self.font_body.size(test_line)[0] > max_w:
                if text_y + self.font_body.get_height() > max_y:
                    break
                rendered = self.font_body.render(line, True, COLOR_WHITE)
                surface.blit(rendered, (text_x, text_y))
                text_y += self.font_body.get_height() + 3
                line = word
            else:
                line = test_line
        if line and text_y + self.font_body.get_height() <= max_y:
            rendered = self.font_body.render(line, True, COLOR_WHITE)
            surface.blit(rendered, (text_x, text_y))
