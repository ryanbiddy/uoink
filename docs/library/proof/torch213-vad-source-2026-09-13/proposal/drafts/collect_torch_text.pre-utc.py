"""Review proposal: fixed public text only; default mode never retrieves."""
import argparse
import encodings.ascii
import encodings.idna
import encodings.utf_8
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import stat
import sys
import time
import urllib.error
import urllib.request


TAG = "v2.13.0"
API = "https://api.github.com/repos/pytorch/pytorch/git/"
RAW = "https://raw.githubusercontent.com/pytorch/pytorch/"
ADMISSION = "reviewed-torch213-vad-public-text-only"
FORBIDDEN = r"C:\Users\hello\AppData\Local\Uoink\index.db"
FIXED_ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\torch213-vad-source-proposal01")
API_LIMIT = 16_384
TOTAL_LIMIT = 4 * 1024 * 1024
REQUEST_LIMIT = 24
SECONDS = 120.0
REQUEST_SECONDS = 10.0
HEX = re.compile(r"[0-9a-f]{40}\Z")
LABEL = re.compile(r"[a-z][a-z0-9-]{0,31}\Z")
FILES = (
    ("version.txt", 4096),
    ("torch/__init__.py", 196608),
    ("torch/__future__.py", 16384),
    ("torch/_tensor.py", 131072),
    ("torch/utils/_device.py", 32768),
    ("torch/nn/parameter.py", 32768),
    ("torch/nn/modules/module.py", 262144),
    ("torch/nn/modules/rnn.py", 131072),
    ("torch/nn/modules/conv.py", 98304),
    ("torch/nn/modules/instancenorm.py", 32768),
    ("torch/nn/modules/batchnorm.py", 65536),
    ("torch/nn/modules/linear.py", 32768),
    ("torch/nn/modules/pooling.py", 98304),
    ("torch/nn/modules/activation.py", 131072),
    ("torch/nn/modules/container.py", 65536),
    ("torch/nn/modules/utils.py", 16384),
    ("torch/nn/init.py", 65536),
    ("torch/nn/functional.py", 393216),
    ("torch/autograd/grad_mode.py", 32768),
)


class Refusal(Exception):
    pass


def require(value, reason):
    if not value:
        raise Refusal(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    raw = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii")
    require(len(raw) <= 128 * 1024, "Local receipt too large")
    return raw


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate API JSON key")
        result[key] = value
    return result


def api_json(raw):
    require(len(raw) <= API_LIMIT, "API body cap")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except (ValueError, UnicodeError, RecursionError):
        raise Refusal("Malformed API JSON") from None
    require(type(value) is dict, "API object required")
    return value


def oid(value):
    require(type(value) is str and HEX.fullmatch(value), "Exact lowercase Git object ID required")
    return value


def object_link(value):
    require(type(value) is dict, "Missing Git object link")
    kind = value.get("type")
    require(kind in ("tag", "commit"), "Unsupported Git object type")
    return kind, oid(value.get("sha"))


def allowed_url(url, mode, commit):
    if url == API + "ref/tags/" + TAG:
        return True
    for prefix in (API + "tags/", API + "commits/"):
        if url.startswith(prefix) and HEX.fullmatch(url[len(prefix):]):
            return True
    return (mode == "sources" and commit is not None
            and url in {RAW + commit + "/" + path for path, _ in FILES})


def check_chain(path, *, missing_leaf=False):
    """Observed alias checks only; caller must keep scratch directories quiescent."""
    require(path.is_absolute(), "Absolute local output required")
    for item in reversed((path, *path.parents)):
        try:
            info = item.lstat()
        except FileNotFoundError:
            require(missing_leaf and item == path, "Missing output ancestor")
            return
        require(not stat.S_ISLNK(info.st_mode)
                and not (getattr(info, "st_file_attributes", 0) & 0x400),
                "Output alias refused")
        require(stat.S_ISDIR(info.st_mode), "Output ancestor must be a directory")


def create_output(label):
    require(LABEL.fullmatch(label), "Restricted fresh label required")
    require(Path(__file__).absolute().parent == FIXED_ROOT, "Collector path mismatch")
    check_chain(FIXED_ROOT)
    retrievals = FIXED_ROOT / "retrievals"
    check_chain(retrievals, missing_leaf=True)
    if not retrievals.exists():
        retrievals.mkdir()
    check_chain(retrievals)
    output = retrievals / label
    require(not output.exists(), "Fresh label already exists")
    output.mkdir()
    check_chain(output)
    return output


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Collection:
    def __init__(self, output, mode, commit, opener):
        self.output, self.mode, self.commit = output, mode, commit
        self.opener = opener
        self.started = time.monotonic()
        self.body_bytes = 0
        self.records = []

    def clock(self):
        require(time.monotonic() - self.started <= SECONDS, "Collection deadline exceeded")

    def save(self, name, raw):
        require(re.fullmatch(r"[a-z0-9-]+\.(txt|json)", name), "Fixed local output name required")
        with (self.output / name).open("xb") as handle:
            handle.write(raw)

    def get(self, url, limit, kind):
        self.clock()
        require(allowed_url(url, self.mode, self.commit), "URL outside fixed public scope")
        require(len(self.records) < REQUEST_LIMIT, "Request limit")
        number = len(self.records) + 1
        record = {"ordinal": number, "url": url, "limit": limit, "kind": kind,
                  "status": "not_completed", "body_file": f"body-{number:02}.txt"}
        self.records.append(record)
        self.save(f"request-{number:02}.json", json_bytes(record))
        request = urllib.request.Request(url, headers={
            "User-Agent": "uoink-source-review/1.0",
            "Accept": "application/vnd.github+json" if kind == "api" else "text/plain",
            "Accept-Encoding": "identity",
        }, method="GET")
        response = None
        body = bytearray()
        oversized = False
        body_saved = False
        body_complete = False
        try:
            try:
                response = self.opener.open(request, timeout=REQUEST_SECONDS)
            except urllib.error.HTTPError as error:
                response = error  # retain the bounded failure body; never follow it
            code = response.code
            record["http_status"] = code
            require(response.geturl() == url, "Response URL changed")
            encoding = response.headers.get("Content-Encoding", "identity").lower()
            record["content_encoding"] = encoding
            require(encoding == "identity", "Encoded response refused")
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            record["content_type"] = content_type
            length = response.headers.get("Content-Length")
            if length is not None:
                require(re.fullmatch(r"[0-9]{1,10}", length), "Invalid response length")
                record["advertised_bytes"] = int(length)
                require(int(length) <= limit, "Advertised response exceeds cap")
            while True:
                self.clock()
                chunk = response.read(min(65536, limit + 1 - len(body)))
                if not chunk:
                    body_complete = True
                    break
                self.body_bytes += len(chunk)
                require(self.body_bytes <= TOTAL_LIMIT, "Total response byte cap")
                body.extend(chunk)
                if len(body) > limit:
                    oversized = True
                    del body[limit:]
                    break
            record["body_bytes"] = len(body)
            record["body_sha256"] = digest(body)
            record["truncated"] = oversized
            record["body_complete"] = body_complete
            self.save(record["body_file"], body)
            body_saved = True
            require(not oversized, "Response exceeds cap")
            require(code == 200, "HTTP response refused")
            require(content_type == ("application/json" if kind == "api" else "text/plain"),
                    "Unexpected successful response type")
            if length is not None:
                require(len(body) == int(length), "Response length mismatch")
            try:
                text = body.decode("utf-8")
            except UnicodeError:
                raise Refusal("Response is not UTF-8 text") from None
            require("\x00" not in text, "NUL in source text")
            require(not text.startswith("version https://git-lfs.github.com/spec/v1"), "LFS pointer is not source")
            self.clock()
            record["status"] = "text_collected"
            return bytes(body)
        except Refusal as error:
            record["status"] = "refused"
            record["reason"] = str(error)
            raise
        except Exception as error:
            record["status"] = "error"
            record["error_type"] = type(error).__name__
            raise
        finally:
            if response is not None:
                response.close()
            if body and not body_saved:
                record.update(body_bytes=len(body), body_sha256=digest(body),
                              body_complete=False, truncated=True)
                self.save(record["body_file"], body)
            self.save(f"response-{number:02}.json", json_bytes(record))


def resolve_binding(collection):
    ref = api_json(collection.get(API + "ref/tags/" + TAG, API_LIMIT, "api"))
    require(ref.get("ref") == "refs/tags/" + TAG, "Git ref mismatch")
    kind, current = object_link(ref.get("object"))
    initial = current
    chain = [{"type": kind, "sha": current}]
    for depth in range(2):
        if kind == "commit":
            break
        tag = api_json(collection.get(API + "tags/" + current, API_LIMIT, "api"))
        require(tag.get("sha") == current, "Git tag object identity mismatch")
        if depth == 0:
            require(tag.get("tag") == TAG, "Annotated tag name mismatch")
        kind, current = object_link(tag.get("object"))
        require(current not in {entry["sha"] for entry in chain}, "Git tag cycle")
        chain.append({"type": kind, "sha": current})
    require(kind == "commit", "Annotated tag depth exceeded")
    commit = api_json(collection.get(API + "commits/" + current, API_LIMIT, "api"))
    require(commit.get("sha") == current, "Git commit identity mismatch")
    require(type(commit.get("tree")) is dict, "Missing commit tree declaration")
    tree = oid(commit["tree"].get("sha"))
    return {"tag": TAG, "initial_ref_object": initial, "commit": current,
            "tree_declaration": tree, "chain": chain,
            "scope": "observed_official_API_binding_not_signed_writer_or_wheel_attestation"}


def install_audit(output):
    # All transport/JSON/hash imports are already loaded. Source bodies are data.
    def audit(event, args):
        if event == "import":
            raise Refusal("Unexpected late import")
        if event == "open":
            path = args[0]
            if isinstance(path, int):
                raise Refusal("Unexpected descriptor open")
            candidate = Path(os.path.abspath(os.fsdecode(path)))
            require(candidate.parent == output
                    and re.fullmatch(r"[a-z0-9-]+\.(txt|json)", candidate.name),
                    "Content open outside fixed output")
            require(bool(args[2] & os.O_EXCL) and bool(args[2] & os.O_CREAT),
                    "Only fresh output content opens allowed")
        if (event.startswith(("subprocess.", "ctypes.", "os.exec", "os.spawn"))
                or event in ("os.system", "os.startfile")):
            raise Refusal("Process or native loader operation refused")
    sys.addaudithook(audit)


def plan():
    return {"status": "preparation_only_no_retrieval", "tag_url": API + "ref/tags/" + TAG,
            "source_count": len(FILES), "source_body_cap_sum": sum(cap for _, cap in FILES),
            "files": [{"path": path, "url_template": RAW + "{REVIEWED_COMMIT_SHA}/" + path,
                       "cap": cap} for path, cap in FILES],
            "limits": {"api_bytes": API_LIMIT, "total_body_bytes": TOTAL_LIMIT,
                       "requests": REQUEST_LIMIT, "request_seconds": REQUEST_SECONDS,
                       "cooperative_seconds": SECONDS}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("plan", "resolve", "sources"), default="plan")
    parser.add_argument("--admission")
    parser.add_argument("--label")
    parser.add_argument("--expected-commit")
    parser.add_argument("--expected-ref-object")
    args = parser.parse_args(argv)
    if args.mode == "plan":
        print(json_bytes(plan()).decode("ascii"), end="")
        return 0
    collection = None
    receipt = {"status": "not_completed", "mode": args.mode, "qualification": False,
               "source_executed": False, "model_or_artifact_access": False}
    exit_code = 1
    try:
        require(args.admission == ADMISSION, "Explicit reviewed text collection admission required")
        require(os.environ.get("IG_FORBIDDEN_LIVE") == FORBIDDEN, "Startup binding absent")
        require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,
                "Required -I -S -B startup missing")
        require(type(args.label) is str and LABEL.fullmatch(args.label), "Fresh restricted label required")
        if args.mode == "sources":
            oid(args.expected_commit)
            oid(args.expected_ref_object)
        else:
            require(args.expected_commit is None and args.expected_ref_object is None,
                    "Resolve stage does not accept source-stage claims")
        # Initialize only stdlib TLS/transport before the content-open guard.
        context = ssl.create_default_context()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                            urllib.request.HTTPSHandler(context=context))
        output = create_output(args.label)
        collection = Collection(output, args.mode, args.expected_commit, opener)
        install_audit(output)
        collection.save("plan.json", json_bytes({**plan(), "mode": args.mode,
                        "expected_commit": args.expected_commit,
                        "expected_ref_object": args.expected_ref_object}))
        binding = resolve_binding(collection)
        receipt["binding"] = binding
        if args.mode == "sources":
            require(binding["commit"] == args.expected_commit
                    and binding["initial_ref_object"] == args.expected_ref_object,
                    "Observed tag binding differs from reviewed binding")
            urls = [{"url": RAW + args.expected_commit + "/" + path, "cap": cap}
                    for path, cap in FILES]
            collection.save("source-urls.json", json_bytes(urls))
            for entry in urls:
                collection.get(entry["url"], entry["cap"], "source")
        collection.clock()
        receipt["status"] = "public_text_collected_pending_source_review"
        exit_code = 0
    except Refusal as error:
        receipt.update(status="refused", reason=str(error))
        exit_code = 2
    except Exception as error:
        receipt.update(status="error", error_type=type(error).__name__)
        exit_code = 1
    if collection is not None:
        receipt.update(requests=collection.records, response_body_bytes=collection.body_bytes,
                       elapsed_seconds=time.monotonic() - collection.started,
                       intended_exit=exit_code)
        serialized = json_bytes(receipt)
        if exit_code == 0:
            try:
                collection.clock()
            except Refusal as error:
                exit_code = 2
                receipt.update(status="refused", reason=str(error), intended_exit=2)
                serialized = json_bytes(receipt)
        collection.save("receipt.json", serialized)
    print(json_bytes(receipt).decode("ascii"), end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
