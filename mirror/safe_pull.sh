#!/bin/bash
# safe_pull.sh [branch] — bring this checkout up to date with GitHub, whatever
# state it's in, without losing anything.
#
# A plain `git pull --ff-only` stops at the first local edit or stray file
# ("commit your changes or stash them") and then the mirror never updates
# again. This tries the normal pull first, and if something is in the way it
# keeps a copy (git stash, or a backup branch for local commits) and then
# matches GitHub. Exit code 0 when up to date.

cd "$(dirname "$0")" || exit 1
BRANCH="${1:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null)}"
[ -z "$BRANCH" ] || [ "$BRANCH" = "HEAD" ] && BRANCH=main
STAMP="$(date +%Y%m%d-%H%M%S)"

# chmod on the Pi (e.g. making the scripts executable) is not a change.
git config core.fileMode false

# mirror/.env is no longer in git (it held a real key). Before an update can
# remove it, keep its settings in the per-Pi file that start_smart_mirror.sh
# loads, without overriding anything already set there.
ENV_FILE="$HOME/.config/smart-mirror/env"
if [ -f .env ]; then
    mkdir -p "$(dirname "$ENV_FILE")"
    touch "$ENV_FILE"
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|\#*) continue ;; esac
        key="${line%%=*}"
        current="$(grep -E "^${key}=" "$ENV_FILE" | tail -1 | cut -d= -f2-)"
        if [ -z "$current" ]; then
            echo "$line" >> "$ENV_FILE"
            echo "[UPDATE] Kept $key from mirror/.env in $ENV_FILE"
        fi
    done < .env
fi

git fetch origin "$BRANCH" || { echo "[UPDATE] Could not reach GitHub."; exit 1; }

if git pull --ff-only origin "$BRANCH"; then
    exit 0
fi

# Something local is in the way. Keep it, then try again.
echo "[UPDATE] Local changes are blocking the update; saving them first."
if git stash push --include-untracked -m "saved by safe_pull.sh before update $STAMP" >/dev/null 2>&1; then
    echo "[UPDATE] Saved: see 'git stash list' (newest first) to get them back."
fi
if git merge --ff-only "origin/$BRANCH"; then
    exit 0
fi

# This checkout has commits of its own: keep them on a branch, then match GitHub.
if ! git merge-base --is-ancestor HEAD "origin/$BRANCH"; then
    git branch "local-backup-$STAMP" HEAD
    echo "[UPDATE] This Pi's own commits are kept on branch local-backup-$STAMP."
fi
git reset --hard "origin/$BRANCH" && exit 0
echo "[UPDATE] Could not update; still on $(git rev-parse --short HEAD)."
exit 1
