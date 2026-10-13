#!/bin/bash
# auto_updater.sh — Background GitHub update watcher for Smart Mirror
# Periodically checks for updates on GitHub 'main'.
# When new commits are found, it pulls them, updates requirements if needed,
# and restarts the mirror by running start_smart_mirror.sh.

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

INTERVAL="${MIRROR_UPDATE_INTERVAL:-120}"   # Check every 2 minutes
BRANCH="${MIRROR_BRANCH:-main}"
LOG_FILE="$APP_DIR/updater.log"

PYTHON="${MIRROR_PYTHON:-$HOME/mirror-venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
    if [ -x "$APP_DIR/.venv/bin/python" ]; then
        PYTHON="$APP_DIR/.venv/bin/python"
    else
        PYTHON="python3"
    fi
fi

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

log "Auto-updater started (interval: ${INTERVAL}s, branch: $BRANCH)"

while true; do
    sleep "$INTERVAL"

    cd "$APP_DIR" || continue

    # 1. Fetch remote tracking branch
    if ! git fetch origin "$BRANCH" 2>/dev/null; then
        continue
    fi

    LOCAL_SHA="$(git rev-parse HEAD 2>/dev/null)"
    REMOTE_SHA="$(git rev-parse "origin/$BRANCH" 2>/dev/null)"

    if [ -n "$LOCAL_SHA" ] && [ -n "$REMOTE_SHA" ] && [ "$LOCAL_SHA" != "$REMOTE_SHA" ]; then
        COMMIT_MSG="$(git log -1 --format="%h: %s" "origin/$BRANCH" 2>/dev/null)"
        log "=========================================================="
        log "New update detected on origin/$BRANCH ($LOCAL_SHA -> $REMOTE_SHA)"
        log "Commit: $COMMIT_MSG"
        log "=========================================================="

        # Check if requirements.txt changed
        REQ_CHANGED=false
        if git diff --name-only "$LOCAL_SHA" "$REMOTE_SHA" 2>/dev/null | grep -q "requirements.txt"; then
            REQ_CHANGED=true
        fi

        # Pull updates
        if git pull --ff-only origin "$BRANCH" >> "$LOG_FILE" 2>&1; then
            log "Successfully pulled updates from GitHub."

            if [ "$REQ_CHANGED" = true ] && [ -x "$PYTHON" ]; then
                log "requirements.txt changed. Installing updated dependencies..."
                "$PYTHON" -m pip install -r requirements.txt >> "$LOG_FILE" 2>&1 || log "[WARN] pip install encountered an issue."
            fi

            log "Restarting Smart Mirror via start_smart_mirror.sh..."
            /bin/bash "$APP_DIR/start_smart_mirror.sh"
            exit 0
        else
            log "[WARN] git pull --ff-only failed. Will retry next cycle."
        fi
    fi
done
