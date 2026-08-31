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
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, QPoint
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

# Right-side gesture panel. It reveals in two stages: the day's timetable first,
# and once that slides out of the way the King's Week grid underneath takes over
# the column.
PEEK_VISIBLE_MS  = 10_000     # timetable holds this long, then slides away
PEEK_WIDTH_FRAC  = 0.42
PEEK_MIN_WIDTH   = 360
PEEK_ANIM_IN_MS  = 420
PEEK_ANIM_OUT_MS = 380
PEEK_STAGE_MS    = 460        # the timetable's slide out / back in

# Share of the panel the timetable takes while both are showing. King's Week
# gets the rest, so it is visibly waiting below before it takes over.
PEEK_SPLIT_FRAC  = 0.56

# With no hand in the right region for this long the whole panel goes away, so
# one student's browsing can't be left stranded on the mirror.
KINGS_IDLE_MS    = 20_000

PEEK_STAGE_TIMETABLE = 1
PEEK_STAGE_KINGS     = 2


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

        # ── Right-side peek: timetable, then King's Week ───────────────────
        self.peek_container = None       # built lazily on first peek
        self.peek_panel     = None       # the day's timetable
        self.kings_panel    = None       # the King's Week grid, below it
        self._peek_visible  = False
        self._peek_stage    = PEEK_STAGE_TIMETABLE
        self._peek_anim     = None
        self._stage_anims   = None

        self.peek_timer = QTimer(self)
        self.peek_timer.setSingleShot(True)
        self.peek_timer.timeout.connect(self._promote_peek)

        self.kings_idle_timer = QTimer(self)
        self.kings_idle_timer.setSingleShot(True)
        self.kings_idle_timer.timeout.connect(self._hide_timetable_peek)

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
        """Position user layout elements matching web screenshot (50/50 split)."""
        banner_h = self.banner_frame.height() if not self.banner_frame.isHidden() else 0
        top = banner_h

        self.user_container.setGeometry(0, top, w, h - top)

        left_w = int(w * 0.50)
        right_w = w - left_w

        # Left column: Notices (50% width scaled up)
        self.notices_widget.setGeometry(0, 0, left_w, h - top)

        # Right top: Clock row
        self.clock_widget.setGeometry(left_w + 30, 20, right_w - 60, 65)

        # Right main: Timetable Class Focus
        self.timetable_widget.setGeometry(left_w + 30, 90, right_w - 60, h - top - 100)



    # ─────────────────────────────────────────────────────────────────────
    # Build: guest layout (clock + notices + onboarding)
    # ─────────────────────────────────────────────────────────────────────
    def _build_guest_layout(self):
        self.guest_container = QWidget(self.central_widget)
        self.guest_container.setStyleSheet("background: #000000;")

        # Left: notices panel (50% width)
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

        left_w = int(w * 0.50)
        right_w = w - left_w

        self.guest_notices.setGeometry(0, 0, left_w, h - top)
        self.guest_clock.setGeometry(left_w + 30, 20, right_w - 60, 65)
        self.guest_hint.setGeometry(left_w + 30, h - top - 70, right_w - 60, 50)

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

    def _handle_gesture(self, data):
        if self._last_state == 'idle' or self._last_state is None:
            return

        present = data.get("present", False)
        region  = data.get("region") if present else None
        event   = data.get("event")
        notices = self._active_notices()

        if region == GESTURE_REGION_RIGHT and self._peek_visible:
            # Any sign of a hand on this side keeps the panel alive, and while
            # King's Week is up the palm position picks a box.
            self.kings_idle_timer.start(KINGS_IDLE_MS)
            if self._peek_stage == PEEK_STAGE_KINGS and self.kings_panel is not None:
                self._focus_kings(data)

        if event:
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
                elif event == "scroll":
                    self._handle_peek_scroll(data.get("scroll_delta", 0))
                elif event == "tap":
                    self._handle_peek_tap()

        # Affordance last, so a gesture that changes which panel is in front —
        # the scroll that promotes King's Week, say — lights up the right one in
        # the same frame rather than a tenth of a second later.
        if notices is not None:
            notices.set_gesture_active(region == GESTURE_REGION_LEFT)
        if self.kings_panel is not None:
            self.kings_panel.set_gesture_active(
                region == GESTURE_REGION_RIGHT
                and self._peek_visible
                and self._peek_stage == PEEK_STAGE_KINGS
            )

    def _handle_peek_scroll(self, delta):
        """Scrolling walks down through timetable → King's Week grid → article."""
        if not delta or not self._peek_visible:
            return
        kings = self.kings_panel

        if self._peek_stage == PEEK_STAGE_TIMETABLE:
            # Scrolling down past the timetable is what reveals King's Week.
            if delta > 0:
                self._promote_peek()
            return

        if kings is None:
            return
        if kings.modal_open:
            kings.scroll_by_pixels(delta)
        elif delta < 0 and kings.at_top():
            # Scrolling back up off the top of the grid brings the timetable back.
            self._demote_peek()
        else:
            kings.scroll_by_pixels(delta)

    def _handle_peek_tap(self):
        if not self._peek_visible:
            return
        kings = self.kings_panel

        if self._peek_stage == PEEK_STAGE_TIMETABLE:
            # Tap to dismiss early instead of waiting out the 10 seconds.
            self._hide_timetable_peek()
        elif kings is not None and kings.modal_open:
            kings.close_modal()
        elif kings is not None:
            kings.activate_selected()

    def _focus_kings(self, data):
        """Turn the published palm position into a box selection.

        gesture_engine publishes a whole-screen fraction, so it is mapped through
        the panel's actual geometry rather than assuming where the panel sits.
        """
        panel = self.kings_panel
        if panel is None or panel.width() <= 0 or panel.height() <= 0:
            return
        origin = panel.mapTo(self.central_widget, QPoint(0, 0))
        x = (data.get("hand_x", 0.0) * self.width() - origin.x()) / panel.width()
        y = (data.get("hand_y", 0.0) * self.height() - origin.y()) / panel.height()
        panel.focus_at(x, y)

    # ─────────────────────────────────────────────────────────────────────
    # Right-side peek: the day's timetable, with King's Week below it
    # ─────────────────────────────────────────────────────────────────────
    def _ensure_peek(self):
        if self.peek_container is None:
            # A plain container so the timetable is clipped as it slides out
            # past the edge rather than drifting across the dashboard.
            self.peek_container = QFrame(self.central_widget)
            self.peek_container.setStyleSheet('background: #000000; border: none;')
            self.peek_panel = SchedulePeekWidget(
                parent=self.peek_container,
                api_url=API_URL,
                user_id=self.current_user_id or '',
            )
            self.kings_panel = KingsWeekWidget(
                parent=self.peek_container,
                api_url=API_URL,
            )
            self.peek_container.hide()
            self._layout_peek_stage(animate=False)
        return self.peek_container

    def _peek_geometry(self, offscreen=False):
        w, h = self.width(), self.height()
        banner_h = self.banner_frame.height() if not self.banner_frame.isHidden() else 0
        panel_w = max(PEEK_MIN_WIDTH, int(w * PEEK_WIDTH_FRAC))
        x = w if offscreen else w - panel_w
        return QRect(x, banner_h, panel_w, h - banner_h)

    def _stage_geometries(self):
        """Where the timetable and King's Week sit, for the current stage."""
        rect = self.peek_container.rect() if self.peek_container else QRect()
        w, h = rect.width(), rect.height()
        split = int(h * PEEK_SPLIT_FRAC)

        if self._peek_stage == PEEK_STAGE_KINGS:
            # Timetable parked off the container's right edge; King's Week fills it.
            return QRect(w, 0, w, split), QRect(0, 0, w, h)
        return QRect(0, 0, w, split), QRect(0, split, w, h - split)

    def _stop_anims(self, *anims):
        """Stop animations that are about to be replaced.

        They are parented to the window, so dropping the Python reference does
        not stop them: two geometry animations would then fight over the same
        widget, and whichever finished last would snap it to the wrong place.
        """
        for anim in anims:
            if anim is not None:
                anim.stop()

    def _layout_peek_stage(self, animate=True):
        if self.peek_container is None:
            return
        sched_rect, kings_rect = self._stage_geometries()
        self._stop_anims(*(self._stage_anims or ()))
        self._stage_anims = None

        if not animate:
            self.peek_panel.setGeometry(sched_rect)
            self.kings_panel.setGeometry(kings_rect)
            return

        anims = []
        for widget, end in ((self.peek_panel, sched_rect), (self.kings_panel, kings_rect)):
            anim = QPropertyAnimation(widget, b"geometry", self)
            anim.setDuration(PEEK_STAGE_MS)
            anim.setStartValue(widget.geometry())
            anim.setEndValue(end)
            anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            anim.start()
            anims.append(anim)
        self._stage_anims = anims

    def _promote_peek(self):
        """Slide the timetable out of the way and hand the column to King's Week."""
        if not self._peek_visible or self._peek_stage == PEEK_STAGE_KINGS:
            return
        self.peek_timer.stop()
        self._peek_stage = PEEK_STAGE_KINGS
        self._layout_peek_stage()
        if self.peek_panel is not None:
            # Keep the timetable on top so it visibly slides away over the grid
            # rather than being covered by it.
            self.peek_panel.raise_()
        if self.kings_panel is not None and not self.kings_panel.has_content:
            self.kings_panel.refresh()
        self.kings_idle_timer.start(KINGS_IDLE_MS)

    def _demote_peek(self):
        """Bring the timetable back over the top of the grid."""
        if not self._peek_visible or self._peek_stage == PEEK_STAGE_TIMETABLE:
            return
        self._peek_stage = PEEK_STAGE_TIMETABLE
        if self.kings_panel is not None:
            self.kings_panel.set_gesture_active(False)
        self._layout_peek_stage()
        self.peek_panel.raise_()
        # Back to the normal countdown, so it promotes again if left alone.
        self.peek_timer.start(PEEK_VISIBLE_MS)
        self.kings_idle_timer.start(KINGS_IDLE_MS)

    def _show_timetable_peek(self):
        if self._last_state in (None, 'idle'):
            return

        container = self._ensure_peek()
        # set_user_id only refetches when the user actually changed, so ask for a
        # refresh ourselves otherwise — the panel is up for 10s and should be current.
        if not self.peek_panel.set_user_id(self.current_user_id or ''):
            self.peek_panel.refresh()

        if self._peek_visible:
            # Already up; another dwell just buys more time on whatever stage it's on.
            self.kings_idle_timer.start(KINGS_IDLE_MS)
            if self._peek_stage == PEEK_STAGE_TIMETABLE:
                self.peek_timer.start(PEEK_VISIBLE_MS)
            return

        self._peek_visible = True
        self._peek_stage = PEEK_STAGE_TIMETABLE
        start, end = self._peek_geometry(offscreen=True), self._peek_geometry()
        container.setGeometry(start)
        self._layout_peek_stage(animate=False)
        container.show()
        container.raise_()

        # A hide may still be sliding out; letting it finish would hide the
        # container we have just brought back.
        self._stop_anims(self._peek_anim)
        anim = QPropertyAnimation(container, b"geometry", self)
        anim.setDuration(PEEK_ANIM_IN_MS)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._peek_anim = anim

        self.peek_timer.start(PEEK_VISIBLE_MS)
        self.kings_idle_timer.start(KINGS_IDLE_MS)

    def _hide_timetable_peek(self, animate=True):
        """Slide the whole panel back out to the right (or drop it instantly)."""
        self.peek_timer.stop()
        self.kings_idle_timer.stop()
        if not self._peek_visible or self.peek_container is None:
            return
        self._peek_visible = False
        container = self.peek_container

        # Reset the stage now so the next peek always opens on the timetable.
        self._peek_stage = PEEK_STAGE_TIMETABLE
        if self.kings_panel is not None:
            self.kings_panel.reset_gesture_state()

        if not animate:
            container.hide()
            self._layout_peek_stage(animate=False)
            return

        self._stop_anims(self._peek_anim)
        anim = QPropertyAnimation(container, b"geometry", self)
        anim.setDuration(PEEK_ANIM_OUT_MS)
        anim.setStartValue(container.geometry())
        anim.setEndValue(self._peek_geometry(offscreen=True))
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(container.hide)
        anim.finished.connect(lambda: self._layout_peek_stage(animate=False))
        anim.start()
        self._peek_anim = anim

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
            if self.peek_panel is not None:
                self.peek_panel.set_user_id(new_user_id)
            self._apply_user_theme(fdata.get('config', {}))
            self._apply_user_layout(self.width(), self.height())
        else:
            self.timetable_widget.set_user_id('')
            if self.peek_panel is not None:
                self.peek_panel.set_user_id('')
            self._apply_guest_layout(self.width(), self.height())

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

