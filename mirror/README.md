# Smart Mirror - Client Application

This folder contains the Python client application for the Smart Mirror, including the PyQt6-based user interface, the face recognition daemon, and the hand gesture recognition engine.

---

## 💻 Windows Setup & Run Guide (Development/Simulator Mode)

For development and testing on Windows, you can run the Smart Mirror in a windowed simulator mode with a mock interface for face/user state transitions.

### 📋 Prerequisites

1. **Python 3.10**: Highly recommended. MediaPipe and FAISS have specific prebuilt wheels for Python 3.10 on Windows. If you use newer versions, package installation might require compiler tools or fail.
   * [Download Python 3.10](https://www.python.org/downloads/release/python-31011/) and make sure to check **"Add Python to PATH"** during installation.

---

### 🛠️ Step 1: Automated Setup

The easiest way to set up your virtual environment and install all dependencies is to run the setup script:

1. Double-click or run [setup_venv.bat](file:///e:/Code/offical/14DTE-Project/mirror/setup_venv.bat) in your terminal.
2. This script will:
   * Create a Python virtual environment in `.venv/`.
   * Upgrade `pip`, `setuptools`, and `wheel`.
   * Install dependencies from both [requirements.txt](file:///e:/Code/offical/14DTE-Project/mirror/requirements.txt) and [requirements-dev.txt](file:///e:/Code/offical/14DTE-Project/mirror/requirements-dev.txt).
   * Download the required MediaPipe `gesture_recognizer.task` model file.

#### Alternately: Manual Setup
If you prefer to run the commands manually:
```bash
# 1. Create the virtual environment
python -m venv .venv

# 2. Activate the virtual environment
# In Command Prompt:
.venv\Scripts\activate.bat
# In PowerShell:
.venv\Scripts\Activate.ps1

# 3. Upgrade pip tools
python -m pip install --upgrade pip setuptools wheel

# 4. Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# 5. Download the gesture recognizer model
powershell -Command "Invoke-WebRequest -Uri 'https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task' -OutFile 'gesture_recognizer.task'"
```

---

### 🚀 Step 2: Running the Simulator

To run the application locally on Windows without a physical smart mirror setup, we run the state simulator alongside the PyQt6 user interface.

#### 1. Start the Mock Face Status Interface
Open a new terminal, navigate to the `mirror` directory, and run:
```bash
.venv\Scripts\python.exe mock_face.py
```
This will launch a CLI prompt allowing you to toggle the mirror's state:
* **`1` (Idle)**: Mirror goes black (screen-saver mode).
* **`2` (Guest)**: Displays generic/public widgets (Clock, public notices).
* **`3` (User)**: Logs in a mock user and shows their custom widgets/timetable.

#### 2. Start the Smart Mirror UI
Open a second terminal, navigate to the `mirror` directory, set the windowed mode environment variable, and start the PyQt6 application:

* **Command Prompt (cmd):**
  ```cmd
  set MIRROR_WINDOWED=1
  .venv\Scripts\python.exe smart_mirror_pro.py
  ```

* **PowerShell:**
  ```powershell
  $env:MIRROR_WINDOWED="1"
  .venv\Scripts\python.exe smart_mirror_pro.py
  ```

The Smart Mirror window will open. As you press `1`, `2`, or `3` in the first terminal, you will see the Smart Mirror UI dynamically transition between the Idle, Guest, and User states.

---

## 🍓 Raspberry Pi Setup (Production Mode)

On the physical Raspberry Pi mirror:
* Run the shell script to install system dependencies, configure autostart, and setup the environment:
  ```bash
  chmod +x setup.sh
  ./setup.sh
  ```
* Launch the complete pipeline (virtual camera loopback, face recognition daemon, and full-screen pygame/PyQt UI) using:
  ```bash
  ./start_smart_mirror.sh
  ```

---

## 📁 Key Files & Architecture

* **[smart_mirror_pro.py](file:///e:/Code/offical/14DTE-Project/mirror/smart_mirror_pro.py)**: The main PyQt6 GUI application. Renders widgets, handles windowed/fullscreen modes, and polls for face/gesture status updates.
* **[mock_face.py](file:///e:/Code/offical/14DTE-Project/mirror/mock_face.py)**: A state simulator utility that writes mock states to the temp directory (`face_status.json`) to simulate camera/OCR inputs.
* **[face_recognize.py](file:///e:/Code/offical/14DTE-Project/mirror/face_recognize.py)**: Daemon responsible for camera polling, Haar Cascade face detection, and API-based face verification.
* **[gesture_engine.py](file:///e:/Code/offical/14DTE-Project/mirror/gesture_engine.py)**: MediaPipe-powered gesture engine daemon that recognizes hand gestures (like swipe, pinch-to-scroll) to interact with the mirror without touching it.
* **[config.py](file:///e:/Code/offical/14DTE-Project/mirror/config.py)**: Stores system paths (shared JSON files in the OS temporary folder), UI constants, and color definitions.
