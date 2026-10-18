\
#!/usr/bin/env python3
"""Safe database backup, verification, and SQLite restore helper for ACE Canteen.

SQLite: uses SQLite's online backup API (consistent snapshots while the app is running).
PostgreSQL: invokes pg_dump; verification checks non-empty dump and SHA-256 manifest.
Restore is intentionally SQLite-only and requires --confirm. PostgreSQL restore is documented
as an operator-managed pg_restore/psql procedure to avoid accidental destructive writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def sqlite_path(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("This operation requires a SQLite DATABASE_URL.")
    raw = database_url[len("sqlite:///"):]
    if raw == ":memory:":
        raise ValueError("In-memory SQLite databases cannot be backed up by this tool.")
    path = Path(unquote(raw))
    return path if path.is_absolute() else Path.cwd() / path

def check_sqlite(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Database file not found: {path}")
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise ValueError(f"SQLite integrity check failed: {result[0] if result else 'no result'}")
        connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
    finally:
        connection.close()

def write_manifest(backup: Path, kind: str, source: str) -> Path:
    manifest = backup.with_suffix(backup.suffix + ".json")
    payload = {
        "format_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "source_database_type": source,
        "file": backup.name,
        "size_bytes": backup.stat().st_size,
        "sha256": sha256(backup),
    }
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return manifest

def backup(database_url: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    if database_url.startswith("sqlite:///"):
        source = sqlite_path(database_url)
        check_sqlite(source)
        target = output_dir / f"ace-canteen-{stamp}.db"
        temp = target.with_name(target.name + ".tmp")
        # SQLite's online backup API creates a consistent snapshot of a live database.
        src_conn = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
        dst_conn = sqlite3.connect(temp)
        try:
            src_conn.backup(dst_conn)
            dst_conn.commit()
        except Exception:
            temp.unlink(missing_ok=True)
            raise
        finally:
            dst_conn.close()
            src_conn.close()
        try:
            check_sqlite(temp)
            os.replace(temp, target)
            write_manifest(target, "sqlite-online-backup", "sqlite")
        except Exception:
            temp.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise
        return target
    if database_url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
        target = output_dir / f"ace-canteen-{stamp}.sql"
        temp = target.with_name(target.name + ".tmp")
        # pg_dump's libpq URL scheme is postgresql://, not SQLAlchemy's driver-qualified URL.
        pg_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        env = os.environ.copy()
        result = subprocess.run(["pg_dump", "--no-owner", "--no-privileges", "--dbname", pg_url, "--file", str(temp)], env=env, capture_output=True, text=True)
        if result.returncode != 0:
            temp.unlink(missing_ok=True)
            raise RuntimeError("pg_dump failed. Check PostgreSQL connectivity and pg_dump installation.")
        if not temp.exists() or temp.stat().st_size < 100:
            temp.unlink(missing_ok=True)
            raise RuntimeError("pg_dump returned an unexpectedly small backup.")
        try:
            with temp.open("rb") as stream:
                header = stream.read(4096).lstrip()
            if b"PostgreSQL database dump" not in header and b"CREATE " not in header:
                raise RuntimeError("pg_dump output does not resemble a PostgreSQL SQL dump.")
            os.replace(temp, target)
            write_manifest(target, "postgresql-sql-dump", "postgresql")
        except Exception:
            temp.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise
        return target
    raise ValueError("Unsupported DATABASE_URL. Expected SQLite or PostgreSQL.")

def verify(backup_path: Path) -> dict:
    manifest_path = backup_path.with_suffix(backup_path.suffix + ".json")
    if not backup_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("Backup or its .json manifest is missing.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("file") != backup_path.name:
        raise ValueError("Manifest filename does not match backup.")
    if manifest.get("size_bytes") != backup_path.stat().st_size:
        raise ValueError("Backup size does not match manifest; file may be truncated.")
    if manifest.get("sha256") != sha256(backup_path):
        raise ValueError("SHA-256 mismatch; backup may be corrupted or changed.")
    if manifest.get("kind") == "sqlite-online-backup":
        check_sqlite(backup_path)
    elif manifest.get("kind") == "postgresql-sql-dump":
        if backup_path.stat().st_size < 100:
            raise ValueError("PostgreSQL dump is unexpectedly small.")
        with backup_path.open("rb") as f:
            header = f.read(4096).lstrip()
        if b"PostgreSQL database dump" not in header and b"CREATE " not in header:
            raise ValueError("PostgreSQL dump does not resemble a SQL dump.")
    else:
        raise ValueError("Unknown backup type in manifest.")
    return manifest

def restore_sqlite(backup_path: Path, destination: Path, confirm: bool) -> Path:
    if not confirm:
        raise ValueError("Restore is destructive; pass --confirm after checking the destination.")
    manifest = verify(backup_path)
    if manifest.get("kind") != "sqlite-online-backup":
        raise ValueError("Only verified SQLite backups can be restored by this command.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        check_sqlite(destination)
        safety_copy = destination.with_name(destination.name + ".pre-restore-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
        shutil.copy2(destination, safety_copy)
    else:
        safety_copy = None
    temp = destination.with_name(destination.name + ".restore-tmp")
    shutil.copy2(backup_path, temp)
    check_sqlite(temp)
    os.replace(temp, destination)
    return safety_copy

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_backup = sub.add_parser("backup", help="Create a consistent database backup and SHA-256 manifest")
    p_backup.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite:///./backend/ace_canteen.db"))
    p_backup.add_argument("--output-dir", type=Path, default=Path("backups"))
    p_verify = sub.add_parser("verify", help="Verify backup manifest, checksum, and SQLite integrity")
    p_verify.add_argument("backup_file", type=Path)
    p_restore = sub.add_parser("restore-sqlite", help="Restore a verified SQLite backup (destructive)")
    p_restore.add_argument("backup_file", type=Path)
    p_restore.add_argument("--destination", type=Path, required=True)
    p_restore.add_argument("--confirm", action="store_true", help="Required acknowledgement of destructive restore")
    args = parser.parse_args()
    try:
        if args.command == "backup":
            output = backup(args.database_url, args.output_dir)
            print(f"Backup created: {output}")
            print(f"Manifest: {output}.json")
        elif args.command == "verify":
            manifest = verify(args.backup_file)
            print(f"Backup verified: {args.backup_file} ({manifest['size_bytes']} bytes, SHA-256 OK)")
        else:
            safety = restore_sqlite(args.backup_file, args.destination, args.confirm)
            print(f"SQLite restore complete: {args.destination}")
            if safety:
                print(f"Previous database preserved at: {safety}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
