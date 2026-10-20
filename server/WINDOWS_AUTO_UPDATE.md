# Windows Server Auto-Updater & Supervisor Guide

This document describes how to run and automate the Smart Mirror Go server on Windows so that it continuously monitors GitHub for updates on the `main` branch, compiles the Go binary, notifies frontends before updating, and restarts automatically with zero manual intervention.

---

## 1. How the Auto-Update System Works

The Windows auto-updater (`run-and-update.ps1`) performs the following continuous cycle:

```
+------------------------------------------------------------------------+
| 1. Watchdog: Checks every 120s (configurable) for Git commits on main  |
+-----------------------------------v------------------------------------+
| 2. Update Detected:                                                    |
|    - Broadcasts notification to Mirror and Web via /api/admin/banner   |
|      "[UPDATE] Server is updating to latest build. Restart in progress"|
|    - Waits 10s grace period for connected clients to receive alert     |
+-----------------------------------v------------------------------------+
| 3. Fast-Forward Pull: git pull --ff-only origin main                   |
+-----------------------------------v------------------------------------+
| 4. Compiles: go build -o smart-mirror-api.new.exe .                    |
|    - If compilation fails: rolls back to previous commit automatically |
+-----------------------------------v------------------------------------+
| 5. Process Swap: Stops old smart-mirror-api.exe, replaces with new,     |
|    and launches the updated binary                                     |
+-----------------------------------v------------------------------------+
| 6. Health Validation: Polls http://localhost:8080/health               |
|    - On Success: broadcasts completion notice, clears after 20s        |
|    - Supervisor watchdog: restarts server if it ever crashes           |
+------------------------------------------------------------------------+
```

---

## 2. Prerequisites on Windows

Ensure the Windows host machine has:
1. **Git for Windows**: Installed and available in PATH (`git --version`).
2. **Go (Golang)**: Go 1.20+ installed and in PATH (`go version`).
3. **PowerShell 5.1 or PowerShell 7+**.
4. **Python 3.10, 3.11 or 3.12** for face scans, installed *for all users* from python.org. `run-and-update.ps1` runs `setup-face-python.ps1` at start and after each update, which creates `server\.venv` with face_recognition. Run it by hand once to check:
   ```powershell
   cd server
   powershell -ExecutionPolicy Bypass -File .\setup-face-python.ps1
   ```

Settings live in `server\.env` (see `.env.example`): `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, `ADMIN_EMAILS`, `MIRROR_API_KEY` (the same value goes on every mirror), `ADMIN_TOKEN`, and optionally `AUTH0_MGMT_CLIENT_ID` / `AUTH0_MGMT_CLIENT_SECRET` so deleting a user also deletes their Auth0 login.

All data is in `server\data\smartmirror.db` (SQLite) plus `server\data\screensaver\`. Back up the `data` folder.

---

## 3. Option A: Quick Manual Start (Interactive Console)

Double-click `start-server.bat` in the `server\` directory, or run from PowerShell:

```powershell
cd server
.\run-and-update.ps1 -IntervalSeconds 120 -Branch main
```

**Parameters:**
- `-IntervalSeconds <int>`: Polling frequency for Git checks (default: `120` seconds / 2 minutes).
- `-Branch <string>`: Target Git branch to watch and deploy (default: `main`).

---

## 4. Option B: Automatic Startup at Windows Boot (Background Service)

To run the server 24/7 without needing an interactive user login (running automatically when the Windows PC boots):

1. Open PowerShell **as Administrator** (Right-click Start > "Terminal (Admin)" or "Windows PowerShell (Admin)").
2. Navigate to your server folder:
   ```powershell
   cd "E:\Code\offical\14DTE-Project\server"
   ```
3. Run the registration script:
   ```powershell
   .\register-startup-task.ps1
   ```

This configures:
- A Windows Scheduled Task named `SmartMirrorAPI` running under `NT AUTHORITY\SYSTEM`.
- Triggers at system startup (`-AtStartup`).
- Unlimited runtime (no default 72-hour Task Scheduler timeout).
- Auto-restart if the supervisor is ever terminated.

### Managing the Scheduled Task:
- **Check Status**:
  ```powershell
  .\register-startup-task.ps1 -Status
  ```
- **Stop and Uninstall**:
  ```powershell
  .\register-startup-task.ps1 -Uninstall
  ```

---

## 5. Front-End Notifications

When an update is pulled, the updater sends notifications through two channels:
1. **Real-Time API & Mirror/Web Banner**:
   - Posts to `/api/admin/banner` and writes `data/admin_banner.json`.
   - Connected Raspberry Pi mirrors and web clients polling `/api/banner` immediately show the notice.
2. **Optional Discord Webhook**:
   - If `DISCORD_WEBHOOK_URL` is configured in `server/.env`, notifications are posted to Discord automatically.

---

## 6. Logs & Diagnostics

- **Supervisor and Update Log**: `server/updater.log`
- **Health Check Endpoint**: `http://localhost:8080/health` (returns `{"status":"ok","version":"v1.2.0"}`)
- **Version Endpoint**: `http://localhost:8080/api/version` (returns `{"version":"v1.2.0","service":"smart-mirror-api"}`)
