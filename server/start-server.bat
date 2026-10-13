@echo off
REM Quick launcher for Smart Mirror API Supervisor & Auto-Updater (No Docker)
cd /d "%~dp0"
echo Starting Smart Mirror API with Auto-Updater...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-and-update.ps1"
pause
