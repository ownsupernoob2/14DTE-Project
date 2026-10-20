"""Settings shared by the mirror's processes (UI, face daemon, gesture daemon)."""
import os
import socket
import tempfile

# --- SERVER ---
API_URL = os.environ.get('API_URL', 'https://api.smartmirror.me').rstrip('/')

# Shared secret proving to the server that this is a real mirror; it guards the
# face index and students' dashboards. Same value as MIRROR_API_KEY in the
# server's .env. start_smart_mirror.sh loads it from ~/.config/smart-mirror/env.
MIRROR_API_KEY = os.environ.get('MIRROR_API_KEY', '')

MIRROR_ID = os.environ.get('MIRROR_ID') or socket.gethostname()
MIRROR_VERSION = "v1.3.0"


def mirror_headers():
    """Headers for requests to mirror-only API endpoints."""
    return {'X-Mirror-Key': MIRROR_API_KEY} if MIRROR_API_KEY else {}


# --- FILES ---
def _get_temp_path(filename):
    if os.name != 'nt' and os.path.exists('/tmp'):
        return os.path.join('/tmp', filename)
    return os.path.join(tempfile.gettempdir(), filename)


def _get_shm_path(filename):
    if os.name != 'nt' and os.path.exists('/dev/shm'):
        return os.path.join('/dev/shm', filename)
    return _get_temp_path(filename)


FACE_DATA_FILE = _get_temp_path('face_status.json')
VISION_FILE = _get_shm_path('ai_view.jpg')

# Data downloaded from the server and kept across restarts (face index,
# screensaver images). Outside the repo, so a git pull never touches it.
CACHE_DIR = os.environ.get('MIRROR_CACHE_DIR') or os.path.join(os.path.expanduser('~'), '.cache', 'smart-mirror')
