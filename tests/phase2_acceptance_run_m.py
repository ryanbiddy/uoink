"""Run M migration measurements. Opens only verified worktree-local duplicates.

Usage: python tests/phase2_acceptance_run_m.py --out tests/.acceptance-run-m/migration
The named source is hashed and copied as bytes; SQLite never opens it.
No source-document paths, live index, helper, or model are accessed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("C:/Users/hello/AppData/Local/AgentControlRoom/uoink-index-copy-2026-09-04-upgraded.db")
EXPECTED = "2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def snapshot(conn):
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    counts = {name: conn.execute('SELECT COUNT(*) FROM "' + name + '"').fetchone()[0]
              for name in tables}
    hashes = {}
    for name in ("yoinks", "citations", "clips"):
        digest = hashlib.sha256()
        rows = [json.dumps(list(row), ensure_ascii=False, separators=(",", ":"))
                for row in conn.execute('SELECT * FROM "' + name + '"')]
        for row in sorted(rows):
            digest.update(row.encode("utf-8") + b"\n")
        hashes[name] = digest.hexdigest()
    return {"schema": conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0],
            "counts": counts, "source_table_hashes": hashes,
            "items_with_clips": conn.execute("SELECT COUNT(DISTINCT video_id) FROM clips").fetchone()[0]}


def integrity(conn):
    checks = {"integrity_check": [r[0] for r in conn.execute("PRAGMA integrity_check")],
              "foreign_key_check": [list(r) for r in conn.execute("PRAGMA foreign_key_check")]}
    for name in ("yoinks_fts", "clips_fts"):
        conn.execute(f"INSERT INTO {name}({name},rank) VALUES('integrity-check',1)")
        checks[name] = "ok"
    conn.rollback()
    assert checks["integrity_check"] == ["ok"] and checks["foreign_key_check"] == []
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    out = parser.parse_args().out.resolve()
    assert out.is_relative_to(ROOT) and not out.exists(), "Use a new directory in this worktree"
    out.mkdir(parents=True)
    for key, child in (("LOCALAPPDATA", "local"), ("XDG_DATA_HOME", "data"),
                       ("UOINK_OUTPUT_DIR", "output"), ("TEMP", "temp"), ("TMP", "temp")):
        (out / child).mkdir(exist_ok=True)
        os.environ[key] = str(out / child)
    sys.path.insert(0, str(ROOT))
    import index

    started = time.perf_counter()
    report = {"candidate_sha": subprocess.check_output(["git", "rev-parse", "f53adaf"], text=True).strip(),
              "checkout_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "python": sys.version, "sqlite": sqlite3.sqlite_version,
              "source_date": "2026-09-04", "source_bytes": SOURCE.stat().st_size,
              "source_sha256_before": sha(SOURCE), "model_calls": 0}
    assert report["source_sha256_before"] == EXPECTED
    target = out / "populated.db"
    shutil.copyfile(SOURCE, target)
    assert sha(target) == EXPECTED
    conn = sqlite3.connect(target.as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    report["named_copy"] = snapshot(conn)
    conn.close()
    # The hash-named copy is schema 25. Prepare schema 26 in this worktree
    # using the candidate's <=26 migrations before measuring the 26->27 gate.
    actual = index._MIGRATIONS_DIR
    old = out / "migrations26"
    old.mkdir()
    for path in actual.glob("*.sql"):
        if int(path.name.split("_", 1)[0]) <= 26:
            shutil.copyfile(path, old / path.name)
    index._MIGRATIONS_DIR = old
    try:
        with index.Index.open(target) as idx:
            report["before"] = snapshot(idx._conn)
            report["prepared26_integrity"] = integrity(idx._conn)
    finally:
        index._MIGRATIONS_DIR = actual
    report["prepared26_sha256"] = sha(target)
    broken = out / "rollback.db"
    shutil.copyfile(target, broken)
    assert report["before"]["schema"] == 26
    with index.Index.open(target) as idx:
        report["after"] = snapshot(idx._conn)
        report["populated_integrity"] = integrity(idx._conn)
    report["post_upgrade_sha256"] = sha(target)
    with index.Index.open(target) as idx:
        report["repeat"] = snapshot(idx._conn)
        report["repeat_integrity"] = integrity(idx._conn)
    report["repeat_open_sha256"] = sha(target)
    assert report["after"] == report["repeat"]
    assert report["post_upgrade_sha256"] == report["repeat_open_sha256"]
    assert report["before"]["source_table_hashes"] == report["after"]["source_table_hashes"]
    assert report["after"]["schema"] == 27
    added = sorted(set(report["after"]["counts"]) - set(report["before"]["counts"]))
    report["added_tables"] = added
    assert len(added) == 16
    assert all(report["after"]["counts"][name] == (1 if name == "library_meta" else 0) for name in added)
    assert all(report["before"]["counts"][name] == count
               for name, count in report["after"]["counts"].items()
               if name in report["before"]["counts"] and name != "schema_version")

    # Empty schema 26 -> 27, then an injected failure on a second populated duplicate.
    index._MIGRATIONS_DIR = old
    fresh = out / "fresh.db"
    with index.Index.open(fresh) as idx:
        report["fresh_before_schema"] = idx.schema_version()
    index._MIGRATIONS_DIR = actual
    with index.Index.open(fresh) as idx:
        report["fresh_after"] = snapshot(idx._conn)
        report["fresh_integrity"] = integrity(idx._conn)
    report["fresh_upgrade_sha256"] = sha(fresh)
    with index.Index.open(fresh) as idx:
        assert snapshot(idx._conn) == report["fresh_after"]
    report["fresh_repeat_sha256"] = sha(fresh)
    assert report["fresh_upgrade_sha256"] == report["fresh_repeat_sha256"]
    assert report["fresh_before_schema"] == 26 and report["fresh_after"]["schema"] == 27
    for name in ("yoinks", "library_work", "item_shelves"):
        assert report["fresh_after"]["counts"][name] == 0

    sql = (actual / "0027_library_substrate.sql").read_text(encoding="utf-8")
    (old / "0027_library_substrate.sql").write_text(sql + "\nTHIS IS NOT SQL;\n", encoding="utf-8")
    index._MIGRATIONS_DIR = old
    try:
        index.Index.open(broken)
        raise AssertionError("Injected migration failure was not raised")
    except sqlite3.Error as exc:
        report["injected_failure"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        index._MIGRATIONS_DIR = actual
    conn = sqlite3.connect(broken.as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    report["after_rollback"] = snapshot(conn)
    conn.close()
    assert report["after_rollback"] == report["before"]
    with index.Index.open(broken) as idx:
        report["rollback_repaired_schema"] = idx.schema_version()
        report["rollback_repaired_integrity"] = integrity(idx._conn)
        assert snapshot(idx._conn)["source_table_hashes"] == report["before"]["source_table_hashes"]
    report["source_sha256_after"] = sha(SOURCE)
    assert report["source_sha256_after"] == EXPECTED
    # Stage the real installer inventory; -I excludes this source checkout.
    sys.path.insert(0, str(ROOT / "tests"))
    from test_installer_files_complete import staged_sources
    stage = out / "installed"
    stage.mkdir()
    for relative in staged_sources():
        src, dst = ROOT / relative, stage / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copyfile(src, dst)
    shutil.copyfile(ROOT / "VERSION", stage / "VERSION")
    smoke = stage / "phase2_smoke.py"
    smoke.write_text('''import json, pathlib, site, sys
stage = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(stage))
site.addsitedir(site.getusersitepackages())
assert pathlib.Path(sys.argv[1]).resolve() not in [pathlib.Path(p).resolve() for p in sys.path]
import index, library_work, library_cards, provenance, clips, server, uoink_mcp_tools, uoink_mcp
modules = (index, library_work, library_cards, provenance, clips, server, uoink_mcp_tools, uoink_mcp)
for module in modules:
    assert pathlib.Path(module.__file__).is_relative_to(stage)
with index.Index.open(stage / "phase2-fixture.db") as idx:
    svc = idx.library_service()
    result = svc.list_work(library_work.RequestContext(authenticated=True), {})
    assert idx.schema_version() == 27 and result["ok"]
    assert result["contract_version"] == "phase2-v1.2-2026-09-04"
    assert not svc.librarian_apply_enabled
print("RUN_M_INSTALLED=" + json.dumps({"modules": [m.__name__ for m in modules],
    "schema": 27, "contract_version": result["contract_version"], "apply_enabled": False,
    "checkout_on_sys_path": False}))
''', encoding="utf-8")
    installed = subprocess.run([sys.executable, "-I", str(smoke), str(ROOT)], cwd=stage,
                               capture_output=True, text=True, timeout=60)
    (out / "installed.log").write_text(installed.stdout + installed.stderr, encoding="utf-8")
    assert installed.returncode == 0, installed.stdout + installed.stderr
    report["installed_imports"] = json.loads(next(
        line.removeprefix("RUN_M_INSTALLED=") for line in installed.stdout.splitlines()
        if line.startswith("RUN_M_INSTALLED=")))
    report["elapsed_seconds"] = round(time.perf_counter() - started, 6)
    (out / "measurement.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
