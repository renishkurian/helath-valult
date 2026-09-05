#!/usr/bin/env bash
# Pull latest code and restart the Health Vault systemd service.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$SCRIPT_DIR}"
SERVICE_NAME="${SERVICE_NAME:-healthvault}"
BRANCH="${BRANCH:-main}"

if [[ ! -d "$REPO_DIR/.git" ]]; then
  echo "error: not a git repo: $REPO_DIR" >&2
  exit 1
fi

echo "==> Pulling $BRANCH in $REPO_DIR"
cd "$REPO_DIR"
git fetch origin "$BRANCH"
git pull --ff-only origin "$BRANCH"
echo "==> Now at $(git rev-parse --short HEAD) ($(git log -1 --format=%s))"

BACKEND_DIR="$REPO_DIR/backend"
if [[ -f "$BACKEND_DIR/alembic.ini" ]]; then
  echo "==> Running DB migrations in $BACKEND_DIR"
  (cd "$BACKEND_DIR" && "$BACKEND_DIR/.venv/bin/alembic" upgrade head)
else
  echo "warn: no alembic.ini found in $BACKEND_DIR, skipping migrations" >&2
fi

echo "==> Restarting $SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
