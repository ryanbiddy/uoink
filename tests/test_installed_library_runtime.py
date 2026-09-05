"""Installed-tree dependency smoke; the subprocess cannot import this checkout."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

from test_installer_files_complete import ROOT, staged_sources


def test_installed_tree_capture_upgrade_search_rebuild(tmp_path):
    stage = tmp_path / "installed"
    stage.mkdir()
    for relative in staged_sources():
        source = ROOT / relative
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copyfile(source, target)
    shutil.copyfile(ROOT / "VERSION", stage / "VERSION")
    smoke = stage / "smoke.py"
    smoke.write_text('''
import json, os, pathlib, shutil, site, sys
stage = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(stage))
# Isolated mode disables user-site packages; allow installed third-party
# dependencies explicitly while continuing to exclude the source checkout.
user_site = site.getusersitepackages()
if user_site not in sys.path:
    site.addsitedir(user_site)
assert pathlib.Path(sys.argv[1]).resolve() not in [pathlib.Path(p).resolve() for p in sys.path]
import index, provenance, clips, library_cards, uoink_mcp_tools
for module in (index, provenance, clips, library_cards, uoink_mcp_tools):
    assert pathlib.Path(module.__file__).is_relative_to(stage)
old = stage / "old-migrations"
old.mkdir()
current = index._MIGRATIONS_DIR
for path in current.glob("*.sql"):
    if int(path.name.split("_", 1)[0]) <= 23:
        shutil.copyfile(path, old / path.name)
index._MIGRATIONS_DIR = old
path = stage / "upgrade.db"
with index.Index.open(path) as idx:
    idx.upsert_yoink(dict(video_id="fixture", slug="fixture", title="Capture",
        channel="Test", topic="Test", yoinked_at="2026-09-04", corpus_path="",
        sidecar_path="", platform="x", metadata_json=json.dumps({"source_type":"x_article"})))
    idx._conn.execute("INSERT INTO citations(video_id, kind, seq, timestamp_start, timestamp_end, text) VALUES('fixture', 'transcript_chunk', 0, 0, 1041, ?)",
        ("installed sentinel " * 200,))
    idx._conn.execute("UPDATE yoinks SET source_type=NULL")
    idx._conn.commit()
index._MIGRATIONS_DIR = current
with index.Index.open(path) as idx:
    assert idx.get_yoink("fixture")["source_type"] == "x_article"
    assert idx.search_clips("installed sentinel")[0]["timing"] == "coarse"
    assert idx.rebuild_clips()["clip_count"] > 1
    card = library_cards.build_card(idx.get_yoink("fixture"), idx.get_clips("fixture"), profile="librarian")
    assert card["evidence_kind"] == "timed_clip"
    assert len(library_cards.card_text(card).encode()) <= 8192
import server, uoink_mcp
assert pathlib.Path(server.__file__).is_relative_to(stage)
print("installed runtime: imports, capture fixture, populated upgrade, search, card, rebuild passed")
''', encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": "", "LOCALAPPDATA": str(stage / "data"),
           "XDG_DATA_HOME": str(stage / "data"), "UOINK_OUTPUT_DIR": str(stage / "output")}
    (stage / "output").mkdir()
    result = subprocess.run([sys.executable, "-I", str(smoke), str(ROOT)],
                            cwd=stage, env=env, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "installed runtime:" in result.stdout
