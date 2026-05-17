#!/bin/bash
# Path to your repository
REPO_DIR="$HOME/14DTE-Project"
VENV_DIR="$HOME/mirror-venv"

cd $REPO_DIR

# Fetch the latest changes from the remote without modifying local files yet
git fetch origin main

# Compare local main branch with remote main branch
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "New updates found on GitHub! Pulling changes..."
    # Reset any local changes just in case, and pull the latest code
    git reset --hard origin/main
    git pull origin main
    
    # Re-install any new dependencies into the venv
    $VENV_DIR/bin/pip install -r $REPO_DIR/mirror/requirements.txt --quiet
    
    echo "Code updated. Restarting mirror service..."
    sudo systemctl restart smartmirror.service
else
    echo "Mirror is up to date. ($LOCAL)"
fi
