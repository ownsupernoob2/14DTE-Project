#!/bin/bash
# start_smart_mirror.sh — Raspberry Pi launch script
# Starts: rpicam-vid → ffmpeg → /dev/video10, then face_recognize.py --rpi, then smart_mirror_pro.py

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

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
pkill -f smart_mirror_pro 2>/dev/null || true
sleep 2

# ── Set up the v4l2loopback virtual camera device (/dev/video10) ────────────
sudo modprobe -r v4l2loopback 2>/dev/null || true
sleep 1
sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="VirtualCam1" exclusive_caps=1

# ── Pipe rpicam-vid → ffmpeg → /dev/video10 ─────────────────────────────────
rpicam-vid -t 0 --nopreview --codec yuv420 -o - --width 640 --height 480 --framerate 30 | \
ffmpeg -f rawvideo -pixel_format yuv420p -video_size 640x480 -framerate 30 -i - \
  -f v4l2 -preset ultrafast -tune zerolatency -fflags nobuffer -flags low_delay /dev/video10 &

echo "[START] Camera pipeline started. Waiting 5s for device to settle..."
sleep 5

# ── Face recognition daemon (RPi mode: reads from /dev/video10) ─────────────
"$PYTHON" -u face_recognize.py --rpi &

echo "[START] face_recognize.py --rpi started. Waiting 2s..."
sleep 2

# ── Pygame mirror UI ─────────────────────────────────────────────────────────
export DISPLAY=:0
"$PYTHON" -u smart_mirror_pro.py &

echo "[START] Smart Mirror is running."
