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



home/raspi/14DTE-Project/mirror/requirements.txt (line 8))
  Downloading https://www.piwheels.org/simple/google-api-python-client/google_api_python_client-2.196.0-py3-none-any.whl.metadata (7.0 kB)
Collecting google-ai-generativelanguage>=0.4.0 (from -r /home/raspi/14DTE-Project/mirror/requirements.txt (line 9))
  Downloading https://www.piwheels.org/simple/google-ai-generativelanguage/google_ai_generativelanguage-0.11.0-py3-none-any.whl.metadata (10.0 kB)
Collecting google-generativeai>=0.3.0 (from -r /home/raspi/14DTE-Project/mirror/requirements.txt (line 10))
  Downloading google_generativeai-0.8.6-py3-none-any.whl.metadata (3.9 kB)
Collecting PyAudio==0.2.13 (from -r /home/raspi/14DTE-Project/mirror/requirements.txt (line 11))
  Downloading PyAudio-0.2.13.tar.gz (46 kB)
  Installing build dependencies ... done
  Getting requirements to build wheel ... error
  error: subprocess-exited-with-error
  
  × Getting requirements to build wheel did not run successfully.
  │ exit code: 1
  ╰─> [32 lines of output]
      Traceback (most recent call last):
        File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_vendor/pyproject_hooks/_in_process/_in_process.py", line 389, in <module>
          main()
          ~~~~^^
        File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_vendor/pyproject_hooks/_in_process/_in_process.py", line 373, in main
          json_out["return_val"] = hook(**hook_input["kwargs"])
                                   ~~~~^^^^^^^^^^^^^^^^^^^^^^^^
        File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_vendor/pyproject_hooks/_in_process/_in_process.py", line 137, in get_requires_for_build_wheel
          backend = _build_backend()
        File "/home/raspi/mirror-venv/lib/python3.13/site-packages/pip/_vendor/pyproject_hooks/_in_process/_in_process.py", line 70, in _build_backend
          obj = import_module(mod_path)
        File "/usr/lib/python3.13/importlib/__init__.py", line 88, in import_module
          return _bootstrap._gcd_import(name[level:], package, level)
                 ~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        File "<frozen importlib._bootstrap>", line 1387, in _gcd_import
        File "<frozen importlib._bootstrap>", line 1360, in _find_and_load
        File "<frozen importlib._bootstrap>", line 1310, in _find_and_load_unlocked
        File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
        File "<frozen importlib._bootstrap>", line 1387, in _gcd_import
        File "<frozen importlib._bootstrap>", line 1360, in _find_and_load
        File "<frozen importlib._bootstrap>", line 1331, in _find_and_load_unlocked
        File "<frozen importlib._bootstrap>", line 935, in _load_unlocked
        File "<frozen importlib._bootstrap_external>", line 1026, in exec_module
        File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
        File "/tmp/pip-build-env-ms_oadkc/overlay/lib/python3.13/site-packages/setuptools/__init__.py", line 16, in <module>
          import setuptools.version
        File "/tmp/pip-build-env-ms_oadkc/overlay/lib/python3.13/site-packages/setuptools/version.py", line 1, in <module>
          import pkg_resources
        File "/tmp/pip-build-env-ms_oadkc/overlay/lib/python3.13/site-packages/pkg_resources/__init__.py", line 2191, in <module>
          register_finder(pkgutil.ImpImporter, find_on_path)
                          ^^^^^^^^^^^^^^^^^^^
      AttributeError: module 'pkgutil' has no attribute 'ImpImporter'. Did you mean: 'zipimporter'?
      [end of output]
  
  note: This error originates from a subprocess, and is likely not a problem with pip.
error: subprocess-exited-with-error

× Getting requirements to build wheel did not run successfully.
│ exit code: 1
╰─> See above for output.

note: This error originates from a subprocess, and is likely not a problem with pip.
raspi@raspi:~/14DTE-Project/mirror $ 
