r"""Local HTTP server for the Yoink browser extension.

Runs on http://127.0.0.1:5179. Pure stdlib — no fastapi/flask required.
Reuses parse_srt/slugify/fmt_time from yt_extract.py.

Endpoints:
    GET  /ping
    POST /extract           single-video, drops in Desktop\Yoink\
    POST /session/start
    POST /session/add       runs extraction into the session folder
    POST /session/close     concatenates combined.md files into corpus.md
    POST /session/cancel
    GET  /session/list
    GET  /session/active
"""

import json
import logging
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# --- Import helpers from the existing CLI script ---------------------------
HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))
from yt_extract import parse_srt, slugify, fmt_time  # noqa: E402

# --- Constants -------------------------------------------------------------
HOST = "127.0.0.1"
PORT = 5179
VERSION = "1.1"
ALLOWED_ORIGINS = {
    "https://www.youtube.com",
    "https://m.youtube.com",
    "https://youtube.com",
}

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
SUBPROCESS_KW = {"creationflags": CREATE_NO_WINDOW} if sys.platform == "win32" else {}

# Invoke yt-dlp via the same interpreter rather than relying on PATH. pip's
# --user install puts yt-dlp.exe in %APPDATA%\Python\PythonXX\Scripts which
# isn't on PATH by default on Windows, so a bare "yt-dlp" call fails.
YTDLP_CMD = [sys.executable, "-m", "yt_dlp"]

DESKTOP_ROOT = Path(os.environ["USERPROFILE"]) / "Desktop" / "Yoink"
SESSIONS_ROOT = DESKTOP_ROOT / "_sessions"

# --- Logging ---------------------------------------------------------------
LOG_PATH = HERE / "server.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("yoink")

# Serialize extractions — yt-dlp + ffmpeg are I/O heavy.
_extract_lock = threading.Lock()
# Serialize session.json mutations to keep the on-disk state consistent.
_session_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Extraction core (shared by /extract and /session/add)
# ---------------------------------------------------------------------------
def _run_extraction(url: str, interval: int, output_folder: Path,
                    *, open_explorer: bool = True) -> dict:
    """Download + screenshot + transcript a single video into output_folder.

    output_folder is created if it doesn't exist. Returns a dict with title,
    folder, combined_md, screenshot_count, video_slug.
    """
    output_folder.mkdir(parents=True, exist_ok=True)

    title = subprocess.check_output(
        [*YTDLP_CMD, "--get-title", url],
        text=True,
        stderr=subprocess.PIPE,
        **SUBPROCESS_KW,
    ).strip()

    video_slug = slugify(title) or "video"
    log.info("Extracting to %s (slug=%s)", output_folder, video_slug)

    subprocess.run(
        [
            *YTDLP_CMD,
            "--write-auto-subs",
            "--write-subs",
            "--sub-lang", "en.*,en",
            "--convert-subs", "srt",
            "-f", "worst[height>=360]/worst",
            "-o", str(output_folder / "video.%(ext)s"),
            url,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        **SUBPROCESS_KW,
    )

    video_files = [f for f in output_folder.glob("video.*")
                   if f.suffix in (".mp4", ".webm", ".mkv")]
    srt_files = list(output_folder.glob("video*.srt"))
    if not video_files:
        raise RuntimeError("yt-dlp finished but no video file was produced.")
    video_file = video_files[0]

    shots_dir = output_folder / "screenshots"
    shots_dir.mkdir(exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-y",
            "-i", str(video_file),
            "-vf", f"fps=1/{interval}",
            "-q:v", "2",
            str(shots_dir / "shot_%04d.jpg"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        **SUBPROCESS_KW,
    )
    shots = sorted(shots_dir.glob("shot_*.jpg"))

    entries = list(parse_srt(srt_files[0])) if srt_files else []

    if entries:
        plain = "\n".join(text for _, _, text in entries)
        (output_folder / "transcript.txt").write_text(plain, encoding="utf-8")

    md_lines = [f"# {title}", "", f"Source: {url}", ""]
    if not entries:
        md_lines.append("> _No captions available for this video._")
        md_lines.append("")
    for i, shot in enumerate(shots):
        start = i * interval
        end = (i + 1) * interval
        chunk = " ".join(t for s, _, t in entries if start <= s < end)
        md_lines.append(f"## [{fmt_time(start)}]")
        md_lines.append("")
        md_lines.append(f"![shot {i+1}](screenshots/{shot.name})")
        md_lines.append("")
        if chunk:
            md_lines.append(chunk)
            md_lines.append("")
    combined_md = "\n".join(md_lines)
    (output_folder / "combined.md").write_text(combined_md, encoding="utf-8")

    video_file.unlink(missing_ok=True)

    if open_explorer:
        try:
            os.startfile(str(output_folder))  # type: ignore[attr-defined]
        except Exception as e:
            log.warning("startfile failed: %s", e)

    return {
        "ok": True,
        "folder": str(output_folder),
        "combined_md": combined_md,
        "screenshot_count": len(shots),
        "title": title,
        "video_slug": video_slug,
        "caption_count": len(entries),
    }


def friendly_error(e: BaseException) -> str:
    if isinstance(e, FileNotFoundError):
        missing = e.filename or str(e)
        return (f"Required tool not found on PATH: {missing}. "
                "Install yt-dlp (pip install yt-dlp) and ffmpeg (winget install Gyan.FFmpeg).")
    if isinstance(e, subprocess.CalledProcessError):
        stderr = (e.stderr.decode("utf-8", errors="ignore") if isinstance(e.stderr, bytes)
                  else (e.stderr or "")).strip()
        last = stderr.splitlines()[-1] if stderr else f"exit code {e.returncode}"
        tool = Path(e.cmd[0]).name if e.cmd else "subprocess"
        return f"{tool} failed: {last}"
    return f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _session_folder(slug: str) -> Path:
    return SESSIONS_ROOT / slug


def _read_session(slug: str) -> dict | None:
    path = _session_folder(slug) / "session.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("Failed to read session %s: %s", slug, e)
        return None


def _write_session(slug: str, data: dict) -> None:
    folder = _session_folder(slug)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "session.json"
    tmp = folder / "session.json.tmp"
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _all_sessions() -> list[dict]:
    if not SESSIONS_ROOT.exists():
        return []
    out = []
    for sub in SESSIONS_ROOT.iterdir():
        if not sub.is_dir():
            continue
        data = _read_session(sub.name)
        if data:
            out.append(data)
    out.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return out


def _active_session() -> dict | None:
    for s in _all_sessions():
        if s.get("status") == "open":
            return s
    return None


def _demote_headings(md: str) -> str:
    """Demote H1/H2 in a video's combined.md so they nest under the corpus's H2.

    H1 -> H3, H2 -> H3 (we want everything below the per-video heading to read
    as a sub-section, but timestamp headings can stay at the same depth).
    """
    out_lines = []
    for ln in md.splitlines():
        m = re.match(r"^(#+)(\s)", ln)
        if m:
            level = len(m.group(1))
            new_level = min(level + 2, 6)
            ln = "#" * new_level + ln[level:]
        out_lines.append(ln)
    return "\n".join(out_lines)


def _build_corpus(session: dict) -> str:
    name = session.get("name") or session.get("slug")
    created = session.get("created_at", "")
    videos = session.get("videos", [])
    folder = _session_folder(session["slug"])

    parts = [
        f"# Research Session: {name}",
        f"# Created: {created}",
        f"# Videos: {len(videos)}",
        "",
        "---",
        "",
    ]
    for i, v in enumerate(videos, 1):
        title = v.get("title", "(unknown)")
        url = v.get("url", "")
        video_slug = v.get("video_slug", "")
        rel = f"{video_slug}/"
        combined_path = folder / video_slug / "combined.md"

        parts.append(f"## Video {i}: {title}")
        parts.append(f"Source: {url}")
        parts.append(f"Local folder: {rel}")
        parts.append("")

        if combined_path.exists():
            try:
                body = combined_path.read_text(encoding="utf-8")
                # Strip the per-video H1 (the title) — we already emitted Video N: title.
                body = re.sub(r"^# .+\n", "", body, count=1)
                # Strip the immediate "Source: ..." line if present.
                body = re.sub(r"^Source: .+\n", "", body, count=1)
                parts.append(_demote_headings(body.strip()))
            except OSError as e:
                parts.append(f"> _Failed to read combined.md: {e}_")
        else:
            parts.append("> _combined.md not found — extraction may have failed._")

        parts.append("")
        parts.append("---")
        parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = f"Yoink/{VERSION}"

    def log_message(self, fmt, *args):
        return

    # ---- CORS helpers ----
    def _cors_origin(self) -> str | None:
        origin = self.headers.get("Origin")
        if not origin:
            return None
        if origin in ALLOWED_ORIGINS:
            return origin
        # Some Chromium builds send the extension origin instead of the page
        # origin for content-script fetches.
        if origin.startswith("chrome-extension://"):
            return origin
        return None

    def _send_cors(self, origin: str | None):
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            # Private Network Access: Chrome requires this header when a public
            # HTTPS origin (youtube.com) fetches a loopback resource. Without
            # it the preflight is rejected and fetch fails as "Failed to fetch"
            # before any visible request reaches the handler.
            self.send_header("Access-Control-Allow-Private-Network", "true")

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors(self._cors_origin())
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    # ---- Methods ----
    def do_OPTIONS(self):
        raw_origin = self.headers.get("Origin")
        origin = self._cors_origin()
        pna = self.headers.get("Access-Control-Request-Private-Network")
        log.info("OPTIONS %s origin=%r allowed=%r pna=%r -> 200",
                 self.path, raw_origin, origin, pna)
        self.send_response(200)
        self._send_cors(origin)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path == "/ping":
            log.info("GET /ping from %s -> ok", self.client_address[0])
            return self._send_json(200, {"ok": True, "version": VERSION})
        if self.path == "/session/list":
            return self._handle_session_list()
        if self.path == "/session/active":
            return self._handle_session_active()
        log.info("GET %s -> 404", self.path)
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        try:
            body = self._read_json_body()
        except (ValueError, json.JSONDecodeError) as e:
            return self._send_json(400, {"ok": False, "error": f"Invalid JSON body: {e}"})

        if self.path == "/extract":
            return self._handle_extract(body)
        if self.path == "/session/start":
            return self._handle_session_start(body)
        if self.path == "/session/add":
            return self._handle_session_add(body)
        if self.path == "/session/close":
            return self._handle_session_close(body)
        if self.path == "/session/cancel":
            return self._handle_session_cancel(body)
        if self.path == "/session/open":
            return self._handle_session_open(body)

        log.info("POST %s -> 404", self.path)
        self._send_json(404, {"ok": False, "error": "not found"})

    # ---- /extract ----
    def _validate_url_interval(self, body: dict):
        url = (body.get("url") or "").strip()
        interval = body.get("interval", 30)
        try:
            interval = int(interval)
        except (TypeError, ValueError):
            return None, None, "interval must be an integer"
        if "youtube.com" not in url and "youtu.be" not in url:
            return None, None, "URL must contain youtube.com or youtu.be"
        if not (5 <= interval <= 300):
            return None, None, "interval must be between 5 and 300"
        return url, interval, None

    def _handle_extract(self, body: dict):
        url, interval, err = self._validate_url_interval(body)
        if err:
            log.info("POST /extract -> 400 (%s)", err)
            return self._send_json(400, {"ok": False, "error": err})

        log.info("POST /extract url=%s interval=%d -> running", url, interval)
        DESKTOP_ROOT.mkdir(parents=True, exist_ok=True)
        with _extract_lock:
            try:
                # Need the title before we know the folder. Inline the title fetch
                # to mirror the prior behavior of slug-by-title.
                title = subprocess.check_output(
                    [*YTDLP_CMD, "--get-title", url],
                    text=True, stderr=subprocess.PIPE, **SUBPROCESS_KW,
                ).strip()
                folder = DESKTOP_ROOT / (slugify(title) or "video")
                # _run_extraction will also fetch the title (a second cheap call).
                # Trade-off: keeps _run_extraction self-contained for sessions
                # where the parent doesn't need the title up front.
                result = _run_extraction(url, interval, folder)
            except BaseException as e:
                msg = friendly_error(e)
                log.error("POST /extract -> error: %s", msg)
                return self._send_json(200, {"ok": False, "error": msg})

        log.info("POST /extract -> ok (%d shots, %s)",
                 result["screenshot_count"], result["folder"])
        self._send_json(200, result)

    # ---- /session/start ----
    def _handle_session_start(self, body: dict):
        name = (body.get("name") or "").strip()
        with _session_lock:
            existing = _active_session()
            if existing:
                msg = (f"A session is already open: '{existing.get('name')}'. "
                       "Close or cancel it before starting a new one.")
                log.info("POST /session/start -> 409 (active=%s)", existing.get("slug"))
                return self._send_json(409, {"ok": False, "error": msg, "active_session": {
                    "id": existing["slug"], "name": existing.get("name"),
                    "video_count": len(existing.get("videos", [])),
                }})

            slug_base = slugify(name) if name else datetime.now().strftime("session_%Y%m%d_%H%M%S")
            slug = slug_base or datetime.now().strftime("session_%Y%m%d_%H%M%S")
            # Disambiguate if a folder with that slug already exists.
            if _session_folder(slug).exists():
                slug = f"{slug}_{uuid.uuid4().hex[:6]}"

            session = {
                "name": name or slug,
                "slug": slug,
                "created_at": _now_iso(),
                "status": "open",
                "videos": [],
            }
            _write_session(slug, session)

        folder = _session_folder(slug)
        log.info("POST /session/start -> created %s", folder)
        self._send_json(200, {
            "ok": True,
            "session_id": slug,
            "name": session["name"],
            "folder": str(folder),
        })

    # ---- /session/add ----
    def _handle_session_add(self, body: dict):
        session_id = (body.get("session_id") or "").strip()
        url, interval, err = self._validate_url_interval(body)
        if err:
            return self._send_json(400, {"ok": False, "error": err})
        if not session_id:
            return self._send_json(400, {"ok": False, "error": "session_id required"})

        session = _read_session(session_id)
        if not session:
            return self._send_json(404, {"ok": False, "error": f"session '{session_id}' not found"})
        if session.get("status") != "open":
            return self._send_json(409, {
                "ok": False,
                "error": f"session '{session_id}' is {session.get('status')}, not open",
            })

        log.info("POST /session/add session=%s url=%s -> running", session_id, url)
        sess_folder = _session_folder(session_id)
        # Disambiguate the per-video subfolder by URL+title — call yt-dlp
        # to get the title first so we know the slug.
        with _extract_lock:
            try:
                title = subprocess.check_output(
                    [*YTDLP_CMD, "--get-title", url],
                    text=True, stderr=subprocess.PIPE, **SUBPROCESS_KW,
                ).strip()
                video_slug = slugify(title) or "video"
                target = sess_folder / video_slug
                # Disambiguate if same-named video already added.
                if target.exists():
                    video_slug = f"{video_slug}_{uuid.uuid4().hex[:6]}"
                    target = sess_folder / video_slug

                result = _run_extraction(url, interval, target, open_explorer=False)
            except BaseException as e:
                msg = friendly_error(e)
                log.error("POST /session/add -> error: %s", msg)
                return self._send_json(200, {"ok": False, "error": msg, "session_id": session_id})

        with _session_lock:
            session = _read_session(session_id) or session
            session.setdefault("videos", []).append({
                "url": url,
                "title": result["title"],
                "video_slug": result["video_slug"],
                "screenshot_count": result["screenshot_count"],
                "caption_count": result.get("caption_count", 0),
                "added_at": _now_iso(),
            })
            _write_session(session_id, session)

        log.info("POST /session/add -> ok (%d shots, total videos=%d)",
                 result["screenshot_count"], len(session["videos"]))
        result.update({"session_id": session_id, "video_count": len(session["videos"])})
        self._send_json(200, result)

    # ---- /session/close ----
    def _handle_session_close(self, body: dict):
        session_id = (body.get("session_id") or "").strip()
        if not session_id:
            return self._send_json(400, {"ok": False, "error": "session_id required"})

        with _session_lock:
            session = _read_session(session_id)
            if not session:
                return self._send_json(404, {"ok": False, "error": f"session '{session_id}' not found"})
            if session.get("status") != "open":
                return self._send_json(409, {
                    "ok": False,
                    "error": f"session is {session.get('status')}, cannot close",
                })

            corpus_md = _build_corpus(session)
            corpus_path = _session_folder(session_id) / "corpus.md"
            corpus_path.write_text(corpus_md, encoding="utf-8")

            session["status"] = "closed"
            session["closed_at"] = _now_iso()
            _write_session(session_id, session)

        sess_folder = _session_folder(session_id)
        try:
            os.startfile(str(sess_folder))  # type: ignore[attr-defined]
        except Exception as e:
            log.warning("startfile failed: %s", e)

        total_captions = sum(v.get("caption_count", 0) for v in session.get("videos", []))
        log.info("POST /session/close -> ok (%d videos, %d chars)",
                 len(session.get("videos", [])), len(corpus_md))
        self._send_json(200, {
            "ok": True,
            "corpus_path": str(corpus_path),
            "corpus_md": corpus_md,
            "video_count": len(session.get("videos", [])),
            "caption_count": total_captions,
            "session_folder": str(sess_folder),
            "name": session.get("name"),
        })

    # ---- /session/cancel ----
    def _handle_session_cancel(self, body: dict):
        session_id = (body.get("session_id") or "").strip()
        if not session_id:
            return self._send_json(400, {"ok": False, "error": "session_id required"})

        with _session_lock:
            session = _read_session(session_id)
            if not session:
                return self._send_json(404, {"ok": False, "error": f"session '{session_id}' not found"})
            if session.get("status") not in ("open",):
                return self._send_json(409, {
                    "ok": False,
                    "error": f"session is {session.get('status')}, cannot cancel",
                })
            session["status"] = "cancelled"
            session["cancelled_at"] = _now_iso()
            _write_session(session_id, session)

        log.info("POST /session/cancel -> ok (%s)", session_id)
        self._send_json(200, {"ok": True, "session_id": session_id})

    # ---- /session/open ----
    def _handle_session_open(self, body: dict):
        session_id = (body.get("session_id") or "").strip()
        if not session_id:
            return self._send_json(400, {"ok": False, "error": "session_id required"})
        folder = _session_folder(session_id)
        if not folder.exists():
            return self._send_json(404, {"ok": False, "error": f"session '{session_id}' not found"})
        try:
            os.startfile(str(folder))  # type: ignore[attr-defined]
        except Exception as e:
            return self._send_json(200, {"ok": False, "error": str(e)})
        log.info("POST /session/open -> %s", folder)
        self._send_json(200, {"ok": True, "folder": str(folder)})

    # ---- /session/list ----
    def _handle_session_list(self):
        sessions = _all_sessions()
        summaries = [{
            "session_id": s["slug"],
            "name": s.get("name"),
            "status": s.get("status"),
            "video_count": len(s.get("videos", [])),
            "created_at": s.get("created_at"),
            "closed_at": s.get("closed_at"),
            "cancelled_at": s.get("cancelled_at"),
            "folder": str(_session_folder(s["slug"])),
        } for s in sessions]
        log.info("GET /session/list -> %d sessions", len(summaries))
        self._send_json(200, {"ok": True, "sessions": summaries})

    # ---- /session/active ----
    def _handle_session_active(self):
        s = _active_session()
        if not s:
            return self._send_json(200, {"ok": True, "session": None})
        recent = list(reversed(s.get("videos", [])))[:3]
        self._send_json(200, {
            "ok": True,
            "session": {
                "session_id": s["slug"],
                "name": s.get("name"),
                "status": s.get("status"),
                "video_count": len(s.get("videos", [])),
                "created_at": s.get("created_at"),
                "folder": str(_session_folder(s["slug"])),
                "recent": [{"title": v.get("title"), "url": v.get("url")} for v in recent],
            },
        })


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
def maybe_toast(title: str, body: str):
    try:
        from win11toast import toast
        toast(title, body, duration="short")
    except Exception:
        pass


def main():
    DESKTOP_ROOT.mkdir(parents=True, exist_ok=True)
    SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    log.info("Yoink server v%s starting on http://%s:%d", VERSION, HOST, PORT)
    log.info("Log file: %s", LOG_PATH)
    log.info("Sessions root: %s", SESSIONS_ROOT)
    maybe_toast("Yoink", f"Server v{VERSION} running on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
