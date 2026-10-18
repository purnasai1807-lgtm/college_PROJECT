$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
if (-not $env:DATABASE_URL) { $env:DATABASE_URL = 'sqlite:///./backend/ace_canteen.db' }
$OutputDir = Join-Path $ProjectRoot 'backups'
$Output = python scripts/backup_manager.py backup --database-url $env:DATABASE_URL --output-dir $OutputDir
if ($LASTEXITCODE -ne 0) { throw 'Backup creation failed.' }
$Output | Write-Output
$BackupLine = $Output | Where-Object { $_ -like 'Backup created:*' } | Select-Object -First 1
if (-not $BackupLine) { throw 'Could not identify the created backup path.' }
$BackupPath = $BackupLine.Substring('Backup created:'.Length).Trim()
python scripts/backup_manager.py verify $BackupPath
if ($LASTEXITCODE -ne 0) { throw 'Backup verification failed.' }
