#!/bin/bash

# Start rpicam-vid piped to ffmpeg for virtual device (background)
# Tee the output to both /dev/video10 and /dev/video11
rpicam-vid -t 0 --nopreview --codec yuv420 -o - --width 640 --height 480 --framerate 30 | ffmpeg -f rawvideo -pixel_format yuv420p -video_size 640x480 -framerate 30 -i - \
  -f v4l2 -preset ultrafast -tune zerolatency -fflags nobuffer -flags low_delay /dev/video10 \
  -f v4l2 -preset ultrafast -tune zerolatency -fflags nobuffer -flags low_delay /dev/video11 &
