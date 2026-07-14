# mirror/smart_mirror_pro.py
import sys
import os
import json
import time
import math
import threading
import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QVBoxLayout, QHBoxLayout, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap, QRadialGradient, QColor, QPainter, QFont, QImage, QFontDatabase

from config import *
from widgets.notices_widget import NoticesWidget
from widgets.timetable_widget import TimetableWidget
from widgets.clock_widget import ClockWidget
from widgets.kings_week_widget import KingsWeekWidget

API_URL = os.environ.get('API_URL', 'https://api.smartmirror.me')
REF_WIDTH  = 1280
REF_HEIGHT = 800
HANKEN_FONT = 'Hanken Grotesk'

# ─────────────────────────────────────────────────────────────────────────────
# Animated background canvas
# ─────────────────────────────────────────────────────────────────────────────
class BackgroundCanvas(QWidget):
    """Full-screen background painted with animated radial gradient orbs."""

    _ORBS = [
        (0.20, 0.50, 0.55, 109,  40, 217, 31),   # purple
        (0.80, 0.30, 0.50,  56, 189, 248, 23),   # sky-blue
    ]
    _DRIFT_PERIOD = 18.0
    _DRIFT_AMP    = 0.03

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.glow_enabled = True
        self._t0 = time.time()

        self._redraw_timer = QTimer(self)
        self._redraw_timer.timeout.connect(self.update)
        self._redraw_timer.start(33)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        painter.fillRect(self.rect(), QColor(5, 5, 8))

        if not self.glow_enabled:
            painter.end()
            return

        t      = time.time() - self._t0
        phases = [0.0, math.pi * 0.6]

        for i, (bcx, bcy, r_pct, r, g, b, max_a) in enumerate(self._ORBS):
            phase = phases[i]
            cx = (bcx + self._DRIFT_AMP * math.sin(2 * math.pi * t / self._DRIFT_PERIOD + phase)) * w
            cy = (bcy + self._DRIFT_AMP * math.cos(2 * math.pi * t / self._DRIFT_PERIOD + phase * 1.3)) * h
            radius = r_pct * max(w, h)

            grad = QRadialGradient(cx, cy, radius)
            grad.setColorAt(0.0, QColor(r, g, b, max_a))
            grad.setColorAt(1.0, QColor(r, g, b, 0))

            painter.setBrush(grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(
                int(cx - radius), int(cy - radius),
                int(radius * 2),  int(radius * 2),
            )

        painter.end()


# ─────────────────────────────────────────────────────────────────────────────
# Main smart mirror window  — fixed layout matching the sketch
# ─────────────────────────────────────────────────────────────────────────────
class SmartMirrorPro(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Mirror")
        self.setStyleSheet("background-color: #050508;")

        # ── Load Hanken Grotesk if available ──────────────────────────────
        hk_id = QFontDatabase.addApplicationFont(
            os.path.join(os.path.dirname(__file__), 'assets', 'HankenGrotesk.ttf')
        )
        if hk_id >= 0:
            families = QFontDatabase.applicationFontFamilies(hk_id)
            if families:
                QApplication.instance().setFont(QFont(families[0], 12))

        # ── Central widget ────────────────────────────────────────────────
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)

        # ── Animated background ───────────────────────────────────────────
        self.bg_canvas = BackgroundCanvas(self.central_widget)
        self.bg_canvas.lower()

        # ── Important-message banner (full width, top) ────────────────────
        self._build_banner()

        # ── User layout (fixed 3-column deck) ────────────────────────────
        self._build_user_layout()

        # ── Guest screen (clock + notices + onboarding) ───────────────────
        self._build_guest_layout()

        # ── Status dot ───────────────────────────────────────────────────
        self.status_dot = QLabel(self.central_widget)
        self.status_dot.setFixedSize(10, 10)
        self.status_dot.setStyleSheet("background: transparent; border-radius: 5px;")
        self.status_dot.hide()

        # ── State tracking ────────────────────────────────────────────────
        self.current_user_id   = None
        self.current_user_name = ""
        self.face_detected     = False
        self.face_recognized   = False
        self.face_confidence   = 0.0
        self.in_grace          = False
        self._last_state       = None
        self._last_user_id     = None
        self.last_gesture_timestamp = 0.0
        self._transitioning    = False   # guard: ignore polls during fade
        self._anim_in          = None    # keep refs alive to prevent GC
        self._anim_out         = None

        # ── Timers ────────────────────────────────────────────────────────
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._update_inputs)
        self.poll_timer.start(200)

        self.gesture_timer = QTimer(self)
        self.gesture_timer.timeout.connect(self._poll_gestures)
        self.gesture_timer.start(100)

        self.banner_timer = QTimer(self)
        self.banner_timer.timeout.connect(self._poll_banner)
        self.banner_timer.start(30000)
        self._poll_banner()

        # ── Window mode ───────────────────────────────────────────────────
        if os.environ.get('MIRROR_WINDOWED') == '1':
            self.resize(REF_WIDTH, REF_HEIGHT)
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.showFullScreen()
            self.setCursor(Qt.CursorShape.BlankCursor)

    # ─────────────────────────────────────────────────────────────────────
    # Build: banner
    # ─────────────────────────────────────────────────────────────────────
    def _build_banner(self):
        self.banner_frame = QFrame(self.central_widget)
        self.banner_frame.setObjectName("BannerFrame")
        self.banner_frame.setStyleSheet("""
            #BannerFrame {
                background-color: rgba(153, 27, 27, 0.95);
                border: none;
                border-radius: 12px;
            }
        """)
        self.banner_frame.setFixedHeight(68)
        self.banner_frame.hide()

        lay = QHBoxLayout(self.banner_frame)
        lay.setContentsMargins(18, 10, 18, 10)
        lay.setSpacing(14)

        self.warn_icon = QLabel("⚠", self.banner_frame)
        self.warn_icon.setStyleSheet(
            f'font-family: "{HANKEN_FONT}"; font-size: 20px; '
            'background: transparent; border: none; color: #fca5a5;'
        )
        self.warn_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.warn_icon)

        text_container = QWidget(self.banner_frame)
        text_container.setStyleSheet("background: transparent; border: none;")
        text_lay = QVBoxLayout(text_container)
        text_lay.setContentsMargins(0, 0, 0, 0)
        text_lay.setSpacing(3)

        self.banner_title = QLabel("IMPORTANT MESSAGE / NOTICE", text_container)
        self.banner_title.setStyleSheet(
            f'font-family: "{HANKEN_FONT}"; color: #fca5a5; '
            'font-size: 11px; font-weight: 700; letter-spacing: 1.5px;'
        )
        text_lay.addWidget(self.banner_title)

        self.banner_label = QLabel(text_container)
        self.banner_label.setStyleSheet(
            f'font-family: "{HANKEN_FONT}"; color: #ffffff; '
            'font-size: 13px; font-weight: 500;'
        )
        text_lay.addWidget(self.banner_label)

        lay.addWidget(text_container, 1)

    # ─────────────────────────────────────────────────────────────────────
    # Build: user layout (floating glassmorphic cards)
    # ─────────────────────────────────────────────────────────────────────
    def _build_user_layout(self):
        self.user_container = QWidget(self.central_widget)
        self.user_container.setStyleSheet("background: transparent;")

        # ── Left column: Notices ──────────────────────────────────────────
        self.notices_widget = NoticesWidget(
            api_url=API_URL, parent=self.user_container
        )

        # ── Center column: Clock (top) + Kings Week (bottom) ─────────────
        self.clock_widget = ClockWidget(parent=self.user_container)

        self.kings_week_widget = KingsWeekWidget(self.user_container)

        # ── Right column: Timetable ───────────────────────────────────────
        self.timetable_widget = TimetableWidget(
            api_url=API_URL, parent=self.user_container
        )

        self.user_container.hide()

    def _apply_user_layout(self, w, h):
        """Position all user layout elements given the window size."""
        banner_h = self.banner_frame.height() + 16 if not self.banner_frame.isHidden() else 0
        margin   = 16
        top      = banner_h + margin

        self.user_container.setGeometry(0, 0, w, h)

        # 3 columns — side panels 27% each, center fills the rest
        col_w    = int((w - margin * 4) * 0.27)
        center_w = w - col_w * 2 - margin * 4

        # Notices (left column)
        self.notices_widget.setGeometry(margin, top, col_w, h - top - margin)

        # Clock (center top) — taller so Kings Week gets ample image space
        clock_h = int(h * 0.22)
        self.clock_widget.setGeometry(margin * 2 + col_w, top, center_w, clock_h)

        # Kings Week (center bottom)
        kw_y = top + clock_h + margin
        self.kings_week_widget.setGeometry(
            margin * 2 + col_w, kw_y, center_w, h - kw_y - margin
        )

        # Timetable (right column)
        self.timetable_widget.setGeometry(w - margin - col_w, top, col_w, h - top - margin)

    # ─────────────────────────────────────────────────────────────────────
    # Build: guest layout (clock + notices + prompt)
    # ─────────────────────────────────────────────────────────────────────
    def _build_guest_layout(self):
        """
        Guest layout (sketch design):
        ─────────────────────────────────────────────────────
        │  [IMPORTANT MESSAGE / NOTICE banner — full width] │
        ├─────────────────┬───────────────────────────────── │
        │  Notices        │     12:00  2/07/2026            │
        │  (left column)  │     (centered clock)            │
        ├─────────────────┴───────────────────────────────── │
        │  STAND IN FRONT OF THE MIRROR  (hint strip)       │
        ─────────────────────────────────────────────────────
        """
        self.guest_container = QWidget(self.central_widget)
        self.guest_container.setStyleSheet("background: transparent;")

        outer = QVBoxLayout(self.guest_container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Content row: notices left, clock right ────────────────────────
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)

        # Left: notices panel (no extra background — uses widget's own style)
        self.guest_notices = NoticesWidget(api_url=API_URL)
        content_row.addWidget(self.guest_notices, 1)

        # Center/Right: clock
        self.guest_clock = ClockWidget()
        content_row.addWidget(self.guest_clock, 2)

        outer.addLayout(content_row, 1)

        # ── Bottom hint strip ─────────────────────────────────────────────
        hint = QFrame()
        hint.setObjectName('GuestHint')
        hint.setStyleSheet("""
            #GuestHint {
                background: rgba(96, 165, 250, 0.08);
                border: 1px solid rgba(96, 165, 250, 0.18);
                border-radius: 0px;
            }
        """)
        hint.setFixedHeight(52)
        h_lay = QHBoxLayout(hint)
        h_lay.setContentsMargins(24, 0, 24, 0)

        hint_icon = QLabel('◎')
        hint_icon.setStyleSheet(
            f'font-family: "{HANKEN_FONT}"; font-size: 16px; '
            'color: #60a5fa; background: transparent; border: none;'
        )
        h_lay.addWidget(hint_icon)

        title = QLabel('STAND IN FRONT OF THE MIRROR TO IDENTIFY YOURSELF')
        title.setStyleSheet(
            f'font-family: "{HANKEN_FONT}"; font-size: 12px; font-weight: 700; '
            'color: #60a5fa; letter-spacing: 2px; background: transparent; border: none;'
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_lay.addWidget(title, 1)

        outer.addWidget(hint)
        self.guest_container.hide()

    # ─────────────────────────────────────────────────────────────────────
    # Resize
    # ─────────────────────────────────────────────────────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()

        if hasattr(self, 'bg_canvas'):
            self.bg_canvas.setGeometry(0, 0, w, h)

        if hasattr(self, 'banner_frame'):
            self.banner_frame.setGeometry(16, 16, w - 32, self.banner_frame.height())

        if hasattr(self, 'guest_container') and not self.guest_container.isHidden():
            banner_h = self.banner_frame.height() + 16 if not self.banner_frame.isHidden() else 0
            self.guest_container.setGeometry(0, banner_h, w, h - banner_h)
        elif hasattr(self, 'guest_container'):
            self.guest_container.setGeometry(0, 0, w, h)

        if hasattr(self, 'user_container') and not self.user_container.isHidden():
            self._apply_user_layout(w, h)

        if hasattr(self, 'status_dot'):
            self.status_dot.move(w - 20, h - 20)

    # ─────────────────────────────────────────────────────────────────────
    # Banner polling
    # ─────────────────────────────────────────────────────────────────────
    def _poll_banner(self):
        def worker():
            try:
                res = requests.get(f"{API_URL}/api/banner", timeout=4)
                if res.status_code == 200:
                    msg = res.json().get("message", "")
                    QTimer.singleShot(0, lambda: self._update_banner(msg))
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _update_banner(self, message):
        if message:
            self.banner_label.setText(message)
            self.banner_frame.show()
            self.banner_frame.raise_()
        else:
            self.banner_frame.hide()
        # Re-apply layout in case banner height changed
        if not self.user_container.isHidden():
            self._apply_user_layout(self.width(), self.height())

    # ─────────────────────────────────────────────────────────────────────
    # Gesture polling
    # ─────────────────────────────────────────────────────────────────────
    def _poll_gestures(self):
        gesture_file = os.path.join(
            os.environ.get("TEMP", os.environ.get("TMP", "/tmp")),
            "gesture_status.json"
        )
        if not os.path.exists(gesture_file):
            return
        try:
            with open(gesture_file) as f:
                data = json.load(f)
            t = data.get("timestamp", 0.0)
            if t > self.last_gesture_timestamp:
                self.last_gesture_timestamp = t
                self._handle_gesture(data.get("gesture"), data.get("scroll_delta", 0))
        except Exception:
            pass

    def _handle_gesture(self, gesture, scroll_delta):
        if self._last_state == 'idle' or not gesture:
            return

        if gesture == "scroll" and scroll_delta != 0:
            if self._last_state == 'user':
                self.notices_widget.scroll_by_pixels(scroll_delta)
                self.timetable_widget.scroll_by_pixels(scroll_delta)
            elif self._last_state == 'guest':
                self.guest_notices.scroll_by_pixels(scroll_delta)

    # ─────────────────────────────────────────────────────────────────────
    # Fade helpers
    # ─────────────────────────────────────────────────────────────────────
    def _fade_in(self, widget, duration=380):
        """Show widget and animate opacity 0 → 1."""
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        widget.show()
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: self._on_fade_in_done(widget))
        anim.start()
        self._anim_in = anim

    def _on_fade_in_done(self, widget):
        # Remove effect so child painting isn't affected by opacity layer
        widget.setGraphicsEffect(None)
        self._transitioning = False

    def _fade_out(self, widget, on_done, duration=280):
        """Animate opacity 1 → 0 then call on_done()."""
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        effect.setOpacity(1.0)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(duration)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(on_done)
        anim.start()
        self._anim_out = anim

    # ─────────────────────────────────────────────────────────────────────
    # Theme application
    # ─────────────────────────────────────────────────────────────────────
    def _apply_user_theme(self, remote_config):
        theme  = remote_config.get("theme", {})
        colors = theme.get("colors", {})
        fonts  = theme.get("fonts", {})
        primary     = colors.get("primary", "#3b82f6")
        secondary   = colors.get("secondary", "#10b981")
        font_family = fonts.get("family", "Outfit")

        for widget in [self.notices_widget, self.clock_widget, self.timetable_widget]:
            if hasattr(widget, 'apply_theme'):
                widget.apply_theme(primary, secondary, font_family)

        if self.current_user_id:
            self.timetable_widget.user_id = self.current_user_id

    # ─────────────────────────────────────────────────────────────────────
    # Face-data polling → show/hide containers
    # ─────────────────────────────────────────────────────────────────────
    def _update_inputs(self):
        if os.path.exists(FACE_DATA_FILE):
            try:
                with open(FACE_DATA_FILE) as f:
                    fdata = json.load(f)

                self.face_detected   = fdata.get('detected', False)
                self.face_recognized = fdata.get('recognized', False)
                self.face_confidence = fdata.get('confidence', 0.0)
                self.in_grace        = fdata.get('in_grace', False)

                new_state   = fdata.get('state', 'idle')
                new_user_id = fdata.get('user_id', 'idle')

                state_changed = (new_state != self._last_state)
                user_switched = (
                    new_state == 'user'
                    and new_user_id != self._last_user_id
                    and new_user_id not in ('', 'idle')
                )

                if (state_changed or user_switched) and not self._transitioning:
                    self._transitioning = True
                    self._last_state    = new_state
                    self._last_user_id  = new_user_id
                    self.current_user_id   = new_user_id
                    self.current_user_name = fdata.get('user_name', '')
                    self._trigger_transition(new_state, new_user_id, fdata)

            except Exception:
                pass

        # Status dot
        if self.face_recognized:
            self.status_dot.setStyleSheet("background: #00c850; border-radius: 5px;")
            self.status_dot.show()
        elif self.in_grace:
            self.status_dot.setStyleSheet("background: #ff9600; border-radius: 5px;")
            self.status_dot.show()
        else:
            self.status_dot.hide()

    def _trigger_transition(self, new_state, new_user_id, fdata):
        """Fade out whatever is currently visible, then apply + fade in new state."""
        # Find the currently visible container (if any)
        visible = None
        if not self.user_container.isHidden():
            visible = self.user_container
        elif not self.guest_container.isHidden():
            visible = self.guest_container

        def apply_new():
            # Hide everything first
            self.user_container.hide()
            self.guest_container.hide()
            if visible:
                visible.setGraphicsEffect(None)

            if new_state == 'user' and new_user_id not in ('', 'idle'):
                self.bg_canvas.glow_enabled = True
                self.timetable_widget.set_user_id(new_user_id)
                self._apply_user_theme(fdata.get('config', {}))
                self._apply_user_layout(self.width(), self.height())
                self._fade_in(self.user_container)

            elif new_state == 'guest':
                self.bg_canvas.glow_enabled = True
                self.timetable_widget.set_user_id('')
                self._fade_in(self.guest_container)

            else:  # idle
                self.bg_canvas.glow_enabled = False
                self._transitioning = False   # nothing to fade in

        if visible:
            self._fade_out(visible, on_done=apply_new)
        else:
            apply_new()

    def keyPressEvent(self, event):
        pass


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app = QApplication(sys.argv)
    mirror = SmartMirrorPro()
    mirror.show()
    sys.exit(app.exec())
