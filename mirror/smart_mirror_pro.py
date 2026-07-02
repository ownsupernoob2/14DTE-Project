# mirror/smart_mirror_pro.py
import sys
import os
import json
import time
import math
import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QVBoxLayout, QHBoxLayout, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap, QRadialGradient, QColor, QPainter, QFont

from config import *
from widgets import (
    ClockWidget, WeatherWidget, NoticesWidget, TimetableWidget, NoteWidget
)
from widgets.kings_week_widget import KingsWeekWidget

API_URL = os.environ.get('API_URL', 'https://api.smartmirror.me')
REF_WIDTH = 1280
REF_HEIGHT = 800

class BackgroundCanvas(QWidget):
    """Full-screen background widget painted with QPainter radial gradients."""

    _ORBS = [
        (0.20, 0.50, 0.55, 109,  40, 217, 31),   # purple
        (0.80, 0.30, 0.50,  56, 189, 248, 23),   # sky-blue
    ]
    _DRIFT_PERIOD = 18.0   # seconds for one full drift cycle
    _DRIFT_AMP    = 0.03   # fraction of screen dimension

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

        if not self.glow_enabled:
            painter.fillRect(self.rect(), QColor(0, 0, 0))
            painter.end()
            return

        w = self.width()
        h = self.height()
        painter.fillRect(self.rect(), QColor(10, 10, 12))

        t = time.time() - self._t0
        phases = [0.0, math.pi * 0.6]

        for i, (bcx, bcy, r_pct, r, g, b, max_a) in enumerate(self._ORBS):
            phase = phases[i]
            cx = (bcx + self._DRIFT_AMP * math.sin(2 * math.pi * t / self._DRIFT_PERIOD + phase)) * w
            cy = (bcy + self._DRIFT_AMP * math.cos(2 * math.pi * t / self._DRIFT_PERIOD + phase * 1.3)) * h
            radius = r_pct * max(w, h)

            grad = QRadialGradient(cx, cy, radius)
            inner = QColor(r, g, b, max_a)
            outer  = QColor(r, g, b, 0)
            grad.setColorAt(0.0, inner)
            grad.setColorAt(1.0, outer)

            painter.setBrush(grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(
                int(cx - radius), int(cy - radius),
                int(radius * 2),  int(radius * 2),
            )

        painter.end()


class SmartMirrorPro(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Mirror Pro")
        self.setStyleSheet("background-color: #000000;")

        # Central Widget & Main absolute layout
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)

        # Animated background
        self.bg_canvas = BackgroundCanvas(self.central_widget)
        self.bg_canvas.setGeometry(self.central_widget.rect())
        self.bg_canvas.lower()

        # Container for User widgets (Fixed layout)
        self.user_container = QWidget(self.central_widget)
        self.user_container.setGeometry(self.rect())
        self.user_container.setStyleSheet("background: transparent;")
        self.setup_user_layout()
        self.user_container.hide()

        # Container for Guest screen
        self.guest_container = QFrame(self.central_widget)
        self.guest_container.setGeometry(self.rect())
        self.guest_container.setStyleSheet("background: transparent;")
        self.guest_container.hide()
        self.setup_guest_layout()

        # Timetable Promo screen for Guest
        self.setup_guest_promo_layout()

        # Status Dot
        self.status_dot = QLabel(self.central_widget)
        self.status_dot.setFixedSize(10, 10)
        self.status_dot.setStyleSheet("background-color: transparent; border-radius: 5px;")
        self.status_dot.hide()

        # Admin Banner overlay
        self.setup_admin_banner()

        # State tracking
        self.current_user_id = None
        self.current_user_name = ""
        self.face_detected = False
        self.face_recognized = False
        self.face_confidence = 0.0
        self.in_grace = False
        self._last_state = None
        self._last_user_id = None
        self.last_gesture_timestamp = 0.0

        # Polling Timers
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.update_inputs)
        self.poll_timer.start(200)

        # Gesture status polling timer
        self.gesture_timer = QTimer(self)
        self.gesture_timer.timeout.connect(self.poll_gestures)
        self.gesture_timer.start(100)

        # Admin banner polling timer
        self.banner_timer = QTimer(self)
        self.banner_timer.timeout.connect(self.poll_admin_banner)
        self.banner_timer.start(10000)
        self.poll_admin_banner()

        # Window state
        windowed = os.environ.get('MIRROR_WINDOWED') == '1'
        if windowed:
            self.resize(1280, 800)
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.showFullScreen()
            self.setCursor(Qt.CursorShape.BlankCursor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        if hasattr(self, 'bg_canvas') and self.bg_canvas:
            self.bg_canvas.setGeometry(0, 0, w, h)
        if hasattr(self, 'user_container') and self.user_container:
            self.user_container.setGeometry(0, 0, w, h)
            self.update_user_layout_geometry(w, h)
        if hasattr(self, 'guest_container') and self.guest_container:
            self.guest_container.setGeometry(0, 0, w, h)
        if hasattr(self, 'guest_promo_container') and self.guest_promo_container:
            self.guest_promo_container.setGeometry(0, 0, w, h)
        if hasattr(self, 'status_dot') and self.status_dot:
            self.status_dot.move(w - 20, 20)
        if hasattr(self, 'banner_frame') and self.banner_frame:
            self.banner_frame.setGeometry(0, 0, w, 40)

    def setup_user_layout(self):
        # Master unified glass card
        self.master_glass_frame = QFrame(self.user_container)
        self.master_glass_frame.setObjectName("MasterGlassFrame")
        self.master_glass_frame.setStyleSheet("""
            #MasterGlassFrame {
                background-color: rgba(15, 15, 25, 140);
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 24px;
            }
        """)

        # Dividers inside master glass
        self.left_divider = QFrame(self.master_glass_frame)
        self.left_divider.setFrameShape(QFrame.Shape.VLine)
        self.left_divider.setStyleSheet("background-color: rgba(255, 255, 255, 20); border: none; min-width: 1px; max-width: 1px;")

        self.right_divider = QFrame(self.master_glass_frame)
        self.right_divider.setFrameShape(QFrame.Shape.VLine)
        self.right_divider.setStyleSheet("background-color: rgba(255, 255, 255, 20); border: none; min-width: 1px; max-width: 1px;")

        self.center_horizontal_divider = QFrame(self.master_glass_frame)
        self.center_horizontal_divider.setFrameShape(QFrame.Shape.HLine)
        self.center_horizontal_divider.setStyleSheet("background-color: rgba(255, 255, 255, 20); border: none; min-height: 1px; max-height: 1px;")

        # User widgets - all set to the master glass container as parent!
        self.user_notices = NoticesWidget(0, 0, 100, 100, API_URL)
        self.user_notices.setParent(self.master_glass_frame)
        self.user_notices.set_orientation("vertical")
        
        self.user_clock = ClockWidget(0, 0, 100, 100)
        self.user_clock.setParent(self.master_glass_frame)
        
        self.user_kingsweek = KingsWeekWidget(self.master_glass_frame)
        
        self.user_timetable = TimetableWidget(0, 0, 100, 100, "", API_URL)
        self.user_timetable.setParent(self.master_glass_frame)
        self.user_timetable.set_orientation("vertical")

        self.user_widgets = [self.user_notices, self.user_clock, self.user_kingsweek, self.user_timetable]

        # Explicitly show them
        self.master_glass_frame.show()
        self.left_divider.show()
        self.right_divider.show()
        self.center_horizontal_divider.show()
        for w in self.user_widgets:
            w.show()

    def update_user_layout_geometry(self, w, h):
        # 24px padding around screen, and top offset for banner
        margin = 24
        top_offset = 64
        
        deck_w = w - margin * 2
        deck_h = h - top_offset - margin

        self.master_glass_frame.setGeometry(margin, top_offset, deck_w, deck_h)

        # Columns inside the master glass frame (0 margin between columns)
        col_w = int(deck_w * 0.26)
        center_w = deck_w - col_w * 2

        # Left Column: Notices
        self.user_notices.setGeometry(0, 0, col_w, deck_h)
        self.left_divider.setGeometry(col_w, 0, 1, deck_h)

        # Center Column: Clock & Kings Week
        clock_h = int(deck_h * 0.55)
        self.user_clock.setGeometry(col_w + 1, 0, center_w - 2, clock_h)
        self.center_horizontal_divider.setGeometry(col_w + 1, clock_h, center_w - 2, 1)
        
        kw_margin = 16
        self.user_kingsweek.setGeometry(
            col_w + 1 + kw_margin, 
            clock_h + kw_margin, 
            center_w - 2 - kw_margin * 2, 
            deck_h - clock_h - kw_margin * 2
        )

        # Right Column: Timetable
        self.right_divider.setGeometry(col_w + center_w - 1, 0, 1, deck_h)
        self.user_timetable.setGeometry(col_w + center_w, 0, col_w, deck_h)

    def setup_guest_layout(self):
        self.guest_layout = QVBoxLayout(self.guest_container)
        self.guest_layout.setContentsMargins(40, 60, 40, 40)
        self.guest_layout.setSpacing(20)

        top_row = QHBoxLayout()
        top_row.setSpacing(30)

        self.guest_clock = ClockWidget(0, 0, 300, 150)
        self.guest_notices = NoticesWidget(0, 0, 500, 300, API_URL)
        
        top_row.addWidget(self.guest_clock, 1)
        top_row.addWidget(self.guest_notices, 2)
        self.guest_layout.addLayout(top_row, 3)

        self.onboarding_card = QFrame(self.guest_container)
        self.onboarding_card.setStyleSheet("background-color: rgba(255, 255, 255, 6); border: 1px solid rgba(255, 255, 255, 12); border-radius: 16px;")
        ob_layout = QVBoxLayout(self.onboarding_card)
        ob_layout.setContentsMargins(20, 16, 20, 16)
        
        ob_title = QLabel("HOW TO INTERACT VIA HAND GESTURES")
        ob_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #60a5fa; letter-spacing: 2px;")
        ob_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ob_layout.addWidget(ob_title)

        self.guest_layout.addWidget(self.onboarding_card, 2)

    def setup_guest_promo_layout(self):
        self.guest_promo_container = QFrame(self.central_widget)
        self.guest_promo_container.setGeometry(self.rect())
        self.guest_promo_container.setStyleSheet("background-color: rgba(10, 10, 12, 235);")
        self.guest_promo_container.hide()

        promo_layout = QVBoxLayout(self.guest_promo_container)
        promo_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        promo_title = QLabel("Timetable Protected")
        promo_title.setStyleSheet("font-size: 36px; font-weight: bold; color: #ef4444;")
        promo_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        promo_layout.addWidget(promo_title)

    def setup_admin_banner(self):
        self.banner_frame = QFrame(self.central_widget)
        self.banner_frame.setStyleSheet("background-color: #ef4444; border-bottom: 2px solid #b91c1c;")
        self.banner_frame.setFixedHeight(40)
        self.banner_frame.hide()

        banner_layout = QHBoxLayout(self.banner_frame)
        banner_layout.setContentsMargins(20, 0, 20, 0)

        self.banner_label = QLabel(self.banner_frame)
        self.banner_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold; letter-spacing: 1px;")
        self.banner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        banner_layout.addWidget(self.banner_label)

    def show_guest_promo(self):
        self.guest_container.hide()
        self.guest_promo_container.show()

    def hide_guest_promo(self):
        self.guest_promo_container.hide()
        self.guest_container.show()

    def poll_admin_banner(self):
        def worker():
            try:
                res = requests.get(f"{API_URL}/api/banner", timeout=4)
                if res.status_code == 200:
                    msg = res.json().get("message", "")
                    QTimer.singleShot(0, lambda: self.update_admin_banner(msg))
            except Exception:
                pass
        import threading
        threading.Thread(target=worker, daemon=True).start()

    def update_admin_banner(self, message):
        if message:
            self.banner_label.setText(message)
            self.banner_frame.show()
            self.banner_frame.raise_()
        else:
            self.banner_frame.hide()

    def poll_gestures(self):
        gesture_file = os.path.join(os.environ.get("TEMP", os.environ.get("TMP", "/tmp")), "gesture_status.json")
        if os.path.exists(gesture_file):
            try:
                with open(gesture_file) as f:
                    data = json.load(f)
                
                t = data.get("timestamp", 0.0)
                if t > self.last_gesture_timestamp:
                    self.last_gesture_timestamp = t
                    gesture = data.get("gesture")
                    scroll_delta = data.get("scroll_delta", 0)
                    if gesture:
                        self.handle_gesture(gesture, scroll_delta)
            except Exception:
                pass

    def handle_gesture(self, gesture, scroll_delta):
        if self._last_state == 'idle': return

        if gesture in ("swipe_right", "ok_hold"):
            if self._last_state == 'guest':
                self.show_guest_promo()
            elif self._last_state == 'user':
                self.user_timetable.raise_()

        elif gesture in ("swipe_left", "peace_hold"):
            if self._last_state == 'guest':
                self.hide_guest_promo()
            elif self._last_state == 'user':
                self.user_notices.raise_()

        elif gesture == "scroll" and scroll_delta != 0:
            if self._last_state == 'user':
                self.user_notices.scroll_by_pixels(scroll_delta)
                self.user_timetable.scroll_by_pixels(scroll_delta)
            elif self._last_state == 'guest':
                self.guest_notices.scroll_by_pixels(scroll_delta)

    def apply_user_theme(self, remote_config):
        theme = remote_config.get("theme", {})
        colors = theme.get("colors", {})
        fonts = theme.get("fonts", {})
        primary = colors.get("primary", "#3b82f6")
        secondary = colors.get("secondary", "#10b981")
        font_family = fonts.get("family", "Outfit")

        for w in self.user_widgets:
            if hasattr(w, 'apply_theme'):
                w.apply_theme(primary, secondary, font_family)
                
        if self.current_user_id:
            self.user_timetable.user_id = self.current_user_id

    def update_inputs(self):
        if os.path.exists(FACE_DATA_FILE):
            try:
                with open(FACE_DATA_FILE) as f:
                    fdata = json.load(f)

                self.face_detected = fdata.get('detected', False)
                self.face_recognized = fdata.get('recognized', False)
                self.face_confidence = fdata.get('confidence', 0.0)
                self.in_grace = fdata.get('in_grace', False)

                new_state = fdata.get('state', 'idle')
                new_user_id = fdata.get('user_id', 'idle')

                state_changed = (new_state != self._last_state)
                user_switched = (new_state == 'user' and new_user_id != self._last_user_id and new_user_id not in ('', 'idle'))

                if state_changed or user_switched:
                    self._last_state = new_state
                    self._last_user_id = new_user_id
                    self.current_user_id = new_user_id
                    self.current_user_name = fdata.get('user_name', '')

                    if new_state == 'user' and new_user_id not in ('', 'idle'):
                        self.bg_canvas.glow_enabled = True
                        self.guest_container.hide()
                        self.guest_promo_container.hide()
                        
                        self.apply_user_theme(fdata.get('config', {}))
                        self.user_container.show()
                        self.update_user_layout_geometry(self.width(), self.height())
                        
                    elif new_state == 'guest':
                        self.bg_canvas.glow_enabled = True
                        self.user_container.hide()
                        self.guest_promo_container.hide()
                        self.guest_container.show()
                        
                    else:
                        self.bg_canvas.glow_enabled = False
                        self.user_container.hide()
                        self.guest_container.hide()
                        self.guest_promo_container.hide()
            except Exception:
                pass

        if self.face_recognized:
            self.status_dot.setStyleSheet("background-color: #00c850; border-radius: 5px;")
            self.status_dot.show()
        elif self.in_grace:
            self.status_dot.setStyleSheet("background-color: #ff9600; border-radius: 5px;")
            self.status_dot.show()
        else:
            self.status_dot.hide()

    def keyPressEvent(self, event):
        pass


if __name__ == '__main__':
    app = QApplication(sys.argv)
    mirror = SmartMirrorPro()
    mirror.show()
    sys.exit(app.exec())
