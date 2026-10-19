@echo off
cd /d "%~dp0"
echo ==========================================================
echo Starting Smart Mirror in Windowed Mode (Windows)...
echo ==========================================================

REM Enable windowed mode (1280x800) instead of fullscreen
set MIRROR_WINDOWED=1

REM Check if .venv exists
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found in .venv!
    echo Please run setup_venv.bat first.
    pause
    exit /b 1
)

echo Starting smart_mirror_pro.py...
.venv\Scripts\python.exe smart_mirror_pro.py %*
pause
