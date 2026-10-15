"""Offline regressions for Comment Intelligence JSON repair and one retry."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402


COMMENTS = [
    {"author": f"Viewer {i}", "text": f"Comment {i}", "like_count": i}
    for i in range(5)
]
ANALYSIS = {
    "top_themes": [{
        "label": "Costs", "description": "Viewers discuss costs.", "count": 5,
        "quotes": [r'Keep ",}" and ",]" and a backslash \ intact.'],
    }],
    "mentioned_products_tools": [{"name": "Example tool", "frequency": 2}],
    "notable_disagreements": [],
}
VALID_JSON = json.dumps(ANALYSIS)
TRAILING_COMMAS = r'''
{
  "top_themes": [{
    "label": "Costs", "description": "Viewers discuss costs.", "count": 5,
    "quotes": ["Keep \",}\" and \",]\" and a backslash \\ intact.", ],
  }, ],
  "mentioned_products_tools": [{"name": "Example tool", "frequency": 2, }, ],
  "notable_disagreements": [],
}
'''
INVALID_JSON = '{"top_themes": [] "mentioned_products_tools": []}'


def response(text, *, input_tokens=100, output_tokens=20):
    return {
        "model": server.ANTHROPIC_MODEL,
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


@pytest.fixture
def model(monkeypatch, tmp_path):
    unexpected_io = Mock(side_effect=AssertionError("unmocked external I/O"))
    for name in ("run", "Popen", "check_output"):
        monkeypatch.setattr(subprocess, name, unexpected_io)
    monkeypatch.setattr(server.urllib.request, "urlopen", unexpected_io)
    monkeypatch.setattr(server.socket, "create_connection", unexpected_io)
    monkeypatch.setattr(server.socket.socket, "connect", unexpected_io)

    idx = server.index.Index.open(tmp_path / "index.db")
    state = SimpleNamespace(
        client=Mock(side_effect=AssertionError("unexpected model request")),
        meter=Mock(wraps=server._record_anthropic_usage),
        invalid_key=Mock(), index=idx,
    )
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "_anthropic_key_available", lambda: "test-key")
    monkeypatch.setattr(server, "_anthropic_messages", state.client)
    monkeypatch.setattr(server, "_record_anthropic_usage", state.meter)
    monkeypatch.setattr(server, "_mark_anthropic_key_invalid", state.invalid_key)
    try:
        yield state
    finally:
        idx.close()
        unexpected_io.assert_not_called()


@pytest.mark.parametrize("text", [
    VALID_JSON,
    f"```json\n{VALID_JSON}\n```",
    f"Here is the analysis:\n{VALID_JSON}\nEnd of analysis.",
    TRAILING_COMMAS,
    f"Here is the analysis:\n```json\n{TRAILING_COMMAS}\n```\nEnd of analysis.",
], ids=["valid", "fenced", "wrapped", "trailing-commas", "combined"])
def test_repairable_output_needs_no_second_call(model, text):
    resp = response(text)
    model.client.side_effect = [resp]

    assert server.analyze_comments(COMMENTS) == {
        "model": server.ANTHROPIC_MODEL, **ANALYSIS,
    }

    model.client.assert_called_once()
    model.meter.assert_called_once_with("comment_intelligence", resp)
    model.invalid_key.assert_not_called()


@pytest.mark.parametrize("text", [
    INVALID_JSON, "No JSON object here.", '{"top_themes": [', "",
], ids=["missing-comma", "no-object", "truncated", "empty"])
def test_unrepairable_output_retries_once_and_records_both_calls(model, text):
    responses = [response(text), response(VALID_JSON, input_tokens=150, output_tokens=30)]
    model.client.side_effect = responses

    assert server.analyze_comments(COMMENTS) == {
        "model": server.ANTHROPIC_MODEL, **ANALYSIS,
    }

    assert model.client.call_count == 2
    first, retry = model.client.call_args_list
    assert first.args == retry.args == ("test-key",)
    assert first.kwargs["system"] == retry.kwargs["system"]
    assert first.kwargs["max_tokens"] == retry.kwargs["max_tokens"] == 1200
    assert retry.kwargs["user"].startswith(first.kwargs["user"])
    assert "previous response was invalid JSON" in retry.kwargs["user"]
    assert "one valid JSON object" in retry.kwargs["user"]
    assert model.meter.call_args_list == [
        call("comment_intelligence", resp) for resp in responses
    ]
    bucket, = server.usage_meter.read_buckets(model.index)
    assert bucket["feature"] == "comment_intelligence"
    assert bucket["calls"] == 2
    assert bucket["input_tokens"] == 250
    assert bucket["output_tokens"] == 50
    assert bucket["est_usd"] == server._anthropic_estimated_cost(250, 50)
    model.invalid_key.assert_not_called()


def test_second_invalid_response_keeps_existing_failure_status(model, tmp_path):
    responses = [response(INVALID_JSON), response(INVALID_JSON)]
    model.client.side_effect = responses
    folder = tmp_path / "capture"
    folder.mkdir()
    sidecar = folder / "capture.json"
    sidecar.write_text("{}", encoding="utf-8")
    markdown = folder / "capture.md"
    markdown.write_text("# Capture\n", encoding="utf-8")

    server._comment_intelligence_worker(folder, markdown, COMMENTS)

    saved = json.loads(sidecar.read_text(encoding="utf-8"))
    assert saved["comment_intelligence_status"] == "failed"
    assert saved["comment_intelligence"] is None
    assert "returned invalid JSON" in saved["comment_intelligence_error"]
    assert "Expecting ',' delimiter" in saved["comment_intelligence_error"]
    assert "Comment Intelligence: analysis failed" in markdown.read_text(encoding="utf-8")
    assert model.client.call_count == 2
    assert model.meter.call_args_list == [
        call("comment_intelligence", resp) for resp in responses
    ]
    bucket, = server.usage_meter.read_buckets(model.index)
    assert bucket["calls"] == 2
    assert bucket["input_tokens"] == 200
    assert bucket["output_tokens"] == 40
    assert bucket["est_usd"] == server._anthropic_estimated_cost(200, 40)
    model.invalid_key.assert_not_called()


@pytest.mark.parametrize("status", [401, 429, 500, None])
@pytest.mark.parametrize("on_retry", [False, True])
def test_api_errors_propagate_without_another_retry(model, status, on_retry):
    error = server.AnthropicAPIError(status, "request failed")
    responses = [response(INVALID_JSON)] if on_retry else []
    model.client.side_effect = [*responses, error]

    with pytest.raises(server.AnthropicAPIError) as exc:
        server.analyze_comments(COMMENTS)

    assert exc.value is error
    assert model.client.call_count == len(responses) + 1
    assert model.meter.call_args_list == [
        call("comment_intelligence", resp) for resp in responses
    ]
    if status == 401:
        model.invalid_key.assert_called_once_with()
    else:
        model.invalid_key.assert_not_called()


def test_other_json_consumers_still_reject_trailing_commas(model):
    with pytest.raises(server.AnthropicAPIError, match="returned invalid JSON"):
        server._extract_json_object(TRAILING_COMMAS)
    model.client.assert_not_called()
