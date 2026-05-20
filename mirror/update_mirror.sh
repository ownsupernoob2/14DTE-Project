#!/bin/bash
# Path to your repository
REPO_DIR="$HOME/14DTE-Project"
PYTHON_ENV="/home/raspi/.pyenv/versions/3.10.7/envs/mediapipe"

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
    
    # Re-install any new dependencies into the pyenv
    $PYTHON_ENV/bin/pip install -r $REPO_DIR/mirror/requirements.txt --quiet
    
    echo "Code updated. Restarting mirror..."
    # Run start_smart_mirror.sh to restart everything
    /home/raspi/14DTE-Project/mirror/start_smart_mirror.sh
else
    echo "Mirror is up to date. ($LOCAL)"
fi
