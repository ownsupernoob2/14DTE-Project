# Raspberry Pi Setup Guide

This guide covers the complete setup process for the Smart Mirror on a Raspberry Pi running Raspberry Pi OS (Debian Bookworm or later).

## Requirements

- Raspberry Pi 4 (2GB RAM or more recommended)
- Raspberry Pi OS (64-bit recommended)
- Python 3.9 to 3.11 (3.13 is NOT supported by mediapipe)
- Internet connection
- Git

## Step 1: Check Python Version

Verify your Python version:
```
python3 --version
```

If Python is 3.13 or above, you must install an older version:
```
sudo apt install python3.11 python3.11-venv python3.11-dev -y
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
```

## Step 2: Clone the Repository

```
git clone https://github.com/ownsupernoob2/14DTE-Project.git
cd 14DTE-Project/mirror
git checkout development
```

## Step 3: Run the Setup Script

```
bash setup.sh
```

This script will:
- Install system-level packages (OpenCV, Pygame, Mediapipe, PyAudio, NumPy, PIL) via apt
- Create a Python virtual environment at `~/mirror-venv` with `--system-site-packages` so it can access apt-installed packages
- Install remaining pip packages from requirements.txt
- Download the gesture recognizer model

## Step 4: Configure Environment Variables

Copy the example env file and edit it:
```
cp .env.example .env
nano .env
```

Fill in the following values:
```
API_URL=https://api.smartmirror.me
GEMINI_API_KEY=your_gemini_key_here
```

## Step 5: Set up Face Recognition

Capture face images:
```
~/mirror-venv/bin/python face_capture.py
```

Train the model:
```
~/mirror-venv/bin/python face_train.py
```

## Step 6: Start the Mirror

```
bash start_smart_mirror.sh
```

Or to auto-start on boot:
```
bash boot_mirror.sh
```

## Troubleshooting

### Pygame window freezes immediately
- This usually means a dependency failed to install
- Check that `python3-mediapipe` is installed: `python3 -c "import mediapipe; print(mediapipe.__version__)"`
- If not, run: `sudo apt install python3-mediapipe -y`

### libgl1-mesa-glx error
- This package was deprecated in Debian Bookworm
- The setup script no longer installs it — you can safely ignore this error on older logs

### mediapipe not found in venv
- The venv must be created with `--system-site-packages`
- Delete the old venv and re-run setup: `rm -rf ~/mirror-venv && bash setup.sh`

### google-genai import error
- The notices fetcher supports both `google-genai` and `google-generativeai` SDKs
- If you see import errors, run: `pip install google-genai`

### Face not recognized
- Re-capture images with better lighting: `~/mirror-venv/bin/python face_capture.py`
- Re-train: `~/mirror-venv/bin/python face_train.py`
