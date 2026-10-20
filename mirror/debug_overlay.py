# mirror/debug_overlay.py
"""
Diagnostics panel for whoever is maintaining the mirror. Triple-click anywhere
with a mouse to open or close it (Esc also closes). Students never use a mouse,
so they can't open it by accident; gestures don't generate clicks.
"""

import html
import os
import subprocess
import time

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

TRIPLE_CLICK_SEC = 0.7


class TripleClickWatcher(QObject):
    """Application-wide event filter: calls `callback` on three quick mouse presses."""

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback
        self._presses = []
        self._last_stamp = None

    def eventFilter(self, obj, event):
        # A press the child ignores is re-sent to each parent; count it once.
        # A fast second click arrives as a double-click event, not a press.
        clicks = (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick)
        if event.type() in clicks and event.timestamp() != self._last_stamp:
            self._last_stamp = event.timestamp()
            now = time.monotonic()
            self._presses = [t for t in self._presses if now - t < TRIPLE_CLICK_SEC] + [now]
            if len(self._presses) >= 3:
                self._presses = []
                self._callback()
        return False


def read_system_stats():
    """CPU temperature, throttling and load on a Raspberry Pi (best effort)."""
    out = {}
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            out["cpu_temp"] = f"{int(f.read()) / 1000:.1f} °C"
    except Exception:
        pass
    try:
        raw = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=1).stdout
        value = int(raw.strip().split("=")[1], 16)
        flags = []
        if value & 0x1:
            flags.append("UNDER-VOLTAGE NOW")
        if value & 0x4:
            flags.append("THROTTLED NOW")
        if value & 0x10000:
            flags.append("under-voltage since boot")
        if value & 0x40000:
            flags.append("throttled since boot")
        out["power"] = ", ".join(flags) or "ok"
    except Exception:
        pass
    try:
        out["load"] = " ".join(f"{x:.2f}" for x in os.getloadavg())
    except Exception:
        pass
    try:
        with open("/proc/uptime") as f:
            secs = float(f.read().split()[0])
        out["uptime"] = f"{int(secs // 3600)}h {int(secs % 3600 // 60)}m"
    except Exception:
        pass
    return out


class DebugOverlay(QWidget):
    """Translucent panel listing `snapshot()`'s sections, refreshed 4×/second.

    snapshot() returns [(section title, [(label, value), ...]), ...].
    """

    def __init__(self, snapshot, parent=None):
        super().__init__(parent)
        self._snapshot = snapshot
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        self._label = QLabel(self)
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setStyleSheet("background: transparent; color: #e5e7eb; "
                                  "font-family: 'DejaVu Sans Mono', Consolas, monospace; font-size: 13px;")
        lay.addWidget(self._label)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.refresh)
        self.hide()

    def toggle(self):
        if self.isVisible():
            self._timer.stop()
            self.hide()
        else:
            self.refresh()
            self.show()
            self.raise_()
            self._timer.start()

    def refresh(self):
        try:
            sections = self._snapshot()
        except Exception as e:                     # never let diagnostics crash the mirror
            sections = [("Error", [("snapshot", repr(e))])]
        rows = []
        for title, items in sections:
            rows.append(f"<tr><td colspan=2 style='color:#60a5fa;padding-top:8px;font-weight:bold'>"
                        f"{html.escape(title.upper())}</td></tr>")
            for key, value in items:
                rows.append(f"<tr><td style='color:#9ca3af;padding-right:14px'>{html.escape(str(key))}</td>"
                            f"<td>{html.escape(str(value))}</td></tr>")
        self._label.setText("<table cellspacing=0>" + "".join(rows) +
                            "<tr><td colspan=2 style='color:#6b7280;padding-top:10px'>"
                            "triple-click or Esc to close</td></tr></table>")
        self.adjustSize()
        self.raise_()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QColor(255, 255, 255, 40))
        p.setBrush(QColor(8, 10, 14, 225))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)
        p.end()
