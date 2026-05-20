# Raspberry Pi Smart Mirror Setup
Run these commands in order. Copy-paste each block exactly.
Your username is "raspi" — replace if different.

---

## STEP 1: Update packages and install git

```bash
sudo apt update && sudo apt install git -y
```

---

## STEP 2: Clone the repository

```bash
git clone https://github.com/ownsupernoob2/14DTE-Project.git ~/14DTE-Project
```

---

## STEP 3: Install system-level Python packages via apt

These packages need compiled C/C++ code (ARM binaries).
apt provides pre-built versions so we don't have to compile from source.

```bash
sudo apt install python3-opencv python3-pyaudio python3-pyqt5 python3-numpy python3-pil python3-full portaudio19-dev -y
```

This may take a few minutes.

---

## STEP 4: Create a Python virtual environment with access to system packages

The --system-site-packages flag lets the venv use the apt packages we just installed.

```bash
python3 -m venv --system-site-packages ~/mirror-venv
```

---

## STEP 5: Upgrade pip and setuptools inside the venv

```bash
~/mirror-venv/bin/pip install --upgrade pip setuptools wheel
```

---

## STEP 6: Install remaining pure-Python packages

```bash
~/mirror-venv/bin/pip install -r ~/14DTE-Project/mirror/requirements.txt
```

This should complete without any compilation errors.

---

## STEP 7: Make the update script executable

```bash
chmod +x ~/14DTE-Project/mirror/update_mirror.sh
```

---

## STEP 8: Set up auto-update cron job (checks GitHub every 5 minutes)

```bash
crontab -e
```

If it asks which editor, press 1 for nano.
Scroll to the very bottom and add this line:

    */5 * * * * /home/raspi/14DTE-Project/mirror/update_mirror.sh >> /home/raspi/mirror_update.log 2>&1

Save: press CTRL+O, then ENTER, then CTRL+X to exit.

---

## STEP 9: Set up the mirror to auto-start on boot (GUI Autostart)

Because Pygame is a graphical application, systemd system services cannot easily open the window (leading to `XDG_RUNTIME_DIR is invalid` errors). Instead, we use the standard Linux Desktop Autostart, which launches the mirror inside your GUI session once the desktop loads.

1. Create the autostart directory if it doesn't exist:
   ```bash
   mkdir -p ~/.config/autostart
   ```

2. Create the autostart config file:
   ```bash
   nano ~/.config/autostart/smartmirror.desktop
   ```

3. Paste this configuration:

   ```ini
   [Desktop Entry]
   Type=Application
   Name=Smart Mirror
   Exec=/home/raspi/14DTE-Project/mirror/start_smart_mirror.sh
   StartupNotify=false
   Terminal=false
   ```

   *(Replace "raspi" with your username if different)*

4. Make the start script executable:
   ```bash
   chmod +x ~/14DTE-Project/mirror/start_smart_mirror.sh
   ```

Save: press CTRL+O, then ENTER, then CTRL+X to exit.

---

## STEP 10: Manually launch the mirror for the first time

To test it right now without rebooting, simply run the start script:
```bash
~/14DTE-Project/mirror/start_smart_mirror.sh
```

This will run all required background services (virtual camera, face recognition, hand gestures, and voice) and finally open your Pygame GUI window!

---

## STEP 11: Verify everything is working

Verify the processes are running:
```bash
ps aux | grep python
```
You should see `smart_mirror_pro.py`, `recognize.py`, `face_recognize.py`, and `ai_service.py` running in the background.

Check the auto-update log (wait 5+ minutes first):
```bash
tail -f ~/mirror_update.log
```
Press CTRL+C to stop watching.

---

## Done! Your workflow from now on:

1. Edit code on your Windows PC
2. git push to the main branch on GitHub
3. Within 5 minutes, the Pi automatically pulls the new code, restarts all services, and opens the mirror!

---

## Useful Commands (for future reference)

| Command | What it does |
|---|---|
| `~/14DTE-Project/mirror/start_smart_mirror.sh` | Start/Restart the mirror and all services |
| `pkill -f smart_mirror_pro.py` | Stop the mirror window |
| `pkill -f python` | Stop all python background services |
| `tail -f ~/mirror_update.log` | Watch the auto-update log |
| `cd ~/14DTE-Project && git pull` | Manually force a git pull |



# 1. Pull the latest files
cd ~/14DTE-Project && git pull

# 2. Nuke the broken venv
rm -rf ~/mirror-venv

# 3. Install pre-built ARM packages via apt (no compilation)
sudo apt install python3-opencv python3-pyaudio python3-pyqt5 python3-numpy python3-pil python3-full portaudio19-dev -y

# 4. Recreate venv with access to those apt packages
python3 -m venv --system-site-packages ~/mirror-venv

# 5. Upgrade pip then install pure Python packages
~/mirror-venv/bin/pip install --upgrade pip setuptools wheel && ~/mirror-venv/bin/pip install -r ~/14DTE-Project/mirror/requirements.txt
