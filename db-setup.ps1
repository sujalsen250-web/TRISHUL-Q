# ============================================================
#  TRISHUL-Q - one-shot DATABASE setup (Windows PowerShell)
#
#  Does everything:
#    1. installs PostgreSQL 15 (if it is not already installed)
#    2. creates the app role + database
#    3. creates ALL tables (migrations) and verifies the connection
#
#  Usage (from the project folder):
#      .\db-setup.ps1
#  If PowerShell blocks scripts, run once:
#      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#
#  Notes:
#    * Super-user password is assumed to be 'postgres' (that is what the
#      unattended install below sets). If you already installed PostgreSQL
#      with a different password, edit $env:PGPASSWORD below.
#    * The app role/password ('trishul'/'trishul') match the DATABASE_URL in
#      .env.example.
# ============================================================

$ErrorActionPreference = 'Continue'
$proj = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location $proj

Write-Host "=== TRISHUL-Q database setup ===" -ForegroundColor Cyan

function Find-Psql {
    $c = Get-Command psql -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    foreach ($v in @('17', '16', '15', '14')) {
        $p = "C:\Program Files\PostgreSQL\$v\bin\psql.exe"
        if (Test-Path $p) { return $p }
    }
    return $null
}

# ------------------------------------------------- 1. PostgreSQL ----
$psql = Find-Psql
if (-not $psql) {
    Write-Host "PostgreSQL not found - installing (unattended)..." -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id PostgreSQL.PostgreSQL.15 --source winget `
            --accept-source-agreements --accept-package-agreements `
            --override "--mode unattended --unattendedmodeui none --superpassword postgres --serverport 5432"
        Start-Sleep -Seconds 10
        $psql = Find-Psql
    } else {
        Write-Host "winget not available. Install PostgreSQL manually from" -ForegroundColor Red
        Write-Host "  https://www.enterprisedb.com/downloads/postgres-postgresql-downloads" -ForegroundColor Red
        Write-Host "  (password: postgres, port: 5432), then re-run this script." -ForegroundColor Red
    }
}

# --------------------------------------- 2. role + database ----
if ($psql) {
    Write-Host "psql: $psql" -ForegroundColor Green
    $env:PGPASSWORD = 'postgres'
    Write-Host "Creating role 'trishul' and database 'trishulq'..."
    & $psql -U postgres -h localhost -c "CREATE USER trishul WITH PASSWORD 'trishul';" 2>$null
    & $psql -U postgres -h localhost -c "CREATE DATABASE trishulq OWNER trishul;" 2>$null

    # ----------------------------------- 3. tables + verify ----
    Write-Host "Creating tables and verifying the connection..."
    python -c "from backend import db; db.init_db(); print(db.database_status())"
    Write-Host "`nDone. Start the server with:  python server.py" -ForegroundColor Cyan
} else {
    Write-Host "`nPostgreSQL is still not available." -ForegroundColor Red
    Write-Host "Open a NEW PowerShell window (so PATH refreshes) and run:  .\db-setup.ps1" -ForegroundColor Red
}
