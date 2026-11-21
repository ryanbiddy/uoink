"""Agent CLI: one registry envelope per call, with no HTTP proxy.

The root uoink launchers send agent subcommands here and everything else to
server.py. The installed cli launcher runs this module with bundled Python;
pin sys.path for Python's embedded ._pth mode.
"""
from __future__ import annotations

import argparse
import hashlib
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
HELP_DESCRIPTION = (
    "Search your Uoink library, capture links and connect AI agents.\n"
    "Add --text to read command results in your terminal.\n"
    "Run 'uoink <command> --help' for one command."
)

TOOLSETS = ("full", "core", "search", "research")
BACKFILL_ACTIONS = ("status", "start", "pause", "resume")
BACKFILL_ROUTE = "/library/transcript-backfill"


class UsageError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        if "invalid choice: " in message and message.startswith("argument <command>"):
            bad = message.split("invalid choice: ", 1)[1].split(" (", 1)[0]
            message = f"unknown command {bad}. Run 'uoink --help' to see the commands."
        raise UsageError(message)


def parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--text", dest="text_output", action="store_true", default=argparse.SUPPRESS,
                        help="print results as readable text")
    root = Parser(prog="uoink", parents=[common], description=HELP_DESCRIPTION,
                  formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = root.add_subparsers(dest="command", metavar="<command>")
    def command(name, **kw):
        return sub.add_parser(name, parents=[common], **kw)
    listing = command("tools", help="list available tools")
    listing.add_argument("--toolset", choices=TOOLSETS, default="full", help="which tools to list (default full)")
    listing.add_argument("--json", action="store_true", help="include client input schemas")
    call = command("call", help="run a tool by name")
    call.add_argument("tool", help="tool name; run 'uoink tools --text' to list them")
    source = call.add_mutually_exclusive_group()
    source.add_argument("--args", help="tool arguments as one JSON object")
    source.add_argument("--args-file", type=Path, help="read the JSON arguments from a file")
    call.add_argument("pairs", nargs="*", metavar="key=value", help="one argument, repeatable")
    search = command("search", help="search saved items and show matching timestamps")
    search.add_argument("query", help="words to look for in your library")
    search.add_argument("--limit", type=int, default=5, help="most results to show (default 5)")
    capture = command("capture", help="save a video, playlist, post or page")
    capture.add_argument("url", help="video, playlist, post or page link")
    capture.add_argument("--shelf", help="put the save on this shelf instead of picking one")
    recent = command("recent", help="list the newest items in your library")
    recent.add_argument("--limit", type=int, default=20, help="most items to show (default 20)")
    get = command("get", help="look up a saved item by ID, or read it in full with --text")
    get.add_argument("id", help="item id from search or recent")
    get.add_argument("--slug", action="store_true", help="interpret id as a slug")
    cues = command("cues", help="timed transcript cues for one item, or list items by show "
                   "and publish date")
    cues.add_argument("id", nargs="?", help="item id from search or recent; omit to list items")
    cues.add_argument("--start", type=float, help="only cues from this second")
    cues.add_argument("--end", type=float, help="only cues up to this second")
    cues.add_argument("--channel", help="list: only this show or channel (exact name)")
    cues.add_argument("--from", dest="published_from", help="list: published on or after YYYY-MM-DD")
    cues.add_argument("--to", dest="published_to", help="list: published on or before YYYY-MM-DD")
    cues.add_argument("--words", dest="q", help="list: words to search for")
    cues.add_argument("--limit", type=int, help="most items (list: 1-200, default 50) or cues "
                      "(item: 1-5000, default 1000)")
    cues.add_argument("--offset", type=int,
                      help="start position; use the printed next_offset for the next page")
    imports = command("import-list", help="queue every video in a HackerTube list, HN thread, "
                      "Reddit thread or YouTube playlist (50 per batch)")
    imports.add_argument("url", help="list, thread or playlist link")
    imports.add_argument("--limit", type=int, default=50, help="videos per batch, 1-50 (default 50)")
    imports.add_argument("--offset", type=int, default=0,
                         help="start position; use the printed next offset for the next batch")
    imports.add_argument("--preview", action="store_true", help="count without queueing")
    saves = command("import", help="import Watch Later, Reddit saves or X bookmarks from a file")
    saves.add_argument("file", type=Path, help="a .csv or .txt saves file")
    saves.add_argument("--source", choices=("watch_later", "x_bookmarks", "reddit_saved"),
                       help="where the file came from (default: detect)")
    saves.add_argument("--limit", type=int, default=50, help="items per batch, 1-50 (default 50)")
    saves.add_argument("--offset", type=int, default=0, help="start position in the staged list")
    saves.add_argument("--preview", action="store_true", help="count without queueing")
    shelves = command("shelves", help="tidy Uncategorized: see proposed shelves, move saves, undo",
                      formatter_class=argparse.RawDescriptionHelpFormatter,
                      description="Nothing moves until you run apply or move, and undo puts the last move back.\n"
                                  "Moves change the shelf in the library, the search index and the saved\n"
                                  "notes. Folders on disk stay where they are.")
    shelves_sub = shelves.add_subparsers(dest="shelves_command", required=True, metavar="<action>")
    tidy = shelves_sub.add_parser("tidy", parents=[common],
                                  help="propose a shelf and a reason for each save on Uncategorized")
    tidy.add_argument("--limit", type=int, default=2000, help="most saves to look at, 1-5000 (default 2000)")
    accept = shelves_sub.add_parser("apply", parents=[common], help="accept one proposed group from tidy")
    accept.add_argument("shelf", help="the group's shelf name, as tidy printed it")
    accept.add_argument("--only", nargs="+", metavar="ID", help="move only these items from the group")
    move = shelves_sub.add_parser("move", parents=[common], help="move items to a shelf (new or existing)")
    move.add_argument("shelf", help="shelf name, 1-64 characters")
    move.add_argument("ids", nargs="+", metavar="ID", help="item ids from search, recent or tidy")
    undo = shelves_sub.add_parser("undo", parents=[common], help="put the last move back")
    undo.add_argument("batch_id", nargs="?", help="a specific move to undo (default: the latest)")
    research = command("research", help="discover sources, capture evidence and publish a research report")
    research.add_argument("words", nargs="+", metavar="WORDS",
                          help="a question to research, or status, publish, open or list")
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
    note = command("note", help="save a note to your library")
    note.add_argument("text", help="the note text")
    note.add_argument("--title", help="a title for the note")
    command("status", help="show the version, data folder and whether the helper is running")
    backfill = command("backfill", help="transcribe saves that have video but no words (runs in the helper)",
                       description="Find saves that have video but no transcript and transcribe them with "
                                   "the local model, one at a time, longest first. It runs inside the "
                                   "helper, so it keeps going after this command ends and pauses while "
                                   "you capture. Nothing leaves this computer except fetching media again "
                                   "from where it was saved.")
    backfill.add_argument("action", choices=BACKFILL_ACTIONS, help="status, start, pause or resume")
    backfill.add_argument("--order", choices=("longest", "newest"),
                          help="with start: longest first (default) or newest saved first")
    connect = command("connect", help="print local connection recipes; never writes client files")
    connect.add_argument("client", nargs="?", help="client name; use --list to see them")
    connect.add_argument("--list", action="store_true", help="list the supported clients")
    connect.add_argument("--deeplink", action="store_true", help="print a Cursor or VS Code install link")
    connect.add_argument("--toolset", choices=TOOLSETS, default=None,
                         help="tools to serve: full (99), core (36), search (9) or research (7); default full, core for Cursor")
    skill = command("skill", help="find or install the Uoink agent skill")
    skill_sub = skill.add_subparsers(dest="skill_command", required=True)
    skill_sub.add_parser("path", help="print where the skill files are")
    install = skill_sub.add_parser("install", help="copy the skill into an agent's skills folder")
    install.add_argument("--to", type=Path, required=True, help="parent skills directory; copies into <dir>/uoink")
    install.add_argument("--force", action="store_true", help="replace an existing copy")
    serve = command("serve", help="run a helper command in this terminal",
                    description="Run the Uoink helper in this terminal. Other words and flags go to "
                                "the helper, for example: uoink serve doctor")
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
    if getattr(ns, "shelf", None):
        if route["source"] in ("youtube_playlist", "podcast_feed"):
            raise UsageError("--shelf works for one save at a time, not a playlist or podcast feed")
        # The capture tools route through server._route_topic, which reads
        # this hint first, so the save lands on the named shelf. It is the
        # user's own pick, so it also replaces a shelf they set before.
        import shelf_router
        shelf_router.remember_hints(server.DATA_ROOT, [(route["canonical"], ns.shelf),
                                                       (ns.url, ns.shelf)], by_hand=True)
    return name, {key: route["canonical"]}


def backfill_command(ns, server, *, running=None):
    """Ask the running helper; the backfill lives there, not in this process."""
    import urllib.error
    import urllib.request
    if ns.order and ns.action != "start":
        raise UsageError("--order goes with start")
    if running is None:
        import uoink_agent_runtime as runtime
        running = runtime.helper_running(server)
    if not running:
        return {"ok": False, "error": "The Uoink helper is not running. Open Uoink, then try again."}
    path = BACKFILL_ROUTE if ns.action == "status" else f"{BACKFILL_ROUTE}/{ns.action}"
    body = {"order": ns.order} if ns.order else {}
    request = urllib.request.Request(
        f"http://{server.HOST}:{server.PORT}{path}",
        data=None if ns.action == "status" else json.dumps(body).encode("utf-8"),
        headers={"X-Uoink-Token": server._current_token(),
                 **({} if ns.action == "status" else {"Content-Type": "application/json"})},
        method="GET" if ns.action == "status" else "POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            return payload
        return {"ok": False, "error": f"The helper answered HTTP {exc.code}."}
    except (OSError, urllib.error.URLError):
        return {"ok": False, "error": "Could not reach the Uoink helper. Open Uoink, then try again."}
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return {"ok": False, "error": "The helper sent an answer this command could not read."}
    return payload if isinstance(payload, dict) else {"ok": False, "error": "unexpected helper answer"}


def text_duration(seconds):
    seconds = int(seconds or 0)
    if seconds < 90:
        return "about a minute"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"about {minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"about {hours} h {minutes} min" if minutes else f"about {hours} h"


def backfill_text(payload):
    def plural(n, one, many=None):
        return f"{n} {one if n == 1 else (many or one + 's')}"
    count, progress = int(payload.get("count") or 0), payload.get("progress") or {}
    state = payload.get("state")
    lines = []
    if count:
        lines.append(f"{plural(count, 'save has', 'saves have')} video but no transcript "
                     f"({payload.get('on_disk', 0)} on this computer, "
                     f"{payload.get('download', 0)} to fetch again).")
    else:
        lines.append("Every save with video has its words.")
    if state == "running":
        lines.append(f"Running: {progress.get('done', 0)} done, {progress.get('left', 0)} left, "
                     f"{text_duration(progress.get('eta_seconds'))} to go.")
    elif state == "paused":
        lines.append(("Pausing at the next safe point. The save in hand starts over on resume."
                      if payload.get("pausing") else "Paused.")
                     + f" {progress.get('done', 0)} done, {progress.get('left', 0)} left. "
                     "Run 'uoink backfill resume' to carry on.")
    elif state == "done" and progress.get("done"):
        lines.append(f"Last run: {progress.get('transcribed', 0)} transcribed, "
                     f"{progress.get('no_words', 0)} had no speech, {progress.get('gone', 0)} gone, "
                     f"{progress.get('failed', 0)} did not work.")
    current = payload.get("current")
    if isinstance(current, dict) and current.get("title"):
        share = current.get("fraction")
        lines.append(f"Now: {terminal_label(current['title'])[:120]}"
                     + (f" ({int(share * 100)}%)" if isinstance(share, (int, float)) else ""))
        if current.get("waiting_for_capture"):
            lines.append("Waiting while your capture finishes.")
    for host, wait in (payload.get("backoff") or {}).items():
        site = {"youtube": "YouTube", "x": "X"}.get(host, "One site")
        lines.append(f"{site} asked Uoink to slow down. Trying again in "
                     f"{text_duration(wait.get('seconds_left')).replace('about ', '')}.")
    if payload.get("message"):
        lines.append(terminal_label(payload["message"]))
    if payload.get("gone"):
        lines.append(f"{plural(int(payload['gone']), 'save')} can't be transcribed because "
                     "the video is gone and no copy is on this computer.")
    if payload.get("half_capture_count"):
        lines.append(f"{plural(int(payload['half_capture_count']), 'capture')} did not finish. "
                     "Finish them in Uoink under Settings, Library health.")
    if (payload.get("model_ready") is False and payload.get("model_message")
            and (count or payload.get("half_capture_count"))):
        lines.append(terminal_label(payload["model_message"]))
    if state in ("idle", "done") and count:
        lines.append("Run 'uoink backfill start' to transcribe them. It uses this computer's CPU "
                     "and may fetch videos again.")
    return "\n".join(lines)


def cues_command(ns, server):
    """`uoink cues`: the timed cues read contract (timed_cues.py) in-process,
    the same envelopes GET /api/cues/v1/items returns. Local reads only."""
    import timed_cues
    item_flags = {"start": ns.start, "end": ns.end}
    list_flags = {"channel": ns.channel, "published_from": ns.published_from,
                  "published_to": ns.published_to, "q": ns.q}
    page_flags = {"limit": ns.limit, "offset": ns.offset}
    if ns.id:
        if any(value is not None for value in list_flags.values()):
            raise UsageError("--channel, --from, --to and --words list items; drop the id")
        flags, operation = {**item_flags, **page_flags}, "get"
    else:
        if any(value is not None for value in item_flags.values()):
            raise UsageError("--start and --end need an item id")
        flags, operation = {**list_flags, **page_flags}, "search"
    query = {k: [str(v)] for k, v in flags.items() if v is not None}
    try:
        idx = server._get_index()
        data = (timed_cues.get_item(idx, ns.id, query) if operation == "get"
                else timed_cues.search(idx, query))
    except timed_cues.CuesError as error:
        return timed_cues.error_envelope(operation, error)
    return timed_cues.envelope(operation, data)


def cues_text(payload):
    data = payload["data"]
    if payload.get("operation") == "search":
        items = data.get("items") or []
        if not items:
            return "No saved items match. Try a wider date range or another show name."
        lines = [f"{data['page']['total']} {'item' if data['page']['total'] == 1 else 'items'}"]
        for item in items:
            date = terminal_label(str(item.get("published_at") or "")[:10]) or "date unknown"
            lines.append(f"{date} | {terminal_label(item.get('title') or '')} | "
                         f"{terminal_label(item.get('channel') or 'source unknown')} "
                         f"[{terminal_label(item.get('id') or '')}]")
        if data["page"].get("next_offset") is not None:
            lines.append(f"More items: add --offset {data['page']['next_offset']}.")
        return "\n".join(lines)
    item, timing, cues = data["item"], data["timing"], data["cues"]
    source = {"captions": "uploaded captions", "auto_captions": "automatic captions",
              "local_asr": "local transcription"}.get(timing.get("source"), "no transcript")
    head = [terminal_label(item.get("title") or item.get("id") or "Item"),
            f"Published: {terminal_label(item.get('published_at') or 'unknown')} | "
            f"Timing: {source} | {len(cues)} cues"]
    rows = [f"{text_timestamp(c['start'])}–{text_timestamp(c['end'])}  {text_excerpt(c['text'])}"
            for c in cues[:40]]
    if len(cues) > 40:
        rows.append("More cues in JSON output.")
    next_offset = (data.get("page") or {}).get("next_offset")
    if next_offset is not None:
        rows.append(f"More cues after these: add --offset {next_offset}.")
    return "\n".join(head + rows)
def shelves_check(ns):
    """Usage errors for shelf options, before the backend or storage loads."""
    import shelf_router
    if ns.command == "capture" and ns.shelf is not None and not shelf_router.clean_shelf_name(ns.shelf):
        raise UsageError("--shelf must be 1-64 characters that also work as a folder name")
    if ns.command != "shelves":
        return
    if ns.shelves_command == "tidy" and not 1 <= ns.limit <= 5000:
        raise UsageError("--limit must be from 1 to 5000")
    if ns.shelves_command == "move":
        if not shelf_router.clean_shelf_name(ns.shelf):
            raise UsageError("the shelf name must be 1-64 characters that also work as a folder name")
        if len(ns.ids) > shelf_router.MAX_MOVES:
            raise UsageError(f"move at most {shelf_router.MAX_MOVES} items at a time")


SHELF_BODY_BYTES = 56 * 1024  # the helper refuses a body over 64 KB


def _helper_shelves(server, path, body):
    """POST one /library/shelves route to the running helper. Raises OSError
    when it can't be reached."""
    import urllib.error
    import urllib.request
    request = urllib.request.Request(
        f"http://{server.HOST}:{server.PORT}{path}", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Uoink-Token": server._current_token()},
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except ValueError:
            payload = None
        return payload if isinstance(payload, dict) else {"ok": False, "error": f"helper returned HTTP {exc.code}"}


def _move_parts(moves):
    """Moves in parts that each fit under the helper's body cap."""
    part, size = [], 0
    for move in moves:
        n = len(json.dumps(move, ensure_ascii=False).encode("utf-8")) + 1
        if part and size + n > SHELF_BODY_BYTES:
            yield part
            part, size = [], 0
        part.append(move)
        size += n
    if part:
        yield part


def _helper_apply(server, moves, label, *, source=None):
    """One undoable move on the running helper, sent in parts."""
    total = {"ok": True, "moved": 0, "skipped": [], "moves": [], "batch_id": None}
    for part in _move_parts(moves):
        body = {"moves": part, "label": label, **({"source": source} if source else {}),
                **({"append_to": total["batch_id"]} if total["batch_id"] else {})}
        result = _helper_shelves(server, "/library/shelves/apply", body)
        if not result.get("ok"):
            # What moved stays moved and can be undone; say what did not.
            return {**total, **result, "moved": total["moved"], "batch_id": total["batch_id"],
                    "not_moved": len(moves) - total["moved"] - len(total["skipped"])}
        total["batch_id"] = result.get("batch_id") or total["batch_id"]
        total["moved"] += int(result.get("moved") or 0)
        total["skipped"] += result.get("skipped") or []
        total["moves"] += result.get("moves") or []
        if result.get("files_not_updated"):
            total.setdefault("files_not_updated", []).extend(result["files_not_updated"])
    return total


def shelves_command(ns, server):
    """Tidy Uncategorized through the same helpers as the dashboard. When
    Uoink is running, moves and undo go to it, so its library stays current
    and one process writes the move log; otherwise they run here, under the
    same cross-process lock."""
    import shelf_router
    import uoink_agent_runtime as runtime
    remote = ns.shelves_command != "tidy" and runtime.helper_running(server)
    try:
        return _shelves_run(ns, server, shelf_router, remote)
    except OSError:
        if not remote:
            raise
        # The helper stopped answering: do it here instead.
        return _shelves_run(ns, server, shelf_router, False)


def _shelves_run(ns, server, shelf_router, remote):
    if ns.shelves_command == "tidy":
        return server._shelf_proposals(limit=ns.limit)
    if ns.shelves_command == "undo":
        if remote:
            return _helper_shelves(server, "/library/shelves/undo",
                                   {"batch_id": ns.batch_id} if ns.batch_id else {})
        return server._shelf_undo(ns.batch_id)
    if ns.shelves_command == "move":
        shelf = shelf_router.clean_shelf_name(ns.shelf)
        ids = list(dict.fromkeys(ns.ids))
        if remote:
            return _helper_apply(server, [{"video_id": item, "shelf": shelf} for item in ids], "Move")
        return server._reshelve([(item, shelf) for item in ids], label="Move")
    proposals = server._shelf_proposals(limit=shelf_router.MAX_MOVES)
    wanted = shelf_router.shelf_key(" ".join(ns.shelf.split()))
    group = next((g for g in proposals.get("groups") or [] if shelf_router.shelf_key(g["shelf"]) == wanted), None)
    if group is None:
        return {"ok": False, "error": f"No proposed group is called {ns.shelf}. "
                                      "Run 'uoink shelves tidy --text' to see the groups."}
    ids = [item["video_id"] for item in group["items"]]
    if ns.only:
        missing = [item for item in ns.only if item not in ids]
        if missing:
            return {"ok": False, "error": "Not in that group: " + ", ".join(missing)}
        ids = [item for item in ids if item in set(ns.only)]
    fallback = proposals.get("fallback") or "Uncategorized"
    if remote:
        return _helper_apply(server, [{"video_id": item, "shelf": group["shelf"], "from": fallback} for item in ids],
                             "Tidy", source="tidy")
    return server._reshelve([(item, group["shelf"]) for item in ids], label="Tidy",
                            expect={item: fallback for item in ids}, skip_by_hand=True)


def shelves_text(payload):
    def label(value):
        return terminal_label(value)[:240]
    if "groups" in payload:
        moving = sum(group["count"] for group in payload["groups"])
        lines = [f"Uncategorized: {payload['total']} saves. {moving} have a proposed shelf, "
                 f"{payload['stays']} stay where they are."]
        if payload.get("more"):
            lines.append("There are more saves on Uncategorized; run tidy again after moving these.")
        for group in payload["groups"]:
            lines.append(f"\n{label(group['shelf'])} ({'new shelf, ' if group['new'] else ''}{group['count']})")
            for item in group["items"][:5]:
                lines.append(f"  {label(item.get('title') or item['video_id'])} [{label(item['video_id'])}]"
                             f"\n    {label(item.get('reason') or '')}")
            if group["count"] > 5:
                lines.append(f"  and {group['count'] - 5} more")
        if payload["groups"]:
            lines.append(f'\nMove a group: uoink shelves apply "{label(payload["groups"][0]["shelf"])}"')
        return "\n".join(lines)
    if "moved" in payload:
        text = f"Moved {payload['moved']} {'save' if payload['moved'] == 1 else 'saves'}."
        if payload.get("skipped"):
            text += f" Left {len(payload['skipped'])} as they were."
        if payload.get("batch_id"):
            text += f"\nUndo: uoink shelves undo {label(payload['batch_id'])}"
        return text
    text = f"Put back {payload['restored']} {'save' if payload['restored'] == 1 else 'saves'}."
    if payload.get("skipped"):
        text += f" {len(payload['skipped'])} moved again since, or are gone, so they stay."
    return text


def error_text(payload):
    error = payload.get("error", "operation failed")
    if isinstance(error, dict):
        details = error.get("details")
        reason = details.get("reason") if isinstance(details, dict) else None
        extra = f" ({str(reason).replace('_', ' ')})" if reason else ""
        return f"{error.get('code', 'error')}: {error.get('message', error)}{extra}"
    if str(error) == "tool not found":
        return "No tool has that name. Run 'uoink tools --text' to see the names."
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


def text_item(payload, index):
    card = payload["card"]
    identity = payload["item_id"]
    lines = [terminal_label(card.get("title") or identity), "ID: " + terminal_label(identity)]
    for name, value in (("Source", card.get("channel")), ("URL", card.get("url")),
                        ("Saved", card.get("yoinked_at")), ("Topic", card.get("topic"))):
        if value:
            lines.append(f"{name}: {terminal_label(value)}")
    row = index.get_yoink(identity) if index is not None else None
    if row and not row.get("deleted_at"):
        with index.detached_snapshot() as db:
            shelves = db.execute(
                "SELECT n.name FROM item_shelves s JOIN shelf_nodes n USING(version_id,shelf_id) "
                "WHERE s.video_id=? AND n.retired=0 ORDER BY s.is_primary DESC, n.name", (identity,))
            lines.append("Shelf: " + (", ".join(terminal_label(r[0]) for r in shelves) or "Unshelved"))
        admission = payload.get("corpus_admission") or {}
        if admission.get("ok") and row.get("corpus_path"):
            import library_resources
            size = admission["total_bytes"]
            try:
                with Path(row["corpus_path"]).open("rb") as handle:
                    raw = handle.read(size + 1)
                if len(raw) == size and hashlib.sha256(raw).hexdigest() == admission["corpus_revision"]:
                    reader = library_resources.LibraryReader(index, data_root=index._path.parent)
                    body, _ = reader._redact(raw.decode("utf-8-sig"), row)
                    lines.extend(["", *(terminal_label(line) for line in body.splitlines())])
                    return "\n".join(lines)
            except (OSError, UnicodeError):
                pass
    lines.append("Full saved text unavailable.")
    for excerpt in card.get("excerpts") or []:
        timecode = text_timestamp(excerpt.get("start"))
        lines.append((timecode + " " if timecode else "") + terminal_label(excerpt.get("text") or ""))
    return "\n".join(lines)


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
    if "half_capture_count" in payload and "progress" in payload:
        return backfill_text(payload)
    if payload.get("contract") == "uoink.cues.read":
        return cues_text(payload)
    if ("groups" in payload and "stays" in payload) or "restored" in payload or (
            "moved" in payload and "undo" in payload):
        return shelves_text(payload)
    if "tools" in payload:
        return "\n".join(f"{tool['name']}: {tool['description']}" for tool in payload["tools"])
    if "data_dir" in payload:
        return (f"Uoink {payload['version']}\nData: {payload['data_dir']}\n"
                f"Helper: {'running' if payload['helper_running'] else 'not running (open Uoink to start it)'}\n"
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
        if not rows:
            return ("No results. Try other words, or run 'uoink recent --text' to see what is saved."
                    if "hits" in payload else
                    "Nothing saved yet. Save a link with: uoink capture <url>")
        lines = [f"{len(rows)} {'result' if len(rows) == 1 else 'results'}"]
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
    if isinstance(payload.get("card"), dict) and payload.get("item_id"):
        return text_item(payload, index) + capture_limits(payload["card"])
    if "corpus_md" in payload:
        return "\n".join(terminal_label(line) for line in payload["corpus_md"].splitlines())
    if "video_id" in payload and "title" in payload:
        return (f"Saved: {label(payload['title'])} [{label(payload['video_id'])}]"
                + capture_limits(payload.get("metadata") or payload))
    if "path" in payload:
        return label(payload["path"])
    if "job_id" in payload:
        return f"Job: {label(payload['job_id'])}. Use get_job_status to check completion."
    return "\n".join(f"{terminal_label(k.replace('_', ' ').capitalize())}: "
                     + (terminal_label(v) if isinstance(v, str) else json.dumps(v, ensure_ascii=True))
                     for k, v in payload.items() if k != "ok") or "OK"


def emit(payload, text=False, *, index=None):
    if text and hasattr(sys.stdout, "reconfigure"):
        # A cp1252 console cannot print a title's music note; show ? instead of crashing.
        sys.stdout.reconfigure(errors="replace")
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
    text_mode = False
    try:
        isolation.apply_from_process(raw)
        clean = isolation.strip_cli(raw)
        # Let serve forward all legacy flags without argparse interpreting them.
        if clean[:1] == ["serve"] and any(a in ("-h", "--help") for a in clean[1:]):
            parser().parse_args(["serve", "--help"])
        if not clean or clean[0] == "serve":
            forwarded = list(raw)
            if clean:
                del forwarded[forwarded.index("serve")]
            with redirect_stdout(sys.stderr):
                return backend().run_cli(forwarded)
        ns = parser().parse_args(clean)
        if ns.command is None:
            raise UsageError("choose a command. Run 'uoink --help' to see them")
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
        shelves_check(ns)
        with redirect_stdout(sys.stderr):
            server = backend()
            import uoink_agent_runtime as runtime
            if ns.command == "research":
                payload = research_command(ns, server)
            elif ns.command == "cues":
                payload = cues_command(ns, server)
            elif ns.command == "shelves":
                payload = shelves_command(ns, server)
            elif ns.command == "status":
                payload = {"ok": True, "version": server.VERSION,
                           "data_dir": str(server.DATA_ROOT.resolve()),
                           "helper_running": runtime.helper_running(server),
                           "tool_counts": {mode: len(registry.stdio_tool_names(mode)) for mode in ("full", "core")}}
                if sys.platform == "darwin" or sys.platform.startswith("linux"):
                    payload["capabilities"] = server._platform.platform_capabilities()
                if sys.platform.startswith("linux"):
                    payload["reliability_model"] = server._reliability_model_status()
            elif ns.command == "backfill":
                payload = backfill_command(ns, server)
            else:
                name, args = (ns.tool, call_args) if ns.command == "call" else friendly_call(ns, server)
                existing_threads = set(threading.enumerate())
                payload = runtime.call_tool(name, args, server)
                finish_call_work(server, name, payload, existing_threads)
        return emit(payload, text_mode, index=(server._get_index() if text_mode
                    and ("hits" in payload or "yoinks" in payload or "card" in payload) else None))
    except UsageError as exc:
        print(f"uoink: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, RuntimeError) as exc:
        if mcp_session:
            # Stdout is the JSON-RPC transport. Fail on stderr, as uoink_mcp.py does.
            raise
        return emit({"ok": False, "error": str(exc)}, text_mode)


if __name__ == "__main__":
    raise SystemExit(main())
