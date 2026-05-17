#!/bin/bash
# Path to your repository
REPO_DIR="$HOME/14DTE-Project"

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
    
    echo "Code updated."
    
    # If you have a systemd service running your mirror (e.g., smartmirror.service),
    # uncomment the line below to automatically restart it when new code arrives!
    # sudo systemctl restart smartmirror.service
    
    # Or, if you use a tool like PM2 to manage your python script:
    # pm2 restart smart_mirror
else
    echo "Mirror is up to date. ($LOCAL)"
fi
