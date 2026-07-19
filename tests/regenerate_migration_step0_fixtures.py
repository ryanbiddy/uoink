"""Regenerate the migration Step 0 HTTP characterization fixtures.

The scenarios use a real temporary SQLite index and the real HTTP handler.
They make loopback-only requests, patch clocks and generated IDs, and stub
the local taste read so the checked-in payloads are deterministic.

Run all:
    python tests/regenerate_migration_step0_fixtures.py

Check without writing:
    python tests/regenerate_migration_step0_fixtures.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from contextlib import ExitStack, contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import index as index_mod  # noqa: E402
import memory_layer  # noqa: E402
import scripts  # noqa: E402
import server  # noqa: E402
import workspaces  # noqa: E402
import writing_studio  # noqa: E402

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "migration_step0"
FIXTURES = {
    "workspace-assembly": {
        "path": FIXTURE_DIR / "workspace-assembly.json",
        "surface": "workspaces.py through /workspaces and /workspace/*",
    },
    "scripts": {
        "path": FIXTURE_DIR / "scripts.json",
        "surface": "scripts.py through /script/* and /scripts",
    },
    "writing": {
        "path": FIXTURE_DIR / "writing.json",
        "surface": "writing_studio.py through /writing/*",
    },
}


class _Clock:
    """Small deterministic clock shared by every write path in a scenario."""

    def __init__(self):
        self.tick = 0

    def __call__(self) -> str:
        self.tick += 1
        return f"2030-01-02T03:04:{self.tick:02d}Z"


class _QuietHandler(server.Handler):
    def log_message(self, format, *args):  # noqa: A002
        return


def _seed_yoink(idx, *, video_id: str, title: str, topic: str,
                hook_type: str, format: str, performance_tier: str,
                comments: list[dict] | None = None) -> None:
    idx.upsert_yoink({
        "video_id": video_id,
        "slug": f"fixture-{video_id}",
        "channel": "Synthetic Creator",
        "title": title,
        "topic": topic,
        "hook_type": hook_type,
        "yoinked_at": "2029-12-31T00:00:00Z",
        "corpus_path": f"fixtures/{video_id}/corpus.md",
        "sidecar_path": f"fixtures/{video_id}/sidecar.json",
        "metadata_json": json.dumps({"comments": comments or []}),
        "source_type": "youtube",
        "platform": "youtube",
        "author": "Synthetic Creator",
    }, content=f"Synthetic transcript for {title}.")
    idx.set_facets(
        video_id,
        format=format,
        performance_tier=performance_tier,
        length_bucket="short",
        topic=topic,
        hook_type=hook_type,
    )


def _seed_corpus(idx) -> None:
    _seed_yoink(
        idx,
        video_id="video-over",
        title="The concrete opener",
        topic="AI workflows",
        hook_type="curiosity_gap",
        format="talking_head",
        performance_tier="over",
        comments=[
            {"text": "Which step saves the most time?", "likes": 12},
            {"text": "This worked for me.", "likes": 4},
        ],
    )
    _seed_yoink(
        idx,
        video_id="video-average",
        title="A second useful example",
        topic="AI systems",
        hook_type="informative",
        format="talking_head",
        performance_tier="average",
        comments=[
            {"text": "Can this run locally?", "likes": 8},
        ],
    )
    _seed_yoink(
        idx,
        video_id="video-filtered",
        title="A filtered tutorial",
        topic="AI workflows",
        hook_type="curiosity_gap",
        format="tutorial",
        performance_tier="over",
    )
    idx.log_engagement(
        "video-over", "cite", "mcp", ts_utc="fixture-timestamp")
    idx.log_engagement(
        "video-average", "opened", "dashboard", ts_utc="fixture-timestamp")


@contextmanager
def _runtime(idx):
    clock = _Clock()
    with ExitStack() as stack:
        stack.enter_context(patch.object(server, "_get_index", lambda: idx))
        stack.enter_context(patch.object(
            server, "_read_settings",
            lambda: {"voice_dna_warnings_enabled": True},
        ))
        stack.enter_context(patch.object(
            workspaces, "_gen_workspace_id", lambda: "ws_fixture"))
        for module in (index_mod, workspaces, scripts, writing_studio):
            stack.enter_context(patch.object(module, "_now_iso", clock))
        stack.enter_context(patch.object(
            memory_layer,
            "read_taste",
            lambda *_args, **_kwargs: {
                "ok": True,
                "content": {"anchors": ["specific mechanisms", "plain claims"]},
            },
        ))
        yield


@contextmanager
def _http_server(idx):
    with _runtime(idx):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
        httpd.daemon_threads = True
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield int(httpd.server_address[1])
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)


def _call(port: int, method: str, path: str, payload=None) -> dict:
    headers = {
        "Content-Type": "application/json",
        "X-Uoink-Token": server.TOKEN,
    }
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=(json.dumps(payload).encode("utf-8")
              if payload is not None else None),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            status = response.status
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        status = error.code
        body = json.loads((error.read().decode("utf-8") or "{}"))
    interaction = {
        "request": {"method": method, "path": path},
        "status": status,
        "body": body,
    }
    if payload is not None:
        interaction["request"]["json"] = payload
    return interaction


def _workspace_assembly_scenario(idx, port: int) -> list[dict]:
    create = {
        "format": "talking_head",
        "topic": "AI",
        "hook_target": "curiosity_gap",
        "n_examples": 2,
        "notes": "Synthetic migration fixture",
    }
    assemble = {
        "workspace_id": "ws_fixture",
        "format": "talking_head",
        "topic": "AI",
        "hook_target": "curiosity_gap",
        "n_examples": 2,
    }
    critique = {
        "workspace_id": "ws_fixture",
        "draft_text": "Open on the saved hour, then show the three steps.",
    }
    findings = {
        **critique,
        "findings": {
            "hook_strength": "specific",
            "pacing_issues": ["The middle repeats the setup."],
            "missing_audience_hooks": ["Answer the local-run question."],
        },
    }
    return [
        _call(port, "POST", "/workspaces", create),
        _call(port, "POST", "/workspace/assemble", assemble),
        _call(port, "POST", "/workspace/critique", critique),
        _call(port, "POST", "/workspace/critique", findings),
        _call(port, "GET", "/workspace/ws_fixture"),
        _call(port, "GET", "/workspaces?limit=5"),
    ]


def _scripts_scenario(idx, port: int) -> list[dict]:
    workspaces.create_workspace(
        idx,
        format="talking_head",
        topic="AI",
        hook_target="curiosity_gap",
        n_examples=2,
    )
    first_script = {
        "target_length_sec": 45,
        "hook": "The slow part was not the model.",
        "beats": [
            {"label": "setup", "content": "Name the repeated task."},
            {"label": "proof", "content": "Show the saved hour."},
        ],
        "body": "A short synthetic script.",
        "cta": "Try the smallest repeatable step.",
        "source_yoinks": [
            {"video_id": "video-over", "why": "Concrete opener"},
        ],
    }
    revised_script = {
        "target_length_sec": 40,
        "hook": "One repeated task cost an hour.",
        "beats": [
            {"label": "setup", "content": "Show the task immediately."},
            {"label": "proof", "content": "Show the saved hour."},
        ],
        "body": "A tighter synthetic script.",
        "cta": "Automate one repeated step.",
        "source_yoinks": [
            {"video_id": "video-over", "why": "Concrete opener"},
        ],
    }
    return [
        _call(port, "POST", "/script/generate", {
            "workspace_id": "ws_fixture",
        }),
        _call(port, "POST", "/script/generate", {
            "workspace_id": "ws_fixture",
            "script": first_script,
        }),
        _call(port, "POST", "/script/shot-list", {"script_id": 1}),
        _call(port, "GET", "/script/1"),
        _call(port, "POST", "/script/revise", {
            "script_id": 1,
            "critique_findings": {"pacing": "Cut the setup."},
            "revision_target": "Open on the result.",
        }),
        _call(port, "POST", "/script/revise", {
            "script_id": 1,
            "revised_script": revised_script,
        }),
        _call(port, "GET", "/scripts?workspace_id=ws_fixture&limit=5"),
    ]


def _writing_scenario(idx, port: int) -> list[dict]:
    anchor = {
        "name": "Fixture voice",
        "source_type": "text",
        "source_value": "Short sentences. Concrete nouns. Show the mechanism.",
    }
    source = {"source_yoink_id": "video-over", "style_anchor_ids": [1]}
    credit = "via Synthetic Creator"
    body = f"One repeated task cost an hour. Three steps fixed it.\n\n{credit}"
    revision = (
        "One repeated task cost an hour. The first step removed half of it."
        f"\n\n{credit}"
    )
    return [
        _call(port, "POST", "/writing/style-anchors", anchor),
        _call(port, "GET", "/writing/style-anchors?active_only=1"),
        _call(port, "POST", "/writing/tweet", source),
        _call(port, "POST", "/writing/tweet", {
            **source,
            "body": body,
            "source_credit_line": credit,
            "angle": "saved time",
            "target_length": 180,
        }),
        _call(port, "GET", "/writing/1"),
        _call(port, "POST", "/writing/compose/validate", {
            "source_yoink_id": "video-over",
            "kind": "tweet",
            "tweets": ["One repeated task cost an hour."],
            "attribution_enabled": True,
        }),
        _call(port, "POST", "/writing/draft", {
            "source_yoink_id": "video-over",
            "kind": "tweet",
            "body": "A synthetic work in progress.",
            "source_credit_line": credit,
        }),
        _call(port, "GET", "/writing/draft/1"),
        _call(port, "POST", "/writing/1/revise", {
            "revision_target": "Make the proof concrete.",
            "body": revision,
            "source_credit_line": credit,
        }),
        _call(port, "POST", "/writing/tweet", {
            **source,
            "body": "This omits the required credit.",
            "source_credit_line": credit,
        }),
    ]


def generate_fixture(name: str) -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        idx = index_mod.Index.open(Path(temp_dir) / "index.db")
        try:
            _seed_corpus(idx)
            with _http_server(idx) as port:
                if name == "workspace-assembly":
                    interactions = _workspace_assembly_scenario(idx, port)
                elif name == "scripts":
                    interactions = _scripts_scenario(idx, port)
                elif name == "writing":
                    interactions = _writing_scenario(idx, port)
                else:  # pragma: no cover - argparse constrains this
                    raise ValueError(f"unknown fixture: {name}")
        finally:
            idx.close()
    return {
        "_fixture": {
            "surface": FIXTURES[name]["surface"],
            "regenerate": (
                "python tests/regenerate_migration_step0_fixtures.py "
                f"--fixture {name}"
            ),
            "check": (
                "python tests/regenerate_migration_step0_fixtures.py "
                f"--check --fixture {name}"
            ),
            "data": "synthetic",
            "network": "loopback only",
        },
        "interactions": interactions,
    }


def _render(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _check(name: str, rendered: str) -> bool:
    path = FIXTURES[name]["path"]
    if not path.exists():
        print(f"missing {path.relative_to(ROOT)}")
        return False
    if path.read_text(encoding="utf-8") != rendered:
        print(f"stale {path.relative_to(ROOT)}")
        return False
    print(f"ok {path.relative_to(ROOT)}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture",
        choices=["all", *FIXTURES],
        default="all",
        help="regenerate or check one named fixture",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if checked-in fixtures differ; do not write",
    )
    args = parser.parse_args()
    names = list(FIXTURES) if args.fixture == "all" else [args.fixture]
    clean = True
    for name in names:
        rendered = _render(generate_fixture(name))
        if args.check:
            clean = _check(name, rendered) and clean
            continue
        path = FIXTURES[name]["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
