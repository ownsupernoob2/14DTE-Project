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

API_URL = os.environ.get('API_URL', 'https://api.smartmirror.me')
REF_WIDTH = 1280
REF_HEIGHT = 800


def _widget_data(wd):
    data = wd.get('data', {}) or {}
    return data if isinstance(data, dict) else {}


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

        # IDLE state: Render completely black (glow_enabled is False)
        if not self.glow_enabled:
            painter.fillRect(self.rect(), QColor(0, 0, 0))
            painter.end()
            return

        w = self.width()
        h = self.height()

        # Solid base -- #0a0a0c
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

        # Animated background -- lowest layer, no mouse interaction
        self.bg_canvas = BackgroundCanvas(self.central_widget)
        self.bg_canvas.setGeometry(self.central_widget.rect())
        self.bg_canvas.lower()

        # Container for User widgets
        self.user_container = QWidget(self.central_widget)
        self.user_container.setGeometry(self.rect())
        self.user_container.setStyleSheet("background: transparent;")

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

        self.widgets = []
        self.last_gesture_timestamp = 0.0

        # Polling Timers
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.update_inputs)
        self.poll_timer.start(200)

        # Gesture status polling timer
        self.gesture_timer = QTimer(self)
        self.gesture_timer.timeout.connect(self.poll_gestures)
        self.gesture_timer.start(100)

        # Admin banner polling timer (every 10 seconds)
        self.banner_timer = QTimer(self)
        self.banner_timer.timeout.connect(self.poll_admin_banner)
        self.banner_timer.start(10000)
        self.poll_admin_banner() # initial check

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
        if hasattr(self, 'guest_container') and self.guest_container:
            self.guest_container.setGeometry(0, 0, w, h)
        if hasattr(self, 'guest_promo_container') and self.guest_promo_container:
            self.guest_promo_container.setGeometry(0, 0, w, h)
        if hasattr(self, 'status_dot') and self.status_dot:
            self.status_dot.move(w - 20, 20)
        if hasattr(self, 'banner_frame') and self.banner_frame:
            self.banner_frame.setGeometry(0, 0, w, 40)

    def setup_guest_layout(self):
        self.guest_layout = QVBoxLayout(self.guest_container)
        self.guest_layout.setContentsMargins(40, 60, 40, 40)
        self.guest_layout.setSpacing(20)

        # Top row: Clock & notices
        top_row = QHBoxLayout()
        top_row.setSpacing(30)

        self.guest_clock = ClockWidget(0, 0, 300, 150)
        self.guest_notices = NoticesWidget(0, 0, 500, 300, API_URL)
        
        top_row.addWidget(self.guest_clock, 1)
        top_row.addWidget(self.guest_notices, 2)
        self.guest_layout.addLayout(top_row, 3)

        # Bottom row: Onboarding dashboard
        self.onboarding_card = QFrame(self.guest_container)
        self.onboarding_card.setObjectName("OnboardingCard")
        self.onboarding_card.setStyleSheet("""
            #OnboardingCard {
                background-color: rgba(255, 255, 255, 6);
                border: 1px solid rgba(255, 255, 255, 12);
                border-radius: 16px;
            }
        """)
        ob_layout = QVBoxLayout(self.onboarding_card)
        ob_layout.setContentsMargins(20, 16, 20, 16)
        ob_layout.setSpacing(10)

        ob_title = QLabel("HOW TO INTERACT VIA HAND GESTURES")
        ob_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #60a5fa; letter-spacing: 2px;")
        ob_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ob_layout.addWidget(ob_title)

        # Gestures row
        gestures_layout = QHBoxLayout()
        gestures_layout.setSpacing(15)

        gesture_guides = [
            ("Swipe Left", "Open Daily Notices"),
            ("Swipe Right", "Open Timetable"),
            ("Pinch & Drag", "Scroll Active View"),
            ("Peace Sign (Hold 2s)", "Notices Shortcut"),
            ("OK Sign (Hold 2s)", "Timetable Shortcut")
        ]
        for title, desc in gesture_guides:
            g_box = QFrame()
            g_box.setStyleSheet("background-color: rgba(255,255,255,8); border-radius: 8px; border: 1px solid rgba(255,255,255,8);")
            gb_lay = QVBoxLayout(g_box)
            gb_lay.setContentsMargins(10, 10, 10, 10)
            gb_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

            g_title = QLabel(title)
            g_title.setStyleSheet("font-weight: bold; color: #ffffff; font-size: 11px;")
            g_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

            g_desc = QLabel(desc)
            g_desc.setStyleSheet("color: #a0a0a0; font-size: 10px;")
            g_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            g_desc.setWordWrap(True)

            gb_lay.addWidget(g_title)
            gb_lay.addWidget(g_desc)
            gestures_layout.addWidget(g_box)

        ob_layout.addLayout(gestures_layout)
        
        # Instructional animations GIF placeholder
        self.ob_gif_label = QLabel(self.onboarding_card)
        self.ob_gif_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ob_gif_label.setText("Looping Instructional Gestures Animation Placeholder (assets/onboarding_gesture.gif)")
        self.ob_gif_label.setStyleSheet("color: rgba(255,255,255,100); font-size: 11px; padding: 10px; border: 1px dashed rgba(255,255,255,20); border-radius: 8px;")
        ob_layout.addWidget(self.ob_gif_label)

        self.guest_layout.addWidget(self.onboarding_card, 2)

    def setup_guest_promo_layout(self):
        self.guest_promo_container = QFrame(self.central_widget)
        self.guest_promo_container.setGeometry(self.rect())
        self.guest_promo_container.setStyleSheet("background-color: rgba(10, 10, 12, 235);")
        self.guest_promo_container.hide()

        promo_layout = QVBoxLayout(self.guest_promo_container)
        promo_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        promo_layout.setSpacing(25)

        promo_title = QLabel("Timetable Protected")
        promo_title.setStyleSheet("font-size: 36px; font-weight: bold; color: #ef4444; letter-spacing: 1px;")
        promo_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        promo_desc = QLabel("Sign up at smartmirror.me to view your custom school timetable.")
        promo_desc.setStyleSheet("font-size: 20px; color: #e5e7eb; max-width: 600px; line-height: 1.6;")
        promo_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        promo_desc.setWordWrap(True)

        promo_hint = QLabel("Swipe Left to return to the guest dashboard.")
        promo_hint.setStyleSheet("font-size: 14px; color: #9ca3af; font-style: italic;")
        promo_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        promo_layout.addWidget(promo_title)
        promo_layout.addWidget(promo_desc)
        promo_layout.addWidget(promo_hint)

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
                    data = res.json()
                    msg = data.get("message", "")
                    QTimer.singleShot(0, lambda: self.update_admin_banner(msg))
            except Exception:
                pass
        import threading
        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def update_admin_banner(self, message):
        if message:
            self.banner_label.setText(message)
            self.banner_frame.show()
            self.banner_frame.raise_()
        else:
            self.banner_frame.hide()

    def poll_gestures(self):
        gesture_file = os.path.join(
            os.environ.get("TEMP", os.environ.get("TMP", "/tmp")), "gesture_status.json"
        )
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
        # Ignore gesture commands if state is idle
        if self._last_state == 'idle':
            return

        if gesture == "swipe_right" or gesture == "ok_hold":
            if self._last_state == 'guest':
                self.show_guest_promo()
            elif self._last_state == 'user':
                for w in self.widgets:
                    if isinstance(w, TimetableWidget):
                        w.raise_()

        elif gesture == "swipe_left" or gesture == "peace_hold":
            if self._last_state == 'guest':
                if self.guest_promo_container.isVisible():
                    self.hide_guest_promo()
            elif self._last_state == 'user':
                for w in self.widgets:
                    if isinstance(w, NoticesWidget):
                        w.raise_()

        elif gesture == "scroll" and scroll_delta != 0:
            for w in self.widgets:
                if isinstance(w, (NoticesWidget, TimetableWidget)) and w.isVisible():
                    w.scroll_by_pixels(scroll_delta)
            if self._last_state == 'guest':
                self.guest_notices.scroll_by_pixels(scroll_delta)

    def clear_widgets(self):
        for w in self.widgets:
            w.deleteLater()
        self.widgets = []

    def _pct_to_pixels(self, wd):
        x = wd.get('x', 5.0)
        y = wd.get('y', 5.0)
        w = wd.get('w')
        h = wd.get('h')

        is_absolute = x > 100 or y > 100 or (w is not None and w > 100) or (h is not None and h > 100)
        if is_absolute:
            x_pct = (x / REF_WIDTH) * 100.0
            y_pct = (y / REF_HEIGHT) * 100.0
            w_pct = (w / REF_WIDTH) * 100.0 if w is not None else 18.0
            h_pct = (h / REF_HEIGHT) * 100.0 if h is not None else 13.0
        else:
            x_pct = x
            y_pct = y
            w_pct = w if w is not None else 18.0
            h_pct = h if h is not None else 13.0

        real_x = int((x_pct / 100.0) * self.width())
        real_y = int((y_pct / 100.0) * self.height())
        real_w = max(160, int((w_pct / 100.0) * self.width()))
        real_h = max(80, int((h_pct / 100.0) * self.height()))
        return real_x, real_y, real_w, real_h

    def apply_remote_widgets(self, remote_config):
        try:
            self.clear_widgets()
            if not remote_config:
                return

            theme = remote_config.get("theme", {})
            colors = theme.get("colors", {})
            fonts = theme.get("fonts", {})
            primary = colors.get("primary", "#3b82f6")
            secondary = colors.get("secondary", "#10b981")
            font_family = fonts.get("family", "Outfit")

            slots = remote_config.get("slots", [])
            for s in slots:
                orientation = s.get("orientation", "horizontal")
                wd = s.get("widget", {})
                if not wd:
                    continue

                real_x, real_y, real_w, real_h = self._pct_to_pixels(wd)
                wtype = wd.get('type', '').lower()
                data = _widget_data(wd)

                widget = None
                if wtype == 'clock':
                    widget = ClockWidget(real_x, real_y, real_w, real_h)
                elif wtype == 'weather':
                    widget = WeatherWidget(real_x, real_y, real_w, real_h)
                elif wtype == 'notices':
                    kw = data.get('keyword_filter') or data.get('keywordFilter') or ''
                    speed = data.get('scroll_speed', data.get('scrollSpeed', 0.5))
                    year = data.get('year_filter') or data.get('yearFilter') or 'All'
                    cats = data.get('cat_filters') or data.get('catFilters') or None
                    widget = NoticesWidget(real_x, real_y, real_w, real_h, API_URL, kw, speed, year, cats)
                elif wtype == 'timetable':
                    view_mode = data.get('viewMode', 'today')
                    subject = data.get('subject_filter') or data.get('subjectFilter') or ''
                    widget = TimetableWidget(
                        real_x, real_y, real_w, real_h,
                        self.current_user_id or '', API_URL,
                        view_mode=view_mode, subject_filter=subject
                    )
                elif wtype == 'note':
                    widget = NoteWidget(real_x, real_y, real_w, real_h, data)

                if widget:
                    widget.setParent(self.user_container)
                    widget.set_orientation(orientation)
                    widget.apply_theme(primary, secondary, font_family)
                    self.widgets.append(widget)
                    
                    widget.setGeometry(real_x, real_y + 40, real_w, real_h)
                    pos_anim = QPropertyAnimation(widget, b"geometry")
                    pos_anim.setDuration(600)
                    pos_anim.setStartValue(QRect(real_x, real_y + 40, real_w, real_h))
                    pos_anim.setEndValue(QRect(real_x, real_y, real_w, real_h))
                    pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                    
                    opacity_effect = QGraphicsOpacityEffect(widget)
                    widget.setGraphicsEffect(opacity_effect)
                    fade_anim = QPropertyAnimation(opacity_effect, b"opacity")
                    fade_anim.setDuration(600)
                    fade_anim.setStartValue(0.0)
                    fade_anim.setEndValue(1.0)
                    
                    pos_anim.start()
                    fade_anim.start()
                    
                    widget._pos_anim = pos_anim
                    widget._fade_anim = fade_anim
                    widget.show()
        except Exception as e:
            print(f"[ERROR] Failed to apply remote widgets: {e}")
            self.clear_widgets()

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
                user_switched = (new_state == 'user' and new_user_id != self._last_user_id
                                 and new_user_id not in ('', 'idle'))

                if state_changed or user_switched:
                    self._last_state = new_state
                    self._last_user_id = new_user_id
                    self.current_user_id = new_user_id
                    self.current_user_name = fdata.get('user_name', '')

                    if new_state == 'user' and new_user_id not in ('', 'idle'):
                        self.bg_canvas.glow_enabled = True
                        self.guest_container.hide()
                        self.guest_promo_container.hide()
                        self.user_container.show()
                        self.apply_remote_widgets(fdata.get('config', {}))
                    elif new_state == 'guest':
                        self.bg_canvas.glow_enabled = True
                        self.clear_widgets()
                        self.user_container.hide()
                        self.guest_promo_container.hide()
                        
                        opacity_effect = QGraphicsOpacityEffect(self.guest_container)
                        self.guest_container.setGraphicsEffect(opacity_effect)
                        self.guest_anim = QPropertyAnimation(opacity_effect, b"opacity")
                        self.guest_anim.setDuration(500)
                        self.guest_anim.setStartValue(0.0)
                        self.guest_anim.setEndValue(1.0)
                        
                        self.guest_container.show()
                        self.guest_anim.start()
                    else:
                        # idle - show completely black screen
                        self.bg_canvas.glow_enabled = False
                        self.clear_widgets()
                        self.guest_container.hide()
                        self.guest_promo_container.hide()
                        self.user_container.hide()
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


if __name__ == '__main__':
    app = QApplication(sys.argv)
    mirror = SmartMirrorPro()
    mirror.show()
    sys.exit(app.exec())
