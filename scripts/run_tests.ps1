$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw "Virtual environment not found. Run .\scripts\start_local.ps1 first, or create .venv and install backend\requirements.txt." }
$env:PYTHONPATH = 'backend'
$env:DATABASE_URL = 'sqlite:///./backend/test_runner.db'
$env:SECRET_KEY = 'local-test-only-secret-key-change-before-deployment'
$env:ENVIRONMENT = 'development'
Write-Host 'Running ACE Canteen backend regression tests...' -ForegroundColor Cyan
& $Python -m pytest backend/tests -q
if ($LASTEXITCODE -ne 0) { throw "Backend tests failed with exit code $LASTEXITCODE" }
Write-Host 'Checking frontend JavaScript syntax...'
if (Get-Command node -ErrorAction SilentlyContinue) {
    node --check frontend/js/app.js
    if ($LASTEXITCODE -ne 0) { throw 'frontend/js/app.js syntax check failed.' }
    node --check frontend/sw.js
    if ($LASTEXITCODE -ne 0) { throw 'frontend/sw.js syntax check failed.' }
} else {
    Write-Warning 'Node.js not found; skipped JavaScript syntax checks.'
}
Write-Host 'Checks completed.' -ForegroundColor Green
