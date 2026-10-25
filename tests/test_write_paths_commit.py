"""Write paths that used to leave idx._conn in a transaction must commit.

Each case calls one leaked public (or helper) writer with valid inputs, then
checks three things: the shared connection is not in a transaction, a second
connection can take BEGIN IMMEDIATE, and the row is still there after close
and reopen. Remove cases assert the row is gone. Zero-row DML and an unknown
writing-draft id must leave no open transaction either.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

import channels
import claims
import index as index_mod
import mobile_playlists
import page_extractor
import scripts
import workspaces
import writing_studio


def _open(path):
    idx, _recovered = index_mod.Index.open_or_recover(path)
    return idx


def _assert_immediate(path):
    outsider = sqlite3.connect(path, timeout=0.5)
    try:
        outsider.execute("BEGIN IMMEDIATE")
        outsider.rollback()
    finally:
        outsider.close()


def _one(idx, sql, params=()):
    return idx._conn.execute(sql, params).fetchone()


def _seed_yoink(idx, video_id, channel="TestChannel"):
    idx.upsert_yoink({
        "video_id": video_id,
        "slug": video_id,
        "channel": channel,
        "title": "Commit test",
        "topic": "AI and ML",
        "hook_type": "demo",
        "yoinked_at": "2026-07-01T10:00:00",
        "corpus_path": "",
        "sidecar_path": "",
        "source_type": "youtube",
    }, content="body")


def _write_extract_claims(idx):
    result = claims.extract_claims(
        idx, "vid-claims", claims=[{"claim_text": "The sky is blue"}])
    claim_id = result["inserted_ids"][0]

    def check(reopened):
        row = _one(reopened, "SELECT claim_text FROM claims WHERE id=?", (claim_id,))
        assert row["claim_text"] == "The sky is blue"
    return check


def _write_verify_claim(idx):
    claim_id = claims.extract_claims(
        idx, "vid-verify", claims=[{"claim_text": "Water boils"}])["inserted_ids"][0]
    verified = claims.verify_claim(idx, claim_id, evidence=[{
        "source_url": "https://example.test/src",
        "quote": "it boils",
        "alignment_signal": "supports",
    }])
    assert verified["ok"] is True

    def check(reopened):
        row = _one(reopened, "SELECT status FROM claims WHERE id=?", (claim_id,))
        assert row["status"] == "verified"
    return check


def _write_mark_not_attempted(idx):
    claim_id = claims.extract_claims(
        idx, "vid-skip", claims=[{"claim_text": "Skip me"}])["inserted_ids"][0]
    assert claims.mark_not_attempted(idx, claim_id) is True

    def check(reopened):
        row = _one(reopened, "SELECT status FROM claims WHERE id=?", (claim_id,))
        assert row["status"] == "not-attempted"
    return check


def _write_add_style_anchor(idx):
    row = writing_studio.add_style_anchor(
        idx, name="Txn voice", source_type="text", source_value="plain prose")
    anchor_id = row["id"]

    def check(reopened):
        got = _one(reopened, "SELECT name, active FROM style_anchors WHERE id=?", (anchor_id,))
        assert got["name"] == "Txn voice" and got["active"] == 1
    return check


def _write_update_style_anchor(idx):
    anchor_id = writing_studio.add_style_anchor(
        idx, name="Before", source_type="text", source_value="prose")["id"]
    updated = writing_studio.update_style_anchor(idx, anchor_id, name="After")
    assert updated["name"] == "After"

    def check(reopened):
        got = _one(reopened, "SELECT name FROM style_anchors WHERE id=?", (anchor_id,))
        assert got["name"] == "After"
    return check


def _write_remove_style_anchor(idx):
    anchor_id = writing_studio.add_style_anchor(
        idx, name="Gone", source_type="text", source_value="prose")["id"]
    assert writing_studio.remove_style_anchor(idx, anchor_id) is True

    def check(reopened):
        assert _one(reopened, "SELECT id FROM style_anchors WHERE id=?", (anchor_id,)) is None
    return check


def _write_persist_piece(idx):
    piece = writing_studio.persist_piece(
        idx, yoink_id=None, kind="tweet",
        body="Ship the note via @creator",
        source_credit_line="via @creator")
    piece_id = piece["id"]

    def check(reopened):
        row = _one(reopened, "SELECT body FROM writing_pieces WHERE id=?", (piece_id,))
        assert row["body"] == "Ship the note via @creator"
    return check


def _write_create_workspace(idx):
    ws = workspaces.create_workspace(idx, topic="txn topic", format="vlog")
    wid = ws["id"]

    def check(reopened):
        row = _one(reopened, "SELECT topic, format FROM workspaces WHERE id=?", (wid,))
        assert row["topic"] == "txn topic" and row["format"] == "vlog"
    return check


def _write_delete_workspace(idx):
    wid = workspaces.create_workspace(idx, topic="gone")["id"]
    assert workspaces.delete_workspace(idx, wid) is True

    def check(reopened):
        assert _one(reopened, "SELECT id FROM workspaces WHERE id=?", (wid,)) is None
    return check


def _write_save_assembled(idx):
    wid = workspaces.create_workspace(idx, topic="asm")["id"]
    workspaces._save_assembled(idx, wid, ["va", "vb"])

    def check(reopened):
        row = _one(reopened, "SELECT assembled_yoinks FROM workspaces WHERE id=?", (wid,))
        assert json.loads(row["assembled_yoinks"]) == ["va", "vb"]
    return check


def _write_log_critique(idx):
    wid = workspaces.create_workspace(idx, topic="critique")["id"]
    row_id = workspaces.log_critique(
        idx, wid, draft_text="my draft", findings={"hook_strength": "ok"})

    def check(reopened):
        row = _one(
            reopened,
            "SELECT draft_text, findings FROM workspace_critique_log WHERE id=?",
            (row_id,))
        assert row["draft_text"] == "my draft"
        assert json.loads(row["findings"])["hook_strength"] == "ok"
    return check


def _write_add_channel(idx):
    channels.add_channel(idx, "txnhandle", name="Txn Channel")

    def check(reopened):
        row = _one(
            reopened,
            "SELECT name FROM user_channels WHERE lower(handle)=lower(?)",
            ("txnhandle",))
        assert row["name"] == "Txn Channel"
    return check


def _write_remove_channel(idx):
    channels.add_channel(idx, "rmhandle", name="Rm")
    assert channels.remove_channel(idx, "rmhandle") is True

    def check(reopened):
        assert _one(
            reopened,
            "SELECT handle FROM user_channels WHERE lower(handle)=lower(?)",
            ("rmhandle",)) is None
    return check


def _write_set_verified(idx):
    channels.add_channel(idx, "verhandle", name="Before")
    channels.set_verified(idx, "verhandle", channel_id="UCtxn", name="After")

    def check(reopened):
        row = _one(
            reopened,
            "SELECT name, channel_id, verified_at FROM user_channels "
            "WHERE lower(handle)=lower(?)",
            ("verhandle",))
        assert row["name"] == "After"
        assert row["channel_id"] == "UCtxn"
        assert row["verified_at"]
    return check


def _write_tag_if_self(idx):
    _seed_yoink(idx, "vid-self", channel="MineShow")
    channels.add_channel(idx, "mineshow", name="MineShow")
    assert channels.tag_if_self(idx, "vid-self", "MineShow") is True

    def check(reopened):
        row = _one(
            reopened,
            "SELECT tag, source FROM yoink_tags WHERE video_id=? AND tag='is_self'",
            ("vid-self",))
        assert row["tag"] == "is_self" and row["source"] == "auto"
    return check


def _write_add_allowed(idx):
    page_extractor.add_allowed(idx, "Txn.Example")
    again = page_extractor.add_allowed(idx, "txn.example")
    assert again["url_pattern"] == "txn.example"

    def check(reopened):
        row = _one(
            reopened,
            "SELECT url_pattern FROM allowed_sites WHERE url_pattern=?",
            ("txn.example",))
        assert row["url_pattern"] == "txn.example"
    return check


def _write_remove_allowed(idx):
    page_extractor.add_allowed(idx, "remove.example")
    assert page_extractor.remove_allowed(idx, "remove.example") is True

    def check(reopened):
        assert _one(
            reopened,
            "SELECT id FROM allowed_sites WHERE url_pattern=?",
            ("remove.example",)) is None
    return check


def _write_persist_script(idx):
    wid = workspaces.create_workspace(idx, topic="script", format="vlog")["id"]
    saved = scripts.persist_script(idx, wid, script={
        "hook": "Open strong",
        "beats": [{"label": "open", "content": "hi"}],
        "format": "vlog",
    })
    script_id = saved["id"]

    def check(reopened):
        row = _one(reopened, "SELECT hook FROM scripts WHERE id=?", (script_id,))
        assert row["hook"] == "Open strong"
    return check


def _write_derive_shot_list(idx):
    wid = workspaces.create_workspace(idx, topic="shots", format="vlog")["id"]
    script_id = scripts.persist_script(idx, wid, script={
        "hook": "Open strong",
        "beats": [{"label": "open", "content": "hi"}],
        "format": "vlog",
    })["id"]
    derived = scripts.derive_shot_list(idx, script_id)
    assert derived["ok"] is True and len(derived["shot_list"]) == 1

    def check(reopened):
        row = _one(reopened, "SELECT shot_list FROM scripts WHERE id=?", (script_id,))
        shots = json.loads(row["shot_list"])
        assert len(shots) == 1 and shots[0]["label"] == "open"
    return check


def _write_record_poll_failure(idx):
    with idx.write_transaction() as conn:
        cur = conn.execute(
            "INSERT INTO monitored_playlists (playlist_url, added_at) VALUES (?, ?)",
            ("https://www.youtube.com/playlist?list=PLtxncommit",
             "2026-07-01T00:00:00Z"))
        playlist_id = int(cur.lastrowid)
    mobile_playlists._record_poll_failure(idx, playlist_id, "fetch blew up")

    def check(reopened):
        row = _one(
            reopened,
            "SELECT error_count, last_error FROM monitored_playlists WHERE id=?",
            (playlist_id,))
        assert row["error_count"] == 1
        assert row["last_error"] == "fetch blew up"
    return check


def _write_add_tags(idx):
    _seed_yoink(idx, "vid-tags")
    assert idx.add_tags("vid-tags", ["MCP", "MCP", "agents"]) == 2
    assert idx.add_tags("vid-tags", ["mcp"]) == 0

    def check(reopened):
        rows = reopened._conn.execute(
            "SELECT tag FROM yoink_tags WHERE video_id=? ORDER BY tag",
            ("vid-tags",)).fetchall()
        assert [r["tag"] for r in rows] == ["agents", "mcp"]
    return check


def _write_save_writing_draft(idx):
    saved = idx.save_writing_draft(
        yoink_id="vid-draft", kind="tweet", title="t", body="first body")
    updated = idx.save_writing_draft(
        draft_id=saved["id"], title="t2", body="second body")
    assert updated["body"] == "second body"
    draft_id = saved["id"]

    def check(reopened):
        row = _one(
            reopened,
            "SELECT title, body FROM writing_drafts WHERE id=?",
            (draft_id,))
        assert row["title"] == "t2" and row["body"] == "second body"
    return check


WRITES = [
    _write_extract_claims,
    _write_verify_claim,
    _write_mark_not_attempted,
    _write_add_style_anchor,
    _write_update_style_anchor,
    _write_remove_style_anchor,
    _write_persist_piece,
    _write_create_workspace,
    _write_delete_workspace,
    _write_save_assembled,
    _write_log_critique,
    _write_add_channel,
    _write_remove_channel,
    _write_set_verified,
    _write_tag_if_self,
    _write_add_allowed,
    _write_remove_allowed,
    _write_persist_script,
    _write_derive_shot_list,
    _write_record_poll_failure,
    _write_add_tags,
    _write_save_writing_draft,
]

ZERO_ROW = [
    ("mark_not_attempted", lambda idx: claims.mark_not_attempted(idx, 424242)),
    ("delete_workspace", lambda idx: workspaces.delete_workspace(idx, "ws_missing")),
    ("remove_channel", lambda idx: channels.remove_channel(idx, "no-such-handle")),
    ("remove_style_anchor", lambda idx: writing_studio.remove_style_anchor(idx, 424242)),
    ("remove_allowed", lambda idx: page_extractor.remove_allowed(idx, "missing.example")),
]


@pytest.mark.parametrize(
    "write", WRITES, ids=[fn.__name__.removeprefix("_write_") for fn in WRITES])
def test_write_path_commits(tmp_path, write):
    path = tmp_path / "index.db"
    idx = _open(path)
    try:
        check = write(idx)
        assert idx._conn.in_transaction is False
        _assert_immediate(path)
    finally:
        idx.close()
    reopened = _open(path)
    try:
        check(reopened)
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "call", [fn for _name, fn in ZERO_ROW], ids=[name for name, _fn in ZERO_ROW])
def test_zero_row_dml_closes_transaction(tmp_path, call):
    path = tmp_path / "index.db"
    idx = _open(path)
    try:
        assert call(idx) is False
        assert idx._conn.in_transaction is False
        _assert_immediate(path)
    finally:
        idx.close()


def test_save_writing_draft_unknown_id_rolls_back(tmp_path):
    path = tmp_path / "index.db"
    idx = _open(path)
    try:
        saved = idx.save_writing_draft(body="kept")
        with pytest.raises(ValueError, match="not found"):
            idx.save_writing_draft(draft_id=saved["id"] + 1, body="nope")
        assert idx._conn.in_transaction is False
        _assert_immediate(path)
        draft_id = saved["id"]
    finally:
        idx.close()
    reopened = _open(path)
    try:
        row = _one(reopened, "SELECT body FROM writing_drafts WHERE id=?", (draft_id,))
        assert row["body"] == "kept"
        assert _one(reopened, "SELECT COUNT(*) AS n FROM writing_drafts")["n"] == 1
    finally:
        reopened.close()


def test_upsert_yoink_self_tag_joins_caller_transaction(tmp_path):
    """tag_if_self from upsert_yoink must join that write, not start its own."""
    path = tmp_path / "index.db"
    idx = _open(path)
    try:
        channels.add_channel(idx, "mineshow", name="MineShow")
        idx.upsert_yoink({
            "video_id": "vid-join",
            "slug": "vid-join",
            "channel": "MineShow",
            "title": "Join test",
            "yoinked_at": "2026-07-01T10:00:00",
            "corpus_path": "",
            "sidecar_path": "",
            "source_type": "youtube",
        }, content="body")
        assert idx._conn.in_transaction is False
        _assert_immediate(path)
    finally:
        idx.close()
    reopened = _open(path)
    try:
        yoink = _one(reopened, "SELECT video_id FROM yoinks WHERE video_id=?", ("vid-join",))
        tag = _one(
            reopened,
            "SELECT source FROM yoink_tags WHERE video_id=? AND tag='is_self'",
            ("vid-join",))
        assert yoink is not None
        assert tag["source"] == "auto"
    finally:
        reopened.close()
