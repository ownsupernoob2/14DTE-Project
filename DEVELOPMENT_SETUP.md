# Development Environment Setup Guide

## Prerequisites Check

Before starting, verify you have:

```
✅ Node.js 16+ installed     → node --version
✅ npm installed            → npm --version  
✅ Go 1.21+ installed       → go version
✅ Git installed            → git --version
```

## Windows Users - Use setup.bat

```powershell
# Open Command Prompt or PowerShell
cd C:\14DTE-Project
setup.bat
```

The script will:
1. Install frontend dependencies
2. Install backend dependencies
3. Create `.env` file
4. Show next steps

## Mac/Linux Users - Use setup.sh

```bash
cd ~/14DTE-Project
chmod +x setup.sh
bash setup.sh
```

## Manual Setup (All Platforms)

### Step 1: Frontend Setup

```bash
cd web
npm install

# Wait for completion...
```

**Expected output:**
```
added XX packages in X.XXs
```

### Step 2: Backend Setup

```bash
cd ../server
go mod download
go mod tidy

# Wait for completion...
```

**Expected output:**
```
go: downloading ...
```

### Step 3: Configure Auth0 (Optional now, Required later)

```bash
cd server
cp .env.example .env

# Edit .env with your Auth0 credentials later
```

---

## Running the Application

### Option 1: Development Mode (Recommended)

**Terminal 1 - Frontend:**
```bash
cd web
npm run dev
```

**Expected output:**
```
  VITE v5.0.0  ready in XXX ms
  ➜  Local:   http://localhost:5173/
  ➜  Press h to show help
```

**Terminal 2 - Backend:**
```bash
cd server
go run main.go auth.go middleware.go
```

**Expected output:**
```
   ╭─────────────────────────────────────────────────────╮
   │                   Echo v4.11.3                       │
   ├─────────────────────────────────────────────────────┤
   │ ✓ bound to 0.0.0.0:8080                             │
   ╰─────────────────────────────────────────────────────╯
```

### Option 2: Using Docker (Requires Docker Desktop)

```bash
cd server
docker-compose up --build
```

**Expected output:**
```
Creating smart_mirror_db_1 ... done
Creating smart_mirror_api_1 ... done
api_1  | 
api_1  |    ╭─────────────────────────────────────────────────────╮
api_1  |    │                   Echo v4.11.3                       │
api_1  |    ├─────────────────────────────────────────────────────┤
api_1  |    │ ✓ bound to 0.0.0.0:8080                             │
api_1  |    ╰─────────────────────────────────────────────────────╯
```

---

## Verify It's Working

### Frontend
1. Open http://localhost:5173 in browser
2. You should see the Login page
3. Try navigating: Dashboard (→ /dashboard), Preferences (→ /preferences)

### Backend
1. Open http://localhost:8080/health in browser
2. Should return: `{"status":"ok"}`

### Both Together
1. Try clicking around in frontend
2. Check browser console (F12) for any errors
3. Check terminal for API logs

---

## Common Issues & Fixes

### Issue: "Port 5173 already in use"
```bash
# Change Vite port
cd web
npm run dev -- --port 3000
# Now visit http://localhost:3000
```

### Issue: "Port 8080 already in use"

**Windows:**
```powershell
netstat -ano | findstr :8080
taskkill /PID <PID> /F
```

**Mac/Linux:**
```bash
lsof -i :8080
kill -9 <PID>
```

### Issue: "npm packages won't install"
```bash
rm -rf node_modules package-lock.json
npm install
```

### Issue: "Go modules error"
```bash
go clean -modcache
go mod tidy
go mod download
```

### Issue: "Can't connect frontend to backend"
- Check backend is running on port 8080
- Check CORS is enabled in backend (it is by default)
- Check browser console for actual error

---

## Testing the Features

### Dashboard
1. Navigate to http://localhost:5173/dashboard
2. Click the **+** button in bottom-right
3. Select "Clock" from menu
4. A clock widget appears
5. Try dragging it around
6. Click **X** to remove it

### Navbar
1. Move mouse to the top of the page
2. Navbar should slide down
3. Move mouse away
4. Navbar stays visible for 10 seconds then hides

### Authentication Pages
1. Visit http://localhost:5173/login
2. Visit http://localhost:5173/register
3. Click links to navigate between pages

### Preferences
1. Visit http://localhost:5173/preferences
2. Try changing theme, language, notifications
3. Click Account buttons

---

## Development Workflow

### Making Changes

**Frontend:**
1. Edit files in `web/src/`
2. Changes auto-refresh (HMR)
3. Check browser console for errors

**Backend:**
1. Edit `.go` files in `server/`
2. Stop running process (Ctrl+C)
3. Run: `go run main.go auth.go middleware.go`
4. Test with API tools or frontend

### Useful Commands

```bash
# Frontend
npm run build      # Production build
npm run preview    # Preview build
npm run lint       # Check code quality

# Backend
go test ./...      # Run tests
go build -o api    # Build executable
go fmt ./...       # Format code
golint ./...       # Lint code
```

---

## Building for Production

### Frontend

```bash
cd web
npm run build
npm run preview  # Preview the build locally
```

**Output:** `dist/` folder ready for deployment

### Backend

```bash
cd server
go build -o smart-mirror-api
./smart-mirror-api
```

**Output:** Executable binary ready for deployment

---

## Stopping the Application

**Terminal:**
- Press `Ctrl+C` in each terminal

**Docker:**
```bash
docker-compose down
```

---

## Next Steps

1. **Test the current setup** (should work as-is)
2. **Set up Auth0** (required for login)
3. **Connect frontend to backend** (after Auth0)
4. **Implement database** (after basic testing)
5. **Deploy to production** (after full testing)

---

## Getting Help

1. Check terminal error messages
2. Look at browser console (F12)
3. Review `IMPLEMENTATION_GUIDE.md`
4. Check `server/API_DOCS.md` for API details
5. Review component source code

---

## Quick Reference

| Task | Command |
|------|---------|
| Start Frontend | `cd web && npm run dev` |
| Start Backend | `cd server && go run main.go auth.go middleware.go` |
| Start Both (Docker) | `cd server && docker-compose up` |
| Build Frontend | `cd web && npm run build` |
| Build Backend | `cd server && go build -o api` |
| Check Frontend | http://localhost:5173 |
| Check Backend | http://localhost:8080/health |
| View Logs | Check terminal output |

---

**You're all set! Happy coding! 🚀**
