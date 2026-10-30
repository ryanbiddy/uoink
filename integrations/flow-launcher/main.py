"""Uoink for Flow Launcher: search your library, open moments, uoink links.

Flow runs this file with one JSON-RPC request in sys.argv[1] and reads one
JSON response from stdout. The installed Uoink CLI does the work; this file
formats results. Standard library only, so there is no lib folder to ship.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlparse
import webbrowser

PLUGIN_DIR = Path(__file__).resolve().parent
ICON = "Images/icon.png"
INSTALL_URL = "https://uoink.app/install"
STATUS_FILE = PLUGIN_DIR / "last-capture.json"
SEARCH_LIMIT = 15
RECENT_LIMIT = 8
# Long videos transcribe and take screenshots before the CLI returns.
CAPTURE_TIMEOUT = 30 * 60

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


class UoinkError(Exception):
    pass


class UoinkMissing(UoinkError):
    pass


def uoink_root(settings: dict) -> Path:
    configured = str((settings or {}).get("uoinkFolder") or "").strip()
    if configured:
        return Path(configured)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Uoink"


def launcher(settings: dict) -> list[str]:
    """Run uoink_cli.py with Uoink's bundled Python, as cli\\uoink.cmd does.

    Skipping the .cmd shim keeps cmd.exe from re-parsing query text.
    """
    root = uoink_root(settings)
    python = root / "python" / "python.exe"
    script = root / "uoink_cli.py"
    if not python.is_file() or not script.is_file():
        raise UoinkMissing(f"No Uoink install at {root}")
    return [str(python), str(script)]


def _windows_flags(extra: int = 0) -> int:
    return CREATE_NO_WINDOW | extra if os.name == "nt" else 0


def _error_text(error) -> str:
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or "Uoink couldn't finish that.")
    return str(error or "Uoink couldn't finish that.")


def _stderr_message(stderr: str) -> str:
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    for line in lines:
        if line.startswith("uoink: "):
            return line[len("uoink: "):]
    return lines[-1] if lines else ""


def uoink_env() -> dict:
    # Flow sets PYTHONPATH for its own plugin library; keep it out of Uoink's Python.
    env = {key: value for key, value in os.environ.items()
           if key not in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP")}
    return {**env, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def run_uoink(settings: dict, *args: str, timeout: float = 60) -> dict:
    env = uoink_env()
    try:
        proc = subprocess.run([*launcher(settings), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, env=env,
                              creationflags=_windows_flags())
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
        raise UoinkError(_error_text(payload.get("error")))
    raise UoinkError(_stderr_message(proc.stderr) or "Uoink returned no result.")


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


def citation(text: str, title: str, link: str | None, start) -> str:
    stamp = timestamp(start)
    label = f"{title} @ {stamp}" if stamp else title
    quote = "\n".join(f"> {line}" for line in (text or "").strip().splitlines())
    return f"{quote}\n>\n> — {f'[{label}]({link})' if link else label}"


def one_line(text: str, limit: int = 140) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def result(title: str, subtitle: str = "", action: tuple | None = None, *, context=None,
           copy: str | None = None, score: int = 0) -> dict:
    item = {"title": title, "subTitle": subtitle, "icoPath": ICON, "score": score}
    if action:
        item["jsonRPCAction"] = {"method": action[0], "parameters": list(action[1:])}
    if context is not None:
        item["contextData"] = context
    if copy:
        item["copyText"] = copy
    return item


def copy_action(text: str) -> tuple:
    # Handled by Flow itself: CopyToClipboard(text, directCopy, showDefaultNotification).
    return ("Flow.Launcher.CopyToClipboard", text, False, True)


def last_capture_row() -> list[dict]:
    try:
        status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(status, dict):
        return []
    state = status.get("state")
    label = status.get("label") or status.get("url") or "a link"
    if state == "running":
        return [result(f"Uoinking {label}…", "Still working. Long videos take a few minutes.")]
    if state == "done":
        return [result(f"Uoinked {label}", "Last capture finished.")]
    if state == "failed":
        return [result(f"Couldn't uoink {label}", one_line(status.get("error", "")))]
    return []


def home(settings: dict) -> list[dict]:
    rows = last_capture_row()
    rows.append(result("Search your Uoink library", "Type a few words, or paste a link to uoink it."))
    for item in run_uoink(settings, "recent", "--limit", str(RECENT_LIMIT)).get("yoinks", []):
        title = item.get("title") or item.get("slug") or "Untitled"
        saved = (item.get("yoinked_at") or "")[:10]
        folder = item.get("folder")
        rows.append(result(title, f"Saved {saved}. Enter opens the folder." if saved else "Enter opens the folder.",
                           ("open_path", folder) if folder else None))
    return rows


def hit_context(hit: dict) -> dict:
    title = hit.get("title") or hit.get("item_id") or "Untitled"
    preview = (hit.get("preview") or {}).get("text") or ""
    link = hit.get("deep_link") or hit.get("source_link")
    return {
        "title": title,
        "itemId": hit.get("item_id") or "",
        "link": link or "",
        "source": hit.get("source_link") or "",
        "citation": citation(preview or title, title, link, hit.get("start")),
    }


def search(text: str, settings: dict) -> list[dict]:
    payload = run_uoink(settings, "search", text, "--limit", str(SEARCH_LIMIT))
    hits = payload.get("hits", [])
    if not hits:
        empty = payload.get("library_items") == 0
        return [result("Your library is empty" if empty else f"No matches for “{text}”",
                       "Paste a link here to uoink it." if empty else "Try fewer or different words.")]
    rows = []
    for rank, hit in enumerate(hits):
        context = hit_context(hit)
        stamp = timestamp(hit.get("start"))
        parts = [stamp, hit.get("channel") or "", one_line((hit.get("preview") or {}).get("text") or "")]
        action = ("open_url", context["link"]) if context["link"] else copy_action(context["citation"])
        rows.append(result(context["title"], " · ".join(p for p in parts if p), action,
                           context=context, copy=context["citation"], score=100 - rank))
    return rows


def query(text: str, settings: dict | None = None) -> list[dict]:
    settings = settings or {}
    text = (text or "").strip()
    try:
        if not text:
            return home(settings)
        url = as_http_url(text)
        if url:
            return [result("Uoink this link", url, ("capture", url), score=100)]
        return search(text, settings)
    except UoinkMissing:
        return [result("Uoink isn't installed here",
                       "Enter opens the install page. Installed elsewhere? Set the Uoink folder in this plugin's settings.",
                       ("open_url", INSTALL_URL))]
    except UoinkError as exc:
        return [result("Uoink couldn't answer", one_line(str(exc)))]


def context_menu(data, settings: dict | None = None) -> list[dict]:
    if not isinstance(data, dict):
        return []
    rows = []
    if data.get("citation"):
        rows.append(result("Copy citation", "Markdown quote with a timestamped link", copy_action(data["citation"])))
    if data.get("link"):
        rows.append(result("Copy link", data["link"], copy_action(data["link"])))
    if data.get("source") and data.get("source") != data.get("link"):
        rows.append(result("Open source", data["source"], ("open_url", data["source"])))
    if data.get("itemId"):
        rows.append(result("Copy item ID", data["itemId"], copy_action(data["itemId"])))
    return rows


def open_url(url: str, settings: dict | None = None) -> None:
    if as_http_url(url):
        webbrowser.open(url)


def open_path(path: str, settings: dict | None = None) -> None:
    if path and Path(path).is_dir() and hasattr(os, "startfile"):
        os.startfile(path)  # noqa: S606 - a library folder Uoink reported


def write_status(**status) -> None:
    try:
        STATUS_FILE.write_text(json.dumps({**status, "at": time.time()}), encoding="utf-8")
    except OSError:
        pass


def capture(url: str, settings: dict | None = None) -> dict:
    """Start the capture in a detached worker so Flow's window can close."""
    if not as_http_url(url):
        return {"method": "Flow.Launcher.ShowMsg", "parameters": ["Uoink", "That isn't a web link.", ""]}
    write_status(state="running", url=url)
    args = [sys.executable, str(Path(__file__).resolve()), "--capture-worker", url,
            json.dumps(settings or {})]
    subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     cwd=str(PLUGIN_DIR), close_fds=True,
                     creationflags=_windows_flags(DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP),
                     start_new_session=os.name != "nt")
    return {"method": "Flow.Launcher.ShowMsg",
            "parameters": ["Uoinking…", "Uoink shows a notification when a video is saved.", ""]}


def capture_worker(url: str, settings: dict) -> int:
    try:
        payload = run_uoink(settings, "capture", url, timeout=CAPTURE_TIMEOUT)
    except UoinkError as exc:
        write_status(state="failed", url=url, error=str(exc))
        return 1
    label = (payload.get("title") or (payload.get("metadata") or {}).get("title")
             or (payload.get("feed") or {}).get("title") or payload.get("slug") or url)
    write_status(state="done", url=url, label=label)
    return 0


ACTIONS = {"query": query, "context_menu": context_menu, "open_url": open_url,
           "open_path": open_path, "capture": capture}


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[1] == "--capture-worker":
        try:
            settings = json.loads(argv[3]) if len(argv) > 3 else {}
        except ValueError:
            settings = {}
        return capture_worker(argv[2], settings if isinstance(settings, dict) else {})
    request = json.loads(argv[1]) if len(argv) > 1 else {"method": "query", "parameters": [""]}
    handler = ACTIONS.get(request.get("method"))
    if handler is None:
        return 0
    output = handler(*(request.get("parameters") or []), settings=request.get("settings") or {})
    if request.get("method") in ("query", "context_menu"):
        print(json.dumps({"result": output}, ensure_ascii=False))
    elif isinstance(output, dict):
        print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    # Flow decodes plugin output as UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main(sys.argv))
