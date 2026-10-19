#!/bin/bash
# start_smart_mirror.sh — Raspberry Pi launch script

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

# Pi 5: ISP owns video20-35, loopback lives at /dev/video42
LOOP_DEV=/dev/video42
export MIRROR_LOOPBACK_DEV="$LOOP_DEV"

echo "[START] Checking for updates from GitHub..."
git pull || echo "[WARN] Failed to pull updates."

PYTHON="${MIRROR_PYTHON:-$HOME/mirror-venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
    PYTHON=python3
fi
echo "[START] Using Python: $($PYTHON --version)"

# ── Kill any previous instances ─────────────────────────────────────────────
pkill -f rpicam-vid       2>/dev/null || true
pkill -f libcamera-vid    2>/dev/null || true
pkill -f ffmpeg           2>/dev/null || true
pkill -f face_recognize   2>/dev/null || true
pkill -f gesture_engine   2>/dev/null || true
pkill -f smart_mirror_pro 2>/dev/null || true
sleep 2

# ── Reload v4l2loopback with MULTI-READ SUPPORT (exclusive_caps=0) ──────────
if lsmod | grep -q '^v4l2loopback'; then
    sudo modprobe -r v4l2loopback 2>/dev/null || true
    sleep 1
fi

# IMPORTANT: exclusive_caps=0 allows OpenCV in multiple daemons to read /dev/video42 simultaneously
if ! sudo modprobe v4l2loopback devices=1 video_nr=42 card_label="VirtualCam1" exclusive_caps=0; then
    echo "[ERROR] Could not load v4l2loopback module."
    exit 1
fi

# ── Pipe Camera Stream to Loopback ───────────────────────────────────────────
RPICAM_BIN="rpicam-vid"
if ! command -v rpicam-vid &>/dev/null && command -v libcamera-vid &>/dev/null; then
    RPICAM_BIN="libcamera-vid"
fi

$RPICAM_BIN -t 0 --nopreview --codec yuv420 -o - --width 640 --height 480 --framerate 30 \
    2> "$APP_DIR/rpicam.log" | \
ffmpeg -hide_banner -loglevel warning \
    -f rawvideo -pixel_format yuv420p -video_size 640x480 -framerate 30 -i - \
    -pix_fmt yuyv422 -f v4l2 "$LOOP_DEV" \
    2> "$APP_DIR/ffmpeg.log" &

echo "[START] Camera pipeline started. Waiting 5s..."
sleep 5

# ── Launch Face Recognition Daemon ──────────────────────────────────────────
PYTHONUNBUFFERED=1 "$PYTHON" -u face_recognize.py --rpi > "$APP_DIR/face_daemon.log" 2>&1 &
echo "[START] face_recognize.py started."

# ── Launch Gesture Engine Daemon ─────────────────────────────────────────────
PYTHONUNBUFFERED=1 "$PYTHON" -u gesture_engine.py --rpi --flip > "$APP_DIR/gesture_daemon.log" 2>&1 &
echo "[START] gesture_engine.py started."

sleep 2

# ── Launch Smart Mirror UI ───────────────────────────────────────────────────
export DISPLAY=:0
"$PYTHON" -u smart_mirror_pro.py > "$APP_DIR/mirror.log" 2>&1 &

echo "[START] Smart Mirror is running."
