# Raspberry Pi Smart Mirror Setup Guide (Updated)

This guide sets up your Smart Mirror to run using the Graphical Desktop Autostart system. This is the **correct way** to launch GUI/Pygame applications on boot, avoiding graphical/XDG environment errors.

---

## STEP 1: Update and pull the latest code

Make sure you have all the latest updates on the Raspberry Pi:
```bash
cd ~/14DTE-Project
git fetch origin main
git reset --hard origin/main
git pull origin main
```

---

## STEP 2: Disable the old systemd service (if active)

Since systemd runs in the background without graphical display access, we will stop and disable it to prevent it from conflicting:
```bash
sudo systemctl stop smartmirror.service
sudo systemctl disable smartmirror.service
```

---

## STEP 3: Make the scripts executable

```bash
chmod +x ~/14DTE-Project/mirror/start_smart_mirror.sh
chmod +x ~/14DTE-Project/mirror/update_mirror.sh
```

---

## STEP 4: Set up GUI Autostart on boot

This creates a desktop entry that launches `start_smart_mirror.sh` automatically as soon as the Raspberry Pi GUI boots up and logs in:

1. Create the autostart directory:
   ```bash
   mkdir -p ~/.config/autostart
   ```

2. Create and edit the autostart config file:
   ```bash
   nano ~/.config/autostart/smartmirror.desktop
   ```

3. Paste this exact block into the file:
   ```ini
   [Desktop Entry]
   Type=Application
   Name=Smart Mirror
   Exec=/home/raspi/14DTE-Project/mirror/start_smart_mirror.sh
   StartupNotify=false
   Terminal=false
   ```
   *(Save: press `CTRL+O`, then `ENTER`, then `CTRL+X` to exit)*

---

## STEP 5: Set up auto-update cron job (checks GitHub every 5 minutes)

We want to poll GitHub for updates. If there are new commits, it automatically pulls and restarts the mirror.

1. Open the cron editor:
   ```bash
   crontab -e
   ```
   *(If prompted, press `1` to choose nano)*

2. Scroll to the very bottom of the file and paste this line:
   ```text
   */5 * * * * /home/raspi/14DTE-Project/mirror/update_mirror.sh >> /home/raspi/mirror_update.log 2>&1
   ```
   *(Save: press `CTRL+O`, then `ENTER`, then `CTRL+X` to exit)*

---

## STEP 6: Run it manually to test!

To launch everything right now without rebooting:
```bash
~/14DTE-Project/mirror/start_smart_mirror.sh
```

---

## How to Verify Everything is Running

### 1. View running Pygame / camera processes:
```bash
ps aux | grep -E 'python|ffmpeg|rpicam'
```

### 2. View auto-update logs:
```bash
tail -f ~/mirror_update.log
```

---

## Done! Your new workflow:

1. Edit mirror code on your Windows PC.
2. Push to GitHub `main` branch.
3. Within 5 minutes, the Pi pulls, triggers `start_smart_mirror.sh`, kills old processes, and launches the updated layout connected to `api.smartmirror.me`!
