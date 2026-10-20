"""
loopback_capture.py — camera readers that always hand back the newest frame.

FFmpegPipeCapture is a fallback for the Pi's v4l2loopback device: if OpenCV's
own V4L2 backend refuses /dev/video42, this reads it through an `ffmpeg` child
process instead, behind the same small cv2.VideoCapture interface the daemons
use (isOpened / read / set / get / release).

LatestFrameReader wraps any capture the same way. The daemons are slower than
the camera (the hand tracker manages ~16 fps on a Pi 5 against a 30 fps feed),
and V4L2 queues frames for them, so a plain cap.read() returns a picture that
is already a couple of frames old. Draining the capture on a thread and keeping
only the newest frame takes that queueing lag out of every gesture.
"""

import subprocess
import threading
import time

import numpy as np


class LatestFrameReader:
    """Drain `cap` on a thread; read() returns the newest frame not yet seen."""

    def __init__(self, cap):
        self._cap = cap
        self._cond = threading.Condition()
        self._frame = None
        self._seq = 0
        self._last_seq = 0
        self._alive = True
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self):
        failures = 0
        while self._alive:
            ok, frame = self._cap.read()
            if not ok or frame is None:
                failures += 1
                if failures > 100:              # ~1s of nothing: the camera is gone
                    break
                time.sleep(0.01)
                continue
            failures = 0
            with self._cond:
                self._frame = frame
                self._seq += 1
                self._cond.notify_all()
        with self._cond:
            self._alive = False
            self._cond.notify_all()

    def isOpened(self):
        return self._alive and self._cap.isOpened()

    def read(self, timeout=2.0):
        with self._cond:
            self._cond.wait_for(lambda: self._seq != self._last_seq or not self._alive,
                                timeout)
            if self._seq == self._last_seq:
                return False, None
            self._last_seq = self._seq
            return True, self._frame

    def set(self, prop, value):
        return self._cap.set(prop, value)

    def get(self, prop):
        return self._cap.get(prop)

    def release(self):
        self._alive = False
        self._thread.join(timeout=1.0)          # never release under a read in flight
        self._cap.release()
        with self._cond:
            self._cond.notify_all()


class FFmpegPipeCapture:
    def __init__(self, device, width=640, height=480, fps=30):
        self.device = device
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps)
        self._nbytes = self.width * self.height * 3

        self._cond = threading.Condition()
        self._frame = None
        self._seq = 0
        self._last_seq = 0
        self._alive = False
        self._proc = None

        try:
            self._proc = subprocess.Popen(
                self._build_cmd(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=None,                 # real ffmpeg errors land in the daemon's log
                bufsize=self._nbytes,
            )
        except Exception as e:               # ffmpeg missing, etc.
            print(f"[CAMERA] Could not start ffmpeg reader: {e}", flush=True)
            return

        self._alive = True
        threading.Thread(target=self._pump, args=(self._proc.stdout,), daemon=True).start()

    def _build_cmd(self):
        return [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-fflags", "nobuffer",
            "-f", "v4l2", "-input_format", "yuyv422",
            "-video_size", f"{self.width}x{self.height}",
            "-framerate", str(self.fps),
            "-i", self.device,
            "-pix_fmt", "bgr24", "-f", "rawvideo", "-",
        ]

    def _pump(self, out):
        try:
            while self._alive:
                buf = out.read(self._nbytes)         # blocks for one whole frame
                if len(buf) < self._nbytes:
                    break                            # EOF: ffmpeg exited
                frame = np.frombuffer(buf, np.uint8).reshape(self.height, self.width, 3)
                with self._cond:
                    self._frame = frame
                    self._seq += 1
                    self._cond.notify_all()
        except Exception:
            pass
        finally:
            with self._cond:
                self._alive = False
                self._cond.notify_all()

    # ── cv2.VideoCapture-compatible surface ──────────────────────────────────
    def isOpened(self):
        return self._proc is not None and self._alive and self._proc.poll() is None

    def read(self, timeout=5.0):
        with self._cond:
            self._cond.wait_for(lambda: self._seq != self._last_seq or not self._alive,
                                timeout)
            if self._seq == self._last_seq:          # timed out, or ffmpeg died
                return False, None
            self._last_seq = self._seq
            return True, self._frame.copy()

    def set(self, *_):
        return False                                 # size/fps are fixed by the loopback

    def get(self, *_):
        return 0.0

    def release(self):
        self._alive = False
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.wait(timeout=2)
            except Exception:
                pass
        with self._cond:
            self._cond.notify_all()
