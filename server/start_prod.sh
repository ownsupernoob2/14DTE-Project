#!/bin/bash
# Production server startup script for Smart Mirror API
# This script ensures the server always pulls the latest changes,
# rebuilds the Go executable, and runs the fresh binary on startup.

echo "=============================================="
echo "🚀 Starting Smart Mirror Production Server"
echo "=============================================="

# Ensure we are in the server directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Pull the latest code
echo ">>> Pulling latest code from GitHub..."
git fetch origin
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "development")
echo ">>> Detected branch: $CURRENT_BRANCH"
git pull origin "$CURRENT_BRANCH"

# 2. Rebuild the Go binary
echo ">>> Rebuilding Go server binary..."
go build -o smart-mirror-api-bin .
if [ $? -ne 0 ]; then
    echo "❌ Build failed! Starting previous binary if available..."
    if [ -f "./smart-mirror-api-bin" ]; then
        exec ./smart-mirror-api-bin
    else
        echo "❌ No previous binary found. Exiting."
        exit 1
    fi
fi

# 3. Start the newly compiled server
echo ">>> Launching production server..."
exec ./smart-mirror-api-bin
