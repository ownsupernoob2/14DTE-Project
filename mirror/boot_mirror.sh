#!/bin/bash
# Path to your repository
REPO_DIR="$HOME/14DTE-Project"
VENV_DIR="$HOME/mirror-venv"

echo "Checking for updates on boot..."
cd $REPO_DIR

# Pull the latest code directly on boot
git pull origin main

# Re-install any new dependencies into the venv just in case
$VENV_DIR/bin/pip install -r $REPO_DIR/mirror/requirements.txt --quiet

# Launch the mirror
echo "Starting Smart Mirror..."
bash $REPO_DIR/mirror/start_smart_mirror.sh
