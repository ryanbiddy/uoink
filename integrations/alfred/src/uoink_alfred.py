"""Uoink for Alfred: Script Filter results and actions.

Runs on the Python inside Uoink.app. Alfred passes the query as an argument
(never in script text), and this file calls the installed uoink CLI with an
argument list, so query text never reaches a shell.

    uoink_alfred.py filter <query>          print Script Filter JSON
    uoink_alfred.py act <action> <value>    open, reveal, copy or capture
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlparse

INSTALL_URL = "https://uoink.app/install"
SEARCH_LIMIT = 20
RECENT_LIMIT = 10
CAPTURE_TIMEOUT = 30 * 60


class UoinkError(Exception):
    pass


class UoinkMissing(UoinkError):
    pass


def uoink_app() -> Path:
    return Path(os.environ.get("uoink_app") or "/Applications/Uoink.app")


def cli() -> str:
    shim = uoink_app() / "Contents" / "Helpers" / "uoink"
    if not shim.is_file():
        raise UoinkMissing(f"No Uoink at {uoink_app()}")
    return str(shim)


def run_uoink(*args: str, timeout: float = 60) -> dict:
    try:
        proc = subprocess.run([cli(), *args], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise UoinkError("Uoink took too long to answer.") from exc
    except OSError as exc:
        raise UoinkMissing(str(exc)) from exc
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and payload.get("ok") is True:
        return payload
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            error = error.get("message") or error.get("code")
        raise UoinkError(str(error or "Uoink couldn't finish that."))
    lines = [line.strip() for line in proc.stderr.splitlines() if line.strip()]
    usage = next((line[len("uoink: "):] for line in lines if line.startswith("uoink: ")), None)
    raise UoinkError(usage or (lines[-1] if lines else "Uoink returned no result."))


def as_http_url(text: str) -> str | None:
    candidate = (text or "").strip()
    if not candidate or any(ch.isspace() for ch in candidate):
        return None
    parsed = urlparse(candidate)
    return candidate if parsed.scheme in ("http", "https") and parsed.netloc else None


def timestamp(seconds) -> str:
    if not isinstance(seconds, (int, float)) or seconds != seconds:
        return ""
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


# Citation formats shared by every Uoink integration (Raycast, Obsidian, Alfred,
# Flow Launcher). Saved source text (a timed_clip or text_only hit) is quoted
# with an attribution line; anything else is a link to the item and moment.
def link_citation(title: str, link: str | None, start) -> str:
    stamp = timestamp(start)
    label = f"{title} @ {stamp}" if stamp else title
    return f"[{label}]({link})" if link else label


def quote_citation(text: str, title: str, link: str | None, start, truncated: bool = False) -> str:
    """A Markdown quote with an attribution line. "…" marks text that was cut short."""
    body = (text or "").strip()
    if not body:
        return link_citation(title, link, start)
    lines = re.split(r"\r?\n", body + ("…" if truncated else ""))
    quote = "\n".join(f"> {line}" for line in lines)
    return f"{quote}\n>\n> — {link_citation(title, link, start)}"


QUOTABLE_KINDS = ("timed_clip", "text_only")


def is_quotable(hit: dict) -> bool:
    """The preview is saved source text: a timed transcript clip or a passage from
    the saved prose. A discovery_hint is a search snippet or the title, and a
    missing or unknown kind is never quoted."""
    return hit.get("evidence_kind") in QUOTABLE_KINDS


def hit_citation(hit: dict) -> str:
    title = hit.get("title") or hit.get("item_id") or "Untitled"
    preview = hit.get("preview") or {}
    link = hit.get("deep_link") or hit.get("source_link")
    if is_quotable(hit):
        return quote_citation(preview.get("text") or "", title, link, hit.get("start"),
                              preview.get("truncated") is True)
    return link_citation(title, link, hit.get("start"))


def one_line(text: str, limit: int = 120) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def item(title: str, subtitle: str = "", *, arg: str | None = None, action: str | None = None,
         valid: bool | None = None, **extra) -> dict:
    row = {"title": title, "subtitle": subtitle, "valid": bool(arg) if valid is None else valid}
    if arg is not None:
        row["arg"] = arg
    if action:
        row["variables"] = {"action": action}
    row.update(extra)
    return row


def hit_item(hit: dict) -> dict:
    title = hit.get("title") or hit.get("item_id") or "Untitled"
    preview = (hit.get("preview") or {}).get("text") or ""
    link = hit.get("deep_link") or hit.get("source_link")
    quote = hit_citation(hit)
    stamp = timestamp(hit.get("start"))
    subtitle = " · ".join(part for part in (stamp, hit.get("channel") or "", one_line(preview)) if part)
    mods = {"cmd": {"arg": quote, "subtitle": "Copy a Markdown citation", "variables": {"action": "copy"}},
            "alt": {"arg": hit.get("item_id") or "", "subtitle": "Copy the item ID", "variables": {"action": "copy"}}}
    if hit.get("source_link") and hit.get("source_link") != link:
        mods["ctrl"] = {"arg": hit["source_link"], "subtitle": "Open the source", "variables": {"action": "open"}}
    row = item(title, subtitle, arg=link or quote, action="open" if link else "copy",
               uid=f"{hit.get('item_id')}:{hit.get('start') if hit.get('start') is not None else 'text'}", mods=mods,
               text={"copy": quote, "largetype": preview or title})
    if link:
        row["quicklookurl"] = link
    return row


def filter_items(query: str) -> list[dict]:
    query = (query or "").strip()
    try:
        if not query:
            rows = [item("Search your Uoink library", "Type a few words, or paste a link to uoink it.", valid=False)]
            for recent in run_uoink("recent", "--limit", str(RECENT_LIMIT)).get("yoinks", []):
                title = recent.get("title") or recent.get("slug") or "Untitled"
                saved = (recent.get("yoinked_at") or "")[:10]
                folder = recent.get("folder")
                rows.append(item(title, f"Saved {saved}. ↩ reveals it in Finder." if saved else "↩ reveals it in Finder.",
                                 arg=folder, action="reveal", type="file:skipcheck" if folder else "default"))
            return rows
        url = as_http_url(query)
        if url:
            return [item("Uoink this link", url, arg=url, action="capture")]
        # Options first; "--" keeps a query that starts with "-" positional.
        payload = run_uoink("search", "--limit", str(SEARCH_LIMIT), "--", query)
        hits = payload.get("hits", [])
        if not hits:
            empty = payload.get("library_items") == 0
            return [item("Your library is empty" if empty else f"No matches for “{query}”",
                         "Paste a link here to uoink it." if empty else "Try fewer or different words.", valid=False)]
        return [hit_item(hit) for hit in hits]
    except UoinkMissing:
        return [item("Uoink isn't installed here",
                     "↩ opens the install page. Installed elsewhere? Set the Uoink app path in the workflow configuration.",
                     arg=INSTALL_URL, action="open")]
    except UoinkError as exc:
        return [item("Uoink couldn't answer", one_line(str(exc)), valid=False)]


def notify(title: str, message: str) -> None:
    # Both strings travel as arguments, never as script text.
    script = ["-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
              "-e", "end run"]
    subprocess.run(["/usr/bin/osascript", *script, title, message], capture_output=True, check=False)


def act(action: str, value: str) -> int:
    if action == "open" and as_http_url(value):
        subprocess.run(["/usr/bin/open", value], check=False)
    elif action == "reveal" and value and Path(value).exists():
        subprocess.run(["/usr/bin/open", "-R", value], check=False)
    elif action == "copy" and value:
        subprocess.run(["/usr/bin/pbcopy"], input=value, text=True, encoding="utf-8", check=False)
        notify("Uoink", "Copied")
    elif action == "capture" and as_http_url(value):
        notify("Uoinking…", value)
        try:
            payload = run_uoink("capture", "--", value, timeout=CAPTURE_TIMEOUT)
        except UoinkError as exc:
            notify("Couldn't uoink that link", one_line(str(exc), 200))
            return 1
        label = (payload.get("title") or (payload.get("metadata") or {}).get("title")
                 or (payload.get("feed") or {}).get("title") or payload.get("slug") or value)
        if payload.get("corpus_md") and os.environ.get("copy_after_capture", "1") == "1":
            subprocess.run(["/usr/bin/pbcopy"], input=payload["corpus_md"], text=True, encoding="utf-8", check=False)
            notify("Uoinked", f"{label}. Markdown copied.")
        else:
            notify("Uoinked", label)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "filter":
        print(json.dumps({"items": filter_items(argv[2] if len(argv) > 2 else "")}, ensure_ascii=False))
        return 0
    if len(argv) >= 4 and argv[1] == "act":
        return act(argv[2], argv[3])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
