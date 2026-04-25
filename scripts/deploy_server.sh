#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="${REPO_ROOT:-/opt/bingo/Bingo-Game}"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"
PYTHON_BIN="$BACKEND_DIR/.venv/bin/python"
PIP_BIN="$BACKEND_DIR/.venv/bin/pip"
HEALTHCHECK_URL="${1:-${HEALTHCHECK_URL:-https://okbingogame.work.gd/healthz}}"
SERVICES=(
  "bingo-web.service"
  "bingo-bot.service"
  "bingo-engine.service"
)

fail() {
  echo "[deploy] $*" >&2
  exit 1
}

run_systemctl() {
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    systemctl "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo systemctl "$@"
  else
    fail "systemctl requires root or passwordless sudo"
  fi
}

[[ -d "$REPO_ROOT/.git" ]] || fail "repo not found at $REPO_ROOT"
[[ -d "$BACKEND_DIR" ]] || fail "backend directory not found"
[[ -d "$FRONTEND_DIR" ]] || fail "frontend directory not found"
[[ -x "$PYTHON_BIN" ]] || fail "python virtualenv not found at $PYTHON_BIN"
[[ -x "$PIP_BIN" ]] || fail "pip virtualenv not found at $PIP_BIN"
command -v npm >/dev/null 2>&1 || fail "npm is required on the server"
command -v curl >/dev/null 2>&1 || fail "curl is required on the server"

echo "[deploy] Starting deploy for commit $(git -C "$REPO_ROOT" rev-parse HEAD)"

echo "[deploy] Installing backend dependencies"
(
  cd "$BACKEND_DIR"
  "$PIP_BIN" install --disable-pip-version-check -r requirements.txt
)

echo "[deploy] Running Django migrations and checks"
(
  cd "$BACKEND_DIR"
  "$PYTHON_BIN" manage.py migrate --noinput
  "$PYTHON_BIN" manage.py check
)

echo "[deploy] Installing frontend dependencies and building production assets"
(
  cd "$FRONTEND_DIR"
  npm ci --no-audit --no-fund
  npm run build
)

echo "[deploy] Restarting services"
run_systemctl restart "${SERVICES[@]}"

echo "[deploy] Confirming service status"
run_systemctl is-active "${SERVICES[@]}"

echo "[deploy] Waiting for health check: $HEALTHCHECK_URL"
curl --fail --silent --show-error --retry 5 --retry-delay 3 --max-time 20 "$HEALTHCHECK_URL" >/dev/null

echo "[deploy] Deployment completed successfully"
