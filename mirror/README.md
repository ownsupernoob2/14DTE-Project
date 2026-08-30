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

#### 3. Gestures

`smart_mirror_pro.py` starts [gesture_engine.py](file:///e:/Code/offical/14DTE-Project/mirror/gesture_engine.py) itself, so there is no third terminal to run — watch its output in the mirror's terminal. It should print:

```
[MIRROR] Gesture daemon started (pid 1234, --camera-id 0).
[GESTURE] Running on camera 0. Regions: left<0.5 right>0.62
```

If it says `Missing gesture_recognizer.task`, re-run the setup script. If it says it could not open the camera, something else already has it — `face_recognize.py` defaults to camera 4 to stay out of the way, but any other app counts too.

| Variable | Effect |
|---|---|
| `MIRROR_GESTURES=0` | Do not start the daemon (no camera to spare, or you are running it yourself) |
| `GESTURE_CAMERA=2` | Use webcam index 2 instead of 0 |

Gestures are ignored while the mirror is idle, so put it in Guest or User state before waving at it.

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
* **[face_recognize.py](file:///e:/Code/offical/14DTE-Project/mirror/face_recognize.py)**: Daemon responsible for camera polling, Haar Cascade face detection, and API-based face verification. Also decodes student ID barcodes held up to the camera and signs that student in.
* **[barcode_reader.py](file:///e:/Code/offical/14DTE-Project/mirror/barcode_reader.py)**: Student ID barcode decoder. Wraps whichever backend the host has (`cv2.barcode`, `cv2.QRCodeDetector` or `pyzbar`) and only reports a code once it has been read on two separate frames, so a motion-blurred misread cannot sign anyone in.
* **[gesture_engine.py](file:///e:/Code/offical/14DTE-Project/mirror/gesture_engine.py)**: MediaPipe-powered gesture daemon, started automatically by `smart_mirror_pro.py`. It does **not** emulate a mouse: the screen is split into left / centre / right regions and whichever region your hand is generally in is the one you interact with. Over the notices column an open palm scrolls and a quick pinch taps to hold the list still; dwelling on the right peeks the day's timetable. The published palm position is rounded to a coarse cell, which is both what keeps the status file from being rewritten on every frame and what makes the King's Week grid lock cleanly from box to box. Hand tracking goes through MediaPipe's **Tasks** API and `gesture_recognizer.task` — not the old `mp.solutions.hands`, which mediapipe 1.x removed.
* **[widgets/schedule_peek_widget.py](file:///e:/Code/offical/14DTE-Project/mirror/widgets/schedule_peek_widget.py)**: The full-day timetable panel that slides in from the right on a gesture, holds for 10 seconds, then slides out of the way.
* **[widgets/kings_week_widget.py](file:///e:/Code/offical/14DTE-Project/mirror/widgets/kings_week_widget.py)**: The King's Week grid that waits underneath the timetable. The latest story gets a full-width feature box and the rest follow in pairs below it, all fed by `GET /api/kings-week`. There is no cursor on a mirror, so nothing hovers: the palm position always resolves to the *nearest* box, the scroll comes to rest aligned to a row rather than halfway through one, and a tap grows the story out of its box into a modal.
* **[config.py](file:///e:/Code/offical/14DTE-Project/mirror/config.py)**: Stores system paths (shared JSON files in the OS temporary folder), UI constants, and color definitions.

### The right-side peek, stage by stage

The right of the screen reveals in two stages, so King's Week is discoverable
without a second gesture to learn:

1. **Dwell on the right** — the panel slides in with the day's timetable across
   the top 56% and King's Week visibly waiting below it.
2. **Scroll down** (or wait 10 seconds) — the timetable slides off the panel's
   right edge and King's Week grows to fill the column.
3. **Move your palm** — the nearest box locks in; **tap** to open it.
4. **Scroll** with a story open goes to that story; **tap** closes it.
5. **Scroll up** at the top of the grid brings the timetable back.
6. Twenty seconds with no hand on that side and the whole panel goes away, so
   one student's browsing is never left stranded on the mirror.

### Tests

All of the below run headless and offline — no camera, no mediapipe, no network:

```bash
python -m unittest test_barcode_reader test_gesture_engine test_kings_week_widget test_peek_stages
```

`test_kings_week_widget.py` covers the grid, box locking, snapping and the
modal; `test_peek_stages.py` drives the real gesture handler with synthetic
payloads to cover the two-stage reveal end to end.
