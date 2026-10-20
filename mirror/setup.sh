#!/bin/bash
# setup.sh — install everything the mirror needs on a Raspberry Pi.
#
#   ./setup.sh           full install (safe to re-run)
#   ./setup.sh --ensure  quick check used by start_smart_mirror.sh on every
#                        launch: installs only what is missing, so a fresh
#                        clone or a pull that changed requirements just works
#
# Needs passwordless sudo for apt (the Pi default) and network on first run.

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"
PATH="$PATH:/usr/sbin:/sbin"     # modinfo / modprobe aren't on a user's PATH on Debian

ENSURE=false
[ "$1" = "--ensure" ] && ENSURE=true

# At boot nobody is there to type a sudo password, so --ensure never asks for
# one: anything that needs it is skipped with a note to run ./setup.sh once.
if $ENSURE; then SUDO="sudo -n"; else SUDO="sudo"; fi

VENV_DIR="$HOME/mirror-venv"
UV="$HOME/.uv-tool/bin/uv"
REQ_STAMP="$VENV_DIR/.requirements.sha256"

say() { echo ">>> $*"; }

# Each entry is "pkg" or "pkg|alternative" (Debian renamed some for t64).
APT_PACKAGES=(
    python3-venv ffmpeg v4l2loopback-dkms v4l-utils "libzbar0t64|libzbar0"
    tesseract-ocr cmake build-essential libopenblas-dev liblapack-dev
)

apt_missing() {
    local entry alt found missing=()
    for entry in "${APT_PACKAGES[@]}"; do
        found=false
        IFS='|' read -ra alts <<< "$entry"
        for alt in "${alts[@]}"; do
            if dpkg -s "$alt" >/dev/null 2>&1; then found=true; break; fi
        done
        $found || missing+=("${alts[0]}")
    done
    echo "${missing[@]}"
}

ensure_apt() {
    local missing
    missing="$(apt_missing)"
    # v4l2loopback is built by DKMS against the running kernel's headers.
    if ! modinfo v4l2loopback >/dev/null 2>&1; then
        missing="$missing v4l2loopback-dkms linux-headers-$(uname -r)"
    fi
    [ -z "${missing// /}" ] && return 0
    say "Installing system packages:$missing"
    if ! $SUDO true 2>/dev/null; then
        say "WARNING: missing packages need sudo — run ./setup.sh once to install them."
        return 0
    fi
    $SUDO apt-get update -q
    # One at a time, so a single unavailable package can't block the rest.
    for pkg in $missing; do
        $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -q "$pkg" \
            || say "WARNING: could not install $pkg"
    done
    if ! modinfo v4l2loopback >/dev/null 2>&1; then
        say "WARNING: v4l2loopback is still unavailable — the camera pipeline will not start."
    fi
}

# The mirror needs Python 3.10 (mediapipe / dlib wheels). Raspberry Pi OS
# trixie ships 3.13, so a standalone 3.10 comes from uv when it's missing.
find_python310() {
    if command -v python3.10 >/dev/null 2>&1; then
        command -v python3.10
    elif [ -x "$UV" ] && "$UV" python find 3.10 >/dev/null 2>&1; then
        "$UV" python find 3.10
    fi
}

ensure_python() {
    PYTHON="$(find_python310)"
    if [ -z "$PYTHON" ]; then
        say "Installing Python 3.10 (via uv)..."
        if [ ! -x "$UV" ]; then
            python3 -m venv "$HOME/.uv-tool" && "$HOME/.uv-tool/bin/pip" install -q uv
        fi
        "$UV" python install 3.10
        PYTHON="$(find_python310)"
    fi
    if [ -z "$PYTHON" ]; then
        say "ERROR: could not provide Python 3.10."
        exit 1
    fi
}

venv_is_310() {
    [ -x "$VENV_DIR/bin/python" ] &&
        "$VENV_DIR/bin/python" -c 'import sys; sys.exit(sys.version_info[:2] != (3, 10))' 2>/dev/null
}

ensure_venv() {
    if [ -e "$VENV_DIR" ] && ! venv_is_310; then
        say "Existing $VENV_DIR is not Python 3.10 — moving it to $VENV_DIR.old"
        rm -rf "$VENV_DIR.old"
        mv "$VENV_DIR" "$VENV_DIR.old"
    fi
    if [ ! -d "$VENV_DIR" ]; then
        say "Creating virtual environment at $VENV_DIR"
        "$PYTHON" -m venv "$VENV_DIR" || exit 1
    fi
}

requirements_hash() {
    cat requirements.txt setup.sh | sha256sum | cut -d' ' -f1
}

ensure_pip() {
    local want
    want="$(requirements_hash)"
    if [ -f "$REQ_STAMP" ] && [ "$(cat "$REQ_STAMP")" = "$want" ]; then
        return 0
    fi
    say "Installing Python packages..."
    "$VENV_DIR/bin/python" -m pip install -q --upgrade pip wheel || exit 1
    "$VENV_DIR/bin/python" -m pip install -q -r requirements.txt || exit 1
    # face_recognition pins a source-built dlib; use the prebuilt dlib-bin instead.
    "$VENV_DIR/bin/python" -m pip install -q --no-deps face_recognition || exit 1
    if ! "$VENV_DIR/bin/python" -c "import cv2, mediapipe, face_recognition, PyQt6.QtWidgets"; then
        say "ERROR: the Python packages did not install cleanly."
        exit 1
    fi
    echo "$want" > "$REQ_STAMP"
}

# The camera pipeline needs two loopback devices: /dev/video42 for the face
# daemon, /dev/video43 for the gesture engine (one reader per device). Loading
# them at boot means the start script never needs sudo.
LOOPBACK_OPTIONS='options v4l2loopback devices=2 video_nr=42,43 card_label=FaceCam,GestureCam exclusive_caps=0,0'
ensure_loopback_at_boot() {
    local conf=/etc/modprobe.d/smart-mirror-v4l2loopback.conf
    local load=/etc/modules-load.d/smart-mirror-v4l2loopback.conf
    if [ "$(cat "$conf" 2>/dev/null)" = "$LOOPBACK_OPTIONS" ] && [ -f "$load" ]; then
        return 0
    fi
    if ! $SUDO true 2>/dev/null; then
        say "WARNING: run ./setup.sh once so the camera loopback loads at boot."
        return 0
    fi
    say "Configuring v4l2loopback to load at boot"
    echo "$LOOPBACK_OPTIONS" | $SUDO tee "$conf" >/dev/null
    echo "v4l2loopback" | $SUDO tee "$load" >/dev/null
}

ensure_files() {
    chmod +x start_smart_mirror.sh setup.sh auto_updater.sh 2>/dev/null || true
    if [ ! -f gesture_recognizer.task ]; then
        say "Downloading the hand tracking model..."
        wget -O gesture_recognizer.task -q \
            https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task
    fi
}

ensure_env_file() {
    local dir="$HOME/.config/smart-mirror" file
    file="$dir/env"
    [ -f "$file" ] && return 0
    mkdir -p "$dir"
    cat > "$file" <<'EOF'
# Smart Mirror settings for this Pi (not stored in git).
# MIRROR_API_KEY must match MIRROR_API_KEY in the server's .env.
MIRROR_API_KEY=
# API_URL=https://api.smartmirror.me
# MIRROR_ID=library-mirror
EOF
    chmod 600 "$file"
    say "Created $file — put the server's MIRROR_API_KEY in it."
}

ensure_autostart() {
    local dir="$HOME/.config/autostart" entry
    entry="$dir/smart_mirror.desktop"
    mkdir -p "$dir"
    cat > "$entry.tmp" <<EOF
[Desktop Entry]
Type=Application
Name=Smart Mirror
Exec=/bin/bash $APP_DIR/start_smart_mirror.sh
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
    if ! cmp -s "$entry.tmp" "$entry"; then
        mv "$entry.tmp" "$entry"
        chmod +x "$entry"
        say "Autostart entry written to $entry"
    else
        rm -f "$entry.tmp"
    fi
}

$ENSURE || echo "=========================================================="
$ENSURE || echo "Installing Smart Mirror Environment..."
$ENSURE || echo "=========================================================="

ensure_apt
ensure_loopback_at_boot
ensure_python
ensure_venv
ensure_pip
ensure_files
ensure_env_file
ensure_autostart

if ! $ENSURE; then
    say "Using $("$VENV_DIR/bin/python" --version) at $VENV_DIR"
    echo "=========================================================="
    echo "Setup complete. Start the mirror with: ./start_smart_mirror.sh"
    echo "=========================================================="
fi
