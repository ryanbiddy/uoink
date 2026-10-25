"""Audit #5 regressions. DNS, HTTP and subprocesses are entirely in memory.

Load server functions without importing the helper or opening a user profile.
The `network` fixture runs urllib's real redirect machinery over a fake
transport. The `dialer` fixture keeps urllib's real HTTP handler and
http.client connection, and fakes only DNS and the socket, so a test sees the
host the connection would dial.
"""
from __future__ import annotations

import ast
import http.client
import io
import ipaddress
import json
import logging
import re
import socket
import ssl
import subprocess
import urllib.error
import urllib.request
from contextlib import nullcontext
from email.message import Message
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, quote, urlparse
from urllib.response import addinfourl

import pytest
import _platform

import podcasts
import source_subscriptions as ss
import uoink_usage


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = "https://public.example/start"
FINAL = "https://cdn.example/final"
# Captured before any fixture patches it.
REAL_BUILD_OPENER = urllib.request.build_opener


@lru_cache(maxsize=None)
def source_tree(filename):
    return ast.parse((ROOT / filename).read_text(encoding="utf-8"))


def load_functions(filename, names, namespace):
    tree = source_tree(filename)
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))
             and n.name in names]
    assert {n.name for n in nodes} == set(names)
    exec(compile(ast.Module(body=ast.parse("from __future__ import annotations").body
                            + nodes, type_ignores=[]), filename, "exec"), namespace)
    return namespace


@pytest.fixture
def network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Real network access is forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    addresses, routes, requests, responses, lookups = {}, {}, [], [], []
    answered = []  # (name, answer addresses) for every lookup that answered

    def resolve(host, *args, **kwargs):
        # Like CPython's getaddrinfo, IDNA-encode the name before any lookup
        # (offline codec): an empty or over-long label raises UnicodeError.
        key = host.encode("idna").decode("ascii").rstrip(".").lower()
        lookups.append(host)
        # Like DNS: case-insensitive, trailing dot optional, and a numeric
        # name answers with itself.
        try:
            literal = [str(ipaddress.ip_address(key))]
        except ValueError:
            literal = None
        values = addresses.get(host, literal or addresses.get(key, ["8.8.8.8"]))
        if callable(values):
            values = values()
        if isinstance(values, Exception):
            raise values
        answered.append((host, list(values)))
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET,
                 socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in values]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)

    class Body(io.BytesIO):
        reads = 0

        def read(self, *args):
            self.reads += 1
            return super().read(*args)

    class Transport(urllib.request.HTTPHandler, urllib.request.HTTPSHandler):
        def http_open(self, req):
            requests.append(req)
            reply = routes.get(
                req.full_url, (200, {}, b"<title>Public page</title><p>Content</p>"))
            # Like HTTPConnection.getresponse(), the response transport can
            # raise raw socket/protocol errors that urllib does not wrap.
            if isinstance(reply, Exception):
                raise reply
            status, headers, body = reply
            message = Message()
            for key, value in headers.items():
                message[key] = value
            stream = Body(body)
            response = addinfourl(stream, message, req.full_url, status)
            response.fixture_body = stream
            response.msg = "fixture response"
            responses.append(response)
            return response

        https_open = http_open

    real_builder = urllib.request.build_opener

    def build(*handlers):
        return real_builder(urllib.request.ProxyHandler({}), Transport(), *handlers)

    monkeypatch.setattr(urllib.request, "build_opener", build)
    # Exercise the old unguarded code too, without ever permitting real I/O.
    monkeypatch.setattr(urllib.request, "urlopen", build().open)
    return SimpleNamespace(addresses=addresses, routes=routes, requests=requests,
                           responses=responses, lookups=lookups, answered=answered)


@pytest.fixture
def dialer(network, monkeypatch):
    """urllib's real Request, HTTP(S) handlers and http.client connection.

    Only socket.create_connection (resolving a name through the fake DNS, as
    the real one does; a numeric host needs no query) and TLS wrapping are
    replaced, and system proxies read as empty. Each dial records:
      dest/port  what http.client asked the socket layer to connect to
      address    the address that connection reached
      host       the request's Host header, i.e. the name it was made for
      validated  whether `address` was a DNS answer the URL check received
                 for `host` before this dial
      sni, check_hostname, verify_mode  the TLS wrapping, for HTTPS
    """
    dials, replies, unreachable = [], {}, set()

    class FakeSocket:
        def __init__(self, dial):
            self.dial, self.sent = dial, b""

        def setsockopt(self, *args):
            pass

        def sendall(self, data):
            self.sent += data

        def makefile(self, *args, **kwargs):
            lines = self.sent.split(b"\r\n")
            target = lines[0].split(b" ", 2)[1].decode("ascii")
            host = next(line.split(b":", 1)[1].strip().decode("latin-1")
                        for line in lines[1:] if line.lower().startswith(b"host:"))
            if not host.startswith("[") and host.rpartition(":")[2].isdigit():
                host = host.rpartition(":")[0]
            self.dial.host = host
            self.dial.validated = any(name == host and self.dial.address in found
                                      for name, found in self.dial.prior_answers)
            self.dial.targets.append(target)
            status, headers, body = replies.get(
                (self.dial.host, target), (200, {}, b"<title>Dialed</title><p>Content</p>"))
            head = [b"HTTP/1.1 %d Fixture" % status]
            head += [name.encode("ascii") + b": "
                     + (value if isinstance(value, bytes) else value.encode("ascii"))
                     for name, value in headers.items()]
            head += [b"Content-Length: %d" % len(body), b"Connection: close"]
            return io.BytesIO(b"\r\n".join(head) + b"\r\n\r\n" + body)

        def close(self):
            pass

    def create_connection(address, *args, **kwargs):
        dest, port = address
        prior_answers = list(network.answered)
        try:
            reached = str(ipaddress.ip_address(dest))
        except ValueError:
            reached = socket.getaddrinfo(dest, port)[0][4][0]
        dial = SimpleNamespace(dest=dest, port=port, address=reached, host=None,
                               validated=False, prior_answers=prior_answers,
                               targets=[], sni=None, check_hostname=None,
                               verify_mode=None)
        dials.append(dial)
        if reached in unreachable:
            raise ConnectionRefusedError("fixture: address unreachable")
        return FakeSocket(dial)

    def wrap_socket(context, sock, *args, server_hostname=None, **kwargs):
        sock.dial.sni = server_hostname
        sock.dial.check_hostname = context.check_hostname
        sock.dial.verify_mode = context.verify_mode
        return sock

    monkeypatch.setattr(socket, "create_connection", create_connection)
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", wrap_socket)
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})
    monkeypatch.setattr(urllib.request, "build_opener", REAL_BUILD_OPENER)
    monkeypatch.setattr(urllib.request, "urlopen", REAL_BUILD_OPENER().open)
    return SimpleNamespace(dials=dials, replies=replies, unreachable=unreachable)


@pytest.fixture
def consumers(network, monkeypatch, tmp_path):
    namespace = dict(_platform=_platform, source_subscriptions=ss, uoink_usage=uoink_usage,
                     urllib=urllib, log=logging.getLogger(__name__),
                     subprocess=subprocess, json=json, Path=Path, urlparse=urlparse,
                     parse_qs=parse_qs, re=re,
                     YTDLP_CMD=["synthetic-yt-dlp"], COMMENTS_TIMEOUT_SEC=10,
                     PLATFORM_YOUTUBE="youtube", PLATFORM_TWITTER="twitter",
                     PLATFORM_TIKTOK="tiktok", PLATFORM_INSTAGRAM="instagram",
                     PLATFORM_GENERIC="generic")
    # Host sets plus the strict platform validators' patterns.
    hosts = {"_YOUTUBE_HOSTS", "_TWITTER_HOSTS", "_TIKTOK_HOSTS", "_INSTAGRAM_HOSTS",
             "_PLATFORM_HOST_HINTS", "_VIDEO_ID_RE", "_TWITTER_STATUS_RE",
             "_TWITTER_HANDLE_RE", "_INSTAGRAM_KIND_RE"}
    nodes = [n for n in source_tree("server.py").body
             if (isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id in hosts for t in n.targets))
             or (isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
                 and n.target.id in hosts)]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "server.py", "exec"), namespace)

    def run(args, **kwargs):
        if args[0] == "ffmpeg":
            Path(args[-1]).write_bytes(b"synthetic JPEG")
        return subprocess.CompletedProcess(args, 0, stdout='{"title":"Public video"}')

    child = Mock(side_effect=run)
    namespace["_run_subprocess"] = child
    load_functions("server.py", ("_fetch_metadata", "_download_thumbnail",
                                 "_is_youtube_ytdlp_call", "_detect_platform_from_url",
                                 "_normalize_video_url", "_normalize_youtube_url",
                                 "_normalize_twitter_url", "_normalize_tiktok_url",
                                 "_normalize_instagram_url", "_normalize_any_url"), namespace)
    page = dict(source_subscriptions=ss, urllib=urllib,
                _PAGE_FETCH_TIMEOUT_SEC=10, _PAGE_MAX_BYTES=1024, ENGINE_STDLIB="stdlib",
                _now_iso=lambda: "test", _html_to_markdown=lambda html: html,
                urlparse=urlparse, log=logging.getLogger(__name__))
    # Use the real parsing regexes without importing Crawl4AI.
    page["re"] = re
    tree = source_tree("page_extractor.py")
    patterns = {"_TITLE_RE", "_META_RE", "_LINK_RE", "_IMG_RE", "_GENERIC_HOST_RE",
                "_USER_AGENT"}
    nodes = [n for n in tree.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id in patterns for t in n.targets)]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "page_extractor.py", "exec"), page)
    namespace["page_extractor"] = SimpleNamespace(_USER_AGENT=page["_USER_AGENT"])
    page.update(RENDER_MODE_JS="js", _RENDER_MODES={"js", "static"},
                _MAX_FOLLOW_LINKS_DEPTH=1, _CRAWL4AI_AVAILABLE=True,
                host_is_allowed=Mock(return_value=True),
                _is_x_login_wall=lambda *args: False,
                _extract_crawl4ai=Mock(return_value={"ok": True, "markdown": "Synthetic article body with enough text to read. " * 10}))
    import article_extractor
    page.update(article_extractor=article_extractor, ENGINE_READABILITY=article_extractor.ENGINE,
                ENGINE_CRAWL4AI="crawl4ai", _X_HOSTS={"x.com"}, _engine_version=lambda engine: "test")
    load_functions("page_extractor.py", ("_extract_stdlib", "extract_page",
                                         "normalize_page_url", "_fetch_page_html",
                                         "_extract_article_page"), page)
    # The relaxed /extract/any and /live/status validator's generic step.
    namespace["page_extractor"].normalize_page_url = page["normalize_page_url"]
    episode ={"feed_id": 1, "audio_url": PUBLIC, "status": "new"}
    monkeypatch.setattr(podcasts, "get_episode", lambda *args: episode)
    monkeypatch.setattr(podcasts, "get_feed", lambda *args: {"id": 1})
    monkeypatch.setattr(podcasts, "_episode_audio_path", lambda *args: tmp_path / "episode.mp3")
    monkeypatch.setattr(podcasts, "_record_audio_result", Mock())
    monkeypatch.setattr(podcasts, "set_episode_status", Mock())

    def audio_run(args, **kwargs):
        (tmp_path / "episode.mp3").write_bytes(b"synthetic audio")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    audio_child = Mock(side_effect=audio_run)
    monkeypatch.setattr(subprocess, "run", audio_child)
    monkeypatch.setattr("uoink_processes.run_owned", audio_child)

    def invoke(kind, url):
        if kind == "feed":
            return podcasts.fetch_feed({"feed_url": url})[0] is not None
        if kind == "standing":
            return ss.default_http_fetch(url, {}).status == 200
        if kind == "page":
            return page["_extract_stdlib"](url, include_screenshot=False)["ok"]
        if kind == "thumbnail":
            return namespace["_download_thumbnail"]({"thumbnail": url}, tmp_path) is not None
        if kind == "generic":
            return bool(namespace["_fetch_metadata"](url))
        episode["audio_url"] = url
        return podcasts.download_episode_audio(
            None, 1, data_root=tmp_path, ytdlp_cmd=["synthetic-yt-dlp"])["ok"]

    return SimpleNamespace(invoke=invoke, child=child, audio_child=audio_child,
                           server=namespace, page=page, audio_path=tmp_path / "episode.mp3")


CONSUMERS = ["feed", "standing", "page", "thumbnail", "generic", "enclosure"]


def assert_refused(consumers, kind, url):
    try:
        assert consumers.invoke(kind, url) is False
    except ss.ServiceError:
        pass
    consumers.child.assert_not_called()
    consumers.audio_child.assert_not_called()


@pytest.mark.parametrize("kind", CONSUMERS)
@pytest.mark.parametrize("host", [
    "127.0.0.1", "10.0.0.1", "169.254.169.254", "8.8.8.8", "[::1]",
    "[2606:4700:4700::1111]", "[::ffff:127.0.0.1]", "127.1", "2130706433",
    "0x7f000001", "0177.0.0.1", "localhost", "localhost.", "a.localhost",
])
def test_literals_and_localhost_never_reach_transport(kind, host, network, consumers):
    assert_refused(consumers, kind, f"http://{host}/resource")
    assert network.requests == []


@pytest.mark.parametrize("kind", CONSUMERS)
@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.1.1", "169.254.169.254",
    "::1", "fc00::1", "fe80::1", "::ffff:127.0.0.1", "0.0.0.0",
    "224.0.0.1", "100.64.0.1",
    # IPv6 answers that embed a nonpublic IPv4: IPv4-mapped, NAT64 (DNS64
    # synthesizes these on IPv6-only networks), NAT64 local-use and 6to4.
    "::ffff:192.168.1.1", "::ffff:169.254.169.254", "::ffff:100.64.0.1",
    "64:ff9b::c0a8:101", "64:ff9b::7f00:1", "64:ff9b::a9fe:a9fe", "64:ff9b::a00:1",
    "64:ff9b:1::c0a8:101", "2002:c0a8:101::1",
])
def test_any_nonpublic_dns_answer_blocks_fetch(kind, address, network, consumers):
    network.addresses["public.example"] = ["8.8.8.8", address]
    assert_refused(consumers, kind, PUBLIC)
    assert network.requests == []


@pytest.mark.parametrize("address,refused", [
    ("64:ff9b::c0a8:101", True), ("64:ff9b::7f00:1", True),
    ("64:ff9b::a9fe:a9fe", True), ("64:ff9b:1::808:808", True),
    ("::ffff:10.0.0.1", True), ("::ffff:127.0.0.1", True),
    ("2002:c0a8:101::1", True), ("2002:7f00:1::1", True),
    ("64:ff9b::808:808", False), ("::ffff:8.8.8.8", False),
    ("2606:4700:4700::1111", False),
])
def test_embedded_ipv4_decides_even_when_ipv6_flags_look_public(
        address, refused, monkeypatch):
    # Python currently also refuses most of these through ::/8 "reserved" or
    # its private-range table. Make every IPv6 flag look public so only the
    # embedded-IPv4 and NAT64 local-use rules can refuse.
    for flag, value in (("is_global", True), ("is_private", False),
                        ("is_reserved", False), ("is_loopback", False),
                        ("is_link_local", False), ("is_multicast", False),
                        ("is_unspecified", False)):
        monkeypatch.setattr(ipaddress.IPv6Address, flag,
                            property(lambda self, value=value: value))
    assert ipaddress.ip_address(address).is_global
    if refused:
        with pytest.raises(ss.ServiceError, match="refused") as exc:
            ss._reject_private_ip(address)
        assert exc.value.code == "unsupported_source"
    else:
        ss._reject_private_ip(address)


@pytest.mark.parametrize("kind", CONSUMERS)
@pytest.mark.parametrize("target", ["http://127.0.0.1/secret", "http://8.8.8.8/secret",
                                    "https://internal.example/secret",
                                    "http://user:pass@public.example/secret"])
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_every_redirect_hop_is_checked(kind, target, status, network, consumers):
    network.addresses["internal.example"] = ["192.168.1.1"]
    network.routes[PUBLIC] = (302, {"Location": FINAL}, b"")
    network.routes[FINAL] = (status, {"Location": target}, b"")
    assert_refused(consumers, kind, PUBLIC)
    assert [req.full_url for req in network.requests] == [PUBLIC, FINAL]
    assert all(response.closed for response in network.responses)


@pytest.mark.parametrize("kind", CONSUMERS)
def test_public_redirect_succeeds_and_ytdlp_gets_checked_destination(kind, network, consumers):
    network.routes[PUBLIC] = (302, {"Location": "/next"}, b"")
    network.routes["https://public.example/next"] = (307, {"Location": FINAL}, b"")
    assert consumers.invoke(kind, PUBLIC)
    assert [req.full_url for req in network.requests] == [
        PUBLIC, "https://public.example/next", FINAL]
    if kind in ("generic", "enclosure"):
        child = consumers.child if kind == "generic" else consumers.audio_child
        assert child.call_args.args[0][-2:] == ["--", FINAL]
        assert all(response.closed for response in network.responses)
        assert network.responses[-1].fixture_body.reads == 0


@pytest.mark.parametrize("kind", ["generic", "enclosure"])
def test_admission_user_agent_is_sent_on_every_hop(kind, network, consumers):
    network.routes[PUBLIC] = (302, {"Location": "/next"}, b"")
    network.routes["https://public.example/next"] = (307, {"Location": FINAL}, b"")
    assert consumers.invoke(kind, PUBLIC)
    assert [req.full_url for req in network.requests] == [
        PUBLIC, "https://public.example/next", FINAL]
    expected = (podcasts._FEED_USER_AGENT if kind == "enclosure"
                else consumers.page["_USER_AGENT"])
    assert expected and not expected.startswith("Python-urllib/")
    assert all(req.get_header("User-agent") == expected for req in network.requests)


@pytest.mark.parametrize("kind", CONSUMERS)
def test_saved_hostname_is_rechecked_on_later_fetch(kind, network, consumers):
    assert consumers.invoke(kind, PUBLIC)
    consumers.child.reset_mock()
    consumers.audio_child.reset_mock()
    # Simulate a saved feed/URL whose DNS changed after a previous fetch.
    consumers.audio_path.unlink(missing_ok=True)
    network.requests.clear()
    network.addresses["public.example"] = ["127.0.0.1"]
    assert_refused(consumers, kind, PUBLIC)
    assert network.requests == []


def test_conditional_feed_headers_and_304_are_preserved(network):
    network.routes[PUBLIC] = (304, {"ETag": '"same"'}, b"")
    body, headers = podcasts.fetch_feed({"feed_url": PUBLIC, "last_etag": '"same"',
                                        "last_modified": "yesterday"})
    assert body is None and headers["ETag"] == '"same"'
    assert network.requests[0].get_header("If-none-match") == '"same"'
    assert network.requests[0].get_header("If-modified-since") == "yesterday"


@pytest.mark.parametrize("kind", CONSUMERS)
@pytest.mark.parametrize("answer", [[], socket.gaierror(socket.EAI_NONAME, "fixture DNS failure")])
def test_failed_or_empty_dns_fails_closed(kind, answer, network, consumers):
    network.addresses["public.example"] = answer
    assert_refused(consumers, kind, PUBLIC)
    assert network.requests == []


@pytest.mark.parametrize("kind", CONSUMERS)
def test_same_host_redirect_rechecks_dns(kind, network, consumers):
    answers = iter([["8.8.8.8"], ["127.0.0.1"]])
    network.addresses["public.example"] = lambda: next(answers)
    network.routes[PUBLIC] = (302, {"Location": "/changed"}, b"")
    assert_refused(consumers, kind, PUBLIC)
    assert [req.full_url for req in network.requests] == [PUBLIC]
    assert network.lookups == ["public.example", "public.example"]


@pytest.mark.parametrize("kind", CONSUMERS)
@pytest.mark.parametrize("url", ["file:///fixture", "ftp://public.example/file",
                                "https://user:pass@public.example/file",
                                "https://public.example:bad/file"])
def test_other_url_checks_stay_strict(kind, url, network, consumers):
    assert_refused(consumers, kind, url)
    assert network.requests == []


@pytest.mark.parametrize("kind", ["generic", "enclosure"])
def test_failed_preflight_never_starts_ytdlp(kind, network, consumers):
    network.routes[PUBLIC] = (403, {}, b"not allowed")
    if kind == "generic":
        with pytest.raises(urllib.error.HTTPError):
            consumers.invoke(kind, PUBLIC)
    else:
        assert consumers.invoke(kind, PUBLIC) is False
    consumers.child.assert_not_called()
    consumers.audio_child.assert_not_called()
    assert network.responses[-1].closed
    assert network.responses[-1].fixture_body.reads == 0


def test_existing_audio_remains_available_without_network(network, consumers):
    consumers.audio_path.write_bytes(b"existing local audio")
    assert consumers.invoke("enclosure", "http://127.0.0.1/audio")
    assert network.requests == network.lookups == []
    consumers.audio_child.assert_not_called()


def test_local_fixture_transport_requires_explicit_injection(network, consumers, tmp_path):
    local = "http://localhost:8765/fixture"

    def fixture_open(url, **kwargs):
        assert url == local
        return addinfourl(io.BytesIO(b"<title>Fixture</title>"), Message(), url, 200)

    assert podcasts.fetch_feed({"feed_url": local}, http_open=fixture_open)[0]
    assert consumers.page["_extract_stdlib"](
        local, include_screenshot=False, http_open=fixture_open)["ok"]
    assert consumers.server["_download_thumbnail"](
        {"thumbnail": local}, tmp_path, http_open=fixture_open)
    assert consumers.server["_fetch_metadata"](local, resolve_url=lambda url, **kwargs: url)
    assert podcasts.download_episode_audio(
        None, 1, data_root=tmp_path, ytdlp_cmd=["synthetic-yt-dlp"],
        resolve_url=lambda url, **kwargs: local)["ok"]
    assert network.requests == network.lookups == []


def test_existing_localhost_harness_injection_preserves_other_host_checks(
        network, monkeypatch):
    # S20/S21 explicitly replace these two checks for their one local feed
    # server. Keep that seam usable, with every other target still checked.
    local = "http://127.0.0.1:8765/feed"
    final = "http://127.0.0.1:8765/final"
    reject_ip, check_host = ss._reject_private_ip, ss._check_resolved_host
    monkeypatch.setattr(ss, "_reject_private_ip",
                        lambda host: None if host == "127.0.0.1" else reject_ip(host))
    monkeypatch.setattr(ss, "_check_resolved_host",
                        lambda host: None if host == "127.0.0.1" else check_host(host))
    network.routes[local] = (302, {"Location": final}, b"")
    assert ss.default_http_fetch(local, {}).status == 200
    assert [req.full_url for req in network.requests] == [local, final]
    assert network.lookups == []

    for target in ("http://8.8.8.8/feed", "http://10.0.0.1/feed",
                   "http://127.0.0.2/feed", "https://internal.example/feed"):
        network.requests.clear()
        network.addresses["internal.example"] = ["192.168.1.1"]
        network.routes[final] = (302, {"Location": target}, b"")
        with pytest.raises(ss.ServiceError, match="refused"):
            ss.default_http_fetch(local, {})
        assert [req.full_url for req in network.requests] == [local, final]


def test_standing_source_body_limit_stays_enforced(network):
    network.routes[PUBLIC] = (200, {}, b"too large")
    with pytest.raises(ss.ServiceError, match="byte budget"):
        ss.default_http_fetch(PUBLIC, {}, max_bytes=3)


def test_public_ipv6_resolution_is_allowed(network):
    network.addresses["public.example"] = ["2606:4700:4700::1111"]
    assert ss.default_http_fetch(PUBLIC, {}).status == 200


@pytest.mark.parametrize("answer,status", [
    (["127.0.0.1"], "error"),
    (socket.gaierror(socket.EAI_NONAME, "fixture DNS failure"), "new"),
])
def test_audio_policy_refusal_and_transient_failure_keep_distinct_statuses(
        answer, status, network, consumers):
    network.addresses["public.example"] = answer
    assert_refused(consumers, "enclosure", PUBLIC)
    assert podcasts._record_audio_result.call_args.kwargs["status"] == status


@pytest.mark.parametrize("host", [
    "youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com",
    "music.youtube.com", "MUSIC.YouTube.com.",
])
def test_youtube_metadata_keeps_original_url_without_unpaced_get(host, network, consumers):
    url = f"https://{host}/watch?v=abcdef12345"
    assert consumers.server["_is_youtube_ytdlp_call"](["synthetic-yt-dlp", url])
    assert consumers.server["_fetch_metadata"](url)
    assert network.requests == network.lookups == []
    assert consumers.child.call_args.args[0][-2:] == ["--", url]


@pytest.mark.parametrize("host", ["music.youtube.com.attacker.example", "fake.youtube.com"])
def test_youtube_lookalikes_still_require_generic_admission(host, network, consumers):
    network.addresses[host] = ["127.0.0.1"]
    assert_refused(consumers, "generic", f"https://{host}/watch?v=abcdef12345")
    assert network.requests == []


@pytest.mark.parametrize("enforce_allowlist", [True, False])
@pytest.mark.parametrize("url,addresses", [
    ("http://127.0.0.1/page", ["8.8.8.8"]),
    ("http://8.8.8.8/page", ["8.8.8.8"]),
    ("http://localhost/page", ["8.8.8.8"]),
    (PUBLIC, ["8.8.8.8", "10.0.0.1"]),
    (PUBLIC, ["::1"]),
    (PUBLIC, ["169.254.169.254"]),
    (PUBLIC, []),
    (PUBLIC, socket.gaierror(socket.EAI_NONAME, "fixture DNS failure")),
])
def test_crawl4ai_refuses_initial_target_even_without_site_allowlist(
        url, addresses, enforce_allowlist, network, consumers):
    network.addresses["public.example"] = addresses
    fallback = Mock(side_effect=AssertionError("Refusal must not fall back"))
    consumers.page["_extract_stdlib"] = fallback
    result = consumers.page["extract_page"](None, url, enforce_allowlist=enforce_allowlist)
    assert result["ok"] is False
    assert result["error"]
    consumers.page["_extract_crawl4ai"].assert_not_called()
    fallback.assert_not_called()
    assert network.requests == []


def test_crawl4ai_checks_public_target_before_rendering(network, consumers):
    at_render = []

    def render(url, **kwargs):
        at_render.append((url, list(network.lookups), list(network.requests)))
        return {"ok": True, "markdown": "Synthetic article body with enough text to read. " * 10}

    consumers.page["_extract_crawl4ai"].side_effect = render
    assert consumers.page["extract_page"](None, PUBLIC)["ok"]
    assert len(at_render) == 1 and at_render[0][0] == PUBLIC
    assert at_render[0][1] and all(host == "public.example" for host in at_render[0][1])
    assert [request.full_url for request in at_render[0][2]] == [PUBLIC]


def test_crawl4ai_local_fixture_requires_explicit_injection(network, consumers):
    local = "http://localhost:8765/fixture"
    check = Mock(side_effect=lambda url: url)
    body = io.BytesIO(b"<html><body>Short fixture</body></html>")
    body.status = 200
    assert consumers.page["extract_page"](None, local, check_url=check,
                                         http_open=lambda *a, **k: body)["ok"]
    check.assert_called_once_with(local)
    assert consumers.page["_extract_crawl4ai"].call_args.args == (local,)
    assert network.requests == network.lookups == []


def test_crawl4ai_runtime_failure_uses_checked_stdlib_fallback(network, consumers):
    consumers.page["_extract_crawl4ai"].side_effect = RuntimeError("renderer unavailable")
    network.routes[PUBLIC] = (302, {"Location": "http://127.0.0.1/secret"}, b"")
    assert consumers.page["extract_page"](None, PUBLIC)["ok"] is False
    assert [request.full_url for request in network.requests] == [PUBLIC]


@pytest.mark.parametrize("failure", [
    "private", "redirect", "credentials", "validation", "dns", "http", "transport",
    "response_timeout", "response_disconnect", "response_protocol",
])
def test_extract_any_url_admission_errors_return_400(failure, network, consumers, tmp_path):
    namespace = consumers.server
    namespace.update(DESKTOP_ROOT=tmp_path, log=Mock(),
                     _ManualOwnership=lambda: SimpleNamespace(process_slot=nullcontext),
                     _normalize_any_url=lambda url: (url, "generic"))
    handler = next(node for node in source_tree("server.py").body
                   if isinstance(node, ast.ClassDef) and node.name == "Handler")
    method = next(node for node in handler.body
                  if isinstance(node, ast.FunctionDef) and node.name == "_handle_extract_any")
    exec(compile(ast.Module(body=[method], type_ignores=[]), "server.py", "exec"), namespace)
    url = PUBLIC
    if failure == "private":
        network.addresses["public.example"] = ["127.0.0.1"]
        message = "refused"
    elif failure == "redirect":
        network.routes[PUBLIC] = (302, {"Location": "http://127.0.0.1/secret"}, b"")
        message = "refused"
    elif failure == "credentials":
        # A redirect can introduce credentials after request normalization.
        network.routes[PUBLIC] = (302, {"Location": "https://user:pass@cdn.example/"}, b"")
        message = "Credentials"
    elif failure == "validation":
        namespace["_fetch_metadata"] = Mock(
            side_effect=ss.ServiceError("validation_error", "fixture invalid URL"))
        message = "fixture invalid URL"
    elif failure == "dns":
        network.addresses["public.example"] = socket.gaierror(socket.EAI_NONAME, "fixture")
        message = "DNS resolution failed"
    elif failure == "http":
        network.routes[PUBLIC] = (403, {}, b"forbidden")
        message = "403"
    elif failure.startswith("response_"):
        error_type = {"response_timeout": TimeoutError,
                      "response_disconnect": http.client.RemoteDisconnected,
                      "response_protocol": http.client.HTTPException}[failure]
        message = "fixture response failure"
        network.routes[PUBLIC] = error_type(message)
    else:
        namespace["_fetch_metadata"] = Mock(side_effect=urllib.error.URLError("fixture transport"))
        message = "fixture transport"
    request = SimpleNamespace(_send_json=lambda status, body: (status, body))
    status, body = namespace["_handle_extract_any"](request, {"url": url})
    assert status == 400
    assert body["ok"] is False
    assert message in body["error"]
    assert body["url"] == url and body["platform"] == "generic"
    namespace["log"].exception.assert_not_called()
    consumers.child.assert_not_called()
    if failure.startswith("response_"):
        assert [req.full_url for req in network.requests] == [PUBLIC]


@pytest.mark.parametrize("error_type", [TimeoutError, http.client.RemoteDisconnected,
                                       http.client.HTTPException])
def test_enclosure_response_errors_leave_episode_retryable(error_type, network, consumers):
    network.routes[PUBLIC] = error_type("fixture response failure")
    assert_refused(consumers, "enclosure", PUBLIC)
    assert podcasts._record_audio_result.call_args.kwargs["status"] == "new"


def load_handler_method(namespace, name):
    handler = next(node for node in source_tree("server.py").body
                   if isinstance(node, ast.ClassDef) and node.name == "Handler")
    method = next(node for node in handler.body
                  if isinstance(node, ast.FunctionDef) and node.name == name)
    exec(compile(ast.Module(body=[method], type_ignores=[]), "server.py", "exec"), namespace)
    return namespace[name]


@pytest.fixture
def extract_any(consumers, tmp_path):
    """The real /extract/any handler and relaxed validator, all in memory."""
    namespace = consumers.server
    namespace.update(DESKTOP_ROOT=tmp_path, log=Mock(),
                     _ManualOwnership=lambda: SimpleNamespace(process_slot=nullcontext))
    handle = load_handler_method(namespace, "_handle_extract_any")
    request = SimpleNamespace(_send_json=lambda status, body: (status, body))
    return lambda url: handle(request, {"url": url})


# getaddrinfo IDNA-encodes hosts: an empty label or one over 63 characters
# raises UnicodeError (a ValueError), which the page validator's host pattern
# does not catch.
UNENCODABLE_HOSTS = ["a..b", "x" * 64 + ".example"]


@pytest.mark.parametrize("host", UNENCODABLE_HOSTS)
@pytest.mark.parametrize("hop", ["initial", "redirect"])
def test_extract_any_unencodable_host_is_a_400_refusal(host, hop, network, consumers,
                                                       extract_any):
    target = f"https://{host}/x"
    assert consumers.page["normalize_page_url"](target) == target
    url = target if hop == "initial" else PUBLIC
    network.routes[PUBLIC] = (302, {"Location": f"http://{host}/"}, b"")
    status, body = extract_any(url)
    assert status == 400
    assert body["ok"] is False
    assert "URL refused or unreachable" in body["error"]
    assert "Malformed URL host" in body["error"]
    assert body["url"] == url and body["platform"] == "generic"
    consumers.server["log"].exception.assert_not_called()
    consumers.child.assert_not_called()
    assert [req.full_url for req in network.requests] == ([] if hop == "initial" else [PUBLIC])
    assert all(response.closed for response in network.responses)
    assert host not in network.lookups


@pytest.mark.parametrize("kind", CONSUMERS)
@pytest.mark.parametrize("host", UNENCODABLE_HOSTS)
@pytest.mark.parametrize("hop", ["initial", "redirect"])
def test_unencodable_host_is_refused_on_every_fetch_path(kind, host, hop, network, consumers):
    url = f"https://{host}/x" if hop == "initial" else PUBLIC
    network.routes[PUBLIC] = (302, {"Location": f"http://{host}/"}, b"")
    assert_refused(consumers, kind, url)
    with pytest.raises(ss.ServiceError, match="Malformed URL host") as exc:
        ss.check_public_http_url(f"http://{host}/")
    assert exc.value.code == "unsupported_source"
    assert [req.full_url for req in network.requests] == ([] if hop == "initial" else [PUBLIC])


@pytest.mark.parametrize("host", UNENCODABLE_HOSTS + ["a.."])
def test_trailing_empty_label_is_checked_as_the_connection_names_it(host, network):
    # Resolving a stripped name ("a") would pass while the connection to
    # "a.." raised UnicodeError outside urllib's URLError wrapping.
    with pytest.raises(ss.ServiceError, match="Malformed URL host"):
        ss.check_public_http_url(f"https://{host}/x")
    assert network.lookups == []
    network.routes[PUBLIC] = (302, {"Location": f"https://{host}/x"}, b"")
    with pytest.raises(ss.ServiceError, match="Malformed URL host"):
        ss.resolve_public_http_url(PUBLIC)
    assert [req.full_url for req in network.requests] == [PUBLIC]


@pytest.mark.parametrize("host", UNENCODABLE_HOSTS)
@pytest.mark.parametrize("enforce_allowlist", [True, False])
def test_crawl4ai_refuses_unencodable_host(host, enforce_allowlist, network, consumers):
    fallback = Mock(side_effect=AssertionError("Refusal must not fall back"))
    consumers.page["_extract_stdlib"] = fallback
    url = f"https://{host}/x"
    result = consumers.page["extract_page"](None, url, enforce_allowlist=enforce_allowlist)
    assert result["ok"] is False
    assert result["code"] == "unsupported_source"
    assert "Malformed URL host" in result["error"]
    consumers.page["_extract_crawl4ai"].assert_not_called()
    fallback.assert_not_called()
    assert network.requests == []


@pytest.mark.parametrize("host", UNENCODABLE_HOSTS)
@pytest.mark.parametrize("hop", ["initial", "redirect"])
def test_enclosure_unencodable_host_is_a_refusal_not_a_retry(host, hop, network, consumers):
    url = f"https://{host}/audio.mp3" if hop == "initial" else PUBLIC
    network.routes[PUBLIC] = (302, {"Location": f"http://{host}/audio.mp3"}, b"")
    assert_refused(consumers, "enclosure", url)
    recorded = podcasts._record_audio_result.call_args.kwargs
    assert recorded["status"] == "error"
    assert "Malformed URL host" in recorded["error"]


# Relaxed URLs on the X/Twitter and Instagram hosts that the strict validator
# rejects: /live/status falls back to _normalize_any_url, which keeps the full
# path and query and tags the platform from the host.
RELAXED_PLATFORM_URLS = [
    "https://x.com/anything/at/all?next=https://elsewhere.example/",
    "https://x.com/i/flow/login?redirect_after_login=%2F",
    "https://www.instagram.com/explore/tags/fixture/?next=1",
    "https://www.instagram.com/accounts/login/?next=/fixture/",
]
NON_STRICT_PLATFORM_URLS = RELAXED_PLATFORM_URLS + [
    # Strict-valid input that is not the strict validator's own output.
    "https://twitter.com/someone/status/1234567890123456789?ref=fixture",
    "https://www.tiktok.com/@someone/video/1234567890?lang=en",
]
STRICT_PLATFORM_URLS = [
    "https://x.com/someone/status/1234567890123456789",
    "https://x.com/i/status/1234567890123456789",
    "https://www.tiktok.com/@someone/video/1234567890",
    "https://vm.tiktok.com/ZMfixture",
    "https://www.instagram.com/reel/AbC123/",
    "https://www.instagram.com/p/AbC123/",
]


@pytest.mark.parametrize("url", NON_STRICT_PLATFORM_URLS)
def test_non_strict_platform_url_is_refused_before_ytdlp(url, network, consumers):
    network.addresses[urlparse(url).hostname] = ["127.0.0.1"]
    assert consumers.server["_normalize_video_url"](url)[0] != url
    with pytest.raises(ss.ServiceError, match="refused"):
        consumers.server["_fetch_metadata"](url)
    consumers.child.assert_not_called()
    assert network.requests == []
    assert network.lookups == [urlparse(url).hostname]


@pytest.mark.parametrize("url", NON_STRICT_PLATFORM_URLS)
def test_non_strict_platform_url_goes_through_checked_get(url, network, consumers):
    at_start = []
    consumers.child.side_effect = lambda args, **kwargs: (
        at_start.append([req.full_url for req in network.requests])
        or subprocess.CompletedProcess(args, 0, stdout='{"title":"Public video"}'))
    network.routes[url] = (302, {"Location": FINAL}, b"")
    assert consumers.server["_fetch_metadata"](url)
    assert at_start == [[url, FINAL]]
    assert consumers.child.call_args.args[0][-2:] == ["--", FINAL]
    assert all(req.get_header("User-agent") == consumers.page["_USER_AGENT"]
               for req in network.requests)


@pytest.mark.parametrize("url", STRICT_PLATFORM_URLS)
def test_strict_platform_url_keeps_existing_ytdlp_flow(url, network, consumers):
    assert consumers.server["_normalize_video_url"](url)[0] == url
    assert consumers.server["_fetch_metadata"](url)
    assert network.requests == network.lookups == []
    assert consumers.child.call_args.args[0][-2:] == ["--", url]


@pytest.fixture
def live_status(consumers):
    namespace = consumers.server
    namespace.update(_detect_live_state=lambda metadata: "not_live",
                     _LIVE_STATES=("not_live",))
    handle = load_handler_method(namespace, "_handle_live_status_get")

    def get(url):
        request = SimpleNamespace(path="/live/status?url=" + quote(url, safe=""),
                                  _require_token=lambda: True,
                                  _send_json=lambda status, body: (status, body))
        return handle(request)

    return get


@pytest.mark.parametrize("url", RELAXED_PLATFORM_URLS)
def test_live_status_relaxed_platform_url_is_admitted(url, network, consumers,
                                                      live_status):
    assert consumers.server["_normalize_video_url"](url) == (None, None)
    assert consumers.server["_normalize_any_url"](url)[0] == url
    network.addresses[urlparse(url).hostname] = ["127.0.0.1"]
    status, body = live_status(url)
    assert status == 400
    assert body["ok"] is False and "refused" in body["error"]
    consumers.child.assert_not_called()
    assert network.requests == []


@pytest.mark.parametrize("url", STRICT_PLATFORM_URLS)
def test_live_status_strict_platform_url_keeps_existing_flow(url, network, consumers,
                                                             live_status):
    status, body = live_status(url)
    assert status == 200
    assert body["ok"] is True and body["url"] == url
    assert network.requests == network.lookups == []
    assert consumers.child.call_args.args[0][-2:] == ["--", url]


DIAL_START = "http://public.example/start"
# Authorities whose checked spelling and dialed name could differ. DNS makes
# every decoded or canonical form internal; the encoded spellings resolve
# public, so only a check of the dialed name can refuse them.
NON_CANONICAL_AUTHORITIES = [
    "%69nternal.attacker.example",                  # the reported bypass
    "internal%2Eattacker.example",                  # encoded dot
    "internal.attacker.example%3A8080",             # encoded port separator
    "public.example%40internal.attacker.example",   # encoded userinfo separator
    "%31%32%37.0.0.1",                              # encoded IPv4 literal
    "[fe80::1%25eth0]",                             # IPv6 zone id
    "user@internal.attacker.example",               # userinfo
    "0x7f.0.0.1", "017700000001",                   # hex and octal IPv4
    "８.８.８.８",                  # fullwidth IPv4 literal
    "ｌｏｃａｌｈｏｓｔ",  # fullwidth localhost
    "ｉnternal.attacker.example",               # fullwidth letter
    "INTERNAL.Attacker.Example.",                   # mixed case, trailing dot
]


@pytest.mark.parametrize("kind", CONSUMERS)
@pytest.mark.parametrize("authority", NON_CANONICAL_AUTHORITIES)
@pytest.mark.parametrize("hop", ["initial", "redirect"])
def test_non_canonical_authority_never_dials_an_unchecked_host(
        kind, authority, hop, network, consumers, dialer):
    network.addresses["internal.attacker.example"] = ["127.0.0.1"]
    network.addresses["localhost"] = ["127.0.0.1"]
    target = f"http://{authority}/resource"
    # Raw UTF-8 Location bytes, as a hostile server would send them.
    dialer.replies[("public.example", "/start")] = (
        302, {"Location": target.encode("utf-8")}, b"")
    assert_refused(consumers, kind, target if hop == "initial" else DIAL_START)
    assert [(dial.host, dial.port) for dial in dialer.dials] == (
        [] if hop == "initial" else [("public.example", 80)])
    assert all(dial.validated for dial in dialer.dials)


@pytest.mark.parametrize("hop", ["initial", "redirect"])
def test_reported_percent_encoded_bypass_is_refused_before_dialing(hop, network, dialer):
    network.addresses["%69nternal.attacker.example"] = ["8.8.8.8"]
    network.addresses["internal.attacker.example"] = ["127.0.0.1"]
    target = "http://%69nternal.attacker.example/resource"
    dialer.replies[("public.example", "/start")] = (302, {"Location": target}, b"")
    with pytest.raises(ss.ServiceError, match="Percent-encoded URL hosts are refused") as exc:
        ss.default_http_fetch(target if hop == "initial" else DIAL_START, {})
    assert exc.value.code == "unsupported_source"
    assert [dial.host for dial in dialer.dials] == (
        [] if hop == "initial" else ["public.example"])
    assert "internal.attacker.example" not in network.lookups
    with pytest.raises(ss.ServiceError, match="Percent-encoded"):
        ss.normalize_podcast_feed_url(target)


@pytest.mark.parametrize("scheme,port", [("http", 80), ("https", 443)])
@pytest.mark.parametrize("host", ["public.example", "PUBLIC.Example", "public.example.",
                                  "bücher.example"])
def test_connection_dials_exactly_the_checked_host_on_every_hop(
        scheme, port, host, network, dialer):
    start, final = f"{scheme}://{host}/start", f"{scheme}://Cdn.Example./final"
    dialer.replies[(host, "/start")] = (302, {"Location": final}, b"")
    assert ss.resolve_public_http_url(start) == final
    assert [(dial.host, dial.port) for dial in dialer.dials] == [
        (host, port), ("Cdn.Example.", port)]
    assert all(dial.validated and ipaddress.ip_address(dial.address).is_global
               for dial in dialer.dials)
    if scheme == "https":
        assert [dial.sni for dial in dialer.dials] == [host, "Cdn.Example."]


@pytest.mark.parametrize("kind", CONSUMERS)
def test_every_fetch_path_dials_only_checked_public_hosts(kind, network, consumers, dialer):
    final = "http://Cdn.Example./final"
    dialer.replies[("public.example", "/start")] = (302, {"Location": final}, b"")
    assert consumers.invoke(kind, DIAL_START)
    assert [(dial.host, dial.targets) for dial in dialer.dials] == [
        ("public.example", ["/start"]), ("Cdn.Example.", ["/final"])]
    assert all(dial.validated and ipaddress.ip_address(dial.address).is_global
               for dial in dialer.dials)
    if kind in ("generic", "enclosure"):
        child = consumers.child if kind == "generic" else consumers.audio_child
        assert child.call_args.args[0][-2:] == ["--", final]


def test_dialed_name_that_differs_from_the_parsed_host_is_refused(network, dialer,
                                                                  monkeypatch):
    # Backstop for any other urllib rewrite of the authority.
    class Rewriting(urllib.request.Request):
        def _parse(self):
            super()._parse()
            self.host = "internal.attacker.example"

    monkeypatch.setattr(urllib.request, "Request", Rewriting)
    with pytest.raises(ss.ServiceError, match="Non-canonical URL hosts are refused"):
        ss.check_public_http_url("http://public.example/resource")
    assert network.lookups == [] and dialer.dials == []


REBIND = "rebind.attacker.example"


def rebinding_dns(network, private, first=("8.8.8.8",)):
    """The first lookup answers `first`; every later lookup answers `private`."""
    answers = iter([list(first)])
    network.addresses[REBIND] = lambda: next(answers, [private])


@pytest.mark.parametrize("scheme,port", [("http", 80), ("https", 443)])
@pytest.mark.parametrize("hop", ["initial", "redirect"])
@pytest.mark.parametrize("private", ["127.0.0.1", "169.254.169.254", "10.0.0.1", "::1"])
def test_dns_rebinding_after_the_check_cannot_move_the_dial(
        scheme, port, hop, private, network, dialer):
    rebinding_dns(network, private)
    target = f"{scheme}://{REBIND}/resource"
    start = target if hop == "initial" else f"{scheme}://public.example/start"
    dialer.replies[("public.example", "/start")] = (302, {"Location": target}, b"")
    fetched = ss.default_http_fetch(start, {})
    assert fetched.status == 200 and b"Dialed" in fetched.body
    rebound = [dial for dial in dialer.dials if dial.host == REBIND]
    assert [(dial.address, dial.port, dial.targets) for dial in rebound] == [
        ("8.8.8.8", port, ["/resource"])]
    assert len(dialer.dials) == (1 if hop == "initial" else 2)
    # The check's lookup is the only one: the socket layer gets an address.
    assert network.lookups.count(REBIND) == 1
    assert all(dial.dest == dial.address for dial in dialer.dials)
    assert all(dial.validated and ipaddress.ip_address(dial.address).is_global
               for dial in dialer.dials)
    if scheme == "https":
        # SNI and certificate hostname verification still use the host name.
        assert [dial.sni for dial in dialer.dials] == [dial.host for dial in dialer.dials]
        assert all(dial.check_hostname is True and dial.verify_mode == ssl.CERT_REQUIRED
                   for dial in dialer.dials)


@pytest.mark.parametrize("kind", CONSUMERS)
def test_every_fetch_path_dials_the_checked_address_despite_rebinding(
        kind, network, consumers, dialer):
    rebinding_dns(network, "127.0.0.1")
    assert consumers.invoke(kind, f"http://{REBIND}/resource")
    assert [(dial.host, dial.dest, dial.address) for dial in dialer.dials] == [
        (REBIND, "8.8.8.8", "8.8.8.8")]
    assert network.lookups.count(REBIND) == 1


def test_pinned_dial_tries_only_checked_addresses_and_never_resolves_again(
        network, dialer):
    checked = ["8.8.4.4", "2606:4700:4700::1111", "8.8.8.8"]
    rebinding_dns(network, "127.0.0.1", first=checked)
    dialer.unreachable.update(checked)
    with pytest.raises(urllib.error.URLError):
        ss.default_http_fetch(f"http://{REBIND}/resource", {})
    assert [dial.dest for dial in dialer.dials] == checked
    assert network.lookups.count(REBIND) == 1

    dialer.dials.clear()
    rebinding_dns(network, "127.0.0.1", first=checked)
    dialer.unreachable.discard("8.8.8.8")
    assert ss.default_http_fetch(f"http://{REBIND}/resource", {}).status == 200
    assert [dial.dest for dial in dialer.dials] == checked
    assert dialer.dials[-1].validated and dialer.dials[-1].host == REBIND
    assert network.lookups.count(REBIND) == 2  # one check per fetch, no dial lookups


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_unpinned_or_mismatched_request_is_refused_without_a_lookup(scheme, network, dialer):
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), ss._PinnedHTTPHandler(), ss._PinnedHTTPSHandler())
    with pytest.raises(ss.ServiceError, match="Unchecked request targets are refused"):
        opener.open(urllib.request.Request(f"{scheme}://public.example/x"))
    request = urllib.request.Request(f"{scheme}://public.example/x")
    ss._pin_request(request, "other.example", ["8.8.8.8"])
    with pytest.raises(ss.ServiceError, match="Unchecked request targets are refused"):
        opener.open(request)
    assert network.lookups == [] and dialer.dials == []


def test_localhost_harness_seam_dials_its_literal_host_through_the_pin(
        network, dialer, monkeypatch):
    # The S20/S21 harnesses replace both checks for 127.0.0.1 only, so the
    # check returns no addresses. The pin then holds that exact literal.
    reject_ip, check_host = ss._reject_private_ip, ss._check_resolved_host
    monkeypatch.setattr(ss, "_reject_private_ip",
                        lambda host: None if host == "127.0.0.1" else reject_ip(host))
    monkeypatch.setattr(ss, "_check_resolved_host",
                        lambda host: None if host == "127.0.0.1" else check_host(host))
    assert ss.default_http_fetch("http://127.0.0.1:8765/feed", {}).status == 200
    assert [(dial.dest, dial.port) for dial in dialer.dials] == [("127.0.0.1", 8765)]
    dialer.replies[("127.0.0.1", "/feed")] = (302, {"Location": "http://10.0.0.1/feed"}, b"")
    with pytest.raises(ss.ServiceError, match="refused"):
        ss.default_http_fetch("http://127.0.0.1:8765/feed", {})
    assert network.lookups == []


def test_fetches_connect_directly_even_with_system_proxies(network, dialer, monkeypatch):
    # A proxy would resolve the name again, out of reach of the pin.
    proxy = "http://proxy.example:3128"
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {"http": proxy, "https": proxy})
    rebinding_dns(network, "127.0.0.1")
    assert ss.default_http_fetch(f"http://{REBIND}/resource", {}).status == 200
    assert [(dial.dest, dial.host) for dial in dialer.dials] == [("8.8.8.8", REBIND)]
    assert "proxy.example" not in network.lookups
