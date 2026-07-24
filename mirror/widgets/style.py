"""Shared styling helpers matching the web dashboard mirror view."""

COLOR_BG = "#000000"
COLOR_PANEL = "#0a0a0a"
COLOR_LINE = "#1c1c1c"
COLOR_TEXT_HI = "#ffffff"
COLOR_TEXT_MID = "#d0d0d0"
COLOR_TEXT_LOW = "#8f8f8f"

COLOR_URGENT = "#ff4d4d"
COLOR_WARN = "#ffb020"
COLOR_OK = "#35d07f"
COLOR_NOW = "#4fc3ff"

FONT_DISPLAY = "Segoe UI"
FONT_MONO = "Consolas"

COLOR_WHITE = (255, 255, 255)
COLOR_TEXT = (208, 208, 208)
COLOR_TEXT_DIM = (143, 143, 143)
COLOR_TEXT_MUTED = (80, 80, 80)
COLOR_CYAN = (79, 195, 255)
COLOR_CYAN_BORDER = (79, 195, 255)
COLOR_BLUE_LOC = (147, 197, 253)
COLOR_GLASS_BORDER = (28, 28, 28)


def widget_scale(w, h, ref_w=220, ref_h=160):
    scale_w = w / ref_w
    scale_h = h / ref_h
    return max(0.5, min(2.5, min(scale_w, scale_h) * 0.9))


def font_size(base_px, w, h, ref_w=220, ref_h=160):
    return max(8, int(base_px * widget_scale(w, h, ref_w, ref_h)))

