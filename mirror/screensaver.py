# mirror/screensaver.py
"""
What the mirror shows while nobody is in front of it, as chosen in the admin
dashboard:

  demo       the gesture demo video (handled by smart_mirror_pro's decoder)
  slideshow  uploaded images, crossfading every few seconds
  logo       one uploaded image, centred

ScreensaverClient polls the server for the choice and downloads the images into
~/.cache/smart-mirror/screensaver, so the screensaver keeps working while the
server is down. SlideshowView paints the slideshow or the logo.
"""

import hashlib
import json
import os
import threading
import time

import requests
from PyQt6.QtCore import QObject, Qt, QTimer, QVariantAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QWidget

from config import API_URL, CACHE_DIR

POLL_SEC = 60
FADE_MS = 1200
MODES = ("demo", "slideshow", "logo")


class ScreensaverClient(QObject):
    """Keeps a local copy of the screensaver settings and images."""

    # {"mode", "slide_seconds", "slides": [paths], "logo": path or None}
    changed = pyqtSignal(dict)

    def __init__(self, api_url=API_URL, cache_dir=None, parent=None):
        super().__init__(parent)
        self.api_url = api_url.rstrip("/")
        self.dir = cache_dir or os.path.join(CACHE_DIR, "screensaver")
        self.config = {"mode": "demo", "slide_seconds": 8, "slides": [], "logo": None}
        self.last_sync = 0.0
        self.last_error = ""
        self._signature = None
        self._stop = threading.Event()
        self._load_cached()

    # ── Public ───────────────────────────────────────────────────────────────

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._stop.set()

    # ── Internals ────────────────────────────────────────────────────────────

    def _config_path(self):
        return os.path.join(self.dir, "config.json")

    def _load_cached(self):
        try:
            with open(self._config_path()) as f:
                self._apply(json.load(f), emit=False)
        except Exception:
            pass

    def _run(self):
        while not self._stop.is_set():
            self.sync_once()
            self._stop.wait(POLL_SEC)

    def sync_once(self):
        try:
            res = requests.get(f"{self.api_url}/api/screensaver", timeout=8)
            res.raise_for_status()
            remote = res.json()
        except Exception as e:
            self.last_error = f"offline ({type(e).__name__})"
            return False
        os.makedirs(self.dir, exist_ok=True)
        wanted = list(remote.get("slides") or [])
        if remote.get("logo"):
            wanted.append(remote["logo"])
        for img in wanted:
            if not self._ensure_file(img):
                self.last_error = "could not download every image"
                return False       # keep showing the old set until all are here
        keep = {self._file_name(img) for img in wanted} | {"config.json"}
        for name in os.listdir(self.dir):
            if name not in keep:
                try:
                    os.remove(os.path.join(self.dir, name))
                except OSError:
                    pass
        try:
            tmp = self._config_path() + ".tmp"
            with open(tmp, "w") as f:
                json.dump(remote, f)
            os.replace(tmp, self._config_path())
        except OSError:
            pass
        self.last_sync, self.last_error = time.time(), ""
        self._apply(remote, emit=True)
        return True

    @staticmethod
    def _file_name(img):
        return f"{img['sha256']}.{img['ext']}"

    def _ensure_file(self, img):
        sha, ext = str(img.get("sha256", "")), str(img.get("ext", ""))
        if len(sha) != 64 or not ext.isalnum():
            return False
        path = os.path.join(self.dir, f"{sha}.{ext}")
        if os.path.exists(path):
            return True
        try:
            res = requests.get(f"{self.api_url}{img['url']}", timeout=30)
            res.raise_for_status()
        except Exception:
            return False
        if hashlib.sha256(res.content).hexdigest() != sha:   # corrupted or tampered
            return False
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            f.write(res.content)
        os.replace(tmp, path)
        return True

    def _apply(self, remote, emit):
        mode = remote.get("mode") if remote.get("mode") in MODES else "demo"
        slides = [os.path.join(self.dir, self._file_name(i)) for i in (remote.get("slides") or [])]
        slides = [p for p in slides if os.path.exists(p)]
        logo = None
        if remote.get("logo"):
            p = os.path.join(self.dir, self._file_name(remote["logo"]))
            logo = p if os.path.exists(p) else None
        if mode == "slideshow" and not slides or mode == "logo" and not logo:
            mode = "demo"           # nothing to show: fall back to the video
        cfg = {"mode": mode, "slide_seconds": max(3, int(remote.get("slide_seconds") or 8)),
               "slides": slides, "logo": logo}
        signature = json.dumps(cfg, sort_keys=True)
        self.config = cfg
        if emit and signature != self._signature:
            self._signature = signature
            self.changed.emit(dict(cfg))
        elif not emit:
            self._signature = signature


class SlideshowView(QWidget):
    """Full-screen crossfading slideshow, or a single centred image."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._paths = []
        self._images = []            # pre-scaled to this widget's size
        self._index = 0
        self._next = None
        self._fade = 0.0
        self._interval_ms = 8000

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(FADE_MS)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.valueChanged.connect(self._on_fade)
        self._anim.finished.connect(self._on_fade_done)

    def set_images(self, paths, seconds=8):
        """Show `paths` in turn (one path = a still logo)."""
        self.stop()
        self._paths = list(paths)
        self._interval_ms = max(3, int(seconds)) * 1000
        self._index, self._next, self._fade = 0, None, 0.0
        self._rescale()

    def current_path(self):
        return self._paths[self._index] if self._paths else None

    def start(self):
        if len(self._images) > 1:
            self._timer.start(self._interval_ms)
        self.update()

    def stop(self):
        self._timer.stop()
        self._anim.stop()
        self._next, self._fade = None, 0.0

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self):
        self._images = []
        for p in self._paths:
            img = QImage(p)
            if img.isNull():
                continue
            if self.width() > 0 and self.height() > 0:
                img = img.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            self._images.append(img)
        self._index = min(self._index, max(0, len(self._images) - 1))
        self.update()

    def _advance(self):
        if len(self._images) < 2 or self._anim.state() == QVariantAnimation.State.Running:
            return
        self._next = (self._index + 1) % len(self._images)
        self._anim.start()

    def _on_fade(self, v):
        self._fade = float(v)
        self.update()

    def _on_fade_done(self):
        if self._next is not None:
            self._index, self._next, self._fade = self._next, None, 0.0
        self.update()

    def _draw(self, painter, img, opacity):
        if img is None or opacity <= 0:
            return
        painter.setOpacity(opacity)
        painter.drawImage((self.width() - img.width()) // 2, (self.height() - img.height()) // 2, img)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0))
        if self._images:
            self._draw(painter, self._images[self._index], 1.0 - self._fade if self._next is not None else 1.0)
            if self._next is not None:
                self._draw(painter, self._images[self._next], self._fade)
        painter.end()
