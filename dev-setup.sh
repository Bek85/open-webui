#!/usr/bin/env bash
# dev-setup.sh — install deps and start both backend and frontend for local dev
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UV="${UV:-$HOME/.local/bin/uv}"
BACKEND_PORT="${BACKEND_PORT:-8080}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

# ── helpers ───────────────────────────────────────────────────────────────────
log() { echo "[dev-setup] $*"; }
die() { echo "[dev-setup] ERROR: $*" >&2; exit 1; }

# ── 1. uv (Python toolchain) ──────────────────────────────────────────────────
if ! command -v "$UV" &>/dev/null; then
    log "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# ── 2. Python deps ────────────────────────────────────────────────────────────
log "Syncing Python dependencies (uv sync)..."
cd "$REPO_DIR"
"$UV" python install 3.11 --quiet
"$UV" sync --quiet

# ── 3. Node deps ──────────────────────────────────────────────────────────────
log "Installing Node dependencies (npm ci)..."
source ~/.nvm/nvm.sh 2>/dev/null || true
npm ci --quiet 2>/dev/null || npm install --quiet

# ── 4. Start backend ─────────────────────────────────────────────────────────
log "Starting backend on port $BACKEND_PORT..."
BACKEND_LOG="/tmp/open-webui-backend.log"
CORS_ALLOW_ORIGIN="*" \
    "$UV" run --directory "$REPO_DIR/backend" \
    uvicorn open_webui.main:app \
    --port "$BACKEND_PORT" --host 0.0.0.0 \
    --forwarded-allow-ips '*' --reload \
    > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
log "Backend PID $BACKEND_PID — logs: $BACKEND_LOG"

# wait for backend to be ready
log "Waiting for backend..."
until curl -sf --max-time 2 "http://localhost:$BACKEND_PORT/health" > /dev/null 2>&1; do
    sleep 2
    # bail if backend process died
    kill -0 $BACKEND_PID 2>/dev/null || { log "Backend crashed. Check $BACKEND_LOG"; exit 1; }
done
log "Backend ready at http://localhost:$BACKEND_PORT"

# ── 5. Start frontend dev server ─────────────────────────────────────────────
log "Starting frontend dev server on port $FRONTEND_PORT..."
npm run dev -- --port "$FRONTEND_PORT" &
FRONTEND_PID=$!
log "Frontend PID $FRONTEND_PID — http://localhost:$FRONTEND_PORT"

# ── 6. Trap Ctrl-C to clean up both ──────────────────────────────────────────
cleanup() {
    log "Shutting down..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
    log "Done."
}
trap cleanup INT TERM

log "Both services running. Press Ctrl-C to stop."
wait $BACKEND_PID $FRONTEND_PID
