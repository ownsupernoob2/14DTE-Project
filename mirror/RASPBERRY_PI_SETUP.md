# Raspberry Pi Setup Guide

This guide covers the complete setup process for the Smart Mirror on a Raspberry Pi running Raspberry Pi OS. 

Because compiling heavy computer vision libraries like OpenCV and Mediapipe directly on the Raspberry Pi is slow and prone to Python version conflicts (especially on Python 3.6 or Python 3.13), we utilize precompiled, hardware-optimized system packages from the official repositories.

---

## Step 1: Update and Install System Dependencies

We install OpenCV, Mediapipe, Pygame, NumPy, PIL, and PyAudio directly from the official Debian/Raspbian repositories. Run the following commands:

```bash
sudo apt update
sudo apt install -y python3-dev python3-venv portaudio19-dev libspeex-dev libspeexdsp-dev ffmpeg v4l2loopback-dkms python3-pip python3-opencv python3-numpy python3-pil python3-pygame python3-mediapipe python3-pyaudio
```

This installs all binary compiled dependencies cleanly and rapidly without needing slow manual compilations.

---

## Step 2: Clone the Repository

Clone the project repository and checkout the `development` branch:

```bash
git clone https://github.com/ownsupernoob2/14DTE-Project.git ~/14DTE-Project
cd ~/14DTE-Project/mirror
git checkout development
```

---

## Step 3: Run the Setup Script

Execute the unified setup script to configure the virtual environment and fetch model files:

```bash
bash setup.sh
```

This setup script:
* Verifies system dependencies.
* Creates a Python virtual environment at `~/mirror-venv` configured with `--system-site-packages` so that the venv cleanly inherits OpenCV (`cv2`), Mediapipe (`mediapipe`), and Pygame (`pygame`) from the system.
* Upgrades pip/wheel and installs pure-Python requirements (like requests and dotenv).
* Downloads the gesture recognizer model task automatically.
* Sets execution permissions for all control scripts.

---

## Step 4: Configure Environment Variables

Copy the example configuration file and edit it to insert your Gemini API Key:

```bash
cp ~/14DTE-Project/mirror/.env.example ~/14DTE-Project/mirror/.env
nano ~/14DTE-Project/mirror/.env
```

Set the following variables inside the file:
```ini
API_URL=https://api.smartmirror.me
GEMINI_API_KEY=your_gemini_api_key_here
```

Press `CTRL+O` then `ENTER` to save, and `CTRL+X` to exit the nano editor.

---

## Step 5: Start the Smart Mirror

You can test the smart mirror directly by executing the boot script:

```bash
~/14DTE-Project/mirror/boot_mirror.sh
```

This pulls any outstanding updates from GitHub and fires up the full Pygame interface along with face recognition and voice assistant processes in the background!

### Useful CLI Controls

| Command | What it does |
|---|---|
| `~/14DTE-Project/mirror/boot_mirror.sh` | Pull latest updates and Start/Restart the mirror |
| `~/14DTE-Project/mirror/start_smart_mirror.sh` | Start/Restart the mirror WITHOUT pulling updates |
| `pkill -f smart_mirror_pro.py` | Stop the Pygame mirror window |
| `pkill -f python` | Stop all background python modules |
| `tail -f ~/mirror_update.log` | View background auto-update details |
