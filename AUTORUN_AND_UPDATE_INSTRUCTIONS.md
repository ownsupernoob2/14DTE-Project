# Smart Mirror: Auto-Update & Startup on Boot Guide

This guide covers setting up automatic GitHub updates and automated startup on boot for both the **Windows Server (Go API Backend)** and the **Raspberry Pi (Smart Mirror Client)**.

---

## Part 1: Windows Server (No Docker)

The Windows Server runs the Go backend API directly on bare metal without Docker, automatically monitors the `main` branch on GitHub, notifies connected mirrors and dashboards, rebuilds the binary, and starts up automatically at boot before any user logs in.

### 📁 Key Files
- `server/run-and-update.ps1`: The PowerShell supervisor and auto-updater script.
- `server/register-startup-task.ps1`: Automated installer that sets up the Windows Scheduled Task to run at boot under `NT AUTHORITY\SYSTEM`.
- `server/start-server.bat`: Quick desktop launcher for running the server and supervisor manually.

---

### 1. Configuration (`server/.env`)

Ensure your `server/.env` file exists and contains your desired settings:
```ini
PORT=8080
AUTH0_DOMAIN=dev-pgz1qjberxzo8hkl.us.auth0.com
AUTH0_AUDIENCE=https://dev-pgz1qjberxzo8hkl.us.auth0.com/api/v2/
MIRROR_API_KEY=your-secret-key

# Optional: Token required to post admin banners via /api/admin/banner
ADMIN_TOKEN=your-admin-token

# Optional: Discord webhook URL to receive notifications when server updates
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

---

### 2. How the Server Updater Works

```
1. Periodic Check (Every 120s):
   git fetch origin main -> Compares HEAD against origin/main.

2. If New Commits are Detected:
   a. Broadcaster: Updates data/admin_banner.json and posts to /api/admin/banner:
      "⚠️ Server is updating to latest build: <hash>. Brief restart in progress..."
   b. Optional: Sends an update alert to your Discord webhook.
   c. Grace Period: Waits 10 seconds so connected Smart Mirrors and Web Dashboards receive and render the banner.
   d. Pull & Compile:
      - Runs git pull --ff-only origin main
      - Compiles to smart-mirror-api.new.exe using go build
      - If build fails: Rolls back git state (git reset --hard), alerts failure, and keeps previous server running!
   e. Safe Swap:
      - Stops existing smart-mirror-api.exe process.
      - Moves smart-mirror-api.new.exe to smart-mirror-api.exe.
      - Starts new smart-mirror-api.exe.
   f. Health Check:
      - Polls http://localhost:8080/health until it responds with 200 OK.
      - Sets banner to "✅ Server update complete! All services operational." for 20s, then clears it.

3. Crash Watchdog:
   If the API process ever exits or crashes unexpectedly, the supervisor automatically restarts it.
```

---

### 3. Setting Up Start on Boot Before Login

To make the server start when Windows boots up without requiring anyone to log in:

1. Open **PowerShell as Administrator** (Right-click PowerShell -> *Run as administrator*).
2. Navigate to the `server` folder and run:
   ```powershell
   cd server
   powershell.exe -ExecutionPolicy Bypass -File .\register-startup-task.ps1
   ```

#### Why This Works Before Login:
- **`-AtStartup` Trigger**: Triggers immediately when the Windows kernel finishes booting up, before the user logon screen.
- **`NT AUTHORITY\SYSTEM` Service Account**: Runs in Windows Session 0. Does not require any user credentials or desktop sessions.
- **Execution Limit Removed**: Disables Windows Task Scheduler's 72-hour limit (`[TimeSpan]::Zero`) so it runs 24/7.
- **Git `safe.directory`**: Automatically configures `git config --system --add safe.directory '*'` to prevent permission errors under `SYSTEM`.

#### Useful Management Commands:
```powershell
# Check task status and running process PID
powershell.exe -File .\server\register-startup-task.ps1 -Status

# Stop the task
Stop-ScheduledTask -TaskName "SmartMirrorAPI"

# Start the task
Start-ScheduledTask -TaskName "SmartMirrorAPI"

# View real-time updater logs
Get-Content .\server\updater.log -Wait -Tail 20

# Completely remove / uninstall the startup task
powershell.exe -File .\server\register-startup-task.ps1 -Uninstall
```

---

## Part 2: Raspberry Pi Mirror (Linux)

The Raspberry Pi runs the camera pipeline (`rpicam-vid` + `ffmpeg`), the face recognition daemon (`face_recognize.py`), and the PyQt UI (`smart_mirror_pro.py`). The auto-updater monitors GitHub, pulls updates, updates Python dependencies, and restarts the mirror pipeline.

### 📁 Key Files
- `mirror/start_smart_mirror.sh`: The main launch script that starts the camera pipeline, face daemon, UI, and spawns the background auto-updater.
- `mirror/auto_updater.sh`: The lightweight background watcher spawned by `start_smart_mirror.sh`.
- `mirror/setup.sh`: Automated installer configuring packages, virtual environment, and desktop autostart.

---

### 1. How the Mirror Updater Works

```
1. Startup via start_smart_mirror.sh:
   - Kills any previous camera, face detection, UI, or updater processes.
   - Sets up v4l2loopback virtual camera (/dev/video20).
   - Starts rpicam-vid -> ffmpeg camera pipeline.
   - Starts face_recognize.py --rpi.
   - Starts gesture_engine.py --rpi --flip.
   - Starts smart_mirror_pro.py on DISPLAY=:0.
   - Spawns auto_updater.sh in the background.

2. Background Polling (Every 120s):
   - auto_updater.sh wakes up and runs git fetch origin main.
   - Compares local commit vs origin/main.

3. When New Updates are Found:
   - Logs commit details to mirror/updater.log.
   - Pulls updates: git pull --ff-only origin main.
   - If requirements.txt changed: runs pip install -r requirements.txt.
   - Restarts mirror: Runs /bin/bash ./start_smart_mirror.sh
     (This cleanly stops existing processes, resets camera, and boots into the updated mirror!)
```

---

### 2. Autostart on Boot

Since your Pi's `~/.config/autostart/smart_mirror.desktop` runs `start_smart_mirror.sh` on boot:
- **No changes to your autostart setup are needed!**
- Every time the Pi boots into the desktop, `start_smart_mirror.sh` runs as usual, launches the mirror, and automatically starts `auto_updater.sh` in the background.

---

### 3. Manual Testing & Controls

#### Run the Mirror Manually:
```bash
cd ~/14DTE-Project/mirror
./start_smart_mirror.sh
```

#### View Real-time Update Logs:
```bash
tail -f ~/14DTE-Project/mirror/updater.log
```

#### Check Logs:
```bash
# View updater & git logs:
tail -f ~/14DTE-Project/mirror/updater.log

# View mirror application logs:
tail -f ~/14DTE-Project/mirror/mirror.log
```

#### Stop All Mirror Processes:
```bash
pkill -f run_and_update_mirror
pkill -f rpicam-vid
pkill -f ffmpeg
pkill -f face_recognize
pkill -f gesture_engine
pkill -f smart_mirror_pro
```
