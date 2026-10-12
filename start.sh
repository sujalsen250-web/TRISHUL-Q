#!/usr/bin/env bash
# TRISHUL-Q — one-shot start (Linux / macOS / WSL).
set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit DATABASE_URL / passwords before production."
fi

echo "==> Installing backend dependencies…"
python3 -m pip install -q -r requirements.txt

echo "==> Building the React frontend (first run only)…"
if [ ! -f frontend/dist/index.html ]; then
  ( cd frontend && npm install --no-audit --no-fund && npm run build ) \
    || ( cd frontend && npm run build:esbuild )
fi

echo "==> Starting TRISHUL-Q…"
python3 server.py --host "${TRISHUL_HOST:-0.0.0.0}" --port "${TRISHUL_PORT:-8000}"
