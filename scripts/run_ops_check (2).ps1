$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$env:PYTHONPATH = 'backend'
$BaseUrl = if ($env:ACE_CANTEEN_BASE_URL) { $env:ACE_CANTEEN_BASE_URL } else { 'http://127.0.0.1:8000' }
python scripts/ops_monitor.py --base-url $BaseUrl --backup-dir backups --max-backup-age-hours 26 --json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
