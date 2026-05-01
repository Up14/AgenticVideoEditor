#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Auto-setup backend venv ──────────────────────────────────────────────────
VENV="$ROOT/backend/venv"
if [ ! -d "$VENV" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv "$VENV"
fi
echo "Installing/updating Python dependencies..."
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$ROOT/backend/requirements.txt"

# ── Auto-setup frontend node_modules ────────────────────────────────────────
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "Installing frontend dependencies..."
  cd "$ROOT/frontend" && npm install
fi

# Kill any leftover processes on our ports
fuser -k 9636/tcp 2>/dev/null || true
fuser -k 9637/tcp 2>/dev/null || true

echo "Starting backend on port 9637..."
cd "$ROOT/backend"
"$VENV/bin/uvicorn" main:app --host 127.0.0.1 --port 9637 --reload &
BACKEND_PID=$!

echo "Starting frontend on port 9636..."
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "App running at http://localhost:9636"
echo "(backend internal port: 9637)"
echo ""
echo "Press Ctrl+C to stop both servers."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
