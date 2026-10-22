# mirror/smart_mirror_pro.py
import gc
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

# The UI only uses OpenCV to decode and scale the demo video. Left at its
# default it fans every resize out over all four cores, competing in bursts
# with the hand tracker, which matters far more.
cv2.setNumThreads(1)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QVBoxLayout, QHBoxLayout, QGraphicsOpacityEffect, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QVariantAnimation, QEasingCurve, QRect, QRectF, QPoint, QPointF, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QFont, QFontDatabase, QImage, QKeySequence, QPainter, QColor, QPen, QPainterPath, QPixmap, QRadialGradient, QRegion

from config import *
from timing_config import (
    GESTURE_TUTORIAL_IDLE_SEC, GESTURE_TUTORIAL_DURATION_SEC, GESTURE_TUTORIAL_SPEED_FACTOR,
    IDLE_DEMO_FADE_IN_SEC, IDLE_DEMO_FADE_OUT_SEC, IDLE_DEMO_GAP_SEC,
    IDLE_DEMO_PRESENCE_FADE_SEC, IDLE_DEMO_RESUME_SEC,
)

from widgets.notices_widget import NoticesWidget
from widgets.timetable_widget import TimetableWidget
from widgets.clock_widget import ClockWidget
from widgets.kings_week_widget import KingsWeekWidget
from telemetry import TelemetryTracker
from screensaver import ScreensaverClient, SlideshowView
from debug_overlay import DebugOverlay, TripleClickWatcher, read_system_stats
from perf_watch import PaintStats, StallWatch
from log_forwarder import start_log_forwarder


def _setup_mirror_log_tee():
    """Ensure stdout and stderr are teed to mirror.log if not already redirected."""
    try:
        if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
            log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mirror.log')
            class _TeeStream:
                def __init__(self, original, file_obj):
                    self._orig = original
                    self._file = file_obj
                def write(self, s):
                    try:
                        self._orig.write(s)
                    except Exception:
                        pass
                    try:
                        self._file.write(s)
                        self._file.flush()
                    except Exception:
                        pass
                def flush(self):
                    try:
                        self._orig.flush()
                    except Exception:
                        pass
                    try:
                        self._file.flush()
                    except Exception:
                        pass

            f = open(log_path, 'a', encoding='utf-8', errors='replace')
            sys.stdout = _TeeStream(sys.stdout, f)
            sys.stderr = _TeeStream(sys.stderr, f)
    except Exception:
        pass


REF_WIDTH  = 1280
REF_HEIGHT = 800

# Gesture regions, mirroring gesture_engine.py.
GESTURE_REGION_LEFT  = 'left'
GESTURE_REGION_RIGHT = 'right'

TIMETABLE_DISPLAY_MS = 10_000       # timetable holds 10s, then slides away to king's week
TIMETABLE_ANIM_MS    = 460
INDICATOR_BAR_WIDTH  = 4
INDICATOR_BAR_HEIGHT = 100

KINGS_IDLE_MS        = 20_000

TUTORIAL_FIRST_DELAY_SEC = 5.0   # someone arrives (or scans): this long before the demo
MAGNET_REACH = 90            # px around a button within which the cursor is drawn towards it
MAGNET_PULL = 0.7            # how strongly (0 none, 1 straight onto its centre)
SIGNED_OUT_FACE_HOLD_SEC = 5.0   # after signing out, ignore their face until it's gone this long
SCAN_TEASE_HOLD_SEC = 4.0    # how long STUDENT ID SCAN stays up after a brief sighting
TEASER_VISIT_WINDOW_SEC = 15.0   # a visit starting this soon after the teaser came from it
PRACTICE_SLIDE_MS = 650      # video sliding aside for the practice (variant B)
PRACTICE_DONE_HOLD_MS = 1400  # "YOU'RE READY" stays this long before the overlay fades


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
    looped = pyqtSignal()          # a looping clip reached its end and started again

    def __init__(self, path, speed=1.0, parent=None):
        """path: one clip, or a list played one after another."""
        super().__init__(parent)
        self.paths = [path] if isinstance(path, str) else [p for p in path if p]
        self.path = self.paths[-1]
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
            for i, clip in enumerate(self.paths):
                cap = cv2.VideoCapture(clip)
                if i == 0:
                    self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                self.frame_count += int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
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
            shrinking = w < frame.shape[1]
            frame = cv2.resize(frame, (w, h),
                               interpolation=cv2.INTER_AREA if shrinking else cv2.INTER_LINEAR)
        # Qt's native 32-bit layout (BGRA bytes = Format_RGB32 on little-endian),
        # converted here on the decoder thread. Handing Qt 24-bit RGB made it
        # convert every frame again on the UI thread at paint time.
        bgra = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
        return QImage(bgra.data, w, h, 4 * w, QImage.Format.Format_RGB32).copy()

    def first_frame(self):
        """A still of the opening frame, shown while the overlay fades in."""
        try:
            cap = cv2.VideoCapture(self.paths[0])
            ok, frame = cap.read()
            cap.release()
            return self._to_image(frame) if ok else None
        except Exception:
            return None

    def run(self):
        # Lowest priority for this thread (and the decoder threads it starts):
        # the hand tracker comes first, and at worst the demo drops a frame.
        try:
            os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 15)
        except (AttributeError, OSError):
            pass                             # Windows: no per-thread niceness
        while True:
            with self._cond:
                self._cond.wait_for(lambda: self._playing or self._quit)
                if self._quit:
                    return
                gen, loop = self._generation, self._loop
            self._play_through(gen, loop)

    def _play_through(self, gen, loop):
        """Play the clips in order; looping, start again (emitting looped) after the last."""
        i, played = 0, False
        while True:
            result = self._play_clip(self.paths[i], gen)
            if result == 'stopped':
                return
            played = played or result == 'ended'
            i += 1
            if i < len(self.paths):
                continue
            if loop and played:
                self.looped.emit()
                i, played = 0, False
                continue
            with self._cond:
                if gen != self._generation:
                    return
                self._playing = False
            self.played_once.emit()
            return

    def _play_clip(self, path, gen):
        """'ended' at the end of the clip, 'missing' if it won't open, 'stopped' if interrupted."""
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return 'missing'
        fps = cap.get(cv2.CAP_PROP_FPS) or self.fps
        interval = 1.0 / (fps * self.speed)
        t0, shown = time.monotonic(), 0
        try:
            while True:
                with self._cond:
                    if gen != self._generation or self._quit:
                        return 'stopped'
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
                    return 'ended'
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
        if background is not None:
            # It covers its whole rect, so each new frame repaints only itself,
            # not the dimmed screen and widgets underneath.
            self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

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


class GestureDemoOverlay(QWidget):
    """The in-session tutorial: the video over the screen, dimmed.

    It used to be a see-through dark layer over the live screen. At 1920x1080
    on the Pi that meant every frame of the video, the pulsing scan hint and
    the practice made Qt redraw the whole guest screen underneath first: the
    UI fell to ~20 fps. Now it shows a dimmed snapshot of the screen taken
    when it opens, and is opaque, so nothing beneath is redrawn while it's up.
    """
    DIM = QColor(0, 0, 0, 184)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._backdrop = None

    def set_backdrop(self, pixmap):
        """A snapshot of what's behind (None: plain see-through dimming)."""
        if pixmap is not None and not pixmap.isNull():
            dimmed = QPixmap(pixmap)
            p = QPainter(dimmed)
            p.fillRect(dimmed.rect(), self.DIM)
            p.end()
            self._backdrop = dimmed
        else:
            self._backdrop = None
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, self._backdrop is not None)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._backdrop is not None:
            painter.drawPixmap(event.rect(), self._backdrop, event.rect())
        else:
            painter.fillRect(self.rect(), self.DIM)
        painter.end()


class IdleDemoScreen(QWidget):
    """The full-screen screensaver: the demo video, a slideshow, or a logo."""

    def __init__(self, decoder, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.surface = VideoSurface(self, background=QColor(0, 0, 0))
        self.slides = SlideshowView(self)
        self.slides.hide()
        self.decoder = decoder
        if decoder is not None:
            decoder.frame_ready.connect(self.surface.set_image)
        self.effect = QGraphicsOpacityEffect(self)
        self.effect.setOpacity(0.0)
        self.setGraphicsEffect(self.effect)

    def show_mode(self, mode):
        self.surface.setVisible(mode == 'demo')
        self.slides.setVisible(mode != 'demo')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.surface.setGeometry(self.rect())
        self.slides.setGeometry(self.rect())
        if self.decoder is not None:
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
        """Stop listening and wait for the thread: emitting after the owner is
        destroyed crashes Qt."""
        self.running = False
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.5)
        self._thread = None

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
                    if data and self.running:
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
    """The gesture trail: a short glowing ribbon behind a moving hand.

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
    _HEAD_TAU       = 0.018   # seconds for the head to close ~63% of the gap (was 35 ms: felt laggy)
    _PREDICT_SHARE  = 0.6     # extrapolate at most this share of one report interval
    _VELOCITY_BLEND = 0.5     # weight of the newest velocity sample
    _STILL_SQ       = 8 ** 2  # no trail unless the hand travelled this far (px²)
    _DOT_FADE_SEC   = 0.25    # how long the head lingers after the hand is lost

    def __init__(self, parent=None, own_window=False):
        """own_window: draw in a separate see-through window above the mirror.

        As a child widget, every trail repaint made Qt repaint the notices and
        cards beneath it too (in software, at 1920x1080), 80 times a second
        while a hand moved: the UI fell to ~30 fps just from hovering. In its
        own window the compositor blends it over the mirror instead, and only
        the trail itself is ever repainted.
        """
        if own_window:
            super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                             | Qt.WindowType.WindowStaysOnTopHint
                             | Qt.WindowType.WindowTransparentForInput
                             | Qt.WindowType.WindowDoesNotAcceptFocus
                             | Qt.WindowType.X11BypassWindowManagerHint)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        else:
            super().__init__(parent)
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            self.setStyleSheet("background: transparent; border: none;")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.own_window = own_window

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
        self._max_age = 0.16         # trail length in seconds (short: less to repaint)
        self._dirty = QRegion()

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(self._TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._active = False
        if not own_window:
            self.hide()

    def raise_(self):
        if not self.own_window:      # a window above the mirror already; restacking it is churn
            super().raise_()

    def setVisible(self, visible):
        # Kept mapped as a window: mapping and unmapping it at every hand
        # movement would be churn. An empty trail paints nothing.
        if self.own_window and not visible and self.parent() is not None and self.parent().isVisible():
            return
        super().setVisible(visible)

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
            self._dirty = QRegion()
            self.hide()
            return

        self._repaint_region()

    _REGION_BOXES = 12        # the trail is invalidated as about this many small boxes
    _CURSOR_R = 20            # cursor mode: the circle's radius (its halo reaches ~1.8x)

    def set_cursor_mode(self, on):
        """A circle where the hand is, instead of a trail (the tutorial).

        People couldn't find their hand during the tutorial: a trail only
        shows while the hand moves. The circle shows even when it's still,
        and shrinks and turns blue while pinched.
        """
        on = bool(on)
        if on != getattr(self, '_cursor_mode', False):
            self._cursor_mode = on
            self._ipoints.clear()
            self.update(self._dirty)

    def _region(self):
        """What to repaint: a chain of small boxes along the trail.

        One rectangle around the whole trail made Qt repaint everything beneath
        it (notices, cards) at the trail's full size, 80 times a second while a
        hand swept across: ~200 megapixels a second, enough to drop frames on
        the Pi. Boxes along the path cover a fraction of that.
        """
        if getattr(self, '_cursor_mode', False):
            region = QRegion()
            if self._rx is not None:
                reach = int(self._CURSOR_R * 1.8) + 4
                region += QRect(int(self._rx) - reach, int(self._ry) - reach, 2 * reach, 2 * reach)
            for rx, ry, _, _, _ in self._ripples:
                region += QRect(int(rx) - 30, int(ry) - 30, 60, 60)
            return region
        pts = [(p[0], p[1]) for p in self._ipoints]
        if self._rx is not None:
            pts.append((self._rx, self._ry))
        pad = 12
        region = QRegion()
        step = max(1, len(pts) // self._REGION_BOXES)
        for i in range(0, max(1, len(pts) - 1), step):
            seg = pts[i:i + step + 1]
            xs, ys = [p[0] for p in seg], [p[1] for p in seg]
            region += QRect(int(min(xs)) - pad, int(min(ys)) - pad,
                            int(max(xs) - min(xs)) + 2 * pad, int(max(ys) - min(ys)) + 2 * pad)
        for rx, ry, _, _, _ in self._ripples:
            region += QRect(int(rx) - 30, int(ry) - 30, 60, 60)
        return region

    def _repaint_region(self):
        region = self._region()
        self.update(region.united(self._dirty))
        self._dirty = region

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

        if getattr(self, '_cursor_mode', False):
            if self._rx is not None:
                alpha = self._dot_alpha(now)
                c = QPointF(self._rx, self._ry)
                rad = self._CURSOR_R * (0.75 if self._pinched else 1.0)
                # The mirror's accent blue: it stands out on the white practice
                # dot and on black alike. Deeper blue and smaller while pinched.
                cr, cg, cb = (37, 99, 235) if self._pinched else (56, 189, 248)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(cr, cg, cb, int(70 * alpha)))   # soft halo: easy to spot
                painter.drawEllipse(c, rad * 1.8, rad * 1.8)
                painter.setBrush(QColor(cr, cg, cb, int(245 * alpha)))
                painter.drawEllipse(c, rad, rad)
            painter.end()
            return

        # Trail: a fading ribbon behind a moving hand. A still hand draws
        # nothing — there is no cursor, only the trail while it moves.
        pts = self._ipoints
        moved = len(pts) >= 2 and (pts[-1][0] - pts[0][0]) ** 2 + (pts[-1][1] - pts[0][1]) ** 2 >= self._STILL_SQ
        if moved:
            # One stroke (it used to be three, a wide glow under a core): far
            # cheaper to draw, and the cursor is what people watch, not the glow.
            painter.setPen(QPen(QColor(r, g, b, 220), 5, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(self._smooth_path(pts))

        painter.end()


class OverscrollGlow(QWidget):
    """The soft half-circle at the edge of a list that has been pulled past its end."""

    MAX_DEPTH = 90          # px the glow reaches into the list at full stretch

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._area = QRect()
        self._edge = 'top'
        self._amount = 0.0      # 0..1
        self.hide()

    def set_glow(self, area, edge, amount):
        old = self._area
        self._area, self._edge, self._amount = QRect(area), edge, max(0.0, min(1.0, amount))
        if self._amount <= 0.0:
            self.hide()
            return
        if self.isHidden():
            self.show()
            self.raise_()
        self.update(old.united(self._area))    # only the list, not the whole screen

    def paintEvent(self, event):
        if self._amount <= 0.0 or self._area.isEmpty():
            return
        r = self._area
        depth = self.MAX_DEPTH * self._amount
        edge_y = r.top() if self._edge == 'top' else r.bottom()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipRect(r)
        painter.translate(r.center().x(), edge_y)
        painter.scale(r.width() * 0.55, depth)
        grad = QRadialGradient(QPointF(0, 0), 1.0)
        grad.setColorAt(0.0, QColor(255, 255, 255, int(40 + 70 * self._amount)))
        grad.setColorAt(0.7, QColor(255, 255, 255, int(18 + 30 * self._amount)))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawEllipse(QPointF(0, 0), 1.0, 1.0)
        painter.end()


class GuestScanCallout(QWidget):
    """The STUDENT ID SCAN callout (or one centred line of text), painted.

    Still: it used to pulse and its arrow bounced, which people didn't need
    and which repainted a full-width strip 30 times a second. set_fade() is
    only for fading in and out with the tutorial.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setStyleSheet("background: transparent;")

        self._fade = 1.0
        self.show_or = False      # "OR": over the tutorial, scanning is the other way in
        self.message = None       # set: one centred line instead (variant B's hint, "step back")

    def set_fade(self, f):
        self._fade = max(0.0, min(1.0, float(f)))
        self.update()

    def start(self):
        self.update()

    def stop(self):
        pass

    def paintEvent(self, event):
        alpha = int(255 * self._fade)
        w = self.width()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        def line(text, top, height, px, weight, spacing, a):
            font = painter.font()
            font.setFamily("Segoe UI")
            font.setPixelSize(px)
            font.setWeight(weight)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255, a))
            painter.drawText(QRect(0, int(top), w, height),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, text)

        if self.message:
            line(self.message, 0, self.height(), 46, QFont.Weight.Black, 7, alpha)
            painter.end()
            return

        steady = alpha
        if self.show_or:
            line("OR", 0, 28, 22, QFont.Weight.Bold, 6, int(steady * 0.7))
        line("STUDENT ID SCAN", 28, 50, 40, QFont.Weight.Black, 7, alpha)
        line("SCAN AGAIN TO SIGN OUT", 78, 24, 16, QFont.Weight.DemiBold, 3, int(steady * 0.6))

        # Arrow below, pointing at the scanner
        line("▼", 104, 56, 44, QFont.Weight.Black, 0, alpha)
        painter.end()


class PracticePanel(QWidget):
    """Variant B: a short hands-on practice beside the tutorial video.

    Two steps, then "YOU'RE READY": pinch the dot (twice, in two places), then
    pinch and drag a list to its end. Painted, not built from child widgets,
    so it fades as one piece and never fights the overlay's own fade. Flat
    panels and white type like the rest of the mirror: no outlines.
    """
    finished = pyqtSignal()

    TAPS = 2
    DOTS = ((0.32, 0.45), (0.70, 0.60))   # where the dot sits, as fractions of the play area
    DOT_R, DOT_HIT = 46, 120               # drawn radius, and how near a pinch counts (at scale 1)
    CARDS = 14                             # a long list, so there's real scrolling to do
    CARD_H, CARD_GAP, PAD = 64, 12, 18
    DESIGN_H = 380                         # the height these sizes were drawn for

    @property
    def scale(self):
        """Sizes grow with the panel (it's bigger on a bigger screen)."""
        return max(0.8, min(1.6, self.height() / self.DESIGN_H)) if self.height() > 0 else 1.0

    def dot_radius(self):
        return int(self.DOT_R * self.scale)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        # Nothing here animates on its own: it repaints only when something
        # changes (the hand moving onto the dot, a pinch, the list scrolling).
        # A 60 fps timer used to repaint it, and the tutorial beneath, nonstop.
        self._fade = 0.0
        self.reset()
        self.hide()

    def reset(self):
        self.step = 0              # 0 pinch the dot, 1 drag the list, 2 done
        self.steps_done = 0
        self._taps = 0
        self._hover = False
        self._scroll = 0.0
        self._flash_at = 0.0
        self.update()

    def set_fade(self, f):
        self._fade = max(0.0, min(1.0, float(f)))
        # Fully in, it paints every pixel, so nothing behind it is repainted.
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, self._fade >= 1.0)
        self.update()

    # ── geometry ──
    def play_rect(self):
        top = int(104 * self.scale)
        return QRect(0, top, self.width(), max(120, self.height() - top))

    def dot_center(self):
        r = self.play_rect()
        fx, fy = self.DOTS[min(self._taps, len(self.DOTS) - 1)]
        return QPointF(r.left() + fx * r.width(), r.top() + fy * r.height())

    def scroll_max(self):
        k = self.scale
        content = (self.PAD * 2 + self.CARDS * self.CARD_H + (self.CARDS - 1) * self.CARD_GAP) * k
        return max(1.0, content - self.play_rect().height())

    # ── input (hand position in this widget's coordinates) ──
    def handle(self, point, event, delta=0):
        changed = False
        if self.step == 0:
            c = self.dot_center()
            hover = math.hypot(point.x() - c.x(), point.y() - c.y()) <= self.DOT_HIT * self.scale
            changed = hover != self._hover
            self._hover = hover
            if event == "tap" and self._hover:
                self._taps += 1
                self._flash_at = time.monotonic()
                QTimer.singleShot(260, self.update)    # clear the flash
                changed = True
                if self._taps >= self.TAPS:
                    self._advance()
        elif self.step == 1 and event in ("scroll", "fling") and delta:
            self._scroll = max(0.0, min(self.scroll_max(), self._scroll + delta))
            changed = True
            if self._scroll >= self.scroll_max() - 1:
                self._advance()
        if changed:
            self.update()

    def _advance(self):
        self.step += 1
        self.steps_done = min(2, self.step)
        self._flash_at = time.monotonic()
        if self.step == 2:
            self.finished.emit()

    # ── drawing ──
    def paintEvent(self, event):
        if self._fade <= 0.0:
            return
        f = self._fade
        now = time.monotonic()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if f >= 1.0:
            painter.fillRect(self.rect(), QColor(0, 0, 0))     # opaque once fully in
        w = self.width()

        def text(t, rect, px, weight, color, alpha=1.0, spacing=0, align=Qt.AlignmentFlag.AlignLeft):
            font = painter.font()
            font.setFamily("Segoe UI")
            font.setPixelSize(px)
            font.setWeight(weight)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
            painter.setFont(font)
            c = QColor(color)
            c.setAlphaF(max(0.0, min(1.0, alpha * f)))
            painter.setPen(c)
            painter.drawText(rect, align | Qt.AlignmentFlag.AlignVCenter, t)

        k = self.scale

        def sz(v):
            return int(round(v * k))

        step_lbl = "PRACTICE" if self.step == 2 else f"PRACTICE  {self.step + 1} / 2"
        text(step_lbl, QRect(0, 0, w, sz(24)), sz(14), QFont.Weight.Bold, '#94a3b8', spacing=3)
        title = ("PINCH THE DOT", "PINCH AND DRAG TO SCROLL", "YOU'RE READY")[self.step]
        text(title, QRect(0, sz(26), w, sz(44)), sz(32), QFont.Weight.Black, '#ffffff', spacing=1)
        sub = (f"{self._taps} of {self.TAPS}", "Scroll to the end", "Explore the mirror")[self.step]
        text(sub, QRect(0, sz(70), w, sz(26)), sz(18), QFont.Weight.DemiBold, '#cbd5e1')

        area = self.play_rect()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(17, 17, 17, int(255 * f)))           # #111, like the notice cards
        painter.drawRoundedRect(QRectF(area), 8, 8)

        if self.step == 0:
            c = self.dot_center()
            flash = 1.0 if now - self._flash_at < 0.25 else 0.0     # a pinch landed
            dot = self.dot_radius()
            halo = dot + sz(18) + sz(26) * flash
            painter.setBrush(QColor(255, 255, 255, int((26 + 40 * flash) * f)))
            painter.drawEllipse(c, halo, halo)
            r = dot + sz(8) if self._hover else dot
            painter.setBrush(QColor(255, 255, 255, int(255 * f)))
            painter.drawEllipse(c, r, r)
        elif self.step == 1:
            painter.save()
            painter.setClipRect(area)
            pad, card_h = sz(self.PAD), sz(self.CARD_H)
            y = area.top() + pad - self._scroll
            for i in range(self.CARDS):
                if y > area.bottom() or y + card_h < area.top():
                    y += card_h + sz(self.CARD_GAP)
                    continue                         # off screen: skip
                card = QRectF(area.left() + pad, y, area.width() - 2 * pad, card_h)
                last = i == self.CARDS - 1
                painter.setBrush(QColor(30, 30, 30, int(255 * f)))
                painter.drawRoundedRect(card, 6, 6)
                painter.setBrush(QColor(56, 189, 248, int(255 * f)) if last else QColor(51, 65, 85, int(255 * f)))
                painter.drawRect(QRectF(card.left(), card.top(), 4, card.height()))
                if last:
                    text("THE END", card.adjusted(sz(20), 0, 0, 0).toRect(), sz(16), QFont.Weight.Black, '#ffffff', spacing=3)
                else:
                    painter.setBrush(QColor(42, 53, 72, int(255 * f)))
                    painter.drawRoundedRect(QRectF(card.left() + sz(20), card.top() + sz(16), card.width() * 0.32, sz(10)), 3, 3)
                    painter.drawRoundedRect(QRectF(card.left() + sz(20), card.top() + sz(36), card.width() * 0.62, sz(10)), 3, 3)
                y += card_h + sz(self.CARD_GAP)
            painter.restore()
            # how far there is to go, along the right edge
            track = QRectF(area.right() - 8, area.top() + 12, 3, area.height() - 24)
            painter.setBrush(QColor(255, 255, 255, int(40 * f)))
            painter.drawRoundedRect(track, 1.5, 1.5)
            done = track.height() * (self._scroll / self.scroll_max())
            painter.setBrush(QColor(255, 255, 255, int(255 * f)))
            painter.drawRoundedRect(QRectF(track.left(), track.top(), 3, done), 1.5, 1.5)
        else:
            c = QPointF(area.center())
            pop = 1.0
            painter.setBrush(QColor(255, 255, 255, int(255 * f)))
            pop = k
            painter.drawEllipse(c, 48 * pop, 48 * pop)
            pen = QPen(QColor(0, 0, 0, int(255 * f)), 8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath(QPointF(c.x() - 20 * pop, c.y() + 2 * pop))
            path.lineTo(c.x() - 6 * pop, c.y() + 16 * pop)
            path.lineTo(c.x() + 22 * pop, c.y() - 14 * pop)
            painter.drawPath(path)
        painter.end()


class SmartMirrorPro(QMainWindow):
    barcode_verified_signal = pyqtSignal(object, list, dict, bool, str)
    banner_fetched_signal = pyqtSignal(dict)
    server_status_signal = pyqtSignal(bool)
    version_fetched_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Mirror")
        self.setStyleSheet("background-color: #000000;")

        # ── Server connectivity & offline state ──────────────────────────
        self.server_is_down = False
        self._admin_banner_msg = ""
        self._admin_banner_level = "notice"

        # ── Cross-thread signal connections ──────────────────────────────
        self.barcode_verified_signal.connect(self._on_barcode_verified)
        self.banner_fetched_signal.connect(self._update_banner)
        self.server_status_signal.connect(self._on_server_status_changed)
        self.version_fetched_signal.connect(self._apply_server_version)

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
        # Gesture scrolls arrive ~15 times a second; this glides the content at
        # display rate instead of jumping on each one (see _momentum_tick).
        self._momentum_timer = QTimer(self)
        self._momentum_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._momentum_timer.setInterval(16)
        self._momentum_timer.timeout.connect(self._momentum_tick)
        self._momentum_velocity = 0.0     # fling speed, px/s
        self._momentum_target = None
        self._scroll_pending = 0.0        # px still to glide through
        self._scroll_frac = 0.0           # sub-pixel remainder
        self._scroll_last_tick = 0.0
        self._scroll_flinging = False
        # Overscroll: how far a list has been pulled past its end (px, + = past
        # the bottom). Held while the pinch is, springs back on release.
        self._overscroll = 0.0
        self._overscroll_target = None
        self._hand_pinched = False

        # ── Activity & Inactivity Timing ──────────────────────────────────
        self._last_activity_time = time.time()
        self._last_interaction_time = 0.0
        self._gesture_tutorial_idle_sec = GESTURE_TUTORIAL_IDLE_SEC
        self._demo_anim = None
        self._scrim_fading_out = False
        self._demo_pinch_start = None
        self._demo_pinch_last = 0.0
        self._scan_tease_until = 0.0
        self._scanned_this_visit = False   # they know about the ID scanner
        self._tutorial_wait = None         # seconds before the demo, when not the usual
        self._last_hand_time = 0.0
        self._signed_out_user = None       # their face is ignored until they step away
        self._signed_out_face_gone = 0.0
        self._teaser_shown_at = 0.0        # brief encounter: when the teaser first showed
        self._teaser_last_seen = 0.0
        self._teaser_variant = 'A'
        self._visit_from_splash = False    # this visit began as a guest from the idle screen
        self._practice_offered = False     # variant B's practice: once per visit at most

        # ── Idle attract loop (full-screen demo while nobody is there) ────
        self._last_presence_time = 0.0   # last face or hand seen, by anyone
        self._last_presence_source = ''
        self._idle_demo_phase = 'off'    # off | playing | ending | gap | restart | leaving
        self._idle_demo_anim = None
        self._idle_gap_timer = QTimer(self)
        self._idle_gap_timer.setSingleShot(True)
        self._idle_gap_timer.timeout.connect(self._end_idle_gap)
        self._idle_demo_mode = ''
        self._screensaver_left_at = 0.0
        self._last_udp_gesture = 0.0

        # ── Frame meter: how smoothly the UI thread is really running ─────
        # A 60 Hz tick that records how late each one fires. If painting or
        # anything else blocks the UI thread, ticks bunch up and this shows it.
        self._frame_gaps = []
        self._frame_last = time.monotonic()
        self._perf_logged = time.monotonic()
        self._frame_meter = QTimer(self)
        self._frame_meter.setTimerType(Qt.TimerType.PreciseTimer)
        self._frame_meter.timeout.connect(self._frame_meter_tick)
        self._frame_meter.start(16)
        # Logs where the UI thread is whenever it freezes (see perf_watch.py)
        self._stall_watch = StallWatch(lambda: self._frame_last).start()
        self._paint_stats = None
        if os.environ.get('MIRROR_PAINT_STATS') == '1':      # which widgets repaint, how much
            self._paint_stats = PaintStats().install(QApplication.instance())

        # ── Debug panel (triple-click with a mouse) ───────────────────────
        self._last_gesture_data = {}
        self._last_gesture_rx = 0.0
        self._gesture_packets = []        # arrival times, for packets/second
        self._last_face_data = {}
        self._sys_stats = {}
        self._sys_stats_at = 0.0
        self.debug_overlay = DebugOverlay(self._debug_snapshot, self.central_widget)
        self._click_watcher = TripleClickWatcher(self.debug_overlay.toggle, self)
        QApplication.instance().installEventFilter(self._click_watcher)

        # ── Telemetry & A/B Testing Tracker ───────────────────────────────
        self.telemetry = TelemetryTracker(api_url=API_URL)
        self.current_variant = "A"

        # ── Log Forwarder ──────────────────────────────────────────────────
        self.log_forwarder = None
        if os.environ.get('MIRROR_LOG_FORWARD', '1') != '0':
            self.log_forwarder = start_log_forwarder(background=True)

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
        self.banner_timer.start(15000)
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

    def _place_trail(self):
        """Lay the trail exactly over the mirror's content (its own window, or a child)."""
        trail = self.gesture_trail
        if trail.own_window:
            trail.setGeometry(QRect(self.central_widget.mapToGlobal(QPoint(0, 0)), self.central_widget.size()))
            if self.isVisible() and not trail.isVisible():
                trail.show()
        else:
            trail.setGeometry(0, 0, self.central_widget.width(), self.central_widget.height())
            trail.raise_()

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, 'gesture_trail'):
            self._place_trail()

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'gesture_trail'):
            self._place_trail()

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, 'gesture_trail') and self.gesture_trail.own_window:
            QWidget.setVisible(self.gesture_trail, False)

    def _fetch_server_version(self):
        """Asynchronously query server /health for dynamic version string."""
        def _worker():
            try:
                resp = requests.get(f"{API_URL}/health", timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    ver = data.get("version")
                    if ver:
                        self.version_fetched_signal.emit(str(ver))   # safe if the window is gone
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
        # Same look as the notice cards: flat #111 panel, accent stripe down the
        # left edge, big white text, no outline. Colours are set per level.
        self.banner_frame = QFrame(self.central_widget)
        self.banner_frame.setObjectName("BannerFrame")
        self.banner_frame.setFixedHeight(78)     # grows for long messages: _fit_banner
        self.banner_frame.hide()

        lay = QVBoxLayout(self.banner_frame)
        lay.setContentsMargins(26, 10, 26, 10)
        lay.setSpacing(4)
        lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.tag_lbl = QLabel("NOTICE", self.banner_frame)
        lay.addWidget(self.tag_lbl)

        self.banner_label = QLabel(self.banner_frame)
        self.banner_label.setWordWrap(True)
        self.banner_label.setStyleSheet(
            'font-family: "Segoe UI", system-ui, sans-serif; color: #ffffff; background: transparent; '
            'border: none; font-size: 22px; font-weight: 700;'
        )
        lay.addWidget(self.banner_label)

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
                font-size: 30px;
                font-weight: 700;
                color: #ffffff;
                background: transparent;
                border: none;
            }
        """)
        self.edge_arrow_label.setFixedSize(44, 40)
        self.edge_arrow_label.hide()

        # People pinch the arrow instead of reaching above it, so say what it
        # is, and let a pinch on it open the timetable too.
        self.edge_arrow_caption = QLabel("TIMETABLE", self.central_widget)
        self.edge_arrow_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edge_arrow_caption.hide()
        self._arrow_hover = None
        self._set_arrow_hover(False)

        # Sign out with a pinch (scanning the ID again does the same).
        self.sign_out_btn = QLabel("SIGN OUT", self.central_widget)
        self.sign_out_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sign_out_btn.setFixedSize(240, 64)
        self.sign_out_btn.hide()
        self._sign_out_hover = None
        self._set_sign_out_hover(False)

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

        # Pulled past the end of a list: a glow at that edge (see _apply_scroll)
        self.overscroll_glow = OverscrollGlow(self.central_widget)

        # Hand cursor (dot + trail), drawn above everything else
        self.gesture_trail = GestureTrailOverlay(
            self, own_window=os.environ.get('MIRROR_TRAIL_WINDOW') == '1')
        self.gesture_trail.setObjectName("GestureTrailOverlay")

    def _set_arrow_hover(self, hover):
        if hover == self._arrow_hover:
            return
        self._arrow_hover = hover
        color = '#ffffff' if hover else '#cbd5e1'
        self.edge_arrow_caption.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 16px; font-weight: 900; "
            f"letter-spacing: 2px; color: {color}; background: transparent;")

    def _set_sign_out_hover(self, hover):
        if hover == self._sign_out_hover:
            return
        self._sign_out_hover = hover
        fg, bg = ('#000000', '#ffffff') if hover else ('#ffffff', '#1e1e1e')
        self.sign_out_btn.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 20px; font-weight: 900; "
            f"letter-spacing: 3px; color: {fg}; background: {bg}; border: none; border-radius: 8px;")

    def _position_sign_out(self):
        """Bottom-left, under the notices: out of the way, easy to reach."""
        if not hasattr(self, 'sign_out_btn'):
            return
        if self._last_state == 'user' and not self._transitioning:
            self.sign_out_btn.move(24, self.height() - self.sign_out_btn.height() - 28)
            self.sign_out_btn.show()
            self.sign_out_btn.raise_()
        else:
            self.sign_out_btn.hide()
            self._set_sign_out_hover(False)

    def _magnet_targets(self):
        """Window rects of what the hand can press right now."""
        targets = [self._skip_rect(), self._sign_out_rect(), self._timetable_button_rect()]
        if self._demo_overlay_active() and self._practice_state == 'active' and self.practice_panel.step == 0:
            c = self.practice_panel.mapTo(self.central_widget, self.practice_panel.dot_center().toPoint())
            r = self.practice_panel.dot_radius()
            targets.append(QRect(c.x() - r, c.y() - r, 2 * r, 2 * r))
        return [t for t in targets if not t.isEmpty()]

    def _apply_magnet(self, data):
        """Draw the hand cursor towards a button it is near (a copy of data, moved).

        The hand jitters and the camera lags a little, so people overshot small
        targets. Within reach of a button the cursor is pulled onto it, more
        strongly the closer it gets, and the pinch lands where it's drawn.
        """
        W, H = self.width(), self.height()
        if not data.get("present") or W <= 0 or H <= 0:
            return data
        x, y = data.get("hand_x", 0.0) * W, data.get("hand_y", 0.0) * H
        best = None
        for rect in self._magnet_targets():
            c = rect.center()
            reach = max(rect.width(), rect.height()) / 2 + MAGNET_REACH
            d = math.hypot(c.x() - x, c.y() - y)
            if d < reach and (best is None or d / reach < best[0]):
                best = (d / reach, c)
        if best is None:
            return data
        pull = MAGNET_PULL * (1.0 - best[0]) ** 0.5
        c = best[1]
        moved = dict(data)
        moved["hand_x"] = (x + (c.x() - x) * pull) / W
        moved["hand_y"] = (y + (c.y() - y) * pull) / H
        return moved

    def _hand_near(self, rect, data):
        """Whether the hand cursor is inside rect (window coordinates)."""
        point = QPoint(int(data.get("hand_x", 0.0) * self.width()),
                       int(data.get("hand_y", 0.0) * self.height()))
        return rect.contains(point)

    def _sign_out_rect(self):
        if self.sign_out_btn.isHidden():
            return QRect()
        return self.sign_out_btn.geometry().adjusted(-24, -24, 24, 24)   # a hand is not a mouse

    def _timetable_button_rect(self):
        if self.edge_arrow_label.isHidden():
            return QRect()
        r = self.edge_arrow_label.geometry().united(self.edge_arrow_caption.geometry())
        return r.adjusted(-40, -20, 40, 24)

    def _position_guest_scan_callout(self):
        """Place STUDENT ID SCAN callout at bottom-center of the window."""
        if not hasattr(self, 'guest_scan_callout'):
            return
        sw = self.width()
        sh = self.height()
        ch = self.SCAN_CALLOUT_H
        cy = sh - ch - 4
        self.guest_scan_callout.setGeometry(0, cy, sw, ch)

    SCAN_CALLOUT_H = 165

    def _layout_demo_overlay(self, with_callout):
        """Centre the video, bar and hint in the space the callout leaves free."""
        self._demo_with_callout = with_callout
        self._place_demo()

    def _place_demo(self):
        """Lay out the tutorial: the video alone, or (practice_p → 1) beside the practice.

        Sized from the screen, as big as fits above SKIP and the scan hint.
        """
        if getattr(self, 'demo_surface', None) is None:
            return
        W, H = self.width(), self.height()
        top = self._banner_space()          # the notice banner stays visible above it
        free = H - top - (self.SCAN_CALLOUT_H if self._demo_with_callout else 0)
        foot = 22 + self.skip_btn.height()
        margin = 16
        avail_h = max(160, free - foot - 2 * margin)

        # The video alone: as big as fits, up to 70% of the width
        vw0 = min(int(W * 0.70), int(avail_h * 16 / 9), 1100)
        vh0 = vw0 * 9 // 16
        r0 = QRect((W - vw0) // 2, top + max(margin, (free - vh0 - foot) // 2), vw0, vh0)

        # With the practice: two columns
        gutter = 32
        col = (W - 3 * gutter) // 2
        vw1 = min(col, int(avail_h * 16 / 9), 900)
        vh1 = vw1 * 9 // 16
        ph = min(avail_h, max(vh1, int(col * 0.8)))
        top1 = top + max(margin, (free - ph - foot) // 2)
        r1 = QRect(W // 2 - gutter // 2 - vw1, top1 + (ph - vh1) // 2, vw1, vh1)
        panel = QRect(W // 2 + gutter // 2, top1, col, ph)

        t = QEasingCurve(QEasingCurve.Type.OutCubic).valueForProgress(self._practice_p)

        def mix(a, b):
            return int(round(a + (b - a) * t))

        video = QRect(mix(r0.x(), r1.x()), mix(r0.y(), r1.y()),
                      mix(r0.width(), r1.width()), mix(r0.height(), r1.height()))
        self.demo_surface.setGeometry(video)
        self.practice_panel.setGeometry(panel.translated(int(48 * (1 - t)), 0))
        self.practice_panel.set_fade(t)
        bottom = mix(r0.bottom(), max(r1.bottom(), panel.bottom()))
        self.skip_btn.move((W - self.skip_btn.width()) // 2, bottom + 22)
        self.practice_must_lbl.setGeometry(0, bottom + 22, W, self.skip_btn.height())

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
    @staticmethod
    def _demo_video(variant=''):
        """Path to a pre-scaled copy of the demo, or the full-size original.

        Decoding the 1080p original costs the Pi about twice what the 540p copy
        does, and that CPU comes straight out of the gesture tracker.
        """
        assets = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
        scaled = os.path.join(assets, f'gesture_demo_{variant}.mp4')
        return scaled if variant and os.path.exists(scaled) else os.path.join(assets, 'gesture_demo.mp4')

    @classmethod
    def _tutorial_clips(cls):
        """The tutorial's clips in order: assets/touchless_intro.mp4 (this display
        is not a touchscreen) when it exists, then the gesture demo."""
        intro = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'touchless_intro.mp4')
        demo = cls._demo_video('480p')     # decoding costs CPU the hand tracker needs: smallest copy that looks right
        if not demo.endswith('_480p.mp4'):
            demo = cls._demo_video('540p')
        return ([intro] if os.path.exists(intro) else []) + [demo]

    def _build_gesture_demo(self):
        has_video = os.path.exists(self._demo_video())

        # In-session tutorial: the demo over a semi-transparent dark overlay,
        # dismissed by pinching and holding.
        self.gesture_demo_overlay = GestureDemoOverlay(self.central_widget)
        self.gesture_demo_overlay.setObjectName("GestureDemoOverlay")
        # Placed by _place_demo, not a layout: in variant B the video slides
        # aside for the practice panel while it keeps playing.
        self._demo_with_callout = False
        self._practice_p = 0.0
        self.demo_movie = None
        self.demo_surface = VideoSurface(self.gesture_demo_overlay)
        self.demo_surface.setGeometry(0, 0, 720, 405)
        if has_video:
            self.demo_movie = DemoVideoDecoder(self._tutorial_clips(), GESTURE_TUTORIAL_SPEED_FACTOR, self)
            self.demo_movie.set_target_size(720, 405)
            self.demo_movie.frame_ready.connect(self.demo_surface.set_image)
            self.demo_surface.set_image(self.demo_movie.first_frame())
            self.demo_movie.looped.connect(self._on_demo_looped)

        self.practice_panel = PracticePanel(self.gesture_demo_overlay)
        self.practice_panel.finished.connect(self._on_practice_finished)
        self._practice_state = None      # None | pending | active | done
        self._practice_anim = None
        self._practice_started_at = 0.0

        # A big SKIP button beneath the video: point and pinch
        self.skip_btn = QLabel("SKIP", self.gesture_demo_overlay)
        self.skip_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.skip_btn.setFixedSize(260, 72)
        self._skip_hover = None
        self._set_skip_hover(False)
        # In its place while the practice is up: it can't be skipped.
        self.practice_must_lbl = QLabel("COMPLETE THE TUTORIAL TO CONTINUE", self.gesture_demo_overlay)
        self.practice_must_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.practice_must_lbl.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 20px; font-weight: 800; "
            "letter-spacing: 3px; color: #cbd5e1; background: transparent;")
        self.practice_must_lbl.hide()
        self.gesture_demo_overlay.hide()

        # Nobody at the mirror: the screensaver chosen in the admin dashboard
        # (the demo full screen, a slideshow, or a logo).
        self.idle_demo_movie = None
        if has_video:
            self.idle_demo_movie = DemoVideoDecoder(self._demo_video('720p'), GESTURE_TUTORIAL_SPEED_FACTOR, self)
            self.idle_demo_movie.played_once.connect(self._on_idle_demo_finished)
        self.idle_demo = IdleDemoScreen(self.idle_demo_movie, self.central_widget)
        self.idle_demo.hide()
        self.screensaver = ScreensaverClient(API_URL, parent=self)
        self.screensaver.changed.connect(self._on_screensaver_changed)
        if os.environ.get('MIRROR_SCREENSAVER_SYNC', '1') != '0':
            self.screensaver.start()

        # Guest-only: bouncing + pulsing STUDENT ID SCAN callout
        # Self-contained widget -- no nested QGraphicsOpacityEffect (avoids freeze).
        self.guest_scan_callout = GuestScanCallout(self.central_widget)
        self.guest_scan_callout.hide()
        # Variant B says this to someone passing by, in the middle of the screen.
        self.stand_close_hint = GuestScanCallout(self.central_widget)
        self.stand_close_hint.message = "STAND 1m AWAY TO INTERACT"
        self.stand_close_hint.hide()

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
        banner_h = self._banner_space()
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
        banner_h = self._banner_space()
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
            self._fit_banner(w - 32)
            self.banner_frame.setGeometry(16, 16, w - 32, self.banner_frame.height())

        if hasattr(self, 'guest_container') and not self.guest_container.isHidden():
            self._apply_guest_layout(w, h)

        if hasattr(self, 'user_container') and not self.user_container.isHidden():
            self._apply_user_layout(w, h)

        if hasattr(self, 'status_dot'):
            self.status_dot.move(w - 20, h - 20)

        if hasattr(self, 'sign_out_btn') and hasattr(self, '_transitioning'):
            self._position_sign_out()

        if hasattr(self, 'version_lbl'):
            self.version_lbl.move(16, h - 22)
            self.version_lbl.raise_()

        if hasattr(self, 'gesture_demo_overlay') and self.gesture_demo_overlay is not None:
            self.gesture_demo_overlay.setGeometry(0, 0, w, h)
            self._place_demo()
            if hasattr(self, 'guest_scan_callout') and self.guest_scan_callout.isVisible():
                self._position_guest_scan_callout()

        if getattr(self, 'idle_demo', None) is not None:
            self.idle_demo.setGeometry(0, 0, w, h)

        if hasattr(self, 'overscroll_glow'):
            self.overscroll_glow.setGeometry(0, 0, w, h)

        if hasattr(self, 'gesture_trail') and self.gesture_trail is not None:
            self._place_trail()

        if hasattr(self, 'debug_overlay'):
            self.debug_overlay.move(16, 16)
            if self.debug_overlay.isVisible():
                self.debug_overlay.raise_()


    # ─────────────────────────────────────────────────────────────────────
    # Banner polling & server status
    # ─────────────────────────────────────────────────────────────────────
    def _poll_banner(self):
        def worker():
            try:
                res = requests.get(f"{API_URL}/api/banner", timeout=4)
                if res.status_code == 200:
                    data = res.json()
                    self.banner_fetched_signal.emit({"message": data.get("message", "") or "",
                                                     "level": data.get("level", "notice") or "notice"})
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
        self._refresh_banner()

    # The admin's mirror-wide notice: one line across the top, for guests and
    # signed-in students alike. Hidden while the screensaver owns the screen.
    BANNER_STYLES = {
        # level:    label      accent
        'notice':  ('NOTICE',  '#3b82f6'),
        'warning': ('WARNING', '#f59e0b'),
        'urgent':  ('URGENT',  '#ef4444'),
    }

    def _update_banner(self, banner):
        if isinstance(banner, str):
            banner = {"message": banner, "level": "notice"}
        self._admin_banner_msg = banner.get("message", "") or ""
        level = banner.get("level", "notice")
        self._admin_banner_level = level if level in self.BANNER_STYLES else "notice"
        tag, accent = self.BANNER_STYLES[self._admin_banner_level]
        self.banner_frame.setStyleSheet(f"""
            #BannerFrame {{
                background-color: #111111;
                border: none;
                border-left: 8px solid {accent};
                border-radius: 6px;
            }}
        """)
        self.tag_lbl.setText(tag)
        self.tag_lbl.setStyleSheet(
            f'font-family: "Consolas", "SFMono-Regular", "Segoe UI", monospace; font-size: 13px; '
            f'font-weight: 800; letter-spacing: 2px; color: {accent}; background: transparent; border: none;'
        )
        self.banner_label.setText(self._admin_banner_msg)
        self._fit_banner(self.width() - 32)
        self.banner_frame.setGeometry(16, 16, self.width() - 32, self.banner_frame.height())
        self._refresh_banner(relayout=True)     # the height may have changed

    def _fit_banner(self, width=None):
        """Size the notice to its text: at least 78 px, taller if it wraps."""
        width = width or self.banner_frame.width()
        text_w = max(200, width - 26 * 2 - 8)
        h = (10 * 2 + 4 + self.tag_lbl.sizeHint().height()
             + self.banner_label.heightForWidth(text_w))
        self.banner_frame.setFixedHeight(max(78, h))

    def _banner_space(self):
        """Pixels the screens move down so the notice doesn't cover them."""
        if self.banner_frame.isHidden():
            return 0
        return self.banner_frame.y() + self.banner_frame.height() + 8

    def _refresh_banner(self, relayout=False):
        """Show the notice on the guest and user screens; never over the screensaver."""
        want = bool(self._admin_banner_msg) and self._last_state in ('guest', 'user')
        if want == self.banner_frame.isVisible() and not relayout:
            if want:
                self.banner_frame.raise_()
            return
        self.banner_frame.setVisible(want)
        if want:
            self.banner_frame.raise_()
        # The layouts make room for the banner.
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
    SCROLL_EASE_SEC = 0.07    # a scroll update is ~63% applied after this long
    FLING_DECAY_SEC = 0.28    # a fling loses ~63% of its speed after this long
    FLING_GAIN = 40.0         # engine fling delta -> starting speed in px/s

    def _scroll_smooth(self, target, delta):
        """A drag-scroll update: glide `target` by `delta` px over the next frames."""
        if target is not self._momentum_target:
            self._stop_momentum()
            self._momentum_target = target
        self._scroll_flinging = False
        self._momentum_velocity = 0.0          # the hand is in control again
        self._scroll_pending += float(delta)
        self._wake_scroller()

    def _start_momentum(self, target, velocity):
        """Release with speed: keep gliding and slow down naturally."""
        if target is not self._momentum_target:
            self._stop_momentum()
            self._momentum_target = target
        self._momentum_velocity = float(velocity) * self.FLING_GAIN
        self._scroll_flinging = True
        self._wake_scroller()

    def _wake_scroller(self):
        if not self._momentum_timer.isActive():
            self._scroll_last_tick = time.monotonic()
            self._momentum_timer.start()

    def _stop_momentum(self):
        if self._momentum_timer.isActive():
            self._momentum_timer.stop()
        self._momentum_velocity = 0.0
        self._momentum_target = None
        self._scroll_pending = 0.0
        self._scroll_frac = 0.0
        self._scroll_flinging = False
        if self._overscroll_target is not None:
            self._set_overscroll(self._overscroll_target, 0.0)

    # ── Overscroll ("rubber band"): show where a list ends ──────────────────
    OVERSCROLL_MAX = 140.0          # px a list can be pulled past its end
    OVERSCROLL_GIVE = 0.5           # first pixels past the end move half as far...
    OVERSCROLL_RETURN_SEC = 0.09    # ...and it springs back this quickly

    @staticmethod
    def _scroll_area_of(target):
        """The QScrollArea a gesture scroll of `target` actually moves, if any."""
        if getattr(target, 'modal_open', False):
            area = getattr(getattr(target, 'modal', None), 'scroll_area', None)
        else:
            area = getattr(target, 'scroll_area', None)
        return area if isinstance(area, QScrollArea) and area.isVisible() else None

    def _apply_scroll(self, target, step):
        """Scroll by `step` px; whatever would go past the end stretches instead."""
        area = self._scroll_area_of(target)
        if area is None:
            target.scroll_by_pixels(step)
            return
        sb = area.verticalScrollBar()
        o = self._overscroll if self._overscroll_target is target else 0.0
        if o and (step > 0) != (o > 0):
            back = min(abs(step), abs(o))          # moving back: undo the stretch first
            o -= math.copysign(back, o)
            step -= int(math.copysign(back, step))
        if step:
            room = (sb.maximum() - sb.value()) if step > 0 else (sb.minimum() - sb.value())
            inside = step if abs(step) <= abs(room) else room
            if inside:
                target.scroll_by_pixels(int(inside))
            excess = step - inside
            if excess:
                # Each extra pixel stretches less the further it has gone.
                give = self.OVERSCROLL_GIVE * max(0.0, 1.0 - abs(o) / self.OVERSCROLL_MAX)
                o += excess * give
        self._set_overscroll(target, o)

    def _set_overscroll(self, target, o):
        if self._overscroll_target is not None and self._overscroll_target is not target:
            self._set_overscroll(self._overscroll_target, 0.0)
        if abs(o) < 0.5:
            o = 0.0
        self._overscroll = o
        self._overscroll_target = target if o else None
        area = self._scroll_area_of(target)
        if area is None or area.widget() is None:
            self.overscroll_glow.set_glow(QRect(), 'top', 0.0)
            return
        # QScrollArea places its content at -value; nudge it past that.
        content = area.widget()
        content.move(content.x(), -area.verticalScrollBar().value() - int(round(o)))
        viewport = area.viewport()
        rect = QRect(viewport.mapTo(self.central_widget, QPoint(0, 0)), viewport.size())
        self.overscroll_glow.set_glow(rect, 'bottom' if o > 0 else 'top',
                                      abs(o) / (self.OVERSCROLL_MAX * self.OVERSCROLL_GIVE))

    def _momentum_tick(self):
        target = self._momentum_target or self._overscroll_target
        if target is None or not hasattr(target, 'scroll_by_pixels'):
            self._stop_momentum()
            return
        now = time.monotonic()
        dt = min(0.05, max(0.001, now - self._scroll_last_tick))   # time-based: same feel at any fps
        self._scroll_last_tick = now

        ease = self._scroll_pending * (1.0 - math.exp(-dt / self.SCROLL_EASE_SEC))
        self._scroll_pending -= ease
        move = ease + self._momentum_velocity * dt
        # A fling that runs into the end is soaked up quickly: a bounce.
        decay = self.FLING_DECAY_SEC if not self._overscroll else 0.04
        self._momentum_velocity *= math.exp(-dt / decay)

        self._scroll_frac += move
        step = int(self._scroll_frac)
        if step:
            self._scroll_frac -= step
            self._apply_scroll(target, step)

        # Released past the end: ease back to the edge.
        if self._overscroll and not self._hand_pinched:
            self._set_overscroll(target, self._overscroll * math.exp(-dt / self.OVERSCROLL_RETURN_SEC))

        if abs(self._scroll_pending) < 0.5 and abs(self._momentum_velocity) < 25.0:
            rest = int(round(self._scroll_frac + self._scroll_pending))
            if rest:                      # land exactly where the hand said
                self._apply_scroll(target, rest)
            self._scroll_pending = self._scroll_frac = self._momentum_velocity = 0.0
            if self._overscroll:
                if self._hand_pinched:    # still holding it stretched: wait for the release
                    self._momentum_timer.stop()
                return                    # otherwise keep ticking until it has sprung back
            flinging = self._scroll_flinging
            self._stop_momentum()
            if flinging and hasattr(target, 'snap_to_nearest_box'):
                target.snap_to_nearest_box()

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
        """The arrow between date and clock, and what reaching up (or pinching it) does next.

        Signed in: ▲ TIMETABLE while King's Week fills the column, ▼ KING'S WEEK
        while the timetable is showing. Guests: the smartmirror.me card instead.
        """
        if not hasattr(self, 'edge_arrow_label') or self.edge_arrow_label is None:
            return
        if hasattr(self, 'dwell_hint_pill'):
            self.dwell_hint_pill.hide()
        if self._last_state == 'user':
            up = self._timetable_slid_away
            caption = "TIMETABLE" if up else "KING'S WEEK"
        elif self._last_state == 'guest':
            up = self._guest_card_slid_away
            caption = "JOIN" if up else "KING'S WEEK"
        else:
            up = None
        if up is None or self._demo_overlay_active():     # nothing to toggle, or under the tutorial
            self.edge_arrow_label.hide()
            self.edge_arrow_caption.hide()
            return
        self.edge_arrow_label.setText("\u25b2" if up else "\u25bc")
        self.edge_arrow_caption.setText(caption)

        w = self.width()
        left_w = int(w * 0.50)
        content_x = left_w + 30
        content_w = (w - left_w) - 60
        top = self._banner_space()

        # Centred in the gap between the date and the clock: caption above the arrow
        aw, ah = self.edge_arrow_label.width(), self.edge_arrow_label.height()
        mid = content_x + content_w // 2
        clock = self.clock_widget if self._last_state == 'user' else self.guest_clock
        if clock.isVisible() and clock.date_label.text():
            d, t = clock.date_label, clock.time_label
            date_right = d.mapTo(self.central_widget, QPoint(0, 0)).x() + d.fontMetrics().horizontalAdvance(d.text())
            time_left = t.mapTo(self.central_widget, QPoint(0, 0)).x() + t.width() - t.fontMetrics().horizontalAdvance(t.text())
            if time_left > date_right:
                mid = (date_right + time_left) // 2
        arrow_x = mid - aw // 2
        arrow_y = top + 20 + (65 - ah) // 2 + 10
        self.edge_arrow_label.move(arrow_x, arrow_y)
        self.edge_arrow_label.show()
        self.edge_arrow_label.raise_()
        cap = self.edge_arrow_caption
        cap.adjustSize()
        cap.move(arrow_x + aw // 2 - cap.width() // 2, arrow_y - cap.height() + 6)
        cap.show()
        cap.raise_()

    # ─────────────────────────────────────────────────────────────────────
    # Gesture tutorial: pinch-and-hold to dismiss
    # ─────────────────────────────────────────────────────────────────────
    def _show_scan_callout(self):
        """Someone seen but not yet a visit: A says STUDENT ID SCAN, B says STAND CLOSE."""
        if not hasattr(self, 'guest_scan_callout'):
            return
        now = time.time()
        if not self._teaser_shown_at:            # a new encounter: pick its variant now
            self._teaser_shown_at = now
            self._teaser_variant = self.telemetry.peek_variant() if self.telemetry is not None else 'A'
        self._teaser_last_seen = now
        if self._teaser_variant == 'B':
            hint = self.stand_close_hint
            hint.setGeometry(0, (self.height() - 120) // 2, self.width(), 120)
        else:
            hint = self.guest_scan_callout
            self._position_guest_scan_callout()
            hint.show_or = False
        hint.set_fade(1.0)
        if not hint.isVisible():
            hint.show()
            hint.start()
        hint.raise_()

    def _hide_scan_callout(self):
        if hasattr(self, 'guest_scan_callout'):
            for hint in (self.guest_scan_callout, self.stand_close_hint):
                hint.stop()
                hint.hide()
        self._scan_tease_until = 0.0

    def _end_teaser(self, became_visit):
        """The brief encounter is over: either a visit began, or they walked on."""
        if not self._teaser_shown_at:
            return None
        variant, shown_for = self._teaser_variant, self._teaser_last_seen - self._teaser_shown_at
        self._teaser_shown_at = 0.0
        if not became_visit and self.telemetry is not None:
            self.telemetry.record_passerby(variant, shown_for)
        return variant

    def _demo_overlay_active(self):
        return (getattr(self, 'gesture_demo_overlay', None) is not None
                and self.gesture_demo_overlay.isVisible()
                and not self._scrim_fading_out)

    def _set_skip_hover(self, hover):
        if hover == self._skip_hover:
            return
        self._skip_hover = hover
        bg = '#38bdf8' if hover else '#ffffff'
        self.skip_btn.setStyleSheet(
            "font-family: 'Segoe UI', system-ui, sans-serif; font-size: 30px; font-weight: 900; "
            f"letter-spacing: 6px; color: #000000; background: {bg}; border: none; border-radius: 36px;")

    def _skip_rect(self):
        if not self._demo_overlay_active() or self.skip_btn.isHidden():
            return QRect()
        return QRect(self.skip_btn.mapTo(self.central_widget, QPoint(0, 0)), self.skip_btn.size())

    def _skip_tutorial(self):
        if self.telemetry is not None and self._practice_state != 'active':
            self.telemetry.record_tutorial_dismissed()   # (mid-practice, the fade records the skip)
        self._last_activity_time = time.time()     # so the idle timer doesn't instantly re-show it
        self._fade_out_gesture_scrim()

    def _tutorial_fully_shown(self):
        if self.gesture_demo_overlay.isVisible() and not self._scrim_fading_out:
            self.gesture_demo_overlay.setGraphicsEffect(None)
            if self._practice_state == 'pending':
                self._start_practice()      # beside the video straight away, not after it

    def _snapshot_behind_tutorial(self):
        """Give the tutorial a still of the screen behind it (see GestureDemoOverlay)."""
        overlay = self.gesture_demo_overlay
        if overlay is None or not overlay.isVisible() or self._scrim_fading_out:
            return
        fading_in = self._anim_in is not None and self._anim_in.state() == QPropertyAnimation.State.Running
        if fading_in:                       # mid-dissolve: see-through until it settles
            QTimer.singleShot(150, self._snapshot_behind_tutorial)
            return
        # grab() renders the whole widget tree: leave our own layers out of it.
        layers = [w for w in (overlay, self.guest_scan_callout, self.stand_close_hint,
                              self.debug_overlay)
                  if w is not None and w.isVisible()]
        if not self.gesture_trail.own_window and self.gesture_trail.isVisible():
            layers.append(self.gesture_trail)
        for w in layers:
            w.setVisible(False)
        try:
            shot = self.central_widget.grab()
        finally:
            for w in layers:
                w.setVisible(True)
        overlay.set_backdrop(shot)
        overlay.raise_()
        for w in (self.guest_scan_callout, self.gesture_trail):
            if w.isVisible():
                w.raise_()

    def _on_demo_looped(self):
        if self._practice_state == 'pending' and self._demo_overlay_active():
            self._start_practice()

    def _start_practice(self):
        """Slide the still-playing video aside and bring in the practice."""
        self._practice_state = 'active'
        self._practice_started_at = time.time()
        self.skip_btn.hide()                 # the practice has to be finished
        self.practice_must_lbl.show()
        self.practice_panel.reset()
        self.practice_panel.show()
        self.practice_panel.raise_()
        if self.telemetry is not None:
            self.telemetry.record_practice_shown()
        anim = QVariantAnimation(self)
        anim.setDuration(PRACTICE_SLIDE_MS)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)

        def step(v):
            self._practice_p = float(v)
            self._place_demo()
        anim.valueChanged.connect(step)
        # Decode at the new size once there, rather than scaling every frame.
        anim.finished.connect(lambda: self.demo_movie.set_target_size(
            self.demo_surface.width(), self.demo_surface.height()))
        anim.start()
        self._practice_anim = anim

    def _on_practice_finished(self):
        if self._practice_state != 'active':
            return
        self._practice_state = 'done'
        if self.telemetry is not None:
            self.telemetry.record_practice_ended(completed=True, steps=2,
                                                 seconds=time.time() - self._practice_started_at)
        self._last_activity_time = time.time()
        QTimer.singleShot(PRACTICE_DONE_HOLD_MS, self._fade_out_gesture_scrim)

    def _practice_point(self, data):
        """The hand cursor in the practice panel's coordinates."""
        p = QPoint(int(data.get("hand_x", 0.0) * self.width()), int(data.get("hand_y", 0.0) * self.height()))
        return QPointF(self.practice_panel.mapFrom(self.central_widget, p))

    def _show_gesture_scrim(self):
        """Play the tutorial over a dark overlay (no gestures for a while)."""
        if self.gesture_demo_overlay is None:
            return
        if self.gesture_demo_overlay.isVisible() and not getattr(self, '_scrim_fading_out', False):
            return

        self._scrim_fading_out = False
        self.gesture_demo_overlay.setGeometry(0, 0, self.width(), self.height())
        effect = QGraphicsOpacityEffect(self.gesture_demo_overlay)
        self.gesture_demo_overlay.setGraphicsEffect(effect)
        effect.setOpacity(0.0)

        self.gesture_demo_overlay.show()
        self.gesture_demo_overlay.raise_()
        self.gesture_trail.raise_()
        self.edge_arrow_label.hide()        # back once the tutorial closes
        self.edge_arrow_caption.hide()
        self.gesture_trail.set_cursor_mode(True)
        self.gesture_demo_overlay.set_backdrop(None)
        self._snapshot_behind_tutorial()    # (waits if the screen is still fading in)
        for n in (self.notices_widget, self.guest_notices):
            n.hold_auto_scroll(True)        # nobody can see it scroll under the tutorial

        self._set_skip_hover(False)
        self.skip_btn.show()
        self.practice_must_lbl.hide()

        # Guests who haven't scanned yet: the gesture OR the ID scanner. Once
        # they've scanned they know about it, so just the gesture.
        with_callout = self._last_state == 'guest' and not self._scanned_this_visit
        self._layout_demo_overlay(with_callout)
        self._tutorial_wait = None
        if hasattr(self, 'guest_scan_callout'):
            if with_callout:
                self.guest_scan_callout.show_or = True
                self.guest_scan_callout.set_fade(0.0)
                self._position_guest_scan_callout()
                self.guest_scan_callout.show()
                self.guest_scan_callout.raise_()  # above overlay
                self.guest_scan_callout.start()
            else:
                self._hide_scan_callout()


        # Variant B, first tutorial of a visit that began as a guest from the
        # idle screen: the practice slides in beside the video once it's shown.
        self._practice_state = None
        self._practice_p = 0.0
        self.practice_panel.hide()
        if (self.current_variant == 'B' and self._last_state == 'guest'
                and self._visit_from_splash and not self._practice_offered
                and self.demo_movie is not None):
            self._practice_offered = True
            self._practice_state = 'pending'
        self._place_demo()
        if self.demo_movie is not None:
            self.demo_movie.set_target_size(self.demo_surface.width(), self.demo_surface.height())

        if self.demo_movie is not None:
            self.demo_movie.play(loop=True)
        if self.telemetry is not None:
            self.telemetry.record_tutorial_shown()

        anim_in = QPropertyAnimation(effect, b"opacity", self)
        anim_in.setDuration(450)
        anim_in.setStartValue(0.0)
        anim_in.setEndValue(1.0)
        anim_in.valueChanged.connect(lambda v: self.guest_scan_callout.set_fade(v))
        # Once fully shown, remove the effect altogether. A widget carrying a
        # graphics effect (even a disabled one) is never treated as opaque, so
        # every video frame, pulse of the scan hint, or notices scroll step also
        # repainted the whole screen hidden beneath it: ~15 fps on the Pi.
        anim_in.finished.connect(self._tutorial_fully_shown)
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
        effect.setEnabled(True)

        current_opacity = effect.opacity()
        anim_out = QPropertyAnimation(effect, b"opacity", self)
        anim_out.setDuration(int(450 * max(0.1, current_opacity)))
        anim_out.setStartValue(current_opacity)
        anim_out.setEndValue(0.0)
        anim_out.valueChanged.connect(lambda v: self.guest_scan_callout.set_fade(v))

        if self._practice_state == 'active':     # left mid-practice (an ID scan, a screen change)
            self._practice_state = 'done'
            if self.telemetry is not None:
                self.telemetry.record_practice_ended(completed=False, steps=self.practice_panel.steps_done,
                                                     seconds=time.time() - self._practice_started_at)

        for n in (self.notices_widget, self.guest_notices):
            n.hold_auto_scroll(False)

        self.gesture_trail.set_cursor_mode(False)

        def on_done():
            self.gesture_demo_overlay.hide()
            self._hide_scan_callout()
            self._scrim_fading_out = False
            self._update_arrow_indicator()
            if self._practice_anim is not None:
                self._practice_anim.stop()
            self.practice_panel.hide()
            self._practice_p = 0.0
            if hasattr(self, 'demo_movie') and self.demo_movie is not None:
                self.demo_movie.stop()

        anim_out.finished.connect(on_done)
        anim_out.start()
        self._demo_anim = anim_out

    # ─────────────────────────────────────────────────────────────────────
    # Idle attract loop: the demo, full screen, while nobody is at the mirror
    #
    #   off ──(empty for IDLE_DEMO_RESUME_SEC)──▶ playing ──(clip ends)──▶ ending
    #    ▲                                          │                        │ 0.5 s fade
    #    │                    (anyone seen) ────────┴──▶ leaving ──▶ off     ▼
    #    └──────── still empty after 5 s of black: fade in, play ◀────────  gap
    # ─────────────────────────────────────────────────────────────────────
    def _screensaver_mode(self):
        mode = self.screensaver.config.get('mode', 'demo')
        if mode == 'demo' and self.idle_demo_movie is None:
            return ''                        # no video on this mirror: plain black
        return mode

    def _on_screensaver_changed(self, cfg):
        print(f"[IDLE] Screensaver set to {cfg['mode']} "
              f"({len(cfg['slides'])} slides, logo {'yes' if cfg['logo'] else 'no'}).", flush=True)
        if self._idle_demo_phase == 'playing':
            self._fade_idle_demo(IDLE_DEMO_FADE_OUT_SEC, 'restart')   # straight into the new choice

    def _idle_demo_wanted(self):
        if self.idle_demo is None or self._transitioning or not self._screensaver_mode():
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
        elif not wanted and self._idle_demo_phase == 'gap':
            self._idle_gap_timer.stop()          # already black: just stop
            self._idle_demo_phase = 'off'
            self.idle_demo.hide()
        elif not wanted and self._idle_demo_phase in ('playing', 'ending', 'restart'):
            self._fade_idle_demo(IDLE_DEMO_PRESENCE_FADE_SEC * self.idle_demo.effect.opacity(), 'leaving')

    def _start_idle_demo(self):
        demo = self.idle_demo
        mode = self._screensaver_mode()
        cfg = self.screensaver.config
        demo.setGeometry(0, 0, self.width(), self.height())
        if demo.isHidden():
            demo.surface.set_image(None)
            demo.effect.setOpacity(0.0)
            demo.show()
        demo.show_mode(mode)
        demo.raise_()
        for w in (self.guest_scan_callout, self.stand_close_hint, self.status_dot, self.version_lbl, self.gesture_trail):
            if w.isVisible():
                w.raise_()
        self._idle_demo_phase = 'playing'
        self._idle_demo_mode = mode
        print(f"[IDLE] Nobody here: showing the {mode} screensaver.", flush=True)
        if mode == 'demo':
            self.idle_demo_movie.set_target_size(self.width(), self.height())
            self.idle_demo_movie.play(loop=False)
        else:
            images = cfg['slides'] if mode == 'slideshow' else [cfg['logo']]
            demo.slides.set_images(images, cfg.get('slide_seconds', 8), logo=mode == 'logo')
            demo.slides.start()
        anim = self._animate_idle_demo(1.0, IDLE_DEMO_FADE_IN_SEC)
        # Fully opaque: drop the effect so each video frame isn't composited twice.
        anim.finished.connect(lambda: self.idle_demo.effect.setEnabled(False))

    def _on_idle_demo_finished(self):
        if self._idle_demo_phase == 'playing':
            self._fade_idle_demo(IDLE_DEMO_FADE_OUT_SEC, 'ending')

    def _fade_idle_demo(self, seconds, phase):
        if phase == 'ending':
            why = f'ended (then {IDLE_DEMO_GAP_SEC:.0f}s of black)'
        elif phase == 'restart':
            why = 'changed by an admin'
        elif self._last_state not in (None, 'idle'):
            why = f'stopped for the {self._last_state} screen'
        else:
            why = f'stopped: a {self._last_presence_source or "person"} was seen'
        print(f"[IDLE] Screensaver {why} — fading out over {seconds:.1f}s.", flush=True)
        if phase == 'leaving':
            self._screensaver_left_at = time.time()
        self._idle_demo_phase = phase
        anim = self._animate_idle_demo(0.0, seconds)
        anim.finished.connect(self._on_idle_demo_faded)

    def _on_idle_demo_faded(self):
        if self.idle_demo_movie is not None:
            self.idle_demo_movie.stop()
        self.idle_demo.slides.stop()
        phase, self._idle_demo_phase = self._idle_demo_phase, 'off'
        if phase == 'ending' and self._idle_demo_wanted():
            self._idle_demo_phase = 'gap'    # black screen, then play it again
            self._idle_gap_timer.start(int(IDLE_DEMO_GAP_SEC * 1000))
        elif phase == 'restart' and self._idle_demo_wanted():
            self._start_idle_demo()
        else:
            self.idle_demo.hide()

    def _end_idle_gap(self):
        if self._idle_demo_phase != 'gap':
            return
        self._idle_demo_phase = 'off'
        if self._idle_demo_wanted():
            self._start_idle_demo()
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

    def _frame_meter_tick(self):
        now = time.monotonic()
        self._frame_gaps.append(now - self._frame_last)
        self._frame_last = now
        if len(self._frame_gaps) > 240:             # ~4 s of history
            del self._frame_gaps[:len(self._frame_gaps) - 240]
        if self._paint_stats is not None:
            self._paint_stats.maybe_report()
        if now - self._perf_logged >= 30.0:
            self._perf_logged = now
            fps, worst = self._ui_frame_stats()
            engine = self._last_gesture_data.get("fps") if now - self._last_gesture_rx < 5 else None
            print(f"[PERF] UI {fps:.0f} fps, worst frame {worst:.0f} ms"
                  + (f", gesture engine {engine:.1f} fps" if engine else ""), flush=True)

    def _ui_frame_stats(self):
        gaps = self._frame_gaps[-120:]
        if not gaps:
            return 0.0, 0.0
        return len(gaps) / max(sum(gaps), 1e-6), 1000.0 * max(gaps)

    # ─────────────────────────────────────────────────────────────────────
    # Debug panel contents
    # ─────────────────────────────────────────────────────────────────────
    def _debug_snapshot(self):
        now = time.time()

        def age(t):
            return "never" if not t else f"{now - t:.1f}s ago"

        g = self._last_gesture_data
        gesture = [
            ("hand", "present" if g.get("present") else "none"),
            ("position", f"x={g.get('hand_x', 0):.3f}  y={g.get('hand_y', 0):.3f}  region={g.get('region')}"),
            ("pinched", g.get("pinched", False)),
            ("dwell", f"{g.get('right_dwell_progress', 0):.0%} ({g.get('dwell_side') or '-'})"),
            ("last event", f"{g.get('event') or '-'} (#{g.get('event_id', 0)})"),
            ("engine", f"{g['fps']:.1f} fps" if g.get("fps") else "fps unknown"),
            ("packets", f"{len(self._gesture_packets) / 2:.0f}/s, newest {age(self._last_gesture_rx)}"),
            ("source", "UDP" if now - self._last_udp_gesture < 1.0 else "status file"),
        ]
        f = self._last_face_data
        face = [
            ("daemon state", f.get("state", "no status file")),
            ("status file", age(f.get("timestamp"))),
            ("face", f"detected={f.get('detected', False)}  count={f.get('count', 0)}  in_grace={f.get('in_grace', False)}"),
            ("last face seen", age(f.get("last_face_time"))),
            ("recognised", f"{f.get('recognized', False)}  user={f.get('user_name') or '-'}"),
            ("user id", f.get("user_id", "-")),
            ("signed in by", f.get("auth_method") or "-"),
            ("server", "online" if f.get("server_online", True) and not self.server_is_down else "OFFLINE"),
        ]
        sess = self.telemetry.current_session if self.telemetry is not None else None
        ss = self.screensaver.config
        ui = [
            ("screen", f"{self._last_state or 'starting'}{' (transitioning)' if self._transitioning else ''}"),
            ("screensaver", f"{self._idle_demo_phase} · showing {self._idle_demo_mode or '-'} · set to {ss.get('mode')}"
                            f" ({len(ss.get('slides', []))} slides)"),
            ("screensaver sync", f"{age(self.screensaver.last_sync)} {self.screensaver.last_error}".strip()),
            ("someone seen", f"{age(self._last_presence_time)} ({self._last_presence_source or '-'})"),
            ("tutorial", "showing" if self._demo_overlay_active() else "hidden"),
            ("timetable", "collapsed" if self._timetable_slid_away else "showing"),
            ("A/B variant", self.current_variant),
            ("session", f"{sess['session_id']} {sess['session_type']} taps={sess['gesture_tap_count']} "
                        f"scrolls={sess['gesture_scroll_count']}" if sess else "none"),
            ("UI frame rate", "{:.0f} fps, worst frame {:.0f} ms".format(*self._ui_frame_stats())),
            ("window", f"{self.width()}×{self.height()}"),
        ]
        if now - self._sys_stats_at > 5:
            self._sys_stats, self._sys_stats_at = read_system_stats(), now
        system = [("mirror", f"{MIRROR_ID} {MIRROR_VERSION}"), ("server url", API_URL),
                  ("mirror key", "set" if MIRROR_API_KEY else "NOT SET")]
        system += list(self._sys_stats.items())
        return [("Gesture", gesture), ("Face", face), ("Mirror", ui), ("System", system)]

    # ─────────────────────────────────────────────────────────────────────
    # Gesture Dispatch
    # ─────────────────────────────────────────────────────────────────────
    def _handle_gesture(self, data):
        now = time.time()
        data = self._apply_magnet(data)
        self._last_gesture_data, self._last_gesture_rx = data, now
        self._gesture_packets = [t for t in self._gesture_packets if now - t < 2.0] + [now]
        if data.get("present", False):
            self._last_presence_time = time.time()   # a hand is someone, even at idle
            self._last_presence_source = 'hand'
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
            self._last_hand_time = time.time()
            # The slow auto-scroll repaints the whole notices column every step
            # (the gesture layer above it stops Qt from scrolling it cheaply):
            # it waits while someone is using the mirror.
            for n in (self.notices_widget, self.guest_notices):
                n.pause_auto_scroll(8.0)
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

        # A click lands where the pinch began (the engine says where): by the
        # time the fingers part the hand has drifted, and with the cursor's
        # lag that sent clicks to the wrong place.
        if event == "tap" and data.get("tap_x") is not None:
            data = self._apply_magnet(dict(data, hand_x=data["tap_x"], hand_y=data["tap_y"]))

        was_pinched, self._hand_pinched = self._hand_pinched, present and bool(data.get("pinched", False))
        if was_pinched and not self._hand_pinched and self._overscroll:
            self._wake_scroller()            # let go of a stretched list: spring back

        # While the tutorial is up, only its SKIP button (and the practice) respond.
        if self._demo_overlay_active():
            on_skip = present and self._hand_near(self._skip_rect(), data)
            self._set_skip_hover(on_skip)
            if on_skip:
                if event == "tap":
                    self._skip_tutorial()
                return
            if self._practice_state == 'active' and present:
                self.practice_panel.handle(self._practice_point(data), event, delta)
            return

        # Buttons the hand can pinch: SIGN OUT, and the TIMETABLE arrow.
        on_sign_out = present and self._hand_near(self._sign_out_rect(), data)
        self._set_sign_out_hover(on_sign_out)
        if on_sign_out:
            if event == "tap":
                self.sign_out(reason="button")
            return                       # nothing underneath reacts to it
        on_timetable = present and self._hand_near(self._timetable_button_rect(), data)
        self._set_arrow_hover(on_timetable)
        if on_timetable and event == "tap":
            self._last_activity_time = time.time()
            self._dwell_tap_lock = True  # the hand is in the dwell corner: don't toggle twice
            self._toggle_timetable_from_gesture()
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
                        self.telemetry.record_hand_seen()

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
                # The arrow and its caption stay: the bar fills in below them.

                w = self.width()
                left_w = int(w * 0.50)
                right_w = w - left_w
                content_x = left_w + 30
                content_w = right_w - 60
                top = self._banner_space()
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
        if getattr(self, '_dwell_tap_lock', False):
            dwell_trigger = False

        if right_dwell < 0.2:
            self._dwell_already_triggered = False
            self._dwell_tap_lock = False

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
            self._toggle_timetable_from_gesture()

        elif effective_region == GESTURE_REGION_LEFT and notices is not None:
            if event == "scroll" and delta != 0:
                if hasattr(notices, 'clear_selection'):
                    notices.clear_selection()
                self._scroll_smooth(notices, delta)
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
                    if hasattr(notices, 'select_at_point'):
                        notices.select_at_point(data.get("hand_x", 0.25), data.get("hand_y", 0.5))
                    if notices.activate_selected() and self.telemetry is not None:
                        self.telemetry.record_modal_open("notice")
                elif hasattr(notices, 'toggle_scroll_pause'):
                    notices.toggle_scroll_pause()
            elif event not in ("scroll", "fling") and not data.get("pinched"):   # hold still mid-pinch
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
                    if hasattr(active_target, 'clear_selection'):
                        active_target.clear_selection()
                    self._scroll_smooth(active_target, delta)
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
                        if self.telemetry is not None:
                            self.telemetry.record_kings_expand()
                    elif hasattr(active_target, 'modal_open') and active_target.modal_open:
                        active_target.close_modal()
                        if hasattr(self, 'telemetry') and self.telemetry is not None:
                            self.telemetry.record_modal_close()
                    else:
                        # Ensure a card is selected nearest to the hand before activating
                        if hasattr(active_target, 'focus_at'):
                            self._focus_kings_target(active_target, data)
                        if hasattr(active_target, 'activate_selected') and active_target.activate_selected():
                            if self.telemetry is not None:
                                self.telemetry.record_modal_open("article")
                elif event not in ("scroll", "fling") and not data.get("pinched"):
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


    def _toggle_timetable_from_gesture(self):
        """What reaching to the top right (or pinching the arrow) does."""
        if self.telemetry is not None:
            self.telemetry.record_timetable_toggle()
        if self._last_state == 'user':
            if self._timetable_slid_away:
                self._show_timetable(animate=True, is_initial_split=True)
            else:
                self._slide_timetable_out(animate=True)    # ▼ KING'S WEEK
        elif self._last_state == 'guest':
            if self._guest_card_slid_away:
                self._show_guest_card(animate=True, is_initial_split=False)
            else:
                self._slide_guest_card_out(animate=True)
        self._update_arrow_indicator()

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

                self._last_face_data = fdata
                self.face_detected   = fdata.get('detected', False)
                self.face_recognized = fdata.get('recognized', False)
                seen = now if self.face_detected else (fdata.get('last_face_time') or 0.0)
                if seen > self._last_presence_time:
                    self._last_presence_time = seen
                    self._last_presence_source = 'face'
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

            # ── Just signed out: don't let their face sign them straight back in ──
            if self._signed_out_user is not None:
                if self.face_detected:
                    self._signed_out_face_gone = 0.0
                elif not self._signed_out_face_gone:
                    self._signed_out_face_gone = now
                if self._signed_out_face_gone and now - self._signed_out_face_gone >= SIGNED_OUT_FACE_HOLD_SEC:
                    self._signed_out_user = None     # they stepped away; next time is a new visit
                elif new_state == 'user' and new_user_id == self._signed_out_user:
                    new_state, new_user_id = 'guest', 'guest'

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
            elif self._teaser_shown_at and now - self._teaser_last_seen > TEASER_VISIT_WINDOW_SEC:
                self._end_teaser(became_visit=False)     # they walked on

        # ── Idle attract loop ─────────────────────────────────────────────
        self._update_idle_demo()

        # ── Gesture Inactivity Tutorial Overlay ───────────────────────────
        if self._last_state in ('guest', 'user') and not self._transitioning:
            idle_threshold = self._tutorial_wait or getattr(self, '_gesture_tutorial_idle_sec', GESTURE_TUTORIAL_IDLE_SEC)
            # A raised hand is someone already trying: don't cover the screen.
            last_active = max(self._last_activity_time, self._last_hand_time)
            if time.time() - last_active >= idle_threshold:
                if not getattr(self, '_scrim_fading_out', False) and (self.gesture_demo_overlay is None or not self.gesture_demo_overlay.isVisible()):
                    self._last_activity_time = time.time()
                    self._show_gesture_scrim()

        self._position_sign_out()

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
        self._stop_momentum()
        self._refresh_banner()     # notice shows for guests and users, not when idle
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
            self._hide_scan_callout()      # the passer-by hint never outlives the encounter
            # Telemetry: Begin tracked session and assign A/B experiment variant
            recent_barcode = (time.time() - getattr(self, '_last_barcode_scan_time', 0) < 60.0)
            auth = 'barcode' if recent_barcode else (getattr(self, '_auth_method', '') or fdata.get('auth_method', ''))
            if not auth:
                auth = 'face' if new_state == 'user' else 'presence'

            uid = new_user_id if new_state == 'user' else None
            teaser_variant = None
            if is_from_idle and self._teaser_shown_at and time.time() - self._teaser_last_seen < TEASER_VISIT_WINDOW_SEC:
                teaser_variant = self._end_teaser(became_visit=True)
            if is_from_idle:
                self._visit_from_splash = new_state == 'guest'
                self._practice_offered = False
            sess = self.telemetry.current_session if self.telemetry is not None else None
            if sess is not None and sess['session_type'] == 'guest' and new_state == 'user':
                # Same visit: the guest was recognised or scanned their ID.
                self.telemetry.update_auth_method(auth, user_id=uid)
            elif incoming is not visible and self.telemetry is not None:
                self.current_variant = self.telemetry.start_session(
                    session_type=new_state, auth_method=auth, user_id=uid,
                    variant=teaser_variant, after_teaser=teaser_variant is not None,
                    from_screensaver=time.time() - self._screensaver_left_at < 30.0,
                    screensaver_mode=self._screensaver_mode())
            elif sess is not None:
                self.telemetry.update_auth_method(auth, user_id=uid)

            self._prepare(incoming, new_state, new_user_id, fdata)
            self._fade_in(incoming, retire=visible)
            if is_from_idle:
                # Give them a moment to look first; the demo comes if they don't start.
                self._last_activity_time = time.time()
                self._tutorial_wait = TUTORIAL_FIRST_DELAY_SEC

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
        self._scanned_this_visit = False
        self._tutorial_wait = None
        self._visit_from_splash = False
        self._hide_scan_callout()
        self.user_container.hide()
        self.guest_container.hide()
        self.user_container.setGraphicsEffect(None)
        self.guest_container.setGraphicsEffect(None)
        if hasattr(self, 'dwell_hint_pill'):
            self.dwell_hint_pill.hide()
        for n in (self.notices_widget, self.guest_notices):
            n.hold_auto_scroll(False)
        self.gesture_trail.set_cursor_mode(False)
        if hasattr(self, 'gesture_demo_overlay') and self.gesture_demo_overlay is not None:
            self.gesture_demo_overlay.hide()
            if hasattr(self, 'demo_movie') and self.demo_movie is not None:
                self.demo_movie.stop()
        if self.kings_widget is not None:
            self.kings_widget.clear_selection()
        if hasattr(self, 'guest_kings_widget') and self.guest_kings_widget is not None:
            self.guest_kings_widget.clear_selection()
        self._transitioning = False

    def closeEvent(self, event):
        self._stall_watch.stop()
        if hasattr(self, 'telemetry') and self.telemetry is not None:
            self.telemetry.end_session()
        for decoder in (self.demo_movie, getattr(self, 'idle_demo_movie', None)):
            if decoder is not None:
                decoder.shutdown()
        self.screensaver.stop()
        self.gesture_receiver.stop()
        # Nothing may tick after the window is gone: running animations call
        # back into widgets that are about to be destroyed.
        for name in ('_anim_in', '_anim_out', '_demo_anim', '_idle_demo_anim',
                     '_timetable_anim', '_kings_anim', '_guest_card_anim'):
            anim = getattr(self, name, None)
            if anim is not None:
                anim.stop()
        for timer in self.findChildren(QTimer):
            timer.stop()
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
            if self.debug_overlay.isVisible():
                self.debug_overlay.toggle()
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
        # Recognised or not, they've found the scanner: drop the demo, and
        # when it comes back it won't point at the scanner again.
        self._scanned_this_visit = True
        self._tutorial_wait = TUTORIAL_FIRST_DELAY_SEC
        self._hide_scan_callout()
        self._fade_out_gesture_scrim()

        def worker():
            try:
                res = requests.post(f"{API_URL}/api/verify-barcode", json={"barcode": code},
                                    headers=mirror_headers(), timeout=4.0)
                if res.status_code == 200:
                    data = res.json()
                    self.barcode_verified_signal.emit(data.get("user_id") or code, data.get("widgets", []),
                                                      data.get("config", {}), True, code)
                    return
                print(f"[BARCODE] Verify failed (HTTP {res.status_code}) for code: {code}")
            except Exception as e:
                print(f"[BARCODE] Verify error: {e}")
            self.barcode_verified_signal.emit(None, [], {}, False, code)

        threading.Thread(target=worker, daemon=True).start()

    def sign_out(self, reason="button"):
        """End the signed-in session (SIGN OUT button, or the same ID scanned again)."""
        if self._last_state != 'user':
            return
        user_id = self.current_user_id
        print(f"[SESSION] {user_id} signed out ({reason}).", flush=True)
        self.show_toast("✓ Signed out", is_success=True)
        self._signed_out_user = user_id
        self._signed_out_face_gone = 0.0
        self._auth_method = ""
        self.face_recognized = False
        self.current_user_id = None
        target_state = 'guest' if self.face_detected else 'idle'
        self._last_state = target_state
        self._last_user_id = None
        self._last_activity_time = time.time()
        self._tutorial_wait = TUTORIAL_FIRST_DELAY_SEC
        self._write_face_data({
            "state": target_state,
            "user_id": target_state,
            "recognized": False,
            "detected": bool(self.face_detected),
            "auth_method": "",
            "timestamp": time.time(),
        })
        self._position_sign_out()
        self._trigger_transition(target_state, None, {'state': target_state})

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
            # Scanning the same ID again signs out
            if self._last_state == 'user' and self.current_user_id == user_id:
                self.sign_out(reason="barcode")
                return

            print(f"[BARCODE] Sign-in accepted for {user_id}")
            self._auth_method = "barcode"
            self._barcode_auth_time = time.time()
            if hasattr(self, 'telemetry') and self.telemetry is not None:
                if self.telemetry.current_session:
                    self.telemetry.update_auth_method("barcode", user_id=user_id)
                else:
                    self.current_variant = self.telemetry.start_session(
                        session_type="user", auth_method="barcode", user_id=user_id)

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
    _setup_mirror_log_tee()
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
    # Garbage collection pauses everything; a full pass over every Qt wrapper
    # took ~100 ms on the Pi, often mid-gesture. Everything built so far lives
    # for the whole run, so freeze it out of future passes, and collect less often.
    gc.collect()
    gc.freeze()
    gc.set_threshold(5000, 20, 20)
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
        if hasattr(mirror, 'log_forwarder') and mirror.log_forwarder:
            try:
                mirror.log_forwarder.sync_once(force=True)
                mirror.log_forwarder.stop()
            except Exception:
                pass
        # Restore Windows timer resolution
        try:
            if _timer_period_set:
                import ctypes
                ctypes.windll.winmm.timeEndPeriod(1)
        except Exception:
            pass
    sys.exit(code)