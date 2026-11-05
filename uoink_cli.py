"""Agent CLI: one registry envelope per call, with no HTTP proxy.

The root uoink launchers send agent subcommands here and everything else to
server.py. The installed cli launcher runs this module with bundled Python;
pin sys.path for Python's embedded ._pth mode.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import threading
import time

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import uoink_install_isolation as isolation  # noqa: E402


# Mirrors uoink_mcp_tools.STDIO_TOOLSETS without importing the registry at parse time.
TOOLSETS = ("full", "core", "search", "research")


class UsageError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--text", dest="text_output", action="store_true", default=argparse.SUPPRESS,
                        help="short human rendering instead of JSON")
    root = Parser(prog="uoink", parents=[common], description=__doc__)
    sub = root.add_subparsers(dest="command")
    def command(name, **kw):
        return sub.add_parser(name, parents=[common], **kw)
    listing = command("tools", help="list registry tools")
    listing.add_argument("--toolset", choices=TOOLSETS, default="full")
    listing.add_argument("--json", action="store_true", help="include client input schemas")
    call = command("call", help="call any registry tool")
    call.add_argument("tool")
    source = call.add_mutually_exclusive_group()
    source.add_argument("--args")
    source.add_argument("--args-file", type=Path)
    call.add_argument("pairs", nargs="*", metavar="key=value")
    search = command("search", help="bounded library search with stored timing")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    capture = command("capture", help="route a URL through existing capture tools")
    capture.add_argument("url")
    recent = command("recent")
    recent.add_argument("--limit", type=int, default=20)
    get = command("get", help="get a bounded library card by item id")
    get.add_argument("id")
    get.add_argument("--slug", action="store_true", help="interpret id as a slug")
    imports = command("import-list", help="queue every video in a HackerTube list, HN thread, "
                      "Reddit thread or YouTube playlist (50 per batch)")
    imports.add_argument("url")
    imports.add_argument("--limit", type=int, default=50, help="videos per batch, 1-50 (default 50)")
    imports.add_argument("--offset", type=int, default=0,
                         help="start position; use the printed next offset for the next batch")
    imports.add_argument("--preview", action="store_true", help="count without queueing")
    saves = command("import", help="import Watch Later, Reddit saves or X bookmarks from a file")
    saves.add_argument("file", type=Path)
    saves.add_argument("--source", choices=("watch_later", "x_bookmarks", "reddit_saved"))
    saves.add_argument("--limit", type=int, default=50, help="items per batch, 1-50 (default 50)")
    saves.add_argument("--offset", type=int, default=0, help="start position in the staged list")
    saves.add_argument("--preview", action="store_true", help="count without queueing")
    research = command("research", help="discover sources, capture evidence and publish a research report")
    research.add_argument("words", nargs="+", metavar="QUESTION|status|publish|open|list")
    research.add_argument("--sources", help="comma-separated source kinds (library,youtube,podcast,hn,hackertube)")
    research.add_argument("--max", dest="max_sources", type=int, help="maximum sources (default 12)")
    research.add_argument("--asr-minutes", type=int, help="ASR budget in minutes (default 120)")
    research.add_argument("--since", help="only sources published since YYYY-MM-DD")
    research.add_argument("--yes", action="store_true", help="capture the top candidates without prompting")
    research.add_argument("--no-wait", action="store_true", help="return after queueing captures")
    research.add_argument("--wait-minutes", type=float, help="maximum capture wait (default 30)")
    research.add_argument("--claims", type=Path, help="publish payload JSON, without run_id")
    research.add_argument("--json", action="store_true", help="one JSON result on stdout (the default)")
    research.add_argument("--explain", action="store_true", help="show the full candidate score breakdown")
    note = command("note")
    note.add_argument("text")
    note.add_argument("--title")
    command("status")
    connect = command("connect", help="print local connection recipes; never writes client files")
    connect.add_argument("client", nargs="?")
    connect.add_argument("--list", action="store_true")
    connect.add_argument("--deeplink", action="store_true", help="print a Cursor or VS Code install link")
    connect.add_argument("--toolset", choices=TOOLSETS, default=None,
                         help="tools to serve: full (99), core (36), search (9) or research (7); default full, core for Cursor")
    skill = command("skill")
    skill_sub = skill.add_subparsers(dest="skill_command", required=True)
    skill_sub.add_parser("path")
    install = skill_sub.add_parser("install")
    install.add_argument("--to", type=Path, required=True, help="parent skills directory; copies into <dir>/uoink")
    install.add_argument("--force", action="store_true")
    serve = command("serve", help="run the original helper CLI; remaining args pass through")
    serve.add_argument("server_args", nargs=argparse.REMAINDER)
    # No --text: the session speaks only JSON-RPC. The toolset stays an env var,
    # as it is for uoink_mcp.py.
    sub.add_parser("mcp", help="run the stdio MCP server for an agent client",
                   formatter_class=argparse.RawDescriptionHelpFormatter,
                   description="Run the stdio MCP server in this process, the same server as uoink_mcp.py.\n"
                               "Stdout carries only JSON-RPC; logs and warnings go to stderr.\n"
                               "UOINK_MCP_TOOLSET=core, search or research serves a smaller toolset (default: full).",
                   epilog='Client config: "command": "uoink", "args": ["mcp"]\n'
                          'Windows clients that cannot start .cmd files: "command": "cmd", '
                          '"args": ["/c", "uoink", "mcp"]')
    return root


def strict_json(text):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise UsageError(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    def constant(value):
        raise UsageError(f"non-finite JSON number: {value}")
    def number(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise UsageError(f"non-finite JSON number: {value}")
        return parsed
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant, parse_float=number)


def arguments(ns):
    if ns.pairs and (ns.args is not None or ns.args_file is not None):
        raise UsageError("use one of --args, --args-file, or key=value arguments")
    if ns.args is not None or ns.args_file is not None:
        try:
            raw = ns.args if ns.args is not None else ns.args_file.read_text(encoding="utf-8-sig")
            result = strict_json(raw)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise UsageError(f"cannot read JSON arguments: {exc}") from exc
        if not isinstance(result, dict):
            raise UsageError("arguments must be a JSON object")
        return result
    result = {}
    for pair in ns.pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise UsageError(f"expected key=value: {pair}")
        if key in result:
            raise UsageError(f"duplicate argument: {key}")
        try:
            result[key] = strict_json(value)
        except json.JSONDecodeError:
            result[key] = value
    return result


def backend():
    # server configures its logger at import. Both imports and handler prints
    # belong on stderr so stdout stays one JSON value even during captures.
    import server
    import uoink_mcp_tools
    uoink_mcp_tools.bind_backend(server)
    return server


# Registry tool and argument for each server._classify_capture_url source.
# The helper's Uoink Relay poller routes through this same map.
CAPTURE_TOOLS = {
    "youtube_video": ("uoink_video", "url"),
    "youtube_playlist": ("uoink_playlist", "url"),
    "short_video": ("uoink_url", "url"),
    "x_video": ("uoink_url", "url"),
    "x_article": ("uoink_page", "url"),
    "reddit_thread": ("uoink_reddit_thread", "url"),
    "podcast_feed": ("add_podcast_feed", "feed_url"),
    "web_page": ("uoink_page", "url"),
}


def friendly_call(ns, server):
    if ns.command == "call":
        return ns.tool, arguments(ns)
    if ns.command == "search":
        return "search_library", {"query": ns.query, "limit": ns.limit}
    if ns.command == "recent":
        return "list_recent_uoinks", {"limit": ns.limit}
    if ns.command == "get":
        return "get_library_item", {"slug" if ns.slug else "video_id": ns.id}
    if ns.command in ("import-list", "import"):
        if not 1 <= ns.limit <= 50:
            raise UsageError("--limit must be from 1 to 50")
        if ns.offset < 0:
            raise UsageError("--offset must be 0 or more")
        source = ({"file": str(ns.file.resolve()), **({"source": ns.source} if ns.source else {})}
                  if ns.command == "import" else {"url": ns.url})
        return "import_list", {**source, "limit": ns.limit, "offset": ns.offset,
                               **({"preview_only": True} if ns.preview else {})}
    if ns.command == "note":
        return "uoink_note", {"text": ns.text, **({"title": ns.title} if ns.title is not None else {})}
    route = server._classify_capture_url(ns.url)
    if not route.get("ok") or route["source"] not in CAPTURE_TOOLS:
        raise UsageError(route.get("note") or "unsupported capture URL")
    name, key = CAPTURE_TOOLS[route["source"]]
    return name, {key: route["canonical"]}


def error_text(payload):
    error = payload.get("error", "operation failed")
    if isinstance(error, dict):
        return f"{error.get('code', 'error')}: {error.get('message', error)}"
    return str(error)


def research_action(ns):
    """Reserve command tokens; a quoted multiword question remains a question."""
    import re
    import research
    words = ns.words
    action, value = "question", " ".join(words)
    if words[0] == "list":
        if len(words) != 1:
            raise UsageError("research list takes no run_id or question; quote a multiword question")
        action, value = "list", None
    elif words[0] in {"status", "publish", "open"}:
        if len(words) != 2 or not re.fullmatch(research.RUN_ID_PATTERN, words[1]):
            raise UsageError(f"research {words[0]}: invalid or missing run_id; quote a multiword question")
        action, value = words
    if action != "question":
        for flag, attr in (("--sources", "sources"), ("--max", "max_sources"),
                           ("--asr-minutes", "asr_minutes"), ("--since", "since"),
                           ("--yes", "yes"), ("--no-wait", "no_wait"), ("--wait-minutes", "wait_minutes")):
            if getattr(ns, attr) is not None and getattr(ns, attr) is not False:
                raise UsageError(f"{flag} requires a research question")
    if ns.claims is not None and action != "publish":
        raise UsageError("--claims requires research publish and a valid run_id")
    if action == "publish" and ns.claims is None:
        raise UsageError("research publish requires --claims claims.json")
    return action, value


def terminal_label(value):
    # Escape controls, not ordinary quotes or backslashes in saved text.
    return "".join(char if char.isprintable() else json.dumps(char, ensure_ascii=True)[1:-1]
                   for char in str(value))


def text_timestamp(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return ""
    minutes, seconds = divmod(int(value), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def text_excerpt(value, limit=140, *, truncated=False):
    text = terminal_label(" ".join(str(value).split()))
    if len(text) > limit:
        text = text[:limit - 1].rsplit(" ", 1)[0].rstrip()
        truncated = True
    return text.rstrip("\u2026") + "\u2026" if truncated else text


def text_library_row(row, index):
    # The frozen recent envelope omits kind, channel and video_id. Enrich a
    # display-only copy from the local index; never change the tool result.
    if index is None:
        return row
    try:
        identity = row.get("item_id") or row.get("video_id")
        item = (index.get_yoink(identity) if identity else
                index.get_by_slug(row["slug"]) if row.get("slug") else None)
    except (OSError, sqlite3.Error):
        return row
    if item and not item.get("deleted_at"):
        import podcasts
        return podcasts.repair_corpus_titles(index, [{**item, **row}])[0]
    return row


def text_kind(row):
    kind = row.get("source_type") or row.get("kind") or row.get("platform")
    if not kind:
        identity = row.get("item_id") or row.get("video_id") or ""
        kind = next((kind for prefix, kind in (("note_", "note"), ("page_", "article"),
                    ("ep_", "podcast"), ("episode_", "podcast")) if identity.startswith(prefix)), "item")
    return {"page": "article", "x_article": "article", "youtube": "video",
            "youtube_video": "video", "short_video": "video", "x_video": "video",
            "x_thread": "thread", "reddit_thread": "thread"}.get(kind, kind)


def text_source(row):
    source = row.get("channel") or row.get("author")
    if not source:
        from urllib.parse import urlsplit
        try:
            source = urlsplit(row.get("source_link") or row.get("source_url") or row.get("url") or "").hostname
        except ValueError:
            pass
    return source or ("local" if text_kind(row) == "note" else "source unknown")


def text_quote(row):
    passage, preview = row.get("passage"), row.get("preview")
    quote, truncated = "", False
    if row.get("passage_verified") is True:
        quote = passage.get("text", "") if isinstance(passage, dict) else passage or ""
        if not quote and isinstance(preview, dict):
            quote, truncated = preview.get("text", ""), preview.get("truncated", False)
    if not quote and row.get("quote_verified") is True:
        quote = row.get("quote", "")
    return text_excerpt(quote, truncated=truncated) if isinstance(quote, str) and quote.strip() else ""


def research_candidate_text(rank, candidate, *, explain=False):
    duration = text_timestamp(candidate.get("duration_s")) or "duration unknown"
    estimate = candidate.get("est_capture") or "unknown"
    if candidate.get("in_library"):
        status = "saved in library"
    elif candidate.get("has_captions") is True or estimate == "captions":
        status = "captions available"
    else:
        status = "no captions" if candidate.get("has_captions") is False else "captions unknown"
        if estimate != "unknown":
            status += "; " + estimate
    line = (f"{rank}. {terminal_label(candidate.get('title') or 'Untitled')} | "
            f"{terminal_label(candidate.get('channel') or 'source unknown')} | {duration} | "
            f"{terminal_label(status)}")
    reasons = candidate.get("why_ranked", [])
    if explain:
        why = "; ".join(reasons)
    else:
        parts = []
        for reason in reasons:
            name, sep, value = reason.rpartition(":")
            try:
                score = round(float(value), 2)
            except ValueError:
                continue
            if sep and math.isfinite(score) and score:
                parts.append(f"{name.strip()}: {score:+.2f}")
        why = "; ".join(parts)
    return line + (f"\n   Why: {terminal_label(why)}" if why else "")


def research_progress(status):
    counts = status.get("counts", {})
    return (f"{status.get('ready_count', 0)} ready; "
            f"{counts.get('queued', 0)} queued; "
            f"{counts.get('capturing', 0) + counts.get('asr_running', 0)} capturing; "
            f"{counts.get('failed', 0)} failed. "
            f"ASR budget left: {status.get('asr_minutes_left', 0)} min.")


def research_command(ns, server, *, call_tool=None, sleep=None, clock=None,
                     stdin=None, progress=None, opener=None):
    """Orchestrate existing tools; injectable I/O keeps the workflow offline-testable."""
    import research
    import uoink_agent_runtime as runtime
    call_tool = call_tool or (lambda name, args: runtime.call_tool(name, args, server))
    sleep, clock = sleep or time.sleep, clock or time.monotonic
    stdin = sys.stdin if stdin is None else stdin
    progress = progress or (lambda text: print(text, file=sys.stderr, flush=True))
    action, value = research_action(ns)
    if action == "list":
        return research.recent_runs(server.DATA_ROOT)
    if action == "status":
        return call_tool("research_status", {"run_id": value})
    if action == "publish":
        try:
            draft = strict_json(ns.claims.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise UsageError(f"cannot read claims JSON: {exc}") from exc
        if not isinstance(draft, dict) or "run_id" in draft:
            raise UsageError("claims file must be a publish payload object without run_id")
        payload = {**draft, "run_id": value}
        research.normalize_publish(payload)
        return call_tool("research_publish", payload)
    if action == "open":
        path = research.report_file(server.DATA_ROOT, value)
        if opener is None:
            import webbrowser
            opener = webbrowser.open
        opened = opener(path.as_uri())
        if opened is False:
            return {"ok": False, "error": "Could not open the report in the default browser.", "path": str(path)}
        return {"ok": True, "run_id": value, "path": str(path)}

    wait_minutes = 30 if ns.wait_minutes is None else ns.wait_minutes
    if not math.isfinite(wait_minutes) or wait_minutes < 0:
        raise UsageError("--wait-minutes must be a finite number of 0 or more")
    scope = {"question": value, "max_sources": 12 if ns.max_sources is None else ns.max_sources,
             "max_asr_minutes": 120 if ns.asr_minutes is None else ns.asr_minutes}
    if ns.sources is not None:
        scope["source_kinds"] = [kind.strip() for kind in ns.sources.split(",")]
    if ns.since is not None:
        scope["since"] = ns.since
    scope = research.normalize_scope(scope)
    start = call_tool("research_start", scope)
    if start.get("ok") is not True:
        return start
    run_id = research.validate_run_id(start["run_id"])
    needs_consent = start.get("needs_consent", [])
    consent_help = ""
    if needs_consent:
        consent_help = ("Network sources need consent: " + ", ".join(needs_consent) + ". "
                        'Enable them in Settings or POST /settings {"research_network_sources": '
                        + json.dumps(needs_consent) + "} (include any sources you already enabled).")
        progress(consent_help)
    discovery = call_tool("research_discover", {"run_id": run_id,
                          "queries": research.heuristic_queries(scope["question"])})
    if discovery.get("ok") is not True:
        return {**discovery, "run_id": run_id}
    candidates = discovery.get("candidates", [])
    for rank, candidate in enumerate(candidates, 1):
        progress(research_candidate_text(rank, candidate, explain=ns.explain))
    for skipped in discovery.get("skipped", []):
        progress(terminal_label(f"Skipped {skipped.get('kind', '')}: {skipped.get('reason', '')}"))
    for error in discovery.get("errors", []):
        progress(terminal_label(f"Discovery {error.get('kind', '')}: {error.get('code', 'failed')}"))
    top = min(scope["max_sources"], len(candidates))
    result = {"ok": True, "run_id": run_id, "scope": scope, "discovery": discovery,
              "needs_consent": needs_consent, "consent_help": consent_help,
              "captured": False, "timed_out": False,
              "prompt": research.continuation_prompt(run_id, scope["question"])}
    confirmed = ns.yes
    if top and not confirmed and stdin.isatty():
        progress(f"Capture the top {top}? [y/N]")
        confirmed = stdin.readline().strip().casefold() in {"y", "yes"}
    if not top or not confirmed:
        result["next_step"] = (f"No capture started. Continue this run with: uoink call research_capture "
                               f"run_id={run_id} top={top}. Use --yes to capture without a TTY on a new run."
                               if top else "No candidates found. Enable sources in Settings or try more focused queries.")
        progress(result["next_step"])
        return result
    capture = call_tool("research_capture", {"run_id": run_id, "top": top})
    result["capture"] = capture
    if capture.get("ok") is not True:
        return {**result, "ok": False, "error": error_text(capture)}
    result["captured"] = True
    eta = capture.get("eta", {})
    progress(f"Capture queued. Estimated {eta.get('min_minutes', '?')}-{eta.get('max_minutes', '?')} min.")
    if capture.get("message"):
        progress(terminal_label(capture["message"]))
    for skipped in capture.get("skipped", []):
        progress(terminal_label(f"Skipped {skipped.get('key', '')}: {skipped.get('reason', '')}"))
    if ns.no_wait:
        return result
    deadline = clock() + wait_minutes * 60
    while True:
        status = call_tool("research_status", {"run_id": run_id})
        result["status"] = status
        if status.get("ok") is not True:
            return {**result, "ok": False, "error": error_text(status)}
        progress(research_progress(status))
        if status.get("done") is True:
            return result
        remaining = deadline - clock()
        if remaining <= 0:
            result.update(ok=False, timed_out=True, code="wait_timeout",
                          error=f"Capture wait timed out. Check progress with: uoink research status {run_id}")
            return result
        sleep(min(10, remaining))


def human(payload, *, index=None):
    if "prompt" in payload and "run_id" in payload:
        lines = [f"Research run: {payload['run_id']}"]
        if payload.get("status"):
            lines.append(research_progress(payload["status"]))
        for key in ("error", "next_step"):
            if payload.get(key):
                lines.append(terminal_label(payload[key]))
        if payload.get("ok") is True or payload.get("captured"):
            lines.extend(["Paste this prompt into your agent:", payload["prompt"]])
        return "\n\n".join(lines)
    if payload.get("ok") is not True:
        return error_text(payload)
    if "tools" in payload:
        return "\n".join(f"{tool['name']}: {tool['description']}" for tool in payload["tools"])
    if "data_dir" in payload:
        return (f"Uoink {payload['version']}\nData: {payload['data_dir']}\n"
                f"Helper: {'running' if payload['helper_running'] else 'not running'}\n"
                f"Tools: {payload['tool_counts']['full']} full, {payload['tool_counts']['core']} core")
    def label(value):
        return terminal_label(value)[:240]
    def capture_limits(value):
        evidence = value.get("x_capture") if isinstance(value, dict) else None
        if not isinstance(evidence, dict):
            return ""
        from uoink_core.x_evidence import summary_lines
        return "\n" + "\n".join(label(line) for line in summary_lines(evidence))
    if "clients" in payload:
        return "\n".join(payload["clients"])
    if "runs" in payload:
        return "\n".join(f"{r['run_id']}  {label(r['question'])}" for r in payload["runs"]) or "No research runs yet."
    if "verification" in payload and "report_html_path" in payload:
        stats = payload["verification"]["stats"]
        return (f"{stats['accepted']} accepted, {stats['flagged']} flagged, {stats['dropped']} dropped.\n"
                + "\n".join(label(payload[key]) for key in ("report_md_path", "report_html_path", "verification_path")))
    if "ready_count" in payload and "run_id" in payload:
        return research_progress(payload)
    if isinstance(payload.get("source"), dict) and "found" in payload:
        source = payload["source"]
        heading = label(source.get("label") or source.get("title") or "")
        title = label(source.get("title") or "")
        if title and title != heading:
            heading += f": {title}"
        lines = [heading, label(payload.get("message") or "")]
        if source.get("url"):
            lines.append(f"List: {label(source['url'])}")
        if payload.get("truncated"):
            lines.append("Staged the first 5000 items.")
        if source.get("credit"):
            lines.append(label(source["credit"]))
        if payload.get("next_offset") is not None:
            lines.append(f"Next batch: uoink import-list {label(source.get('url') or '')} "
                         f"--offset {payload['next_offset']}")
        return "\n".join(line for line in lines if line)
    if "hits" in payload or "yoinks" in payload:
        rows = payload.get("hits", payload.get("yoinks", []))
        lines = [f"{len(rows)} result(s)"]
        for row in rows[:10]:
            row = text_library_row(row, index)
            identity = row.get("item_id") or row.get("video_id") or row.get("slug") or ""
            title, source = label(row.get("title") or identity), label(text_source(row))
            kind = label(text_kind(row))
            if "hits" in payload:
                start, end = text_timestamp(row.get("start")), text_timestamp(row.get("end"))
                timing = start + (f"\u2013{end}" if end and row["end"] >= row["start"] else "") if start else kind
                line = f"{title} | {source} | {timing}"
            else:
                date = label(str(row.get("yoinked_at") or "")[:10]) or "date unknown"
                line = f"{date} | {kind} | {title} | {source}"
            lines.append(line + (f" [{terminal_label(identity)}]" if identity else ""))
            if "hits" in payload:
                quote = text_quote(row)
                if quote:
                    lines.append(f'  "{quote}"')
        if len(rows) > 10:
            lines.append("More results in JSON output.")
        return "\n".join(lines)
    if "card" in payload:
        card = payload["card"]
        return (f"{label(card.get('title') or payload.get('item_id', 'Item'))}\n"
                f"ID: {label(payload.get('item_id', ''))}\nUse JSON output for excerpts and source revisions."
                + capture_limits(card))
    if "video_id" in payload and "title" in payload:
        return (f"Saved: {label(payload['title'])} [{label(payload['video_id'])}]"
                + capture_limits(payload.get("metadata") or payload))
    if "path" in payload:
        return label(payload["path"])
    if "job_id" in payload:
        return f"Job: {label(payload['job_id'])}. Use get_job_status to check completion."
    fields = ", ".join(key for key in payload if key != "ok")
    return f"OK ({fields}). Use JSON output for the full result." if fields else "OK"


def emit(payload, text=False, *, index=None):
    print(human(payload, index=index) if text else json.dumps(payload, ensure_ascii=False, allow_nan=False))
    if payload.get("ok") is not True:
        if not text:
            print(error_text(payload), file=sys.stderr)
        return 1
    return 0


def refuse_linked_path(path: Path):
    """Inspect without resolving links, including Windows junctions/reparse points."""
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise UsageError(f"skill destination contains a link or reparse point: {part}")


def install_skill(parent: Path, force=False):
    source = APP_DIR / "skills" / "uoink"
    destination = Path(os.path.abspath(parent.expanduser())) / "uoink"
    refuse_linked_path(destination)
    if destination == source.resolve() or destination in source.resolve().parents or source.resolve() in destination.parents:
        raise UsageError("skill destination must be separate from the source folder")
    if destination.exists() and not force:
        raise UsageError(f"{destination} already exists; pass --force to overwrite skill files")
    # Preflight the entire existing tree before writing anything. os.walk does
    # not follow symlinks; reject junctions before descending into them too.
    for directory, dirs, files in os.walk(destination, followlinks=False):
        for name in dirs + files:
            refuse_linked_path(Path(directory) / name)
    shutil.copytree(source, destination, dirs_exist_ok=force)
    return {"ok": True, "path": str(destination)}


# These finite backend workers may outlive a registry call in a persistent MCP
# session. A one-shot CLI must let them finish before its daemon threads exit.
# The podcast worker is permanent, so drain its queue instead of joining it.
CAPTURE_WORKERS = ("playlist-", "source-capture-", "comments-", "hook-type-",
                   "comment-intelligence-", "entity-extraction-")


def serve_mcp():
    """Run uoink_mcp.py's stdio server in this process, through its own main()."""
    # Importing uoink_mcp binds server.py logging to stderr. Never redirect
    # stdout here: the transport claims the real descriptor for JSON-RPC and
    # diverts stray prints to stderr for the rest of the session.
    import uoink_mcp
    uoink_mcp.main()
    return 0


def finish_call_work(server, name, payload, existing_threads):
    if name == "transcribe_podcast_episode" and payload.get("ok") is True:
        server._podcast_transcription_queue.join()
    while True:
        workers = [thread for thread in threading.enumerate()
                   if thread not in existing_threads
                   and thread.name.startswith(CAPTURE_WORKERS)]
        if not workers:
            return
        # A comments worker can create a hook or analysis worker before it
        # exits. Rescan after joining, so those descendants finish too.
        for thread in workers:
            thread.join()


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    mcp_session = False
    try:
        isolation.apply_from_process(raw)
        clean = isolation.strip_cli(raw)
        # Let serve forward all legacy flags without argparse interpreting them.
        if not clean or clean[0] == "serve":
            forwarded = list(raw)
            if clean:
                del forwarded[forwarded.index("serve")]
            with redirect_stdout(sys.stderr):
                return backend().run_cli(forwarded)
        ns = parser().parse_args(clean)
        if ns.command is None:
            raise UsageError("choose a command; use uoink --help")
        if ns.command == "mcp":
            mcp_session = True
            return serve_mcp()
        text_mode = getattr(ns, "text_output", False) and not (ns.command == "research" and ns.json)
        if ns.command == "serve":
            with redirect_stdout(sys.stderr):
                return backend().run_cli([*isolation.child_argv(), *ns.server_args])
        if ns.command == "connect":
            from uoink_connect import CLIENTS, client_spec, render, deeplink, python_command
            if ns.list and ns.client:
                raise UsageError("choose a client or --list, not both")
            if ns.deeplink and (ns.list or ns.client not in ("cursor", "vscode")):
                raise UsageError("--deeplink requires cursor or vscode")
            if ns.list:
                return emit({"ok": True, "clients": list(CLIENTS)}, text_mode)
            if ns.client not in CLIENTS:
                raise UsageError("unknown or missing client; use uoink connect --list")
            spec = client_spec(ns.client)
            from uoink_connect import require_platform
            try:
                require_platform(ns.client)
            except ValueError as exc:
                raise UsageError(str(exc)) from exc
            python = python_command(APP_DIR)
            output_format = "install deeplink" if ns.deeplink else spec.format
            print(f"File: {spec.location}\nFormat: {output_format}. Status: not yet tested.", file=sys.stderr)
            verification = "yes" if spec.verified else "no: " + spec.reason
            print(f"Official docs verified: {verification}. Checked: {spec.checked}.", file=sys.stderr)
            print("Sources: " + ", ".join(spec.sources), file=sys.stderr)
            if spec.note:
                print(spec.note, file=sys.stderr)
            if spec.format == "yaml":
                print("JSON-form YAML 1.2; the entire output is a valid YAML document.", file=sys.stderr)
            if spec.format == "shell" and sys.platform == "win32":
                print("Run this command in PowerShell.", file=sys.stderr)
            print(deeplink(ns.client, APP_DIR, python, isolation.child_argv(), ns.toolset) if ns.deeplink
                  else render(ns.client, APP_DIR, python, isolation.child_argv(), ns.toolset))
            return 0
        if ns.command == "skill":
            if ns.skill_command == "path":
                print(APP_DIR / "skills" / "uoink")
                return 0
            return emit(install_skill(ns.to, ns.force), text_mode)
        import uoink_mcp_tools as registry
        if ns.command == "tools":
            items = []
            for name in registry.stdio_tool_names(ns.toolset):
                spec = registry.TOOL_REGISTRY[name]
                item = {"name": name, "description": " ".join(spec.description.split())}
                if ns.json:
                    item["inputSchema"] = registry.client_input_schema(spec.input_schema, name)
                items.append(item)
            return emit({"ok": True, "tools": items}, text_mode)
        # Parse generic inputs before importing the backend or touching storage.
        call_args = arguments(ns) if ns.command == "call" else None
        if ns.command == "research":
            research_action(ns)
        with redirect_stdout(sys.stderr):
            server = backend()
            import uoink_agent_runtime as runtime
            if ns.command == "research":
                payload = research_command(ns, server)
            elif ns.command == "status":
                payload = {"ok": True, "version": server.VERSION,
                           "data_dir": str(server.DATA_ROOT.resolve()),
                           "helper_running": runtime.helper_running(server),
                           "tool_counts": {mode: len(registry.stdio_tool_names(mode)) for mode in ("full", "core")}}
                if sys.platform == "darwin" or sys.platform.startswith("linux"):
                    payload["capabilities"] = server._platform.platform_capabilities()
                if sys.platform.startswith("linux"):
                    payload["reliability_model"] = server._reliability_model_status()
            else:
                name, args = (ns.tool, call_args) if ns.command == "call" else friendly_call(ns, server)
                existing_threads = set(threading.enumerate())
                payload = runtime.call_tool(name, args, server)
                finish_call_work(server, name, payload, existing_threads)
        return emit(payload, text_mode, index=(server._get_index() if text_mode
                    and ("hits" in payload or "yoinks" in payload) else None))
    except UsageError as exc:
        print(f"uoink: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, RuntimeError) as exc:
        if mcp_session:
            # Stdout is the JSON-RPC transport. Fail on stderr, as uoink_mcp.py does.
            raise
        return emit({"ok": False, "error": str(exc)})


if __name__ == "__main__":
    raise SystemExit(main())
