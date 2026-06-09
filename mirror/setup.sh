#!/bin/bash
echo "=========================================================="
echo "Installing Smart Mirror Environment..."
echo "=========================================================="

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

if command -v python3.10 &>/dev/null; then
    PYTHON=python3.10
elif command -v pyenv &>/dev/null && pyenv versions --bare | grep -q '^3\.10'; then
    PYTHON="$(pyenv root)/versions/$(pyenv versions --bare | grep '^3\.10' | head -1)/bin/python"
else
    echo "ERROR: Python 3.10 is required for mediapipe on Raspberry Pi."
    echo "Install with: sudo apt install python3.10 python3.10-venv"
    exit 1
fi

echo ">>> Using Python: $($PYTHON --version)"

echo ">>> Installing apt packages..."
sudo apt update
sudo apt install -y \
    python3.10-venv python3.10-dev \
    ffmpeg v4l2loopback-dkms \
    python3-opencv python3-numpy python3-pil python3-pygame python3-mediapipe

VENV_DIR="$HOME/mirror-venv"
echo ">>> Using virtual environment at: $VENV_DIR"

if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON" -m venv --system-site-packages "$VENV_DIR"
fi

echo ">>> Installing pip packages..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/python" -m pip install -r requirements.txt

if [ ! -f "gesture_recognizer.task" ]; then
    echo ">>> Downloading gesture recognizer task..."
    wget -O gesture_recognizer.task -q \
        https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task
fi

chmod +x start_smart_mirror.sh start_camera.sh 2>/dev/null || true

echo "=========================================================="
echo "Setup Complete!"
echo "Start the mirror with: ./start_smart_mirror.sh"
echo "=========================================================="
