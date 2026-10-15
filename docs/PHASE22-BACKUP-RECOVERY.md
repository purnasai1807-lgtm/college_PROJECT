\
# Phase 22 — Backup integrity and safer SQLite recovery

## Added

- `scripts/backup_manager.py` creates consistent SQLite snapshots using SQLite's online backup API rather than copying a live database file.
- Backup files are written to a temporary path, checked, then atomically moved into place; unique timestamp names avoid same-second collisions. Each backup has a JSON manifest containing creation time, database type, byte size, and SHA-256 checksum.
- `verify` validates the manifest/checksum and runs SQLite `PRAGMA integrity_check`.
- `restore-sqlite` refuses to run without `--confirm`, validates the backup first, writes a pre-restore safety copy when the destination exists, and replaces the database atomically via a temporary file.
- PostgreSQL backups use `pg_dump` and get a checksum manifest. SQLAlchemy's `postgresql+psycopg://` URL is normalized to libpq's `postgresql://` scheme before invoking `pg_dump`, and the output is checked for plausible SQL dump content. PostgreSQL restore is deliberately not automated here: rehearse restore to a separate staging database with your DBA/operator and a verified `psql`/`pg_restore` process.

## Windows PowerShell

From the project root, ensure `backend/ace_canteen.db` exists (or set `DATABASE_URL` to your actual SQLite URL).

```powershell
$env:DATABASE_URL = "sqlite:///./backend/ace_canteen.db"
python scripts/backup_manager.py backup --output-dir backups
```

The command prints the backup file. Verify it before storing it elsewhere:

```powershell
python scripts/backup_manager.py verify backups\ace-canteen-YYYYMMDD-HHMMSS.db
```

Restore only after stopping the app and confirming the destination path. The command preserves the old database as a timestamped `.pre-restore-*` copy.

```powershell
python scripts/backup_manager.py restore-sqlite backups\ace-canteen-YYYYMMDD-HHMMSS.db --destination backend\ace_canteen.db --confirm
```

## Linux/macOS or server

```sh
DATABASE_URL='sqlite:///./backend/ace_canteen.db' python scripts/backup_manager.py backup --output-dir backups
python scripts/backup_manager.py verify backups/ace-canteen-YYYYMMDD-HHMMSS.db
```

For PostgreSQL, set `DATABASE_URL` to the deployment URL and ensure `pg_dump` is installed and permitted to connect. The URL can contain credentials, so do not paste it into logs or commit it to Git.

## Operational guidance

- Store copies off the application host and encrypt them at rest; the local `backups/` folder alone is not disaster recovery.
- Use a scheduler (Task Scheduler or cron) and alert on non-zero exit codes.
- Periodically restore into an isolated staging environment and verify order/catalogue data before calling the backup process reliable.
- The restore helper only restores SQLite databases. Do not use it on a production database while the app is running.
- This phase does not change payments, orders, refunds, or the existing no-refunds policy.
