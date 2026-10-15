"""Recovery preserves storage on operational errors and quarantine failures."""

import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest

import index
from index import Index


def _storage(tmp_path):
    path = tmp_path / "index.db"
    files = {
        path: b"original database",
        tmp_path / "index.db-wal": b"uncheckpointed writes",
        tmp_path / "index.db-shm": b"shared memory",
    }
    for target, content in files.items():
        target.write_bytes(content)
    return path, files


def _fail_open(monkeypatch, error):
    replacement = object()
    opener = Mock(side_effect=[error, replacement])
    monkeypatch.setattr(Index, "open", opener)
    return opener, replacement


def _assert_originals(files):
    for path, content in files.items():
        assert path.read_bytes() == content


@pytest.mark.parametrize("error", [
    sqlite3.OperationalError("database is locked"),
    sqlite3.OperationalError("database table is locked"),
    sqlite3.OperationalError("database or disk is full"),
    sqlite3.OperationalError("disk I/O error"),
    sqlite3.OperationalError("attempt to write a readonly database"),
    sqlite3.OperationalError("unable to open database file"),
    sqlite3.OperationalError("no such table: schema_version"),
    sqlite3.OperationalError("database disk image is malformed"),
    sqlite3.DatabaseError("unrecognized database error"),
    sqlite3.IntegrityError("UNIQUE constraint failed: schema_version.version"),
])
def test_non_corruption_propagates_without_touching_storage(
        tmp_path, monkeypatch, error):
    path, files = _storage(tmp_path)
    opener, _ = _fail_open(monkeypatch, error)

    with pytest.raises(type(error)) as raised:
        Index.open_or_recover(path)

    assert raised.value is error
    opener.assert_called_once_with(path)
    _assert_originals(files)
    assert set(tmp_path.iterdir()) == set(files)


@pytest.mark.parametrize("code", [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_FULL,
                                  sqlite3.SQLITE_IOERR, sqlite3.SQLITE_ERROR])
def test_non_corruption_code_takes_precedence_over_message(
        tmp_path, monkeypatch, code):
    path, files = _storage(tmp_path)
    error = sqlite3.DatabaseError("file is not a database")
    error.sqlite_errorcode = code
    opener, _ = _fail_open(monkeypatch, error)

    with pytest.raises(sqlite3.DatabaseError) as raised:
        Index.open_or_recover(path)

    assert raised.value is error
    opener.assert_called_once_with(path)
    _assert_originals(files)
    assert set(tmp_path.iterdir()) == set(files)


@pytest.mark.parametrize("message,code", [
    ("file is not a database", None),
    ("database disk image is malformed", None),
    ("corruption", sqlite3.SQLITE_CORRUPT),
    ("not a database", sqlite3.SQLITE_NOTADB),
    ("corrupt index", sqlite3.SQLITE_CORRUPT | (3 << 8)),
])
def test_verified_corruption_preserves_database_and_sidecars_together(
        tmp_path, monkeypatch, message, code):
    path, files = _storage(tmp_path)
    error = sqlite3.DatabaseError(message)
    if code is not None:
        error.sqlite_errorcode = code
    opener, replacement = _fail_open(monkeypatch, error)

    assert Index.open_or_recover(path) == (replacement, True)

    assert opener.call_count == 2
    quarantine, = tmp_path.glob("index.db.corrupt-*")
    assert {item.name for item in quarantine.iterdir()} == {
        source.name for source in files}
    for source, content in files.items():
        assert not source.exists()
        assert (quarantine / source.name).read_bytes() == content


@pytest.mark.parametrize("failed_name", ["index.db-wal", "index.db-shm", "index.db"])
def test_rename_failure_restores_originals_and_never_opens_a_replacement(
        tmp_path, monkeypatch, failed_name):
    path, files = _storage(tmp_path)
    opener, _ = _fail_open(
        monkeypatch, sqlite3.DatabaseError("file is not a database"))
    real_rename = Path.rename
    failure = PermissionError("injected rename failure")

    def rename(source, target):
        if source.name == failed_name:
            raise failure
        return real_rename(source, target)

    monkeypatch.setattr(Path, "rename", rename)

    with pytest.raises(PermissionError) as raised:
        Index.open_or_recover(path)

    assert raised.value is failure
    opener.assert_called_once_with(path)
    _assert_originals(files)
    for saved in tmp_path.glob("index.db.corrupt-*/*"):
        assert saved.read_bytes() == files[tmp_path / saved.name]


@pytest.mark.parametrize("restore_failure", ["occupied", "unsupported"])
def test_failed_rollback_keeps_quarantined_bytes_and_does_not_overwrite(
        tmp_path, monkeypatch, caplog, restore_failure):
    path, files = _storage(tmp_path)
    wal = tmp_path / "index.db-wal"
    opener, _ = _fail_open(
        monkeypatch, sqlite3.DatabaseError("file is not a database"))
    real_rename = Path.rename

    def rename(source, target):
        if source == path:
            if restore_failure == "occupied":
                wal.write_bytes(b"new file at original path")
            raise PermissionError("injected rename failure")
        return real_rename(source, target)

    monkeypatch.setattr(Path, "rename", rename)
    if restore_failure == "unsupported":
        monkeypatch.setattr(Path, "hardlink_to", Mock(
            side_effect=OSError("injected hard link failure")))

    with pytest.raises(PermissionError, match="injected rename failure"):
        Index.open_or_recover(path)

    opener.assert_called_once_with(path)
    assert path.read_bytes() == files[path]
    quarantine, = tmp_path.glob("index.db.corrupt-*")
    for source, content in files.items():
        if source != path:
            assert (quarantine / source.name).read_bytes() == content
    if restore_failure == "occupied":
        assert wal.read_bytes() == b"new file at original path"
    assert "could not restore" in caplog.text
    assert str(quarantine) in caplog.text


def test_quarantine_creation_failure_preserves_originals(tmp_path, monkeypatch):
    path, files = _storage(tmp_path)
    opener, _ = _fail_open(
        monkeypatch, sqlite3.DatabaseError("file is not a database"))
    monkeypatch.setattr(index.tempfile, "mkdtemp", Mock(
        side_effect=OSError("injected disk full")))

    with pytest.raises(OSError, match="injected disk full"):
        Index.open_or_recover(path)

    opener.assert_called_once_with(path)
    _assert_originals(files)
    assert set(tmp_path.iterdir()) == set(files)


def test_sidecar_stat_failure_preserves_originals(tmp_path, monkeypatch):
    path, files = _storage(tmp_path)
    opener, _ = _fail_open(
        monkeypatch, sqlite3.DatabaseError("file is not a database"))
    real_stat = Path.stat

    def stat(source, *args, **kwargs):
        if source.name == "index.db-wal":
            raise PermissionError("injected stat failure")
        return real_stat(source, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "stat", stat)
        with pytest.raises(PermissionError, match="injected stat failure"):
            Index.open_or_recover(path)

    opener.assert_called_once_with(path)
    _assert_originals(files)
    assert set(tmp_path.iterdir()) == set(files)


def test_failed_fresh_open_preserves_quarantine(tmp_path, monkeypatch):
    path, files = _storage(tmp_path)
    error = sqlite3.OperationalError("database or disk is full")
    opener = Mock(side_effect=[
        sqlite3.DatabaseError("file is not a database"), error])
    monkeypatch.setattr(Index, "open", opener)

    with pytest.raises(sqlite3.OperationalError) as raised:
        Index.open_or_recover(path)

    assert raised.value is error
    assert opener.call_count == 2
    quarantine, = tmp_path.glob("index.db.corrupt-*")
    for source, content in files.items():
        assert (quarantine / source.name).read_bytes() == content


def test_same_timestamp_recoveries_never_overwrite_previous_quarantines(
        tmp_path, monkeypatch):
    monkeypatch.setattr(index.time, "strftime", lambda *_args: "20261015-120000")
    previous = tmp_path / "index.db.corrupt-20261015-120000"
    previous.write_bytes(b"older quarantine")
    expected = []
    for number in range(2):
        path, files = _storage(tmp_path)
        files[path] = f"corrupt database {number}".encode()
        path.write_bytes(files[path])
        _fail_open(monkeypatch, sqlite3.DatabaseError("file is not a database"))
        Index.open_or_recover(path)
        expected.append(files[path])

    quarantines = [item for item in tmp_path.glob("index.db.corrupt-*")
                   if item.is_dir()]
    assert len(quarantines) == 2
    assert sorted((item / "index.db").read_bytes() for item in quarantines) == expected
    for quarantine in quarantines:
        assert (quarantine / "index.db-wal").read_bytes() == b"uncheckpointed writes"
        assert (quarantine / "index.db-shm").read_bytes() == b"shared memory"
    assert previous.read_bytes() == b"older quarantine"


def test_real_non_database_file_is_quarantined_and_rebuilt(tmp_path):
    path = tmp_path / "index.db"
    original = b"this is not a SQLite database"
    path.write_bytes(original)

    idx, recovered = Index.open_or_recover(path)
    with idx:
        assert recovered is True
        assert idx.schema_version() == index.latest_schema_version()
        assert idx._conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    quarantine, = tmp_path.glob("index.db.corrupt-*")
    assert (quarantine / path.name).read_bytes() == original


def test_healthy_database_keeps_records_and_is_not_quarantined(tmp_path):
    path = tmp_path / "index.db"
    with Index.open(path) as idx:
        idx._conn.execute("CREATE TABLE recovery_sentinel (value TEXT)")
        idx._conn.execute("INSERT INTO recovery_sentinel VALUES ('keep me')")
        idx._conn.commit()

    idx, recovered = Index.open_or_recover(path)
    with idx:
        assert recovered is False
        assert idx._conn.execute("SELECT value FROM recovery_sentinel").fetchone()[0] == "keep me"
    assert list(tmp_path.glob("index.db.corrupt-*")) == []


def test_migration_operational_error_preserves_real_database(tmp_path, monkeypatch):
    path = tmp_path / "index.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE recovery_sentinel (value TEXT)")
        conn.execute("INSERT INTO recovery_sentinel VALUES ('saved draft')")
    conn.close()
    error = sqlite3.OperationalError("database or disk is full")
    monkeypatch.setattr(index, "_run_migrations", Mock(side_effect=error))

    with pytest.raises(sqlite3.OperationalError) as raised:
        Index.open_or_recover(path)

    assert raised.value is error
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT value FROM recovery_sentinel").fetchone()[0] == "saved draft"
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()
    assert list(tmp_path.glob("index.db.corrupt-*")) == []
