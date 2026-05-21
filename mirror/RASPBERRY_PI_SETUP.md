# Raspberry Pi Smart Mirror Setup

Run these commands in order. Copy-paste each block exactly.
Your username is **"raspi"** — replace if different.

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

The `--system-site-packages` flag lets the venv use the apt packages we just installed.

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

## STEP 7: Make all mirror scripts executable

Make sure the startup, update, and boot scripts have execute permissions:

```bash
chmod +x ~/14DTE-Project/mirror/update_mirror.sh
chmod +x ~/14DTE-Project/mirror/start_smart_mirror.sh
chmod +x ~/14DTE-Project/mirror/boot_mirror.sh
```

---

## STEP 8: Set up auto-update cron job (Checks GitHub every 5 minutes)

This ensures your mirror updates quietly in the background while it is running.

```bash
crontab -e
```

If it asks which editor, press `1` for nano.
Scroll to the very bottom and add this line:

```text
*/5 * * * * /home/raspi/14DTE-Project/mirror/update_mirror.sh >> /home/raspi/mirror_update.log 2>&1
```

Save: press `CTRL+O`, then `ENTER`, then `CTRL+X` to exit.

---

## STEP 9: Set up Auto-Start on Boot (With Auto-Update First!)

We use the standard Linux Desktop Autostart, which launches the mirror inside your GUI session once the desktop loads. It is configured to pull the latest GitHub code *before* launching the mirror window.

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
   Exec=/home/raspi/14DTE-Project/mirror/boot_mirror.sh
   StartupNotify=false
   Terminal=false
   ```

   *(Replace "raspi" with your username if different)*

Save: press `CTRL+O`, then `ENTER`, then `CTRL+X` to exit.

---

## STEP 10: Verify everything is working

To test it right now without rebooting, simply run the boot script (which pulls the latest code and then starts the mirror):
```bash
~/14DTE-Project/mirror/boot_mirror.sh
```

Verify the processes are running in a new terminal:
```bash
ps aux | grep python
```
You should see `smart_mirror_pro.py`, `recognize.py`, `face_recognize.py`, and `ai_service.py` running in the background.

---

## Done! Your workflow from now on:

1. Edit code on your Windows PC.
2. `git commit` and `git push` to the main branch on GitHub.
3. If the mirror is **off**, turning it on will automatically pull the new code during boot.
4. If the mirror is already **running**, it will automatically pull the new code and seamlessly restart within 5 minutes.

---

## Useful Commands (for future reference)

| Command | What it does |
|---|---|
| `~/14DTE-Project/mirror/boot_mirror.sh` | Pull latest updates and Start/Restart the mirror |
| `~/14DTE-Project/mirror/start_smart_mirror.sh` | Start/Restart the mirror WITHOUT pulling updates |
| `pkill -f smart_mirror_pro.py` | Stop the mirror window |
| `pkill -f python` | Stop all python background services |
| `tail -f ~/mirror_update.log` | Watch the background 5-minute auto-update log |
