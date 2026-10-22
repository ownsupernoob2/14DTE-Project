"""
perf_watch.py — find out what freezes the UI thread.

A smooth cursor needs the Qt thread free every 16 ms. When something holds it
for longer, the cursor stops and then jumps. StallWatch runs on its own thread,
notices when the UI's frame meter stops ticking, and logs where the UI thread
was at that moment:

    [STALL] UI blocked 140 ms in smart_mirror_pro.py:2210 _update_inputs <- ...

It also times Python's garbage collector, whose full collections can stop
everything for tens of milliseconds:

    [GC] gen 2 collection took 85 ms
"""

import gc
import os
import sys
import threading
import time
import traceback

STALL_MS = 80          # report the UI being stuck at least this long
REPORT_EVERY_SEC = 3   # at most one report this often (the log mustn't become the stall)
GC_REPORT_MS = 15


class StallWatch:
    def __init__(self, heartbeat, main_thread_id=None):
        """heartbeat(): monotonic time of the UI's last frame tick."""
        self._heartbeat = heartbeat
        self._main = main_thread_id or threading.main_thread().ident
        self._alive = True
        self._last_report = 0.0
        self._gc_start = {}
        self.stalls = 0

    def start(self):
        gc.callbacks.append(self._on_gc)
        threading.Thread(target=self._run, name="stall-watch", daemon=True).start()
        return self

    def stop(self):
        self._alive = False
        if self._on_gc in gc.callbacks:
            gc.callbacks.remove(self._on_gc)

    def _on_gc(self, phase, info):
        gen = info.get("generation", 0)
        if phase == "start":
            self._gc_start[gen] = time.perf_counter()
        elif gen in self._gc_start:
            ms = 1000 * (time.perf_counter() - self._gc_start.pop(gen))
            if ms >= GC_REPORT_MS:
                print(f"[GC] gen {gen} collection took {ms:.0f} ms "
                      f"({info.get('collected', 0)} freed)", flush=True)

    def _run(self):
        reported_for = None
        while self._alive:
            time.sleep(0.02)
            beat = self._heartbeat()
            blocked = time.monotonic() - beat
            if blocked * 1000 < STALL_MS or beat == reported_for:
                continue
            reported_for = beat                       # one report per stall
            self.stalls += 1
            now = time.monotonic()
            if now - self._last_report < REPORT_EVERY_SEC:
                continue
            self._last_report = now
            frame = sys._current_frames().get(self._main)
            where = "?"
            if frame is not None:
                stack = traceback.extract_stack(frame)[-4:]
                where = " <- ".join(f"{os.path.basename(f.filename)}:{f.lineno} {f.name}"
                                    for f in reversed(stack))
            print(f"[STALL] UI blocked {blocked * 1000:.0f}+ ms in {where}", flush=True)


class PaintStats:
    """Which widgets repaint, how often, and how much screen they cover.

    Install with MIRROR_PAINT_STATS=1; every REPORT_SEC it logs the busiest:
        [PAINT] GuestScanCallout x30/s 1920x210, VideoSurface x24/s 720x405 ...
    Software painting at 1920x1080 is costly, so area x rate is what to look at.
    """
    REPORT_SEC = 15

    def __init__(self):
        from PyQt6.QtCore import QObject
        from PyQt6.QtGui import QPaintEvent
        from PyQt6.QtWidgets import QWidget

        stats = self

        class _Filter(QObject):
            def eventFilter(self, obj, event):
                if isinstance(event, QPaintEvent) and isinstance(obj, QWidget):
                    r = event.rect()
                    key = obj.objectName() or type(obj).__name__
                    parent = obj.parent()
                    if parent is not None and not obj.objectName():
                        key += "<" + (parent.objectName() or type(parent).__name__)
                    effect = obj.graphicsEffect()
                    if effect is not None and effect.isEnabled():
                        key += "[effect]"
                    n, area = stats._counts.get(key, (0, 0))
                    stats._counts[key] = (n + 1, area + r.width() * r.height())
                return False

        self._filter = _Filter()
        self._counts = {}
        self._since = time.monotonic()

    def install(self, app):
        app.installEventFilter(self._filter)
        return self

    def maybe_report(self):
        now = time.monotonic()
        secs = now - self._since
        if secs < self.REPORT_SEC:
            return
        top = sorted(self._counts.items(), key=lambda kv: kv[1][1], reverse=True)[:8]
        mpix = sum(a for _, a in self._counts.values()) / secs / 1e6
        parts = [f"{k} x{n / secs:.0f}/s {a / secs / 1e6:.2f}Mpx/s" for k, (n, a) in top]
        print(f"[PAINT] {mpix:.1f} Mpx/s painted: " + ", ".join(parts), flush=True)
        self._counts.clear()
        self._since = now
