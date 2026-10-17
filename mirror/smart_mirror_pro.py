# mirror/smart_mirror_pro.py
import sys
import os
import json
import subprocess
import time
import threading
import requests
import re
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QVBoxLayout, QHBoxLayout, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, QPoint, QSize, pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase, QPixmap, QMovie, QKeySequence

from config import *
try:
    from timing_config import GESTURE_TUTORIAL_IDLE_SEC, GESTURE_TUTORIAL_DURATION_SEC, GESTURE_TUTORIAL_SPEED_FACTOR
except ImportError:
    GESTURE_TUTORIAL_IDLE_SEC = 10.0
    GESTURE_TUTORIAL_DURATION_SEC = 5.6
    GESTURE_TUTORIAL_SPEED_FACTOR = 1.30

from widgets.notices_widget import NoticesWidget
from widgets.timetable_widget import TimetableWidget
from widgets.schedule_peek_widget import SchedulePeekWidget
from widgets.clock_widget import ClockWidget
from widgets.kings_week_widget import KingsWeekWidget
from telemetry import TelemetryTracker

API_URL = os.environ.get('API_URL', 'https://api.smartmirror.me')

REF_WIDTH  = 1280
REF_HEIGHT = 800
MIRROR_VERSION = "v1.2.0"

# Gesture regions, mirroring gesture_engine.py.
GESTURE_REGION_LEFT  = 'left'
GESTURE_REGION_RIGHT = 'right'

TIMETABLE_DISPLAY_MS = 10_000       # timetable holds 10s, then slides away to king's week
TIMETABLE_ANIM_MS    = 460
INDICATOR_BAR_WIDTH  = 4
INDICATOR_BAR_HEIGHT = 100

KINGS_IDLE_MS        = 20_000


# ─────────────────────────────────────────────────────────────────────────────
# Video player for gesture demo MP4 (QMediaPlayer with OpenCV fallback)
# ─────────────────────────────────────────────────────────────────────────────
class GestureVideoPlayer:
    """Video player for gesture_demo.mp4 rendering to QLabel so it fades smoothly with QGraphicsOpacityEffect."""

    def __init__(self, mp4_path, parent_widget, layout, target_size=(480, 480), speed_factor=None):
        self.mp4_path = mp4_path
        self.parent_widget = parent_widget
        self.layout = layout
        self.target_size = target_size
        self.player_type = 'cv'
        self.speed_factor = float(speed_factor) if speed_factor is not None else float(GESTURE_TUTORIAL_SPEED_FACTOR)

        # Render onto a transparent QLabel so QGraphicsOpacityEffect fades both background & video
        self.label = QLabel(parent_widget)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("background: transparent; border: none;")
        self.label.setFixedSize(target_size[0], target_size[1])
        layout.addWidget(self.label, alignment=Qt.AlignmentFlag.AlignCenter)
        self.widget = self.label

        self.cap = None
        self.cv_timer = QTimer(parent_widget)
        self.cv_timer.timeout.connect(self._cv_tick)
        self.fps = 30.0
        self.total_frames = 218
        self._detect_video_info()
        self._render_first_frame()

    def _detect_video_info(self):
        try:
            import cv2
            cap = cv2.VideoCapture(self.mp4_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.release()
            if fps > 0:
                self.fps = fps
            if count > 0:
                self.total_frames = count
        except Exception:
            pass

    def get_duration_ms(self):
        """Return video duration in milliseconds accounting for playback speed."""
        eff_fps = max(1.0, self.fps * getattr(self, 'speed_factor', 1.0))
        if eff_fps > 0 and self.total_frames > 0:
            return int((self.total_frames / eff_fps) * 1000)
        return int(GESTURE_TUTORIAL_DURATION_SEC * 1000)

    def _render_first_frame(self):
        try:
            import cv2
            from PyQt6.QtGui import QImage, QPixmap
            cap = cv2.VideoCapture(self.mp4_path)
            ret, frame = cap.read()
            cap.release()
            if ret and hasattr(self, 'label') and self.label is not None:
                # Fast SIMD downscale directly in OpenCV before allocating Qt image
                resized = cv2.resize(frame, (self.target_size[0], self.target_size[1]), interpolation=cv2.INTER_AREA)
                rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
                self.label.setPixmap(QPixmap.fromImage(qimg))
        except Exception:
            pass

    def start(self):
        try:
            import cv2
            if self.cap is None or not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.mp4_path)
            else:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            eff_fps = max(1.0, self.fps * getattr(self, 'speed_factor', 1.0))
            interval_ms = max(10, int(1000.0 / eff_fps))
            if self.cv_timer is not None:
                self.cv_timer.start(interval_ms)
        except Exception:
            pass

    def stop(self):
        if self.cv_timer is not None:
            self.cv_timer.stop()
        if self.cap is not None:
            try:
                import cv2
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            except Exception:
                pass

    def _cv_tick(self):
        if self.cap is None or not self.cap.isOpened():
            return
        try:
            import cv2
            from PyQt6.QtGui import QImage, QPixmap
            ret, frame = self.cap.read()
            if not ret:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
            if ret and hasattr(self, 'label') and self.label is not None:
                # Fast SIMD downscale directly in OpenCV avoiding expensive Qt SmoothTransformation
                resized = cv2.resize(frame, (self.target_size[0], self.target_size[1]), interpolation=cv2.INTER_AREA)
                rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
                self.label.setPixmap(QPixmap.fromImage(qimg))
        except Exception:
            pass



# ─────────────────────────────────────────────────────────────────────────────
# Main smart mirror window — clean 2-column layout matching web screenshot
# ─────────────────────────────────────────────────────────────────────────────
class SmartMirrorPro(QMainWindow):
    barcode_verified_signal = pyqtSignal(object, list, dict, bool, str)
    banner_fetched_signal = pyqtSignal(str)
    server_status_signal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Mirror")
        self.setStyleSheet("background-color: #000000;")

        # ── Server connectivity & offline state ──────────────────────────
        self.server_is_down = False
        self._admin_banner_msg = ""

        # ── Cross-thread signal connections ──────────────────────────────
        self.barcode_verified_signal.connect(self._on_barcode_verified)
        self.banner_fetched_signal.connect(self._update_banner)
        self.server_status_signal.connect(self._on_server_status_changed)

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

        # ── Floating Toast Overlay for Alerts / Barcode Scans ────────────
        self._build_toast()

        # ── Status dot ───────────────────────────────────────────────────
        self.status_dot = QLabel(self.central_widget)
        self.status_dot.setFixedSize(10, 10)
        self.status_dot.setStyleSheet("background: transparent; border-radius: 5px;")
        self.status_dot.hide()

        # ── Subtle version code in corner ────────────────────────────────
        self.version_lbl = QLabel(MIRROR_VERSION, self.central_widget)
        self.version_lbl.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 11px; font-weight: 600; "
            "color: #444444; background: transparent; letter-spacing: 0.5px;"
        )
        self.version_lbl.adjustSize()

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
        self.gesture_proc      = None
        self._transitioning    = False   # guard: ignore polls during fade
        self._anim_in          = None    # keep refs alive to prevent GC
        self._anim_out         = None

        # ── Physical barcode / student ID scanner input state ─────────────
        self._barcode_buffer = ""
        self._barcode_buffer_time = 0.0

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
        self._gesture_tutorial_idle_sec = GESTURE_TUTORIAL_IDLE_SEC
        self._gesture_tutorial_duration_sec = GESTURE_TUTORIAL_DURATION_SEC
        self._demo_anim = None
        self._scrim_timer = None
        self._scrim_fading_out = False

        # ── Telemetry & A/B Testing Tracker ───────────────────────────────
        self.telemetry = TelemetryTracker(api_url=API_URL)
        self.current_variant = "A"

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
        self.banner_frame.setFixedHeight(54)
        self.banner_frame.hide()

        lay = QHBoxLayout(self.banner_frame)
        lay.setContentsMargins(24, 6, 24, 6)
        lay.setSpacing(14)

        self.tag_lbl = QLabel("Notice", self.banner_frame)
        self.tag_lbl.setStyleSheet(
            'font-family: "Segoe UI", sans-serif; font-size: 14px; font-weight: 800; '
            'color: #ffffff; background-color: #dc2626; border-radius: 4px; padding: 4px 10px;'
        )
        lay.addWidget(self.tag_lbl)

        self.banner_label = QLabel(self.banner_frame)
        self.banner_label.setStyleSheet(
            'font-family: "Segoe UI", sans-serif; color: #ffffff; '
            'font-size: 18px; font-weight: 600;'
        )
        lay.addWidget(self.banner_label, 1)

    # ─────────────────────────────────────────────────────────────────────
    # Build: top horizontal indicator bar and header arrow indicator
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
        self.indicator_fill.setGeometry(0, 0, 0, 4)
        self.indicator_bar.setFixedHeight(4)
        self.indicator_bar.hide()

        # Indicator arrow in the header between date and clock (▲ / ▼)
        self.edge_arrow_label = QLabel("▲", self.central_widget)
        self.edge_arrow_label.setObjectName("EdgeArrow")
        self.edge_arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edge_arrow_label.setStyleSheet("""
            #EdgeArrow {
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 20px;
                font-weight: 700;
                color: #ffffff;
                background: transparent;
                border: none;
            }
        """)
        self.edge_arrow_label.setFixedSize(32, 32)
        self.edge_arrow_label.hide()

        # Variant B proactive dwell hint pill in header
        self.dwell_hint_pill = QLabel("✋ Hold hand in top-right for Timetable", self.central_widget)
        self.dwell_hint_pill.setObjectName("DwellHintPill")
        self.dwell_hint_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dwell_hint_pill.setStyleSheet("""
            #DwellHintPill {
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 13px;
                font-weight: 700;
                color: #e2e8f0;
                background: rgba(15, 23, 42, 0.88);
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 12px;
                padding: 4px 12px;
            }
        """)
        self.dwell_hint_pill.hide()

        # Barcode slot guidance indicator (points down to physical scanner slot)
        self.barcode_guide_pill = QLabel("💳 STUDENT ID SCANNER ⬇️  (Hold card steady in slot below)", self.central_widget)
        self.barcode_guide_pill.setObjectName("BarcodeGuidePill")
        self.barcode_guide_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.barcode_guide_pill.setStyleSheet("""
            #BarcodeGuidePill {
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 13px;
                font-weight: 700;
                color: #ffffff;
                background: rgba(9, 14, 23, 0.94);
                border: 1.5px solid #38bdf8;
                border-radius: 14px;
                padding: 6px 18px;
            }
        """)
        self.barcode_guide_pill.hide()

        # Variant B live floating on-screen hand cursor dot
        self.hand_cursor_dot = QLabel(self.central_widget)
        self.hand_cursor_dot.setObjectName("HandCursorDot")
        self.hand_cursor_dot.setFixedSize(28, 28)
        self.hand_cursor_dot.setStyleSheet("""
            #HandCursorDot {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 rgba(79, 195, 255, 0.95), stop:0.7 rgba(56, 189, 248, 0.8), stop:1 rgba(56, 189, 248, 0));
                border: 2px solid #ffffff;
                border-radius: 14px;
            }
        """)
        self.hand_cursor_dot.hide()

    def _update_barcode_guide(self):
        """Display visual arrow pointing down to physical barcode reader during guest/tutorial."""
        if not hasattr(self, 'barcode_guide_pill'):
            return
        is_guest = (getattr(self, '_last_state', 'idle') == 'guest')
        is_tutorial = (hasattr(self, 'gesture_demo_overlay') and self.gesture_demo_overlay is not None and self.gesture_demo_overlay.isVisible())
        
        if (is_guest or is_tutorial) and getattr(self, '_last_state', 'idle') != 'user':
            pill_w = 480
            pill_h = 38
            x = (self.width() - pill_w) // 2
            y = self.height() - pill_h - 24
            self.barcode_guide_pill.setGeometry(x, y, pill_w, pill_h)
            self.barcode_guide_pill.setText("💳 STUDENT ID SCANNER ⬇️  (Hold card steady in slot below)")
            self.barcode_guide_pill.show()
            self.barcode_guide_pill.raise_()
        else:
            self.barcode_guide_pill.hide()

    # ─────────────────────────────────────────────────────────────────────
    # Build: Floating Toast Notification
    # ─────────────────────────────────────────────────────────────────────
    def _build_toast(self):
        self.toast_frame = QFrame(self.central_widget)
        self.toast_frame.setObjectName("ToastFrame")
        self.toast_frame.setStyleSheet("""
            #ToastFrame {
                background: rgba(6, 78, 59, 0.95);
                border: 1px solid #10b981;
                border-radius: 22px;
            }
        """)
        t_lay = QHBoxLayout(self.toast_frame)
        t_lay.setContentsMargins(24, 8, 24, 8)
        self.toast_lbl = QLabel(self.toast_frame)
        self.toast_lbl.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 16px; font-weight: 700; color: #ffffff; background: transparent; border: none;")
        self.toast_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t_lay.addWidget(self.toast_lbl)
        self.toast_frame.hide()

    def show_toast(self, message, is_success=True, duration_ms=4500):
        """Display an unmistakable floating notification toast at top-center."""
        if is_success:
            self.toast_frame.setStyleSheet("""
                #ToastFrame {
                    background: rgba(6, 78, 59, 0.95);
                    border: 2px solid #10b981;
                    border-radius: 24px;
                }
            """)
            self.toast_lbl.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 18px; font-weight: 700; color: #ffffff; background: transparent; border: none;")
        else:
            self.toast_frame.setStyleSheet("""
                #ToastFrame {
                    background: rgba(127, 29, 29, 0.95);
                    border: 2px solid #ef4444;
                    border-radius: 24px;
                }
            """)
            self.toast_lbl.setStyleSheet("font-family: 'Segoe UI', system-ui, sans-serif; font-size: 18px; font-weight: 700; color: #ffffff; background: transparent; border: none;")

        self.toast_lbl.setText(message)
        self.toast_lbl.adjustSize()
        tw = max(380, self.toast_lbl.sizeHint().width() + 72)
        th = 48
        self.toast_frame.setGeometry((self.width() - tw) // 2, 24, tw, th)
        self.toast_frame.show()
        self.toast_frame.raise_()
        QTimer.singleShot(duration_ms, self.toast_frame.hide)


    # ─────────────────────────────────────────────────────────────────────
    # Build: gesture demo / inactivity darkened background scrim
    # ─────────────────────────────────────────────────────────────────────
    def _build_gesture_demo(self):
        self.gesture_demo_overlay = QWidget(self.central_widget)
        self.gesture_demo_overlay.setObjectName("GestureDemoOverlay")
        self.gesture_demo_overlay.setStyleSheet("background: rgba(0, 0, 0, 0.72);")

        lay = QVBoxLayout(self.gesture_demo_overlay)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        mp4_path = os.path.join(os.path.dirname(__file__), 'assets', 'gesture_demo.mp4')
        png_path = os.path.join(os.path.dirname(__file__), 'assets', 'gesture_demo.png')

        self.demo_movie = None
        self.demo_img_label = None

        if os.path.exists(mp4_path):
            self.demo_movie = GestureVideoPlayer(mp4_path, self.gesture_demo_overlay, lay, target_size=(480, 480))
            self.demo_img_label = self.demo_movie.widget
        elif os.path.exists(png_path):
            self.demo_img_label = QLabel(self.gesture_demo_overlay)
            self.demo_img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.demo_img_label.setStyleSheet("background: transparent; border: none;")
            pix = QPixmap(png_path)
            if not pix.isNull():
                self.demo_img_label.setPixmap(
                    pix.scaled(480, 480, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
            lay.addWidget(self.demo_img_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Variant B explicit anti-touchscreen warning (tackles the false glass-touching habit)
        self.demo_touchless_hint = QLabel(
            "❌ DO NOT TOUCH GLASS (Inert Screen)   •   ✔️ MOVE HAND IN AIR (30-40cm Away)",
            self.gesture_demo_overlay
        )
        self.demo_touchless_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.demo_touchless_hint.setStyleSheet("""
            font-family: 'Segoe UI', system-ui, sans-serif;
            font-size: 15px;
            font-weight: 800;
            color: #ffffff;
            background: rgba(10, 16, 28, 0.95);
            border: 2px solid #ef4444;
            border-radius: 20px;
            padding: 8px 24px;
            margin-top: 16px;
            letter-spacing: 0.5px;
        """)
        lay.addWidget(self.demo_touchless_hint, alignment=Qt.AlignmentFlag.AlignCenter)
        self.demo_touchless_hint.hide()

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
        self.kings_widget.clear_selection()

        self.user_container.hide()

    def _apply_user_layout(self, w, h):
        """Position user layout elements matching 50/50 split and vertical accordion."""
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

        split_h = int(content_h * 0.46)
        if getattr(self, '_timetable_full_mode', False) and not self._timetable_slid_away:
            self.timetable_widget.set_mode('full')
            self.timetable_widget.setGeometry(0, 0, content_w, content_h)
            self.timetable_widget.show()
            self.kings_widget.setGeometry(0, content_h, content_w, content_h)
        elif not self._timetable_slid_away:
            # Initial Split View
            self.timetable_widget.set_mode('compact')
            self.timetable_widget.setGeometry(0, 0, content_w, split_h)
            self.timetable_widget.show()
            self.kings_widget.setGeometry(0, split_h, content_w, content_h - split_h)
            self.kings_widget.show()
        else:
            # Timetable collapsed UP, King's Week expanded to full height
            self.timetable_widget.setGeometry(0, -split_h, content_w, split_h)
            self.kings_widget.setGeometry(0, 0, content_w, content_h)
            self.kings_widget.show()

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
        self.guest_kings_widget.clear_selection()

        # Right main: Centered smartmirror.me registration prompt (On top, slides away)
        self.guest_register_card = QWidget(self.guest_stack_container)
        self.guest_register_card.setObjectName('GuestRegisterCard')
        self.guest_register_card.setStyleSheet("background: #000000; border: none;")

        card_lay = QVBoxLayout(self.guest_register_card)
        card_lay.setContentsMargins(16, 16, 16, 16)
        card_lay.setSpacing(24)
        card_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Barcode status banner / headline in large bold typography
        self.guest_barcode_status_lbl = QLabel("Barcode Not Detected", self.guest_register_card)
        self.guest_barcode_status_lbl.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 40px; font-weight: 800; "
            "color: #fbbf24; background: transparent; border: none; letter-spacing: 0.5px;"
        )
        self.guest_barcode_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.guest_barcode_status_lbl.hide()
        card_lay.addWidget(self.guest_barcode_status_lbl)

        # Server status alert banner on guest screen
        self.guest_server_status_lbl = QLabel("Server is experiencing downtime", self.guest_register_card)
        self.guest_server_status_lbl.setWordWrap(True)
        self.guest_server_status_lbl.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 20px; font-weight: 800; "
            "color: #ef4444; background: transparent; border: none; letter-spacing: 0.5px; padding: 0 4px;"
        )
        self.guest_server_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.guest_server_status_lbl.hide()
        card_lay.addWidget(self.guest_server_status_lbl)

        # Domain title with clean prominence (fits column without cutoff)
        domain_lbl = QLabel("smartmirror.me", self.guest_register_card)
        domain_lbl.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 48px; font-weight: 900; "
            "color: #ffffff; background: transparent; border: none; letter-spacing: 1px;"
        )
        domain_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(domain_lbl)
        self.guest_domain_lbl = domain_lbl

        # Information text with increased size and readability
        info_lbl = QLabel(
            "Visit smartmirror.me to link your student ID barcode, register your face, and customize your timetable.",
            self.guest_register_card
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 24px; font-weight: 600; "
            "color: #f1f5f9; background: transparent; border: none; line-height: 1.5;"
        )
        info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(info_lbl)
        self.guest_info_lbl = info_lbl

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

        split_h = int(content_h * 0.46)
        if not self._guest_card_slid_away:
            self.guest_register_card.setGeometry(0, 0, content_w, split_h)
            self.guest_kings_widget.setGeometry(0, split_h, content_w, content_h - split_h)
            self.guest_register_card.show()
            self.guest_kings_widget.show()
        else:
            self.guest_register_card.setGeometry(0, -split_h, content_w, split_h)
            self.guest_kings_widget.setGeometry(0, 0, content_w, content_h)
            self.guest_kings_widget.show()

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

        if hasattr(self, 'version_lbl'):
            self.version_lbl.move(16, h - 22)
            self.version_lbl.raise_()

        if hasattr(self, 'gesture_demo_overlay') and self.gesture_demo_overlay is not None:
            self.gesture_demo_overlay.setGeometry(0, 0, w, h)

        # getattr: resizeEvent can fire while __init__ is still building.
        if getattr(self, '_peek_visible', False) and self.peek_container is not None:
            self.peek_container.setGeometry(self._peek_geometry())
            self._layout_peek_stage(animate=False)

        self._update_barcode_guide()

    # ─────────────────────────────────────────────────────────────────────
    # Banner polling & server status
    # ─────────────────────────────────────────────────────────────────────
    def _poll_banner(self):
        def worker():
            try:
                res = requests.get(f"{API_URL}/api/banner", timeout=4)
                if res.status_code == 200:
                    msg = res.json().get("message", "")
                    self.banner_fetched_signal.emit(msg)
                    self.server_status_signal.emit(True)
                else:
                    self.server_status_signal.emit(False)
            except Exception:
                self.server_status_signal.emit(False)
        threading.Thread(target=worker, daemon=True).start()

    def _on_server_status_changed(self, is_online):
        was_down = self.server_is_down
        self.server_is_down = not is_online
        if self.server_is_down:
            if not was_down:
                print("[MIRROR] Server detected as OFFLINE")
                if self._last_state in ('guest', 'user'):
                    self.show_toast("Server is experiencing downtime", is_success=False)
            self._update_offline_banner(True)
            if hasattr(self, 'guest_server_status_lbl'):
                self.guest_server_status_lbl.show()
        else:
            if was_down:
                print("[MIRROR] Server back ONLINE")
                self.show_toast("Server Connected", is_success=True)
            self._update_offline_banner(False)
            if hasattr(self, 'guest_server_status_lbl'):
                self.guest_server_status_lbl.hide()

    def _update_offline_banner(self, is_down):
        if is_down:
            if self._admin_banner_msg:
                self._update_banner(self._admin_banner_msg)
            else:
                self.banner_frame.hide()
        else:
            if self._admin_banner_msg:
                self._update_banner(self._admin_banner_msg)
            else:
                self.banner_frame.hide()
        # Re-apply layout in case banner height changed
        if hasattr(self, 'user_container') and not self.user_container.isHidden():
            self._apply_user_layout(self.width(), self.height())
        elif hasattr(self, 'guest_container') and not self.guest_container.isHidden():
            self._apply_guest_layout(self.width(), self.height())

    def _update_banner(self, message):
        self._admin_banner_msg = message or ""
        if message:
            self.tag_lbl.setText("Notice")
            self.tag_lbl.setStyleSheet(
                'font-family: "Segoe UI", sans-serif; font-size: 14px; font-weight: 800; '
                'color: #ffffff; background-color: #dc2626; border-radius: 4px; padding: 4px 10px;'
            )
            self.banner_label.setText(message)
            self.banner_label.setStyleSheet(
                'font-family: "Segoe UI", sans-serif; color: #ffffff; '
                'font-size: 18px; font-weight: 600;'
            )
            self.banner_frame.show()
            self.banner_frame.raise_()
        elif self.server_is_down:
            self._update_offline_banner(True)
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
        if getattr(self, 'gesture_proc', None) is not None:
            if self.gesture_proc.poll() is not None:
                ret = self.gesture_proc.returncode
                print(f"[MIRROR] Warning: Gesture daemon has exited (exit code {ret}). Check gesture_daemon.log for details.")
                self.gesture_proc = None

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
            target = self._momentum_target
            self._stop_momentum()
            if target is not None and hasattr(target, 'snap_to_nearest_box'):
                target.snap_to_nearest_box()
            return
        step = int(self._momentum_velocity)
        if step != 0 and hasattr(self._momentum_target, 'scroll_by_pixels'):
            self._momentum_target.scroll_by_pixels(step)
        self._momentum_velocity *= 0.90

    # ─────────────────────────────────────────────────────────────────────
    # Timetable & King's Week Layered Slide Transition
    # ─────────────────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────────────────
    # Timetable & King's Week Accordion Slide Transitions
    # ─────────────────────────────────────────────────────────────────────
    def _show_timetable(self, animate=True, is_initial_split=False):
        """Reveal the Timetable. If re-activated, expands to full schedule view."""
        if self.right_stack_container is None:
            return
        self.timetable_display_timer.stop()
        self._timetable_slid_away = False
        cw = self.right_stack_container.width()
        ch = self.right_stack_container.height()
        split_h = int(ch * 0.46)

        if self.kings_widget is not None and self.kings_widget.modal_open:
            self.kings_widget.close_modal(animate=False)

        if self._timetable_anim is not None:
            self._timetable_anim.stop()

        if is_initial_split:
            self._timetable_full_mode = False
            self.timetable_widget.set_mode('compact')
            self.timetable_widget.setGeometry(0, 0, cw, split_h)
            self.kings_widget.setGeometry(0, split_h, cw, ch - split_h)
            self.timetable_widget.show()
            self.kings_widget.show()
            self.timetable_widget.raise_()
            self.timetable_display_timer.start(TIMETABLE_DISPLAY_MS)
        else:
            self._timetable_full_mode = True
            self.timetable_widget.set_mode('full')
            self.timetable_widget.show()
            self.timetable_widget.raise_()

            if animate:
                anim_tt = QPropertyAnimation(self.timetable_widget, b"geometry", self)
                anim_tt.setDuration(TIMETABLE_ANIM_MS)
                anim_tt.setStartValue(QRect(0, -ch, cw, ch))
                anim_tt.setEndValue(QRect(0, 0, cw, ch))
                anim_tt.setEasingCurve(QEasingCurve.Type.OutCubic)

                anim_kw = QPropertyAnimation(self.kings_widget, b"geometry", self)
                anim_kw.setDuration(TIMETABLE_ANIM_MS)
                anim_kw.setStartValue(self.kings_widget.geometry())
                anim_kw.setEndValue(QRect(0, ch, cw, ch))
                anim_kw.setEasingCurve(QEasingCurve.Type.OutCubic)

                anim_tt.start()
                anim_kw.start()
                self._timetable_anim = anim_tt
                self._kings_anim = anim_kw
            else:
                self.timetable_widget.setGeometry(0, 0, cw, ch)
                self.kings_widget.setGeometry(0, ch, cw, ch)

            self.timetable_display_timer.start(TIMETABLE_DISPLAY_MS)

        self._update_arrow_indicator()

    def _slide_timetable_out(self, animate=True):
        """Slide Timetable UP, smoothly expanding King's Week to full column height."""
        if self.right_stack_container is None:
            return
        self.timetable_display_timer.stop()
        self._timetable_slid_away = True
        self._timetable_full_mode = False
        cw = self.right_stack_container.width()
        ch = self.right_stack_container.height()
        split_h = int(ch * 0.46)

        if self._timetable_anim is not None:
            self._timetable_anim.stop()

        target_tt_y = -ch if self.timetable_widget.height() > split_h else -split_h
        tt_h = self.timetable_widget.height()

        if animate:
            anim_tt = QPropertyAnimation(self.timetable_widget, b"geometry", self)
            anim_tt.setDuration(TIMETABLE_ANIM_MS)
            anim_tt.setStartValue(self.timetable_widget.geometry())
            anim_tt.setEndValue(QRect(0, -tt_h, cw, tt_h))
            anim_tt.setEasingCurve(QEasingCurve.Type.InOutCubic)

            anim_kw = QPropertyAnimation(self.kings_widget, b"geometry", self)
            anim_kw.setDuration(TIMETABLE_ANIM_MS)
            anim_kw.setStartValue(self.kings_widget.geometry())
            anim_kw.setEndValue(QRect(0, 0, cw, ch))
            anim_kw.setEasingCurve(QEasingCurve.Type.InOutCubic)
            anim_kw.finished.connect(self._update_arrow_indicator)

            anim_tt.start()
            anim_kw.start()
            self._timetable_anim = anim_tt
            self._kings_anim = anim_kw
        else:
            self.timetable_widget.setGeometry(0, -tt_h, cw, tt_h)
            self.kings_widget.setGeometry(0, 0, cw, ch)
            self._update_arrow_indicator()

        if self.kings_widget is not None and not self.kings_widget.has_content:
            self.kings_widget.refresh()

    def _show_guest_card(self, animate=True, is_initial_split=False):
        """Reveal the smartmirror.me suggestion card."""
        if self.guest_stack_container is None:
            return
        self.guest_display_timer.stop()
        self._guest_card_slid_away = False
        cw = self.guest_stack_container.width()
        ch = self.guest_stack_container.height()
        split_h = int(ch * 0.46)

        self.guest_register_card.show()
        self.guest_register_card.raise_()

        if hasattr(self, 'guest_kings_widget') and self.guest_kings_widget is not None and self.guest_kings_widget.modal_open:
            self.guest_kings_widget.close_modal(animate=False)

        if self._guest_card_anim is not None:
            self._guest_card_anim.stop()

        if is_initial_split:
            self.guest_register_card.setGeometry(0, 0, cw, split_h)
            self.guest_kings_widget.setGeometry(0, split_h, cw, ch - split_h)
            self.guest_kings_widget.show()
        else:
            if animate:
                anim_gc = QPropertyAnimation(self.guest_register_card, b"geometry", self)
                anim_gc.setDuration(TIMETABLE_ANIM_MS)
                anim_gc.setStartValue(self.guest_register_card.geometry())
                anim_gc.setEndValue(QRect(0, 0, cw, ch))
                anim_gc.setEasingCurve(QEasingCurve.Type.OutCubic)

                anim_kw = QPropertyAnimation(self.guest_kings_widget, b"geometry", self)
                anim_kw.setDuration(TIMETABLE_ANIM_MS)
                anim_kw.setStartValue(self.guest_kings_widget.geometry())
                anim_kw.setEndValue(QRect(0, ch, cw, ch))
                anim_kw.setEasingCurve(QEasingCurve.Type.OutCubic)

                anim_gc.start()
                anim_kw.start()
                self._guest_card_anim = anim_gc
            else:
                self.guest_register_card.setGeometry(0, 0, cw, ch)
                self.guest_kings_widget.setGeometry(0, ch, cw, ch)

        self._update_arrow_indicator()
        self.guest_display_timer.start(TIMETABLE_DISPLAY_MS)

    def _slide_guest_card_out(self, animate=True):
        """Slide the smartmirror.me card UP, expanding King's Week to full height."""
        if self.guest_stack_container is None:
            return
        self.guest_display_timer.stop()
        self._guest_card_slid_away = True
        cw = self.guest_stack_container.width()
        ch = self.guest_stack_container.height()
        split_h = int(ch * 0.46)
        gc_h = self.guest_register_card.height()

        if self._guest_card_anim is not None:
            self._guest_card_anim.stop()

        if animate:
            anim_gc = QPropertyAnimation(self.guest_register_card, b"geometry", self)
            anim_gc.setDuration(TIMETABLE_ANIM_MS)
            anim_gc.setStartValue(self.guest_register_card.geometry())
            anim_gc.setEndValue(QRect(0, -gc_h, cw, gc_h))
            anim_gc.setEasingCurve(QEasingCurve.Type.InOutCubic)

            anim_kw = QPropertyAnimation(self.guest_kings_widget, b"geometry", self)
            anim_kw.setDuration(TIMETABLE_ANIM_MS)
            anim_kw.setStartValue(self.guest_kings_widget.geometry())
            anim_kw.setEndValue(QRect(0, 0, cw, ch))
            anim_kw.setEasingCurve(QEasingCurve.Type.InOutCubic)
            anim_kw.finished.connect(self._update_arrow_indicator)

            anim_gc.start()
            anim_kw.start()
            self._guest_card_anim = anim_gc
        else:
            self.guest_register_card.setGeometry(0, -gc_h, cw, gc_h)
            self.guest_kings_widget.setGeometry(0, 0, cw, ch)
            self._update_arrow_indicator()

        if self.guest_kings_widget is not None and not self.guest_kings_widget.has_content:
            self.guest_kings_widget.refresh()

    def _update_arrow_indicator(self):
        """Show subtle arrow (▲) between date and clock in header ONLY when timetable/card is collapsed."""
        if not hasattr(self, 'edge_arrow_label') or self.edge_arrow_label is None:
            return

        is_active = self._last_state in ('user', 'guest')
        is_dwelling = hasattr(self, 'indicator_bar') and not self.indicator_bar.isHidden()

        if not is_active or is_dwelling:
            self.edge_arrow_label.hide()
            if hasattr(self, 'dwell_hint_pill'):
                self.dwell_hint_pill.hide()
            return

        # Arrow is ONLY shown when timetable or guest card is slid away (collapsed), never when visible
        if self._last_state == 'user':
            if not self._timetable_slid_away:
                self.edge_arrow_label.hide()
                if hasattr(self, 'dwell_hint_pill'):
                    self.dwell_hint_pill.hide()
                return
            self.edge_arrow_label.setText("▲")
        elif self._last_state == 'guest':
            if not self._guest_card_slid_away:
                self.edge_arrow_label.hide()
                if hasattr(self, 'dwell_hint_pill'):
                    self.dwell_hint_pill.hide()
                return
            self.edge_arrow_label.setText("▲")
        else:
            self.edge_arrow_label.hide()
            if hasattr(self, 'dwell_hint_pill'):
                self.dwell_hint_pill.hide()
            return

        w = self.width()
        left_w = int(w * 0.50)
        right_w = w - left_w
        content_x = left_w + 30
        content_w = right_w - 60
        top = self.banner_frame.height() if not self.banner_frame.isHidden() else 0

        # Position arrow centered in the header area between date and clock
        arrow_x = content_x + (content_w - 32) // 2
        arrow_y = top + 20 + (65 - 32) // 2
        self.edge_arrow_label.move(arrow_x, arrow_y)
        self.edge_arrow_label.show()
        self.edge_arrow_label.raise_()

        # Variant B: Show proactive dwell hint pill beneath arrow
        if getattr(self, 'current_variant', 'A') == 'B' and hasattr(self, 'dwell_hint_pill'):
            pill_w = 290
            pill_h = 28
            pill_x = content_x + (content_w - pill_w) // 2
            pill_y = arrow_y + 36
            self.dwell_hint_pill.setGeometry(pill_x, pill_y, pill_w, pill_h)
            self.dwell_hint_pill.setText("✋ Hold hand in top-right for Timetable")
            self.dwell_hint_pill.show()
            self.dwell_hint_pill.raise_()
        elif hasattr(self, 'dwell_hint_pill'):
            self.dwell_hint_pill.hide()

    def _show_gesture_scrim(self):
        """Darken the screen background slightly for the duration of the tutorial video and play demo MP4."""
        if self.gesture_demo_overlay is None:
            return
        if self.gesture_demo_overlay.isVisible() and not getattr(self, '_scrim_fading_out', False):
            return

        self._scrim_fading_out = False
        self.gesture_demo_overlay.setGeometry(0, 0, self.width(), self.height())
        effect = QGraphicsOpacityEffect(self.gesture_demo_overlay)
        self.gesture_demo_overlay.setGraphicsEffect(effect)
        effect.setOpacity(0.0)

        # Variant B explicit touchless banner beneath tutorial video
        if getattr(self, 'current_variant', 'A') == 'B' and hasattr(self, 'demo_touchless_hint'):
            self.demo_touchless_hint.show()
        elif hasattr(self, 'demo_touchless_hint'):
            self.demo_touchless_hint.hide()

        self.gesture_demo_overlay.show()
        self.gesture_demo_overlay.raise_()
        self._update_barcode_guide()

        if hasattr(self, 'demo_movie') and self.demo_movie is not None:
            self.demo_movie.start()

        anim_in = QPropertyAnimation(effect, b"opacity", self)
        anim_in.setDuration(450)
        anim_in.setStartValue(0.0)
        anim_in.setEndValue(1.0)
        anim_in.start()
        self._demo_anim = anim_in

        # Show for the length of the video (approx 7.27 seconds) or configured timing
        duration_ms = int(getattr(self, '_gesture_tutorial_duration_sec', GESTURE_TUTORIAL_DURATION_SEC) * 1000)
        if hasattr(self, 'demo_movie') and self.demo_movie is not None:
            d = self.demo_movie.get_duration_ms()
            if d > 0:
                duration_ms = d

        if hasattr(self, '_scrim_timer') and self._scrim_timer is not None:
            self._scrim_timer.stop()
        self._scrim_timer = QTimer(self)
        self._scrim_timer.setSingleShot(True)
        self._scrim_timer.timeout.connect(self._fade_out_gesture_scrim)
        self._scrim_timer.start(duration_ms)

    def _fade_out_gesture_scrim(self):
        """Smoothly fade out the tutorial overlay (background + video) to 0.0 opacity."""
        if not hasattr(self, 'gesture_demo_overlay') or self.gesture_demo_overlay is None:
            return
        if not self.gesture_demo_overlay.isVisible() or getattr(self, '_scrim_fading_out', False):
            return
        self._scrim_fading_out = True

        if hasattr(self, '_scrim_timer') and self._scrim_timer is not None:
            self._scrim_timer.stop()

        effect = self.gesture_demo_overlay.graphicsEffect()
        if effect is None:
            effect = QGraphicsOpacityEffect(self.gesture_demo_overlay)
            self.gesture_demo_overlay.setGraphicsEffect(effect)

        current_opacity = effect.opacity()
        anim_out = QPropertyAnimation(effect, b"opacity", self)
        anim_out.setDuration(int(450 * max(0.1, current_opacity)))
        anim_out.setStartValue(current_opacity)
        anim_out.setEndValue(0.0)

        def on_done():
            self.gesture_demo_overlay.hide()
            if hasattr(self, 'demo_touchless_hint'):
                self.demo_touchless_hint.hide()
            self._scrim_fading_out = False
            self._update_barcode_guide()
            if hasattr(self, 'demo_movie') and self.demo_movie is not None:
                self.demo_movie.stop()

        anim_out.finished.connect(on_done)
        anim_out.start()
        self._demo_anim = anim_out

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
        right_dwell = data.get("top_right_dwell_progress", data.get("right_dwell_progress", 0.0))
        dwell_side  = data.get("dwell_side") or ("top_right" if data.get("hand_x", 0.5) >= 0.5 else "left")
        notices     = self._active_notices()

        if present:
            self._last_interaction_time = time.time()

        # Variant B live floating on-screen hand cursor dot
        if getattr(self, 'current_variant', 'A') == 'B' and hasattr(self, 'hand_cursor_dot'):
            if present:
                hx = data.get("hand_x", 0.5)
                hy = data.get("hand_y", 0.5)
                dot_x = int(hx * self.width()) - 14
                dot_y = int(hy * self.height()) - 14
                self.hand_cursor_dot.move(dot_x, dot_y)
                self.hand_cursor_dot.show()
                self.hand_cursor_dot.raise_()
            else:
                self.hand_cursor_dot.hide()
        elif hasattr(self, 'hand_cursor_dot'):
            self.hand_cursor_dot.hide()

        # Telemetry: Record gesture events & dwell progress
        if hasattr(self, 'telemetry') and self.telemetry is not None:
            if event:
                self.telemetry.record_gesture(event_type=event, region=region)
            if right_dwell > 0:
                self.telemetry.record_dwell_progress(right_dwell)

        # Action gestures: clicking (tap/click), scrolling (scroll/fling with delta != 0)
        is_click_or_scroll = (
            event in ("tap", "click") or
            (event in ("scroll", "fling") and delta != 0)
        )

        if is_click_or_scroll:
            # Gesture tutorial idle time only counts and resets on active clicks or scrolls
            self._last_activity_time = time.time()
            # If user starts clicking/scrolling in the middle of demo, fade out smoothly
            self._fade_out_gesture_scrim()

        # ── Horizontal Top Indicator Bar on Edge Dwell (Top-Right Arm) ───
        if self._last_state in ('user', 'guest'):
            if right_dwell > 0.02 and dwell_side in ('top_right', 'right'):
                self._last_interaction_time = time.time()
                if hasattr(self, 'edge_arrow_label'):
                    self.edge_arrow_label.hide()

                w = self.width()
                left_w = int(w * 0.50)
                right_w = w - left_w
                content_x = left_w + 30
                content_w = right_w - 60
                top = self.banner_frame.height() if not self.banner_frame.isHidden() else 0
                bar_y = top + 86

                self.indicator_bar.setGeometry(content_x, bar_y, content_w, 4)
                fill_w = max(1, int(content_w * right_dwell))
                self.indicator_fill.setGeometry(0, 0, fill_w, 4)
                self.indicator_bar.show()
                self.indicator_bar.raise_()

                # In Variant B, display active percentage completion in the dwell pill
                if getattr(self, 'current_variant', 'A') == 'B' and hasattr(self, 'dwell_hint_pill'):
                    pct = int(right_dwell * 100)
                    self.dwell_hint_pill.setText(f"✋ Hold hand in top-right for Timetable ({pct}%)")
                    pill_w = 290
                    pill_h = 28
                    pill_x = content_x + (content_w - pill_w) // 2
                    pill_y = top + 20 + 36
                    self.dwell_hint_pill.setGeometry(pill_x, pill_y, pill_w, pill_h)
                    self.dwell_hint_pill.show()
                    self.dwell_hint_pill.raise_()
            else:
                self.indicator_bar.hide()
                self._update_arrow_indicator()
        else:
            self.indicator_bar.hide()
            if hasattr(self, 'dwell_hint_pill'):
                self.dwell_hint_pill.hide()

        # ── Handle Events (Right-side / Top-Right Dwell Toggle) ───────────
        dwell_filled = (right_dwell >= 0.98)
        dwell_trigger = (event in ("enter_top_right", "enter_right", "enter_dwell")) or (dwell_filled and not getattr(self, '_dwell_already_triggered', False))

        if right_dwell < 0.2:
            self._dwell_already_triggered = False

        # Resolve effective region cleanly so gestures near the center gutter are never dropped
        effective_region = region
        if effective_region not in (GESTURE_REGION_LEFT, GESTURE_REGION_RIGHT):
            hx = data.get("hand_x")
            if hx is not None:
                effective_region = GESTURE_REGION_LEFT if hx < 0.50 else GESTURE_REGION_RIGHT
            else:
                effective_region = region

        if dwell_trigger and self._last_state in ('user', 'guest'):
            self._last_activity_time = time.time()
            self._fade_out_gesture_scrim()
            self._dwell_already_triggered = True
            self.indicator_bar.hide()
            if hasattr(self, 'dwell_hint_pill'):
                self.dwell_hint_pill.hide()
            if hasattr(self, 'telemetry') and self.telemetry is not None:
                self.telemetry.record_timetable_toggle()
            if self._last_state == 'user':
                if self._timetable_slid_away:
                    self._show_timetable(animate=True, is_initial_split=False)
                else:
                    self._slide_timetable_out(animate=True)
            elif self._last_state == 'guest':
                if self._guest_card_slid_away:
                    self._show_guest_card(animate=True, is_initial_split=False)
                else:
                    self._slide_guest_card_out(animate=True)

        elif effective_region == GESTURE_REGION_LEFT and notices is not None:
            if event == "scroll" and delta != 0:
                self._stop_momentum()
                notices.scroll_by_pixels(delta)
            elif event == "fling" and delta != 0:
                self._start_momentum(notices, delta)
            elif event == "tap":
                self._stop_momentum()
                notices.toggle_scroll_pause()

        elif effective_region == GESTURE_REGION_RIGHT:
            active_target = None
            if self._last_state == 'user':
                if getattr(self, '_timetable_full_mode', False):
                    active_target = self.timetable_widget
                elif self._timetable_slid_away:
                    active_target = self.kings_widget
                else:
                    # Split view: if hand is in top half (y < 0.46), target timetable; else King's Week
                    hy = data.get("hand_y", 0.5)
                    if hy < 0.46 and hasattr(self, 'timetable_widget'):
                        active_target = self.timetable_widget
                    else:
                        active_target = self.kings_widget
            elif self._last_state == 'guest':
                if self._guest_card_slid_away or (hasattr(self, 'guest_kings_widget') and self.guest_kings_widget.y() < self.height()):
                    active_target = self.guest_kings_widget

            if active_target is not None:
                if event == "scroll" and delta != 0:
                    self._stop_momentum()
                    if hasattr(active_target, 'clear_selection'):
                        active_target.clear_selection()
                    if hasattr(active_target, 'scroll_by_pixels'):
                        active_target.scroll_by_pixels(delta)
                elif event == "fling" and delta != 0:
                    if hasattr(active_target, 'clear_selection'):
                        active_target.clear_selection()
                    self._start_momentum(active_target, delta)
                elif event == "tap":
                    self._stop_momentum()
                    if hasattr(active_target, 'modal_open') and active_target.modal_open:
                        active_target.close_modal()
                        if hasattr(self, 'telemetry') and self.telemetry is not None:
                            self.telemetry.record_modal_close()
                    elif hasattr(active_target, 'activate_selected'):
                        active_target.activate_selected()
                        if hasattr(self, 'telemetry') and self.telemetry is not None:
                            self.telemetry.record_modal_open()
                elif event not in ("scroll", "fling"):
                    if hasattr(active_target, 'focus_at'):
                        self._focus_kings_target(active_target, data)

        variant = getattr(self, 'current_variant', 'A')
        # Affordances: strictly mutually exclusive to prevent double highlighting
        if effective_region == GESTURE_REGION_LEFT:
            if notices is not None:
                notices.set_gesture_active(True, variant=variant)
            if self.kings_widget is not None:
                self.kings_widget.set_gesture_active(False, variant=variant)
            if hasattr(self, 'guest_kings_widget') and self.guest_kings_widget is not None:
                self.guest_kings_widget.set_gesture_active(False, variant=variant)
        elif effective_region == GESTURE_REGION_RIGHT:
            if notices is not None:
                notices.set_gesture_active(False, variant=variant)
            if self.kings_widget is not None:
                self.kings_widget.set_gesture_active(
                    self._last_state == 'user' and (self._timetable_slid_away or getattr(self.kings_widget, 'isVisible', lambda: True)()),
                    variant=variant
                )
            if hasattr(self, 'guest_kings_widget') and self.guest_kings_widget is not None:
                self.guest_kings_widget.set_gesture_active(
                    self._last_state == 'guest' and (self._guest_card_slid_away or self.guest_kings_widget.y() < self.height()),
                    variant=variant
                )
        else:
            if notices is not None:
                notices.set_gesture_active(False, variant=variant)
            if self.kings_widget is not None:
                self.kings_widget.set_gesture_active(False, variant=variant)
            if hasattr(self, 'guest_kings_widget') and self.guest_kings_widget is not None:
                self.guest_kings_widget.set_gesture_active(False, variant=variant)


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
        # ── 5-Minute Inactivity Auto Logout for Barcode Sessions ─────────
        if self._last_state == 'user' and getattr(self, '_auth_method', '') == 'barcode' and not self._transitioning:
            if (time.time() - getattr(self, '_barcode_auth_time', time.time()) >= 300.0) or (time.time() - self._last_interaction_time >= 300.0):
                print("[BARCODE] 5-minute session expired. Auto logging out to guest.")
                self.show_toast("Session Expired — Auto Logged Out", is_success=False)
                self._auth_method = ""
                self.face_recognized = False
                self.current_user_id = None
                self._last_state = 'guest'
                self._last_user_id = None
                self._trigger_transition('guest', None, {'state': 'guest'})
                return

        now = time.time()
        file_valid = False
        fdata = {}
        if os.path.exists(FACE_DATA_FILE):
            try:
                with open(FACE_DATA_FILE) as f:
                    fdata = json.load(f)
                stamp = fdata.get('timestamp', 0.0)
                # Stale daemon check: if file is newer than 4.0 seconds, consider face status live
                if now - stamp <= 4.0:
                    file_valid = True
            except Exception:
                pass

            if file_valid:
                if "server_online" in fdata:
                    self.server_status_signal.emit(bool(fdata["server_online"]))

                self.face_detected   = fdata.get('detected', False)
                self.face_recognized = fdata.get('recognized', False)
                self.face_confidence = fdata.get('confidence', 0.0)
                self.in_grace        = fdata.get('in_grace', False)

                new_state   = fdata.get('state', 'idle')
                new_user_id = fdata.get('user_id', 'idle')
                daemon_auth = fdata.get('auth_method', '')
                if daemon_auth:
                    self._auth_method = daemon_auth
            else:
                self.face_detected   = False
                self.face_recognized = False
                self.face_confidence = 0.0
                self.in_grace        = False
                new_state   = 'idle'
                new_user_id = 'idle'

            # ── Barcode Session Lock: Active barcode session overrides face 'idle'/'guest' ──
            if self._last_state == 'user' and getattr(self, '_auth_method', '') == 'barcode':
                if new_state in ('idle', 'guest'):
                    new_state = 'user'
                    new_user_id = self.current_user_id

            # Hold guest screen for at least 15s after a barcode scan attempt
            if self._last_state == 'guest' and getattr(self, '_last_barcode_scan_time', 0) > 0:
                if now - self._last_barcode_scan_time < 15.0:
                    if new_state == 'idle':
                        new_state = 'guest'
                        new_user_id = 'guest'

            state_changed = (new_state != self._last_state)
            user_switched = (
                new_state == 'user'
                and new_user_id != self._last_user_id
                and new_user_id not in ('', 'idle')
            )

            # ── Guard: Don't interrupt active interactions IF face is actually detected ─────
            # Gestures alone without a face must never hold the mirror from fading to idle.
            is_interacting = (
                self.face_detected and (
                    (now - self._last_interaction_time < 6.0)
                    or (self.kings_widget and self.kings_widget.modal_open)
                    or (hasattr(self, 'guest_kings_widget') and self.guest_kings_widget and self.guest_kings_widget.modal_open)
                    or (self.indicator_bar and not self.indicator_bar.isHidden())
                )
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
                    self._last_activity_time = now
                    self._trigger_transition(new_state, new_user_id, fdata)
            elif (state_changed or user_switched) and not self._transitioning:
                self._transitioning = True
                self._last_state    = new_state
                self._last_user_id  = new_user_id
                self.current_user_id   = new_user_id
                self.current_user_name = fdata.get('user_name', '')
                self._last_activity_time = now
                self._trigger_transition(new_state, new_user_id, fdata)

        # ── Gesture Inactivity Tutorial Overlay ───────────────────────────
        if self._last_state in ('guest', 'user') and not self._transitioning:
            idle_threshold = getattr(self, '_gesture_tutorial_idle_sec', GESTURE_TUTORIAL_IDLE_SEC)
            if time.time() - self._last_activity_time >= idle_threshold:
                if not getattr(self, '_scrim_fading_out', False) and (self.gesture_demo_overlay is None or not self.gesture_demo_overlay.isVisible()):
                    self._last_activity_time = time.time()
                    self._show_gesture_scrim()

        # Status dot
        if self.face_recognized:
            self.status_dot.setStyleSheet("background: #00c850; border-radius: 5px;")
            self.status_dot.show()
        elif self.server_is_down and self._last_state in ('guest', 'user'):
            self.status_dot.setStyleSheet("background: #ef4444; border-radius: 5px;")
            self.status_dot.show()
        elif self.in_grace:
            self.status_dot.setStyleSheet("background: #ff9600; border-radius: 5px;")
            self.status_dot.show()
        else:
            self.status_dot.hide()

    def _trigger_transition(self, new_state, new_user_id, fdata):
        """Dissolve from whatever is on screen to the new state."""
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

        self._hide_timetable_peek(animate=False)
        self.notices_widget.reset_gesture_state()
        self.guest_notices.reset_gesture_state()
        if self.kings_widget is not None:
            self.kings_widget.reset_gesture_state()
            self.kings_widget.clear_selection()
        if hasattr(self, 'guest_kings_widget') and self.guest_kings_widget is not None:
            self.guest_kings_widget.reset_gesture_state()
            self.guest_kings_widget.clear_selection()

        is_from_idle = (visible is None)

        if incoming is not None and incoming is visible:
            self._prepare(incoming, new_state, new_user_id, fdata)
            self._update_arrow_indicator()
            self._transitioning = False
            return

        if visible is not None:
            visible.setGraphicsEffect(None)
            visible.lower()

        if incoming is not None:
            # Telemetry: Begin tracked session and assign A/B experiment variant
            auth = getattr(self, '_auth_method', '') or fdata.get('auth_method', '')
            if not auth:
                auth = 'face' if new_state == 'user' else 'presence'

            if incoming is not visible and hasattr(self, 'telemetry') and self.telemetry is not None:
                self.current_variant = self.telemetry.start_session(session_type=new_state, auth_method=auth)
            elif hasattr(self, 'telemetry') and self.telemetry is not None and self.telemetry.current_session:
                self.telemetry.update_auth_method(auth)

            self._prepare(incoming, new_state, new_user_id, fdata)
            self._fade_in(incoming, retire=visible)
            if is_from_idle and new_state == 'guest':
                self._show_gesture_scrim()

        elif visible is not None:
            self._fade_out(visible, on_done=self._on_fade_to_idle_done)

        else:
            self._transitioning = False

    def _prepare(self, container, new_state, new_user_id, fdata):
        """Fill in and lay out a container before it is displayed."""
        if container is self.user_container:
            self.timetable_widget.set_user_id(new_user_id)
            self._apply_user_theme(fdata.get('config', {}))
            self._apply_user_layout(self.width(), self.height())
            self._show_timetable(animate=False, is_initial_split=True)
        else:
            self.timetable_widget.set_user_id('')
            self._apply_guest_layout(self.width(), self.height())
            if not fdata.get('barcode_failed', False):
                if hasattr(self, 'guest_barcode_status_lbl'):
                    self.guest_barcode_status_lbl.hide()
            if hasattr(self, 'guest_server_status_lbl'):
                if self.server_is_down:
                    self.guest_server_status_lbl.show()
                else:
                    self.guest_server_status_lbl.hide()
            self._show_guest_card(animate=False, is_initial_split=True)
        self._update_arrow_indicator()
        self._update_barcode_guide()

    def _on_fade_to_idle_done(self):
        if hasattr(self, 'telemetry') and self.telemetry is not None:
            self.telemetry.end_session()
        self._auth_method = ""
        self.user_container.hide()
        self.guest_container.hide()
        self.user_container.setGraphicsEffect(None)
        self.guest_container.setGraphicsEffect(None)
        if hasattr(self, 'dwell_hint_pill'):
            self.dwell_hint_pill.hide()
        if hasattr(self, 'gesture_demo_overlay') and self.gesture_demo_overlay is not None:
            self.gesture_demo_overlay.hide()
            if hasattr(self, 'demo_movie') and self.demo_movie is not None:
                self.demo_movie.stop()
        if self.kings_widget is not None:
            self.kings_widget.clear_selection()
        if hasattr(self, 'guest_kings_widget') and self.guest_kings_widget is not None:
            self.guest_kings_widget.clear_selection()
        self._update_barcode_guide()
        self._transitioning = False

    def closeEvent(self, event):
        if hasattr(self, 'telemetry') and self.telemetry is not None:
            self.telemetry.end_session()
        super().closeEvent(event)

    # ─────────────────────────────────────────────────────────────────────
    # Hardware Barcode Scanner & Keyboard / Paste Input
    # ─────────────────────────────────────────────────────────────────────
    def keyPressEvent(self, event):
        # Support Paste shortcuts (Ctrl+V / Shift+Insert)
        if event.matches(QKeySequence.StandardKey.Paste):
            clipboard = QApplication.clipboard()
            if clipboard:
                text = clipboard.text()
                if text:
                    self._on_barcode_scanned(text)
                    return

        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            code = self._barcode_buffer.strip()
            self._barcode_buffer = ""
            if code:
                self._on_barcode_scanned(code)
            return

        if key == Qt.Key.Key_Escape:
            self._barcode_buffer = ""
            return

        if key == Qt.Key.Key_Backspace:
            self._barcode_buffer = self._barcode_buffer[:-1]
            return

        # Regular characters typed by barcode reader or user
        text = event.text()
        if text:
            # If there's an embedded newline in pasted text
            if '\n' in text or '\r' in text:
                full_text = (self._barcode_buffer + text).strip()
                self._barcode_buffer = ""
                if full_text:
                    self._on_barcode_scanned(full_text)
                return

            now = time.time()
            if now - self._barcode_buffer_time > 3.0:
                self._barcode_buffer = ""
            self._barcode_buffer += text
            self._barcode_buffer_time = now

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self._last_activity_time = time.time()
        self._last_interaction_time = time.time()
        self._fade_out_gesture_scrim()

    def wheelEvent(self, event):
        super().wheelEvent(event)
        self._last_activity_time = time.time()
        self._last_interaction_time = time.time()
        self._fade_out_gesture_scrim()

    def _on_barcode_scanned(self, raw_code):
        """Process scanned/pasted student ID barcode."""
        if not raw_code:
            return
        code = str(raw_code).strip().upper()
        code = re.sub(r'[\r\n\t ]+', '', code)
        if not code:
            return

        print(f"[BARCODE] Scanned barcode: {code}")
        self._last_barcode_scan_time = time.time()
        self._last_interaction_time = time.time()
        self._last_activity_time = time.time()

        def worker():
            urls = [API_URL]
            if "localhost" not in API_URL and "127.0.0.1" not in API_URL:
                urls.extend(["http://localhost:8080", "http://127.0.0.1:8080"])

            for base_url in urls:
                try:
                    res = requests.post(
                        f"{base_url}/api/verify-barcode",
                        json={"barcode": code},
                        timeout=3.0
                    )
                    if res.status_code == 200:
                        data = res.json()
                        user_id = data.get("user_id") or data.get("student_id") or code
                        widgets = data.get("widgets", [])
                        config = data.get("config", {})
                        self.barcode_verified_signal.emit(user_id, widgets, config, True, code)
                        return
                    elif res.status_code in (400, 404):
                        print(f"[BARCODE] Verify failed (status {res.status_code}: Student ID not recognized) for code: {code}")
                        break
                    else:
                        print(f"[BARCODE] Verify failed (status {res.status_code}) at {base_url} for code: {code}")
                except Exception as e:
                    print(f"[BARCODE] Verify error at {base_url}: {e}")

            self.barcode_verified_signal.emit(None, [], {}, False, code)

        threading.Thread(target=worker, daemon=True).start()

    def _write_face_data(self, data):
        try:
            target_dir = os.path.dirname(os.path.abspath(FACE_DATA_FILE))
            tmp = os.path.join(target_dir, f'face_status.mirror_{os.getpid()}.tmp')
            with open(tmp, 'w') as f:
                json.dump(data, f)
            for attempt in range(3):
                try:
                    os.replace(tmp, FACE_DATA_FILE)
                    break
                except PermissionError:
                    time.sleep(0.005)
        except Exception as e:
            pass

    def _on_barcode_verified(self, user_id, widgets, config, success, code=""):
        """Apply verification outcome: switch to user dashboard or show guest screen."""
        self._last_barcode_scan_time = time.time()
        self._last_interaction_time = time.time()
        self._last_activity_time = time.time()

        if success and user_id:
            # If same barcode is scanned while logged in -> LOG OUT
            if self._last_state == 'user' and self.current_user_id == user_id:
                print(f"[BARCODE] Same barcode scanned for {user_id}. Logging out.")
                self.show_toast(f"✓ Logged Out: {user_id}", is_success=True)
                self._auth_method = ""
                self.face_recognized = False
                self.current_user_id = None
                target_state = 'guest' if self.face_detected else 'idle'
                self._last_state = target_state
                self._last_user_id = None
                self._write_face_data({
                    "state": target_state,
                    "user_id": target_state,
                    "recognized": False,
                    "detected": bool(self.face_detected),
                    "auth_method": "",
                    "timestamp": time.time(),
                })
                self._trigger_transition(target_state, None, {'state': target_state})
                return

            print(f"[BARCODE] Sign-in accepted for {user_id}")
            self._auth_method = "barcode"
            self._barcode_auth_time = time.time()
            if hasattr(self, 'telemetry') and self.telemetry is not None:
                if self.telemetry.current_session:
                    self.telemetry.update_auth_method("barcode")
                else:
                    self.current_variant = self.telemetry.start_session(session_type="user", auth_method="barcode")

            fdata = {
                "state": "user",
                "user_id": user_id,
                "user_name": user_id,
                "widgets": widgets,
                "config": config,
                "recognized": True,
                "detected": True,
                "auth_method": "barcode",
                "timestamp": time.time(),
            }
            self._write_face_data(fdata)
            self.face_detected = True
            self.face_recognized = True
            self.current_user_id = user_id
            self.current_user_name = user_id
            self._last_state = 'user'
            self._last_user_id = user_id
            self._update_barcode_guide()
            self._trigger_transition('user', user_id, fdata)
            self._show_timetable(animate=True, is_initial_split=True)
        else:
            print(f"[BARCODE] Barcode {code} not recognized / not linked. Showing guest screen.")
            self.show_toast(f"ID Not Recognized: {code or 'Unknown'}", is_success=False)
            if hasattr(self, 'guest_barcode_status_lbl'):
                self.guest_barcode_status_lbl.setText("ID Not Recognized")
                self.guest_barcode_status_lbl.show()

            fdata = {
                "state": "guest",
                "user_id": "guest",
                "recognized": False,
                "detected": True,
                "barcode_failed": True,
                "timestamp": time.time(),
            }
            self._write_face_data(fdata)
            self._auth_method = ""
            self._update_barcode_guide()
            if self._last_state != 'guest':
                self._last_state = 'guest'
                self._last_user_id = 'guest'
                self._trigger_transition('guest', None, fdata)
            else:
                self._show_guest_card(animate=True, is_initial_split=True)


# ─────────────────────────────────────────────────────────────────────────────
def _get_cli_camera():
    for i, arg in enumerate(sys.argv):
        if arg == '--camera-id' and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def _is_rpi_cli():
    return '--rpi' in sys.argv or sys.platform.startswith('linux')


def start_face_daemon():
    """Launch face_recognize.py alongside the UI, and return the process.

    Set MIRROR_FACE_DAEMON=0 to opt out (e.g. if running the face daemon externally).
    If a face daemon is already running and publishing fresh heartbeats to
    face_status.json, this gracefully detects it and avoids starting a duplicate.
    """
    if os.environ.get('MIRROR_FACE_DAEMON', '1') == '0':
        print('[MIRROR] MIRROR_FACE_DAEMON=0 — not starting the face daemon.')
        return None

    if os.path.exists(FACE_DATA_FILE):
        try:
            with open(FACE_DATA_FILE) as f:
                data = json.load(f)
            if time.time() - data.get('timestamp', 0.0) < 2.5:
                print('[MIRROR] Face daemon is already running externally.')
                return None
        except Exception:
            pass

    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'face_recognize.py')
    camera = os.environ.get('MIRROR_CAMERA_INDEX') or _get_cli_camera()
    if camera is None:
        args = ['--rpi'] if _is_rpi_cli() else ['--camera-id', '0']
    else:
        args = ['--camera-id', str(camera)]
    args.append('--exit-with-parent')

    try:
        proc = subprocess.Popen([sys.executable, '-u', script] + args,
                                stdin=subprocess.PIPE)
        print(f'[MIRROR] Face recognition daemon started (pid {proc.pid}, {" ".join(args)}).')
        return proc
    except Exception as e:
        print(f'[MIRROR] Could not start the face recognition daemon: {e}')
        return None


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
    camera = os.environ.get('GESTURE_CAMERA') or _get_cli_camera()
    if camera is None:
        args = ['--rpi'] if _is_rpi_cli() else ['--camera-id', '0']
    else:
        args = ['--camera-id', str(camera)]
    args.append('--exit-with-parent')

    try:
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gesture_daemon.log')
        log_f = open(log_path, 'a', encoding='utf-8')
        proc = subprocess.Popen([sys.executable, '-u', script] + args,
                                stdin=subprocess.PIPE,
                                stdout=log_f,
                                stderr=subprocess.STDOUT)
        print(f'[MIRROR] Gesture daemon started (pid {proc.pid}, {" ".join(args)}). Logs: {log_path}')
        return proc
    except Exception as e:
        # A mirror with no gestures is still a working mirror, so this is never
        # allowed to stop the UI from coming up.
        print(f'[MIRROR] Could not start the gesture daemon: {e}')
        return None


if __name__ == '__main__':
    app = QApplication(sys.argv)
    face_proc = start_face_daemon()
    gestures = start_gesture_daemon()
    mirror = SmartMirrorPro()
    mirror.gesture_proc = gestures
    mirror.show()
    try:
        code = app.exec()
    finally:
        for p in (face_proc, gestures):
            if p is not None and p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()
    sys.exit(code)

