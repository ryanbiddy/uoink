"""Provider and HTTP conformance tests for corpus read contract v1."""

from __future__ import annotations

import copy
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import corpus_contract  # noqa: E402
import regenerate_corpus_contract_v1_fixture as regenerate  # noqa: E402
import server  # noqa: E402

DASHBOARD = (
    ROOT / "assets" / "dashboard" / "index.html"
).read_text(encoding="utf-8")


def _section(start: str, end: str) -> str:
    assert start in DASHBOARD
    body = DASHBOARD.split(start, 1)[1]
    assert end in body
    return body.split(end, 1)[0]


def test_uoink_provider_matches_conformance_fixture():
    expected = json.loads(
        regenerate.FIXTURE_PATH.read_text(encoding="utf-8"))
    actual = regenerate.generate_fixture()
    assert actual == expected
    assert expected["_fixture"] == {
        "contract": "uoink.corpus.read",
        "version": 1,
        "provider": "UoinkCorpusProvider",
        "regenerate": (
            "python tests/regenerate_corpus_contract_v1_fixture.py"
        ),
        "check": (
            "python tests/regenerate_corpus_contract_v1_fixture.py --check"
        ),
        "data": "synthetic",
    }


def test_contract_rejects_unknown_provider_fields():
    fixture = regenerate.generate_fixture()
    data = copy.deepcopy(fixture["operations"]["get"]["data"])
    data["item"]["corpus_path"] = "must never cross the contract"
    with pytest.raises(corpus_contract.ContractError) as raised:
        corpus_contract.success("get", data)
    assert raised.value.code == "provider_nonconformant"
    assert "unknown corpus_path" in raised.value.message


@pytest.mark.parametrize("query,message", [
    ({"limit": ["0"]}, "limit must be between 1 and 200"),
    ({"offset": ["-1"]}, "offset must be between 0 and 1000000"),
    ({"surprise": ["1"]}, "unknown search parameters: surprise"),
    ({"date_from": ["2030-02-01"], "date_to": ["2030-01-01"]},
     "date_from is after date_to"),
])
def test_search_request_rejects_invalid_bounds(query, message):
    with pytest.raises(corpus_contract.ContractError) as raised:
        corpus_contract.SearchRequest.from_query(query)
    assert raised.value.code == "invalid_request"
    assert raised.value.message == message


class _QuietHandler(server.Handler):
    def log_message(self, format, *args):  # noqa: A002
        return


def _request(port: int, path: str, *, token: bool = True):
    headers = {"X-Uoink-Token": server.TOKEN} if token else {}
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return (
                response.status,
                response.headers.get_content_type(),
                response.read(),
            )
    except urllib.error.HTTPError as error:
        return (
            error.code,
            error.headers.get_content_type(),
            error.read(),
        )


def test_http_contract_routes_and_attachment(tmp_path, monkeypatch):
    idx, _provider = regenerate.build_provider(tmp_path)
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path / "corpus")
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = int(httpd.server_address[1])
    try:
        for operation, path in (
            ("search", "/api/corpus/v1/search?limit=20"),
            ("get", "/api/corpus/v1/items/video-contract"),
            ("facets", "/api/corpus/v1/facets"),
            ("taste", "/api/corpus/v1/taste"),
        ):
            status, mime, raw = _request(port, path)
            payload = json.loads(raw.decode("utf-8"))
            assert status == 200
            assert mime == "application/json"
            assert payload["contract"] == "uoink.corpus.read"
            assert payload["version"] == 1
            assert payload["operation"] == operation
            corpus_contract.validate_data(operation, payload["data"])
            assert "corpus_path" not in raw.decode("utf-8")
            assert "sidecar_path" not in raw.decode("utf-8")

        status, mime, raw = _request(
            port,
            "/api/corpus/v1/items/video-contract/attachments/screenshot-0",
        )
        assert status == 200
        assert mime == "image/jpeg"
        assert raw == b"fixture-screenshot"

        status, mime, raw = _request(
            port,
            "/api/corpus/v1/items/note-contract/attachments/primary",
        )
        assert status == 200
        assert mime == "image/png"
        assert raw == b"fixture-note-image"

        status, _mime, raw = _request(
            port, "/api/corpus/v1/items/missing")
        missing = json.loads(raw.decode("utf-8"))
        assert status == 404
        assert missing["error"] == {
            "code": "not_found",
            "message": "corpus item not found",
            "retryable": False,
        }

        status, _mime, raw = _request(
            port, "/api/corpus/v1/search?limit=0")
        invalid = json.loads(raw.decode("utf-8"))
        assert status == 400
        assert invalid["error"]["code"] == "invalid_request"

        status, _mime, _raw = _request(
            port, "/api/corpus/v1/search", token=False)
        assert status == 403
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        idx.close()


def test_generate_tab_dogfoods_contract():
    sources = _section(
        "async function loadWritingSources(force = false)",
        "function syncWritingSourceOptions()",
    )
    assert "/api/corpus/v1/search?limit=200" in sources
    assert "/memory/search?limit=200" not in sources
    assert "data.data && data.data.items" in sources

    smart_inputs = _section(
        "async function loadGenerateSmartInputs()",
        "const FACET_EMPTY_STATES",
    )
    assert 'authFetch("/api/corpus/v1/facets")' in smart_inputs
    assert 'authFetch("/library/facets")' not in smart_inputs
    assert 'authFetch("/corpus/channels?limit=80")' not in smart_inputs
    assert "normalizeFacetItems(facets.channel)" in smart_inputs

    selection = _section(
        "async function selectWritingSourceById(id)",
        "function toggleWritingSourceCombo(open)",
    )
    assert "/api/corpus/v1/items/${encodeURIComponent" in selection
    assert "detail.content" in selection
    assert "detail.attachments" in selection

    image_loader = _section(
        "async function loadDetailFileImages()",
        "function rowFromCard(card)",
    )
    assert 'img[data-file-img], img[data-file-url]' in image_loader
