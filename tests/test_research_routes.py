"""In-process GET dispatch, with disposable data and no listening helper."""
from io import BytesIO
import json
import socket
from types import SimpleNamespace
import urllib.request

import pytest

import research
from tests.test_research_evidence import rig
from tests.test_research_publish import prepared, publish, claim


@pytest.fixture
def http(tmp_path, monkeypatch):
    profile, app = tmp_path / "profile", tmp_path / "app"
    profile.mkdir()
    app.mkdir()
    monkeypatch.setenv("UOINK_ISOLATED_PROFILE", str(profile))
    monkeypatch.setenv("UOINK_ISOLATED_APP_DIR", str(app))
    monkeypatch.setenv("UOINK_ISOLATED_PORT", "18124")
    monkeypatch.setenv("UOINK_OUTPUT_DIR", str(tmp_path / "output"))
    import server
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "TOKEN", "synthetic-test-token")
    def forbidden(*args, **kwargs):
        pytest.fail("Research route tests must not access the network")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    def request(path, *, token=True, origin="http://127.0.0.1:18124"):
        handler = object.__new__(server.Handler)
        handler.path, handler.command = path, "GET"
        handler.server = SimpleNamespace(server_address=("127.0.0.1", 18124))
        handler.headers = {"Host": "127.0.0.1:18124", "Origin": origin,
                           "Sec-Fetch-Site": "same-origin"}
        if token:
            handler.headers["X-Uoink-Token"] = "synthetic-test-token"
        handler.wfile = BytesIO()
        handler.client_address = ("127.0.0.1", 18124)
        response = {"headers": {}}
        handler.send_response = lambda status: response.update(status=status)
        handler.send_header = lambda key, value: response["headers"].update({key: value})
        handler.end_headers = lambda: None
        handler.do_GET()
        response["body"] = handler.wfile.getvalue()
        return response
    return request


def test_fixed_html_route_and_security_headers(tmp_path, http):
    run = research.create_run(tmp_path, {"question": "Synthetic question"})
    directory = tmp_path / "research" / run["run_id"]
    html = b"<!doctype html><h1>Synthetic report</h1>"
    (directory / "report.html").write_bytes(html)
    (directory / "report.md").write_text("# Synthetic report", encoding="utf-8")
    (directory / "private.txt").write_text("not a report", encoding="utf-8")
    base = f"/research/{run['run_id']}"
    result = http(base + "/report")
    assert result["status"] == 200 and result["body"] == html
    assert result["headers"]["Content-Security-Policy"] == (
        "default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
    assert result["headers"]["X-Frame-Options"] == "DENY"
    assert result["headers"]["X-Content-Type-Options"] == "nosniff"
    assert result["headers"]["Cache-Control"] == "no-store"
    for name in ("private.txt", "run.json", "verification.json", "report.md", "report.html", "report/extra"):
        refused = http(base + "/" + name)
        assert refused["status"] in (400, 404)
    assert json.loads(http(base + "/markdown")["body"])["content"] == "# Synthetic report"


@pytest.mark.parametrize("tail", ["../report", "%2e%2e/report", "rr_20261103000000_aabbccdd/../report",
    "rr_20261103000000_aabbccdd%2f..%2f/report", "rr_20261103000000_aabbccdd\\..\\/report",
    "rr_20261103000000_aabbccdd%00/report", "rr_20261103000000_aabbccdd/../../secret"])
def test_traversal_is_rejected_before_read(http, monkeypatch, tail):
    monkeypatch.setattr(research, "report_file", lambda *args: pytest.fail("traversal reached file reading"))
    assert http("/research/" + tail)["status"] in (400, 404)


def test_token_and_origin_checks_apply_to_all_research_reads(http):
    for path in ("/research", "/research/rr_20261103000000_aabbccdd",
                 "/research/rr_20261103000000_aabbccdd/report", "/research/rr_20261103000000_aabbccdd/markdown"):
        assert http(path, token=False)["status"] == 403
        assert http(path, origin="https://evil.example")["status"] == 403


def test_run_view_is_read_only_and_omits_evidence(tmp_path, http):
    run = research.create_run(tmp_path, {"question": "Synthetic question"})
    run["excerpts"] = {"secret": {"text": "Full transcript text must not appear"}}
    research.save_run(tmp_path, run)
    before = {p: p.read_bytes() for p in (tmp_path / "research").rglob("*") if p.is_file()}
    result = http("/research/" + run["run_id"])
    assert result["status"] == 200
    view = json.loads(result["body"])
    assert view["run_id"] == run["run_id"] and run["run_id"] in view["prompt"]
    assert view["exports"] == {"html": False, "md": False}
    assert "Full transcript" not in result["body"].decode()
    assert len(json.loads(http("/research")["body"])["runs"]) == 1
    assert http("/research/" + run["run_id"] + "/report")["status"] == 404
    assert before == {p: p.read_bytes() for p in (tmp_path / "research").rglob("*") if p.is_file()}


def test_markdown_only_report_is_available(tmp_path, http):
    run = research.create_run(tmp_path, {"question": "Markdown export"})
    (tmp_path / "research" / run["run_id"] / "report.md").write_text("# Markdown only", encoding="utf-8")
    base = f"/research/{run['run_id']}"
    view = json.loads(http(base)["body"])
    assert view["exports"] == {"html": False, "md": True} and view["report"] is None
    assert json.loads(http(base + "/markdown")["body"])["content"] == "# Markdown only"
    assert http(base + "/report")["status"] == 404


def test_linked_report_location_is_refused(tmp_path):
    run = research.create_run(tmp_path, {"question": "Synthetic question"})
    target = tmp_path / "elsewhere.html"
    target.write_text("outside the run")
    path = tmp_path / "research" / run["run_id"] / "report.html"
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("Creating symlinks is unavailable on this Windows account")
    with pytest.raises(research.ResearchError, match="location"):
        research.report_file(tmp_path, run["run_id"])


def test_publish_adds_quote_free_dashboard_view(rig):
    run, excerpt = prepared(rig)
    good = claim(excerpt, judge="supports")
    bad = claim(excerpt, quote="fabricated quote must be omitted", id="bad", text="Dropped claim")
    result = publish(run, [good, bad])
    view = research.run_view(rig.root, run["run_id"])
    assert view["exports"] == {"html": True, "md": True}
    assert view["report"]["claims"][0]["text"] == good["text"]
    assert view["report"]["claims"][0]["receipts"][0]["deep_link"].endswith("&t=27s")
    assert view["verification"]["dropped"][0]["reasons"] == ["quote_not_found"]
    assert "fabricated quote" not in json.dumps(view)
    assert all("quote" not in ref for c in view["report"]["claims"] for ref in c["receipts"])
    assert result["verification"] == {key: view["verification"][key] for key in result["verification"]}
