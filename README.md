# 🪞 Smart Mirror — 14DTE Project

A personalized smart mirror system that recognizes registered users by their face and displays their custom widget dashboard. The project is split into three components that work together: the **Web** app, the **Server**, and the **Mirror**.

---

## 📐 System Overview

```
┌──────────────────────────────────────────────────────────┐
│                        USER                              │
│                                                          │
│   1. Registers & configures widgets on the Web app       │
│   2. Submits a face scan via the Web app                 │
│   3. Walks up to the Mirror                              │
└───────────┬──────────────────────────────────────────────┘
            │
            ▼
┌───────────────────────┐        ┌─────────────────────────┐
│       WEB APP         │◄──────►│        SERVER           │
│  (React / Vite)       │  REST  │  (Go + Python scripts)  │
│  smartmirror.me       │        │  api.smartmirror.me     │
└───────────────────────┘        └────────────┬────────────┘
                                              │
                                              │ POST /api/verify-face
                                              │ GET  /api/dashboard/widgets
                                              │
                                 ┌────────────▼────────────┐
                                 │         MIRROR          │
                                 │  (Python / Pygame / Pi) │
                                 │  face_recognize.py      │
                                 │  smart_mirror_pro.py    │
                                 └─────────────────────────┘
```

---

## 1. 🌐 Web App (`/web`)

**Technology:** React (Vite), Auth0 authentication, deployed to `smartmirror.me`

The web app is the control panel where users register, configure their mirror layout, and submit their face scan.

### Main Purpose

- **Account management** — Users sign up and log in via Auth0.
- **Face registration** — Users open the face scan modal, which captures ~10 frames from their webcam and sends them to the server as base64-encoded JPEG images. The server trains a face encoding model and saves it as a `.pickle` file.
- **Widget dashboard** — Users can build and customize the layout they want to see on the mirror. The dashboard is a 1280×800 canvas where widgets are placed and resized using percentage-based coordinates (so the layout works on any screen size).

### Pages

| Page | Description |
|---|---|
| `Login.jsx` | Auth0 login/register entry point |
| `Dashboard.jsx` | Main widget layout editor — drag, resize, add, and save widgets |
| `Settings.jsx` | Profile settings, face scan management (register / delete) |
| `Simulator.jsx` | Preview of how the mirror will look for the logged-in user |

### Widget Types

Users can add any combination of these widgets to their dashboard:

| Widget | Description |
|---|---|
| **Clock** | Live date and time display |
| **Daily Notices** | School notices feed fetched from the server, with keyword and year-group filters |
| **Timetable** | Today's or the week's class schedule, parsed from an ICS/calendar URL |
| **Note** | A personal freeform text sticky note |

### Face Scan Flow (Web → Server)

1. User clicks **"Register Face Scan"** in the Dashboard or Settings.
2. The `FaceCaptureModal` opens the webcam and captures ~10 frames over a few seconds.
3. All frames are sent together as a `POST /api/faces/train` request (with a JWT bearer token).
4. The server processes them with `train.py`, creates a `.pickle` file, and returns the number of usable frames.
5. A 24-hour cooldown prevents the user from re-training too frequently (to avoid polluting the model).

---

## 2. ⚙️ Server (`/server`)

**Technology:** Go (Echo framework) + Python helper scripts, deployable via Docker

The server is the central hub. It handles authentication, stores widget layouts per user, and performs face recognition when the mirror sends a camera frame.

### Key Responsibilities

| Responsibility | Details |
|---|---|
| **Auth** | JWT-based login/register via `handlers_auth.go`; tokens validated by `middleware.go` |
| **Face Training** | Receives batched images from the web app, runs `train.py`, saves `encodings/<user_id>.pickle` |
| **Face Verification** | Receives a JPEG from the mirror, runs `verify.py` against all `.pickle` files in `encodings/`, returns the matched `user_id` and their widget layout |
| **Widget Storage** | Each user's widget layout is saved as `data/<user_id>_widgets.json`; CRUD via REST endpoints |
| **Notices** | Periodically fetches and caches school daily notices (`fetch_notices.py`) |
| **Timetable** | Parses ICS calendar URLs and returns today's/weekly schedule |
| **King's Week** | Hourly scrape of the school's weekly publication (`handlers_kingsweek.go`): the edition list comes from `kingshigh.school.nz`, and the latest edition's articles and images from the `hail.to` publication behind it. Cached to `data/kings_week.json` and served from memory |

### Python Scripts

#### `train.py` — Face Encoder
Receives a directory of JPEG frames and an output path. It:
1. Loads every image and extracts a 128-dimension face encoding using the `face_recognition` library.
2. Filters out **outlier frames** (side profiles, blinks, background faces) by removing any encoding whose distance from the median exceeds `0.40`.
3. Saves the cleaned list of encodings to a `.pickle` file.
4. Prints `OK:<N>` on success or `ERROR:<msg>` on failure.

#### `verify.py` — Face Verifier
Receives a single JPEG (the mirror's camera frame) and the `encodings/` directory. It:
1. Extracts a face encoding from the target image.
2. Compares it against **every** `<user_id>.pickle` file in the directory.
3. Finds the closest match with a distance below `0.50`.
4. Prints `MATCH:<user_id>` or `NO_FACE`.

### API Endpoints (Summary)

```
POST   /auth/login                  — Log in, receive JWT
POST   /auth/register               — Register new account
POST   /api/verify-face             — Mirror face check (no auth required)
POST   /api/verify-barcode          — Mirror student ID check (no auth, rate limited)
POST   /api/faces/train             — Submit face scan frames (JWT required)
DELETE /api/faces/me                — Delete your face encoding
GET    /api/users/me/barcode        — Get your linked student ID
PUT    /api/users/me/barcode        — Link a student ID for mirror sign-in
DELETE /api/users/me/barcode        — Unlink your student ID
GET    /api/dashboard/widgets       — Get your widget layout
PUT    /api/dashboard/widgets/bulk  — Save your full widget layout
GET    /api/notices                 — Get cached school notices
GET    /api/timetable               — Get today's/weekly timetable
GET    /api/kings-week              — Get the scraped King's Week edition + articles
```

### File Storage Layout

```
server/
├── encodings/          # One .pickle file per registered user
│   ├── auth0_abc123.pickle
│   └── auth0_xyz789.pickle
├── data/               # One JSON file per user's widget layout
│   ├── auth0_abc123_widgets.json
│   └── auth0_xyz789_widgets.json
├── faces/              # Legacy single-image face uploads
└── temp/               # Temporary frames during training (auto-deleted)
```

---

## 3. 🪞 Mirror (`/mirror`)

**Technology:** Python, Pygame, OpenCV — designed to run on a Raspberry Pi (or Windows for development)

The mirror software runs on a Raspberry Pi hidden behind a two-way mirror. It runs two processes simultaneously:

| Process | Script | Role |
|---|---|---|
| **Face Recognition Daemon** | `face_recognize.py` | Reads camera frames, detects faces, POSTs to the server, writes a state JSON file |
| **Mirror UI** | `smart_mirror_pro.py` | Reads the state JSON file and renders the user's widgets on screen |

### Face Recognition Daemon (`face_recognize.py`)

This daemon implements a **3-state machine**:

```
         No face for IDLE_TIMEOUT_SEC
  IDLE ◄────────────────────────────── USER
   │                                    ▲
   │ Face detected                      │ Server returns MATCH
   ▼                                    │
 (detecting) ──── Server returns ───► USER
                  unrecognised
                  for GUEST_GRACE_SEC
                        │
                        ▼
                      GUEST
```

| State | Meaning | What the mirror shows |
|---|---|---|
| **IDLE** | No face present | Blank / minimal screen |
| **GUEST** | Unregistered face has been visible for `GUEST_GRACE_SEC` | A welcome screen prompting the visitor to sign up at `smartmirror.me` |
| **USER** | A registered user was recognised | That user's custom widget dashboard |

**How it works:**
1. Reads camera frames via OpenCV (supports Raspberry Pi `v4l2loopback` or a standard webcam).
2. Every 3rd frame, runs a lightweight **Haar Cascade** face detector to check if a face is present.
3. On a configurable interval, POSTs the current frame as a base64 JPEG to `POST /api/verify-face`.
4. The server runs `verify.py` and responds with either:
   - `200` + `{ user_id, widgets }` — recognised user
   - `401 "no face detected"` — no face in frame
   - `401 "face not recognised"` — face present but not in database
5. State + widget data is written **atomically** to a JSON file (`face_status.json`) so the UI process can read it safely.

### Mirror UI (`smart_mirror_pro.py`)

A Pygame application that runs fullscreen (or windowed for development). It:
1. Reads `face_status.json` every frame to detect state changes.
2. When a **USER** is recognised, loads their widgets from the JSON (which were returned by the server) and renders them on screen with a smooth **fade-in + slide-up animation**.
3. When a **GUEST** is detected, fades in a welcome screen with the daily notices on the left and a sign-up prompt on the right showing `smartmirror.me`.
4. When **IDLE**, clears the screen.
5. Shows a subtle **status dot** in the top-right corner:
   - 🟢 Green — user recognised
   - 🟠 Orange — face present, grace period (checking...)
   - Hidden — idle

### Widget Rendering

Each widget type is a separate Python class in `mirror/widgets/`:

| Widget | Class | Description |
|---|---|---|
| Clock | `ClockWidget` | Renders live time and date |
| Weather | `WeatherWidget` | Renders current weather conditions |
| Daily Notices | `NoticesWidget` | Fetches notices from the server API and auto-scrolls |
| Timetable | `TimetableWidget` | Fetches and displays the user's class schedule |
| Note | `NoteWidget` | Displays a saved personal text note |

Widget positions and sizes are stored as **percentages** (0–100%) so the layout scales correctly from the web app's preview to the mirror's physical display.

---

## 🚀 Getting Started

### Prerequisites
- **Server:** Go 1.21+, Python 3.10+, `pip install face_recognition numpy`
- **Web:** Node.js 18+
- **Mirror:** Python 3.10+, `pip install -r requirements.txt`, Pygame, OpenCV

### Quick Start

```bash
# 1. Start the server
cd server
go run .

# 2. Start the web app
cd web
npm install
npm run dev

# 3. Start the mirror (development / Windows)
cd mirror
python face_recognize.py --camera-id 0
python smart_mirror_pro.py

# 3. Start the mirror (Raspberry Pi)
cd mirror
bash start_smart_mirror.sh
```

### Environment Variables

**Server** (`.env`):
```
PORT=8080
JWT_SECRET=your_secret
```

**Web** (`.env`):
```
VITE_API_URL=https://api.smartmirror.me
VITE_AUTH0_DOMAIN=your_auth0_domain
VITE_AUTH0_CLIENT_ID=your_client_id
```

**Mirror** (environment):
```
API_URL=https://api.smartmirror.me
MIRROR_WINDOWED=1   # set to 1 for windowed dev mode
```

---

## 📁 Project Structure

```
14DTE-Project/
├── web/                    # React web app (user dashboard & face registration)
│   └── src/
│       ├── pages/          # Dashboard, Settings, Login, Simulator
│       ├── components/     # Navbar, WidgetContainer, FaceCaptureModal, ...
│       └── contexts/       # Auth, server status contexts
│
├── server/                 # Go REST API + Python face scripts
│   ├── main.go             # Server entry point, route registration
│   ├── handlers_face.go    # Face train & verify endpoints
│   ├── handlers_dashboard.go # Widget CRUD endpoints
│   ├── handlers_auth.go    # Login / register
│   ├── train.py            # Face encoding trainer (Python)
│   ├── verify.py           # Face verifier (Python)
│   ├── notices.go          # School notices handler
│   ├── timetable.go        # ICS timetable parser
│   ├── handlers_kingsweek.go # King's Week scraper (school site + hail.to)
│   ├── encodings/          # Per-user face encoding pickles
│   └── data/               # Per-user widget layout JSON files
│
└── mirror/                 # Raspberry Pi smart mirror software
    ├── face_recognize.py   # Camera loop + face recognition daemon
    ├── smart_mirror_pro.py # Pygame UI renderer
    ├── config.py           # Shared config (file paths, API URL)
    ├── timing_config.py    # Tunable timing constants
    └── widgets/            # Widget classes (clock, weather, notices, etc.)
```
