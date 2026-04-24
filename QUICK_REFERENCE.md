# Smart Mirror - Quick Reference

## 🚀 Quick Start (2 minutes)

### Windows
```bash
cd c:\14DTE-Project
setup.bat
```

### macOS/Linux
```bash
cd ~/14DTE-Project
bash setup.sh
```

## 📂 What Was Created

### Frontend (React + Vite)
✅ **Pages:**
- `/login` - Login page  
- `/register` - Registration page
- `/` or `/dashboard` - Main dashboard with draggable widgets
- `/preferences` - User settings

✅ **Components:**
- Navbar with auto-hide (shows when mouse near top, hides after 10s)
- Draggable widget container
- Plus button to add widgets

✅ **Features:**
- Black background dashboard
- Add widgets: Clock, Weather, Calendar, Note
- Drag widgets to move them
- Remove widgets with X button
- All UI components with modern styling

### Backend (Go + Echo)
✅ **API Structure:**
- Auth endpoints (login, register, refresh)
- Protected user endpoints
- Dashboard/widget management
- JWT authentication ready
- CORS enabled

✅ **Files:**
- `main.go` - Routes & handlers
- `auth.go` - Auth0 integration
- `middleware.go` - JWT & error handling
- `Dockerfile` - Container setup
- `docker-compose.yml` - Multi-service setup

## ⚙️ Development Commands

### Frontend Terminal
```bash
cd web
npm install          # First time only
npm run dev         # Start dev server (http://localhost:5173)
npm run build       # Production build
npm run lint        # Check code quality
```

### Backend Terminal
```bash
cd server
go mod download     # First time only
go run main.go auth.go middleware.go  # Run API (http://localhost:8080)
go build -o api     # Build executable
```

### Docker
```bash
cd server
docker-compose up --build
# API at http://localhost:8080
# DB at localhost:5432
```

## 🔐 Auth0 Setup (Required for Full Features)

1. Create account at [auth0.com](https://auth0.com)
2. Create "Smart Mirror" Regular Web Application
3. Copy Domain, Client ID, Client Secret
4. Create "Smart Mirror API" - copy Identifier
5. Edit `server/.env`:
   ```env
   AUTH0_DOMAIN=your-domain.auth0.com
   AUTH0_CLIENT_ID=your-client-id
   AUTH0_CLIENT_SECRET=your-client-secret
   AUTH0_AUDIENCE=smart-mirror-api
   ```
6. Add to Auth0 "Allowed Callback URLs": `http://localhost:5173`
7. Add to Auth0 "Allowed Web Origins": `http://localhost:5173`, `http://localhost:8080`

## 📋 File Structure

```
14DTE-Project/
├── web/                           # React frontend
│   ├── src/
│   │   ├── pages/                # Page components
│   │   │   ├── Login.jsx
│   │   │   ├── Register.jsx
│   │   │   ├── Dashboard.jsx
│   │   │   └── Preferences.jsx
│   │   ├── components/           # Reusable components
│   │   │   ├── Navbar.jsx
│   │   │   └── WidgetContainer.jsx
│   │   ├── styles/               # CSS files
│   │   │   ├── global.css
│   │   │   ├── navbar.css
│   │   │   ├── dashboard.css
│   │   │   ├── widget.css
│   │   │   └── pages.css
│   │   └── App.jsx               # Router setup
│   └── package.json
│
├── server/                        # Go API
│   ├── main.go                   # Routes
│   ├── auth.go                   # Auth0 integration
│   ├── middleware.go             # JWT & errors
│   ├── go.mod                    # Dependencies
│   ├── Dockerfile                # Container
│   └── docker-compose.yml        # Services
│
├── SETUP_SUMMARY.md              # What was done
├── IMPLEMENTATION_GUIDE.md       # Full guide
├── setup.sh / setup.bat          # Quick setup
└── README.md                     # Root readme
```

## 🎯 Key Features Implemented

### Dashboard
- Black background ⬛
- Floating plus button (+) in bottom-right
- Click to see widget types menu
- Drag widgets anywhere on screen
- Close widgets with X button
- Supported widgets: Clock, Weather, Calendar, Note

### Navbar
- Hides by default
- Appears when mouse moves to top
- Auto-hides after 10 seconds of inactivity
- Smooth transitions with blur effect
- Links to Dashboard and Preferences

### Authentication Pages
- Login form with email/password
- Register form with confirmation
- Links between pages
- Styled with gradients

### Preferences
- Theme selection (Dark/Light)
- Language chooser
- Notification settings
- Account management buttons
- Logout functionality

## 🔌 API Endpoints

### Public
- `GET /health` - Health check
- `POST /auth/login` - Login
- `POST /auth/register` - Register
- `POST /auth/refresh` - Refresh token

### Protected (require JWT)
- `GET /api/users/me` - Current user
- `GET /api/users/:id` - Get user
- `PUT /api/users/:id` - Update user
- `GET /api/dashboard` - Get dashboard
- `GET /api/dashboard/widgets` - Get widgets
- `POST /api/dashboard/widgets` - Create widget
- `PUT /api/dashboard/widgets/:id` - Update widget
- `DELETE /api/dashboard/widgets/:id` - Delete widget

See `server/API_DOCS.md` for full details.

## 🐛 Troubleshooting

**Port already in use?**
```bash
# Windows: Find and kill process on port 8080
netstat -ano | findstr :8080
taskkill /PID <PID> /F

# Mac/Linux: Find and kill process
lsof -i :8080
kill -9 <PID>
```

**npm packages won't install?**
```bash
rm -rf node_modules package-lock.json
npm install
```

**Go modules error?**
```bash
go clean -modcache
go mod tidy
go mod download
```

**CORS error in console?**
- Backend CORS is enabled
- If still failing, check `main.go` middleware

## 📚 Documentation

- `SETUP_SUMMARY.md` - Overview of what was created
- `IMPLEMENTATION_GUIDE.md` - Complete implementation guide
- `web/README.md` - Frontend specific guide
- `server/README.md` - Backend specific guide
- `server/API_DOCS.md` - API endpoint documentation

## ✨ Next Steps

1. **Auth0 Integration** ← DO THIS FIRST
   - Set up Auth0 account
   - Configure Auth0 application
   - Update `.env` file
   - Install @auth0/auth0-react in frontend

2. **Database Setup**
   - Configure PostgreSQL
   - Create database models
   - Write migrations

3. **Testing**
   - Write unit tests
   - Integration tests
   - E2E tests

4. **Deployment**
   - Build Docker images
   - Deploy to Railway/Vercel/AWS
   - Set up monitoring

## 🎓 Learning Resources

- **React**: https://react.dev/
- **React Router**: https://reactrouter.com/
- **Go**: https://golang.org/doc/
- **Echo Framework**: https://echo.labstack.com/
- **Auth0**: https://auth0.com/docs
- **Docker**: https://docs.docker.com/

---

**Everything is ready! Start with Auth0 setup, then build out the database layer.** 🚀
