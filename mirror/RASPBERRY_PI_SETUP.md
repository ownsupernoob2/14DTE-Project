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

## STEP 3: Install system-level dependencies

Install system packages needed for audio, display, and compiling Python packages.
Do NOT install `python3-mediapipe` or `python3-opencv` via apt — we install those via pip to get working versions.

```bash
sudo apt install python3-full python3-dev portaudio19-dev libspeex-dev libspeexdsp-dev libatlas-base-dev libjpeg-dev libpng-dev ffmpeg v4l2loopback-dkms cmake -y
```

This may take a few minutes.

---

## STEP 4: Create a clean Python virtual environment

**Important:** Do NOT use `--system-site-packages`. The system mediapipe package on Raspberry Pi OS is broken and will cause an import error. We install everything we need via pip instead.

```bash
python3 -m venv ~/mirror-venv
```

---

## STEP 5: Upgrade pip inside the venv

```bash
~/mirror-venv/bin/pip install --upgrade pip setuptools wheel
```

---

## STEP 6: Install all Python packages

```bash
~/mirror-venv/bin/pip install -r ~/14DTE-Project/mirror/requirements.txt
```

This installs mediapipe, opencv, and all other dependencies cleanly.
This step may take several minutes on a Raspberry Pi.

---

## STEP 7: Make all mirror scripts executable

```bash
chmod +x ~/14DTE-Project/mirror/update_mirror.sh
chmod +x ~/14DTE-Project/mirror/start_smart_mirror.sh
chmod +x ~/14DTE-Project/mirror/boot_mirror.sh
```

---

## STEP 8: Set up auto-update cron job (Checks GitHub every 5 minutes AND on first launch)

This ensures your mirror updates quietly in the background while it is running, and also pulls the latest code immediately when the mirror boots.

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

The `boot_mirror.sh` script always pulls the latest code from GitHub **before** starting the mirror. This means every boot automatically has the newest version.

1. Create the autostart directory if it does not exist:
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

To test without rebooting, run the boot script directly:

```bash
~/14DTE-Project/mirror/boot_mirror.sh
```

Verify the processes are running in a new terminal:
```bash
ps aux | grep python
```
You should see `smart_mirror_pro.py`, `recognize.py`, `face_recognize.py`, and `ai_service.py` running in the background.

---

## Troubleshooting

**mediapipe import error (`ModuleNotFoundError: No module named 'mediapipe.python._framework_bindings'`)**

This happens when the broken system mediapipe is being picked up instead of the pip-installed one.
Fix: Make sure your venv was created WITHOUT `--system-site-packages`. If you used that flag before, delete and recreate the venv:

```bash
rm -rf ~/mirror-venv
python3 -m venv ~/mirror-venv
~/mirror-venv/bin/pip install --upgrade pip setuptools wheel
~/mirror-venv/bin/pip install -r ~/14DTE-Project/mirror/requirements.txt
```

**`ImportError: cannot import name 'genai' from 'google'`**

The `google-generativeai` package changed its import. This is fixed in the latest code — just pull the latest version:

```bash
cd ~/14DTE-Project && git pull
```

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
