# Smart Mirror - Complete Implementation Guide

## 📋 Table of Contents
1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Frontend Setup](#frontend-setup)
4. [Backend Setup](#backend-setup)
5. [Auth0 Integration](#auth0-integration)
6. [Development Workflow](#development-workflow)
7. [Deployment](#deployment)
8. [Troubleshooting](#troubleshooting)

---

## Project Overview

Smart Mirror is a full-stack application with:
- **Frontend**: React + Vite with React Router
- **Backend**: Go + Echo web framework
- **Authentication**: Auth0 OAuth2
- **Database**: PostgreSQL (to be implemented)

### Key Features
✨ Interactive dashboard with draggable widgets  
✨ Auto-hiding navbar (shows on mouse hover)  
✨ User authentication with Auth0  
✨ Real-time widget management  
✨ User preferences management  
✨ RESTful API with JWT protection  

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Browser                              │
│  ┌──────────────────────────────────────────────────┐  │
│  │     React Frontend (Vite)                        │  │
│  │  ┌────────────────────────────────────────────┐  │  │
│  │  │  Dashboard  │  Preferences  │  Auth Pages  │  │  │
│  │  │  (Widgets)  │  (Settings)   │  (Login)    │  │  │
│  │  └────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────┬──────────────────────────────────────┘
                  │ HTTPS/REST API
                  │ (JWT Auth)
┌─────────────────▼──────────────────────────────────────┐
│               Go Echo Server (API)                      │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Routes  │  Middleware  │  Handlers             │  │
│  │  - Auth  │  - JWT       │  - User Management    │  │
│  │  - Users │  - CORS      │  - Widget Management  │  │
│  │  - Dash  │  - Logging   │  - Dashboard          │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────┬──────────────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
    ┌───▼────┐         ┌───▼────┐
    │ Auth0  │         │   DB   │
    │ OAuth2 │         │PostgreSQL
    └────────┘         └────────┘
```

---

## Frontend Setup

### Prerequisites
- Node.js 16+ ([Download](https://nodejs.org/))
- npm or yarn

### Installation

```bash
cd web
npm install
```

### Project Structure
```
web/
├── src/
│   ├── pages/
│   │   ├── Login.jsx         # Login form
│   │   ├── Register.jsx      # Registration form
│   │   ├── Dashboard.jsx     # Main dashboard with widgets
│   │   └── Preferences.jsx   # User preferences
│   ├── components/
│   │   ├── Navbar.jsx        # Auto-hiding navbar
│   │   └── WidgetContainer.jsx # Draggable widget
│   ├── styles/
│   │   ├── global.css        # Global styles
│   │   ├── navbar.css        # Navbar styles
│   │   ├── dashboard.css     # Dashboard styles
│   │   ├── widget.css        # Widget styles
│   │   └── pages.css         # Page styles
│   ├── App.jsx              # Router setup
│   ├── App.css              # App styles
│   └── main.jsx             # Entry point
├── public/                   # Static assets
├── package.json             # Dependencies
└── README.md                # Frontend docs
```

### Running Development Server
```bash
cd web
npm run dev
```
Access at `http://localhost:5173`

### Building for Production
```bash
npm run build
npm run preview
```

### Development Features
- Hot Module Replacement (HMR)
- Fast refresh
- ESLint validation
- Vite optimization

---

## Backend Setup

### Prerequisites
- Go 1.21+ ([Download](https://golang.org/dl/))
- PostgreSQL 13+ ([Download](https://www.postgresql.org/download/))

### Installation

```bash
cd server
go mod download
go mod tidy
```

### Project Structure
```
server/
├── main.go           # Application entry & routes
├── auth.go           # Auth0 integration
├── middleware.go     # JWT & error handling
├── go.mod            # Go modules
├── go.sum            # Module checksums
├── Dockerfile        # Container image
├── docker-compose.yml # Multi-container setup
├── .env.example      # Environment template
└── README.md         # Backend docs
```

### Environment Variables
Create `.env` file:
```bash
cp .env.example .env
```

Edit `.env`:
```
AUTH0_DOMAIN=your-domain.auth0.com
AUTH0_CLIENT_ID=your-client-id
AUTH0_CLIENT_SECRET=your-client-secret
AUTH0_AUDIENCE=your-api-audience
PORT=8080
DATABASE_URL=postgresql://user:pass@localhost:5432/smart_mirror
```

### Running Development Server
```bash
cd server
go run main.go auth.go middleware.go
```
API available at `http://localhost:8080`

### Building for Production
```bash
go build -o smart-mirror-api
./smart-mirror-api
```

### Available Endpoints
- `GET /health` - Health check
- `POST /auth/login` - Login
- `POST /auth/register` - Register
- `GET /api/users/me` - Current user (protected)
- `GET /api/dashboard` - Dashboard (protected)
- `POST /api/dashboard/widgets` - Add widget (protected)
- See `server/API_DOCS.md` for full documentation

---

## Auth0 Integration

### Step 1: Create Auth0 Account
1. Go to [auth0.com](https://auth0.com)
2. Sign up for a free account
3. Create a new tenant

### Step 2: Create Application
1. Navigate to Applications > Applications
2. Click "Create Application"
3. Name: "Smart Mirror"
4. Choose "Regular Web Application"
5. Select: Node.js
6. Copy your **Domain**, **Client ID**, and **Client Secret**

### Step 3: Configure Application
In Auth0 dashboard:
1. Go to Application Settings
2. Add to "Allowed Callback URLs":
   ```
   http://localhost:5173
   ```
3. Add to "Allowed Logout URLs":
   ```
   http://localhost:5173
   ```
4. Add to "Allowed Web Origins":
   ```
   http://localhost:5173
   http://localhost:8080
   ```

### Step 4: Create API
1. Navigate to APIs
2. Click "Create API"
3. Name: "Smart Mirror API"
4. Identifier: `smart-mirror-api`
5. Copy the **Identifier** to use as `AUTH0_AUDIENCE`

### Step 5: Update Environment
```env
AUTH0_DOMAIN=your-domain.auth0.com
AUTH0_CLIENT_ID=your-client-id
AUTH0_CLIENT_SECRET=your-client-secret
AUTH0_AUDIENCE=smart-mirror-api
```

### Step 6: Frontend Integration
Install Auth0 SDK:
```bash
npm install @auth0/auth0-react
```

Wrap app with Auth0Provider in `main.jsx`:
```javascript
import { Auth0Provider } from '@auth0/auth0-react'

ReactDOM.render(
  <Auth0Provider
    domain={import.meta.env.VITE_AUTH0_DOMAIN}
    clientId={import.meta.env.VITE_AUTH0_CLIENT_ID}
    authorizationParams={{
      audience: import.meta.env.VITE_AUTH0_AUDIENCE,
      redirect_uri: window.location.origin
    }}
  >
    <App />
  </Auth0Provider>,
  document.getElementById('root')
)
```

### Step 7: Backend Token Validation
Backend will validate tokens using Auth0 JWKS endpoint. See `server/middleware.go` for implementation.

---

## Development Workflow

### 1. Daily Development
```bash
# Terminal 1 - Frontend
cd web
npm run dev

# Terminal 2 - Backend
cd server
go run main.go auth.go middleware.go
```

### 2. Adding a New Widget Type
**Frontend:**
1. Update `WidgetContainer.jsx` to handle new type
2. Add styling in `widget.css`

**Backend:**
1. Handle in handlers (e.g., `addWidget`)
2. Add validation in middleware

### 3. Adding a New API Endpoint
**Backend:**
1. Create handler function in `main.go`
2. Add route in `main()` function
3. Add to `API_DOCS.md`

**Frontend:**
1. Create API service function
2. Call from component
3. Update styling if needed

### 4. Database Operations
Currently stubbed out. To implement:
1. Create database models
2. Add migration scripts
3. Implement database functions
4. Replace dummy handlers with real queries

---

## Deployment

### Docker Deployment (Recommended)
```bash
cd server
docker-compose up --build
```

### Manual Linux/Mac Deployment
1. Install Go and PostgreSQL
2. Clone repository
3. Set environment variables
4. Build backend:
   ```bash
   go build -o smart-mirror-api
   ```
5. Run with process manager (systemd, supervisord)

### Railway Deployment
1. Connect GitHub repository
2. Set environment variables in Railway
3. Deploy automatically on push

### Vercel (Frontend)
1. Connect web/ folder
2. Set environment variables
3. Deploy

### Example Production .env
```env
AUTH0_DOMAIN=prod-domain.auth0.com
AUTH0_CLIENT_ID=prod-client-id
AUTH0_CLIENT_SECRET=prod-client-secret
AUTH0_AUDIENCE=smart-mirror-api
PORT=8080
DATABASE_URL=postgresql://user:pass@prod-db:5432/smart_mirror
```

---

## Troubleshooting

### Frontend Issues

**Port 5173 already in use:**
```bash
npm run dev -- --port 3000
```

**Module not found errors:**
```bash
rm -rf node_modules
npm install
```

**Hot reload not working:**
- Check Vite config
- Restart dev server
- Clear browser cache

### Backend Issues

**Port 8080 already in use:**
```bash
lsof -i :8080  # Find process
kill -9 <PID>  # Kill process
# Or change PORT env variable
```

**Module errors:**
```bash
go mod tidy
go mod download
```

**Auth0 token validation fails:**
- Check `AUTH0_DOMAIN` is correct
- Verify token is not expired
- Check audience matches `AUTH0_AUDIENCE`

### Database Issues

**Can't connect to PostgreSQL:**
```bash
# Check if running
pg_isready

# Connection string format
postgresql://username:password@localhost:5432/database_name
```

### CORS Issues

**Frontend can't reach backend:**
- Ensure backend CORS middleware is enabled
- Check allowed origins in `main.go`
- Browser console shows the actual error

### Auth0 Issues

**Login redirect loop:**
- Check callback URLs in Auth0 settings
- Clear browser cookies and cache
- Verify redirect_uri matches exactly

**Token validation fails:**
- Verify environment variables are set
- Check token is not expired
- Validate with `jwt.io`

---

## Next Steps Checklist

- [ ] Complete Auth0 setup
- [ ] Integrate Auth0 React SDK
- [ ] Connect frontend to backend API
- [ ] Set up PostgreSQL database
- [ ] Implement database models
- [ ] Create database migrations
- [ ] Add input validation
- [ ] Add error handling
- [ ] Write tests
- [ ] Set up CI/CD
- [ ] Deploy to production
- [ ] Monitor and logs
- [ ] Add analytics

---

## Useful Commands

### Frontend
```bash
npm run dev        # Start dev server
npm run build      # Build for production
npm run preview    # Preview production build
npm run lint       # Run ESLint
```

### Backend
```bash
go run main.go auth.go middleware.go  # Run locally
go test ./...                          # Run tests
go build -o api                        # Build binary
go fmt ./...                           # Format code
```

### Docker
```bash
docker-compose up                 # Start services
docker-compose down               # Stop services
docker-compose logs -f api        # View logs
docker-compose build --no-cache   # Rebuild images
```

---

## Support & Resources

- **React Router**: https://reactrouter.com/
- **Echo Framework**: https://echo.labstack.com/
- **Auth0 Docs**: https://auth0.com/docs
- **Go Docs**: https://golang.org/doc/
- **PostgreSQL**: https://www.postgresql.org/docs/
- **Docker**: https://docs.docker.com/

---

**Project is ready for development! 🚀**
