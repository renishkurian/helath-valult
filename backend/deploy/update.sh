#!/usr/bin/env bash
# Pull latest code and/or restart the Health Vault systemd service.
#
# Usage:
#   ./update.sh pull      # git pull only
#   ./update.sh restart   # restart service only
#   ./update.sh deploy    # pull then restart (default)
#   ./update.sh status    # show service status
#   ./update.sh logs      # follow service logs
#
# Override paths on another host:
#   REPO_DIR=/path/to/repo SERVICE_NAME=healthvault ./update.sh deploy

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
SERVICE_NAME="${SERVICE_NAME:-healthvault}"
BRANCH="${BRANCH:-main}"

usage() {
  cat <<EOF
Health Vault deploy helper

Usage: $(basename "$0") [command]

Commands:
  deploy    Pull latest code and restart service (default)
  pull      git pull only
  restart   Restart systemd service only
  status    Show service status
  logs      Follow journal logs (Ctrl+C to exit)

Environment:
  REPO_DIR       Git repo root (default: $REPO_DIR)
  SERVICE_NAME   systemd unit name (default: $SERVICE_NAME)
  BRANCH         Git branch to pull (default: $BRANCH)
EOF
}

require_git_repo() {
  if [[ ! -d "$REPO_DIR/.git" ]]; then
    echo "error: not a git repo: $REPO_DIR" >&2
    exit 1
  fi
}

cmd_pull() {
  require_git_repo
  echo "==> Pulling $BRANCH in $REPO_DIR"
  cd "$REPO_DIR"
  git fetch origin "$BRANCH"
  git pull --ff-only origin "$BRANCH"
  echo "==> Now at $(git rev-parse --short HEAD) ($(git log -1 --format=%s))"
}

cmd_restart() {
  echo "==> Restarting $SERVICE_NAME"
  sudo systemctl restart "$SERVICE_NAME"
  sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
}

cmd_deploy() {
  cmd_pull
  cmd_restart
}

cmd_status() {
  sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
}

cmd_logs() {
  sudo journalctl -u "$SERVICE_NAME" -f
}

main() {
  local cmd="${1:-deploy}"
  case "$cmd" in
    pull) cmd_pull ;;
    restart) cmd_restart ;;
    deploy) cmd_deploy ;;
    status) cmd_status ;;
    logs) cmd_logs ;;
    -h|--help|help) usage ;;
    *)
      echo "error: unknown command: $cmd" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
