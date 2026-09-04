from __future__ import annotations

import sqlite3

import pytest

import index as index_mod
import server


def test_main_exits_nonzero_when_bind_fails(monkeypatch):
    monkeypatch.setattr(server, "_existing_server_responds", lambda: False)
    monkeypatch.setattr(
        server.migrate_install, "run_migration", lambda **_kwargs: {"outcome": "noop"}
    )
    monkeypatch.setattr(server, "_apply_output_root_fallback", lambda: None)

    class BindFailure:
        def __init__(self, *_args, **_kwargs):
            raise OSError("address already in use")

    monkeypatch.setattr(server, "_YoinkHTTPServer", BindFailure)
    with pytest.raises(SystemExit) as raised:
        server.main()
    assert raised.value.code == 1


@pytest.mark.parametrize(("healthy", "expected"), [(True, 0), (False, 1)])
def test_doctor_exit_tracks_health(monkeypatch, healthy, expected):
    monkeypatch.setattr(server, "doctor_payload", lambda: {"ok": healthy})
    monkeypatch.setattr(server, "_print_json", lambda _payload: None)
    assert server.run_cli(["--doctor"]) == expected


def test_doctor_fails_for_unhealthy_helper_or_pending_migration(monkeypatch):
    monkeypatch.setattr(server, "_diagnose_payload", lambda: {"ok": True})
    monkeypatch.setattr(server.migrate_install, "migration_status", lambda: {})
    monkeypatch.setattr(server, "_mcp_stdio_selfcheck", lambda: {"ok": True})
    monkeypatch.setattr(
        server, "_path_integrity_status", lambda force=False: {"ok": True}
    )
    monkeypatch.setattr(
        server, "_podcast_corpus_reconciliation_status", lambda: {"ok": True}
    )

    monkeypatch.setattr(server, "_helper_health_status", lambda: {"ok": False})
    monkeypatch.setattr(
        server.index,
        "schema_migration_status",
        lambda _path: {"current": 24, "latest": 24, "pending": False},
    )
    assert server.doctor_payload()["ok"] is False

    monkeypatch.setattr(server, "_helper_health_status", lambda: {"ok": True})
    monkeypatch.setattr(
        server.index,
        "schema_migration_status",
        lambda _path: {"current": 23, "latest": 24, "pending": True},
    )
    assert server.doctor_payload()["ok"] is False


def test_schema_migration_status_is_read_only(tmp_path, monkeypatch):
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "0001_initial.sql").write_text("SELECT 1;", encoding="utf-8")
    (migration_dir / "0002_next.sql").write_text("SELECT 2;", encoding="utf-8")
    monkeypatch.setattr(index_mod, "_MIGRATIONS_DIR", migration_dir)

    db_path = tmp_path / "index.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT)"
        )
        conn.execute("INSERT INTO schema_version VALUES (1, 'now')")

    status = index_mod.schema_migration_status(db_path)
    assert status == {
        "database_exists": True,
        "current": 1,
        "latest": 2,
        "pending": True,
    }
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 1


def test_successful_scheduler_tick_updates_health_timestamp(monkeypatch):
    monkeypatch.setattr(server.podcasts, "list_due_feeds", lambda _idx: [])
    monkeypatch.setattr(server, "_get_index", lambda: object())
    monkeypatch.setattr(server.suite_service, "utc_now", lambda: "2026-09-04T16:30:00Z")
    monkeypatch.setattr(server, "_last_successful_tick_at", None)

    assert server._podcast_feed_scheduler_tick() == []
    assert server._last_successful_tick_at == "2026-09-04T16:30:00Z"


def test_watchdog_has_bounded_restart_policy():
    script = (server.HERE / "scripts" / "install-watchdog.ps1").read_text(
        encoding="utf-8"
    )
    assert "-RestartCount 3" in script
    assert "-RestartInterval (New-TimeSpan -Minutes 1)" in script
    assert "Register-ScheduledTask" in script
    assert "-Force" in script
