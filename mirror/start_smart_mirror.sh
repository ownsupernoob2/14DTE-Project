#!/bin/bash
# start_smart_mirror.sh — Raspberry Pi launch script

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

# Pi 5: the PiSP ISP owns /dev/video20-35, so the loopback must live elsewhere.
LOOP_DEV=/dev/video42
export MIRROR_LOOPBACK_DEV="$LOOP_DEV"   # face_recognize.py / gesture_engine.py read this

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
pkill -f libcamera-vid    2>/dev/null || true
pkill -f ffmpeg           2>/dev/null || true
pkill -f face_recognize   2>/dev/null || true
pkill -f gesture_engine   2>/dev/null || true
pkill -f smart_mirror_pro 2>/dev/null || true
pkill -f auto_updater.sh  2>/dev/null || true
sleep 2

# ── (Re)load v4l2loopback — and FAIL LOUDLY if that doesn't work ─────────────
# The old `modprobe -r ... || true` hid the case where something still held the
# device: the module never reloaded, so a stale loopback with an old format
# stayed in place and the new ffmpeg got "Invalid argument" on its first write.
if lsmod | grep -q '^v4l2loopback'; then
    if ! sudo modprobe -r v4l2loopback; then
        echo "[ERROR] v4l2loopback is still in use. Processes holding it:"
        sudo fuser -v "$LOOP_DEV" 2>&1
        exit 1
    fi
    sleep 1
fi

if ! sudo modprobe v4l2loopback devices=1 video_nr=42 card_label="VirtualCam1" exclusive_caps=1; then
    echo "[ERROR] Could not load v4l2loopback (kernel updated without rebuilding the module?)."
    echo "        Check: uname -r ; dkms status ; sudo dmesg | tail -20"
    exit 1
fi

if [ ! -e "$LOOP_DEV" ]; then
    echo "[ERROR] $LOOP_DEV does not exist after loading v4l2loopback. Devices present:"
    v4l2-ctl --list-devices 2>&1
    exit 1
fi

# Existing is not enough: make sure the node really is the loopback driver.
if command -v v4l2-ctl &>/dev/null && ! v4l2-ctl -d "$LOOP_DEV" -D 2>/dev/null | grep -qi 'loopback'; then
    echo "[ERROR] $LOOP_DEV exists but is NOT a v4l2loopback device:"
    v4l2-ctl -d "$LOOP_DEV" -D 2>&1 | head -5
    echo "        Devices present:"
    v4l2-ctl --list-devices 2>&1
    exit 1
fi

# ── Pipe rpicam-vid / libcamera-vid → ffmpeg → /dev/video20 ─────────────────
# Separate log per process so they stop truncating each other's output.
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

# ── Verify the pipeline actually produces frames before starting daemons ─────
if ! pgrep -x ffmpeg >/dev/null; then
    echo "[ERROR] Camera pipeline died. ffmpeg.log / rpicam.log:"
    tail -n 20 "$APP_DIR/ffmpeg.log" "$APP_DIR/rpicam.log"
    exit 1
fi

if command -v v4l2-ctl &>/dev/null; then
    if timeout 5 v4l2-ctl -d "$LOOP_DEV" --stream-mmap --stream-count=5 --stream-to=/dev/null 2>/dev/null; then
        echo "[START] $LOOP_DEV is delivering frames."
    else
        echo "[WARN] ffmpeg is running but $LOOP_DEV did not deliver frames. See ffmpeg.log."
    fi
fi

# ── Launch Face Recognition Daemon ──────────────────────────────────────────
"$PYTHON" -u face_recognize.py --rpi > "$APP_DIR/face_daemon.log" 2>&1 &
echo "[START] face_recognize.py started."

# ── Launch Gesture Engine Daemon ─────────────────────────────────────────────
"$PYTHON" -u gesture_engine.py --rpi --flip > "$APP_DIR/gesture_daemon.log" 2>&1 &
echo "[START] gesture_engine.py started."

sleep 2

# ── Launch Smart Mirror UI ───────────────────────────────────────────────────
# smart_mirror_pro.py spawns its own face + gesture daemons by default, which
# duplicated the two started above. Tell it not to.
export MIRROR_FACE_DAEMON=0
export MIRROR_GESTURES=0
export DISPLAY=:0
"$PYTHON" -u smart_mirror_pro.py > "$APP_DIR/mirror.log" 2>&1 &

echo "[START] Smart Mirror is running."

# ── Auto Updater ─────────────────────────────────────────────────────────────
chmod +x "$APP_DIR/auto_updater.sh" 2>/dev/null || true
/bin/bash "$APP_DIR/auto_updater.sh" &
