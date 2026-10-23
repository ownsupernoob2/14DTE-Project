#!/bin/bash
# start_smart_mirror.sh — Raspberry Pi launch script

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"
PATH="$PATH:/usr/sbin:/sbin"

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
    # Gets past local edits and stray files (keeping a copy) instead of
    # leaving the Pi stuck on an old version.
    /bin/bash "$APP_DIR/safe_pull.sh" || echo "[WARN] Failed to pull updates."
    if [ "$(git rev-parse HEAD 2>/dev/null)" != "$BEFORE" ]; then
        # bash reads this file as it runs; start again on the version just pulled.
        exec /bin/bash "$APP_DIR/start_smart_mirror.sh" --pulled
    fi
fi

# Install anything missing (Python 3.10 venv, packages, v4l2loopback). Quick
# when nothing has changed, so a fresh clone or a pull just works.
/bin/bash "$APP_DIR/setup.sh" --ensure || echo "[WARN] setup.sh --ensure reported a problem."

# Per-mirror settings that must not live in git: MIRROR_API_KEY (and optionally
# API_URL, MIRROR_ID). setup.sh creates the file.
ENV_FILE="$HOME/.config/smart-mirror/env"
if [ -f "$ENV_FILE" ]; then
    set -a; . "$ENV_FILE"; set +a
fi
[ -z "$MIRROR_API_KEY" ] && echo "[WARN] MIRROR_API_KEY is not set in $ENV_FILE — the server may refuse face sign-in."

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
pkill -f log_forwarder    2>/dev/null || true
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

# --exposure sport favours short exposures (raising gain instead), so a moving
# hand is sharp rather than smeared: blur made the tracked hand jump about.
$RPICAM_BIN -t 0 --nopreview --codec yuv420 -o - --width 640 --height 480 --framerate 30     --exposure sport \
    2> "$APP_DIR/rpicam.log" | \
ffmpeg -hide_banner -loglevel warning \
    -f rawvideo -pixel_format yuv420p -video_size 640x480 -framerate 30 -i - \
    -pix_fmt yuyv422 -f v4l2 "$LOOP_DEV" \
    -pix_fmt yuyv422 -f v4l2 "$GESTURE_DEV" \
    2> "$APP_DIR/ffmpeg.log" &

echo "[START] Camera pipeline started. Waiting 5s..."
sleep 5

# Background work (face recognition, the log uploader) shares CPU core 0, so
# it can never crowd out the hand tracker: competing for the CPU nearly
# doubled the model's time per frame (31 ms alone, ~55 ms with everything).
CORE0=""
command -v taskset >/dev/null && CORE0="taskset -c 0"

# ── Launch Face Recognition Daemon ──────────────────────────────────────────
# Lower CPU priority: recognising a face a fraction of a second later is
# invisible, but gestures and the UI stuttering is not.
PYTHONUNBUFFERED=1 $CORE0 nice -n 10 "$PYTHON" -u face_recognize.py --rpi > "$APP_DIR/face_daemon.log" 2>&1 &
echo "[START] face_recognize.py started."

# ── Launch Gesture Engine Daemon ─────────────────────────────────────────────
PYTHONUNBUFFERED=1 "$PYTHON" -u gesture_engine.py --rpi --flip > "$APP_DIR/gesture_daemon.log" 2>&1 &
echo "[START] gesture_engine.py started."

sleep 2

# ── Display resolution ───────────────────────────────────────────────────────
# The UI is drawn in software, so every pixel costs CPU the hand tracker needs.
# 1280x720 paints less than half as many pixels as 1920x1080 (the monitor
# scales it up; text is a little softer). MIRROR_RESOLUTION in
# ~/.config/smart-mirror/env: e.g. 1280x720 (default), 1920x1080, or "native"
# to put a monitor back on its own preferred mode.
RES="${MIRROR_RESOLUTION:-1280x720}"
if command -v wlr-randr >/dev/null; then
    export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
    for OUT in $(wlr-randr 2>/dev/null | awk '/^[^ ]/ {print $1}'); do
        if [ "$RES" = "native" ]; then
            case "$OUT" in NOOP-*) ;; *) wlr-randr --output "$OUT" --preferred ;; esac
        else
            wlr-randr --output "$OUT" --mode "$RES" 2>/dev/null                 || wlr-randr --output "$OUT" --custom-mode "$RES" 2>/dev/null                 || echo "[WARN] Could not set $OUT to $RES."
        fi
    done
    echo "[START] Display: $(wlr-randr 2>/dev/null | grep -m1 current | xargs)"
    sleep 1
fi

# ── Launch Smart Mirror UI ───────────────────────────────────────────────────
export DISPLAY=:0
# The daemons above are already running, so stop the UI spawning a second pair
# that would fight them for /dev/video42.
MIRROR_FACE_DAEMON=0 MIRROR_GESTURES=0 "$PYTHON" -u smart_mirror_pro.py > "$APP_DIR/mirror.log" 2>&1 &

# ── Launch Log Forwarder Daemon ──────────────────────────────────────────────
PYTHONUNBUFFERED=1 $CORE0 nice -n 15 "$PYTHON" -u log_forwarder.py > "$APP_DIR/log_forwarder.log" 2>&1 &
echo "[START] log_forwarder.py started."

echo "[START] Smart Mirror is running."
