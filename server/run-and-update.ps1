<#
.SYNOPSIS
    Smart Mirror API - Windows Auto-Updater & Supervisor (No Docker)
    Monitors GitHub for updates on the main branch, notifies active users
    (via Mirror/Web banner and optional Discord webhook), rebuilds the Go binary,
    and restarts the server with health-check validation and auto-rollback.
#>

param (
    [string]$RepoPath = "",
    [int]$IntervalSeconds = 120,
    [string]$Branch = "main"
)

# ── 1. Configuration & Auto-Detection ─────────────────────────────────────────

# Locate server repo folder (defaults to script's directory, or C:\smart-mirror\server)
if (-not $RepoPath) {
    if (Test-Path "$PSScriptRoot\main.go") {
        $RepoPath = $PSScriptRoot
    } elseif (Test-Path "C:\smart-mirror\server\main.go") {
        $RepoPath = "C:\smart-mirror\server"
    } else {
        $RepoPath = (Get-Location).Path
    }
}

$exeName  = "smart-mirror-api"
$logFile  = Join-Path $RepoPath "updater.log"

# Find git.exe
$git = (Get-Command "git.exe" -ErrorAction SilentlyContinue).Source
if (-not $git) {
    if (Test-Path "C:\Program Files\Git\cmd\git.exe") {
        $git = "C:\Program Files\Git\cmd\git.exe"
    } else {
        Write-Error "git.exe could not be found. Please ensure Git is installed and in PATH."
        exit 1
    }
}

# Find go.exe
$go = (Get-Command "go.exe" -ErrorAction SilentlyContinue).Source
if (-not $go) {
    if (Test-Path "C:\Program Files\Go\bin\go.exe") {
        $go = "C:\Program Files\Go\bin\go.exe"
    } else {
        Write-Error "go.exe could not be found. Please ensure Go is installed and in PATH."
        exit 1
    }
}

# Go cache settings (required when running as Windows SYSTEM or Scheduled Task)
if (-not $env:GOCACHE) { $env:GOCACHE = Join-Path $RepoPath ".gocache" }
if (-not $env:GOPATH)  { $env:GOPATH  = Join-Path $RepoPath ".gopath" }

# Read environment variables from .env if present
$port = "8080"
$adminToken = ""
$discordWebhook = ""

$envFile = Join-Path $RepoPath ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $k = $parts[0].Trim()
            $v = $parts[1].Trim()
            if ($k -eq "PORT") { $port = $v }
            if ($k -eq "ADMIN_TOKEN") { $adminToken = $v }
            if ($k -eq "DISCORD_WEBHOOK_URL") { $discordWebhook = $v }
        }
    }
}

# ── 2. Logging & Notification Utilities ───────────────────────────────────────

function Write-Log($msg) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] $msg"
    Write-Host $line
    $line | Out-File -FilePath $logFile -Append -Encoding utf8
}

function Send-DiscordNotification($message) {
    if (-not $discordWebhook) { return }
    try {
        $payload = @{
            content = $message
            username = "Smart Mirror Server"
        } | ConvertTo-Json -Compress

        Invoke-RestMethod -Uri $discordWebhook -Method Post -Body $payload -ContentType "application/json" -TimeoutSec 5 -ErrorAction SilentlyContinue | Out-Null
    } catch {
        Write-Log "Failed to send Discord webhook: $_"
    }
}

function Notify-Clients($message) {
    Write-Log "Broadcasting Notification: $message"

    # 1. Update data/admin_banner.json directly on disk (ensures state persists across restarts)
    $dataDir = Join-Path $RepoPath "data"
    if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir -Force | Out-Null }
    $bannerFile = Join-Path $dataDir "admin_banner.json"
    @{ message = $message } | ConvertTo-Json | Set-Content -Path $bannerFile -Encoding utf8 -Force

    # 2. If the API is currently alive, send live POST /api/admin/banner so clients fetch immediately
    if (Test-ApiRunning) {
        try {
            $headers = @{}
            if ($adminToken) { $headers["X-Admin-Token"] = $adminToken }
            $body = @{ message = $message } | ConvertTo-Json -Compress
            Invoke-RestMethod -Uri "http://localhost:$port/api/admin/banner" -Method Post -Body $body -Headers $headers -ContentType "application/json" -TimeoutSec 3 -ErrorAction SilentlyContinue | Out-Null
        } catch {
            # In-memory update failed, but data/admin_banner.json is already updated
        }
    }

    # 3. Send optional Discord/External Webhook
    Send-DiscordNotification $message
}

function Clear-ClientsNotification() {
    Notify-Clients ""
}

# ── 3. Process Management & Health Checks ─────────────────────────────────────

function Test-ApiRunning {
    return [bool](Get-Process -Name $exeName -ErrorAction SilentlyContinue)
}

function Start-ApiProcess {
    Write-Log "Starting $exeName.exe on port $port..."
    Set-Location $RepoPath
    Start-Process -FilePath (Join-Path $RepoPath "$exeName.exe") -WorkingDirectory $RepoPath -WindowStyle Hidden
}

function Stop-ApiProcess {
    Write-Log "Stopping running $exeName process..."
    Get-Process -Name $exeName -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
}

function Wait-ApiHealthy([int]$timeoutSeconds = 20) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $timeoutSeconds) {
        try {
            $res = Invoke-RestMethod -Uri "http://localhost:$port/health" -Method Get -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($res.status -eq "ok") {
                return $true
            }
        } catch {}
        Start-Sleep -Seconds 1
    }
    return $false
}

# ── 4. Update Engine ──────────────────────────────────────────────────────────

function Check-And-Apply-Updates {
    Set-Location $RepoPath

    # 1. Fetch remote tracking branch
    $fetchOut = & $git fetch origin $Branch 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        Write-Log "git fetch origin $Branch failed: $fetchOut"
        return
    }

    $localSha = (& $git rev-parse HEAD).Trim()
    $remoteSha = (& $git rev-parse "origin/$Branch").Trim()

    if ($localSha -eq $remoteSha) {
        # Already up to date
        return
    }

    # Retrieve commit details for the notification
    $commitSummary = (& $git log -1 --format="%h: %s" "origin/$Branch").Trim()
    Write-Log "New commits found on origin/$Branch ($localSha -> $remoteSha): $commitSummary"

    # Step A: Notify connected mirrors and web clients BEFORE taking anything down
    $updateNotice = "[UPDATE] Server is updating to latest build ($commitSummary). Restart in progress..."
    Notify-Clients $updateNotice

    # Allow a 10-second grace window so connected clients (polling /api/banner) receive the warning
    Write-Log "Waiting 10s for connected mirrors & clients to receive update notice..."
    Start-Sleep -Seconds 10

    # Step B: Fast-forward git repository
    $pullOut = & $git pull --ff-only origin $Branch 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        Write-Log "git pull failed: $pullOut"
        Notify-Clients "[ERROR] Server update failed during git pull. Continuing with previous version."
        Start-Sleep -Seconds 10
        Clear-ClientsNotification
        return
    }

    # Step C: Compile new binary to a temporary target (smart-mirror-api.new.exe)
    Write-Log "Building new Go binary ($exeName.new.exe)..."
    $buildOut = & $go build -o "$exeName.new.exe" . 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Build failed! Output: $buildOut"
        Notify-Clients "[ERROR] Go build failed on latest commit. Rolling back changes."

        # Revert git pull so code remains in working state
        & $git reset --hard $localSha 2>&1 | Out-Null

        Start-Sleep -Seconds 10
        Clear-ClientsNotification
        return
    }

    # Step D: Build succeeded. Stop old API and replace executable
    Stop-ApiProcess
    Move-Item -Force "$RepoPath\$exeName.new.exe" "$RepoPath\$exeName.exe"

    # Step E: Launch new binary and check health
    Start-ApiProcess
    $isHealthy = Wait-ApiHealthy -timeoutSeconds 20

    if ($isHealthy) {
        Write-Log "Update successfully applied! Server is healthy on port $port."
        Notify-Clients "[OK] Server update complete ($commitSummary). All services operational."
        # Keep success notice visible for 20s, then clear
        Start-Sleep -Seconds 20
        Clear-ClientsNotification
    } else {
        Write-Log "WARNING: API did not respond to /health after restart!"
        Notify-Clients "[WARNING] Server updated, but health check is pending. Please verify server status."
    }
}

# ── 5. Main Supervisor Loop ───────────────────────────────────────────────────

Write-Log "=========================================================="
Write-Log "Smart Mirror API Supervisor & Auto-Updater Started"
Write-Log "Repo Path: $RepoPath"
Write-Log "Branch:    $Branch"
Write-Log "Interval:  $IntervalSeconds seconds"
Write-Log "=========================================================="

# Initial build if binary does not exist
if (-not (Test-Path "$RepoPath\$exeName.exe")) {
    Write-Log "$exeName.exe not found. Running initial build..."
    Set-Location $RepoPath
    & $go build -o "$exeName.exe" .
}

# Ensure API is running at start
if (-not (Test-ApiRunning)) {
    Start-ApiProcess
    Wait-ApiHealthy -timeoutSeconds 15 | Out-Null
}

# Continuous loop
while ($true) {
    try {
        Check-And-Apply-Updates
    } catch {
        Write-Log "Error during update check: $_"
    }

    # Watchdog: restart server if it unexpectedly stopped
    if (-not (Test-ApiRunning)) {
        Write-Log "WARNING: $exeName is not running. Restarting..."
        Start-ApiProcess
        Wait-ApiHealthy -timeoutSeconds 15 | Out-Null
    }

    Start-Sleep -Seconds $IntervalSeconds
}
