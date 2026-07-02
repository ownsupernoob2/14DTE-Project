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
from PyQt6.QtGui import QPixmap, QRadialGradient, QColor, QPainter, QFont, QImage

from config import *
from widgets.notices_widget import NoticesWidget
from widgets.timetable_widget import TimetableWidget
from widgets.clock_widget import ClockWidget
from widgets.kings_week_widget import KingsWeekWidget

API_URL = os.environ.get('API_URL', 'https://api.smartmirror.me')
REF_WIDTH  = 1280
REF_HEIGHT = 800

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
                background-color: rgba(239, 68, 68, 0.18);
                border-bottom: 1px solid rgba(239, 68, 68, 0.35);
            }
        """)
        self.banner_frame.setFixedHeight(44)
        self.banner_frame.hide()

        lay = QHBoxLayout(self.banner_frame)
        lay.setContentsMargins(24, 0, 24, 0)

        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet("background: #ef4444; border-radius: 4px;")
        lay.addWidget(dot)

        self.banner_label = QLabel()
        self.banner_label.setStyleSheet(
            "color: #fecaca; font-size: 14px; font-weight: 600; letter-spacing: 1px;"
        )
        self.banner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.banner_label, 1)

    # ─────────────────────────────────────────────────────────────────────
    # Build: user layout (fixed 3-column glass deck)
    # ─────────────────────────────────────────────────────────────────────
    def _build_user_layout(self):
        self.user_container = QWidget(self.central_widget)
        self.user_container.setStyleSheet("background: transparent;")

        # Master glass card
        self.deck = QFrame(self.user_container)
        self.deck.setObjectName("Deck")
        self.deck.setStyleSheet("""
            #Deck {
                background-color: rgba(12, 12, 20, 140);
                border: 1px solid rgba(255, 255, 255, 18);
                border-radius: 20px;
            }
        """)

        # ── Left column: Notices ──────────────────────────────────────────
        self.notices_widget = NoticesWidget(0, 0, 100, 100, API_URL)
        self.notices_widget.setParent(self.deck)

        self.left_vdiv = QFrame(self.deck)
        self.left_vdiv.setFrameShape(QFrame.Shape.VLine)
        self.left_vdiv.setStyleSheet("background: rgba(255,255,255,18); border: none;")

        # ── Center column: Clock (top) + Kings Week (bottom) ─────────────
        self.clock_widget = ClockWidget(0, 0, 100, 100)
        self.clock_widget.setParent(self.deck)

        self.center_hdiv = QFrame(self.deck)
        self.center_hdiv.setFrameShape(QFrame.Shape.HLine)
        self.center_hdiv.setStyleSheet("background: rgba(255,255,255,18); border: none;")

        self.kings_week_widget = KingsWeekWidget(self.deck)

        # ── Right column: Timetable ───────────────────────────────────────
        self.right_vdiv = QFrame(self.deck)
        self.right_vdiv.setFrameShape(QFrame.Shape.VLine)
        self.right_vdiv.setStyleSheet("background: rgba(255,255,255,18); border: none;")

        self.timetable_widget = TimetableWidget(0, 0, 100, 100, "", API_URL)
        self.timetable_widget.setParent(self.deck)

        self.user_container.hide()

    def _apply_user_layout(self, w, h):
        """Position all user layout elements given the window size."""
        banner_h   = self.banner_frame.height() if not self.banner_frame.isHidden() else 0
        margin     = 16
        top        = banner_h + margin

        deck_x = margin
        deck_y = top
        deck_w = w - margin * 2
        deck_h = h - top - margin

        self.user_container.setGeometry(0, 0, w, h)
        self.deck.setGeometry(deck_x, deck_y, deck_w, deck_h)

        col_w    = int(deck_w * 0.25)
        center_w = deck_w - col_w * 2
        clock_h  = int(deck_h * 0.52)

        # Left notices
        self.notices_widget.setGeometry(0, 0, col_w, deck_h)
        self.left_vdiv.setGeometry(col_w, 0, 1, deck_h)

        # Center clock
        self.clock_widget.setGeometry(col_w + 1, 0, center_w - 2, clock_h)
        self.center_hdiv.setGeometry(col_w + 1, clock_h, center_w - 2, 1)

        # Center kings week
        kw_pad = 12
        self.kings_week_widget.setGeometry(
            col_w + 1 + kw_pad,
            clock_h + 1 + kw_pad,
            center_w - 2 - kw_pad * 2,
            deck_h - clock_h - 1 - kw_pad * 2,
        )

        # Right timetable
        self.right_vdiv.setGeometry(col_w + center_w - 1, 0, 1, deck_h)
        self.timetable_widget.setGeometry(col_w + center_w, 0, col_w, deck_h)

    # ─────────────────────────────────────────────────────────────────────
    # Build: guest layout (clock + notices + prompt)
    # ─────────────────────────────────────────────────────────────────────
    def _build_guest_layout(self):
        self.guest_container = QWidget(self.central_widget)
        self.guest_container.setStyleSheet("background: transparent;")

        outer = QVBoxLayout(self.guest_container)
        outer.setContentsMargins(40, 60, 40, 40)
        outer.setSpacing(20)

        top_row = QHBoxLayout()
        top_row.setSpacing(20)

        self.guest_clock   = ClockWidget(0, 0, 300, 150)
        self.guest_notices = NoticesWidget(0, 0, 500, 300, API_URL)
        top_row.addWidget(self.guest_clock, 1)
        top_row.addWidget(self.guest_notices, 2)
        outer.addLayout(top_row, 3)

        hint = QFrame()
        hint.setStyleSheet(
            "background: rgba(255,255,255,5); border: 1px solid rgba(255,255,255,10); border-radius: 14px;"
        )
        h_lay = QVBoxLayout(hint)
        h_lay.setContentsMargins(20, 16, 20, 16)

        title = QLabel("STAND IN FRONT OF THE MIRROR TO IDENTIFY YOURSELF")
        title.setStyleSheet("font-size: 12px; font-weight: bold; color: #60a5fa; letter-spacing: 2px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_lay.addWidget(title)

        outer.addWidget(hint, 1)
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
            self.banner_frame.setGeometry(0, 0, w, self.banner_frame.height())

        if hasattr(self, 'guest_container'):
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

                if state_changed or user_switched:
                    self._last_state   = new_state
                    self._last_user_id = new_user_id
                    self.current_user_id   = new_user_id
                    self.current_user_name = fdata.get('user_name', '')

                    if new_state == 'user' and new_user_id not in ('', 'idle'):
                        self.bg_canvas.glow_enabled = True
                        self.guest_container.hide()
                        self._apply_user_theme(fdata.get('config', {}))
                        self.user_container.show()
                        self._apply_user_layout(self.width(), self.height())

                    elif new_state == 'guest':
                        self.bg_canvas.glow_enabled = True
                        self.user_container.hide()
                        self.guest_container.show()

                    else:  # idle
                        self.bg_canvas.glow_enabled = False
                        self.user_container.hide()
                        self.guest_container.hide()

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

    def keyPressEvent(self, event):
        pass


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app = QApplication(sys.argv)
    mirror = SmartMirrorPro()
    mirror.show()
    sys.exit(app.exec())
