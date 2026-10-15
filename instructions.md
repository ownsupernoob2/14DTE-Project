Part 1: Create the Cloudflare Tunnel
1. Go to https://one.dash.cloudflare.com (Cloudflare Zero Trust). If this is your first time, choose a team name and the Free plan.
2. Open Networks → Tunnels (newer layouts may label it Connectors) and click Create a tunnel.
3. Choose Cloudflared, name it smart-mirror, and click Save tunnel.
4. Select Windows as the operating system. The dashboard shows an installer download link and a command containing your token. Install cloudflared, then run the command in the admin PowerShell. It looks like this:
   cloudflared.exe service install <YOUR-LONG-TOKEN>
   This registers cloudflared as a Windows service that starts automatically at boot. Treat the token like a password.
5. Back in the dashboard the connector should show Connected. Click Next.
6. Add a public hostname with these values:
    ◦ Subdomain: api
    ◦ Domain: smartmirror.me
    ◦ Service type: HTTP
    ◦ URL: localhost:8080
7. Save. Cloudflare creates the DNS record for api.smartmirror.me automatically. If an old api record already exists in your DNS, delete it first or the save will complain.
Verify the service is running:
Get-Service cloudflared
Until the API is running you will see a Cloudflare 502 error at the URL. That is expected.
Part 2: The run-and-update script (with Client Notifications & Safe Rollback)
The updater script is located in `server/run-and-update.ps1` (or can be placed at `C:\smart-mirror\run-and-update.ps1`). It monitors GitHub for updates on `main` without using Docker, broadcasts an update notice to connected Smart Mirrors and Web Dashboards, safely compiles the Go binary, verifies health, and restarts.

Key features:
1. **Pre-Update Notification**: Sets a banner (`/api/admin/banner` and `data/admin_banner.json`) and gives mirrors/browsers a 10-second grace window to display `"⚠️ Server is updating..."` before the server restarts.
2. **Discord/Slack Webhook Support**: If `DISCORD_WEBHOOK_URL` is set in `.env`, posts notifications with commit details directly to Discord.
3. **Safe Build & Rollback**: Compiles to `smart-mirror-api.new.exe` before touching the running process. If compilation fails, the working version stays online and git state is rolled back.
4. **Health Check Validation**: Verifies `GET /health` returns `200 OK` before marking the update complete and clearing the banner.
5. **Watchdog**: If the API crashes at any point, the script automatically restarts it.

Run it manually:
```powershell
powershell.exe -ExecutionPolicy Bypass -File .\server\run-and-update.ps1
```
Or simply double-click `server\start-server.bat`.
One-time git setting. The task runs as the SYSTEM account, and git may refuse to work in a folder owned by another user ("dubious ownership"). Run this once:
& "C:\Program Files\Git\cmd\git.exe" config --system --add safe.directory '*'
Things to check in your project:
• If the main package is not in the root of C:\smart-mirror\server (for example cmd/api), change the . after -o in both build lines to ./cmd/api.
• Do not commit the .exe. Add *.exe to .gitignore, otherwise git pull can fail on local changes.
• The API is started with C:\smart-mirror\server as its working directory, so any .env or config files it reads by relative path work the same as when you run it manually.
Part 3: Run it on boot before login with Task Scheduler
To have the server launch automatically as soon as Windows boots (without needing anyone to sign in), run the automated registration script in an Administrator PowerShell prompt:

```powershell
cd server
powershell.exe -ExecutionPolicy Bypass -File .\register-startup-task.ps1
```

### What this configures:
1. **Trigger (`-AtStartup`)**: Fires as soon as the operating system kernel starts up, well before the Windows login screen appears.
2. **Account (`NT AUTHORITY\SYSTEM`)**: Runs as a background service account in Session 0 so no user profile or password login is required.
3. **Execution Time Limit (`[TimeSpan]::Zero`)**: Disables Windows Task Scheduler's default 72-hour execution cap, allowing the supervisor to run continuously 24/7.
4. **Git Safe Directory**: Automatically executes `git config --system --add safe.directory '*'` so Git permits the SYSTEM user to pull repository updates without ownership conflicts.

### Useful Task Commands:
- Check Status: `powershell.exe -File .\server\register-startup-task.ps1 -Status`
- Stop Task: `Stop-ScheduledTask -TaskName "SmartMirrorAPI"`
- Start Task: `Start-ScheduledTask -TaskName "SmartMirrorAPI"`
- Uninstall Task: `powershell.exe -File .\server\register-startup-task.ps1 -Uninstall`
Part 4: Test it
1. Right now: wait about 10 seconds after the last command, then run Get-Process smart-mirror-api and open https://api.smartmirror.me.
2. After a reboot: run Restart-Computer, do not log in, and check https://api.smartmirror.me from another device after a minute or two.
3. Auto-update: push a small commit, wait up to 5 minutes, then run:
   Get-Content C:\smart-mirror\updater.log -Tail 20
Handy task commands:
Stop-ScheduledTask -TaskName "SmartMirrorAPI"
Start-ScheduledTask -TaskName "SmartMirrorAPI"
Unregister-ScheduledTask -TaskName "SmartMirrorAPI" -Confirm:$false
Stopping the task does not stop the API itself. Also run Stop-Process -Name smart-mirror-api if you want it down.
Troubleshooting
• Cloudflare 502 or 1033 at the URL: the API isn't running or the tunnel isn't connected. Check Get-Process smart-mirror-api and Get-Service cloudflared. If both are fine, change the hostname URL in the tunnel to 127.0.0.1:8080 in case the API only listens on IPv4.
• Log says "dubious ownership": run the safe.directory command from Part 2.
• Log says git or go can't be found: fix the two paths at the top of the script (see Step 0).
• Task didn't start after reboot: open Task Scheduler → Task Scheduler Library → SmartMirrorAPI and check Last Run Result and the History tab.
• Build keeps failing in the log: run go build -o test.exe . manually in C:\smart-mirror\server to see the real error, and check the main package path note in Part 2.