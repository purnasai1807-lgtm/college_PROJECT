$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "`n=== ACE Canteen local setup ===" -ForegroundColor Cyan
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found. Install Python 3.11+ from python.org and enable the launcher, then retry."
}
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    Write-Host '[1/5] Creating virtual environment...'
    py -3 -m venv .venv
} else {
    Write-Host '[1/5] Reusing .venv'
}
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path '.env')) {
    Write-Host '[2/5] Creating local .env from .env.example...'
    Copy-Item '.env.example' '.env'
} else {
    Write-Host '[2/5] Keeping existing .env'
}

Write-Host '[3/5] Installing backend dependencies (first run may take a few minutes)...'
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Could not upgrade pip.' }
& $Python -m pip install -r 'backend\requirements.txt'
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }

Write-Host '[4/5] Applying database migrations...'
$env:PYTHONPATH = 'backend'
& $Python -m alembic -c 'backend/alembic.ini' upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed. Read the error above; your existing database was not intentionally deleted.' }

Write-Host '[5/5] Starting ACE Canteen at http://127.0.0.1:8000/' -ForegroundColor Green
Write-Host 'Keep this terminal open. Press Ctrl+C to stop the server.'
& $Python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
