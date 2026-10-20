#!/bin/bash
echo "=========================================================="
echo "Installing Smart Mirror Environment..."
echo "=========================================================="

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

echo ">>> Installing apt packages..."
sudo apt update
# Each package on its own so one missing package (python3-mediapipe does not
# exist on Debian trixie) cannot silently skip v4l2loopback-dkms with it.
for pkg in python3-venv ffmpeg v4l2loopback-dkms v4l-utils libzbar0 tesseract-ocr \
           cmake build-essential libopenblas-dev liblapack-dev; do
    sudo apt install -y "$pkg" || echo ">>> WARNING: could not install $pkg"
done

# The mirror needs Python 3.10 (mediapipe / dlib wheels). Raspberry Pi OS
# trixie ships 3.13, so fetch a standalone 3.10 with uv when it is missing.
if command -v python3.10 &>/dev/null; then
    PYTHON="$(command -v python3.10)"
else
    if [ ! -x "$HOME/.uv-tool/bin/uv" ]; then
        python3 -m venv "$HOME/.uv-tool"
        "$HOME/.uv-tool/bin/pip" install -q uv
    fi
    "$HOME/.uv-tool/bin/uv" python install 3.10
    PYTHON="$("$HOME/.uv-tool/bin/uv" python find 3.10)"
fi
echo ">>> Using Python: $($PYTHON --version)"

VENV_DIR="$HOME/mirror-venv"
echo ">>> Using virtual environment at: $VENV_DIR"

if [ -x "$VENV_DIR/bin/python" ] && ! "$VENV_DIR/bin/python" -c 'import sys; sys.exit(sys.version_info[:2] != (3, 10))'; then
    echo ">>> Existing venv is not Python 3.10 — moving it to $VENV_DIR.old"
    rm -rf "$VENV_DIR.old"
    mv "$VENV_DIR" "$VENV_DIR.old"
fi
if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON" -m venv "$VENV_DIR"
fi

echo ">>> Installing pip packages..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip wheel
"$VENV_DIR/bin/python" -m pip install -r requirements.txt
# face_recognition pins a source-built dlib; use the prebuilt dlib-bin instead.
"$VENV_DIR/bin/python" -m pip install --no-deps face_recognition

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
