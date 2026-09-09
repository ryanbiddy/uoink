"""Prepare the frozen AW client fixture; does not start a client or model.

Run only after the client rerun brief's implementation prerequisites are met.
The source is the explicitly authorized archived index copy, read as bytes.
All database paths are rebound before importing or opening the staged runtime.
Expected evidence comes from stored rows and canonical pure construction, never
from LibraryReader or an MCP response. Raw private output stays in the fixture.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import site
import sqlite3
import subprocess
import sys


SOURCE_HASH = "2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc"
SOURCE_BYTES = 71733248
ITEMS = ("WgPbbWmnXJ8", "x_27061a15409")
ABSOLUTE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/)")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def rebind(conn, fixture):
    counts = {"items": 0, "embedded_json_paths": 0}
    for (vid,) in conn.execute("SELECT video_id FROM yoinks").fetchall():
        folder = fixture / "items" / sha(vid.encode())
        conn.execute("UPDATE yoinks SET corpus_path=?,sidecar_path=? WHERE video_id=?",
                     (str(folder / "corpus.md"), str(folder / "corpus.json"), vid))
        counts["items"] += 1
    columns = {
        "citations": ("file_path",),
        "podcast_episodes": ("audio_local_path", "transcript_local_path"),
    }
    for table, names in columns.items():
        for name in names:
            counts[f"{table}.{name}"] = conn.execute(
                f'SELECT count(*) FROM "{table}" WHERE "{name}" IS NOT NULL').fetchone()[0]
            conn.execute(f'UPDATE "{table}" SET "{name}"=? WHERE "{name}" IS NOT NULL',
                         (str(fixture / "unavailable" / name),))

    def transform(value):
        if isinstance(value, dict):
            return {key: transform(child) for key, child in value.items()}
        if isinstance(value, list):
            return [transform(child) for child in value]
        if isinstance(value, str) and ABSOLUTE.match(value):
            counts["embedded_json_paths"] += 1
            return str(fixture / "unavailable" / sha(value.encode()))
        return value

    def ident(value):
        return '"' + value.replace('"', '""') + '"'

    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND sql NOT LIKE '%VIRTUAL TABLE%'").fetchall()
    for (table,) in tables:
        names = [r[1] for r in conn.execute(f"PRAGMA table_info({ident(table)})")]
        for name in [n for n in names if "json" in n]:
            rows = conn.execute(f"SELECT rowid,{ident(name)} FROM {ident(table)} WHERE {ident(name)} IS NOT NULL").fetchall()
            for rowid, raw in rows:
                try:
                    before = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                after = transform(before)
                if before != after:
                    conn.execute(f"UPDATE {ident(table)} SET {ident(name)}=? WHERE rowid=?",
                                 (json.dumps(after, ensure_ascii=False), rowid))
    conn.commit()
    for table, names in {**columns, "yoinks": ("corpus_path", "sidecar_path")}.items():
        for name in names:
            for (value,) in conn.execute(f'SELECT DISTINCT "{name}" FROM "{table}" WHERE "{name}" IS NOT NULL'):
                if not Path(value).resolve().is_relative_to(fixture):
                    raise ValueError("unrebound path in disposable database")
    return counts


def expected_item(idx, vid):
    import library_cards as cards
    import library_resources as resources
    from clips import timing_kind

    # Stored rows and pure card/renderer operations only. No reader retrieval.
    item = idx.get_yoink(vid)
    clips = idx.get_clips(vid)
    corpus = Path(item["corpus_path"]).read_bytes()
    head = corpus[:cards.CORPUS_READ_BYTES].decode("utf-8", "replace")
    card = cards.build_card(item, clips, corpus_text=head, profile="librarian")
    card_text = cards.card_text(card)
    chosen = card["excerpts"][0]
    evidence = [{"start": c.get("start"), "end": c.get("end"), "text": c.get("text") or "",
                 "deep_link": cards._web_link(c.get("source_deep_link")),
                 "seq": c.get("seq", i), "timing": timing_kind(c)}
                for i, c in enumerate(clips) if cards._string(c.get("text"))]
    evidence.sort(key=lambda row: (row["seq"], row["start"] or 0))
    by_id = {cards._hash([vid, row]): row for row in evidence}
    if chosen["evidence_kind"] == "timed_clip":
        resolved = by_id[chosen["excerpt_id"]]
    else:
        prose = cards.opening_prose(head)
        assert chosen["excerpt_id"] == cards._hash([vid, "opening_prose", prose])
        resolved = {"text": prose, "start": None, "end": None,
                    "deep_link": card.get("url"), "timing": "not_timed"}
    full = resolved["text"]
    bounded = full[:resources.LIMITS["max_excerpt_codepoints"]]
    body = {
        "schema_version": resources.SCHEMA_VERSION,
        "contract_version": resources.CONTRACT_VERSION,
        "render_version": resources.RENDER_VERSION,
        "document": "excerpt",
        "identity": {"item_id": vid, "slug": card.get("slug"), "excerpt_id": chosen["excerpt_id"]},
        "requested_revision": {"source_revision": card["source_revision"]},
        "bindings": {"card_hash": card["card_hash"], "selection": card["selection_version"]},
        "evidence_kind": chosen["evidence_kind"], "timing": resolved["timing"],
        "start": resolved["start"], "end": resolved["end"], "text": bounded,
        "truncated": len(bounded) < len(full), "original_length_codepoints": len(full),
        "returned_codepoints": len(bounded),
        "links": {"source": resources.safe_url(card.get("url")), "deep_link": resources.safe_url(resolved["deep_link"])},
        "labels": {"title": resources.label(card.get("title")), "channel": resources.label(card.get("channel"))},
        "continuation": None, "card_uri": resources.card_uri(vid, card),
    }
    rendered = resources.render_document(body)
    return {
        "item_id": vid, "stored_item": item, "stored_clips": clips,
        "post_migration_clip_count": len(clips), "corpus_sha256": sha(corpus),
        "card": card, "card_uri": resources.card_uri(vid, card),
        "card_text": card_text, "card_text_sha256": sha(card_text.encode()),
        "excerpt_uri": resources.excerpt_uri(vid, card["source_revision"], chosen["excerpt_id"]),
        "full_stored_excerpt": full, "full_stored_excerpt_sha256": sha(full.encode()),
        "excerpt_body": body, "excerpt_text": rendered, "excerpt_text_sha256": sha(rendered.encode()),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--fixture-root", type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    fixture = args.fixture_root.resolve()
    if not fixture.is_relative_to(repo / "_scratch") or fixture.exists():
        parser.error("fixture must be a fresh directory under this checkout's _scratch")
    if os.environ.get("ANTHROPIC_API_KEY"):
        parser.error("API key must be absent")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    if head != args.candidate:
        parser.error("candidate must be the exact current committed SHA")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo, text=True).strip():
        parser.error("tracked source changes must be committed before freezing")
    original_local = Path(os.environ["LOCALAPPDATA"])
    source = original_local / "AgentControlRoom" / "uoink-index-copy-2026-09-04-upgraded.db"
    original = source.read_bytes()
    if len(original) != SOURCE_BYTES or sha(original) != SOURCE_HASH:
        raise ValueError("authorized archived index copy changed")
    packages = Path(site.getusersitepackages())
    fixture.mkdir(parents=True)
    profile = fixture / "profile"
    data = profile / "Uoink"
    data.mkdir(parents=True)
    (fixture / "records").mkdir()
    (fixture / "client").mkdir()
    database = data / "index.db"
    database.write_bytes(original)
    conn = sqlite3.connect(database)
    counts = rebind(conn, fixture)
    conn.close()
    old_manifest = json.loads((repo / "docs/library/proof/aw-2026-09-08/manifest.json").read_text(encoding="utf-8"))
    copies = {}
    for vid in ITEMS:
        entry = old_manifest["items"][vid]
        target = fixture / "items" / sha(vid.encode())
        target.mkdir(parents=True)
        copies[vid] = {}
        for field, name in (("corpus_path", "corpus.md"), ("sidecar_path", "corpus.json")):
            # Follow only the existing authorized scratch copy. Never original_dir.
            source_path = Path(entry[field]).resolve(strict=True)
            if not source_path.is_relative_to(repo / "_scratch" / "aw" / "corpus"):
                raise ValueError("source artifact is outside the retained scratch copy")
            raw = source_path.read_bytes()
            if sha(raw) != entry["files"][source_path.name]:
                raise ValueError("retained source artifact changed")
            copied = raw
            if field == "sidecar_path":
                def rewrite_sidecar(value):
                    if isinstance(value, dict):
                        return {key: rewrite_sidecar(child) for key, child in value.items()}
                    if isinstance(value, list):
                        return [rewrite_sidecar(child) for child in value]
                    if isinstance(value, str) and ABSOLUTE.match(value):
                        return str(fixture / "unavailable" / sha(value.encode()))
                    return value
                parsed = json.loads(raw)
                rewritten = rewrite_sidecar(parsed)
                if rewritten != parsed:
                    copied = (json.dumps(rewritten, ensure_ascii=False, indent=2) + "\n").encode()
            (target / name).write_bytes(copied)
            copies[vid][name] = {"source": str(source_path), "source_sha256": sha(raw),
                                 "copied_sha256": sha(copied), "source_bytes": len(raw), "copied_bytes": len(copied)}
    # Explicit safe defaults; no inherited application/client configuration.
    save(data / "settings.json", {"librarian_apply_enabled": False, "library_mirror_enabled": False})
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    for key in ("LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "XDG_DATA_HOME"):
        env[key] = str(profile)
    env.update(UOINK_OUTPUT_DIR=str(fixture / "output"), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    (fixture / "output").mkdir()
    stage = fixture / "stage"
    stage_result = subprocess.run(["pwsh", "-NoProfile", "-File", str(repo / "build.ps1"),
                                   "-StageSourceOnly", "-SourceStagePath", str(stage)],
                                  cwd=repo, env=env, capture_output=True, text=True, timeout=60)
    (fixture / "stage.log").write_text(stage_result.stdout + stage_result.stderr, encoding="utf-8")
    if stage_result.returncode or not (stage / "library_mirror_vault_io.py").is_file():
        raise RuntimeError("source staging failed or omitted the isolated vault writer")
    guard = fixture / "guard"
    guard.mkdir()
    # The model is a separate client. These guards govern the stdio data child.
    guard_code = '''import os,sys
from pathlib import Path
def audit(event,args):
    if event in ('open','sqlite3.connect') and isinstance(args[0],(str,bytes,os.PathLike)):
        value=os.fsdecode(args[0]).replace('\\\\','/').lower()
        if os.environ['AW_FORBIDDEN_INDEX'].replace('\\\\','/').lower() in value:
            raise PermissionError('AW live index forbidden')
    if event=='sqlite3.connect' and isinstance(args[0],str) and args[0]!=':memory:':
        if not Path(args[0]).resolve().is_relative_to(Path(os.environ['AW_FIXTURE_ROOT'])):
            raise PermissionError('AW database outside fixture')
    if event in ('socket.connect','socket.bind','socket.sendto','socket.getaddrinfo'):
        address=args[:2] if event=='socket.getaddrinfo' else args[1]
        if isinstance(address,tuple) and (str(address[1])=='5179' or address[0] not in ('127.0.0.1','::1','localhost','')):
            raise PermissionError('AW external network or resident port forbidden')
    if event=='subprocess.Popen':
        command=args[1]
        first=command[0] if isinstance(command,(tuple,list)) else str(command).split()[0]
        if Path(str(first)).stem.lower() in ('claude','codex','grok','gemini','yt-dlp','ffmpeg','curl'):
            raise PermissionError('AW execution/fetch sentinel')
sys.addaudithook(audit)
'''
    (guard / "sitecustomize.py").write_text(guard_code, encoding="utf-8")
    env.update(AW_FIXTURE_ROOT=str(fixture), AW_FORBIDDEN_INDEX=str(original_local / "Uoink" / "index.db"),
               PYTHONPATH=os.pathsep.join(map(str, [guard, stage, packages, packages / "win32", packages / "win32/lib", packages / "pythonwin"])))
    os.environ.update(env)
    sys.path[:0] = [str(guard), str(stage)]
    exec(compile(guard_code, str(guard / "sitecustomize.py"), "exec"), {})
    import index
    idx = index.Index.open(database)
    try:
        expected = {vid: expected_item(idx, vid) for vid in ITEMS}
        assert idx._conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert idx._conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        idx.close()
    save(fixture / "expected.json", expected)
    child_env_keys = ("LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "XDG_DATA_HOME", "UOINK_OUTPUT_DIR",
                      "PYTHONDONTWRITEBYTECODE", "PYTHONUTF8", "PYTHONPATH", "AW_FIXTURE_ROOT", "AW_FORBIDDEN_INDEX")
    recorder = fixture / "stdio_tap.py"
    shutil.copyfile(Path(__file__).with_name("stdio_tap.py"), recorder)
    config = {"mcpServers": {"uoink": {
        "type": "stdio", "command": sys.executable,
        "args": [str(recorder), "--fixture-root", str(fixture), "--record-dir", str(fixture / "records" / "stdio"),
                 "--cwd", str(stage), "--", sys.executable, "-B", str(stage / "uoink_mcp.py")],
        "env": {key: env[key] for key in child_env_keys},
    }}}
    save(fixture / "mcp.json", config)
    stage_hashes = {str(p.relative_to(stage)).replace('\\', '/'): sha(p.read_bytes())
                    for p in sorted(stage.rglob("*")) if p.is_file()}
    if sha(source.read_bytes()) != SOURCE_HASH:
        raise ValueError("authorized source changed during preparation")
    receipt = {
        "candidate": head, "prepared_at": datetime.now(timezone.utc).isoformat(),
        "status": "fixture prepared; client not run", "source_copy_sha256_before_after": SOURCE_HASH,
        "source_copy_bytes": SOURCE_BYTES, "rebound": counts, "artifacts": copies,
        "database_sha256_before_client": sha(database.read_bytes()),
        "expected_sha256": sha((fixture / "expected.json").read_bytes()),
        "mcp_config_sha256": sha((fixture / "mcp.json").read_bytes()),
        "stage_files": stage_hashes, "interpreter": sys.executable, "python": sys.version,
        "expected_method": "stored post-migration item/clip rows plus pure canonical card and document construction; no LibraryReader or protocol response",
        "limits": ["No client/model invocation", "Only two retained corpus/sidecar pairs copied; other rebound files are unavailable",
                   "Post-migration clip count is measured in expected.json; no historical count reused"],
    }
    save(fixture / "preparation.json", receipt)
    print(json.dumps({"fixture": str(fixture), "candidate": head, "items": counts["items"],
                      "expected_sha256": receipt["expected_sha256"], "status": receipt["status"]}))


if __name__ == "__main__":
    main()
