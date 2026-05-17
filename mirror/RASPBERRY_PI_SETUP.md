# Raspberry Pi Smart Mirror Setup
Run these commands in order. Copy-paste each block exactly.
raspi@raspi:~/14DTE-Project/mirror $ cd ~/14DTE-Project/mirror
pip3 install -r requirements.txt
error: externally-managed-environment

× This environment is externally managed
╰─> To install Python packages system-wide, try apt install
    python3-xyz, where xyz is the package you are trying to
    install.
    
    If you wish to install a non-Debian-packaged Python package,
    create a virtual environment using python3 -m venv path/to/venv.
    Then use path/to/venv/bin/python and path/to/venv/bin/pip. Make
    sure you have python3-full installed.
    
    For more information visit http://rptl.io/venv

note: If you believe this is a mistake, please contact your Python installation or OS distribution provider. You can override this, at the risk of breaking your Python installation or OS, by passing --break-system-packages.
hint: See PEP 668 for the detailed specification.
raspi@raspi:~/14DTE-Project/mirror $ 

---

## STEP 1: Install dependencies

```bash
sudo apt update && sudo apt install git python3-pip -y
```

---

## STEP 2: Clone the repository

```bash
git clone raspi@raspi:~/14DTE-Project/mirror $ cd ~/14DTE-Project/mirror
pip3 install -r requirements.txt
error: externally-managed-environment

× This environment is externally managed
╰─> To install Python packages system-wide, try apt install
    python3-xyz, where xyz is the package you are trying to
    install.
    
    If you wish to install a non-Debian-packaged Python package,
    create a virtual environment using python3 -m venv path/to/venv.
    Then use path/to/venv/bin/python and path/to/venv/bin/pip. Make
    sure you have python3-full installed.
    
    For more information visit http://rptl.io/venv

note: If you believe this is a mistake, please contact your Python installation or OS distribution provider. You can override this, at the risk of breaking your Python installation or OS, by passing --break-system-packages.
hint: See PEP 668 for the detailed specification.
raspi@raspi:~/14DTE-Project/mirror $ 
https://github.com/ownsupernoob2/14DTE-Project.git ~/14DTE-Project
```

---

## STEP 3: Install Python packages

```bash
cd ~/14DTE-Project/mirror
pip3 install -r requirements.txt
```

---

## STEP 4: Make the update script executable

```bash
chmod +x ~/14DTE-Project/mirror/update_mirror.sh
```

---

## STEP 5: Edit the update script to auto-restart the mirror on update

```bash
nano ~/14DTE-Project/mirror/update_mirror.sh
```

Find this line:
    # sudo systemctl restart smartmirror.service

Remove the # at the start so it becomes:
    sudo systemctl restart smartmirror.service

Save: press CTRL+O, then ENTER, then CTRL+X to exit.

---

## STEP 6: Set up auto-update cron job (checks GitHub every 5 minutes)

```bash
crontab -e
```

If it asks which editor, press 1 for nano.
Scroll to the very bottom and add this line:

    */5 * * * * /home/pi/14DTE-Project/mirror/update_mirror.sh >> /home/pi/mirror_update.log 2>&1

NOTE: If your username is NOT "pi", replace /home/pi with your actual home directory.
      You can check by running: echo $HOME

Save: press CTRL+O, then ENTER, then CTRL+X to exit.

---

## STEP 7: Set up the mirror to auto-start on boot

```bash
sudo nano /etc/systemd/system/smartmirror.service
```

Paste this entire block into the file:

    [Unit]
    Description=Smart Mirror
    After=network.target

    [Service]
    User=pi
    WorkingDirectory=/home/pi/14DTE-Project/mirror
    ExecStart=/usr/bin/python3 /home/pi/14DTE-Project/mirror/smart_mirror_pro.py
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target

NOTE: Again, replace "pi" and "/home/pi" with your actual username if different.

Save: press CTRL+O, then ENTER, then CTRL+X to exit.

---

## STEP 8: Enable and start the service

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

Check the update log (wait a few minutes first):
```bash
tail -f ~/mirror_update.log
```
Press CTRL+C to stop watching the log.

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




error:

raspi@raspi:~/14DTE-Project/mirror $ cd ~/14DTE-Project/mirror
pip3 install -r requirements.txt
error: externally-managed-environment

× This environment is externally managed
╰─> To install Python packages system-wide, try apt install
    python3-xyz, where xyz is the package you are trying to
    install.
    
    If you wish to install a non-Debian-packaged Python package,
    create a virtual environment using python3 -m venv path/to/venv.
    Then use path/to/venv/bin/python and path/to/venv/bin/pip. Make
    sure you have python3-full installed.
    
    For more information visit http://rptl.io/venv

note: If you believe this is a mistake, please contact your Python installation or OS distribution provider. You can override this, at the risk of breaking your Python installation or OS, by passing --break-system-packages.
hint: See PEP 668 for the detailed specification.
raspi@raspi:~/14DTE-Project/mirror $ 




