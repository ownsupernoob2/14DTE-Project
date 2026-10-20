# mirror/smart_mirror_pro.py
import sys
import os
import json
import math
import subprocess
import time
import threading
import requests
import re
import socket

import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QVBoxLayout, QHBoxLayout, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, QPoint, QPointF, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QFont, QFontDatabase, QImage, QKeySequence, QPainter, QColor, QPen, QPainterPath

from config import *
from timing_config import (
    GESTURE_TUTORIAL_IDLE_SEC, GESTURE_TUTORIAL_DURATION_SEC, GESTURE_TUTORIAL_SPEED_FACTOR,
    IDLE_DEMO_FADE_IN_SEC, IDLE_DEMO_FADE_OUT_SEC, IDLE_DEMO_PRESENCE_FADE_SEC, IDLE_DEMO_RESUME_SEC,
)

from widgets.notices_widget import NoticesWidget
from widgets.timetable_widget import TimetableWidget
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

PINCH_EXIT_HOLD_SEC = 1.5    # how long to hold pinch to dismiss the tutorial
PINCH_DROPOUT_SEC   = 0.25   # tolerate brief tracking drops without resetting
SCAN_TEASE_HOLD_SEC = 4.0    # how long STUDENT ID SCAN stays up after a brief sighting


# ─────────────────────────────────────────────────────────────────────────────
# Gesture demo video: decoded off the UI thread, painted by a plain widget
# ─────────────────────────────────────────────────────────────────────────────
class DemoVideoDecoder(QThread):
    """Plays gesture_demo.mp4 on a worker thread and emits ready-to-paint frames.

    The clip is 1080p. Decoding and scaling it on the Qt thread, as the old
    QTimer player did, stalled the event loop for tens of milliseconds a frame
    on the Pi — and the event loop is where the gesture cursor is drawn.
    """
    frame_ready = pyqtSignal(QImage)
    played_once = pyqtSignal()

    def __init__(self, path, speed=1.0, parent=None):
        super().__init__(parent)
        self.path = path
        self.speed = max(0.1, float(speed))
        self._cond = threading.Condition()
        self._size = (0, 0)
        self._loop = False
        self._generation = 0          # bumped by play()/stop() to interrupt a run
        self._playing = False
        self._quit = False
        self.fps = 30.0
        self.frame_count = 0
        try:
            cap = cv2.VideoCapture(path)
            self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            self.frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            cap.release()
        except Exception:
            pass

    def duration_ms(self):
        if self.frame_count <= 0:
            return int(GESTURE_TUTORIAL_DURATION_SEC * 1000)
        return int(1000 * self.frame_count / (self.fps * self.speed))

    def set_target_size(self, w, h):
        with self._cond:
            self._size = (max(2, int(w)), max(2, int(h)))

    def play(self, loop=False):
        """Start from the first frame; with loop=False, emit played_once at the end."""
        with self._cond:
            self._loop = loop
            self._playing = True
            self._generation += 1
            self._cond.notify_all()
        if not self.isRunning():
            self.start()

    def stop(self):
        with self._cond:
            self._playing = False
            self._generation += 1
            self._cond.notify_all()

    def shutdown(self):
        with self._cond:
            self._quit = True
            self._playing = False
            self._generation += 1
            self._cond.notify_all()
        self.wait(2000)

    def _fit(self, vw, vh):
        tw, th = self._size
        if vw <= 0 or vh <= 0 or tw <= 0 or th <= 0:
            return vw, vh
        scale = min(tw / vw, th / vh)
        return max(2, int(vw * scale) // 2 * 2), max(2, int(vh * scale) // 2 * 2)

    def _to_image(self, frame):
        w, h = self._fit(frame.shape[1], frame.shape[0])
        if (w, h) != (frame.shape[1], frame.shape[0]):
            frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()

    def first_frame(self):
        """A still of the opening frame, shown while the overlay fades in."""
        try:
            cap = cv2.VideoCapture(self.path)
            ok, frame = cap.read()
            cap.release()
            return self._to_image(frame) if ok else None
        except Exception:
            return None

    def run(self):
        while True:
            with self._cond:
                self._cond.wait_for(lambda: self._playing or self._quit)
                if self._quit:
                    return
                gen, loop = self._generation, self._loop
            self._play_through(gen, loop)

    def _play_through(self, gen, loop):
        cap = cv2.VideoCapture(self.path)
        if not cap.isOpened():
            with self._cond:
                self._playing = False
            return
        interval = 1.0 / (self.fps * self.speed)
        t0, shown = time.monotonic(), 0
        try:
            while True:
                with self._cond:
                    if gen != self._generation or self._quit:
                        return
                lag = time.monotonic() - (t0 + shown * interval)
                if lag < 0:
                    time.sleep(min(-lag, 0.05))
                    continue
                for _ in range(min(int(lag / interval), 5)):   # behind: skip, don't drift
                    cap.grab()
                    shown += 1
                ok, frame = cap.read()
                shown += 1
                if not ok:
                    if loop:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        t0, shown = time.monotonic(), 0
                        continue
                    with self._cond:
                        if gen != self._generation:
                            return
                        self._playing = False
                    self.played_once.emit()
                    return
                self.frame_ready.emit(self._to_image(frame))
        finally:
            cap.release()


class VideoSurface(QWidget):
    """Paints the newest decoded frame, centred and letterboxed."""

    def __init__(self, parent=None, background=None):
        super().__init__(parent)
        self._image = None
        self._background = background
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_image(self, img):
        self._image = img
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._background is not None:
            painter.fillRect(self.rect(), self._background)
        img = self._image
        if img is not None and not img.isNull():
            if img.width() > self.width() or img.height() > self.height():
                img = img.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            painter.drawImage((self.width() - img.width()) // 2,
                              (self.height() - img.height()) // 2, img)
        painter.end()


def blurred_snapshot(widget, downscale=8, sigma=3.0):
    """A soft-focus copy of what `widget` shows right now.

    Blurring one still grab is cheap; a live QGraphicsBlurEffect would re-blur
    the whole screen on every repaint, which the Pi cannot afford.
    """
    img = widget.grab().toImage().convertToFormat(QImage.Format.Format_RGB888)
    w, h = img.width(), img.height()
    if w < 2 or h < 2:
        return img
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    arr = np.frombuffer(ptr, np.uint8).reshape(h, img.bytesPerLine())[:, :w * 3].reshape(h, w, 3)
    small = cv2.resize(arr, (max(1, w // downscale), max(1, h // downscale)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), sigma)
    big = np.ascontiguousarray(cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR))
    return QImage(big.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


class GestureDemoOverlay(QWidget):
    """The in-session tutorial: the video over a blurred, dimmed copy of the screen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._backdrop = None

    def set_backdrop(self, img):
        self._backdrop = img
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._backdrop is not None and not self._backdrop.isNull():
            painter.drawImage(self.rect(), self._backdrop)
            painter.fillRect(self.rect(), QColor(0, 0, 0, 110))
        else:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 184))
        painter.end()


class IdleDemoScreen(QWidget):
    """Full-screen gesture demo that plays while nobody is at the mirror."""

    def __init__(self, decoder, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.surface = VideoSurface(self, background=QColor(0, 0, 0))
        self.decoder = decoder
        decoder.frame_ready.connect(self.surface.set_image)
        self.effect = QGraphicsOpacityEffect(self)
        self.effect.setOpacity(0.0)
        self.setGraphicsEffect(self.effect)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.surface.setGeometry(self.rect())
        self.decoder.set_target_size(self.width(), self.height())


# ─────────────────────────────────────────────────────────────────────────────
# Real-Time Zero-Latency UDP Gesture Receiver
# ─────────────────────────────────────────────────────────────────────────────
class GestureUdpReceiver(QObject):
    """Sub-millisecond UDP listener receiving instant hand gesture packets from gesture_engine."""
    gesture_received = pyqtSignal(dict)

    def __init__(self, parent=None, port=50123):
        super().__init__(parent)
        self.port = port
        self.running = False
        self._thread = None

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False

    def _run(self):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", self.port))
            sock.settimeout(0.5)
            while self.running:
                try:
                    data, _ = sock.recvfrom(4096)
                    if data:
                        parsed = json.loads(data.decode('utf-8'))
                        self.gesture_received.emit(parsed)
                except socket.timeout:
                    continue
                except Exception:
                    time.sleep(0.005)
        except Exception:
            pass
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass


# ─────────────────────────────────────────────────────────────────────────────
# Gesture cursor: a dot with a short glowing trail
# ─────────────────────────────────────────────────────────────────────────────
class GestureTrailOverlay(QWidget):
    """The on-screen hand cursor.

    The camera only reports the hand ~16 times a second on a Pi, so drawing
    each report as it arrives makes the cursor step. Between reports the
    cursor head instead keeps moving along the hand's measured velocity (for at
    most part of one report interval, so it never runs far ahead), and eases
    toward that predicted point with a time constant measured in real time —
    the same feel at any frame rate, without the lag of a heavy filter.

    Only the region around the cursor is repainted on each tick: the overlay
    covers the whole window, and repainting all of it at 60 fps is a large part
    of what made the Pi feel sluggish.

    Colour: near-white when hovering, royal blue when pinching.
    """
    _OPEN_RGB  = (220, 220, 255)
    _PINCH_RGB = ( 59, 130, 246)

    _TICK_MS        = 16      # display rate
    _HEAD_TAU       = 0.035   # seconds for the head to close ~63% of the gap
    _PREDICT_SHARE  = 0.6     # extrapolate at most this share of one report interval
    _VELOCITY_BLEND = 0.5     # weight of the newest velocity sample
    _DOT_RADIUS     = 7.0
    _DOT_FADE_SEC   = 0.25

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("background: transparent; border: none;")

        self._was_pinched = False
        self._pinched = False

        # Latest report from the gesture engine, and the hand's velocity.
        self._sample = None          # (x, y, t)
        self._vx = self._vy = 0.0
        self._interval = 1 / 16      # running estimate of the report interval

        # Rendered cursor head.
        self._rx = self._ry = None
        self._last_tick = None
        self._present = False
        self._lost_at = None

        self._ipoints = []           # (x, y, t, pinched) head positions, newest last
        self._ripples = []           # (x, y, t_start, duration, QColor)
        self._max_age = 0.28         # trail length in seconds
        self._dirty = QRect()

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(self._TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._active = False
        self.hide()

    def is_empty(self):
        return self._rx is None and not self._ipoints and not self._ripples

    def head(self):
        return None if self._rx is None else (self._rx, self._ry)

    def _wake(self):
        if not self._active:
            self._active = True
            self._last_tick = time.monotonic()
            self._timer.start()
            self.show()
            self.raise_()

    def add_point(self, x, y, pinched=False):
        """A position report from the gesture engine (~16-30 per second)."""
        now = time.monotonic()
        x, y = float(x), float(y)
        if pinched and not self._was_pinched:
            self.trigger_ripple(x, y, color=QColor(*self._PINCH_RGB), duration=0.28)
        elif not pinched and self._was_pinched:
            self.trigger_ripple(x, y, color=QColor(210, 220, 255), duration=0.16)
        self._was_pinched = pinched
        self._pinched = pinched

        if self._sample is not None and self._present:
            px, py, pt = self._sample
            dt = now - pt
            if 0.004 < dt < 0.25:
                b = self._VELOCITY_BLEND
                self._vx = (1 - b) * self._vx + b * (x - px) / dt
                self._vy = (1 - b) * self._vy + b * (y - py) / dt
                self._interval = 0.8 * self._interval + 0.2 * dt
            elif dt >= 0.25:
                self._vx = self._vy = 0.0
        else:
            self._vx = self._vy = 0.0
        self._sample = (x, y, now)

        if self._rx is None or not self._present:
            self._rx, self._ry = x, y      # appear where the hand is, no glide in
            self._ipoints.clear()
        self._present = True
        self._lost_at = None
        self._wake()

    def trigger_ripple(self, x, y, color=None, duration=0.28):
        if color is None:
            color = QColor(200, 200, 255)
        self._ripples.append((float(x), float(y), time.monotonic(), duration, color))
        self._wake()
        self.update()

    def fade_out(self):
        """The hand left the frame: stop following and let the cursor fade."""
        if self._present:
            self._present = False
            self._lost_at = time.monotonic()
        self._vx = self._vy = 0.0
        self._was_pinched = False

    def clear_trail(self):
        self._ipoints.clear()
        self._ripples.clear()
        self._sample = None
        self._rx = self._ry = None
        self._present = False
        self._lost_at = None
        self._vx = self._vy = 0.0
        self._was_pinched = False
        if self._active:
            self._timer.stop()
            self._active = False
            self.hide()
        self.update()

    def _target(self, now):
        x, y, t = self._sample
        ahead = min(max(0.0, now - t), self._PREDICT_SHARE * self._interval)
        return x + self._vx * ahead, y + self._vy * ahead

    def _dot_alpha(self, now):
        if self._present:
            return 1.0
        if self._lost_at is None:
            return 0.0
        return max(0.0, 1.0 - (now - self._lost_at) / self._DOT_FADE_SEC)

    def _tick(self):
        now = time.monotonic()
        dt = min(0.1, max(0.0, now - (self._last_tick or now)))
        self._last_tick = now

        if self._present and self._sample is not None and self._rx is not None:
            tx, ty = self._target(now)
            a = 1.0 - math.exp(-dt / self._HEAD_TAU) if dt > 0 else 0.0
            self._rx += a * (tx - self._rx)
            self._ry += a * (ty - self._ry)
            last = self._ipoints[-1] if self._ipoints else None
            if last is None or (last[0] - self._rx) ** 2 + (last[1] - self._ry) ** 2 >= 0.25:
                self._ipoints.append((self._rx, self._ry, now, self._pinched))

        cutoff = now - self._max_age
        self._ipoints = [p for p in self._ipoints if p[2] >= cutoff]
        self._ripples = [r for r in self._ripples if now - r[2] <= r[3]]

        if not self._present and self._dot_alpha(now) <= 0.0:
            self._rx = self._ry = None
        if self._rx is None and not self._ipoints and not self._ripples:
            self._timer.stop()
            self._active = False
            self.update(self._dirty)
            self._dirty = QRect()
            self.hide()
            return

        self._repaint_region()

    def _bounds(self):
        xs, ys = [p[0] for p in self._ipoints], [p[1] for p in self._ipoints]
        if self._rx is not None:
            xs.append(self._rx)
            ys.append(self._ry)
        pad = 18
        rect = QRect()
        if xs:
            rect = QRect(int(min(xs)) - pad, int(min(ys)) - pad,
                         int(max(xs) - min(xs)) + 2 * pad, int(max(ys) - min(ys)) + 2 * pad)
        for rx, ry, _, _, _ in self._ripples:
            rect = rect.united(QRect(int(rx) - 30, int(ry) - 30, 60, 60))
        return rect

    def _repaint_region(self):
        rect = self._bounds()
        self.update(rect.united(self._dirty))
        self._dirty = rect

    @staticmethod
    def _smooth_path(pts):
        """Mid-point quadratic Bezier through recorded positions (C1 continuous)."""
        path = QPainterPath()
        if len(pts) < 2:
            return path
        path.moveTo(pts[0][0], pts[0][1])
        for i in range(1, len(pts) - 1):
            path.quadTo(pts[i][0], pts[i][1],
                        (pts[i][0] + pts[i + 1][0]) * 0.5, (pts[i][1] + pts[i + 1][1]) * 0.5)
        path.lineTo(pts[-1][0], pts[-1][1])
        return path

    def paintEvent(self, event):
        now = time.monotonic()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Ripple bursts on pinch / release
        for rx, ry, rt, rd, rcolor in self._ripples:
            age = (now - rt) / rd
            if age > 1.0:
                continue
            radius = 5 + 20 * age
            c = QColor(rcolor.red(), rcolor.green(), rcolor.blue(), int(190 * (1.0 - age) ** 1.6))
            painter.setPen(QPen(c, 1.8))
            painter.drawEllipse(QPointF(rx, ry), radius, radius)

        r, g, b = self._PINCH_RGB if self._pinched else self._OPEN_RGB

        # Trail: a fading ribbon behind a moving hand
        pts = self._ipoints
        if len(pts) >= 2:
            path = self._smooth_path(pts)
            for width, alpha in ((12, 70), (5, 150), (2.2, 230)):
                painter.setPen(QPen(QColor(r, g, b, alpha), width, Qt.PenStyle.SolidLine,
                                    Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                painter.drawPath(path)

        # Cursor dot, always visible while a hand is tracked
        dot = self._dot_alpha(now)
        if self._rx is not None and dot > 0:
            centre = QPointF(self._rx, self._ry)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(r, g, b, int(60 * dot)))
            painter.drawEllipse(centre, self._DOT_RADIUS * 2.0, self._DOT_RADIUS * 2.0)
            painter.setBrush(QColor(255, 255, 255, int(235 * dot)) if not self._pinched
                             else QColor(r, g, b, int(240 * dot)))
            painter.drawEllipse(centre, self._DOT_RADIUS, self._DOT_RADIUS)
        painter.end()


class GuestScanCallout(QWidget):
    """Bouncing + pulsing STUDENT ID SCAN callout drawn entirely in paintEvent.

    Avoids QGraphicsOpacityEffect (which conflicts with the overlay's own
    fade effect and causes UI freezes). The widget drives its own 60 fps
    timer and uses time.time() + math.sin() to compute both the bounce
    offset and the alpha pulse on every frame.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setStyleSheet("background: transparent;")

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(16)   # 60 fps
        self._timer.timeout.connect(self.update)
        self._fade = 1.0

    def set_fade(self, f):
        self._fade = max(0.0, min(1.0, float(f)))
        self.update()

    def start(self):
        self._timer.start()
        self.update()

    def stop(self):
        self._timer.stop()

    def paintEvent(self, event):
        import math as _math
        t = time.time()

        # Pulse: 0.55 -> 1.0 oscillation at ~0.8 Hz
        pulse = 0.55 + 0.45 * (0.5 + 0.5 * _math.sin(t * _math.pi * 1.6))

        # Bounce: arrow moves up/down 12px at ~1.2 Hz
        bounce = 12.0 * _math.sin(t * _math.pi * 2.4)

        alpha = int(255 * pulse * self._fade)
        w, h = self.width(), self.height()
        half = h // 2

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = QColor(255, 255, 255, alpha)
        painter.setPen(color)

        # --- Text: "STUDENT ID SCAN" in the top half ---
        font = painter.font()
        font.setFamily("Segoe UI")
        font.setPixelSize(46)
        font.setWeight(QFont.Weight.Black)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 7)
        painter.setFont(font)
        text_rect = QRect(0, 0, w, half)
        painter.drawText(text_rect,
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                         "STUDENT ID SCAN")

        # --- Arrow "v" in the bottom half, bouncing ---
        afont = painter.font()
        afont.setPixelSize(68)
        afont.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
        painter.setFont(afont)

        # Translate painter down by bounce amount
        painter.translate(0.0, bounce)
        arrow_rect = QRect(0, half, w, half)
        painter.drawText(arrow_rect,
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                         "▼")

        painter.end()


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
        font_path = os.path.join(os.path.dirname(__file__), 'assets', 'HankenGrotesk.ttf')
        if os.path.exists(font_path):
            hk_id = QFontDatabase.addApplicationFont(font_path)
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
        self._demo_anim = None
        self._scrim_fading_out = False
        self._demo_pinch_start = None
        self._demo_pinch_last = 0.0
        self._scan_tease_until = 0.0

        # ── Idle attract loop (full-screen demo while nobody is there) ────
        self._last_presence_time = 0.0   # last face or hand seen, by anyone
        self._idle_demo_phase = 'off'    # off | playing | ending | leaving
        self._idle_demo_anim = None
        self._last_udp_gesture = 0.0

        # ── Telemetry & A/B Testing Tracker ───────────────────────────────
        self.telemetry = TelemetryTracker(api_url=API_URL)
        self.current_variant = "A"

        # ── Timers ────────────────────────────────────────────────────────

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._update_inputs)
        self.poll_timer.start(200)

        self.gesture_timer = QTimer(self)
        self.gesture_timer.timeout.connect(self._poll_gestures)
        self.gesture_timer.start(25)

        # Real-time sub-millisecond UDP gesture listener (bypasses disk I/O and polling lag)
        self.gesture_receiver = GestureUdpReceiver(self)
        self.gesture_receiver.gesture_received.connect(self._handle_gesture_direct)
        self.gesture_receiver.start()

        self.banner_timer = QTimer(self)
        self.banner_timer.timeout.connect(self._poll_banner)
        self.banner_timer.start(30000)
        self._poll_banner()

        # Fetch version code from server /health
        self._fetch_server_version()

        # ── Window mode ───────────────────────────────────────────────────
        if os.environ.get('MIRROR_WINDOWED') == '1':
            self.resize(REF_WIDTH, REF_HEIGHT)
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.showFullScreen()
            self.setCursor(Qt.CursorShape.BlankCursor)

    def _fetch_server_version(self):
        """Asynchronously query server /health for dynamic version string."""
        def _worker():
            try:
                resp = requests.get(f"{API_URL}/health", timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    ver = data.get("version")
                    if ver:
                        QTimer.singleShot(0, lambda: self._apply_server_version(ver))
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _apply_server_version(self, ver):
        if hasattr(self, 'version_lbl') and self.version_lbl:
            self.version_lbl.setText(ver)
            self.version_lbl.adjustSize()

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
        self.dwell_hint_pill = QLabel("Hold hand in top-right for Timetable", self.central_widget)
        self.dwell_hint_pill.setObjectName("DwellHintPill")
        self.dwell_hint_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dwell_hint_pill.setStyleSheet("""
            #DwellHintPill {
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 13px;
                font-weight: 700;
                color: #e2e8f0;
                background: #000000;
                border: none;
                border-radius: 0px;
                padding: 4px 12px;
            }
        """)
        self.dwell_hint_pill.hide()

        # Hand cursor (dot + trail), drawn above everything else
        self.gesture_trail = GestureTrailOverlay(self.central_widget)
        self.gesture_trail.setObjectName("GestureTrailOverlay")

    def _position_guest_scan_callout(self):
        """Place STUDENT ID SCAN callout at bottom-center of the window."""
        if not hasattr(self, 'guest_scan_callout'):
            return
        sw = self.width()
        sh = self.height()
        ch = 220
        cy = sh - ch - 50
        self.guest_scan_callout.setGeometry(0, cy, sw, ch)

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
    # Build: gesture demo (in-session tutorial + idle attract loop)
    # ─────────────────────────────────────────────────────────────────────
    def _build_gesture_demo(self):
        mp4_path = os.path.join(os.path.dirname(__file__), 'assets', 'gesture_demo.mp4')
        has_video = os.path.exists(mp4_path)

        # In-session tutorial: the demo over a blurred copy of the screen,
        # dismissed by pinching and holding.
        self.gesture_demo_overlay = GestureDemoOverlay(self.central_widget)
        self.gesture_demo_overlay.setObjectName("GestureDemoOverlay")
        lay = QVBoxLayout(self.gesture_demo_overlay)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(24)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.demo_movie = None
        self.demo_surface = VideoSurface(self.gesture_demo_overlay)
        self.demo_surface.setFixedSize(800, 450)
        lay.addWidget(self.demo_surface, alignment=Qt.AlignmentFlag.AlignCenter)
        if has_video:
            self.demo_movie = DemoVideoDecoder(mp4_path, GESTURE_TUTORIAL_SPEED_FACTOR, self)
            self.demo_movie.set_target_size(800, 450)
            self.demo_movie.frame_ready.connect(self.demo_surface.set_image)
            self.demo_surface.set_image(self.demo_movie.first_frame())

        # Pinch-and-hold progress bar beneath the video
        self.demo_hold_bar = QFrame(self.gesture_demo_overlay)
        self.demo_hold_bar.setFixedSize(800, 6)
        self.demo_hold_bar.setStyleSheet("background: rgba(255,255,255,0.16); border: none; border-radius: 3px;")
        self.demo_hold_fill = QFrame(self.demo_hold_bar)
        self.demo_hold_fill.setStyleSheet("background: #ffffff; border: none; border-radius: 3px;")
        self.demo_hold_fill.setGeometry(0, 0, 0, 6)
        lay.addWidget(self.demo_hold_bar, alignment=Qt.AlignmentFlag.AlignCenter)
        self.gesture_demo_overlay.hide()

        # Nobody at the mirror: the same demo, full screen, on a loop.
        self.idle_demo = None
        if has_video:
            self.idle_demo_movie = DemoVideoDecoder(mp4_path, GESTURE_TUTORIAL_SPEED_FACTOR, self)
            self.idle_demo_movie.played_once.connect(self._on_idle_demo_finished)
            self.idle_demo = IdleDemoScreen(self.idle_demo_movie, self.central_widget)
            self.idle_demo.hide()

        # Guest-only: bouncing + pulsing STUDENT ID SCAN callout
        # Self-contained widget -- no nested QGraphicsOpacityEffect (avoids freeze).
        self.guest_scan_callout = GuestScanCallout(self.central_widget)
        self.guest_scan_callout.hide()

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

        # Unsure face recognition alert banner
        self.guest_unsure_prompt_lbl = QLabel(
            "⚠️ Face Not Confirmed: We might be getting the wrong person.\nScan your Student ID barcode below to make sure!",
            self.guest_register_card
        )
        self.guest_unsure_prompt_lbl.setWordWrap(True)
        self.guest_unsure_prompt_lbl.setStyleSheet("""
            font-family: 'Segoe UI', system-ui, sans-serif;
            font-size: 19px;
            font-weight: 700;
            color: #fef08a;
            background: rgba(133, 77, 14, 0.40);
            border: 2px solid #eab308;
            border-radius: 12px;
            padding: 10px 16px;
            letter-spacing: 0.3px;
        """)
        self.guest_unsure_prompt_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.guest_unsure_prompt_lbl.hide()
        card_lay.addWidget(self.guest_unsure_prompt_lbl)

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
            "Visit smartmirror.me to register your face and customize your timetable.",
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
            if hasattr(self, 'guest_scan_callout') and self.guest_scan_callout.isVisible():
                self._position_guest_scan_callout()

        if getattr(self, 'idle_demo', None) is not None:
            self.idle_demo.setGeometry(0, 0, w, h)

        if hasattr(self, 'gesture_trail') and self.gesture_trail is not None:
            self.gesture_trail.setGeometry(0, 0, w, h)
            self.gesture_trail.raise_()


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

        # The status file is only a fallback for when UDP isn't arriving.
        if time.time() - self._last_udp_gesture < 0.5:
            return
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

    def _handle_gesture_direct(self, data):
        """Zero-latency callback triggered immediately when UDP datagram arrives from gesture_engine."""
        self._last_udp_gesture = time.time()
        t = data.get("timestamp", 0.0)
        if t > self.last_gesture_timestamp:
            self.last_gesture_timestamp = t
            self._handle_gesture(data)

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
            if animate:
                anim_tt = QPropertyAnimation(self.timetable_widget, b"geometry", self)
                anim_tt.setDuration(TIMETABLE_ANIM_MS)
                anim_tt.setStartValue(self.timetable_widget.geometry())
                anim_tt.setEndValue(QRect(0, 0, cw, split_h))
                anim_tt.setEasingCurve(QEasingCurve.Type.OutCubic)

                anim_kw = QPropertyAnimation(self.kings_widget, b"geometry", self)
                anim_kw.setDuration(TIMETABLE_ANIM_MS)
                anim_kw.setStartValue(self.kings_widget.geometry())
                anim_kw.setEndValue(QRect(0, split_h, cw, ch - split_h))
                anim_kw.setEasingCurve(QEasingCurve.Type.OutCubic)

                anim_tt.start()
                anim_kw.start()
                self._timetable_anim = anim_tt
                self._kings_anim = anim_kw
            else:
                self.timetable_widget.setGeometry(0, 0, cw, split_h)
                self.kings_widget.setGeometry(0, split_h, cw, ch - split_h)
            self.timetable_widget.show()
            self.kings_widget.show()
            self.timetable_widget.raise_()
            self.timetable_display_timer.start(TIMETABLE_DISPLAY_MS)
            if self.kings_widget is not None:
                self.kings_widget.set_half_mode(True)   # split view: focus only
        else:
            self._timetable_full_mode = True
            self.timetable_widget.set_mode('full')
            self.timetable_widget.show()
            self.timetable_widget.raise_()

            if animate:
                anim_tt = QPropertyAnimation(self.timetable_widget, b"geometry", self)
                anim_tt.setDuration(TIMETABLE_ANIM_MS)
                start_geom = self.timetable_widget.geometry() if not self._timetable_slid_away else QRect(0, -ch, cw, ch)
                anim_tt.setStartValue(start_geom)
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
            if self.kings_widget is not None:
                self.kings_widget.set_half_mode(False)  # full timetable: KW hidden below

        self._update_arrow_indicator()

    def _slide_timetable_out(self, animate=True):
        """Slide Timetable UP, smoothly expanding King's Week to full column height."""
        if self.right_stack_container is None:
            return
        self.timetable_display_timer.stop()
        self._timetable_slid_away = True
        self._timetable_full_mode = False
        if self.kings_widget is not None:
            self.kings_widget.set_half_mode(False)  # fully expanded: cards are clickable
        cw = self.right_stack_container.width()
        ch = self.right_stack_container.height()

        if self._timetable_anim is not None:
            self._timetable_anim.stop()

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

        # Variant B: show dwell hint pill beneath arrow (no emoji, black bg)
        if getattr(self, 'current_variant', 'A') == 'B' and hasattr(self, 'dwell_hint_pill'):
            pill_w = 290
            pill_h = 28
            pill_x = content_x + (content_w - pill_w) // 2
            pill_y = arrow_y + 36
            self.dwell_hint_pill.setGeometry(pill_x, pill_y, pill_w, pill_h)
            self.dwell_hint_pill.setText("Hold hand in top-right for Timetable")
            self.dwell_hint_pill.show()
            self.dwell_hint_pill.raise_()
        elif hasattr(self, 'dwell_hint_pill'):
            self.dwell_hint_pill.hide()

    # ─────────────────────────────────────────────────────────────────────
    # Gesture tutorial: pinch-and-hold to dismiss
    # ─────────────────────────────────────────────────────────────────────
    def _show_scan_callout(self):
        if not hasattr(self, 'guest_scan_callout'):
            return
        self._position_guest_scan_callout()
        self.guest_scan_callout.set_fade(1.0)
        if not self.guest_scan_callout.isVisible():
            self.guest_scan_callout.show()
            self.guest_scan_callout.start()
        self.guest_scan_callout.raise_()

    def _hide_scan_callout(self):
        if hasattr(self, 'guest_scan_callout'):
            self.guest_scan_callout.stop()
            self.guest_scan_callout.hide()
        self._scan_tease_until = 0.0

    def _demo_overlay_active(self):
        return (getattr(self, 'gesture_demo_overlay', None) is not None
                and self.gesture_demo_overlay.isVisible()
                and not self._scrim_fading_out)

    def _set_demo_hold_progress(self, p):
        if not hasattr(self, 'demo_hold_bar') or self.demo_hold_bar is None:
            return
        p = max(0.0, min(1.0, p))
        self.demo_hold_fill.setGeometry(0, 0, int(self.demo_hold_bar.width() * p), self.demo_hold_bar.height())

    def _update_demo_hold(self, pinched):
        now = time.time()
        if pinched:
            self._demo_pinch_last = now
            if self._demo_pinch_start is None:
                self._demo_pinch_start = now
        elif self._demo_pinch_start is not None and now - self._demo_pinch_last > PINCH_DROPOUT_SEC:
            self._demo_pinch_start = None

        if self._demo_pinch_start is None:
            self._set_demo_hold_progress(0.0)
            return

        progress = (now - self._demo_pinch_start) / PINCH_EXIT_HOLD_SEC
        self._set_demo_hold_progress(progress)
        if progress >= 1.0:
            self._demo_pinch_start = None
            self._last_activity_time = now      # so the idle timer doesn't instantly re-show it
            self._fade_out_gesture_scrim()

    def _show_gesture_scrim(self):
        """Play the tutorial over a blurred copy of the screen (no gestures for a while)."""
        if self.gesture_demo_overlay is None:
            return
        if self.gesture_demo_overlay.isVisible() and not getattr(self, '_scrim_fading_out', False):
            return

        self._scrim_fading_out = False
        self.gesture_demo_overlay.setGeometry(0, 0, self.width(), self.height())
        if not self.gesture_demo_overlay.isVisible():
            self.gesture_trail.hide()             # keep the cursor out of the snapshot
            self.gesture_demo_overlay.set_backdrop(blurred_snapshot(self.central_widget))
            self.gesture_trail.setVisible(self.gesture_trail._active)
        effect = QGraphicsOpacityEffect(self.gesture_demo_overlay)
        self.gesture_demo_overlay.setGraphicsEffect(effect)
        effect.setOpacity(0.0)

        self.gesture_demo_overlay.show()
        self.gesture_demo_overlay.raise_()
        self.gesture_trail.raise_()

        self._demo_pinch_start = None
        self._set_demo_hold_progress(0.0)

        # Show guest barcode callout only in guest state
        if hasattr(self, 'guest_scan_callout'):
            if self._last_state == 'guest':
                self.guest_scan_callout.set_fade(0.0)
                self._position_guest_scan_callout()
                self.guest_scan_callout.show()
                self.guest_scan_callout.raise_()  # above overlay
                self.guest_scan_callout.start()
            else:
                self._hide_scan_callout()


        if self.demo_movie is not None:
            self.demo_movie.play(loop=True)

        anim_in = QPropertyAnimation(effect, b"opacity", self)
        anim_in.setDuration(450)
        anim_in.setStartValue(0.0)
        anim_in.setEndValue(1.0)
        anim_in.valueChanged.connect(lambda v: self.guest_scan_callout.set_fade(v))
        anim_in.start()
        self._demo_anim = anim_in

        # No auto-dismiss timer: the video loops until the user pinch-holds to exit.

    def _fade_out_gesture_scrim(self):
        """Smoothly fade out the tutorial overlay (background + video) to 0.0 opacity."""
        if not hasattr(self, 'gesture_demo_overlay') or self.gesture_demo_overlay is None:
            return
        if not self.gesture_demo_overlay.isVisible() or getattr(self, '_scrim_fading_out', False):
            return
        self._scrim_fading_out = True

        effect = self.gesture_demo_overlay.graphicsEffect()
        if effect is None:
            effect = QGraphicsOpacityEffect(self.gesture_demo_overlay)
            self.gesture_demo_overlay.setGraphicsEffect(effect)

        current_opacity = effect.opacity()
        anim_out = QPropertyAnimation(effect, b"opacity", self)
        anim_out.setDuration(int(450 * max(0.1, current_opacity)))
        anim_out.setStartValue(current_opacity)
        anim_out.setEndValue(0.0)
        anim_out.valueChanged.connect(lambda v: self.guest_scan_callout.set_fade(v))

        def on_done():
            self.gesture_demo_overlay.hide()
            self.gesture_demo_overlay.set_backdrop(None)
            self._hide_scan_callout()
            self._scrim_fading_out = False
            self._demo_pinch_start = None
            self._set_demo_hold_progress(0.0)
            if hasattr(self, 'demo_movie') and self.demo_movie is not None:
                self.demo_movie.stop()

        anim_out.finished.connect(on_done)
        anim_out.start()
        self._demo_anim = anim_out

    # ─────────────────────────────────────────────────────────────────────
    # Idle attract loop: the demo, full screen, while nobody is at the mirror
    #
    #   off ──(empty for IDLE_DEMO_RESUME_SEC)──▶ playing ──(clip ends)──▶ ending
    #    ▲                                          │                        │
    #    │                    (anyone seen) ────────┴──▶ leaving ──▶ off     │
    #    └──────── fade-out done, still empty: play again ◀──────────────────┘
    # ─────────────────────────────────────────────────────────────────────
    def _idle_demo_wanted(self):
        if self.idle_demo is None or self._transitioning:
            return False
        if self._last_state not in (None, 'idle'):
            return False
        return time.time() - self._last_presence_time >= IDLE_DEMO_RESUME_SEC

    def _update_idle_demo(self):
        """Start the loop when the mirror is empty; fade it the moment anyone shows up."""
        if self.idle_demo is None:
            return
        wanted = self._idle_demo_wanted()
        if wanted and self._idle_demo_phase == 'off':
            self._start_idle_demo()
        elif not wanted and self._idle_demo_phase in ('playing', 'ending'):
            self._fade_idle_demo(IDLE_DEMO_PRESENCE_FADE_SEC * self.idle_demo.effect.opacity(), 'leaving')

    def _start_idle_demo(self):
        demo = self.idle_demo
        demo.setGeometry(0, 0, self.width(), self.height())
        self.idle_demo_movie.set_target_size(self.width(), self.height())
        if demo.isHidden():
            demo.surface.set_image(None)
            demo.effect.setOpacity(0.0)
            demo.show()
        demo.raise_()
        for w in (self.guest_scan_callout, self.status_dot, self.version_lbl, self.gesture_trail):
            if w.isVisible():
                w.raise_()
        self._idle_demo_phase = 'playing'
        self.idle_demo_movie.play(loop=False)
        anim = self._animate_idle_demo(1.0, IDLE_DEMO_FADE_IN_SEC)
        # Fully opaque: drop the effect so each video frame isn't composited twice.
        anim.finished.connect(lambda: self.idle_demo.effect.setEnabled(False))

    def _on_idle_demo_finished(self):
        if self._idle_demo_phase == 'playing':
            self._fade_idle_demo(IDLE_DEMO_FADE_OUT_SEC, 'ending')

    def _fade_idle_demo(self, seconds, phase):
        self._idle_demo_phase = phase
        anim = self._animate_idle_demo(0.0, seconds)
        anim.finished.connect(self._on_idle_demo_faded)

    def _on_idle_demo_faded(self):
        self.idle_demo_movie.stop()
        phase, self._idle_demo_phase = self._idle_demo_phase, 'off'
        if phase == 'ending' and self._idle_demo_wanted():
            self._start_idle_demo()          # still nobody here: play it again
        else:
            self.idle_demo.hide()

    def _animate_idle_demo(self, end, seconds):
        if self._idle_demo_anim is not None:
            self._idle_demo_anim.stop()      # stop() does not emit finished
        effect = self.idle_demo.effect
        effect.setEnabled(True)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(max(1, int(seconds * 1000)))
        anim.setStartValue(effect.opacity())
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        anim.start()
        self._idle_demo_anim = anim
        return anim

    # ─────────────────────────────────────────────────────────────────────
    # Gesture Dispatch
    # ─────────────────────────────────────────────────────────────────────
    def _handle_gesture(self, data):
        if data.get("present", False):
            self._last_presence_time = time.time()   # a hand is someone, even at idle
            self._update_idle_demo()

        # Don't turn on gestures until it's either in guest or recognized
        if self._last_state not in ('guest', 'user'):
            return

        present     = data.get("present", False)
        region      = data.get("region") if present else None
        event       = data.get("event")
        delta       = data.get("scroll_delta", 0)

        # Receiver-side tap gate: the gesture engine has a 0.35s cooldown but
        # multiple UDP packets with event="tap" can still arrive in the same
        # Qt event-loop tick.  Drop any tap within 700ms of the last accepted
        # one to prevent open-close-open flicker on Kings Week cards.
        if event == "tap":
            _now = time.time()
            if _now - getattr(self, '_last_rx_tap_time', 0.0) < 0.70:
                event = None   # suppress -- treat as a no-op hover packet
            else:
                self._last_rx_tap_time = _now

        right_dwell = data.get("top_right_dwell_progress", data.get("right_dwell_progress", 0.0))
        dwell_side  = data.get("dwell_side") or ("top_right" if data.get("hand_x", 0.5) >= 0.5 else "left")
        notices     = self._active_notices()

        if present:
            self._last_interaction_time = time.time()

        if hasattr(self, 'gesture_trail') and self.gesture_trail is not None:
            if present:
                hx = data.get("hand_x", 0.5)
                hy = data.get("hand_y", 0.5)
                target_x = hx * self.width()
                target_y = hy * self.height()
                # gesture_engine already applies 0.88 EMA smoothing, map position directly
                self._cur_trail_x = float(target_x)
                self._cur_trail_y = float(target_y)

                pinched = bool(data.get("pinched", False))
                self.gesture_trail.add_point(self._cur_trail_x, self._cur_trail_y, pinched)
            else:
                self.gesture_trail.fade_out()

        # While the tutorial video is up, the only thing that does anything is
        # a held pinch (fills the bar under the video, exits at 100%).
        if self._demo_overlay_active():
            self._update_demo_hold(present and bool(data.get("pinched", False)))
            return

        # Telemetry: Record gesture events & dwell progress
        event_id = data.get("event_id", 0)
        is_new_event = False
        if event and event_id != getattr(self, '_last_handled_event_id', -1):
            self._last_handled_event_id = event_id
            is_new_event = True

        if hasattr(self, 'telemetry') and self.telemetry is not None:
            if is_new_event:     # the engine repeats an event for ~100 ms; count it once
                self.telemetry.record_gesture(event_type=event, region=region)
            if right_dwell > 0:
                self.telemetry.record_dwell_progress(right_dwell)

            # Mid-air hand movement detection: user gesturing in front of mirror
            if present:
                hx = data.get("hand_x")
                hy = data.get("hand_y")
                if hx is not None and hy is not None:
                    last_hx = getattr(self, '_last_telemetry_hx', hx)
                    last_hy = getattr(self, '_last_telemetry_hy', hy)
                    dist = ((hx - last_hx)**2 + (hy - last_hy)**2)**0.5
                    self._last_telemetry_hx = hx
                    self._last_telemetry_hy = hy
                    if dist > 0.025:
                        self.telemetry.record_gesture(event_type="motion", region=region)

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

                # Variant B dwell pill hides during active dwell (progress bar is sufficient feedback)
                if hasattr(self, 'dwell_hint_pill'):
                    self.dwell_hint_pill.hide()
            elif not self.indicator_bar.isHidden():
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
                self.telemetry.record_gesture(event_type="dwell", region="top_right")
                self.telemetry.record_timetable_toggle()
            if self._last_state == 'user':
                if self._timetable_slid_away or getattr(self, '_timetable_full_mode', False):
                    self._show_timetable(animate=True, is_initial_split=True)
                else:
                    self._show_timetable(animate=True, is_initial_split=False)
            elif self._last_state == 'guest':
                if self._guest_card_slid_away:
                    self._show_guest_card(animate=True, is_initial_split=False)
                else:
                    self._slide_guest_card_out(animate=True)

        elif effective_region == GESTURE_REGION_LEFT and notices is not None:
            if event == "scroll" and delta != 0:
                self._stop_momentum()
                if hasattr(notices, 'clear_selection'):
                    notices.clear_selection()
                notices.scroll_by_pixels(delta)
            elif event == "fling" and delta != 0:
                if hasattr(notices, 'clear_selection'):
                    notices.clear_selection()
                self._start_momentum(notices, delta)
            elif event == "tap":
                self._stop_momentum()
                if hasattr(notices, 'modal_open') and notices.modal_open:
                    notices.close_modal()
                    if hasattr(self, 'telemetry') and self.telemetry is not None:
                        self.telemetry.record_modal_close()
                elif hasattr(notices, 'activate_selected'):
                    notices.activate_selected()
                    if hasattr(self, 'telemetry') and self.telemetry is not None:
                        self.telemetry.record_modal_open()
                elif hasattr(notices, 'toggle_scroll_pause'):
                    notices.toggle_scroll_pause()
            elif event not in ("scroll", "fling"):
                if hasattr(notices, 'select_at_point'):
                    hx = data.get("hand_x", 0.25)
                    hy = data.get("hand_y", 0.5)
                    notices.select_at_point(hx, hy)

        elif effective_region == GESTURE_REGION_RIGHT:
            active_target = None
            split_kings = None     # King's Week while it shares the column, hand over it
            if self._last_state == 'user':
                if getattr(self, '_timetable_full_mode', False):
                    active_target = self.timetable_widget
                elif self._timetable_slid_away:
                    active_target = self.kings_widget
                elif self._hand_over(self.timetable_widget, data):
                    active_target = self.timetable_widget
                else:
                    active_target = split_kings = self.kings_widget
            elif self._last_state == 'guest':
                if self._guest_card_slid_away:
                    active_target = self.guest_kings_widget
                elif not self._hand_over(self.guest_register_card, data):
                    active_target = split_kings = self.guest_kings_widget

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
                    if split_kings is not None:
                        # Half and half: a tap on King's Week gives it the whole column.
                        if split_kings is self.kings_widget:
                            self._slide_timetable_out(animate=True)
                        else:
                            self._slide_guest_card_out(animate=True)
                    elif hasattr(active_target, 'modal_open') and active_target.modal_open:
                        active_target.close_modal()
                        if hasattr(self, 'telemetry') and self.telemetry is not None:
                            self.telemetry.record_modal_close()
                    else:
                        # Ensure a card is selected nearest to the hand before activating
                        if hasattr(active_target, 'focus_at'):
                            self._focus_kings_target(active_target, data)
                        if hasattr(active_target, 'activate_selected') and active_target.activate_selected():
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


    def _hand_over(self, widget, data):
        """Whether the hand cursor is inside `widget` as drawn on screen."""
        if widget is None or not widget.isVisible():
            return False
        point = QPoint(int(data.get("hand_x", 0.0) * self.width()),
                       int(data.get("hand_y", 0.0) * self.height()))
        return QRect(widget.mapTo(self.central_widget, QPoint(0, 0)), widget.size()).contains(point)

    def _focus_kings_target(self, panel, data):
        if panel is None or panel.width() <= 0 or panel.height() <= 0:
            return
        origin = panel.mapTo(self.central_widget, QPoint(0, 0))
        x = (data.get("hand_x", 0.0) * self.width() - origin.x()) / panel.width()
        y = (data.get("hand_y", 0.0) * self.height() - origin.y()) / panel.height()
        panel.focus_at(x, y)

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
                seen = now if self.face_detected else fdata.get('last_face_time', 0.0)
                self._last_presence_time = max(self._last_presence_time, seen or 0.0)
                self.face_confidence = fdata.get('confidence', 0.0)
                self.in_grace        = fdata.get('in_grace', False)

                new_state   = fdata.get('state', 'idle')
                new_user_id = fdata.get('user_id', 'idle')
                daemon_auth = fdata.get('auth_method', '')
                if daemon_auth:
                    is_barcode_live = (getattr(self, '_auth_method', '') == 'barcode' and (now - getattr(self, '_last_barcode_scan_time', 0) < 300.0))
                    if not is_barcode_live:
                        self._auth_method = daemon_auth
            else:
                self.face_detected   = False
                self.face_recognized = False
                self.face_confidence = 0.0
                self.in_grace        = False
                new_state   = 'idle'
                new_user_id = 'idle'

            # Unsure face recognition alert prompt on guest screen kept hidden
            if hasattr(self, 'guest_unsure_prompt_lbl'):
                self.guest_unsure_prompt_lbl.hide()

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

            # ── Guard: Don’t interrupt active interactions ───────────────────
            # A hand being actively tracked counts as interaction even if face
            # detection briefly drops (head turn, glare, blink).  We also widen
            # the grace window so a user isn’t kicked mid-scroll.
            hand_present = bool(getattr(self, '_cur_trail_x', None) is not None
                                and (now - self._last_interaction_time < 12.0))
            is_interacting = (
                (self.face_detected or hand_present) and (
                    (now - self._last_interaction_time < 12.0)
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

        # ── STUDENT ID SCAN teaser: someone was seen, but not long enough for guest/user ──
        if self._last_state not in ('guest', 'user') and not self._transitioning:
            if self.face_detected:
                self._scan_tease_until = now + SCAN_TEASE_HOLD_SEC
                self._show_scan_callout()
            elif self._scan_tease_until and now >= self._scan_tease_until:
                self._hide_scan_callout()

        # ── Idle attract loop ─────────────────────────────────────────────
        self._update_idle_demo()

        # ── Gesture Inactivity Tutorial Overlay ───────────────────────────
        if self._demo_overlay_active():
            self._update_demo_hold(False)   # resets the bar if pinch packets stop arriving

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

        self._slide_timetable_out(animate=False)
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
            recent_barcode = (time.time() - getattr(self, '_last_barcode_scan_time', 0) < 60.0)
            auth = 'barcode' if recent_barcode else (getattr(self, '_auth_method', '') or fdata.get('auth_method', ''))
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
            self._hide_scan_callout()
            self._fade_out(visible, on_done=self._on_fade_to_idle_done)

        else:
            self._transitioning = False

    def _prepare(self, container, new_state, new_user_id, fdata):
        """Fill in and lay out a container before it is displayed."""
        if container is self.user_container:
            self._hide_scan_callout()
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

    def _on_fade_to_idle_done(self):
        if hasattr(self, 'telemetry') and self.telemetry is not None:
            self.telemetry.end_session()
        self._auth_method = ""
        self._hide_scan_callout()
        self.user_container.hide()
        self.guest_container.hide()
        self.user_container.setGraphicsEffect(None)
        self.guest_container.setGraphicsEffect(None)
        if hasattr(self, 'dwell_hint_pill'):
            self.dwell_hint_pill.hide()
        if hasattr(self, 'gesture_demo_overlay') and self.gesture_demo_overlay is not None:
            self.gesture_demo_overlay.hide()
            self._demo_pinch_start = None
            self._set_demo_hold_progress(0.0)
            if hasattr(self, 'demo_movie') and self.demo_movie is not None:
                self.demo_movie.stop()
        if self.kings_widget is not None:
            self.kings_widget.clear_selection()
        if hasattr(self, 'guest_kings_widget') and self.guest_kings_widget is not None:
            self.guest_kings_widget.clear_selection()
        self._transitioning = False

    def closeEvent(self, event):
        if hasattr(self, 'telemetry') and self.telemetry is not None:
            self.telemetry.end_session()
        for decoder in (self.demo_movie, getattr(self, 'idle_demo_movie', None)):
            if decoder is not None:
                decoder.shutdown()
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
    # Set Windows multimedia timer resolution to 1 ms so QTimer intervals
    # are actually honoured at 8/16 ms instead of the default ~15.6 ms.
    try:
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)
        _timer_period_set = True
    except Exception:
        _timer_period_set = False

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
        # Restore Windows timer resolution
        try:
            if _timer_period_set:
                import ctypes
                ctypes.windll.winmm.timeEndPeriod(1)
        except Exception:
            pass
    sys.exit(code)