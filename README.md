# Smart Mirror Pro - Monorepo

A comprehensive smart mirror application combining voice assistance, gesture recognition, calendar integration, and weather information.

## 📁 Repository Structure

```
smart-mirror-pro/
├── web/                 # React web frontend
│   ├── src/
│   ├── public/
│   └── package.json
├── server/              # Go backend API
│   ├── main.go
│   ├── handlers/
│   ├── models/
│   └── go.mod
├── mirror/              # Python mirror application (core)
│   ├── ai_service.py
│   ├── face_capture.py
│   ├── face_recognize.py
│   ├── gesture_recognizer.py
│   ├── google_calendar.py
│   ├── voice_assistant_widget.py
│   ├── widgets/
│   ├── ui/
│   ├── utils/
│   ├── dataset/
│   └── requirements.txt
├── docs/                # Documentation
│   ├── API.md
│   ├── ARCHITECTURE.md
│   ├── SETUP.md
│   └── DEPLOYMENT.md
├── .gitignore
└── README.md
```

## 🏗️ Architecture Overview

### Frontend Layer (`/web`)
- **Technology**: React.js
- **Purpose**: Web-based control panel and dashboard
- **Features**: 
  - Real-time mirror status monitoring
  - Configuration interface
  - Settings management
  - Voice command history
  - Calendar integration view

### Backend Layer (`/server`)
- **Technology**: Go
- **Purpose**: RESTful API server
- **Features**:
  - User authentication
  - Data persistence
  - Integration with Python services
  - Real-time WebSocket support
  - Calendar and weather API integration

### Mirror Application (`/mirror`)
- **Technology**: Python
- **Purpose**: Core smart mirror application running on the device
- **Key Components**:
  - **Face Recognition**: OpenCV-based facial recognition and training
  - **Gesture Recognition**: Real-time gesture detection
  - **Voice Assistant**: Google Generative AI integration with speech recognition
  - **Calendar Integration**: Google Calendar syncing and display
  - **Widget System**: Modular UI components (Clock, Weather, Calendar)
  - **AI Service**: Gemini voice assistant integration

### Documentation (`/docs`)
- API documentation
- Architecture diagrams
- Setup guides
- Deployment instructions

## 🚀 Quick Start

### Prerequisites
- Node.js 16+ (for web)
- Go 1.21+ (for server)
- Python 3.9+ (for mirror)
- Git

### Web Setup
```bash
cd web
npm install
npm run dev
```

### Server Setup
```bash
cd server
go mod download
go run main.go
```

### Mirror Setup
```bash
cd mirror
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python smart_mirror_pro.py
```

## 🛠️ Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Frontend | React | 18.2.0 |
| Backend API | Go | 1.21 |
| Mirror Core | Python | 3.9+ |
| Face Recognition | OpenCV | 4.8.0 |
| Voice Assistant | Google Generative AI | Latest |
| Calendar | Google Calendar API | v3 |

## 📦 Key Dependencies

### Web (`/web`)
- react: 18.2.0
- react-dom: 18.2.0
- react-scripts: 5.0.1

### Server (`/server`)
- Standard Go libraries
- Third-party packages for API routing and database

### Mirror (`/mirror`)
- opencv-python: 4.8.0.74
- google-auth-oauthlib: 1.1.0
- google-generativeai: 0.3.0
- PyQt5: 5.15.9
- SpeechRecognition: 3.10.0

## 🔧 Development Workflow

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/smart-mirror-pro.git
   cd smart-mirror-pro
   ```

2. **Create feature branches**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Work on your component**
   - Frontend changes in `/web`
   - Backend changes in `/server`
   - Mirror updates in `/mirror`

4. **Commit and push**
   ```bash
   git add .
   git commit -m "feat: add your feature"
   git push origin feature/your-feature-name
   ```

5. **Create a Pull Request** on GitHub

## 📝 Commit Convention

- `feat:` New feature
- `fix:` Bug fixes
- `docs:` Documentation updates
- `style:` Code style changes
- `refactor:` Code refactoring
- `test:` Test-related changes
- `chore:` Build and dependency updates

Example: `git commit -m "feat: add gesture recognition widget"`

## 🔐 Environment Variables

Create `.env.local` files in each component:

### `/web/.env.local`
```
REACT_APP_API_URL=http://localhost:8080
REACT_APP_WS_URL=ws://localhost:8080
```

### `/server/.env.local`
```
PORT=8080
DATABASE_URL=your_database_url
MIRROR_HOST=192.168.1.x
```

### `/mirror/.env.local`
```
GOOGLE_API_KEY=your_google_api_key
GOOGLE_CALENDAR_ID=your_calendar_id
```

## 📚 Documentation

For more detailed information:
- [API Documentation](docs/API.md)
- [Architecture Details](docs/ARCHITECTURE.md)
- [Setup Guide](docs/SETUP.md)
- [Deployment Guide](docs/DEPLOYMENT.md)

## 🤝 Contributing

1. Create a new branch for your feature
2. Make your changes
3. Ensure code quality and tests pass
4. Submit a pull request with a clear description

## 📄 License

[Specify your license here]

## 👥 Team

- **Frontend Lead**: [Name]
- **Backend Lead**: [Name]
- **Mirror/AI Lead**: [Name]

## 📞 Support

For issues, feature requests, or questions:
- Open an issue on GitHub
- Contact the team leads
- Check existing documentation in `/docs`

---

**Last Updated**: April 2026
