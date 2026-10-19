#!/bin/bash
# start_smart_mirror.sh — Raspberry Pi launch script

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

# ── Automatic GitHub Updates ─────────────────────────────────────────────────
echo "[START] Checking for updates from GitHub..."
git pull || echo "[WARN] Failed to pull updates from GitHub. Running with current code."

# ── Python interpreter ──────────────────────────────────────────────────────
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

# ── Set up v4l2loopback device (/dev/video10) ─────────────────────────────
# exclusive_caps=0 allows multiple processes (face_recognize & gesture_engine) to read concurrently
sudo modprobe -r v4l2loopback 2>/dev/null || true
sleep 1
sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="VirtualCam1" exclusive_caps=0

# ── Pipe rpicam-vid / libcamera-vid → ffmpeg → /dev/video10 ─────────────────
RPICAM_BIN="rpicam-vid"
if ! command -v rpicam-vid &>/dev/null && command -v libcamera-vid &>/dev/null; then
    RPICAM_BIN="libcamera-vid"
fi

$RPICAM_BIN -t 0 --nopreview --codec yuv420 -o - --width 640 --height 480 --framerate 30 2>> "$APP_DIR/camera_pipeline.log" | \
ffmpeg -f rawvideo -pixel_format yuv420p -video_size 640x480 -framerate 30 -i - \
  -f v4l2 -preset ultrafast -tune zerolatency -fflags nobuffer -flags low_delay /dev/video10 > "$APP_DIR/camera_pipeline.log" 2>&1 &

echo "[START] Camera pipeline started. Waiting 5s..."
sleep 5

# ── Launch Face Recognition Daemon ──────────────────────────────────────────
"$PYTHON" -u face_recognize.py --rpi > "$APP_DIR/face_daemon.log" 2>&1 &
echo "[START] face_recognize.py started."

# ── Launch Gesture Engine Daemon ─────────────────────────────────────────────
"$PYTHON" -u gesture_engine.py --rpi > "$APP_DIR/gesture_daemon.log" 2>&1 &
echo "[START] gesture_engine.py started."

sleep 2

# ── Launch Smart Mirror UI ───────────────────────────────────────────────────
export DISPLAY=:0
"$PYTHON" -u smart_mirror_pro.py > "$APP_DIR/mirror.log" 2>&1 &

echo "[START] Smart Mirror is running."

# ── Auto Updater ─────────────────────────────────────────────────────────────
chmod +x "$APP_DIR/auto_updater.sh" 2>/dev/null || true
/bin/bash "$APP_DIR/auto_updater.sh" &