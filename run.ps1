# ============================================================
#  TRISHUL-Q - run everything (Windows PowerShell)
#
#  Starts:
#    1. the ngrok public tunnel (a separate minimised window)
#    2. the TRISHUL-Q server (this window, foreground)
#
#  Usage (from the project folder):
#      .\run.ps1
#  If PowerShell blocks scripts, run once:
#      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#
#  Notes:
#    * PostgreSQL must already be running (see db-setup.ps1 the first time).
#    * Keep BOTH windows open while you use the app.
# ============================================================

$ErrorActionPreference = 'Continue'
if ($PSScriptRoot) { Set-Location $PSScriptRoot }

if (-not (Test-Path .env)) {
    Write-Host "WARNING: .env not found - starting with defaults (dev)." -ForegroundColor Yellow
}

# ------------------------------------------- public tunnel (optional) ----
$ngrok = $null
if (Test-Path "$HOME\ngrok\ngrok.exe") { $ngrok = "$HOME\ngrok\ngrok.exe" }
elseif (Get-Command ngrok -ErrorAction SilentlyContinue) { $ngrok = "ngrok" }

if ($ngrok) {
    Write-Host "Starting ngrok tunnel..." -ForegroundColor Cyan
    Start-Process $ngrok -ArgumentList 'http', '8000' -WindowStyle Minimized
    Start-Sleep -Seconds 6
    try {
        $url = (Invoke-RestMethod 'http://127.0.0.1:4040/api/tunnels').tunnels |
               Where-Object { $_.public_url -like 'https*' } |
               Select-Object -First 1 -ExpandProperty public_url
        if ($url) {
            Write-Host ""
            Write-Host "  PUBLIC URL : $url" -ForegroundColor Green
            Write-Host "  (share this; Super Admin stays localhost-only)" -ForegroundColor DarkGray
            Write-Host ""
        }
    } catch {
        Write-Host "ngrok URL not ready yet - check the ngrok window." -ForegroundColor Yellow
    }
} else {
    Write-Host "ngrok not found - skipping public tunnel (app still runs on localhost)." -ForegroundColor Yellow
}

# ------------------------------------------- server (foreground) ----
Write-Host "Starting TRISHUL-Q server..." -ForegroundColor Cyan
python server.py
