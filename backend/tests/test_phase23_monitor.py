import importlib.util
import hashlib
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops_monitor.py"
spec = importlib.util.spec_from_file_location("ops_monitor", SCRIPT)
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


def test_backup_check_fails_when_no_backup_exists(tmp_path):
    result = ops.check_backup(tmp_path, 26)
    assert result["ok"] is False
    assert result["latest"] is None


def test_backup_check_accepts_fresh_manifested_backup(tmp_path):
    backup = tmp_path / "ace-canteen-test.db"
    payload = b"example backup"
    backup.write_bytes(payload)
    Path(str(backup) + ".json").write_text(json.dumps({"file": backup.name, "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}), encoding="utf-8")
    result = ops.check_backup(tmp_path, 26)
    assert result["ok"] is True
    assert result["latest"] == backup.name
    assert "checksum verified" in result["detail"]


def test_backup_check_flags_tampered_backup(tmp_path):
    backup = tmp_path / "ace-canteen-test.db"
    backup.write_bytes(b"original backup")
    Path(str(backup) + ".json").write_text(json.dumps({"file": backup.name, "size_bytes": len(b"original backup"), "sha256": hashlib.sha256(b"original backup").hexdigest()}), encoding="utf-8")
    backup.write_bytes(b"tampered backup")
    result = ops.check_backup(tmp_path, 26)
    assert result["ok"] is False
    assert "verification failed" in result["detail"]


def test_backup_check_flags_stale_backup(tmp_path):
    backup = tmp_path / "ace-canteen-old.sql"
    payload = b"example backup"
    backup.write_bytes(payload)
    Path(str(backup) + ".json").write_text(json.dumps({"file": backup.name, "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}), encoding="utf-8")
    import os, time
    old = time.time() - 48 * 3600
    os.utime(backup, (old, old))
    result = ops.check_backup(tmp_path, 26)
    assert result["ok"] is False
    assert result["detail"] == "backup is stale"
