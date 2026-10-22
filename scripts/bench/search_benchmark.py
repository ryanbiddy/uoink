#!/usr/bin/env python3
"""Benchmark a checkout's source search against a frozen, offline corpus.

Example (use new, empty output/work directories for every run)::

    python scripts/bench/search_benchmark.py --repo . --modes strict \
        --out _scratch/bench/run/results --workdir _scratch/bench/run/index

The snapshot's cleaned text already includes available transcripts. Feed it
unchanged to upsert_yoink; do not invent transcript timestamps or reread captures.
Optional modes use Index.search_<mode>(query, limit=...) or an explicitly
declared mode on Index.search(query, limit=..., mode=...). Unknown APIs skip;
there is no harness implementation of retrieval and no semantic fallback.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import hashlib
import importlib.util
import inspect
import json
import math
import ntpath
import os
from pathlib import Path
import platform
import re
import statistics
import sys
import textwrap
import time
from urllib.parse import urlparse


DEFAULT_CORPUS = Path("E:/AI/projects/uoink/experiments/search-jev-gemma-2026-09-23")
MODES = ("strict", "forgiving", "embedding", "hybrid")
GROUPS = ("keyword", "paraphrase", "constraints")
PUBLIC_HOSTS = {"x.com", "twitter.com", "youtube.com", "youtu.be", "reddit.com"}


def _path_key(path):
    # Recognize Windows paths even when tests run on Linux.
    value = os.fsdecode(path).replace("\\", "/")
    if value.startswith("//?/"):
        value = value[4:]
    return ntpath.normpath(value).replace("\\", "/").rstrip("/").casefold()


def _under(path, root):
    return path == root or path.startswith(root + "/")


def safe_path(path):
    """Reject live roots before resolution, then check symlink/junction targets."""
    roots = ["E:/Uoink", "E:/AI/_keys",
             str(Path.home() / "AppData/Local/Uoink"),
             str(Path.home() / ".local/share/Uoink"),
             str(Path.home() / "Library/Application Support/Uoink")]
    if os.environ.get("LOCALAPPDATA"):
        roots.append(os.environ["LOCALAPPDATA"] + "/Uoink")
    if os.environ.get("XDG_DATA_HOME"):
        roots.append(os.environ["XDG_DATA_HOME"] + "/Uoink")
    forbidden = os.environ.get("IG_FORBIDDEN_LIVE")
    if forbidden:
        roots.append(forbidden)
    key = _path_key(path)
    if any(_under(key, _path_key(root)) for root in roots):
        raise ValueError(f"refusing protected path: {path}")
    if re.search(r"(^|/)index\.db(?:$|[-.])", key):
        raise ValueError(f"refusing possible live index.db: {path}")
    resolved = Path(path).expanduser().resolve()
    key = _path_key(resolved)
    if any(_under(key, _path_key(root)) for root in roots):
        raise ValueError(f"refusing protected path: {path}")
    if re.search(r"(^|/)index\.db(?:$|[-.])", key):
        raise ValueError(f"refusing possible live index.db: {path}")
    return resolved


def fresh_directory(path):
    path = safe_path(path)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError(f"directory must be new or empty: {path}")
    path.mkdir(parents=True, exist_ok=True)
    return path


class OfflineGuard:
    """CLI-only Python audit hook. All writes stay in the two disposable roots.

    This protects accidental access by checkout Python code, including SQLite.
    It is not an OS sandbox for hostile code or native extensions.
    """

    def __init__(self, workdir, out):
        self.roots = [safe_path(workdir), safe_path(out)]
        self.database = self.roots[0] / "benchmark.sqlite3"

    def writable(self, path):
        resolved = safe_path(path)
        if not any(resolved.is_relative_to(root) for root in self.roots):
            raise ValueError(f"refusing write outside --workdir/--out: {path}")

    def __call__(self, event, args):
        if (event.startswith("socket.") and event != "socket.gethostname") or event in {
            "subprocess.Popen", "os.system", "os.posix_spawn", "os.exec", "os.spawn"
        }:
            raise RuntimeError(f"offline benchmark refuses {event}")
        if event == "open" and not isinstance(args[0], int):
            safe_path(args[0])
            mode, flags = args[1], args[2]
            if (mode and any(c in mode for c in "wax+")) or (
                flags and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
            ):
                self.writable(args[0])
        elif event == "sqlite3.connect":
            if args[0] != ":memory:" and safe_path(args[0]) != self.database:
                raise ValueError("refusing SQLite database outside disposable index")
        elif event in {"os.listdir", "os.scandir"}:
            if args[0] is not None and not isinstance(args[0], int):
                safe_path(args[0])
        elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.truncate"}:
            self.writable(args[0])
        elif event in {"os.rename", "os.link", "os.symlink"}:
            self.writable(args[0])
            self.writable(args[1])


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def source_id(url):
    """Experiment identity: exact URL bytes, no URL canonicalization."""
    return digest(url.encode("utf-8"))[:12]


def read_json(path):
    return json.loads(safe_path(path).read_text(encoding="utf-8"))


def load_corpus(corpus):
    corpus = safe_path(corpus)
    manifest = read_json(corpus / "manifest.json")
    protocol = read_json(corpus / "protocol.json")
    blobs = {}
    for name, expected in (
        ("documents.jsonl", manifest["documents_sha256"]),
        ("passages.jsonl", manifest["passages_sha256"]),
        ("queries.json", protocol["queries_sha256"]),
    ):
        blobs[name] = safe_path(corpus / name).read_bytes()
        if digest(blobs[name]) != expected:
            raise ValueError(f"frozen checksum mismatch: {name}")
    docs = [json.loads(line) for line in blobs["documents.jsonl"].splitlines() if line]
    queries = json.loads(blobs["queries.json"])
    ids = set()
    for doc in docs:
        host = (urlparse(doc["url"]).hostname or "").removeprefix("www.")
        if host not in PUBLIC_HOSTS or urlparse(doc["url"]).scheme not in {"http", "https"}:
            raise ValueError("source outside frozen public-platform allowlist")
        if doc["topic"] == "Job Hunt and Career" or doc["topic"].startswith("_"):
            raise ValueError("source outside frozen topic scope")
        if doc["id"] != source_id(doc["url"]) or doc["id"] in ids:
            raise ValueError("invalid or duplicate frozen source id")
        ids.add(doc["id"])
    if len(docs) != manifest["documents"]:
        raise ValueError("frozen document count mismatch")
    if len(queries) != 30 or len({q["id"] for q in queries}) != 30:
        raise ValueError("expected 30 distinct frozen queries")
    if any(sum(q["group"] == group for q in queries) != 10 for group in GROUPS):
        raise ValueError("expected ten frozen queries per group")
    if any(not q["targets"] or not set(q["targets"]) <= ids for q in queries):
        raise ValueError("query target outside frozen corpus")
    return docs, queries, {"manifest": manifest, "protocol": protocol}


@contextmanager
def checkout_index(repo):
    """Load index and its local dependencies from --repo, even in a test process."""
    repo = safe_path(repo)
    index_path = safe_path(repo / "index.py")
    names = {p.stem for p in repo.glob("*.py")}
    names.update(p.name for p in repo.iterdir() if p.is_dir() and (p / "__init__.py").is_file())
    saved = {k: v for k, v in sys.modules.items() if k.split(".")[0] in names}
    old_path = sys.path[:]
    old_bytecode = sys.dont_write_bytecode
    try:
        for name in saved:
            del sys.modules[name]
        sys.path.insert(0, str(repo))
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location("index", index_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["index"] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        for name in list(sys.modules):
            if name.split(".")[0] in names:
                del sys.modules[name]
        sys.modules.update(saved)
        sys.path[:] = old_path
        sys.dont_write_bytecode = old_bytecode


def mode_search(index, mode):
    """Only call declared modes; **kwargs alone is not evidence of support."""
    explicit = getattr(index, "search_" + mode, None)
    if callable(explicit):
        return lambda query: explicit(query, limit=30)
    search = getattr(index, "search", None)
    if not callable(search):
        return None
    params = inspect.signature(search).parameters
    # 3.11 keyword search takes match="forgiving" | "strict" and defaults to forgiving.
    if "match" in params and mode in ("strict", "forgiving"):
        return lambda query: search(query, limit=30, match=mode)
    if "mode" not in params:
        return (lambda query: search(query, limit=30)) if mode == "strict" else None
    declared = set(getattr(index, "SEARCH_MODES", ()))
    # Recognize explicit `mode == 'x'` / `mode in (...)` validation in a later
    # checkout without calling a permissive dispatcher with an unknown value.
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(search)))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "mode":
                for comparator in node.comparators:
                    declared.update(n.value for n in ast.walk(comparator)
                                    if isinstance(n, ast.Constant) and isinstance(n.value, str))
    except (OSError, TypeError, IndentationError, SyntaxError):
        pass
    if params["mode"].default in MODES:
        declared.add(params["mode"].default)
    if mode in declared:
        return lambda query: search(query, limit=30, mode=mode)
    return None


def ingest(index, docs, workdir):
    captures = safe_path(workdir / "sources")
    captures.mkdir()
    for doc in docs:
        path = safe_path(captures / (doc["id"] + ".md"))
        path.write_text(doc["text"], encoding="utf-8")
        sidecar = safe_path(path.with_suffix(".json"))
        sidecar.write_text(json.dumps({"video_id": doc["id"], "url": doc["url"],
                                       "title": doc["title"]}), encoding="utf-8")
        host = (urlparse(doc["url"]).hostname or "").removeprefix("www.")
        platform_name, kind = ("youtube", "video") if host in {"youtube.com", "youtu.be"} else (
            ("reddit", "reddit_thread") if host == "reddit.com" else ("x", "x_thread"))
        index.upsert_yoink({
            "video_id": doc["id"], "slug": doc["id"], "title": doc["title"],
            "topic": doc["topic"], "platform": platform_name, "source_type": kind,
            "corpus_path": str(path), "sidecar_path": str(sidecar),
            # Some frozen captures have no date. Satisfy the storage contract
            # with an empty value rather than inventing a capture timestamp.
            "yoinked_at": doc.get("captured_at") or "",
            "metadata_json": json.dumps({"url": doc["url"]}),
        }, content=doc["text"])


def map_results(results, docs):
    """Map source rows to frozen identities, deduplicating in retrieval order."""
    known = {doc["id"] for doc in docs}
    mapped = []
    rows = results["results"] if isinstance(results, dict) else results
    for row in rows:
        candidates = {row[k] for k in ("video_id", "doc_id", "id") if row.get(k) in known}
        metadata = row.get("metadata_json") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        for url in (row.get("url"), row.get("source_url"), metadata.get("url")):
            if url:
                candidate = source_id(url)
                if candidate in known:
                    candidates.add(candidate)
        if len(candidates) != 1:
            raise ValueError("unmapped or ambiguous search result identity")
        candidate = candidates.pop()
        if candidate not in mapped:
            mapped.append(candidate)
    return mapped


def rank_metrics(ranking, targets):
    rank = next((i for i, key in enumerate(ranking[:30], 1) if key in targets), None)
    return {"target_rank": rank, **{f"hit{k}": int(rank is not None and rank <= k)
                                  for k in (1, 5, 10, 30)},
            "mrr30": 1 / rank if rank else 0.0, "zero_results": int(not ranking)}


def percentile(values, fraction):
    """Linear interpolation, matching numpy.percentile's default estimator."""
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def aggregate(rows):
    samples = [value for row in rows for value in row["seconds"]]
    return {"n": len(rows),
            **{key: sum(row[key] for row in rows) for key in
               ("hit1", "hit5", "hit10", "hit30", "zero_results")},
            "mrr30": statistics.mean(row["mrr30"] for row in rows) if rows else None,
            "latency_samples": len(samples), "p50_seconds": percentile(samples, .5),
            "p95_seconds": percentile(samples, .95)}


def evaluate(search, docs, queries, mode, repeats):
    if repeats < 1:
        raise ValueError("repeats must be positive")
    # One full untimed pass. Mapping and scoring are outside the timed region.
    rankings = [map_results(search(q["query"]), docs) for q in queries]
    timings = [[] for _ in queries]
    for _ in range(repeats):
        for number, query in enumerate(queries):
            start = time.perf_counter()
            results = search(query["query"])
            elapsed = time.perf_counter() - start
            if map_results(results, docs) != rankings[number]:
                raise RuntimeError(f"ranking changed between repeats: {mode}/{query['id']}")
            timings[number].append(elapsed)
    rows = [{"kind": "query", "mode": mode, "query_id": q["id"], "group": q["group"],
             "query": q["query"], "targets": q["targets"], "ranking": ranking,
             "seconds": seconds, **rank_metrics(ranking, q["targets"])}
            for q, ranking, seconds in zip(queries, rankings, timings)]
    titles = []
    for doc in docs:
        ranking = map_results(search(doc["title"]), docs)
        titles.append({"kind": "exact_title", "mode": mode, "source_id": doc["id"],
                       "query": doc["title"], "first_id": ranking[0] if ranking else None,
                       "passed": bool(ranking and ranking[0] == doc["id"])})
    metrics = {"status": "ok", "all": aggregate(rows),
               "groups": {g: aggregate([r for r in rows if r["group"] == g]) for g in GROUPS},
               "exact_title": {"passed": sum(row["passed"] for row in titles), "n": len(titles)}}
    return metrics, rows + titles


def summary(metrics):
    lines = ["# Search benchmark", "",
             f"Checkout: `{metrics['repo']}`. Index SHA-256: `{metrics['index_sha256']}`.", "",
             f"{metrics['documents']} sources; {metrics['queries']} queries; one warm-up pass; "
             f"{metrics['repeats']} timed repeats. Python {metrics['python']}; CPU {metrics['cpu']}.", "",
             "| Mode / group | First | Top 5 | Top 10 | Empty | MRR@30 | Median / p95 ms |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for mode, data in metrics["modes"].items():
        if data["status"] == "skipped":
            continue
        for group, row in {"all": data["all"], **data["groups"]}.items():
            if not row["n"]:
                continue
            lines.append(f"| {mode} / {group} | {row['hit1']}/{row['n']} | {row['hit5']}/{row['n']} | "
                         f"{row['hit10']}/{row['n']} | {row['zero_results']} | {row['mrr30']:.4f} | "
                         f"{row['p50_seconds'] * 1000:.3f} / {row['p95_seconds'] * 1000:.3f} |")
    lines.append("")
    for mode, data in metrics["modes"].items():
        if data["status"] == "skipped":
            lines.append(f"{mode}: {data['reason']}.")
        else:
            title = data["exact_title"]
            lines.append(f"{mode} exact-title first: {title['passed']}/{title['n']}.")
    lines.extend(["", "Known-target hits use incomplete labels, not precision or complete recall. "
                  "Latency pools all timed query calls and excludes ingestion, mapping and title checks. "
                  "The frozen replay used a standalone FTS table; this run uses the checkout's "
                  "schema, tokenizer, ranking and result materialization. Cleaned transcript text is "
                  "included as source content; timestamp/clip retrieval is not measured.", ""])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--modes", default=",".join(MODES))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args(argv)
    modes = list(dict.fromkeys(part.strip() for part in args.modes.split(",")))
    if not modes or any(mode not in MODES for mode in modes) or args.repeats < 1:
        parser.error("use strict,forgiving,embedding,hybrid and --repeats >= 1")
    repo, corpus, out, workdir = map(safe_path, (args.repo, args.corpus, args.out, args.workdir))
    for destination in (out, workdir):
        for frozen_root in (corpus, safe_path(DEFAULT_CORPUS)):
            if destination.is_relative_to(frozen_root) or frozen_root.is_relative_to(destination):
                raise ValueError("output/work directory must not overlap the frozen corpus")
        if destination == repo or repo.is_relative_to(destination):
            raise ValueError("output/work directory must not contain the measured checkout")
    if out.is_relative_to(workdir) or workdir.is_relative_to(out):
        raise ValueError("--out and --workdir must be separate directories")
    fresh_directory(out)
    fresh_directory(workdir)
    # platform.processor() can invoke a local uname subprocess on Linux. Gather
    # runtime metadata before the audit hook forbids checkout child processes.
    runtime = {"python": platform.python_version(), "python_executable": sys.executable,
               "cpu": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER") or platform.machine(),
               "logical_cpus": os.cpu_count(), "platform": platform.platform()}
    sys.dont_write_bytecode = True
    sys.addaudithook(OfflineGuard(workdir, out))
    docs, queries, frozen = load_corpus(corpus)
    metrics = {"schema_version": 1, "repo": str(repo), "corpus": str(corpus),
               "index_sha256": digest(safe_path(repo / "index.py").read_bytes()),
               "frozen": frozen, "documents": len(docs), "queries": len(queries),
               "repeats": args.repeats, "warmup_passes": 1,
               "latency_estimator": "pooled calls, linear percentile interpolation",
               **runtime, "modes": {}}
    records = []
    with checkout_index(repo) as module:
        with module.Index.open(workdir / "benchmark.sqlite3") as index:
            ingest(index, docs, workdir)
            for mode in modes:
                search = mode_search(index, mode)
                if search is None:
                    reason = "not available in this checkout"
                    print(f"{mode}: {reason}", flush=True)
                    metrics["modes"][mode] = {"status": "skipped", "reason": reason}
                    continue
                print(f"Measuring {mode}: {len(queries)} queries, {args.repeats} repeats", flush=True)
                metrics["modes"][mode], rows = evaluate(search, docs, queries, mode, args.repeats)
                records.extend(rows)
    (out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "per-query.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")
    report = summary(metrics)
    (out / "summary.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"search benchmark: {exc}", file=sys.stderr)
        raise SystemExit(1)
