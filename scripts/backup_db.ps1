param(
    [string]$OutputDirectory = ".\backups"
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

$composeDb = docker compose ps --status running --services db 2>$null
if (($env:DATABASE_URL -and $env:DATABASE_URL.StartsWith("postgresql")) -or $composeDb) {
    $file = Join-Path $OutputDirectory "ace-canteen-$stamp.sql"
    docker compose exec -T db sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | Set-Content -Encoding utf8 $file
} else {
    $source = ".\backend\ace_canteen.db"
    if (!(Test-Path $source)) { throw "SQLite database not found at $source. Set DATABASE_URL or run the app once first." }
    $file = Join-Path $OutputDirectory "ace-canteen-$stamp.db"
    Copy-Item $source $file
}
Write-Host "Backup written to $file"
