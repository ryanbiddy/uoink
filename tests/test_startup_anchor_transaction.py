"""Default seed durability and ownership before standing-capture startup."""
import sqlite3
import pytest

from index import Index
from writing_studio import seed_default_anchors


def test_default_seed_is_durable_and_releases_transaction(tmp_path):
    path = tmp_path / "index.db"
    anchors = [{"name": "Seeded", "source_type": "text", "raw_text": "Fixture prose"}]
    with Index.open(path) as idx:
        assert seed_default_anchors(idx, anchors) == 1
        assert not idx._conn.in_transaction
        with sqlite3.connect(path) as observer:
            assert observer.execute("SELECT name,active,is_default FROM style_anchors").fetchall() == [("Seeded", 0, 1)]
        with idx.write_transaction() as conn:
            assert conn.execute("SELECT COUNT(*) FROM style_anchors").fetchone()[0] == 1
    with Index.open(path) as reopened:
        assert seed_default_anchors(reopened, anchors) == 0
        assert not reopened._conn.in_transaction


def test_default_seed_refuses_foreign_transaction_without_absorbing_it(tmp_path):
    with Index.open(tmp_path / "index.db") as idx:
        idx._conn.execute("BEGIN IMMEDIATE")
        idx._conn.execute("INSERT INTO style_anchors(name,source_type,raw_text,active,is_default,added_at) VALUES ('Caller','text','Uncommitted',1,0,'fixture')")
        with pytest.raises(RuntimeError, match="transaction"):
            seed_default_anchors(idx, [{"name": "Default", "raw_text": "Fixture"}])
        assert idx._conn.in_transaction
        assert idx._conn.execute("SELECT name FROM style_anchors").fetchall()[0][0] == "Caller"
        idx._conn.rollback()
        assert idx._conn.execute("SELECT COUNT(*) FROM style_anchors").fetchone()[0] == 0


def test_default_seed_rolls_back_partial_failure(tmp_path):
    with Index.open(tmp_path / "index.db") as idx:
        anchors = [{"name": "First", "raw_text": "Fixture"}, {"name": "Bad", "raw_text": {"unsupported": True}}]
        with pytest.raises(sqlite3.ProgrammingError):
            seed_default_anchors(idx, anchors)
        assert not idx._conn.in_transaction
        assert idx._conn.execute("SELECT COUNT(*) FROM style_anchors").fetchone()[0] == 0
