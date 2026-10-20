"""Screensaver client/modes and the triple-click debug panel."""

import hashlib
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('MIRROR_SCREENSAVER_SYNC', '0')

from PyQt6.QtCore import QBuffer, QByteArray, QEvent, QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QMouseEvent

from tests.test_peek_stages import app, close_mirror, make_mirror
import screensaver
from screensaver import ScreensaverClient


def png_bytes(color):
    img = QImage(40, 30, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


class FakeServer:
    """Stands in for requests.get against /api/screensaver and its files."""

    def __init__(self):
        self.files = {}
        self.config = {"mode": "demo", "slide_seconds": 5, "slides": [], "logo": None}
        self.online = True

    def add(self, color, kind="slide"):
        data = png_bytes(color)
        sha = hashlib.sha256(data).hexdigest()
        self.files[f"/api/screensaver/files/{sha}.png"] = data
        entry = {"id": len(self.files), "kind": kind, "sha256": sha, "ext": "png",
                 "url": f"/api/screensaver/files/{sha}.png"}
        if kind == "logo":
            self.config["logo"] = entry
        else:
            self.config["slides"].append(entry)
        return entry

    def get(self, url, timeout=None, **_):
        if not self.online:
            raise ConnectionError("offline")
        server = self

        class Resp:
            status_code = 200

            def raise_for_status(self):
                if self.status_code != 200:
                    raise RuntimeError(self.status_code)

            def json(self):
                return server.config

        r = Resp()
        path = url.split("http://test", 1)[1]
        if path == "/api/screensaver":
            return r
        if path in server.files:
            r.content = server.files[path]
            return r
        r.status_code = 404
        return r


class TestScreensaverClient(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.server = FakeServer()
        self.patch = patch.object(screensaver.requests, "get", self.server.get)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def client(self):
        return ScreensaverClient("http://test", cache_dir=self.dir)

    def test_downloads_verifies_and_caches_the_slideshow(self):
        self.server.add("red")
        self.server.add("blue")
        self.server.config["mode"] = "slideshow"
        c = self.client()
        seen = []
        c.changed.connect(seen.append)
        self.assertTrue(c.sync_once())
        self.assertEqual(c.config["mode"], "slideshow")
        self.assertEqual(len(c.config["slides"]), 2)
        self.assertTrue(all(os.path.exists(p) for p in c.config["slides"]))
        self.assertEqual(len(seen), 1)
        self.assertTrue(c.sync_once())          # nothing changed: no second signal
        self.assertEqual(len(seen), 1)

        # Offline restart: the cached copy is used.
        self.server.online = False
        again = self.client()
        self.assertEqual(again.config["mode"], "slideshow")
        self.assertEqual(len(again.config["slides"]), 2)
        self.assertFalse(again.sync_once())

    def test_a_tampered_download_is_rejected(self):
        entry = self.server.add("red")
        self.server.files[entry["url"]] = b"not the image"
        self.server.config["mode"] = "slideshow"
        c = self.client()
        self.assertFalse(c.sync_once())
        self.assertEqual(c.config["mode"], "demo")

    def test_removed_images_are_deleted_and_an_empty_mode_falls_back(self):
        self.server.add("red")
        self.server.config["mode"] = "slideshow"
        c = self.client()
        c.sync_once()
        old = c.config["slides"][0]
        self.server.config["slides"] = []
        c.sync_once()
        self.assertFalse(os.path.exists(old))
        self.assertEqual(c.config["mode"], "demo")

    def test_logo_mode(self):
        self.server.add("white", kind="logo")
        self.server.config["mode"] = "logo"
        c = self.client()
        c.sync_once()
        self.assertEqual(c.config["mode"], "logo")
        self.assertTrue(os.path.exists(c.config["logo"]))


class TestScreensaverOnTheMirror(unittest.TestCase):
    def setUp(self):
        self.mirror = make_mirror()
        self.mirror.user_container.hide()
        self.mirror._last_state = 'idle'
        self.mirror._last_presence_time = 0.0
        self.paths = []
        for color in ("red", "green"):
            path = os.path.join(tempfile.mkdtemp(), f"{color}.png")
            with open(path, "wb") as f:
                f.write(png_bytes(color))
            self.paths.append(path)

    def tearDown(self):
        close_mirror(self.mirror)

    def _finish_fade(self):
        anim = self.mirror._idle_demo_anim
        anim.setCurrentTime(anim.duration())
        app.processEvents()

    def test_the_slideshow_plays_when_nobody_is_there(self):
        self.mirror.screensaver.config = {"mode": "slideshow", "slide_seconds": 4, "slides": self.paths, "logo": None}
        self.mirror._update_idle_demo()
        slides = self.mirror.idle_demo.slides
        self.assertEqual(self.mirror._idle_demo_mode, "slideshow")
        self.assertTrue(slides.isVisible())
        self.assertFalse(self.mirror.idle_demo.surface.isVisible())
        self.assertEqual(slides.current_path(), self.paths[0])
        self.assertTrue(slides._timer.isActive())
        slides._advance()
        slides._anim.setCurrentTime(slides._anim.duration())
        app.processEvents()
        self.assertEqual(slides.current_path(), self.paths[1])

        # Someone arrives: it fades away and stops.
        self.mirror._handle_gesture({"present": True, "timestamp": 1.0})
        self.assertEqual(self.mirror._idle_demo_phase, "leaving")
        self._finish_fade()
        self.assertFalse(slides._timer.isActive())
        self.assertGreater(self.mirror._screensaver_left_at, 0)

    def test_a_new_choice_from_the_admin_replaces_what_is_showing(self):
        self.mirror.screensaver.config = {"mode": "logo", "slide_seconds": 8, "slides": [], "logo": self.paths[0]}
        self.mirror._update_idle_demo()
        self._finish_fade()
        cfg = {"mode": "slideshow", "slide_seconds": 8, "slides": self.paths, "logo": None}
        self.mirror.screensaver.config = cfg
        self.mirror._on_screensaver_changed(cfg)
        self.assertEqual(self.mirror._idle_demo_phase, "ending")
        self._finish_fade()
        self.assertEqual(self.mirror._idle_demo_mode, "slideshow")

    def test_a_session_started_from_the_screensaver_says_so(self):
        self.mirror.screensaver.config = {"mode": "logo", "slide_seconds": 8, "slides": [], "logo": self.paths[0]}
        self.mirror._update_idle_demo()
        self.mirror._handle_gesture({"present": True, "timestamp": 1.0})
        self.mirror.telemetry.current_session = None
        self.mirror.telemetry._last_cfg_check = float("inf")
        self.mirror._transitioning = True
        self.mirror._last_state = 'guest'
        self.mirror._trigger_transition('guest', '', {'config': {}})
        sess = self.mirror.telemetry.current_session
        self.assertTrue(sess["from_screensaver"])
        self.assertEqual(sess["screensaver_mode"], "logo")


class TestDebugPanel(unittest.TestCase):
    def setUp(self):
        self.mirror = make_mirror()

    def tearDown(self):
        close_mirror(self.mirror)

    stamp = 1000

    def click(self, widget, kind=QEvent.Type.MouseButtonPress):
        TestDebugPanel.stamp += 120
        ev = QMouseEvent(kind, QPointF(5, 5), QPointF(5, 5), QPointF(5, 5), Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        ev.setTimestamp(TestDebugPanel.stamp) if hasattr(ev, "setTimestamp") else None
        self.mirror._click_watcher._last_stamp = None   # synthetic events share a timestamp
        app.sendEvent(widget, ev)

    def test_three_quick_clicks_open_it_and_three_more_close_it(self):
        panel = self.mirror.debug_overlay
        self.assertFalse(panel.isVisible())
        for _ in range(2):
            self.click(self.mirror.central_widget)
        self.assertFalse(panel.isVisible())
        self.click(self.mirror.central_widget)
        self.assertTrue(panel.isVisible())
        # A real fast triple-click: press, double-click, press — anywhere on the mirror.
        self.click(self.mirror.notices_widget)
        self.click(self.mirror.notices_widget, QEvent.Type.MouseButtonDblClick)
        self.click(self.mirror.notices_widget)
        self.assertFalse(panel.isVisible())

    def test_slow_clicks_do_not_open_it(self):
        watcher = self.mirror._click_watcher
        for _ in range(3):
            self.click(self.mirror.central_widget)
            watcher._presses = [t - 1.0 for t in watcher._presses]   # each a second apart
        self.assertFalse(self.mirror.debug_overlay.isVisible())

    def test_it_shows_gesture_face_and_system_information(self):
        self.mirror._handle_gesture({"present": True, "hand_x": 0.25, "hand_y": 0.5, "pinched": True,
                                     "region": "left", "fps": 17.5, "timestamp": 2.0})
        self.mirror._last_face_data = {"state": "user", "detected": True, "recognized": True,
                                       "user_name": "Kid", "user_id": "auth0|kid", "timestamp": time.time()}
        sections = dict(self.mirror._debug_snapshot())
        self.assertEqual(set(sections), {"Gesture", "Face", "Mirror", "System"})
        gesture = dict(sections["Gesture"])
        self.assertEqual(gesture["hand"], "present")
        self.assertIn("17.5 fps", gesture["engine"])
        self.assertIn("Kid", dict(sections["Face"])["recognised"])
        self.mirror.debug_overlay.toggle()
        self.assertIn("GESTURE", self.mirror.debug_overlay._label.text())


if __name__ == "__main__":
    unittest.main()
