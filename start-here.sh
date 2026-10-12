#!/usr/bin/env bash
# ============================================================
#  TRISHUL-Q - portable launcher (Linux / macOS / WSL)
#  Run:   bash start-here.sh
# ============================================================
set -e
cd "$(dirname "$0")"
echo "== TRISHUL-Q portable start =="

PY=python3
command -v python3 >/dev/null 2>&1 || PY=python

get_env() { [ -f .env ] && sed -n "s/^$1=//p" .env | head -1; }
set_env() {
  if grep -q "^$1=" .env 2>/dev/null; then
    sed -i.bak "s|^$1=.*|$1=$2|" .env && rm -f .env.bak
  else
    echo "$1=$2" >> .env
  fi
}

# 1. venv + deps
if [ ! -d venv ]; then
  echo "[1/6] Creating virtual environment..."
  "$PY" -m venv venv
fi
echo "[2/6] Installing dependencies..."
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt
[ -f requirements-quantum.txt ] && ./venv/bin/python -m pip install -r requirements-quantum.txt || true

# 2. .env
echo "[3/6] Checking .env..."
if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "  .env created from .env.example."
fi

# 3. database: PostgreSQL on 15432 via Docker
echo "[4/6] Database (PostgreSQL on port 15432)..."
port_up() { (exec 3<>"/dev/tcp/127.0.0.1/15432") 2>/dev/null; }
if port_up; then
  echo "  PostgreSQL already running on 15432."
elif command -v docker >/dev/null 2>&1; then
  echo "  Starting PostgreSQL via docker compose (port 15432)..."
  docker compose up -d db
  for i in $(seq 1 30); do sleep 2; port_up && break; done
else
  echo "  Docker not found. TRISHUL-Q runs on PostgreSQL ONLY - start PostgreSQL"
  echo "  on port 15432 (e.g. install Docker Desktop) or set DATABASE_URL in .env."
fi

# 4. ngrok public tunnel
echo "[5/6] ngrok public tunnel..."
NGTOKEN=$(get_env NGROK_AUTHTOKEN)
NGDOMAIN=$(get_env NGROK_DOMAIN)
if command -v ngrok >/dev/null 2>&1; then
  [ -n "$NGTOKEN" ] && ngrok config add-authtoken "$NGTOKEN" >/dev/null 2>&1 || true
  if [ -n "$NGDOMAIN" ]; then
    ngrok http 8000 --domain="$NGDOMAIN" --log=stdout >/dev/null 2>&1 &
  else
    ngrok http 8000 --log=stdout >/dev/null 2>&1 &
  fi
  PUB=""
  for i in $(seq 1 20); do
    sleep 1
    PUB=$(curl -s http://127.0.0.1:4040/api/tunnels | grep -o 'https://[^"]*ngrok[^"]*' | head -1 || true)
    [ -n "$PUB" ] && break
  done
  if [ -n "$PUB" ]; then
    set_env PUBLIC_BASE_URL "$PUB"
    echo "  PUBLIC URL : $PUB"
  else
    echo "  ngrok started but URL not ready yet."
  fi
else
  echo "  ngrok not found - running on localhost only."
fi

# 5. frontend
echo "[6/6] Frontend build..."
if [ ! -f frontend/dist/index.html ] && command -v npm >/dev/null 2>&1; then
  ( cd frontend && npm install --no-audit --no-fund && npm run build )
fi

# 6. run
echo
echo "Starting TRISHUL-Q on http://localhost:8000 ..."
exec ./venv/bin/python server.py
