# ============================================================
#  TRISHUL-Q - one-shot setup (Windows PowerShell)
#  Does everything in one run:
#    1. creates the PostgreSQL role + database
#    2. starts an ngrok public tunnel (accessible from other networks)
#    3. writes the .env  (PostgreSQL + Google OAuth + SMTP + public URL)
#    4. starts the server
#
#  Usage (from the project folder):
#      .\setup.ps1
#  If PowerShell blocks scripts, run once:
#      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
# ============================================================

$ErrorActionPreference = "Stop"
if ($PSScriptRoot) { Set-Location -Path $PSScriptRoot }

Write-Host "=== TRISHUL-Q setup ===" -ForegroundColor Cyan
Write-Host "Answer the prompts (Enter accepts the default).`n"

# ------------------------------------------------ PostgreSQL ----
Write-Host "--- PostgreSQL ---" -ForegroundColor Yellow
$pgUser = Read-Host "PostgreSQL admin user [postgres]"
if ([string]::IsNullOrWhiteSpace($pgUser)) { $pgUser = "postgres" }
$pgPass = Read-Host "PostgreSQL admin password"
$pgDb   = Read-Host "Database name [trishulq]"
if ([string]::IsNullOrWhiteSpace($pgDb)) { $pgDb = "trishulq" }
$appUser = Read-Host "App DB user [trishul]"
if ([string]::IsNullOrWhiteSpace($appUser)) { $appUser = "trishul" }
$appPass = Read-Host "App DB password [trishul]"
if ([string]::IsNullOrWhiteSpace($appPass)) { $appPass = "trishul" }

# ------------------------------------------------ Google OAuth ----
Write-Host "`n--- Google OAuth (blank to skip) ---" -ForegroundColor Yellow
$gId  = Read-Host "Google Client ID"
$gSec = ""
if (-not [string]::IsNullOrWhiteSpace($gId)) { $gSec = Read-Host "Google Client Secret" }

# ------------------------------------------------ SMTP mail ----
Write-Host "`n--- SMTP mail (blank host to skip) ---" -ForegroundColor Yellow
$smtpHost = Read-Host "SMTP host (e.g. smtp.gmail.com)"
$smtpPort = "587"; $smtpUser = ""; $smtpPass = ""; $smtpFrom = ""; $smtpName = "TRISHUL-Q"
if (-not [string]::IsNullOrWhiteSpace($smtpHost)) {
    $smtpPort = Read-Host "SMTP port [587]"; if ([string]::IsNullOrWhiteSpace($smtpPort)) { $smtpPort = "587" }
    $smtpUser = Read-Host "SMTP username (email)"
    $smtpPass = Read-Host "SMTP password / app password"
    $smtpFrom = Read-Host "From email [$smtpUser]"; if ([string]::IsNullOrWhiteSpace($smtpFrom)) { $smtpFrom = $smtpUser }
}
$saEmail = Read-Host "SUPER_ADMIN_EMAIL (where admin welcome mail is sent)"

# ------------------------------------------------ ngrok ----
Write-Host "`n--- ngrok public tunnel (blank to skip) ---" -ForegroundColor Yellow
$ngToken = Read-Host "ngrok authtoken (blank if already configured)"
$ngDom   = Read-Host "ngrok static domain, e.g. name.ngrok-free.app (blank = random URL)"

$appEnv = Read-Host "`nAPP_ENV: production (PostgreSQL only, no SQLite fallback) or development [production]"
if ([string]::IsNullOrWhiteSpace($appEnv)) { $appEnv = "production" }

# -------------------------------------------- 1. PostgreSQL ----
Write-Host "`n[1/4] PostgreSQL..." -ForegroundColor Yellow
if (-not (Get-Command psql -ErrorAction SilentlyContinue)) {
    Write-Warning "psql not found on PATH. Add PostgreSQL\bin to PATH (or use pgAdmin) and re-run."
} else {
    $env:PGPASSWORD = $pgPass
    # role
    $roleExists = (psql -U $pgUser -h localhost -tAc "SELECT 1 FROM pg_roles WHERE rolname='$appUser'") 2>$null
    if ("$roleExists".Trim() -eq "1") {
        Write-Host "  role '$appUser' exists" -ForegroundColor Green
    } else {
        psql -U $pgUser -h localhost -c "CREATE USER $appUser WITH PASSWORD '$appPass'" | Out-Null
        Write-Host "  created role '$appUser'" -ForegroundColor Green
    }
    # database
    $dbExists = (psql -U $pgUser -h localhost -tAc "SELECT 1 FROM pg_database WHERE datname='$pgDb'") 2>$null
    if ("$dbExists".Trim() -eq "1") {
        Write-Host "  database '$pgDb' exists" -ForegroundColor Green
    } else {
        psql -U $pgUser -h localhost -c "CREATE DATABASE $pgDb OWNER $appUser" | Out-Null
        Write-Host "  created database '$pgDb'" -ForegroundColor Green
    }
}

# ------------------------------------------------ 2. ngrok ----
Write-Host "[2/4] ngrok public tunnel..." -ForegroundColor Yellow
$pub = ""
if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    Write-Warning "  ngrok not found on PATH - skipping public tunnel."
} else {
    if (-not [string]::IsNullOrWhiteSpace($ngToken)) { ngrok config add-authtoken $ngToken | Out-Null }
    $ngArgs = @("http", "8000")
    if (-not [string]::IsNullOrWhiteSpace($ngDom)) { $ngArgs += "--domain=$ngDom" }
    Start-Process ngrok -ArgumentList $ngArgs -WindowStyle Minimized
    for ($i = 0; $i -lt 25; $i++) {
        Start-Sleep -Seconds 1
        try {
            $t = (Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2).tunnels |
                 Where-Object { $_.public_url -like "https*" } | Select-Object -First 1
            if ($t) { $pub = $t.public_url; break }
        } catch { }
    }
    if ($pub) { Write-Host "  public URL: $pub" -ForegroundColor Green }
    else { Write-Warning "  could not read the ngrok URL - check the ngrok window." }
}

# ------------------------------------------------ 3. .env ----
Write-Host "[3/4] writing .env..." -ForegroundColor Yellow
$encAppPass = [uri]::EscapeDataString($appPass)
$baseUrl = if ($pub) { $pub } else { "http://localhost:8000" }
$envContent = @"
APP_ENV=$appEnv
APP_MODE=live
DATABASE_URL=postgresql+psycopg2://$appUser:$encAppPass@localhost:5432/$pgDb
TRISHUL_DB_FALLBACK=0
PUBLIC_BASE_URL=$baseUrl

GOOGLE_CLIENT_ID=$gId
GOOGLE_CLIENT_SECRET=$gSec

SMTP_HOST=$smtpHost
SMTP_PORT=$smtpPort
SMTP_USERNAME=$smtpUser
SMTP_PASSWORD=$smtpPass
SMTP_FROM_EMAIL=$smtpFrom
SMTP_FROM_NAME=$smtpName
SMTP_USE_TLS=1

SUPER_ADMIN_EMAIL=$saEmail
"@
Set-Content -Path ".env" -Value $envContent -Encoding UTF8
Write-Host "  .env written" -ForegroundColor Green

# ------------------------------- 4. Google redirect reminder ----
if (-not [string]::IsNullOrWhiteSpace($gId)) {
    Write-Host "`n  IMPORTANT - add BOTH redirect URIs in Google Cloud Console" -ForegroundColor Magenta
    Write-Host "  (APIs & Services -> Credentials -> your OAuth client):" -ForegroundColor Magenta
    Write-Host "     http://localhost:8000/api/auth/google/callback"
    if ($pub) { Write-Host "     $pub/api/auth/google/callback" }
    Read-Host "  Press Enter once you have added them (or Enter to continue now)"
}

# --------------------------------------------- start server ----
Write-Host "[4/4] starting TRISHUL-Q..." -ForegroundColor Cyan
python server.py
