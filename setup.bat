@echo off
REM Smart Mirror Project - Quick Start Script for Windows

echo.
echo 🚀 Smart Mirror Project - Quick Start
echo =======================================
echo.

REM Check if Node is installed
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Node.js is not installed. Please install Node.js 16+
    exit /b 1
)

REM Check if Go is installed
where go >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Go is not installed. Please install Go 1.21+
    exit /b 1
)

for /f "tokens=*" %%i in ('node --version') do set NODE_VERSION=%%i
for /f "tokens=*" %%i in ('go version') do set GO_VERSION=%%i

echo ✅ Node.js version: %NODE_VERSION%
echo ✅ %GO_VERSION%
echo.

REM Frontend setup
echo 📦 Setting up frontend...
cd web
call npm install
echo ✅ Frontend dependencies installed
echo.

REM Backend setup
echo 📦 Setting up backend...
cd ..\server
call go mod download
call go mod tidy
echo ✅ Backend dependencies installed
echo.

REM Create .env file if it doesn't exist
if not exist .env (
    echo 📝 Creating .env file from template...
    copy .env.example .env
    echo ⚠️  Please edit server\.env with your Auth0 credentials
    echo.
)

echo =======================================
echo ✅ Setup complete!
echo.
echo To start development:
echo.
echo Frontend:
echo   cd web
echo   npm run dev
echo.
echo Backend:
echo   cd server
echo   go run main.go auth.go middleware.go
echo.
echo Or use Docker:
echo   cd server
echo   docker-compose up --build
echo.
echo Visit http://localhost:5173 for the frontend
echo API will be at http://localhost:8080
echo.
pause
