#!/bin/bash
# start_smart_mirror.sh — Raspberry Pi launch script

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

# Pi 5: ISP owns video20-35, so the loopbacks live at /dev/video42 and 43.
# v4l2loopback only lets one reader stream at a time, so each daemon gets its
# own device carrying the same camera feed.
LOOP_DEV=/dev/video42           # face_recognize.py
GESTURE_DEV=/dev/video43        # gesture_engine.py
export MIRROR_LOOPBACK_DEV="$LOOP_DEV"
export MIRROR_GESTURE_DEV="$GESTURE_DEV"

if [ "$1" != "--pulled" ]; then
    echo "[START] Checking for updates from GitHub..."
    BEFORE="$(git rev-parse HEAD 2>/dev/null)"
    git pull --ff-only || echo "[WARN] Failed to pull updates."
    if [ "$(git rev-parse HEAD 2>/dev/null)" != "$BEFORE" ]; then
        # bash reads this file as it runs; start again on the version just pulled.
        exec /bin/bash "$APP_DIR/start_smart_mirror.sh" --pulled
    fi
fi

# Install anything missing (Python 3.10 venv, packages, v4l2loopback). Quick
# when nothing has changed, so a fresh clone or a pull just works.
/bin/bash "$APP_DIR/setup.sh" --ensure || echo "[WARN] setup.sh --ensure reported a problem."

PYTHON="${MIRROR_PYTHON:-$HOME/mirror-venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
    echo "[ERROR] $PYTHON not found — run ./setup.sh"
    exit 1
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

# ── Loopback devices, one per daemon ────────────────────────────────────────
# setup.sh has the kernel create these at boot, so normally there is nothing
# to do. Otherwise try to (re)load the module — without ever waiting on a sudo
# password that nobody is there to type.
if [ ! -e "$LOOP_DEV" ] || [ ! -e "$GESTURE_DEV" ]; then
    sudo -n modprobe -r v4l2loopback 2>/dev/null
    if ! sudo -n modprobe v4l2loopback devices=2 video_nr=42,43 \
            card_label=FaceCam,GestureCam exclusive_caps=0,0; then
        echo "[ERROR] $LOOP_DEV / $GESTURE_DEV are missing, and loading v4l2loopback needs sudo."
        echo "[ERROR] Run ./setup.sh once (it makes them load at boot), then start again."
        exit 1
    fi
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
    -pix_fmt yuyv422 -f v4l2 "$GESTURE_DEV" \
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
# The daemons above are already running, so stop the UI spawning a second pair
# that would fight them for /dev/video42.
MIRROR_FACE_DAEMON=0 MIRROR_GESTURES=0 "$PYTHON" -u smart_mirror_pro.py > "$APP_DIR/mirror.log" 2>&1 &

echo "[START] Smart Mirror is running."
