# mirror/smart_mirror_pro.py
import sys
import os
import json
import time
import math
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QVBoxLayout, QHBoxLayout, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap, QRadialGradient, QColor, QPainter

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


# ---------------------------------------------------------------------------
# Animated background -- two blurred radial-gradient orbs that slowly drift,
# matching the web dashboard body::before effect.
# ---------------------------------------------------------------------------
class BackgroundCanvas(QWidget):
    """Full-screen background widget painted with QPainter radial gradients.

    Two glow orbs:
      - Purple  at roughly (20%, 50%)  -- rgba(109, 40, 217, 0.12)
      - Sky-blue at roughly (80%, 30%) -- rgba( 56,189, 248, 0.09)

    Their centres drift gently on an 18-second sine cycle to simulate
    the CSS 'bg-drift' animation.
    """

    # Orb definitions: (base_cx_pct, base_cy_pct, radius_pct, r, g, b, max_alpha)
    _ORBS = [
        (0.20, 0.50, 0.55, 109,  40, 217, 31),   # purple  -- 0.12 * 255 ~ 31
        (0.80, 0.30, 0.50,  56, 189, 248, 23),   # sky-blue -- 0.09 * 255 ~ 23
    ]
    _DRIFT_PERIOD = 18.0   # seconds for one full drift cycle
    _DRIFT_AMP    = 0.03   # fraction of screen dimension

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._t0 = time.time()

        self._redraw_timer = QTimer(self)
        self._redraw_timer.timeout.connect(self.update)   # triggers paintEvent
        self._redraw_timer.start(33)   # ~30 fps repaint

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Solid base -- #0a0a0c
        painter.fillRect(self.rect(), QColor(10, 10, 12))

        t = time.time() - self._t0
        # Phase offsets keep the two orbs out of sync
        phases = [0.0, math.pi * 0.6]

        for i, (bcx, bcy, r_pct, r, g, b, max_a) in enumerate(self._ORBS):
            phase = phases[i]
            # Slow sine drift in both axes
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
        self.bg_canvas.lower()   # always below all sibling widgets

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

        # Status Dot
        self.status_dot = QLabel(self.central_widget)
        self.status_dot.setFixedSize(10, 10)
        self.status_dot.setStyleSheet("background-color: transparent; border-radius: 5px;")
        self.status_dot.hide()

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

        # Polling Timer (Checks face recognition status file every 200ms)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.update_inputs)
        self.poll_timer.start(200)

        # Window state (show / resize at the end of __init__ so everything is fully initialized)
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
        if hasattr(self, 'status_dot') and self.status_dot:
            self.status_dot.move(w - 20, 20)

    def setup_guest_layout(self):
        layout = QHBoxLayout(self.guest_container)
        layout.setContentsMargins(40, 80, 40, 120)
        layout.setSpacing(40)

        # Left Column - Guest Notices
        self.guest_notices = NoticesWidget(0, 0, self.width() // 2 - 60, self.height() - 200, API_URL)
        layout.addWidget(self.guest_notices, 1)

        # Right Column - Welcome panel
        right_panel = QFrame(self.guest_container)
        right_panel.setObjectName("WelcomePanel")
        right_panel.setStyleSheet("""
            #WelcomePanel {
                background-color: rgba(255, 255, 255, 6);
                border: 1px solid rgba(255, 255, 255, 12);
                border-radius: 16px;
            }
        """)
        
        rp_layout = QVBoxLayout(right_panel)
        rp_layout.setContentsMargins(32, 48, 32, 48)
        rp_layout.setSpacing(20)
        rp_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_lbl = QLabel("New Visitor?")
        title_lbl.setStyleSheet("font-size: 32px; font-weight: bold; color: #f0f0f0;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        desc_lbl = QLabel("Scan your face to configure your\npersonalized smart mirror dashboard.")
        desc_lbl.setStyleSheet("font-size: 18px; color: #a0a0a0; line-height: 1.5;")
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Image placeholder
        img_lbl = QLabel(right_panel)
        img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        guest_img_path = None
        for ext in ['gif', 'png', 'jpg', 'jpeg']:
            p = f"assets/guest.{ext}"
            if os.path.exists(p):
                guest_img_path = p
                break
        if guest_img_path:
            pix = QPixmap(guest_img_path)
            img_lbl.setPixmap(pix.scaled(260, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        
        url_lbl = QLabel("smartmirror.me")
        url_lbl.setStyleSheet("font-size: 38px; font-weight: bold; color: #60a5fa;")
        url_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        prompt_lbl = QLabel("Sign up and register on the website")
        prompt_lbl.setStyleSheet("font-size: 16px; color: #787878;")
        prompt_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        rp_layout.addWidget(title_lbl)
        rp_layout.addWidget(desc_lbl)
        if guest_img_path:
            rp_layout.addWidget(img_lbl)
        rp_layout.addWidget(url_lbl)
        rp_layout.addWidget(prompt_lbl)
        
        layout.addWidget(right_panel, 1)

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

    def apply_remote_widgets(self, remote_widgets):
        try:
            self.clear_widgets()
            if not remote_widgets:
                return

            for wd in remote_widgets:
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
                    self.widgets.append(widget)
                    
                    # Smooth Fade-in Slide Transition using QPropertyAnimation
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
                    
                    # Prevent animation garbage collection
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
                        self.guest_container.hide()
                        self.user_container.show()
                        self.apply_remote_widgets(fdata.get('widgets', []))
                    elif new_state == 'guest':
                        self.clear_widgets()
                        self.user_container.hide()
                        
                        # Animate guest screen fade-in
                        opacity_effect = QGraphicsOpacityEffect(self.guest_container)
                        self.guest_container.setGraphicsEffect(opacity_effect)
                        self.guest_anim = QPropertyAnimation(opacity_effect, b"opacity")
                        self.guest_anim.setDuration(500)
                        self.guest_anim.setStartValue(0.0)
                        self.guest_anim.setEndValue(1.0)
                        
                        self.guest_container.show()
                        self.guest_anim.start()
                    else:
                        # idle - show black screen
                        self.clear_widgets()
                        self.guest_container.hide()
                        self.user_container.hide()
            except Exception:
                pass

        # Update status dot
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
