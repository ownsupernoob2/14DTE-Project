#!/bin/bash
# start_smart_mirror.sh — Raspberry Pi launch script
# Starts: rpicam-vid → ffmpeg → /dev/video10, then face_recognize.py --rpi, then smart_mirror_pro.py

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

# ── Automatic GitHub Updates ─────────────────────────────────────────────────
echo "[START] Checking for updates from GitHub..."
git pull || echo "[WARN] Failed to pull updates from GitHub. Running with current code."

# ── Python interpreter ──────────────────────────────────────────────────────
# Prefer the venv created by setup.sh, fall back to system python3.10 / python3
PYTHON="${MIRROR_PYTHON:-$HOME/mirror-venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
    if command -v python3.10 &>/dev/null; then
        PYTHON=python3.10
    else
        PYTHON=python3
    fi
fi

echo "[START] Using Python: $($PYTHON --version)"

# ── Kill any previous instances ─────────────────────────────────────────────
pkill -f rpicam-vid       2>/dev/null || true
pkill -f ffmpeg           2>/dev/null || true
pkill -f face_recognize   2>/dev/null || true
pkill -f gesture_engine   2>/dev/null || true
pkill -f smart_mirror_pro 2>/dev/null || true
pkill -f auto_updater.sh  2>/dev/null || true
sleep 2

# ── Set up the v4l2loopback virtual camera device (/dev/video10) ────────────
sudo modprobe -r v4l2loopback 2>/dev/null || true
sleep 1
sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="VirtualCam1" exclusive_caps=1

# ── Pipe rpicam-vid → ffmpeg → /dev/video10 ─────────────────────────────────
# EXPOSURE FIX ADJUSTMENTS:
#  --metering spot       : Measures light in the center of the frame (your face) instead of averaging the bright background.
#  --ev 2.0              : Boosts exposure target by +2 EV to brighten shadows.
#  --shutter 30000       : Locks shutter speed to 30,000 µs (30ms).
#  --gain 4.0            : Disables auto-gain and sets manual digital/analogue gain boost.

rpicam-vid -t 0 --nopreview --codec yuv420 \
  --metering spot \
  --ev 2.0 \
  --shutter 30000 \
  --gain 4.0 \
  -o - --width 640 --height 480 --framerate 30 | \
ffmpeg -f rawvideo -pixel_format yuv420p -video_size 640x480 -framerate 30 -i - \
  -f v4l2 -preset ultrafast -tune zerolatency -fflags nobuffer -flags low_delay /dev/video10 &

echo "[START] Camera pipeline started. Waiting 5s for device to settle..."
sleep 5

# ── Face recognition daemon (RPi mode: reads from /dev/video10) ─────────────
"$PYTHON" -u face_recognize.py --rpi > "$APP_DIR/face_daemon.log" 2>&1 &

echo "[START] face_recognize.py --rpi started (logging to face_daemon.log). Waiting 2s..."
sleep 2

# ── Smart Mirror UI ──────────────────────────────────────────────────────────
# This also spawns gesture_engine.py, which reads the same loopback device, so
# there is no separate launch line for it here.
export DISPLAY=:0
"$PYTHON" -u smart_mirror_pro.py > "$APP_DIR/mirror.log" 2>&1 &

echo "[START] Smart Mirror is running."

# ── Background GitHub update watcher ─────────────────────────────────────────
chmod +x "$APP_DIR/auto_updater.sh" 2>/dev/null || true
/bin/bash "$APP_DIR/auto_updater.sh" &
echo "[START] Background GitHub auto-updater started."
