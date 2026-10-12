@echo off
REM TRISHUL-Q - one-shot start (Windows)
cd /d "%~dp0"

if not exist .env copy .env.example .env

echo ==^> Installing backend dependencies...
python -m pip install -q -r requirements.txt

echo ==^> Building the React frontend (first run only)...
if not exist frontend\dist\index.html (
  pushd frontend
  call npm install --no-audit --no-fund
  call npm run build
  popd
)

echo ==^> Starting TRISHUL-Q...
python server.py --host 0.0.0.0 --port 8000
pause
