# utils/fonts.py
import pygame

def get_font(size, bold=False):
    fonts = ['roboto', 'segoeui', 'arial', 'dejavusans']
    font_name = pygame.font.match_font(','.join(fonts), bold=bold)
    if font_name:
        return pygame.font.Font(font_name, size)
    return pygame.font.SysFont(None, size, bold=bold)
