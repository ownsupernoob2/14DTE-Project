# --- TIMING CONFIGURATION FOR SMART MIRROR ---

# Time (in seconds) to keep the user's dashboard active after they walk away (no face detected)
IDLE_TIMEOUT_SEC = 30.0

# Time (in seconds) an unrecognized face must be visible before switching to the GUEST visitor screen
GUEST_GRACE_SEC = 1.5

# Time (in seconds) a *recognised* student keeps their dashboard while recognition
# keeps failing. This is deliberately much longer than GUEST_GRACE_SEC, which
# governs a stranger walking up to an idle mirror. Once somebody is signed in,
# a failed match is nearly always a bad frame — they turned their head, blinked,
# moved — and demoting them to the guest screen after a second meant the mirror
# flipped USER → GUEST → USER continuously, running a full fade each way. It read
# as flashing. Only a sustained run of failures should give up on them.
USER_HOLD_SEC = 25.0

# How often (in seconds) to poll the face recognition API when in IDLE state or during the grace period
API_POLL_INTERVAL = 1.5

# How often (in seconds) to poll the face recognition API when in GUEST (visitor) state
API_POLL_GUEST = 3.0

# How often (in seconds) to poll the face recognition API when in USER (recognized) state
API_POLL_RECOGNISED = 5.0

# How often (in seconds) to send a heartbeat request to the server when no face is detected
HEARTBEAT_INTERVAL = 3.0

# --- BARCODE / STUDENT ID SIGN-IN ---

# How long (in seconds) a barcode sign-in keeps the dashboard up. Scanning a card
# is a deliberate action, so it holds even when the student's face is not
# detected (they may be looking at their card, not the mirror).
BARCODE_SESSION_SEC = 45.0

# Decode barcodes on every Nth camera frame. Barcode decoding is cheaper than
# face recognition but still worth throttling on a Raspberry Pi.
BARCODE_SCAN_EVERY_N_FRAMES = 4
