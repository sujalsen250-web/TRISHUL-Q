# ============================================================
#  TRISHUL-Q  -  portable launcher (Windows PowerShell)
# ------------------------------------------------------------
#  Copy the whole project folder to ANY Windows device and run:
#      powershell -ExecutionPolicy Bypass -File .\start-here.ps1
#  (or just double-click  start-here.bat )
#
#  It does everything by itself:
#    1. finds the project folder (this script's own folder)
#    2. creates a Python virtual environment
#    3. downloads + installs the requirements
#    4. keeps your .env (Google login + SMTP already inside)
#    5. brings up PostgreSQL on port 15432 via Docker
#       (if Docker is missing it still runs on the SQLite fallback)
#    6. downloads ngrok if needed and opens the public tunnel
#    7. builds the frontend only if needed
#    8. starts the server on http://localhost:8000
#
#  Safe to re-run - it skips whatever already exists.
# ============================================================

$ErrorActionPreference = "Continue"
$proj = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location $proj
Write-Host "== TRISHUL-Q portable start ==" -ForegroundColor Cyan
Write-Host "Folder: $proj`n"

# ---- helpers to read/write single keys in .env -----------------------------
function Get-EnvVal([string]$key) {
    if (-not (Test-Path ".env")) { return "" }
    foreach ($l in Get-Content ".env") {
        if ($l -match ("^\s*" + [regex]::Escape($key) + "\s*=\s*(.*)$")) { return $Matches[1].Trim() }
    }
    return ""
}
function Set-EnvVal([string]$key, [string]$val) {
    $lines = New-Object System.Collections.ArrayList
    if (Test-Path ".env") { foreach ($l in Get-Content ".env") { [void]$lines.Add($l) } }
    $done = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match ("^\s*" + [regex]::Escape($key) + "\s*=")) { $lines[$i] = "$key=$val"; $done = $true; break }
    }
    if (-not $done) { [void]$lines.Add("$key=$val") }
    $lines | Set-Content ".env" -Encoding ASCII
}

# ---- 1. find Python --------------------------------------------------------
$pyExe = $null
if (Get-Command py -ErrorAction SilentlyContinue) { $pyExe = "py" }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $pyExe = "python" }
elseif (Get-Command python3 -ErrorAction SilentlyContinue) { $pyExe = "python3" }
if (-not $pyExe) {
    Write-Host "Python not found. Install Python 3.10+ from https://python.org and re-run." -ForegroundColor Red
    exit 1
}

# ---- 2. virtual environment ------------------------------------------------
$venvPy = Join-Path $proj "venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "[1/6] Creating virtual environment..." -ForegroundColor Yellow
    if ($pyExe -eq "py") { py -3 -m venv venv } else { & $pyExe -m venv venv }
    $venvPy = Join-Path $proj "venv\Scripts\python.exe"
} else {
    Write-Host "[1/6] venv already exists - reusing it." -ForegroundColor Green
}

# ---- 3. dependencies -------------------------------------------------------
Write-Host "[2/6] Installing dependencies (first run downloads them)..." -ForegroundColor Yellow
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r requirements.txt
if (Test-Path "requirements-quantum.txt") {
    try { & $venvPy -m pip install -r requirements-quantum.txt } catch { }
}

# ---- 4. .env (kept as-is; created from example only if missing) ------------
Write-Host "[3/6] Checking .env..." -ForegroundColor Yellow
if (Test-Path ".env") {
    Write-Host "  .env found - keeping your Google/SMTP settings." -ForegroundColor Green
} elseif (Test-Path ".env.example") {
    Copy-Item ".env.example" ".env"
    Write-Host "  .env created from .env.example." -ForegroundColor Yellow
}

# ---- 5. database: PostgreSQL on 15432 via Docker ---------------------------
Write-Host "[4/6] Database (PostgreSQL on port 15432)..." -ForegroundColor Yellow
function Test-Port([int]$p) {
    try { $c = New-Object Net.Sockets.TcpClient; $c.Connect("127.0.0.1", $p); $c.Close(); return $true }
    catch { return $false }
}
if (Test-Port 15432) {
    Write-Host "  PostgreSQL already running on 15432." -ForegroundColor Green
} elseif (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Host "  Starting PostgreSQL via docker compose (port 15432)..."
    docker compose up -d db | Out-Null
    $up = $false
    for ($i = 0; $i -lt 30; $i++) { Start-Sleep -Seconds 2; if (Test-Port 15432) { $up = $true; break } }
    if ($up) { Write-Host "  PostgreSQL ready on 15432." -ForegroundColor Green }
    else { Write-Host "  Postgres start nahi hua - SQLite fallback use hoga." -ForegroundColor Yellow }
} else {
    Write-Host "  Docker nahi mila. TRISHUL-Q runs on PostgreSQL ONLY -- start PostgreSQL" -ForegroundColor Red
    Write-Host "  on port 15432 (easiest: install Docker Desktop: https://www.docker.com/products/docker-desktop )" -ForegroundColor Red
    Write-Host "  or set DATABASE_URL in .env to your PostgreSQL, then re-run." -ForegroundColor Red
}

# ---- 6. ngrok public tunnel ------------------------------------------------
Write-Host "[5/6] ngrok public tunnel..." -ForegroundColor Yellow
$ngToken  = Get-EnvVal "NGROK_AUTHTOKEN"
$ngDomain = Get-EnvVal "NGROK_DOMAIN"
$ngrok = $null
if (Test-Path "$HOME\ngrok\ngrok.exe") { $ngrok = "$HOME\ngrok\ngrok.exe" }
elseif (Get-Command ngrok -ErrorAction SilentlyContinue) { $ngrok = "ngrok" }
if (-not $ngrok) {
    Write-Host "  ngrok download kar rahe hain..."
    try {
        $zip = "$HOME\ngrok.zip"
        Invoke-WebRequest "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip" -OutFile $zip -UseBasicParsing
        Expand-Archive $zip "$HOME\ngrok" -Force
        if (Test-Path "$HOME\ngrok\ngrok.exe") { $ngrok = "$HOME\ngrok\ngrok.exe" }
    } catch { Write-Host "  ngrok download fail - tunnel skip." -ForegroundColor Yellow }
}
if ($ngrok) {
    if ($ngToken) { & $ngrok config add-authtoken $ngToken | Out-Null }
    $ngArgs = @("http", "8000")
    if ($ngDomain) { $ngArgs += "--domain=$ngDomain" }
    Start-Process $ngrok -ArgumentList $ngArgs -WindowStyle Minimized
    $pub = ""
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        try {
            $t = (Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2).tunnels |
                 Where-Object { $_.public_url -like "https*" } | Select-Object -First 1
            if ($t) { $pub = $t.public_url; break }
        } catch { }
    }
    if ($pub) {
        Set-EnvVal "PUBLIC_BASE_URL" $pub
        Write-Host "  PUBLIC URL : $pub" -ForegroundColor Green
    } else {
        Write-Host "  ngrok chalu hua par URL ready nahi - ngrok window dekho." -ForegroundColor Yellow
    }
} else {
    Write-Host "  ngrok nahi mila - localhost pe chalega (app phir bhi chalega)." -ForegroundColor Yellow
}

# ---- 7. frontend -----------------------------------------------------------
Write-Host "[6/6] Frontend build..." -ForegroundColor Yellow
if (Test-Path "frontend\dist\index.html") {
    Write-Host "  frontend\dist present." -ForegroundColor Green
} elseif (Get-Command npm -ErrorAction SilentlyContinue) {
    Push-Location frontend
    npm install --no-audit --no-fund
    npm run build
    Pop-Location
} else {
    Write-Host "  frontend\dist missing and npm not found - install Node.js LTS." -ForegroundColor Red
}

# ---- 8. run ----------------------------------------------------------------
Write-Host "`nStarting TRISHUL-Q on http://localhost:8000 ..." -ForegroundColor Cyan
Write-Host "  Super Admin: http://127.0.0.1:8000/superadmin (localhost only)`n" -ForegroundColor Green
& $venvPy server.py
