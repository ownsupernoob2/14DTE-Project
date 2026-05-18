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

## STEP 9: Set up the mirror to auto-start on boot

```bash
sudo nano /etc/systemd/system/smartmirror.service
```

Paste this entire block (replace "raspi" with your username if different):

    [Unit]
    Description=Smart Mirror
    After=network.target

    [Service]
    User=raspi
    WorkingDirectory=/home/raspi/14DTE-Project/mirror
    ExecStart=/home/raspi/mirror-venv/bin/python /home/raspi/14DTE-Project/mirror/smart_mirror_pro.py
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target

Save: press CTRL+O, then ENTER, then CTRL+X to exit.

---

## STEP 10: Enable and start the mirror service

```bash
sudo systemctl daemon-reload
sudo systemctl enable smartmirror.service
sudo systemctl start smartmirror.service
```

---

## STEP 11: Verify everything is working

Check the mirror service is running:
```bash
sudo systemctl status smartmirror.service
```
You should see "active (running)" in green.
raspi@raspi:~/14DTE-Project/mirror $ sudo systemctl status smartmirror.service
● smartmirror.service - Smart Mirror
     Loaded: loaded (/etc/systemd/system/smartmirror.service; enabled; preset: enabled)
     Active: active (running) since Tue 2026-05-19 11:15:58 NZST; 1min 7s ago
 Invocation: d51a1156b91d4c4096206d747a0dae41
   Main PID: 11927 (python)
      Tasks: 8 (limit: 9570)
        CPU: 18.177s
     CGroup: /system.slice/smartmirror.service
             └─11927 /home/raspi/mirror-venv/bin/python /home/raspi/14DTE-Project/mirror/smart_mirror_pro.py

May 19 11:15:58 raspi systemd[1]: Started smartmirror.service - Smart Mirror.
May 19 11:16:00 raspi python[11927]: error: XDG_RUNTIME_DIR is invalid or not set in the environment.
raspi@raspi:~/14DTE-Project/mirror $ 

If it shows an error, view the logs:
```bash
sudo journalctl -u smartmirror.service -n 50
```

Check the auto-update log (wait 5+ minutes first):
```bash
tail -f ~/mirror_update.log
```
Press CTRL+C to stop watching.

---

## Done! Your workflow from now on:

1. Edit code on your Windows PC
2. git push to the main branch on GitHub
3. Within 5 minutes, the Pi automatically pulls the new code and restarts the mirror

---

## Useful Commands (for future reference)

| Command | What it does |
|---|---|
| `sudo systemctl status smartmirror.service` | Check if mirror is running |
| `sudo systemctl restart smartmirror.service` | Manually restart the mirror |
| `sudo systemctl stop smartmirror.service` | Stop the mirror |
| `sudo journalctl -u smartmirror.service -f` | Watch live mirror logs |
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
