# 🪞 Smart Mirror — 14DTE Project

An intelligent, personalized smart mirror ecosystem engineered for King's High School. The system recognizes enrolled students seamlessly using biometric face recognition or physical student ID barcode scanning, displaying an individualized, high-contrast dashboard with live class timetables, daily notices, school newsletters, and personal widgets. The mirror supports touch-free navigation via computer vision hand gestures.

The project is structured into three interconnected components: the **Web App**, the **Backend Server**, and the **Mirror Client**.

---

## 📐 System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                   STUDENT                                   │
│                                                                             │
│   1. Enrolls & personalizes widgets on the Web App (smartmirror.me)         │
│   2. Registers face scan (multi-frame) and/or links Student ID barcode      │
│   3. Approaches the physical Mirror                                         │
│   4. Navigates hands-free using MediaPipe air gestures                      │
└───────────────────────┬───────────────────────────────────┬─────────────────┘
                        │                                   │
                        ▼                                   ▼
          ┌───────────────────────────┐       ┌───────────────────────────┐
          │          WEB APP          │       │       MIRROR CLIENT       │
          │  React 19 / Vite / Auth0  │       │ PyQt6 / MediaPipe / FAISS │
          │      smartmirror.me       │       │    Raspberry Pi / Win     │
          └─────────────┬─────────────┘       └─────────────▲─────────────┘
                        │ REST                              │
                        │ (JWT Auth)                        │ REST & Local Cache
                        │                                   │ - POST /api/verify-face
                        │                                   │ - POST /api/verify-barcode
                        │                                   │ - GET  /api/download-index
                        ▼                                   │ - GET  /api/notices
          ┌─────────────────────────────────────────────────┴─────────────┐
          │                         BACKEND SERVER                        │
          │             Go 1.25+ (Echo v4) + Python Workers               │
          │             Docker Container + Watchtower Auto-CD             │
          │                    api.smartmirror.me                         │
          └───────────────────────────────────────────────────────────────┘
```

---

## 🎨 Design Philosophy & Style System

Both the Web Application and the Mirror PyQt6 interface adhere to a synchronized, high-contrast pure-black minimal design system tailored for two-way mirror glass and OLED reflection minimization:

- **Canvas Background**: `#000000` (Pure Black — transparent behind two-way mirror glass)
- **Panel & Card Fill**: `#0a0a0a` (Subtle Dark Gray)
- **Borders & Dividers**: `#1c1c1c` (Thin, crisp structural lines)
- **Primary Text**: `#ffffff` (Pure White display headings and titles)
- **Secondary Text**: `#d0d0d0` (Soft Gray body copy)
- **Muted & Metadata**: `#8f8f8f` (Muted Gray timestamps and tags)
- **Active / Accent Highlight**: `#4fc3ff` (Cyan accent for current class, active chips, and focuses)
- **Urgent Alert**: `#ff4d4d` (Vibrant Red for high-priority campus notices and banners)
- **Medium Alert**: `#ffb020` (Amber for academic and club notices)
- **Typography**: Hanken Grotesk / Segoe UI for interface elements; Consolas / SFMono for clocks, countdowns, and room numbers.

---

## 1. 🌐 Web Application (`/web`)

**Technology:** React 19, Vite, Auth0 SPA SDK, ZXing Barcode Scanner, Framer Motion  
**Deployment:** Automated via GitHub Actions to GitHub Pages (`smartmirror.me`)

The Web App serves as the student self-service portal where users configure their dashboard widgets, manage authentication credentials, link their student ID cards, and test their layout inside a mirror simulator.

### Key Pages

| Page | Path | Description |
|---|---|---|
| [Login](file:///e:/Code/offical/14DTE-Project/web/src/pages/Login.jsx) | `/login` | Auth0 single sign-on authentication gateway. |
| [Dashboard](file:///e:/Code/offical/14DTE-Project/web/src/pages/Dashboard.jsx) | `/` | 1280×800 canvas editor to add, configure, and position widgets with responsive percentage-based scaling. |
| [Settings](file:///e:/Code/offical/14DTE-Project/web/src/pages/Settings.jsx) | `/settings` | Profile management, face enrollment modal, student ID card linking, and timetable calendar (ICS) synchronization. |
| [Simulator](file:///e:/Code/offical/14DTE-Project/web/src/pages/Simulator.jsx) | `/simulator` | Real-time mirror preview allowing students to test both Guest (unrecognized) and User (signed-in) screen modes. |
| [Privacy](file:///e:/Code/offical/14DTE-Project/web/src/pages/Privacy.jsx) | `/privacy` | Student privacy policy disclosing biometric facial vector handling, student ID protection, and data retention policies. |

### Widget Ecosystem

| Widget | Component | Description |
|---|---|---|
| **Timetable Hero** | [TimetableWidget.jsx](file:///e:/Code/offical/14DTE-Project/web/src/components/TimetableWidget.jsx) | Hero current class view with cyan `CURRENT CLASS` eyebrow, bold subject title, room number, live countdown timer, and upcoming `NEXT` period block. Configured via iCalendar (ICS) URL. |
| **Daily Notices** | [DailyNoticesWidget.jsx](file:///e:/Code/offical/14DTE-Project/web/src/components/DailyNoticesWidget.jsx) | Live school notice feed categorized into filter chips (`All`, `Academic`, `Sports`, `Arts`) with color-coded urgency borders (`#ff4d4d` urgent, `#ffb020` medium, `#3a3a3a` general). |
| **King's Week** | [KingsWeekWidget.jsx](file:///e:/Code/offical/14DTE-Project/web/src/components/KingsWeekWidget.jsx) | Live weekly school publication preview displaying the latest edition cover, headline article, and thumbnail gallery scraped from Hail.to. |
| **Digital Clock** | Internal Header | Formatted date string (`Wed, 22 Jul`) paired with high-precision digital monospace time. |
| **Note** | [WidgetContainer.jsx](file:///e:/Code/offical/14DTE-Project/web/src/components/WidgetContainer.jsx) | Freeform customizable text note or reminder card. |
| **Emergency Banner** | [Dashboard.jsx](file:///e:/Code/offical/14DTE-Project/web/src/pages/Dashboard.jsx) | Real-time campus alert banner broadcast from the server. |

### Enrollment Workflows

1. **Face Registration Modal ([FaceCaptureModal.jsx](file:///e:/Code/offical/14DTE-Project/web/src/components/FaceCaptureModal.jsx))**:
   - Opens the student's webcam and captures ~10 frames across varying natural angles.
   - Dispatches a batched `POST /api/faces/train` request with JWT authentication.
   - The server extracts 128-dimensional encodings, removes statistical outlier frames (distance > 0.40 from median), and persists the `.pickle` file.
   - A 24-hour retrain cooldown prevents accidental model thrashing.
2. **Student ID Barcode Modal ([BarcodeCaptureModal.jsx](file:///e:/Code/offical/14DTE-Project/web/src/components/BarcodeCaptureModal.jsx))**:
   - Allows students to scan their physical school ID card using their camera (powered by `@zxing/library`) or manually enter their alphanumeric ID.
   - Dispatches `PUT /api/users/me/barcode` with strict format validation (`^[A-Z0-9][A-Z0-9-]*$`) and duplicate-ownership collision checks.

---

## 2. ⚙️ Backend Server (`/server`)

**Technology:** Go 1.25+ (Echo v4 Framework), Python 3.10 helper scripts, Docker, GHCR, Watchtower  
**API Gateway:** `https://api.smartmirror.me` (Port 8080)

The server acts as the central coordination hub. It handles JWT authentication, widget layout persistence, face encoding generation and distribution, student ID verification, and continuous web scraping of school feeds.

### Core Handlers & Services

- **Database ([db.go](server/db.go))**: one SQLite file, `data/smartmirror.db` (pure-Go driver, no C compiler needed). Users, face encodings, student IDs, sessions, settings, screensaver images and an admin audit log. Creating it for the first time wipes the old file-based data.
- **Auth & access ([auth.go](server/auth.go))**: Auth0 RS256 tokens on every signed-in route. Admins are verified Auth0 emails listed in `ADMIN_EMAILS` (looked up via Auth0 `/userinfo`, never trusted from the browser). Mirrors prove themselves with the shared `MIRROR_API_KEY` (`X-Mirror-Key` header).
- **Face scans ([handlers_face.go](server/handlers_face.go), [python.go](server/python.go), [train.py](server/train.py))**: `POST /api/faces/train` runs train.py (in `server/.venv`, created by `setup-face-python.ps1`) to turn photos into 128-number encodings; photos are deleted straight away, duplicate faces across accounts are blocked. `GET /api/download-index` (mirror) hands the encodings to the mirror's local matcher.
- **Student IDs ([handlers_barcode.go](server/handlers_barcode.go))**: one ID per account; `POST /api/verify-barcode` (mirror, rate limited) signs a student in by card scan.
- **Admin ([admin.go](server/admin.go))**: users table with search, removing a face scan / student ID / timetable link / whole account. The student is told next time they sign in ([users.go](server/users.go)).
- **Screensaver ([screensaver.go](server/screensaver.go))**: gesture demo, image slideshow or logo, chosen in the admin dashboard; mirrors cache the images.
- **Analytics ([handlers_analytics.go](server/handlers_analytics.go))**: one record per mirror visit, A/B variant control and the summary behind the admin dashboard.
- **School content ([notices.go](server/notices.go), [handlers_kingsweek.go](server/handlers_kingsweek.go), [timetable.go](server/timetable.go))**: daily notices PDF, King's Week articles and each student's ICS timetable.

See [server/API_DOCS.md](server/API_DOCS.md) for every route and who may call it.

### Data Storage

```
server/data/
├── smartmirror.db        # users, faces, sessions, settings (SQLite)
├── screensaver/          # uploaded screensaver images, named by SHA-256
├── daily_notices.json    # cached school notices (public)
└── kings_week.json       # cached King's Week articles (public)
```

---

## 3. 🪞 Mirror Client (`/mirror`)

**Technology:** Python 3.10+, **PyQt6**, OpenCV, MediaPipe Tasks (`gesture_recognizer.task`), FAISS-CPU  
**Platform:** Raspberry Pi (Production with dual cameras / v4l2loopback) or Windows (Development Simulator)

The Mirror client is a high-performance Python application built on **PyQt6**. It runs on the hardware behind the two-way glass, combining camera vision, local vector search, touchless hand gesture tracking, and physical barcode scanner input.

### Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                        PHYSICAL MIRROR CLIENT                          │
│                                                                        │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │               PyQt6 User Interface Process                     │   │
│   │                 (smart_mirror_pro.py)                          │   │
│   │                                                                │   │
│   │  • Pure black 2-column layout (34% Notices / 66% Timetable)    │   │
│   │  • Direct USB HID Barcode Scanner keyboard event capture       │   │
│   │  • Two-stage schedule peek & King's Week article reader        │   │
│   │  • Smooth QPropertyAnimation fades and slide transitions       │   │
│   └──────────────▲──────────────────────────────────▲──────────────┘   │
│                  │ IPC: face_status.json            │ IPC: gestures    │
│   ┌──────────────┴──────────────┐    ┌──────────────┴──────────────┐   │
│   │    Face Recognition Daemon  │    │     MediaPipe Gesture Daemon│   │
│   │     (face_recognize.py)     │    │      (gesture_engine.py)    │   │
│   │                             │    │                             │   │
│   │ • Multi-detector cascade    │    │ • MediaPipe Tasks API       │   │
│   │   (dlib HOG + Haar)         │    │ • Region-based tracking     │   │
│   │ • Local FAISS vector search │    │ • Hand-normalized pinch     │   │
│   │ • 3-state machine logic     │    │ • Auto-exit with parent     │   │
│   └─────────────────────────────┘    └─────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

### The 3-State Machine & Anti-Flashing Logic

The face daemon implements a stabilized state machine configured in [timing_config.py](file:///e:/Code/offical/14DTE-Project/mirror/timing_config.py):

```
                       No face for IDLE_TIMEOUT_SEC (30s)
         IDLE ◄──────────────────────────────────────────────── USER
          │                                                       ▲
          │ Face detected                                         │ Server/FAISS
          ▼                                                       │ match
        CHECK ──────────────────── Match confirmed ───────────────┤
          │                                                       │
          │ Unrecognised                                          │
          │ for GUEST_GRACE_SEC (1.5s)                            │
          ▼                                                       │
        GUEST ──────────────────── Recognized later ──────────────┘
```

- **IDLE Mode**: When nobody is standing at the mirror, the screen is dark with an unobtrusive digital clock.
- **GUEST Mode**: If an unknown visitor stands in front of the mirror for `GUEST_GRACE_SEC` (1.5s), the mirror displays general school notices, a digital clock, and a sign-up call to action pointing to `smartmirror.me`.
- **USER Mode**: When an enrolled student is identified, their custom widget dashboard immediately fades in.
- **Anti-Flashing Protection (`USER_HOLD_SEC = 25.0s`)**: In physical mirror conditions, students turn their heads, blink, or look down at bags. Instead of immediately demoting the student to the guest screen upon a single dropped frame (which causes distracting visual flashing), the system maintains the active dashboard for up to 25 seconds of failed recognition before concluding the student has left.
- **Barcode Session (`BARCODE_SESSION_SEC = 45.0s`)**: Scanning a physical card is a deliberate sign-in action; the dashboard is held for 45 seconds regardless of facial pose.

### Face Locator Cascade (dlib HOG + Haar Fallback)

In physical testing, users standing at a mirror naturally tilt their heads back with their chins raised. Standard dlib HOG detectors can fail on this angle. [face_recognize.py](file:///e:/Code/offical/14DTE-Project/mirror/face_recognize.py) implements a multi-tiered detector cascade:
1. Standard dlib HOG face detector.
2. Upsampled HOG detector (for distant faces).
3. OpenCV Haar Cascade fallback (robust against tilted poses).

### MediaPipe Hand Gesture Engine ([gesture_engine.py](file:///e:/Code/offical/14DTE-Project/mirror/gesture_engine.py))

Touchless interaction avoids smudging the glass mirror:
- **MediaPipe Tasks API**: Built using the modern MediaPipe Tasks framework and `gesture_recognizer.task` (compatible with modern Python wheels).
- **Region-Based Interaction**: The screen is split into left and right interaction zones rather than attempting jittery mouse cursor emulation. Hovering an open palm over the left column scrolls daily notices smoothly.
- **Hand-Normalized Pinch Detection**: Click detection measures the thumb-to-index finger gap divided by the wrist-to-knuckle span. This ensures consistent pinch gestures whether the student's hand is close to the lens or at full arm's length. Dual hysteresis thresholds prevent contact chatter.
- **Process Lifecycle**: Launched automatically as a subprocess by `smart_mirror_pro.py` with `--exit-with-parent` to prevent orphaned background processes. Supports orientation inversion via `GESTURE_FLIP=1`.

### Two-Stage Right-Side Peek Interaction

The right side of the mirror reveals contextual information in two intuitive stages:
1. **Dwell Right (Stage 1)**: Dwelling a hand in the right region slides in the full-day Timetable panel across the top 56% of the screen, with King's Week visible underneath.
2. **Scroll Down (Stage 2)**: Scrolling down (or idling for 10 seconds) slides the timetable away and expands King's Week to fill the column. Moving your palm magnetically locks the nearest article card; pinching your thumb and index finger opens the article in a full-screen reading modal.

---

## 🚀 Setup & Installation Guide

### Prerequisites

| Component | Requirements |
|---|---|
| **Server** | Docker & Docker Compose (or Go 1.25+, Python 3.10+, `face_recognition`, `numpy`) |
| **Web** | Node.js 20+, npm |
| **Mirror** | Python 3.10 (recommended for MediaPipe / FAISS wheels), webcam / Pi Camera, USB barcode scanner (optional) |

---

### Option A: Server Deployment (Docker & Watchtower)

The server is fully containerized with automated CI/CD. When new code is merged to `main`, GitHub Actions pushes an updated image to GHCR, and Watchtower auto-restarts the container with zero data loss.

1. **Download configuration files**:
   ```bash
   mkdir -p ~/smart-mirror && cd ~/smart-mirror
   curl -fsSL https://raw.githubusercontent.com/ownsupernoob2/14DTE-Project/main/server/docker-compose.yml -o docker-compose.yml
   curl -fsSL https://raw.githubusercontent.com/ownsupernoob2/14DTE-Project/main/server/.env.example -o .env
   ```
2. **Configure environment variables** in `.env`:
   ```ini
   AUTH0_DOMAIN=dev-pgz1qjberxzo8hkl.us.auth0.com
   AUTH0_AUDIENCE=https://dev-pgz1qjberxzo8hkl.us.auth0.com/api/v2/
   PORT=8080
   ```
3. **Launch container**:
   ```bash
   docker compose up -d
   ```
   *For detailed reverse proxy setup with Caddy or Cloudflare Tunnels, see [setup.md](file:///e:/Code/offical/14DTE-Project/setup.md).*

---

### Option B: Local Web App Development

```bash
cd web
npm install
npm run dev
```
The web dashboard will be available at `http://localhost:5173`.

---

### Option C: Mirror Client Setup

#### 1. Windows Development / Simulator Mode
The mirror client includes a headless state simulator allowing you to develop without a camera or physical mirror:

```cmd
cd mirror
setup_venv.bat
```
*This script creates `.venv/`, installs all dependencies, and downloads the `gesture_recognizer.task` model.*

To run the simulator:
1. **Terminal 1 (Mock Face State)**:
   ```cmd
   .venv\Scripts\python.exe mock_face.py
   ```
   *Press `1` for Idle, `2` for Guest, `3` for Logged-In User.*
2. **Terminal 2 (PyQt6 Mirror UI)**:
   ```cmd
   set MIRROR_WINDOWED=1
   .venv\Scripts\python.exe smart_mirror_pro.py
   ```

#### 2. Raspberry Pi Production Mode
On the physical Raspberry Pi running behind the mirror glass:
```bash
cd mirror
chmod +x setup.sh start_smart_mirror.sh
./setup.sh
./start_smart_mirror.sh
```
*This configures `v4l2loopback` virtual cameras, downloads MediaPipe models, and launches both the face daemon and the PyQt6 client.*

---

## 🔧 Environment Variables Reference

### Backend Server (`server/.env`)
| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8080` | Port on which Echo HTTP server listens. |
| `AUTH0_DOMAIN` | `dev-pgz1qjberxzo8hkl.us.auth0.com` | Auth0 tenant domain for JWT token verification. |
| `AUTH0_AUDIENCE` | `https://dev-pgz1qjberxzo8hkl...` | Expected audience claim in bearer JWTs. |
| `ADMIN_TOKEN` | *(optional)* | Secret key required in `X-Admin-Token` to post emergency banners. |

### Web Application (`web/.env`)
| Variable | Purpose |
|---|---|
| `VITE_API_URL` | Base URL of backend server (e.g., `https://api.smartmirror.me` or `http://localhost:8080`). |
| `VITE_AUTH0_DOMAIN` | Auth0 tenant domain. |
| `VITE_AUTH0_CLIENT_ID` | Auth0 client application ID. |

### Mirror Client (Runtime Environment)
| Variable | Default | Purpose |
|---|---|---|
| `API_URL` | `https://api.smartmirror.me` | Target backend API server. |
| `MIRROR_WINDOWED` | `0` | Set to `1` to run in a floating window (dev mode) rather than fullscreen. |
| `MIRROR_GESTURES` | `1` | Set to `0` to disable starting the gesture recognition engine. |
| `GESTURE_CAMERA` | `0` | Camera device index used for gesture tracking. |
| `GESTURE_FLIP` | `0` (Win) / `1` (Pi) | Inverts horizontal gesture coordinates to match user orientation. |

---

## 🧪 Automated Testing Suite

The repository contains extensive offline, headless unit test suites verifying all critical algorithms without requiring hardware:

### Mirror Python Test Suite
Run the 137 unit tests covering gestures, state transitions, barcode keyboard decoders, King's Week grid snapping, and face locator logic:
```bash
python -m unittest discover mirror/tests
```

### Server Go Test Suite
Run the backend tests covering barcode normalisation, daily notices HTML parsing, and Hail.to publication scraping:
```bash
cd server
go test -v .
```

### Web App Build Verification
Ensure all React JSX components, styles, and dependencies compile cleanly:
```bash
cd web
npm run build
```

---

## 📁 Repository Structure

```
14DTE-Project/
├── .github/
│   └── workflows/
│       ├── deploy-backend.yml      # CI/CD: Builds and pushes server Docker image to GHCR
│       └── deploy-frontend.yml     # CI/CD: Builds and deploys React web app to GitHub Pages
│
├── web/                            # React 19 / Vite Web Application
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx       # Widget drag/resize configuration canvas
│   │   │   ├── Settings.jsx        # Face enrollment & barcode linking
│   │   │   ├── Simulator.jsx       # In-browser mirror preview
│   │   │   ├── Login.jsx           # Auth0 login entry point
│   │   │   └── Privacy.jsx         # Biometric privacy & data terms
│   │   ├── components/
│   │   │   ├── FaceCaptureModal.jsx    # Webcam frame capture & upload
│   │   │   ├── BarcodeCaptureModal.jsx # Camera barcode scanner (ZXing)
│   │   │   ├── DailyNoticesWidget.jsx  # Category-filtered notice cards
│   │   │   ├── TimetableWidget.jsx     # Hero current/next class layout
│   │   │   ├── KingsWeekWidget.jsx     # School newsletter preview
│   │   │   └── Navbar.jsx              # Application navigation bar
│   │   ├── contexts/               # Auth & Server status providers
│   │   └── index.css               # Pure black minimal style definitions
│   └── package.json
│
├── server/                         # Go 1.25+ Echo REST API + Python Workers
│   ├── main.go                     # Routes, grouped by who may call them
│   ├── db.go                       # SQLite schema, settings, first-run wipe
│   ├── auth.go                     # Auth0 tokens, admins, mirror key
│   ├── users.go                    # /users/me, removal messages, self-service wipe
│   ├── admin.go                    # Users table, data removal, audit log
│   ├── handlers_face.go            # Face scans and the mirror's face index
│   ├── python.go                   # Finds a Python able to run train.py
│   ├── handlers_barcode.go         # Student ID linking & mirror sign-in
│   ├── handlers_dashboard.go       # Per-user widget layout
│   ├── handlers_analytics.go       # Mirror visit analytics & A/B config
│   ├── screensaver.go              # Demo / slideshow / logo screensaver
│   ├── handlers_kingsweek.go       # King's Week scraper (school + Hail.to)
│   ├── handlers_banner.go          # Campus banner broadcast
│   ├── notices.go                  # Daily notices parsing & caching
│   ├── timetable.go                # iCalendar (ICS) schedule parser
│   ├── train.py                    # 128-d face encoding & outlier filter
│   ├── setup-face-python.ps1       # Creates server/.venv for train.py (Windows)
│   ├── run-and-update.ps1          # Windows supervisor & auto-updater
│   ├── Dockerfile                  # Multi-stage production container
│   └── docker-compose.yml          # Container configuration with Watchtower
│
├── mirror/                         # PyQt6 Smart Mirror Hardware Client
│   ├── smart_mirror_pro.py         # Main PyQt6 fullscreen UI & barcode handler
│   ├── face_recognize.py           # Face detection daemon & 3-state machine
│   ├── gesture_engine.py           # MediaPipe touchless air gesture daemon
│   ├── screensaver.py              # Screensaver sync & slideshow
│   ├── debug_overlay.py            # Triple-click diagnostics panel
│   ├── telemetry.py                # Visit analytics & A/B variant
│   ├── mock_face.py                # Terminal-based state simulator (Idle/Guest/User)
│   ├── timing_config.py            # State machine timeouts & hold constants
│   ├── config.py                   # Server URL, mirror key, shared paths
│   ├── barcode_reader.py           # Camera barcode reader fallback
│   ├── setup_venv.bat              # Automated Windows environment installer
│   ├── setup.sh                    # Automated Raspberry Pi installer
│   ├── start_smart_mirror.sh       # Raspberry Pi production launch script
│   ├── widgets/
│   │   ├── clock_widget.py         # Digital time & date display
│   │   ├── notices_widget.py       # Scrolling notice column with category chips
│   │   ├── timetable_widget.py     # Hero current class & next block view
│   │   └── kings_week_widget.py    # Gesture-navigable school newsletter grid
│   └── tests/                      # Unit tests for UI, gestures & detectors
│
├── docs/                           # Project documents (A/B plans, testing notes)
├── setup.md                        # Production Docker & reverse-proxy guide
├── setup.bat                       # Root quick-start script for Windows
├── setup.sh                        # Root quick-start script for Linux/macOS
└── README.md                       # Master project documentation
```
