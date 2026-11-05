 Smart Mirror
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


### Prerequisites

| Component | Requirements |
|---|---|
| **Server** | Docker & Docker Compose (or Go 1.25+, Python 3.10+, `face_recognition`, `numpy`) |
| **Web** | Node.js 20+, npm |
| **Mirror** | Python 3.10 (recommended for MediaPipe / FAISS wheels), webcam / Pi Camera, USB barcode scanner (optional) |
