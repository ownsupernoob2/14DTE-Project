import os
import tempfile

def _get_temp_path(filename):
    if os.name != 'nt' and os.path.exists('/tmp'):
        return os.path.join('/tmp', filename)
    return os.path.join(tempfile.gettempdir(), filename)

# --- SYSTEM PATHS ---
HAND_DATA_FILE = _get_temp_path('hand_data.json')
FACE_DATA_FILE = _get_temp_path('face_status.json')

def _get_shm_path(filename):
    if os.name != 'nt' and os.path.exists('/dev/shm'):
        return os.path.join('/dev/shm', filename)
    return _get_temp_path(filename)

VISION_FILE = _get_shm_path('ai_view.jpg')

# --- UI CONSTANTS ---
GRID_COLS = 12
GRID_ROWS = 12
GRID_GAP = 20

# --- COLORS ---
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)
COLOR_BG_OVERLAY = (20, 20, 20, 200)
COLOR_TEXT_DIM = (180, 180, 180)
COLOR_ACCENT = (0, 255, 255)
