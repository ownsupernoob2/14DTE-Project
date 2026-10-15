<#
.SYNOPSIS
    Registers the Smart Mirror API supervisor to run automatically at Windows boot
    BEFORE any user logs in (as NT AUTHORITY\SYSTEM).
.DESCRIPTION
    Must be run in an Administrator PowerShell console.
    Configures:
    1. System-wide git safe.directory for the SYSTEM account
    2. Scheduled task with -AtStartup trigger running under SYSTEM
    3. Unlimited runtime execution (removes the default 72h limit)
#>

param (
    [switch]$Uninstall,
    [switch]$Status
)

$TaskName = "SmartMirrorAPI"

if ($Status) {
    Write-Host "Checking status of '$TaskName'..." -ForegroundColor Cyan
    Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Format-List TaskName, State
    Get-Process -Name "smart-mirror-api" -ErrorAction SilentlyContinue | Format-Table Id, ProcessName, WorkingSet64, StartTime
    exit 0
}

if ($Uninstall) {
    Write-Host "Unregistering '$TaskName'..." -ForegroundColor Yellow
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Get-Process -Name "smart-mirror-api" -ErrorAction SilentlyContinue | Stop-Process -Force
    Write-Host "Task '$TaskName' removed and process stopped." -ForegroundColor Green
    exit 0
}

# ── 1. Check Administrator Privileges ─────────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "This script must be run as Administrator! Please right-click PowerShell and select 'Run as Administrator'."
    exit 1
}

# ── 2. Locate run-and-update.ps1 ──────────────────────────────────────────────
$scriptPath = Join-Path $PSScriptRoot "run-and-update.ps1"
if (-not (Test-Path $scriptPath)) {
    Write-Error "Could not find run-and-update.ps1 at $scriptPath"
    exit 1
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Registering Smart Mirror API Startup Task (Boot Before Login)" -ForegroundColor Cyan
Write-Host "Target Script: $scriptPath"
Write-Host "=========================================================="

# ── 3. Configure Git safe.directory for SYSTEM account ────────────────────────
try {
    & git config --system --add safe.directory '*' 2>$null
    Write-Host "[OK] Configured git safe.directory for SYSTEM account" -ForegroundColor Green
} catch {
    Write-Warning "Could not configure git safe.directory. Ensure Git is installed."
}

# ── 4. Create Scheduled Task Definitions ──────────────────────────────────────
$actionArg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""
$action    = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArg
$trigger   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# Set execution time limit to zero (disabled, prevents stopping after 72 hours)
$settings  = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

# ── 5. Register and Start Task ────────────────────────────────────────────────
Write-Host "Registering Task '$TaskName'..."
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host "[OK] Task successfully registered!" -ForegroundColor Green

Write-Host "Starting task now to verify..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 5

$task = Get-ScheduledTask -TaskName $TaskName
Write-Host "Task State: $($task.State)" -ForegroundColor Yellow

$proc = Get-Process -Name "smart-mirror-api" -ErrorAction SilentlyContinue
if ($proc) {
    Write-Host "[OK] smart-mirror-api process is running (PID: $($proc.Id))" -ForegroundColor Green
} else {
    Write-Host "Notice: The process is starting in background. Check: Get-ScheduledTask $TaskName" -ForegroundColor Yellow
}

Write-Host "`nSetup complete! The server will now start automatically whenever Windows boots, before any user logs in." -ForegroundColor Green
