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
import stat
import sys
import threading

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import uoink_install_isolation as isolation  # noqa: E402


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
    listing.add_argument("--toolset", choices=("full", "core"), default="full")
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
    note = command("note")
    note.add_argument("text")
    note.add_argument("--title")
    command("status")
    connect = command("connect", help="print local connection recipes; never writes client files")
    connect.add_argument("client", nargs="?")
    connect.add_argument("--list", action="store_true")
    connect.add_argument("--deeplink", action="store_true", help="print a Cursor or VS Code install link")
    skill = command("skill")
    skill_sub = skill.add_subparsers(dest="skill_command", required=True)
    skill_sub.add_parser("path")
    install = skill_sub.add_parser("install")
    install.add_argument("--to", type=Path, required=True, help="parent skills directory; copies into <dir>/uoink")
    install.add_argument("--force", action="store_true")
    serve = command("serve", help="run the original helper CLI; remaining args pass through")
    serve.add_argument("server_args", nargs=argparse.REMAINDER)
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


def human(payload):
    if payload.get("ok") is not True:
        return error_text(payload)
    if "tools" in payload:
        return "\n".join(f"{tool['name']}: {tool['description']}" for tool in payload["tools"])
    if "data_dir" in payload:
        return (f"Uoink {payload['version']}\nData: {payload['data_dir']}\n"
                f"Helper: {'running' if payload['helper_running'] else 'not running'}\n"
                f"Tools: {payload['tool_counts']['full']} full, {payload['tool_counts']['core']} core")
    def label(value):
        # Keep control characters escaped even in the human display.
        return json.dumps(str(value), ensure_ascii=False)[1:-1][:240]
    def capture_limits(value):
        evidence = value.get("x_capture") if isinstance(value, dict) else None
        if not isinstance(evidence, dict):
            return ""
        from uoink_core.x_evidence import summary_lines
        return "\n" + "\n".join(label(line) for line in summary_lines(evidence))
    if "clients" in payload:
        return "\n".join(payload["clients"])
    if "hits" in payload or "yoinks" in payload:
        rows = payload.get("hits", payload.get("yoinks", []))
        lines = [f"{len(rows)} result(s)"]
        for row in rows[:10]:
            identity = row.get("item_id") or row.get("slug") or ""
            timing = (f"{row['start']}s to {row.get('end')}s"
                      if row.get("start") is not None else "untimed")
            lines.append(f"{label(row.get('title') or identity)} [{label(identity)}] ({timing})")
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


def emit(payload, text=False):
    print(human(payload) if text else json.dumps(payload, ensure_ascii=False, allow_nan=False))
    if payload.get("ok") is not True:
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
        text_mode = getattr(ns, "text_output", False)
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
            print(deeplink(ns.client, APP_DIR, python, isolation.child_argv()) if ns.deeplink
                  else render(ns.client, APP_DIR, python, isolation.child_argv()))
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
        with redirect_stdout(sys.stderr):
            server = backend()
            import uoink_agent_runtime as runtime
            if ns.command == "status":
                payload = {"ok": True, "version": server.VERSION,
                           "data_dir": str(server.DATA_ROOT.resolve()),
                           "helper_running": runtime.helper_running(server),
                           "tool_counts": {mode: len(registry.stdio_tool_names(mode)) for mode in ("full", "core")}}
                if sys.platform == "darwin":
                    payload["capabilities"] = server._platform.platform_capabilities()
            else:
                name, args = (ns.tool, call_args) if ns.command == "call" else friendly_call(ns, server)
                existing_threads = set(threading.enumerate())
                payload = runtime.call_tool(name, args, server)
                finish_call_work(server, name, payload, existing_threads)
        return emit(payload, text_mode)
    except UsageError as exc:
        print(f"uoink: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, RuntimeError) as exc:
        return emit({"ok": False, "error": str(exc)})


if __name__ == "__main__":
    raise SystemExit(main())
