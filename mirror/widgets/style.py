"""Shared styling helpers matching the web dashboard mirror view."""

COLOR_WHITE = (255, 255, 255)
COLOR_TEXT = (230, 230, 230)
COLOR_TEXT_DIM = (180, 180, 180)
COLOR_TEXT_MUTED = (102, 102, 102)
COLOR_CYAN = (34, 211, 238)
COLOR_CYAN_BORDER = (6, 182, 212)
COLOR_BLUE_LOC = (147, 197, 253)
COLOR_GLASS_BORDER = (255, 255, 255, 18)


def widget_scale(w, h, ref_w=220, ref_h=160):
    scale_w = w / ref_w
    scale_h = h / ref_h
    return max(0.5, min(2.5, min(scale_w, scale_h) * 0.9))


def font_size(base_px, w, h, ref_w=220, ref_h=160):
    return max(8, int(base_px * widget_scale(w, h, ref_w, ref_h)))
