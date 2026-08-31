# mirror/smart_mirror_pro.py
import sys
import os
import json
import subprocess
import time
import threading
import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QVBoxLayout, QHBoxLayout, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, QPoint, QSize
from PyQt6.QtGui import QFont, QFontDatabase, QPixmap, QMovie

from config import *
from widgets.notices_widget import NoticesWidget
from widgets.timetable_widget import TimetableWidget
from widgets.schedule_peek_widget import SchedulePeekWidget
from widgets.clock_widget import ClockWidget
from widgets.kings_week_widget import KingsWeekWidget

API_URL = os.environ.get('API_URL', 'https://api.smartmirror.me')
REF_WIDTH  = 1280
REF_HEIGHT = 800

# Gesture regions, mirroring gesture_engine.py.
GESTURE_REGION_LEFT  = 'left'
GESTURE_REGION_RIGHT = 'right'

TIMETABLE_DISPLAY_MS = 5000       # timetable holds this long, then slides away to king's week
TIMETABLE_ANIM_MS    = 460
INDICATOR_BAR_WIDTH  = 4
INDICATOR_BAR_HEIGHT = 100

KINGS_IDLE_MS        = 20_000


# ─────────────────────────────────────────────────────────────────────────────
# Main smart mirror window — clean 2-column layout matching web screenshot
# ─────────────────────────────────────────────────────────────────────────────
class SmartMirrorPro(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Mirror")
        self.setStyleSheet("background-color: #000000;")

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
        self.central_widget.setStyleSheet("background-color: #000000;")
        self.setCentralWidget(self.central_widget)

        # ── Important-message banner (full width, top) ────────────────────
        self._build_banner()

        # ── User layout (matching web screenshot: notices left, focus right) ─
        self._build_user_layout()

        # ── Guest screen (clock + notices + onboarding) ───────────────────
        self._build_guest_layout()

        # ── Vertical Right Dwell Indicator Bar ────────────────────────────
        self._build_indicator_bar()

        # ── Inactivity Darkened Scrim Overlay ─────────────────────────────
        self._build_gesture_demo()

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

        # ── Timetable & King's Week slide state ────────────────────────────
        self._timetable_slid_away = False
        self._timetable_anim = None
        self.timetable_display_timer = QTimer(self)
        self.timetable_display_timer.setSingleShot(True)
        self.timetable_display_timer.timeout.connect(self._slide_timetable_out)

        self.guest_display_timer = QTimer(self)
        self.guest_display_timer.setSingleShot(True)
        self.guest_display_timer.timeout.connect(self._slide_guest_card_out)

        # ── Momentum scrolling engine ─────────────────────────────────────
        self._momentum_timer = QTimer(self)
        self._momentum_timer.timeout.connect(self._momentum_tick)
        self._momentum_velocity = 0.0
        self._momentum_target = None

        # ── Activity & Inactivity Timing ──────────────────────────────────
        self._last_activity_time = time.time()
        self._last_interaction_time = 0.0
        self._demo_anim = None

        # ── Timers ────────────────────────────────────────────────────────
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._update_inputs)
        self.poll_timer.start(200)

        self.gesture_timer = QTimer(self)
        self.gesture_timer.timeout.connect(self._poll_gestures)
        self.gesture_timer.start(50)

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
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3a0d0d, stop:1 #1a0505);
                border-bottom: 1px solid #4a1414;
            }
        """)
        self.banner_frame.setFixedHeight(48)
        self.banner_frame.hide()

        lay = QHBoxLayout(self.banner_frame)
        lay.setContentsMargins(24, 6, 24, 6)
        lay.setSpacing(12)

        self.tag_lbl = QLabel("Notice", self.banner_frame)
        self.tag_lbl.setStyleSheet(
            'font-family: "Segoe UI", sans-serif; font-size: 11px; font-weight: 700; '
            'color: #1a0000; background-color: #ff4d4d; border-radius: 3px; padding: 2px 8px;'
        )
        lay.addWidget(self.tag_lbl)

        self.banner_label = QLabel(self.banner_frame)
        self.banner_label.setStyleSheet(
            'font-family: "Segoe UI", sans-serif; color: #ffdcdc; '
            'font-size: 14px; font-weight: 500;'
        )
        lay.addWidget(self.banner_label, 1)

    # ─────────────────────────────────────────────────────────────────────
    # Build: right-side vertical indicator bar (all white)
    # ─────────────────────────────────────────────────────────────────────
    def _build_indicator_bar(self):
        self.indicator_bar = QFrame(self.central_widget)
        self.indicator_bar.setObjectName("IndicatorBar")
        self.indicator_bar.setStyleSheet("""
            #IndicatorBar {
                background: rgba(255, 255, 255, 0.16);
                border: none;
                border-radius: 2px;
            }
        """)
        self.indicator_fill = QFrame(self.indicator_bar)
        self.indicator_fill.setStyleSheet("""
            background: #ffffff;
            border-radius: 2px;
        """)
        self.indicator_fill.setGeometry(0, INDICATOR_BAR_HEIGHT, INDICATOR_BAR_WIDTH, 0)
        self.indicator_bar.hide()

        # Right-side arrow indicator pointing right (›)
        self.edge_arrow_label = QLabel("›", self.central_widget)
        self.edge_arrow_label.setObjectName("EdgeArrow")
        self.edge_arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edge_arrow_label.setStyleSheet("""
            #EdgeArrow {
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 32px;
                font-weight: 700;
                color: rgba(255, 255, 255, 0.45);
                background: transparent;
                border: none;
            }
        """)
        self.edge_arrow_label.setFixedSize(24, 48)
        self.edge_arrow_label.hide()

    # ─────────────────────────────────────────────────────────────────────
    # Build: gesture demo / inactivity darkened background scrim
    # ─────────────────────────────────────────────────────────────────────
    def _build_gesture_demo(self):
        self.gesture_demo_overlay = QWidget(self.central_widget)
        self.gesture_demo_overlay.setObjectName("GestureDemoOverlay")
        self.gesture_demo_overlay.setStyleSheet("background: rgba(0, 0, 0, 0.72);")

        lay = QVBoxLayout(self.gesture_demo_overlay)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.demo_img_label = QLabel(self.gesture_demo_overlay)
        self.demo_img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.demo_img_label.setStyleSheet("background: transparent; border: none;")
        
        gif_path = os.path.join(os.path.dirname(__file__), 'assets', 'gesture_demo.gif')
        png_path = os.path.join(os.path.dirname(__file__), 'assets', 'gesture_demo.png')
        self.demo_movie = None

        if os.path.exists(gif_path):
            self.demo_movie = QMovie(gif_path)
            self.demo_movie.setFormat(b"gif")
            self.demo_movie.setScaledSize(QSize(360, 240))
            self.demo_img_label.setMovie(self.demo_movie)
        elif os.path.exists(png_path):
            pix = QPixmap(png_path)
            if not pix.isNull():
                self.demo_img_label.setPixmap(
                    pix.scaled(360, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
        lay.addWidget(self.demo_img_label)
        self.gesture_demo_overlay.hide()

    # ─────────────────────────────────────────────────────────────────────
    # Build: user layout (matching web screenshot: 50% notices, 50% right stack)
    # ─────────────────────────────────────────────────────────────────────
    def _build_user_layout(self):
        self.user_container = QWidget(self.central_widget)
        self.user_container.setStyleSheet("background: #000000;")

        # Left column: Notices
        self.notices_widget = NoticesWidget(
            api_url=API_URL, parent=self.user_container
        )

        # Right top: Clock header row
        self.clock_widget = ClockWidget(parent=self.user_container)

        # Right main: Stack container holding King's Week underneath Timetable
        self.right_stack_container = QFrame(self.user_container)
        self.right_stack_container.setStyleSheet("background: transparent; border: none;")

        # King's Week Widget (Underneath)
        self.kings_widget = KingsWeekWidget(
            parent=self.right_stack_container,
            api_url=API_URL
        )

        # Timetable Class Focus block (On top, slides out to the left after 5s)
        self.timetable_widget = TimetableWidget(
            api_url=API_URL, parent=self.right_stack_container
        )

        # For backwards compatibility in tests that access peek_panel / kings_panel
        self.peek_panel = self.timetable_widget
        self.kings_panel = self.kings_widget

        self.user_container.hide()

    def _apply_user_layout(self, w, h):
        """Position user layout elements matching web screenshot (50/50 split)."""
        banner_h = self.banner_frame.height() if not self.banner_frame.isHidden() else 0
        top = banner_h

        self.user_container.setGeometry(0, top, w, h - top)

        left_w = int(w * 0.50)
        right_w = w - left_w
        content_x = left_w + 30
        content_w = right_w - 60
        content_h = h - top - 100

        # Left column: Notices
        self.notices_widget.setGeometry(0, 0, left_w, h - top)

        # Right top: Clock row
        self.clock_widget.setGeometry(content_x, 20, content_w, 65)

        # Right main: Stack Container
        self.right_stack_container.setGeometry(content_x, 90, content_w, content_h)

        # King's Week fills the stack container underneath
        self.kings_widget.setGeometry(0, 0, content_w, content_h)

        # Timetable position depending on whether it's slid away (slides to the left)
        if not self._timetable_slid_away:
            self.timetable_widget.setGeometry(0, 0, content_w, content_h)
        else:
            self.timetable_widget.setGeometry(-content_w, 0, content_w, content_h)

    # ─────────────────────────────────────────────────────────────────────
    # Build: guest layout (clock + notices + smartmirror.me sliding over King's Week)
    # ─────────────────────────────────────────────────────────────────────
    def _build_guest_layout(self):
        self.guest_container = QWidget(self.central_widget)
        self.guest_container.setStyleSheet("background: #000000;")

        # Left: notices panel (50% width)
        self.guest_notices = NoticesWidget(api_url=API_URL, parent=self.guest_container)

        # Right top: clock
        self.guest_clock = ClockWidget(parent=self.guest_container)

        # Right main: Stack container holding King's Week underneath smartmirror.me card
        self.guest_stack_container = QFrame(self.guest_container)
        self.guest_stack_container.setStyleSheet("background: transparent; border: none;")

        # King's Week Widget (Underneath)
        self.guest_kings_widget = KingsWeekWidget(
            parent=self.guest_stack_container,
            api_url=API_URL
        )

        # Right main: Centered smartmirror.me registration prompt (On top, slides away)
        self.guest_register_card = QWidget(self.guest_stack_container)
        self.guest_register_card.setObjectName('GuestRegisterCard')
        self.guest_register_card.setStyleSheet("background: #000000; border: none;")

        card_lay = QVBoxLayout(self.guest_register_card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(16)
        card_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        domain_lbl = QLabel("smartmirror.me", self.guest_register_card)
        domain_lbl.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 52px; font-weight: 800; "
            "color: #ffffff; background: transparent; border: none; letter-spacing: 1px;"
        )
        domain_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(domain_lbl)

        info_lbl = QLabel(
            "Visit smartmirror.me to register your face, customize your timetable, and access personalized notices.",
            self.guest_register_card
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 18px; font-weight: 500; "
            "color: #94a3b8; background: transparent; border: none; line-height: 1.5;"
        )
        info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(info_lbl)

        # For test backwards compatibility
        self.guest_hint = self.guest_register_card
        self._guest_card_slid_away = False
        self._guest_card_anim = None

        self.guest_container.hide()

    def _apply_guest_layout(self, w, h):
        """Position guest layout elements."""
        banner_h = self.banner_frame.height() if not self.banner_frame.isHidden() else 0
        top = banner_h

        self.guest_container.setGeometry(0, top, w, h - top)

        left_w = int(w * 0.50)
        right_w = w - left_w
        content_x = left_w + 30
        content_w = right_w - 60
        content_h = h - top - 100

        self.guest_notices.setGeometry(0, 0, left_w, h - top)
        self.guest_clock.setGeometry(content_x, 20, content_w, 65)

        self.guest_stack_container.setGeometry(content_x, 90, content_w, content_h)
        self.guest_kings_widget.setGeometry(0, 0, content_w, content_h)

        if not self._guest_card_slid_away:
            self.guest_register_card.setGeometry(0, 0, content_w, content_h)
        else:
            self.guest_register_card.setGeometry(content_w, 0, content_w, content_h)

    # ─────────────────────────────────────────────────────────────────────
    # Resize
    # ─────────────────────────────────────────────────────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()

        if hasattr(self, 'banner_frame'):
            self.banner_frame.setGeometry(16, 16, w - 32, self.banner_frame.height())

        if hasattr(self, 'guest_container') and not self.guest_container.isHidden():
            self._apply_guest_layout(w, h)

        if hasattr(self, 'user_container') and not self.user_container.isHidden():
            self._apply_user_layout(w, h)

        if hasattr(self, 'status_dot'):
            self.status_dot.move(w - 20, h - 20)

        # getattr: resizeEvent can fire while __init__ is still building.
        if getattr(self, '_peek_visible', False) and self.peek_container is not None:
            self.peek_container.setGeometry(self._peek_geometry())
            self._layout_peek_stage(animate=False)

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
        if hasattr(self, 'user_container') and not self.user_container.isHidden():
            self._apply_user_layout(self.width(), self.height())
        elif hasattr(self, 'guest_container') and not self.guest_container.isHidden():
            self._apply_guest_layout(self.width(), self.height())

    # ─────────────────────────────────────────────────────────────────────
    # Gesture polling
    #
    # gesture_engine.py publishes which broad region of the screen the hand is
    # in rather than a cursor position, so a gesture acts on whatever panel the
    # hand is generally over: left = notices, right = timetable peek.
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
                self._handle_gesture(data)
        except Exception:
            pass

    def _active_notices(self):
        """The notices panel currently on screen, or None."""
        if self._last_state == 'user':
            return self.notices_widget
        if self._last_state == 'guest':
            return self.guest_notices
        return None

    def _active_notices(self):
        """The notices panel currently on screen, or None."""
        if self._last_state == 'user':
            return self.notices_widget
        if self._last_state == 'guest':
            return self.guest_notices
        return None

    # ─────────────────────────────────────────────────────────────────────
    # Momentum Scrolling Engine
    # ─────────────────────────────────────────────────────────────────────
    def _start_momentum(self, target, velocity):
        self._momentum_target = target
        self._momentum_velocity = float(velocity)
        if not self._momentum_timer.isActive():
            self._momentum_timer.start(16)

    def _stop_momentum(self):
        if self._momentum_timer.isActive():
            self._momentum_timer.stop()
        self._momentum_velocity = 0.0
        self._momentum_target = None

    def _momentum_tick(self):
        if self._momentum_target is None or abs(self._momentum_velocity) < 0.8:
            self._stop_momentum()
            return
        step = int(self._momentum_velocity)
        if step != 0 and hasattr(self._momentum_target, 'scroll_by_pixels'):
            self._momentum_target.scroll_by_pixels(step)
        self._momentum_velocity *= 0.91

    # ─────────────────────────────────────────────────────────────────────
    # Timetable & King's Week Layered Slide Transition
    # ─────────────────────────────────────────────────────────────────────
    def _show_timetable(self, animate=True):
        """Reveal the Timetable over King's Week by fading in from the right."""
        if self.right_stack_container is None:
            return
        self.timetable_display_timer.stop()
        self._timetable_slid_away = False
        cw = self.right_stack_container.width()
        ch = self.right_stack_container.height()

        self.timetable_widget.show()
        self.timetable_widget.raise_()

        if self.kings_widget is not None and self.kings_widget.modal_open:
            self.kings_widget.close_modal(animate=False)

        if self._timetable_anim is not None:
            self._timetable_anim.stop()

        if animate:
            effect = QGraphicsOpacityEffect(self.timetable_widget)
            self.timetable_widget.setGraphicsEffect(effect)
            effect.setOpacity(0.0)

            fade = QPropertyAnimation(effect, b"opacity", self)
            fade.setDuration(TIMETABLE_ANIM_MS)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setEasingCurve(QEasingCurve.Type.OutCubic)

            slide = QPropertyAnimation(self.timetable_widget, b"geometry", self)
            slide.setDuration(TIMETABLE_ANIM_MS)
            slide.setStartValue(QRect(cw // 2, 0, cw, ch))
            slide.setEndValue(QRect(0, 0, cw, ch))
            slide.setEasingCurve(QEasingCurve.Type.OutCubic)
            slide.finished.connect(lambda: self.timetable_widget.setGraphicsEffect(None))

            fade.start()
            slide.start()
            self._timetable_anim = slide
            self._timetable_fade = fade
        else:
            self.timetable_widget.setGeometry(0, 0, cw, ch)
            self.timetable_widget.setGraphicsEffect(None)

        self._update_arrow_indicator()
        self.timetable_display_timer.start(TIMETABLE_DISPLAY_MS)

    def _slide_timetable_out(self, animate=True):
        """Slide the Timetable to the left out of the stack, revealing King's Week."""
        if self.right_stack_container is None:
            return
        self.timetable_display_timer.stop()
        self._timetable_slid_away = True
        cw = self.right_stack_container.width()
        ch = self.right_stack_container.height()

        if self._timetable_anim is not None:
            self._timetable_anim.stop()

        if animate:
            anim = QPropertyAnimation(self.timetable_widget, b"geometry", self)
            anim.setDuration(TIMETABLE_ANIM_MS)
            anim.setStartValue(self.timetable_widget.geometry())
            anim.setEndValue(QRect(-cw, 0, cw, ch))
            anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            anim.finished.connect(self._update_arrow_indicator)
            anim.start()
            self._timetable_anim = anim
        else:
            self.timetable_widget.setGeometry(-cw, 0, cw, ch)
            self._update_arrow_indicator()

        if self.kings_widget is not None and not self.kings_widget.has_content:
            self.kings_widget.refresh()

    def _show_guest_card(self, animate=True):
        """Reveal the smartmirror.me suggestion card over King's Week."""
        if self.guest_stack_container is None:
            return
        self.guest_display_timer.stop()
        self._guest_card_slid_away = False
        cw = self.guest_stack_container.width()
        ch = self.guest_stack_container.height()

        self.guest_register_card.show()
        self.guest_register_card.raise_()

        if hasattr(self, 'guest_kings_widget') and self.guest_kings_widget is not None and self.guest_kings_widget.modal_open:
            self.guest_kings_widget.close_modal(animate=False)

        if self._guest_card_anim is not None:
            self._guest_card_anim.stop()

        if animate:
            effect = QGraphicsOpacityEffect(self.guest_register_card)
            self.guest_register_card.setGraphicsEffect(effect)
            effect.setOpacity(0.0)

            fade = QPropertyAnimation(effect, b"opacity", self)
            fade.setDuration(TIMETABLE_ANIM_MS)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setEasingCurve(QEasingCurve.Type.OutCubic)

            slide = QPropertyAnimation(self.guest_register_card, b"geometry", self)
            slide.setDuration(TIMETABLE_ANIM_MS)
            slide.setStartValue(QRect(cw // 2, 0, cw, ch))
            slide.setEndValue(QRect(0, 0, cw, ch))
            slide.setEasingCurve(QEasingCurve.Type.OutCubic)
            slide.finished.connect(lambda: self.guest_register_card.setGraphicsEffect(None))

            fade.start()
            slide.start()
            self._guest_card_anim = slide
        else:
            self.guest_register_card.setGeometry(0, 0, cw, ch)
            self.guest_register_card.setGraphicsEffect(None)

        self._update_arrow_indicator()
        self.guest_display_timer.start(TIMETABLE_DISPLAY_MS)

    def _slide_guest_card_out(self, animate=True):
        """Slide the smartmirror.me suggestion card to the right out of the stack, revealing King's Week."""
        if self.guest_stack_container is None:
            return
        self.guest_display_timer.stop()
        self._guest_card_slid_away = True
        cw = self.guest_stack_container.width()
        ch = self.guest_stack_container.height()

        if self._guest_card_anim is not None:
            self._guest_card_anim.stop()

        if animate:
            anim = QPropertyAnimation(self.guest_register_card, b"geometry", self)
            anim.setDuration(TIMETABLE_ANIM_MS)
            anim.setStartValue(self.guest_register_card.geometry())
            anim.setEndValue(QRect(cw, 0, cw, ch))
            anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            anim.finished.connect(self._update_arrow_indicator)
            anim.start()
            self._guest_card_anim = anim
        else:
            self.guest_register_card.setGeometry(cw, 0, cw, ch)
            self._update_arrow_indicator()

        if self.guest_kings_widget is not None and not self.guest_kings_widget.has_content:
            self.guest_kings_widget.refresh()

    def _update_arrow_indicator(self):
        """Show the arrow pointing right when King's Week is shown and dwell is inactive."""
        if not hasattr(self, 'edge_arrow_label') or self.edge_arrow_label is None:
            return
        if hasattr(self, 'indicator_bar') and not self.indicator_bar.isHidden():
            self.edge_arrow_label.hide()
            return

        should_show = (
            (self._last_state == 'user' and self._timetable_slid_away)
            or (self._last_state == 'guest' and self._guest_card_slid_away)
        )
        if should_show:
            top = self.banner_frame.height() if not self.banner_frame.isHidden() else 0
            arrow_y = top + (self.height() - top - 48) // 2
            self.edge_arrow_label.move(self.width() - 28, arrow_y)
            self.edge_arrow_label.show()
            self.edge_arrow_label.raise_()
        else:
            self.edge_arrow_label.hide()

    def _show_gesture_scrim(self):
        """Darken the screen background slightly for ~3.5 seconds and play demo GIF."""
        if self.gesture_demo_overlay is None:
            return
        self.gesture_demo_overlay.setGeometry(0, 0, self.width(), self.height())
        effect = QGraphicsOpacityEffect(self.gesture_demo_overlay)
        self.gesture_demo_overlay.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        self.gesture_demo_overlay.show()
        self.gesture_demo_overlay.raise_()

        if hasattr(self, 'demo_movie') and self.demo_movie is not None:
            self.demo_movie.start()

        anim_in = QPropertyAnimation(effect, b"opacity", self)
        anim_in.setDuration(500)
        anim_in.setStartValue(0.0)
        anim_in.setEndValue(1.0)
        anim_in.start()
        self._demo_anim = anim_in

        def fade_out():
            anim_out = QPropertyAnimation(effect, b"opacity", self)
            anim_out.setDuration(500)
            anim_out.setStartValue(1.0)
            anim_out.setEndValue(0.0)

            def on_done():
                self.gesture_demo_overlay.hide()
                if hasattr(self, 'demo_movie') and self.demo_movie is not None:
                    self.demo_movie.stop()

            anim_out.finished.connect(on_done)
            anim_out.start()
            self._demo_anim = anim_out

        QTimer.singleShot(3500, fade_out)

    # ─────────────────────────────────────────────────────────────────────
    # Gesture Dispatch
    # ─────────────────────────────────────────────────────────────────────
    def _handle_gesture(self, data):
        # Don't turn on gestures until it's either in guest or recognized
        if self._last_state not in ('guest', 'user'):
            return

        present     = data.get("present", False)
        region      = data.get("region") if present else None
        event       = data.get("event")
        delta       = data.get("scroll_delta", 0)
        right_dwell = data.get("right_dwell_progress", 0.0)
        dwell_side  = data.get("dwell_side") or ("right" if data.get("hand_x", 0.5) >= 0.5 else "left")
        notices     = self._active_notices()

        if present:
            self._last_activity_time = time.time()
            self._last_interaction_time = time.time()

        # ── Indicator Bar on Edge Dwell (Left or Right) ───────────────────
        if self._last_state in ('user', 'guest'):
            if right_dwell > 0.02:
                self._last_interaction_time = time.time()
                if hasattr(self, 'edge_arrow_label'):
                    self.edge_arrow_label.hide()
                top = self.banner_frame.height() if not self.banner_frame.isHidden() else 0
                bar_y = top + (self.height() - top - INDICATOR_BAR_HEIGHT) // 2
                bar_x = 12 if dwell_side == 'left' else (self.width() - INDICATOR_BAR_WIDTH - 12)
                self.indicator_bar.setGeometry(bar_x, bar_y, INDICATOR_BAR_WIDTH, INDICATOR_BAR_HEIGHT)
                fill_h = int(INDICATOR_BAR_HEIGHT * right_dwell)
                self.indicator_fill.setGeometry(0, INDICATOR_BAR_HEIGHT - fill_h, INDICATOR_BAR_WIDTH, fill_h)
                self.indicator_bar.show()
                self.indicator_bar.raise_()
            else:
                self.indicator_bar.hide()
                self._update_arrow_indicator()

        # ── Handle Events ────────────────────────────────────────────────
        if event in ("enter_right", "enter_left", "enter_dwell"):
            self.indicator_bar.hide()
            if self._last_state == 'user':
                if self._timetable_slid_away:
                    self._show_timetable(animate=True)
                else:
                    self._slide_timetable_out(animate=True)
            elif self._last_state == 'guest':
                if self._guest_card_slid_away:
                    self._show_guest_card(animate=True)
                else:
                    self._slide_guest_card_out(animate=True)

        elif region == GESTURE_REGION_LEFT and notices is not None:
            if event == "scroll" and delta != 0:
                self._stop_momentum()
                notices.scroll_by_pixels(delta)
            elif event == "fling" and delta != 0:
                self._start_momentum(notices, delta)
            elif event == "tap":
                self._stop_momentum()
                notices.toggle_scroll_pause()

        elif region == GESTURE_REGION_RIGHT:
            active_kings = None
            if self._last_state == 'user' and self._timetable_slid_away:
                active_kings = self.kings_widget
            elif self._last_state == 'guest' and self._guest_card_slid_away:
                active_kings = self.guest_kings_widget

            if active_kings is not None:
                if event == "scroll" and delta != 0:
                    self._stop_momentum()
                    active_kings.clear_selection()
                    active_kings.scroll_by_pixels(delta)
                elif event == "fling" and delta != 0:
                    active_kings.clear_selection()
                    self._start_momentum(active_kings, delta)
                elif event == "tap":
                    self._stop_momentum()
                    if active_kings.modal_open:
                        active_kings.close_modal()
                    else:
                        active_kings.activate_selected()
                elif event not in ("scroll", "fling"):
                    self._focus_kings_target(active_kings, data)

        # Affordances
        if notices is not None:
            notices.set_gesture_active(region == GESTURE_REGION_LEFT)
        if self.kings_widget is not None:
            self.kings_widget.set_gesture_active(
                region == GESTURE_REGION_RIGHT
                and self._last_state == 'user'
                and self._timetable_slid_away
            )
        if hasattr(self, 'guest_kings_widget') and self.guest_kings_widget is not None:
            self.guest_kings_widget.set_gesture_active(
                region == GESTURE_REGION_RIGHT
                and self._last_state == 'guest'
                and self._guest_card_slid_away
            )

    def _focus_kings(self, data):
        self._focus_kings_target(self.kings_widget, data)

    def _focus_kings_target(self, panel, data):
        if panel is None or panel.width() <= 0 or panel.height() <= 0:
            return
        origin = panel.mapTo(self.central_widget, QPoint(0, 0))
        x = (data.get("hand_x", 0.0) * self.width() - origin.x()) / panel.width()
        y = (data.get("hand_y", 0.0) * self.height() - origin.y()) / panel.height()
        panel.focus_at(x, y)

    # ─────────────────────────────────────────────────────────────────────
    # Legacy peek helpers for backward compatibility in tests
    # ─────────────────────────────────────────────────────────────────────
    def _ensure_peek(self):
        return self.right_stack_container

    def _show_timetable_peek(self):
        self._show_timetable(animate=True)

    def _hide_timetable_peek(self, animate=True):
        self._slide_timetable_out(animate=animate)

    # ─────────────────────────────────────────────────────────────────────
    # Fade helpers
    # ─────────────────────────────────────────────────────────────────────
    def _fade_in(self, widget, duration=380, retire=None):
        """Show widget and animate opacity 0 → 1.

        `retire` is whatever was on screen before: it stays fully opaque
        underneath and is hidden once the new screen has finished arriving. That
        makes this a dissolve rather than a fade to black and back — see
        _trigger_transition for why that matters.
        """
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        widget.show()
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: self._on_fade_in_done(widget, retire))
        anim.start()
        self._anim_in = anim

    def _on_fade_in_done(self, widget, retire=None):
        # Remove effect so child painting isn't affected by opacity layer
        widget.setGraphicsEffect(None)
        if retire is not None:
            retire.hide()
            retire.setGraphicsEffect(None)
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
        font_family = fonts.get("family", "Segoe UI")

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

                # ── Guard: Don't interrupt active interactions ─────────────
                is_interacting = (
                    (time.time() - self._last_interaction_time < 6.0)
                    or (self.kings_widget and self.kings_widget.modal_open)
                    or (self.indicator_bar and not self.indicator_bar.isHidden())
                )
                if is_interacting and not user_switched:
                    # If state is trying to demote from user -> guest/idle or guest -> idle while interacting
                    if (self._last_state == 'user' and new_state in ('guest', 'idle')) or (self._last_state == 'guest' and new_state == 'idle'):
                        pass  # Defer transition while user is actively interacting
                    elif (state_changed or user_switched) and not self._transitioning:
                        self._transitioning = True
                        self._last_state    = new_state
                        self._last_user_id  = new_user_id
                        self.current_user_id   = new_user_id
                        self.current_user_name = fdata.get('user_name', '')
                        self._last_activity_time = time.time()
                        self._trigger_transition(new_state, new_user_id, fdata)
                elif (state_changed or user_switched) and not self._transitioning:
                    self._transitioning = True
                    self._last_state    = new_state
                    self._last_user_id  = new_user_id
                    self.current_user_id   = new_user_id
                    self.current_user_name = fdata.get('user_name', '')
                    self._last_activity_time = time.time()
                    self._trigger_transition(new_state, new_user_id, fdata)

            except Exception:
                pass

        # ── 20-second Inactivity Darkened Overlay ─────────────────────────
        if self._last_state in ('guest', 'user') and not self._transitioning:
            if time.time() - self._last_activity_time >= 20.0:
                self._last_activity_time = time.time()
                self._show_gesture_scrim()

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
        """Dissolve from whatever is on screen to the new state.

        The old version faded the current screen out to black over 280ms and only
        then began fading the new one in over another 380ms: two thirds of a
        second, with a fully black screen in the middle of it. One trip through
        that is a transition. A run of them — which is what a recognition that
        keeps dropping out produces — is a strobe, and that is what "flashing"
        was. USER_HOLD_SEC stops the state from bouncing in the first place; this
        makes the one transition that remains half as long and never dark, by
        building the new screen underneath the old one and dissolving across.
        """
        visible = None
        if not self.user_container.isHidden():
            visible = self.user_container
        elif not self.guest_container.isHidden():
            visible = self.guest_container

        if new_state == 'user' and new_user_id not in ('', 'idle'):
            incoming = self.user_container
        elif new_state == 'guest':
            incoming = self.guest_container
        else:
            incoming = None

        # The peek belongs to whoever was just on screen — drop it outright
        # rather than sliding it out over a different student's dashboard.
        self._hide_timetable_peek(animate=False)
        self.notices_widget.reset_gesture_state()
        self.guest_notices.reset_gesture_state()
        if self.kings_panel is not None:
            self.kings_panel.reset_gesture_state()

        # One student handing over to another reuses the same container, so there
        # is nothing to dissolve across and it keeps the old two-stage fade. That
        # is the right language for it anyway: a different person's dashboard
        # should not appear to grow out of the last one's.
        if incoming is not None and incoming is visible:
            def swap():
                self._prepare(incoming, new_state, new_user_id, fdata)
                self._fade_in(incoming)
            self._fade_out(visible, on_done=swap)
            return

        # Otherwise: whatever is leaving drops to the bottom of the stack so the
        # arriving screen dissolves in over the top of it. Not raise_() on the
        # arriving one — that would also lift it over the banner and status dot.
        if visible is not None:
            visible.setGraphicsEffect(None)
            visible.lower()

        if incoming is not None:
            self._prepare(incoming, new_state, new_user_id, fdata)
            self._fade_in(incoming, retire=visible)

        elif visible is not None:
            # Idle: there is nothing to dissolve to, so this one really does fade
            # to black — which is the intended end state, not a gap.
            self._fade_out(visible, on_done=self._on_fade_to_idle_done)

        else:
            self._transitioning = False   # already blank, nothing to animate

    def _prepare(self, container, new_state, new_user_id, fdata):
        """Fill in and lay out a container before it is faded in."""
        if container is self.user_container:
            self.timetable_widget.set_user_id(new_user_id)
            self._apply_user_theme(fdata.get('config', {}))
            self._apply_user_layout(self.width(), self.height())
            self._show_timetable(animate=False)
        else:
            self.timetable_widget.set_user_id('')
            self._apply_guest_layout(self.width(), self.height())
            self._show_guest_card(animate=False)

    def _on_fade_to_idle_done(self):
        self.user_container.hide()
        self.guest_container.hide()
        self.user_container.setGraphicsEffect(None)
        self.guest_container.setGraphicsEffect(None)
        self._transitioning = False

    def keyPressEvent(self, event):
        pass


# ─────────────────────────────────────────────────────────────────────────────
def start_gesture_daemon():
    """Launch gesture_engine.py alongside the UI, and return the process.

    The UI only ever *reads* gesture_status.json, so until now the gestures
    silently did nothing unless somebody happened to know to start the daemon in
    a third terminal — nothing in the launch scripts or the README did. Spawning
    it here means running the mirror is enough.

    Set MIRROR_GESTURES=0 to opt out (no camera to spare, or you are running the
    daemon yourself). GESTURE_CAMERA picks the device: an index on a desktop
    webcam, or --rpi for the loopback device the Pi's camera pipeline feeds.
    GESTURE_FLIP=0/1 sets which physical side of you drives which panel — the
    daemon reads it directly, so nothing needs passing here.

    The daemon is given a pipe on stdin and told to exit when it closes. The
    `finally` block below only runs on a graceful exit, and during a debugging
    session the mirror is mostly killed rather than closed — which left a daemon
    behind every time. Eight of them accumulated, all publishing to the same
    status file, and the log filled with WinError 5 as each replaced a scratch
    file another had already moved. A pipe cannot be leaked: the OS closes this
    end however the mirror dies, so the daemon always learns about it.
    """
    if os.environ.get('MIRROR_GESTURES', '1') == '0':
        print('[MIRROR] MIRROR_GESTURES=0 — not starting the gesture daemon.')
        return None

    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'gesture_engine.py')
    camera = os.environ.get('GESTURE_CAMERA')
    if camera is None:
        args = ['--rpi'] if sys.platform.startswith('linux') else ['--camera-id', '0']
    else:
        args = ['--camera-id', camera]
    args.append('--exit-with-parent')

    try:
        proc = subprocess.Popen([sys.executable, '-u', script] + args,
                                stdin=subprocess.PIPE)
        print(f'[MIRROR] Gesture daemon started (pid {proc.pid}, {" ".join(args)}).')
        return proc
    except Exception as e:
        # A mirror with no gestures is still a working mirror, so this is never
        # allowed to stop the UI from coming up.
        print(f'[MIRROR] Could not start the gesture daemon: {e}')
        return None


if __name__ == '__main__':
    app = QApplication(sys.argv)
    gestures = start_gesture_daemon()
    mirror = SmartMirrorPro()
    mirror.show()
    try:
        code = app.exec()
    finally:
        if gestures is not None and gestures.poll() is None:
            gestures.terminate()
            try:
                gestures.wait(timeout=3)
            except subprocess.TimeoutExpired:
                gestures.kill()
    sys.exit(code)

