#!/usr/bin/env python3
"""Log Forwarder for Smart Mirror.

Continuously monitors daemon log files on the mirror:
  - mirror.log
  - face_daemon.log
  - gesture_daemon.log
  - rpicam.log
  - ffmpeg.log

When changes are detected, sends the latest lines to the server endpoint
POST /api/logs with the mirror's API key header (X-Mirror-Key).
"""

import argparse
import json
import os
import sys
import tempfile
import threading
import time

try:
    import requests
except ImportError:
    requests = None

from config import API_URL, LOG_DIR, LOG_FILES, MIRROR_ID, mirror_headers

LOCK_FILE = os.path.join(
    os.environ.get("TEMP", os.environ.get("TMP", "/tmp")),
    "smartmirror_log_forwarder.pid"
)


def read_tail(filepath, max_lines=500, max_bytes=256 * 1024):
    """Read the last N lines of a file efficiently without loading the whole file."""
    if not os.path.isfile(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size == 0:
                return ""
            read_size = min(size, max_bytes)
            f.seek(size - read_size)
            chunk = f.read()
            lines = chunk.splitlines()
            if size > read_size and len(lines) > 1:
                # Discard partial first line if we seeked into middle of file
                lines = lines[1:]
            return "\n".join(lines[-max_lines:])
    except Exception as e:
        return f"[Error reading log: {e}]"


class LogForwarder:
    """Monitors local mirror log files and posts updates to the server."""

    def __init__(self, api_url=None, log_dir=None, interval=2.5, heartbeat_interval=30.0):
        self.api_url = (api_url or API_URL).rstrip("/")
        self.log_dir = log_dir or LOG_DIR
        self.interval = interval
        self.heartbeat_interval = heartbeat_interval
        self._running = False
        self._thread = None
        self._last_stats = {}  # {name: (st_mtime, st_size)}
        self._last_sync_time = 0.0
        self._backoff = 0.0

    def sync_once(self, force=False):
        """Check all configured log files and send changed ones to the server."""
        if requests is None:
            print("[LOG_FORWARDER] Python 'requests' module is missing. Cannot forward logs.")
            return False

        now = time.time()
        heartbeat_due = (now - self._last_sync_time) >= self.heartbeat_interval
        changed_logs = {}

        for name, filename in LOG_FILES.items():
            filepath = os.path.join(self.log_dir, filename)
            if not os.path.isfile(filepath):
                continue
            try:
                stat = os.stat(filepath)
                curr_stats = (stat.st_mtime, stat.st_size)
            except OSError:
                continue

            last_stat = self._last_stats.get(name)
            if force or heartbeat_due or last_stat != curr_stats:
                content = read_tail(filepath, max_lines=500)
                if content is not None:
                    changed_logs[name] = content

        if not changed_logs:
            return True

        payload = {
            "mirror_id": MIRROR_ID,
            "logs": changed_logs,
        }

        url = f"{self.api_url}/api/logs"
        headers = mirror_headers()
        headers["Content-Type"] = "application/json"

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=5)
            if resp.status_code == 404:
                # Fallback to /api/mirror/logs if /api/logs returns 404
                alt_url = f"{self.api_url}/api/mirror/logs"
                resp = requests.post(alt_url, json=payload, headers=headers, timeout=5)

            if resp.status_code == 200:
                self._last_sync_time = now
                self._backoff = 0.0
                # Record successful sync stats
                for name in changed_logs:
                    filepath = os.path.join(self.log_dir, LOG_FILES[name])
                    try:
                        stat = os.stat(filepath)
                        self._last_stats[name] = (stat.st_mtime, stat.st_size)
                    except OSError:
                        pass
                return True
            else:
                print(f"[LOG_FORWARDER] Server responded HTTP {resp.status_code}: {resp.text[:100]}")
                self._backoff = min(10.0, self._backoff + 2.0)
                return False
        except Exception as e:
            # Network error or timeout, silently backoff
            self._backoff = min(10.0, self._backoff + 2.0)
            return False

    def run(self):
        """Continuous polling loop."""
        self._running = True
        print(f"[LOG_FORWARDER] Monitoring logs in {self.log_dir} -> {self.api_url}/api/logs")
        # Initial push of current logs
        self.sync_once(force=True)

        while self._running:
            sleep_time = self.interval + self._backoff
            time.sleep(sleep_time)
            if not self._running:
                break
            self.sync_once(force=False)

    def start(self):
        """Start the forwarder in a background daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self.run, daemon=True, name="LogForwarderThread")
        self._thread.start()

    def stop(self):
        """Stop the background forwarder."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None


def is_external_forwarder_running():
    """Check if another log_forwarder process is currently alive."""
    if not os.path.isfile(LOCK_FILE):
        return False
    try:
        with open(LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
        if pid == os.getpid():
            return False

        if os.name == "nt":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            STILL_ACTIVE = 259
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if h:
                code = ctypes.c_ulong()
                kernel32.GetExitCodeProcess(h, ctypes.byref(code))
                kernel32.CloseHandle(h)
                return code.value == STILL_ACTIVE
            return False
        else:
            try:
                os.kill(pid, 0)
                return True
            except (OSError, ProcessLookupError):
                return False
    except Exception:
        return False


def acquire_pid_lock():
    """Record current process PID in the lock file."""
    try:
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass


def release_pid_lock():
    """Remove lock file on clean exit."""
    try:
        if os.path.isfile(LOCK_FILE):
            with open(LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
            if pid == os.getpid():
                os.remove(LOCK_FILE)
    except Exception:
        pass


_global_forwarder = None


def start_log_forwarder(background=True):
    """Start the log forwarder if not already running."""
    global _global_forwarder
    if is_external_forwarder_running():
        print("[LOG_FORWARDER] External log forwarder process is already running.")
        return None

    if _global_forwarder is not None and _global_forwarder._running:
        return _global_forwarder

    acquire_pid_lock()
    _global_forwarder = LogForwarder()
    if background:
        _global_forwarder.start()
    else:
        _global_forwarder.run()
    return _global_forwarder


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smart Mirror Log Forwarder")
    parser.add_argument("--once", action="store_true", help="Perform a single sync and exit")
    parser.add_argument("--interval", type=float, default=2.5, help="Poll interval in seconds")
    args = parser.parse_args()

    if args.once:
        forwarder = LogForwarder(interval=args.interval)
        success = forwarder.sync_once(force=True)
        print(f"[LOG_FORWARDER] Sync result: {'SUCCESS' if success else 'FAILED'}")
        sys.exit(0 if success else 1)

    if is_external_forwarder_running():
        print("[LOG_FORWARDER] Another instance is already running. Exiting.")
        sys.exit(0)

    acquire_pid_lock()
    try:
        forwarder = LogForwarder(interval=args.interval)
        forwarder.run()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        release_pid_lock()
