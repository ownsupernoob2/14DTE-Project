# mirror/smart_mirror_pro.py
import sys
import os
import json
import time
import threading
import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QVBoxLayout, QHBoxLayout, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect
from PyQt6.QtGui import QFont, QFontDatabase

from config import *
from widgets.notices_widget import NoticesWidget
from widgets.timetable_widget import TimetableWidget
from widgets.schedule_peek_widget import SchedulePeekWidget
from widgets.clock_widget import ClockWidget
from widgets.kings_week_widget import KingsWeekWidget

API_URL = os.environ.get('API_URL', 'https://api.smartmirror.me')
REF_WIDTH  = 1280
REF_HEIGHT = 800

# Gesture regions, mirroring gesture_engine.py. Duplicated as literals rather
# than imported so this process never pulls in cv2/mediapipe.
GESTURE_REGION_LEFT  = 'left'
GESTURE_REGION_RIGHT = 'right'

# Timetable peek: how long the panel stays up, how wide it is, and its slide.
PEEK_VISIBLE_MS  = 10_000
PEEK_WIDTH_FRAC  = 0.42
PEEK_MIN_WIDTH   = 360
PEEK_ANIM_IN_MS  = 420
PEEK_ANIM_OUT_MS = 380


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

        # ── Timetable peek (right-side gesture) ───────────────────────────
        self.peek_panel     = None       # built lazily on first peek
        self._peek_visible  = False
        self._peek_anim     = None

        self.peek_timer = QTimer(self)
        self.peek_timer.setSingleShot(True)
        self.peek_timer.timeout.connect(self._hide_timetable_peek)

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
    # Build: user layout (matching web screenshot: 34% / 66% 2-column)
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

        # Right main: Timetable Class Focus block
        self.timetable_widget = TimetableWidget(
            api_url=API_URL, parent=self.user_container
        )

        self.user_container.hide()

    def _apply_user_layout(self, w, h):
        """Position user layout elements matching web screenshot."""
        banner_h = self.banner_frame.height() if not self.banner_frame.isHidden() else 0
        top = banner_h

        self.user_container.setGeometry(0, top, w, h - top)

        left_w = int(w * 0.34)
        right_w = w - left_w

        # Left column: Notices (with vertical right border)
        self.notices_widget.setGeometry(0, 0, left_w, h - top)

        # Right top: Clock row
        self.clock_widget.setGeometry(left_w + 34, 20, right_w - 68, 65)

        # Right main: Timetable Class Focus
        self.timetable_widget.setGeometry(left_w + 34, 90, right_w - 68, h - top - 100)



    # ─────────────────────────────────────────────────────────────────────
    # Build: guest layout (clock + notices + onboarding)
    # ─────────────────────────────────────────────────────────────────────
    def _build_guest_layout(self):
        self.guest_container = QWidget(self.central_widget)
        self.guest_container.setStyleSheet("background: #000000;")

        # Left: notices panel
        self.guest_notices = NoticesWidget(api_url=API_URL, parent=self.guest_container)

        # Right top: clock
        self.guest_clock = ClockWidget(parent=self.guest_container)

        # Right bottom hint strip
        self.guest_hint = QFrame(self.guest_container)
        self.guest_hint.setObjectName('GuestHint')
        self.guest_hint.setStyleSheet("""
            #GuestHint {
                background: rgba(96, 165, 250, 0.08);
                border: 1px solid rgba(96, 165, 250, 0.18);
                border-radius: 0px;
            }
        """)
        h_lay = QHBoxLayout(self.guest_hint)
        h_lay.setContentsMargins(24, 0, 24, 0)

        hint_icon = QLabel('◎', self.guest_hint)
        hint_icon.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 16px; "
            "color: #60a5fa; background: transparent; border: none;"
        )
        h_lay.addWidget(hint_icon)

        title = QLabel('STAND IN FRONT OF THE MIRROR TO IDENTIFY YOURSELF', self.guest_hint)
        title.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 12px; font-weight: 700; "
            "color: #60a5fa; letter-spacing: 2px; background: transparent; border: none;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_lay.addWidget(title, 1)

        self.guest_container.hide()

    def _apply_guest_layout(self, w, h):
        """Position guest layout elements."""
        banner_h = self.banner_frame.height() if not self.banner_frame.isHidden() else 0
        top = banner_h

        self.guest_container.setGeometry(0, top, w, h - top)

        left_w = int(w * 0.34)
        right_w = w - left_w

        self.guest_notices.setGeometry(0, 0, left_w, h - top)
        self.guest_clock.setGeometry(left_w + 34, 20, right_w - 68, 65)
        self.guest_hint.setGeometry(left_w + 34, h - top - 70, right_w - 68, 50)

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
        if getattr(self, '_peek_visible', False) and self.peek_panel is not None:
            self.peek_panel.setGeometry(self._peek_geometry())

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

    def _handle_gesture(self, data):
        if self._last_state == 'idle' or self._last_state is None:
            return

        present = data.get("present", False)
        region  = data.get("region") if present else None
        event   = data.get("event")

        # Affordance first, so the panel lights up as soon as the hand arrives —
        # before the student has done anything with it.
        notices = self._active_notices()
        if notices is not None:
            notices.set_gesture_active(region == GESTURE_REGION_LEFT)

        if not event:
            return

        if region == GESTURE_REGION_LEFT and notices is not None:
            if event == "scroll":
                delta = data.get("scroll_delta", 0)
                if delta:
                    notices.scroll_by_pixels(delta)
            elif event == "tap":
                notices.toggle_scroll_pause()

        elif region == GESTURE_REGION_RIGHT:
            if event == "enter_right":
                self._show_timetable_peek()
            elif event == "tap" and self._peek_visible:
                # Tap to dismiss early instead of waiting out the 10 seconds.
                self._hide_timetable_peek()

    # ─────────────────────────────────────────────────────────────────────
    # Timetable peek panel
    # ─────────────────────────────────────────────────────────────────────
    def _ensure_peek(self):
        if self.peek_panel is None:
            self.peek_panel = SchedulePeekWidget(
                parent=self.central_widget,
                api_url=API_URL,
                user_id=self.current_user_id or '',
            )
            self.peek_panel.hide()
        return self.peek_panel

    def _peek_geometry(self, offscreen=False):
        w, h = self.width(), self.height()
        banner_h = self.banner_frame.height() if not self.banner_frame.isHidden() else 0
        panel_w = max(PEEK_MIN_WIDTH, int(w * PEEK_WIDTH_FRAC))
        x = w if offscreen else w - panel_w
        return QRect(x, banner_h, panel_w, h - banner_h)

    def _show_timetable_peek(self):
        if self._last_state in (None, 'idle'):
            return

        panel = self._ensure_peek()
        # set_user_id only refetches when the user actually changed, so ask for a
        # refresh ourselves otherwise — the panel is up for 10s and should be current.
        if not panel.set_user_id(self.current_user_id or ''):
            panel.refresh()

        if self._peek_visible:
            # Already up; a second dwell just buys another 10 seconds.
            self.peek_timer.start(PEEK_VISIBLE_MS)
            return

        self._peek_visible = True
        start, end = self._peek_geometry(offscreen=True), self._peek_geometry()
        panel.setGeometry(start)
        panel.show()
        panel.raise_()

        anim = QPropertyAnimation(panel, b"geometry", self)
        anim.setDuration(PEEK_ANIM_IN_MS)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._peek_anim = anim

        self.peek_timer.start(PEEK_VISIBLE_MS)

    def _hide_timetable_peek(self, animate=True):
        """Slide the panel back out to the right (or drop it instantly)."""
        self.peek_timer.stop()
        if not self._peek_visible or self.peek_panel is None:
            return
        self._peek_visible = False
        panel = self.peek_panel

        if not animate:
            panel.hide()
            return

        anim = QPropertyAnimation(panel, b"geometry", self)
        anim.setDuration(PEEK_ANIM_OUT_MS)
        anim.setStartValue(panel.geometry())
        anim.setEndValue(self._peek_geometry(offscreen=True))
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(panel.hide)
        anim.start()
        self._peek_anim = anim

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
        visible = None
        if not self.user_container.isHidden():
            visible = self.user_container
        elif not self.guest_container.isHidden():
            visible = self.guest_container

        def apply_new():
            # The peek belongs to whoever was just on screen — drop it outright
            # rather than sliding it out over a different student's dashboard.
            self._hide_timetable_peek(animate=False)
            self.notices_widget.reset_gesture_state()
            self.guest_notices.reset_gesture_state()

            self.user_container.hide()
            self.guest_container.hide()
            if visible:
                visible.setGraphicsEffect(None)

            if new_state == 'user' and new_user_id not in ('', 'idle'):
                self.timetable_widget.set_user_id(new_user_id)
                if self.peek_panel is not None:
                    self.peek_panel.set_user_id(new_user_id)
                self._apply_user_theme(fdata.get('config', {}))
                self._apply_user_layout(self.width(), self.height())
                self._fade_in(self.user_container)

            elif new_state == 'guest':
                self.timetable_widget.set_user_id('')
                if self.peek_panel is not None:
                    self.peek_panel.set_user_id('')
                self._apply_guest_layout(self.width(), self.height())
                self._fade_in(self.guest_container)

            else:  # idle
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

