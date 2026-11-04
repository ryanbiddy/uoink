"""Check the CI fixture allowance without Docker, sockets, or app imports."""
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest


@pytest.fixture
def smoke():
    return runpy.run_path(str(Path(__file__).resolve().parents[1]
                              / "scripts/linux/smoke_capture.py"))


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:49495/episode.mp3",
    "https://127.0.0.1:49494/episode.mp3",
    "http://localhost:49494/episode.mp3",
    "http://127.0.0.1.example.com:49494/episode.mp3",
    "http://user@127.0.0.1:49494/episode.mp3",
    "http://127.0.0.1:49494@elsewhere.example/episode.mp3",
    "http://10.0.0.1:49494/episode.mp3",
    "http://127.0.0.1:49494/episode.mp3#fragment",
    "http://127.0.0.1:49494/episode.mp3\n",
    "https://example.com/feed.xml",
])
def test_fixture_allowance_delegates_every_other_url(smoke, url):
    calls = []

    def original(name):
        def guard(url, **kwargs):
            calls.append((name, url, kwargs))
            return "real-guard-result"
        return guard

    names = ("public_http_open", "resolve_public_http_url", "check_public_http_url")
    originals = {name: original(name) for name in names}
    guards = SimpleNamespace(**originals)
    with smoke["allow_fixture_origin"](guards, "http://127.0.0.1:49494"):
        assert guards.public_http_open(url, headers={"Accept": "audio/*"},
                                       timeout=2, method="HEAD", follow_redirects=False) == "real-guard-result"
        assert guards.resolve_public_http_url(url, user_agent="smoke", timeout=3) == "real-guard-result"
        assert guards.check_public_http_url(url) == "real-guard-result"
    assert calls == [
        ("public_http_open", url, {"headers": {"Accept": "audio/*"}, "timeout": 2,
                                  "method": "HEAD", "follow_redirects": False}),
        ("resolve_public_http_url", url, {"user_agent": "smoke", "timeout": 3}),
        ("check_public_http_url", url, {}),
    ]
    assert all(getattr(guards, name) is originals[name] for name in names)


def test_fixture_allowance_opens_only_its_origin_and_restores_on_failure(smoke, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Fixture URL sent to the public-network guard")

    names = ("public_http_open", "resolve_public_http_url", "check_public_http_url")
    guards = SimpleNamespace(**dict.fromkeys(names, forbidden))
    requests = []

    def opener(*handlers):
        redirect = next(handler for handler in handlers
                        if isinstance(handler, smoke["urllib"].request.HTTPRedirectHandler))
        assert redirect.redirect_request(None, None, 302, "redirect", {}, "http://elsewhere.example/") is None

        def open(request, *, timeout):
            requests.append((request.full_url, request.get_method(), timeout))
            return "fixture-response"
        return SimpleNamespace(open=open)

    monkeypatch.setattr(smoke["urllib"].request, "build_opener", opener)
    with pytest.raises(RuntimeError, match="cleanup"):
        with smoke["allow_fixture_origin"](guards, "http://127.0.0.1:49494"):
            url = "http://127.0.0.1:49494/episode.mp3"
            assert guards.public_http_open(url, method="HEAD", timeout=5) == "fixture-response"
            assert guards.resolve_public_http_url(url) == url
            assert guards.check_public_http_url(url) == url
            raise RuntimeError("cleanup")
    assert requests == [(url, "HEAD", 5)]
    assert all(getattr(guards, name) is forbidden for name in names)
