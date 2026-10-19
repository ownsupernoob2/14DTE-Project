#!/bin/bash

# Start rpicam-vid piped to ffmpeg for virtual device (background)
# Tee the output to /dev/video20

RPICAM_BIN="rpicam-vid"
if ! command -v rpicam-vid &>/dev/null && command -v libcamera-vid &>/dev/null; then
    RPICAM_BIN="libcamera-vid"
fi

$RPICAM_BIN -t 0 --nopreview --codec yuv420 -o - --width 640 --height 480 --framerate 30 | ffmpeg -f rawvideo -pixel_format yuv420p -video_size 640x480 -framerate 30 -i - \
  -pix_fmt yuyv422 -f v4l2 -preset ultrafast -tune zerolatency -fflags nobuffer -flags low_delay /dev/video20 &
