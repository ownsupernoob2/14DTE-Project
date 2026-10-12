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
Part 2: The run-and-update script
Create C:\smart-mirror\run-and-update.ps1 with the contents below. It lives outside the repo folder so git pull never touches it.
$repo     = "C:\smart-mirror\server"
$exeName  = "smart-mirror-api"
$git      = "C:\Program Files\Git\cmd\git.exe"
$go       = "C:\Program Files\Go\bin\go.exe"
$log      = "C:\smart-mirror\updater.log"
$interval = 300   # seconds between update checks

# Go needs writable cache folders when running as SYSTEM
$env:GOCACHE = "C:\smart-mirror\.gocache"
$env:GOPATH  = "C:\smart-mirror\.gopath"
$env:PATH   += ";C:\Program Files\Git\cmd"

function Log($msg) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg" | Out-File -FilePath $log -Append -Encoding utf8
}
function Api-Running { [bool](Get-Process -Name $exeName -ErrorAction SilentlyContinue) }
function Start-Api {
    Log "Starting $exeName.exe"
    Start-Process -FilePath "$repo\$exeName.exe" -WorkingDirectory $repo -WindowStyle Hidden
}
function Stop-Api {
    Get-Process -Name $exeName -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
}
function Update-IfNeeded {
    Set-Location $repo
    $before = (& $git rev-parse HEAD).Trim()
    $out = & $git pull --ff-only 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { Log "git pull failed: $out"; return }
    $after = (& $git rev-parse HEAD).Trim()
    if ($before -eq $after) { return }

    Log "New commits found ($before -> $after). Building..."
    $build = & $go build -o "$exeName.new.exe" . 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        Log "Build failed, keeping the current version running: $build"
        return
    }
    Stop-Api
    Move-Item -Force "$repo\$exeName.new.exe" "$repo\$exeName.exe"
    Start-Api
    Log "Update applied and API restarted"
}

Log "Script started"
if (-not (Test-Path "$repo\$exeName.exe")) { Set-Location $repo; & $go build -o "$exeName.exe" . }
if (-not (Api-Running)) { Start-Api }

while ($true) {
    try { Update-IfNeeded } catch { Log "Error: $_" }
    if (-not (Api-Running)) { Log "API not running, restarting it"; Start-Api }
    Start-Sleep -Seconds $interval
}
What it does: starts the API at launch, then every 5 minutes pulls from git. If the commit changed, it builds into a temporary file first, and only if the build succeeds does it stop the running exe, swap the new one in and start it. A broken commit therefore never takes the API down. It also restarts the API if it ever crashes. Everything is logged to C:\smart-mirror\updater.log.
One-time git setting. The task runs as the SYSTEM account, and git may refuse to work in a folder owned by another user ("dubious ownership"). Run this once:
& "C:\Program Files\Git\cmd\git.exe" config --system --add safe.directory '*'
Things to check in your project:
• If the main package is not in the root of C:\smart-mirror\server (for example cmd/api), change the . after -o in both build lines to ./cmd/api.
• Do not commit the .exe. Add *.exe to .gitignore, otherwise git pull can fail on local changes.
• The API is started with C:\smart-mirror\server as its working directory, so any .env or config files it reads by relative path work the same as when you run it manually.
Part 3: Run it at boot with Task Scheduler
This registers a task that runs as SYSTEM at startup whether or not anyone is logged in. The time limit is disabled because Task Scheduler otherwise stops tasks after 72 hours.
$action    = New-ScheduledTaskAction -Execute "powershell.exe" -Argument '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\smart-mirror\run-and-update.ps1"'
$trigger   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "SmartMirrorAPI" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force
Start-ScheduledTask -TaskName "SmartMirrorAPI"
If you don't have administrator rights on the VM, you can't register a SYSTEM task. As a fallback, create the task for your own user with an At log on trigger and enable automatic login on the VM.
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