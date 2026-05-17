# Raspberry Pi Smart Mirror Setup
Run these commands in order. Copy-paste each block exactly.
Your username appears to be "raspi" and your home is /home/raspi — replace if different.

---

## STEP 1: Update packages and install dependencies

```bash
sudo apt update && sudo apt install git python3-full python3-pip -y
```

---

## STEP 2: Clone the repository

```bash
git clone https://github.com/ownsupernoob2/14DTE-Project.git ~/14DTE-Project
```

---

## STEP 3: Create a Python virtual environment

Modern Raspberry Pi OS requires a venv for pip installs.

```bash
python3 -m venv ~/mirror-venv
```

---

## STEP 4: Install Python packages into the venv

```bash
~/mirror-venv/bin/pip install -r ~/14DTE-Project/mirror/requirements.txt
```

This will take a few minutes. Wait for it to fully finish before moving on.

---

## STEP 5: Make the update script executable

```bash
chmod +x ~/14DTE-Project/mirror/update_mirror.sh
```

---

## STEP 6: Set up auto-update cron job (checks GitHub every 5 minutes)

```bash
crontab -e
```

If it asks which editor, press 1 for nano.
Scroll to the very bottom and add this line:

    */5 * * * * /home/raspi/14DTE-Project/mirror/update_mirror.sh >> /home/raspi/mirror_update.log 2>&1

NOTE: If your username is NOT "raspi", replace /home/raspi with your actual home directory.
      You can check what it is by running: echo $HOME

Save: press CTRL+O, then ENTER, then CTRL+X to exit.

---

## STEP 7: Set up the mirror to auto-start on boot

```bash
sudo nano /etc/systemd/system/smartmirror.service
```

Paste this entire block into the file (replace "raspi" with your username if different):

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

## STEP 8: Enable and start the mirror service

```bash
sudo systemctl daemon-reload
sudo systemctl enable smartmirror.service
sudo systemctl start smartmirror.service
```

---

## STEP 9: Verify everything is working

Check the mirror service is running:
```bash
sudo systemctl status smartmirror.service
```
You should see "active (running)" in green.

If it shows an error, view the full logs:
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
