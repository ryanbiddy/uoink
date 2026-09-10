"""An existing read does not initialize storage; explicit work still can."""
import sqlite3

import pytest

from index import Index
from server import _get_index as _production_get_index


def test_existing_open_never_creates_missing_storage(tmp_path):
    target = tmp_path / "absent" / "index.db"
    with pytest.raises(sqlite3.OperationalError):
        Index.open_existing(target)
    assert not target.parent.exists()


def test_read_open_does_not_migrate_then_explicit_backend_promotes(tmp_path, monkeypatch):
    import index
    import server
    path = tmp_path / "index.db"
    with Index.open(path):
        pass
    calls = []
    original = index._run_migrations
    def migrations(conn):
        calls.append(True)
        return original(conn)
    monkeypatch.setattr(index, "_run_migrations", migrations)
    monkeypatch.setattr(server, "_get_index", _production_get_index)
    monkeypatch.setattr(server, "INDEX_PATH", path)
    monkeypatch.setattr(server, "_index_singleton", None)
    reader = server._get_existing_index(timeout_s=1)
    try:
        assert calls == []
        assert reader._existing_read_only
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            with reader.write_transaction() as conn:
                conn.execute("UPDATE library_meta SET projection_revision=1")
        writer = server._get_index()
        assert writer is reader
        assert calls == [True]
        with writer.write_transaction() as conn:
            conn.execute("UPDATE library_meta SET projection_revision=1")
        assert writer._conn.execute("SELECT projection_revision FROM library_meta").fetchone()[0] == 1
        assert server._get_existing_index() is writer
        assert server._get_index() is writer
        assert calls == [True]
    finally:
        reader.close()


def test_failed_promotion_preserves_original_read_connection(tmp_path, monkeypatch):
    import index
    path = tmp_path / "index.db"
    with Index.open(path):
        pass
    with Index.open_existing(path) as reader:
        previous = reader._conn
        def unavailable(conn):
            raise sqlite3.OperationalError("declared initialization failure")
        monkeypatch.setattr(index, "_run_migrations", unavailable)
        with pytest.raises(sqlite3.OperationalError, match="declared initialization"):
            reader.initialize_for_write()
        assert reader._conn is previous
        assert reader._existing_read_only
        assert reader._conn.execute("SELECT projection_revision FROM library_meta").fetchone()[0] == 0
        assert not hasattr(reader, "_library_work_service")
