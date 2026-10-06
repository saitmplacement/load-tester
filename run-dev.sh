#!/usr/bin/env bash
# Launch the FastAPI backend and the Next.js frontend together for local dev.
#
#   ./run-dev.sh
#
# Backend:  http://localhost:8000   (API)
# Frontend: http://localhost:3000   (open this in your browser)
#
# Requires: Python venv with requirements installed, and `npm install` run in web/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Start the FastAPI backend.
echo "Starting backend on http://localhost:8000 ..."
uvicorn api.main:app --port 8000 --reload &
BACKEND_PID=$!

# Ensure the backend is stopped when this script exits.
cleanup() {
  echo "Shutting down..."
  kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Start the Next.js dev server (foreground).
echo "Starting frontend on http://localhost:3000 ..."
cd "$ROOT/web"
npm run dev
