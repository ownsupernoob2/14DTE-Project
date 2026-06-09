#!/bin/bash

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

PYTHON="${MIRROR_PYTHON:-$HOME/mirror-venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
    if command -v python3.10 &>/dev/null; then
        PYTHON=python3.10
    else
        PYTHON=python3
    fi
fi

pkill -f rpicam-vid
pkill -f ffmpeg
pkill -f recognize.py
pkill -f face_recognize.py
pkill -f smart_mirror_pro.py
sleep 2

sudo modprobe -r v4l2loopback 2>/dev/null || true
sleep 1
sudo modprobe v4l2loopback devices=2 video_nr=10,11 card_label="VirtualCam1","VirtualCam2" exclusive_caps=1,1

rpicam-vid -t 0 --nopreview --codec yuv420 -o - --width 640 --height 480 --framerate 30 | \
ffmpeg -f rawvideo -pixel_format yuv420p -video_size 640x480 -framerate 30 -i - \
  -f v4l2 -preset ultrafast -tune zerolatency -fflags nobuffer -flags low_delay /dev/video10 \
  -f v4l2 -preset ultrafast -tune zerolatency -fflags nobuffer -flags low_delay /dev/video11 &

sleep 5

"$PYTHON" face_recognize.py &
"$PYTHON" recognize.py --cameraId 11 --frameWidth 640 --frameHeight 480 &

sleep 2

export DISPLAY=:0
"$PYTHON" smart_mirror_pro.py &
