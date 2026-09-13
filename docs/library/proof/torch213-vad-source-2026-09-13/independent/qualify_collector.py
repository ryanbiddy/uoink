"""Generated-byte transport qualification only. No real opener or output I/O."""
import argparse
from datetime import datetime, timezone
import encodings.ascii
import encodings.idna
import encodings.utf_8
import hashlib
import io
import json
import os
from pathlib import Path
import re
import ssl
import stat
import sys
import time
import types
import urllib.error
import urllib.request
from contextlib import contextmanager, redirect_stdout

EXPECTED = "6971aa91d430f0b43f3a3215d2dfe8a0c467b234ead827d311b1323b348fdc93"
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
source_path = Path(__file__).absolute().parent / "collect_torch_text.py"
source_bytes = source_path.read_bytes()
harness_bytes = Path(__file__).read_bytes()
assert hashlib.sha256(source_bytes).hexdigest() == EXPECTED
guard_denials = []


def guard(event, args):
    if (event == "open" or event == "import" or event.startswith(("socket.", "subprocess.", "ctypes.", "os.exec", "os.spawn"))
            or event in ("os.system", "os.startfile")):
        guard_denials.append(event)
        raise RuntimeError("Synthetic guard refused " + event)


sys.addaudithook(guard)
subject = types.ModuleType("reviewed_collector")
subject.__file__ = str(source_path)
exec(compile(source_bytes, str(source_path), "exec"), subject.__dict__)
cases = []
C, T, U, TREE = "1" * 40, "2" * 40, "3" * 40, "4" * 40
API, RAW = subject.API, subject.RAW
TEST_URL = API + "commits/" + C


def case(name):
    def register(function):
        cases.append((name, function))
        return function
    return register


def refused(function, marker):
    try:
        function()
    except subject.Refusal as error:
        assert marker in str(error), (marker, str(error))
    else:
        raise AssertionError("Expected refusal: " + marker)


@contextmanager
def patched(obj, name, replacement):
    previous = getattr(obj, name)
    setattr(obj, name, replacement)
    try:
        yield
    finally:
        setattr(obj, name, previous)


class Response:
    def __init__(self, body=b'{"ok":true}', *, code=200, headers=None, url=TEST_URL, chunks=None):
        self.body, self.code, self.url, self.offset = body, code, url, 0
        self.headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
        if headers is not None:
            self.headers = headers
        self.chunks = None if chunks is None else list(chunks)
        self.closed = False

    def read(self, size):
        if self.chunks is not None:
            next_chunk = self.chunks.pop(0) if self.chunks else b""
            if isinstance(next_chunk, Exception):
                raise next_chunk
            assert len(next_chunk) <= size
            return next_chunk
        part = self.body[self.offset:self.offset + size]
        self.offset += len(part)
        return part

    def geturl(self):
        return self.url

    def close(self):
        self.closed = True


class Opener:
    def __init__(self, sequence):
        self.sequence, self.calls = list(sequence), []

    def open(self, request, timeout):
        self.calls.append({"url": request.full_url, "method": request.get_method(),
                           "headers": dict(request.header_items()), "timeout": timeout})
        assert self.sequence, "Unexpected request"
        expected_url, response = self.sequence.pop(0)
        assert request.full_url == expected_url
        if isinstance(response, Exception):
            raise response
        return response


class MemoryCollection(subject.Collection):
    instances = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.saved = {}
        self.instances.append(self)

    def save(self, name, raw):
        assert re.fullmatch(r"[a-z0-9-]+\.(txt|json)", name)
        assert name not in self.saved, "Exclusive synthetic output"
        self.saved[name] = bytes(raw)


def collection(response=None, *, sequence=None, mode="resolve", commit=None):
    if sequence is None:
        sequence = [(TEST_URL, response or Response())]
    opener = Opener(sequence)
    return MemoryCollection(Path("E:/synthetic-never-created"), mode, commit, opener)


def json_response(url, value):
    return (url, Response(json.dumps(value).encode("ascii"), url=url))


def binding_sequence(*, annotated=False):
    rows = [json_response(API + "ref/tags/v2.13.0", {
        "ref": "refs/tags/v2.13.0", "object": {"type": "tag" if annotated else "commit", "sha": T if annotated else C}})]
    if annotated:
        rows.append(json_response(API + "tags/" + T, {"sha": T, "tag": "v2.13.0", "object": {"type": "commit", "sha": C}}))
    rows.append(json_response(API + "commits/" + C, {"sha": C, "tree": {"sha": TREE}}))
    return rows


@case("fixed_scope_and_caps")
def fixed_scope():
    result = subject.plan()
    assert len(subject.FILES) == len(set(path for path, _ in subject.FILES)) == 19
    assert sum(cap for _, cap in subject.FILES) == 1839104
    assert result["source_body_cap_sum"] == 1839104
    assert subject.TOTAL_LIMIT == 4194304 and subject.REQUEST_LIMIT == 24
    assert subject.API_LIMIT == 16384 and subject.SECONDS == 120 and subject.REQUEST_SECONDS == 10


@case("url_scope_exact")
def url_scope():
    for path, _ in subject.FILES:
        assert subject.allowed_url(RAW + C + "/" + path, "sources", C)
    for url in ("http://api.github.com/repos/pytorch/pytorch/git/ref/tags/v2.13.0",
                RAW + "v2.13.0/torch/__init__.py", RAW + U + "/torch/__init__.py",
                RAW + C + "/model.bin", RAW + C + "/../torch/__init__.py",
                TEST_URL + "?secret=value", "https://example.com/source.py"):
        assert not subject.allowed_url(url, "sources", C), url
    assert not subject.allowed_url(RAW + C + "/torch/__init__.py", "resolve", C)


@case("request_headers_utc_sha_and_inert_body")
def request_success():
    payload = b"__import__('os').system('THIS MUST STAY DATA')\n"
    col = collection(Response(payload, headers={"Content-Type": "text/plain"}))
    assert col.get(TEST_URL, 256, "source") == payload
    record = col.records[0]
    assert record["status"] == "text_collected" and record["body_complete"]
    assert datetime.fromisoformat(record["started_utc"]) <= datetime.fromisoformat(record["finished_utc"])
    assert record["body_sha256"] == hashlib.sha256(payload).hexdigest()
    assert col.saved["body-01.txt"] == payload
    call = col.opener.calls[0]
    assert call["method"] == "GET" and call["timeout"] == 10
    assert call["headers"]["Accept-encoding"] == "identity"
    assert not any(key.lower() in ("authorization", "cookie", "proxy-authorization") for key in call["headers"])


for name, response, marker in (
    ("redirect_status_refused", Response(b"moved", code=302), "HTTP response"),
    ("changed_response_url", Response(url="https://example.com/redirect"), "Response URL changed"),
    ("encoded_response", Response(headers={"Content-Encoding": "gzip"}), "Encoded response"),
    ("successful_html", Response(headers={"Content-Type": "text/html"}), "Unexpected successful"),
    ("invalid_content_length", Response(headers={"Content-Length": "-1"}), "Invalid response length"),
    ("oversized_content_length", Response(headers={"Content-Length": "257"}), "Advertised response"),
    ("short_body", Response(b"a", headers={"Content-Type": "application/json", "Content-Length": "5"}), "Response length mismatch"),
    ("invalid_utf8", Response(b"\xff"), "not UTF-8"),
    ("nul_source", Response(b"a\x00b"), "NUL"),
    ("lfs_pointer", Response(b"version https://git-lfs.github.com/spec/v1\noid sha256:x\n"), "LFS pointer"),
):
    def check(response=response, marker=marker):
        col = collection(response)
        refused(lambda: col.get(TEST_URL, 256, "api"), marker)
        assert col.records[0]["status"] == "refused"
        assert "finished_utc" in col.records[0]
        assert response.closed
    case(name)(check)


@case("http_error_body_is_failure_evidence")
def http_error_body():
    error = urllib.error.HTTPError(TEST_URL, 403, "denied", {"Content-Type": "text/plain"}, io.BytesIO(b"denied"))
    col = collection(sequence=[(TEST_URL, error)])
    refused(lambda: col.get(TEST_URL, 256, "api"), "HTTP response")
    assert col.records[0]["http_status"] == 403
    assert col.saved["body-01.txt"] == b"denied"


@case("oversized_body_retains_only_bounded_prefix")
def oversized_body():
    col = collection(Response(b"x" * 17, headers={"Content-Type": "application/json"}))
    refused(lambda: col.get(TEST_URL, 16, "api"), "Response exceeds cap")
    assert len(col.saved["body-01.txt"]) == 16
    assert col.records[0]["truncated"] and not col.records[0]["body_complete"]


@case("interrupted_read_preserves_partial_error")
def interrupted():
    col = collection(Response(headers={"Content-Type": "application/json"}, chunks=[b"abc", TimeoutError()]))
    try:
        col.get(TEST_URL, 256, "api")
    except TimeoutError:
        pass
    else:
        raise AssertionError("Timeout required")
    assert col.records[0]["status"] == "error"
    assert col.records[0]["body_complete"] is False
    assert col.saved["body-01.txt"] == b"abc"


@case("total_byte_cap")
def total_cap():
    col = collection(Response(b"abcd"))
    with patched(subject, "TOTAL_LIMIT", 3):
        refused(lambda: col.get(TEST_URL, 256, "api"), "Total response byte cap")


@case("request_cap_before_open")
def request_cap():
    col = collection()
    with patched(subject, "REQUEST_LIMIT", 0):
        refused(lambda: col.get(TEST_URL, 256, "api"), "Request limit")
    assert not col.opener.calls


@case("deadline_before_open")
def deadline():
    col = collection()
    col.started -= 121
    refused(lambda: col.get(TEST_URL, 256, "api"), "deadline")
    assert not col.opener.calls


@case("local_json_receipt_cap")
def receipt_cap():
    refused(lambda: subject.json_bytes({"oversized": "x" * 131072}), "receipt too large")


for name, payload, marker in (
    ("duplicate_api_key", b'{"object":1,"object":2}', "Duplicate API JSON key"),
    ("malformed_api_json", b"{", "Malformed API JSON"),
    ("api_root_array", b"[]", "API object required"),
    ("api_body_cap", b"x" * 16385, "API body cap"),
):
    case(name)(lambda payload=payload, marker=marker: refused(lambda: subject.api_json(payload), marker))


@case("lightweight_tag_chain")
def lightweight():
    col = collection(sequence=binding_sequence())
    value = subject.resolve_binding(col)
    assert value["commit"] == value["initial_ref_object"] == C
    assert value["tree_declaration"] == TREE and len(col.opener.calls) == 2


@case("annotated_tag_chain")
def annotated():
    col = collection(sequence=binding_sequence(annotated=True))
    value = subject.resolve_binding(col)
    assert value["commit"] == C and value["initial_ref_object"] == T
    assert len(value["chain"]) == 2 and len(col.opener.calls) == 3


for name, field, value, marker in (
    ("wrong_ref_name", "ref", "refs/heads/main", "Git ref mismatch"),
    ("unsupported_ref_type", "object", {"type": "blob", "sha": C}, "Unsupported Git object type"),
    ("invalid_ref_id", "object", {"type": "commit", "sha": "main"}, "Git object ID"),
):
    def check(field=field, value=value, marker=marker):
        ref = {"ref": "refs/tags/v2.13.0", "object": {"type": "commit", "sha": C}}
        ref[field] = value
        col = collection(sequence=[json_response(API + "ref/tags/v2.13.0", ref)])
        refused(lambda: subject.resolve_binding(col), marker)
    case(name)(check)


@case("wrong_annotated_tag_name")
def wrong_tag_name():
    rows = binding_sequence(annotated=True)
    rows[1] = json_response(API + "tags/" + T, {"sha": T, "tag": "v2.12.0", "object": {"type": "commit", "sha": C}})
    refused(lambda: subject.resolve_binding(collection(sequence=rows)), "Annotated tag name")


@case("tag_cycle_refused")
def tag_cycle():
    rows = binding_sequence(annotated=True)
    rows[1] = json_response(API + "tags/" + T, {"sha": T, "tag": "v2.13.0", "object": {"type": "tag", "sha": T}})
    refused(lambda: subject.resolve_binding(collection(sequence=rows)), "tag cycle")


@case("tag_depth_refused")
def tag_depth():
    rows = binding_sequence(annotated=True)[:1]
    rows += [json_response(API + "tags/" + T, {"sha": T, "tag": "v2.13.0", "object": {"type": "tag", "sha": U}}),
             json_response(API + "tags/" + U, {"sha": U, "tag": "inner", "object": {"type": "tag", "sha": TREE}})]
    refused(lambda: subject.resolve_binding(collection(sequence=rows)), "tag depth")


@case("commit_identity_refused")
def wrong_commit():
    rows = binding_sequence()
    rows[-1] = json_response(API + "commits/" + C, {"sha": U, "tree": {"sha": TREE}})
    refused(lambda: subject.resolve_binding(collection(sequence=rows)), "commit identity")


@contextmanager
def main_seams(opener, **overrides):
    args = types.SimpleNamespace(mode="sources", admission=subject.ADMISSION, label="synthetic01",
                                 expected_commit=C, expected_ref_object=C)
    for name, value in overrides.items():
        setattr(args, name, value)
    class Parser:
        def __init__(self, *a, **k): pass
        def add_argument(self, *a, **k): pass
        def parse_args(self, argv): return args
    calls = []
    # These seams isolate orchestration logic. They do not qualify argparse, TLS or path I/O.
    def output(label):
        calls.append("output")
        return Path("E:/synthetic-never-created")
    def context():
        calls.append("tls-context")
        return object()
    with patched(subject.argparse, "ArgumentParser", Parser), patched(subject.ssl, "create_default_context", context), \
         patched(subject.urllib.request, "HTTPSHandler", lambda **kw: object()), \
         patched(subject.urllib.request, "build_opener", lambda *a: opener), \
         patched(subject, "create_output", output), patched(subject, "Collection", MemoryCollection), \
         patched(subject, "install_audit", lambda output: calls.append("instrument-audit")), redirect_stdout(io.StringIO()) as stdout:
        yield calls, stdout


@case("absent_admission_before_tls_and_paths")
def absent_admission():
    opener = Opener([])
    with main_seams(opener, admission=None) as (calls, stdout):
        assert subject.main([]) == 2
        assert not calls and not opener.calls
        assert json.loads(stdout.getvalue())["status"] == "refused"


for name, changes in (("changed_reviewed_commit", {"expected_commit": U}),
                      ("changed_reviewed_ref_object", {"expected_ref_object": U})):
    def check(changes=changes):
        opener = Opener(binding_sequence())
        with main_seams(opener, **changes) as (_, stdout):
            assert subject.main([]) == 2
            receipt = json.loads(stdout.getvalue())
            assert "differs from reviewed" in receipt["reason"]
            assert len(opener.calls) == 2 and all(call["url"].startswith(API) for call in opener.calls)
    case(name)(check)


@case("complete_fake_source_stage_exact_19_urls")
def complete_stage():
    rows = binding_sequence()
    for path, _ in subject.FILES:
        url = RAW + C + "/" + path
        rows.append((url, Response(b"synthetic source text\n", url=url, headers={"Content-Type": "text/plain"})))
    opener = Opener(rows)
    with main_seams(opener) as (_, stdout):
        assert subject.main([]) == 0
        value = json.loads(stdout.getvalue())
        assert value["status"] == "public_text_collected_pending_source_review"
        assert value["qualification"] is False and value["source_executed"] is False
    assert [call["url"] for call in opener.calls[2:]] == [RAW + C + "/" + path for path, _ in subject.FILES]
    assert len(opener.calls) == 21 and not opener.sequence


@case("post_serialization_deadline_retains_refusal")
def serialization_deadline():
    opener = Opener(binding_sequence())
    original_json, original_clock = subject.json_bytes, subject.Collection.clock
    crossed = [False]
    def serialized(value):
        raw = original_json(value)
        if type(value) is dict and "requests" in value and value.get("status") == "public_text_collected_pending_source_review":
            crossed[0] = True
        return raw
    def clock(self):
        if crossed[0]:
            raise subject.Refusal("Collection deadline exceeded")
        return original_clock(self)
    with main_seams(opener, mode="resolve", expected_commit=None, expected_ref_object=None) as (_, stdout), \
         patched(subject, "json_bytes", serialized), patched(MemoryCollection, "clock", clock):
        assert subject.main([]) == 2
        value = json.loads(stdout.getvalue())
        assert value["status"] == "refused" and value["intended_exit"] == 2
        assert json.loads(MemoryCollection.instances[-1].saved["receipt.json"])["status"] == "refused"


@case("collector_audit_predicates_direct_inert_calls")
def collector_policy():
    callbacks = []
    output = Path("E:/synthetic-never-created")
    with patched(subject.sys, "addaudithook", callbacks.append):
        subject.install_audit(output)
    assert len(callbacks) == 1
    policy = callbacks[0]
    policy("open", (str(output / "body-01.txt"), "xb", os.O_WRONLY | os.O_CREAT | os.O_EXCL))
    refused(lambda: policy("open", ("E:/outside.txt", "r", os.O_RDONLY)), "outside fixed output")
    refused(lambda: policy("open", (str(output / "body-01.txt"), "wb", os.O_WRONLY | os.O_CREAT)), "fresh output")
    refused(lambda: policy("import", ("not_preloaded",)), "late import")
    refused(lambda: policy("subprocess.Popen", ()), "Process")


@case("redirect_handler_never_follows")
def redirect_policy():
    assert subject.NoRedirect().redirect_request(None, None, 302, "moved", {}, "https://example.com") is None


results = []
started = time.monotonic()
for name, function in cases:
    try:
        function()
        results.append({"name": name, "status": "passed"})
    except Exception as error:
        frames, tb = [], error.__traceback__
        while tb is not None and len(frames) < 8:
            frames.append({"file": tb.tb_frame.f_code.co_filename, "line": tb.tb_lineno})
            tb = tb.tb_next
        results.append({"name": name, "status": "failed", "type": type(error).__name__,
                        "reason": str(error), "frames": frames})
assert len(cases) == len(set(name for name, _ in cases))
failed = sum(item["status"] == "failed" for item in results)
report = {"scope": "synthetic_fake_transport_only", "cases": results,
          "passed": len(results) - failed, "failed": failed,
          "elapsed_seconds": time.monotonic() - started, "startup_binding": True,
          "guard_denials": guard_denials, "collector_sha256": EXPECTED,
          "harness_sha256": hashlib.sha256(harness_bytes).hexdigest(),
          "network_or_real_path_calls": 0,
          "limitations": "Real TLS, DNS, CLI parsing and output filesystem are unexecuted; direct audit predicates are not OS isolation."}
report["qualification_exit"] = 1 if failed or guard_denials else 0
print(json.dumps(report, indent=2))
raise SystemExit(report["qualification_exit"])
