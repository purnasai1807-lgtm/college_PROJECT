# Phase 23 — Operations monitoring and scheduled backup checks

## Included

- `scripts/ops_monitor.py`: checks `/api/health`, `/api/ready`, and whether the latest manifested backup is within the allowed age. It validates the manifest filename, byte size, and SHA-256 digest before treating a backup as healthy. Supports readable output and JSON, returns exit code 1 if any check fails.
- `scripts/backup_and_verify.ps1`: creates a backup and immediately verifies the manifest/checksum/integrity using the Phase 22 tool.
- `scripts/run_ops_check.ps1`: runs the monitoring check from Windows PowerShell.
- CI workflow additions exercise monitor behavior without requiring a running canteen service.

## Run manually (PowerShell)

From the project root with the app running:

```powershell
$env:ACE_CANTEEN_BASE_URL = 'http://127.0.0.1:8000'
$env:DATABASE_URL = 'sqlite:///./backend/ace_canteen.db'
.\scriptsackup_and_verify.ps1
python scripts/ops_monitor.py --base-url $env:ACE_CANTEEN_BASE_URL --backup-dir backups --max-backup-age-hours 26 --json
```

Exit code `0` means all checks passed; exit code `1` means the health, readiness, or backup-freshness check failed. The monitor intentionally does not expose environment variables, database credentials, or detailed server errors.

## Windows Task Scheduler (example)

Create two separate scheduled tasks, running under a dedicated least-privilege account:

- Backup: daily at a low-traffic time; program `powershell.exe`; arguments `-NoProfile -ExecutionPolicy Bypass -File "C:\path	o\clg\scriptsackup_and_verify.ps1"`; start in `C:\path	o\clg`.
- Monitor: every 15 minutes; program `powershell.exe`; arguments `-NoProfile -ExecutionPolicy Bypass -File "C:\path	o\clg\scripts
un_ops_check.ps1"`; start in the project root.

Replace paths with the actual installation path. Configure Task Scheduler to alert an operator on non-zero exit codes using your organization's chosen monitoring/notification mechanism; this script does not send external alerts by itself.

## Linux cron (example)

Run with a dedicated service account and absolute paths. Example schedules (adjust paths and environment file handling to your deployment):

```cron
15 2 * * * cd /opt/ace-canteen && /opt/ace-canteen/.venv/bin/python scripts/backup_manager.py backup --output-dir /opt/ace-canteen/backups && /opt/ace-canteen/.venv/bin/python scripts/ops_monitor.py --base-url http://127.0.0.1:8000 --backup-dir /opt/ace-canteen/backups >> /var/log/ace-canteen-ops.log 2>&1
*/15 * * * * cd /opt/ace-canteen && /opt/ace-canteen/.venv/bin/python scripts/ops_monitor.py --base-url http://127.0.0.1:8000 --backup-dir /opt/ace-canteen/backups >> /var/log/ace-canteen-ops.log 2>&1
```

Use a secured secret/environment management approach for `DATABASE_URL`; do not place credentials in source control or shared crontab text.

## Production limitations

- A successful HTTP health/readiness check only indicates that the app responds and can reach its database; it does not prove payment-provider health or business workflows.
- The monitor validates backup manifest consistency and SHA-256 integrity, but does not run a full database integrity check or restore the backup on every monitoring interval. The backup script verifies new backups; schedule periodic full verification and restoration drills as well.
- Store encrypted backups off-host and restrict access. Avoid retaining customer data in publicly accessible locations.
- No refund feature or paid-order refund workflow is introduced.
