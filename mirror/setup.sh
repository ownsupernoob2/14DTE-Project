#!/bin/bash
echo "=========================================================="
echo "Installing Smart Mirror Environment..."
echo "=========================================================="

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

# Detect suitable Python version (Python 3.10, 3.11, or default python3 >= 3.10)
if command -v python3.11 &>/dev/null; then
    PYTHON=python3.11
elif command -v python3.10 &>/dev/null; then
    PYTHON=python3.10
elif command -v pyenv &>/dev/null && pyenv versions --bare | grep -q '^3\.\(10\|11\)'; then
    PYTHON="$(pyenv root)/versions/$(pyenv versions --bare | grep '^3\.\(10\|11\)' | head -1)/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON=python3
else
    echo "ERROR: python3 is not installed."
    echo "Install with: sudo apt install python3 python3-venv python3-dev"
    exit 1
fi

PY_CHECK=$("$PYTHON" -c "import sys; print(1 if sys.version_info >= (3, 10) else 0)" 2>/dev/null || echo 0)
if [ "$PY_CHECK" != "1" ]; then
    echo "ERROR: Python 3.10+ is required (found $($PYTHON --version 2>&1))."
    echo "Install Python 3.10 or 3.11 before running setup."
    exit 1
fi

echo ">>> Using Python: $($PYTHON --version)"

echo ">>> Installing apt packages..."
sudo apt update
sudo apt install -y \
    python3-venv python3-dev \
    ffmpeg v4l2loopback-dkms \
    python3-opencv python3-numpy python3-pil python3-pygame \
    python3-mediapipe 2>/dev/null || echo ">>> Note: python3-mediapipe apt package not found, will install via pip fallback."

VENV_DIR="$HOME/mirror-venv"
echo ">>> Using virtual environment at: $VENV_DIR"

if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON" -m venv --system-site-packages "$VENV_DIR"
fi

echo ">>> Installing pip packages..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/python" -m pip install -r requirements.txt

# Verification step for MediaPipe
echo ">>> Verifying MediaPipe installation..."
if "$VENV_DIR/bin/python" -c "import mediapipe" 2>/dev/null; then
    echo ">>> MediaPipe installed successfully!"
else
    echo ">>> Standard mediapipe import failed. Attempting ARM-compatible fallback install..."
    "$VENV_DIR/bin/python" -m pip install mediapipe-rpi4 || "$VENV_DIR/bin/python" -m pip install mediapipe-silicon
fi

if [ ! -f "gesture_recognizer.task" ]; then
    echo ">>> Downloading gesture recognizer task..."
    wget -O gesture_recognizer.task -q \
        https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task
fi

chmod +x start_smart_mirror.sh start_camera.sh auto_updater.sh 2>/dev/null || true

echo ">>> Setting up automatic startup on boot..."
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cat <<EOF > "$AUTOSTART_DIR/smart_mirror.desktop"
[Desktop Entry]
Type=Application
Name=Smart Mirror
Exec=/bin/bash $APP_DIR/start_smart_mirror.sh
Terminal=true
X-GNOME-Autostart-enabled=true
EOF
chmod +x "$AUTOSTART_DIR/smart_mirror.desktop"
echo ">>> Configured autostart desktop entry at: $AUTOSTART_DIR/smart_mirror.desktop"

echo "=========================================================="
echo "Setup Complete!"
echo "Start the mirror now with: ./start_smart_mirror.sh"
echo "=========================================================="
