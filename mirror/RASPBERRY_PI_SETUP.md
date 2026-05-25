# Raspberry Pi Smart Mirror Setup (Updated)

This setup is fully automated to match the exact working environment of the older mirror while supporting the latest code.

---
cd ~/14DTE-Project
git reset --hard origin/development
git pull

cd mirror
chmod +x setup.sh
./setup.sh

## 1. Get the latest code

First, make sure you are in the correct directory and have the very latest code:

`ash
cd ~/14DTE-Project
git reset --hard origin/main
git pull origin main
cd mirror
`

---

## 2. Run the Automated Setup

We have created an automated setup script that properly handles Virtual Environments (venv), cleanly installs Mediapipe without system conflicts, and installs the required Google GenAI packages exact to the working old-mirror specification.

`ash
cd ~/14DTE-Project/mirror
chmod +x setup.sh
./setup.sh
`

**What it does:**
- Completely cleans up broken python3-mediapipe apt packages.
- Creates an isolated Virtual Environment (~/mirror-venv).
- Correctly sets up google-genai rather than the outdated google-generativeai.
- Downloads the gesture_recognizer.task automatically.

If this completes successfully (it will say ✅ Setup Complete at the bottom), proceed to step 3.

---

## 3. Verify it Works

To test without rebooting, run the dedicated start script:

`ash
cd ~/14DTE-Project/mirror
./start_smart_mirror.sh
`

Verify that i_service.py, 
ecognize.py, and the main smart_mirror_pro.py are properly running without (unknown location) errors.

---

## Troubleshooting

### Q: "ModuleNotFoundError: No module named 'mediapipe.python._framework_bindings'"
This will NOT happen if you run .start_smart_mirror.sh because it explicitly uses the cleanly built virtual environment from step 2 (~/mirror-venv/bin/python). Never run the python files manually using standard python3 command, you must either activate the venv or use the start scripts.

### Q: "cannot import name 'genai' from 'google'"
The setup script completely uninstalls conflicting google packages and installs google-genai. If it ever occurs again, simply run ./setup.sh to fix it.

