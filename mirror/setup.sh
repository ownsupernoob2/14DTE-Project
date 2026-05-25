#!/bin/bash
echo "=========================================================="
echo "Installing Smart Mirror Environment..."
echo "=========================================================="

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

# 1. Update system dependencies
echo ">>> Installing missing apt packages..."
sudo apt update
sudo apt install -y python3-dev python3-venv portaudio19-dev libspeex-dev libspeexdsp-dev ffmpeg v4l2loopback-dkms libgl1-mesa-glx python3-pip

# 2. Cleanup broken system packages to avoid conflicts
echo ">>> Removing conflicting system packages (if any)..."
sudo apt remove -y python3-mediapipe

# 3. Create absolute virtual environment path
VENV_DIR="$HOME/mirror-venv"
echo ">>> Using virtual environment at: $VENV_DIR"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating clean python venv..."
    # We create it with system site packages in case we want to fallback,
    # but we heavily rely on pip for mediapipe and google modules.
    python3 -m venv "$VENV_DIR"
fi

# 4. Install all pip dependencies
echo ">>> Upgrading PIP and installing packages (this may take a few minutes)..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/python" -m pip install -r requirements.txt

# 5. Fix Google module issues (clean reinstall of google packages if they exist)
# Ensure we map "genai" correctly to the new package instead of lingering old ones
"$VENV_DIR/bin/python" -m pip uninstall -y google-genai google-generativeai google-api-core
"$VENV_DIR/bin/python" -m pip install google-genai google-api-python-client google-auth-oauthlib google-auth-httplib2

# 6. Download Gesture Task
if [ ! -f "gesture_recognizer.task" ]; then
    echo ">>> Downloading gesture recognizer task..."
    wget -O gesture_recognizer.task -q https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task
fi

# 7. Make run scripts executable
chmod +x start_smart_mirror.sh update_mirror.sh boot_mirror.sh

echo "=========================================================="
echo "✅ Setup Complete!"
echo "You can now start the mirror using: ./start_smart_mirror.sh"
echo "=========================================================="