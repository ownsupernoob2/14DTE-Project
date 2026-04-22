# --- SYSTEM PATHS ---
HAND_DATA_FILE = '/tmp/hand_data.json'
FACE_DATA_FILE = '/tmp/face_status.json'
AI_STATUS_FILE = '/tmp/ai_status.json'
AI_CONTROL_FILE = '/tmp/ai_control.json'
USER_PROFILES_FILE = '/tmp/user_profiles.json'
RENAME_REQUEST_FILE = '/tmp/rename_user.json'

# --- UI CONSTANTS ---
GRID_COLS = 12
GRID_ROWS = 12
GRID_GAP = 20

# --- THEMES & COLORS ---
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)
COLOR_BG_OVERLAY = (20, 20, 20, 200)
COLOR_HIGHLIGHT = (255, 255, 255, 30)
COLOR_TEXT_DIM = (180, 180, 180)

# Default Accent (Can be changed by profiles)
COLOR_ACCENT = (0, 255, 255) 

# --- USER PROFILES ---
# Define different layouts for different states
PROFILES = {
    "idle": {
        "widgets": ["clock"],
        "theme": (100, 100, 100), # Dim Grey
        "bg_alpha": 0 # Transparent/Black
    },
    "default_user": {
        "widgets": ["clock", "weather", "calendar", "news", "music"],
        "theme": (0, 255, 255), # Cyan
        "bg_alpha": 100
    },
    "developer_mode": {
        "widgets": ["clock", "system", "crypto", "notes"],
        "theme": (0, 255, 0), # Hacker Green
        "bg_alpha": 150
    },
    "morning_mode": {
        "widgets": ["clock", "weather", "calendar", "news"],
        "theme": (255, 200, 0), # Gold
        "bg_alpha": 120
    }
}
