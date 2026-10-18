\
import importlib.util
import json
import sqlite3
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "backup_manager.py"
spec = importlib.util.spec_from_file_location("backup_manager", MODULE_PATH)
backup_manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup_manager)


def make_db(path: Path, value: str = "hello") -> None:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE IF NOT EXISTS sample (value TEXT)")
    connection.execute("DELETE FROM sample")
    connection.execute("INSERT INTO sample(value) VALUES (?)", (value,))
    connection.commit()
    connection.close()


def test_backup_and_manifest_verify(tmp_path):
    source = tmp_path / "source.db"
    make_db(source)
    output = backup_manager.backup(f"sqlite:///{source}", tmp_path / "backups")
    manifest = backup_manager.verify(output)
    assert manifest["kind"] == "sqlite-online-backup"
    connection = sqlite3.connect(output)
    assert connection.execute("SELECT value FROM sample").fetchone()[0] == "hello"
    connection.close()


def test_verification_detects_tampering(tmp_path):
    source = tmp_path / "source.db"
    make_db(source)
    output = backup_manager.backup(f"sqlite:///{source}", tmp_path / "backups")
    with output.open("ab") as stream:
        stream.write(b"tamper")
    try:
        backup_manager.verify(output)
    except ValueError as exc:
        assert "size" in str(exc).lower() or "sha-256" in str(exc).lower()
    else:
        raise AssertionError("Tampering must be detected")


def test_restore_requires_explicit_confirmation_and_preserves_old_db(tmp_path):
    source = tmp_path / "source.db"
    make_db(source, "from-backup")
    backup = backup_manager.backup(f"sqlite:///{source}", tmp_path / "backups")
    destination = tmp_path / "restore.db"
    make_db(destination, "existing-data")
    try:
        backup_manager.restore_sqlite(backup, destination, confirm=False)
    except ValueError as exc:
        assert "destructive" in str(exc)
    else:
        raise AssertionError("Restore should require confirmation")
    safety_copy = backup_manager.restore_sqlite(backup, destination, confirm=True)
    assert safety_copy and safety_copy.exists()
    connection = sqlite3.connect(destination)
    assert connection.execute("SELECT value FROM sample").fetchone()[0] == "from-backup"
    connection.close()
    connection = sqlite3.connect(safety_copy)
    assert connection.execute("SELECT value FROM sample").fetchone()[0] == "existing-data"
    connection.close()


def test_restore_rejects_corrupt_or_unverified_backup(tmp_path):
    source = tmp_path / "source.db"
    make_db(source)
    backup = backup_manager.backup(f"sqlite:///{source}", tmp_path / "backups")
    backup.with_suffix(backup.suffix + ".json").unlink()
    try:
        backup_manager.restore_sqlite(backup, tmp_path / "restore.db", confirm=True)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Unverified backup must not be restored")


def test_sqlite_integrity_check_rejects_missing_file(tmp_path):
    try:
        backup_manager.check_sqlite(tmp_path / "missing.db")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Missing database must fail")
