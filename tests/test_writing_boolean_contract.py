from __future__ import annotations

import pytest

import index as index_mod
import server
import uoink_mcp_tools
import writing_studio


@pytest.fixture
def writing_index(tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(
        server,
        "_read_settings",
        lambda: {"voice_dna_warnings_enabled": True},
    )
    uoink_mcp_tools.bind_backend(server)
    try:
        yield idx
    finally:
        idx.close()


def _payload(field: str) -> dict:
    return {
        "kind": "tweet",
        "body": "A grounded draft.\n\nvia Uoink corpus",
        "source_credit_line": "via Uoink corpus",
        field: "false",
    }


@pytest.mark.parametrize(
    "field",
    ("suppress_credit", "skip_voice_dna_this_time"),
)
def test_mcp_writing_rejects_string_booleans_without_persistence(
    writing_index, field
):
    result = uoink_mcp_tools.write_tweet(_payload(field))

    assert result["ok"] is False
    assert f"{field} must be a boolean" in result["error"]
    assert writing_index._conn.execute(
        "SELECT COUNT(*) FROM writing_pieces"
    ).fetchone()[0] == 0


@pytest.mark.parametrize(
    "field",
    ("suppress_credit", "skip_voice_dna_this_time"),
)
def test_http_writing_rejects_string_booleans_without_persistence(
    writing_index, field
):
    status, result = server.Handler._writing_two_phase(
        None,
        _payload(field),
        kind=writing_studio.KIND_TWEET,
    )

    assert status == 400
    assert f"{field} must be a boolean" in result["error"]
    assert writing_index._conn.execute(
        "SELECT COUNT(*) FROM writing_pieces"
    ).fetchone()[0] == 0


@pytest.mark.parametrize(
    "field",
    ("suppress_credit", "skip_voice_dna_this_time"),
)
def test_persistence_boundary_rejects_string_booleans(
    writing_index, field
):
    options = {field: "false"}

    with pytest.raises(ValueError, match=f"{field} must be a boolean"):
        writing_studio.persist_piece(
            writing_index,
            yoink_id=None,
            kind=writing_studio.KIND_TWEET,
            body="A grounded draft.\n\nvia Uoink corpus",
            source_credit_line="via Uoink corpus",
            **options,
        )

    assert writing_index._conn.execute(
        "SELECT COUNT(*) FROM writing_pieces"
    ).fetchone()[0] == 0


def test_false_boolean_keeps_voice_scan_enabled(
    writing_index, monkeypatch
):
    monkeypatch.setattr(
        writing_studio.voice_dna,
        "scan",
        lambda _body: [{"severity": "warn", "message": "measured"}],
    )

    result = writing_studio.persist_piece(
        writing_index,
        yoink_id=None,
        kind=writing_studio.KIND_TWEET,
        body="A grounded draft.\n\nvia Uoink corpus",
        source_credit_line="via Uoink corpus",
        suppress_credit=False,
        skip_voice_dna_this_time=False,
    )

    assert result["voice_warnings"] == [{
        "severity": "warn",
        "message": "measured",
    }]


@pytest.mark.parametrize("generate", (1, "1", "true", "false"))
def test_mcp_generate_rejects_non_boolean_before_key_lookup(
    writing_index, monkeypatch, generate
):
    monkeypatch.setattr(
        server,
        "_saved_anthropic_key",
        lambda: pytest.fail(
            "non-boolean generate reached credential lookup"),
    )

    result = uoink_mcp_tools.write_tweet({"generate": generate})

    assert result == {
        "ok": False,
        "error": "generate must be a boolean",
    }
