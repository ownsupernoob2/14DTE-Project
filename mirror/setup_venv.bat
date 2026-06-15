@echo off
echo ==========================================================
echo Setting up Smart Mirror Local Dev Environment (Windows)...
echo ==========================================================

cd /d "%~dp0"

echo.
echo --- Creating virtual environment in .venv...
python -m venv .venv

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to create virtual environment. Make sure Python is installed and added to PATH.
    pause
    exit /b 1
)

echo.
echo --- Activating virtual environment...
call .venv\Scripts\activate

echo.
echo --- Installing dependencies from requirements-dev.txt...
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements-dev.txt

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install pip dependencies.
    pause
    exit /b 1
)

if not exist gesture_recognizer.task (
    echo.
    echo --- Downloading MediaPipe gesture recognizer task...
    powershell -Command "Invoke-WebRequest -Uri 'https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task' -OutFile 'gesture_recognizer.task'"
)

echo.
echo ==========================================================
echo Setup Completed Successfully!
echo.
echo To run the mirror simulator:
echo   1. Open a terminal and run: .venv\Scripts\python.exe simulator_camera.py --mock
echo   2. Open a second terminal, set environment variable and run:
echo      $env:MIRROR_WINDOWED="1"
echo      .venv\Scripts\python.exe smart_mirror_pro.py
echo ==========================================================
pause
