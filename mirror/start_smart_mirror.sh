#!/bin/bash

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

# Cleanup previous processes
pkill -f rpicam-vid
pkill -f ffmpeg
pkill -f detect.py
pkill -f recognize.py
pkill -f smart_mirror_pro.py
pkill -f ai_service.py
sleep 2

# Setup Virtual Camera first
sudo modprobe -r v4l2loopback
sleep 1
sudo modprobe v4l2loopback devices=2 video_nr=10,11 card_label="VirtualCam1","VirtualCam2" exclusive_caps=1,1

# Start rpicam-vid piped to ffmpeg for virtual device (background)
# Tee the output to both /dev/video10 and /dev/video11
rpicam-vid -t 0 --nopreview --codec yuv420 -o - --width 640 --height 480 --framerate 30 | ffmpeg -f rawvideo -pixel_format yuv420p -video_size 640x480 -framerate 30 -i - \
  -f v4l2 -preset ultrafast -tune zerolatency -fflags nobuffer -flags low_delay /dev/video10 \
  -f v4l2 -preset ultrafast -tune zerolatency -fflags nobuffer -flags low_delay /dev/video11 &

# Wait a bit for camera to initialize
sleep 5

# [New] Start Face Recognition (background)
# Ensuring we use the correct path and venv
/home/raspi/.pyenv/versions/3.10.7/envs/mediapipe/bin/python face_recognize.py &

# Activate venv and start recognize.py (background)
/home/raspi/.pyenv/versions/3.10.7/envs/mediapipe/bin/python recognize.py \
  --cameraId 11 --frameWidth 640 --frameHeight 480 & # Using the virtual camera 2

# Wait a bit
sleep 2

# Start AI Service (background)
/home/raspi/.pyenv/versions/3.10.7/envs/mediapipe/bin/python ai_service.py &

# Start smart_mirror.py (background)
export DISPLAY=:0
/home/raspi/.pyenv/versions/3.10.7/envs/mediapipe/bin/python smart_mirror_pro.py &
