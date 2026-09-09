"""Receipt-local sitecustomize and bundled-python guard install.

Not a server overlay. The original installed server.py still starts. Guards
block 5179, the live index, model/client spawns and undeclared network, and
apply the narrowly declared synthetic acquisition / failure injections.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .constants import FORBIDDEN_PORT, ORDINARY_LIVE_INDEX, SYNTHETIC_HOSTNAME
from .hashes import omit_raw_bytes, sha256_bytes
from .validation import C22ValidationError

SITECUSTOMIZE_NAME = "sitecustomize.py"

# Loaded by the bundled interpreter from Lib/site-packages (embeddable ._pth
# ignores PYTHONPATH). Inherited children of that interpreter load it too.
SITECUSTOMIZE_SOURCE = r'''# C22 receipt guard. Synthetic acquisition / declared injections only.
import builtins
import json
import os
import sys
import urllib.parse
import urllib.request

FORBIDDEN_PORT = 5179
ALLOWED = set()
for _part in (os.environ.get("C22_ALLOWED_PORTS") or "").split(","):
    _part = _part.strip()
    if _part.isdigit():
        ALLOWED.add(int(_part))
PROFILE = os.environ.get("C22_ISOLATED_PROFILE") or ""
FORBIDDEN_LIVE = (os.environ.get("C22_FORBIDDEN_LIVE") or "").replace("\\", "/").lower()
IG_FORBIDDEN = (os.environ.get("IG_FORBIDDEN_LIVE") or "").replace("\\", "/").lower()
INJECT = os.environ.get("C22_INJECT") or ""
AUDIO_PATH = os.environ.get("C22_SYNTHETIC_AUDIO_PATH") or ""
TRANSCRIPT_PATH = os.environ.get("C22_SYNTHETIC_TRANSCRIPT_PATH") or ""
SYNTHETIC_HOST = (os.environ.get("C22_SYNTHETIC_HOST") or "c22-fixture.invalid").lower()
FIXTURE_LOOPBACK = (os.environ.get("C22_FIXTURE_LOOPBACK") or "").rstrip("/")
LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}
MODEL_STEMS = {"claude", "codex", "gemini", "grok", "whisperx", "anthropic"}
_WRAPPED = set()


def _addr_port(addr):
    if isinstance(addr, tuple) and len(addr) >= 2:
        return str(addr[0]), addr[1]
    return None, None


def _is_forbidden_index(name):
    lowered = name.replace("\\", "/").lower()
    if FORBIDDEN_LIVE and FORBIDDEN_LIVE in lowered:
        return True
    if IG_FORBIDDEN and IG_FORBIDDEN in lowered:
        return True
    return False


def _event(kind, **details):
    path = os.environ.get("C22_EVENTS_PATH")
    if not path:
        return
    with open(path, "a", encoding="utf8") as handle:
        handle.write(json.dumps({"event": kind, "pid": os.getpid(), **details}) + "\n")


def _denied(reason):
    _event("forbidden_attempt", reason=reason)
    return PermissionError(reason)


def _urllib3_ipv6_query():
    frame = sys._getframe(1)
    while frame is not None:
        module = sys.modules.get("urllib3.util.connection")
        function = getattr(module, "_has_ipv6", None)
        if (function is not None and frame.f_code is getattr(function, "__code__", None)
                and frame.f_globals.get("__name__") == "urllib3.util.connection"
                and frame.f_code.co_filename.replace("\\", "/").lower().endswith("/urllib3/util/connection.py")):
            return True
        frame = frame.f_back
    return False


def audit(event, args):
    if event in ("open", "sqlite3.connect"):
        value = args[0] if args else None
        if isinstance(value, (str, bytes, os.PathLike)):
            name = os.fsdecode(value)
            if _is_forbidden_index(name):
                _event("forbidden_attempt", operation=event, resource="live_index")
                raise _denied("C22 guard: live index forbidden")
    if event in ("socket.connect", "socket.bind", "socket.sendto", "socket.getaddrinfo"):
        addr = args[:2] if event == "socket.getaddrinfo" else (args[1] if len(args) > 1 else None)
        host, port = _addr_port(addr)
        _event("network_attempt", operation=event, address=str(addr))
        if event == "socket.getaddrinfo":
            host = str(args[0]).lower() if args else ""
            gport = args[1] if len(args) > 1 else None
            if host == SYNTHETIC_HOST:
                raise _denied(
                    "C22 guard: refusing external resolution of synthetic fixture host")
            try:
                if gport is not None and int(gport) == FORBIDDEN_PORT:
                    raise _denied("C22 guard: port 5179 forbidden")
            except (TypeError, ValueError):
                pass
            if host not in LOOPBACK and host not in {"", None}:
                raise _denied("C22 guard: non-loopback network forbidden")
            return
        if port is None:
            return
        try:
            port_i = int(port)
        except (TypeError, ValueError):
            return
        if port_i == FORBIDDEN_PORT:
            raise _denied("C22 guard: port 5179 forbidden")
        if event == "socket.bind" and host == "::1" and port_i == 0 and _urllib3_ipv6_query():
            _event("blocked_capability_probe", operation=event, address=str(addr),
                   dependency="urllib3.util.connection._has_ipv6", bound=False)
            raise PermissionError("C22 guard: IPv6 capability bind deliberately refused")
        if host not in LOOPBACK:
            raise _denied("C22 guard: non-loopback network forbidden")
        if port_i not in ALLOWED and event != "socket.bind":
            raise _denied("C22 guard: undeclared port %s forbidden" % port_i)
        if event == "socket.bind" and port_i not in ALLOWED:
            raise _denied("C22 guard: bind of undeclared port %s forbidden" % port_i)
    if event == "subprocess.Popen":
        _event("subprocess_attempt", command=str(args[1] if len(args) > 1 else args[0]))
        if os.environ.get("C22_PROVENANCE_ONLY") == "1":
            _event("forbidden_attempt", operation=event, resource="provenance_descendant")
            raise _denied("C22 guard: provenance may not spawn descendants")
        cmd = args[1] if len(args) > 1 else args[0]
        first = cmd[0] if isinstance(cmd, (list, tuple)) and cmd else str(cmd).split()[0]
        name = os.path.basename(str(first)).lower().strip('"')
        stem = name.split(".")[0]
        if stem in MODEL_STEMS:
            _event("forbidden_attempt", operation=event, resource="model_client")
            raise _denied("C22 guard: model/client process forbidden")


sys.addaudithook(audit)
_event("guard_loaded", isolated_profile=PROFILE, injection=INJECT)

_real_import = builtins.__import__


def _url_text(arg):
    if isinstance(arg, urllib.request.Request):
        return arg.full_url
    return str(arg)


def _is_synthetic_url(url):
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host == SYNTHETIC_HOST


def _rewrite_synthetic(url):
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return url, None
    if (parsed.hostname or "").lower() != SYNTHETIC_HOST:
        return url, None
    if not FIXTURE_LOOPBACK:
        return url, "files"
    path = parsed.path or "/"
    query = ("?" + parsed.query) if parsed.query else ""
    return FIXTURE_LOOPBACK + path + query, "rewrite"


def _wrap_urlopen():
    if getattr(urllib.request, "_c22_urlopen_wrapped", False):
        return
    original = urllib.request.urlopen

    def wrapped(*args, **kwargs):
        url = args[0] if args else kwargs.get("url")
        text = _url_text(url)
        rewritten, mode = _rewrite_synthetic(text)
        if mode == "rewrite":
            if isinstance(url, urllib.request.Request):
                url = urllib.request.Request(
                    rewritten, data=url.data, headers=dict(url.headers),
                    method=url.get_method())
            else:
                url = rewritten
            args = (url,) + args[1:]
            if "url" in kwargs:
                kwargs["url"] = url
        elif mode == "files":
            raise _denied("C22 guard: synthetic host has no declared loopback fixture")
        elif _is_synthetic_url(text):
            raise _denied("C22 guard: refusing external fetch of synthetic fixture host")
        return original(*args, **kwargs)

    urllib.request.urlopen = wrapped
    urllib.request._c22_urlopen_wrapped = True


def _record_inject_child(proc):
    if not PROFILE:
        return
    try:
        dest = os.path.join(PROFILE, "c22-inject-child.json")
        payload = {
            "pid": getattr(proc, "pid", None),
            "inject": INJECT,
            "executable": sys.executable,
        }
        with open(dest, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    except OSError:
        pass


def _wrap_whisper(mod):
    def synthetic_transcript(*a, **k):
        _event("synthetic_transcript", model_invoked=False)
        if TRANSCRIPT_PATH and os.path.isfile(TRANSCRIPT_PATH):
            with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as handle:
                return json.load(handle)
        return {
            "model": "synthetic-C22",
            "language": "en",
            "diarization_ran": False,
            "segments": [{"start": 12.5, "end": 21.75,
                          "text": "C22 fixture: durable capture waits for complete publication."}],
        }

    mod.is_whisperx_available = lambda: True
    mod.is_model_downloaded = lambda *a, **k: True
    mod.transcribe_audio = synthetic_transcript
    mod.set_current_thread_below_normal = lambda: False
    mod._c22_wrapped = True


def _drive_original_run_subprocess():
    """Drive helper _run_subprocess so launch intent is recorded first."""
    main = sys.modules.get("__main__")
    run = getattr(main, "_run_subprocess", None)
    if not callable(run):
        raise OSError("C22 inject requires original helper _run_subprocess")
    return run(
        [sys.executable, "-B", "-c", "print('c22-capture-child')"],
        timeout=20, check=False,
    )


def _wrap_podcasts(mod):
    def download(idx, episode_id, *, data_root, **kwargs):
        episode = None
        try:
            episode = mod.get_episode(idx, episode_id)
        except Exception:
            episode = None
        audio_url = (episode or {}).get("audio_url") if isinstance(episode, dict) else None
        body = b"C22 SYNTHETIC AUDIO PLACEHOLDER"
        if AUDIO_PATH and os.path.isfile(AUDIO_PATH):
            with open(AUDIO_PATH, "rb") as handle:
                body = handle.read()
        elif audio_url and _is_synthetic_url(str(audio_url)) and FIXTURE_LOOPBACK:
            rewritten, _mode = _rewrite_synthetic(str(audio_url))
            with urllib.request.urlopen(rewritten, timeout=5) as response:
                body = response.read(4096)
        root = os.path.abspath(str(data_root))
        audio = os.path.join(root, "fixture.mp3")
        with open(audio, "wb") as handle:
            handle.write(body)
        if episode is not None:
            try:
                with idx.write_transaction() as conn:
                    conn.execute(
                        "UPDATE podcast_episodes SET audio_local_path=? WHERE id=?",
                        (audio, episode_id))
            except Exception:
                pass
        if INJECT in ("spawn_child", "launch_interrupt", "registration_failure"):
            _drive_original_run_subprocess()
        return {"ok": True, "audio_local_path": audio, "local_path": audio,
                "episode_id": episode_id, "size_bytes": len(body)}

    original_fetch = getattr(mod, "fetch_feed", None)

    def fetch_feed(feed_row):
        url = (feed_row or {}).get("feed_url") if isinstance(feed_row, dict) else None
        if url and _is_synthetic_url(str(url)):
            rewritten, mode = _rewrite_synthetic(str(url))
            if mode != "rewrite":
                raise _denied("C22 guard: synthetic host has no declared loopback fixture")
            req = urllib.request.Request(rewritten, headers={"User-Agent": "c22-fixture"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.read(), dict(resp.headers.items())
        if original_fetch is not None:
            return original_fetch(feed_row)
        raise RuntimeError("podcasts.fetch_feed missing")

    mod.download_episode_audio = download
    if original_fetch is not None:
        mod.fetch_feed = fetch_feed
    mod._c22_wrapped = True


def _wrap_popen():
    """Declared failure injection against the product _run_subprocess path.

    Product records launch intent, then Popen, then record_child_start.
    Raising OSError (not FileNotFoundError) leaves the intent unresolved.
    """
    import subprocess
    if getattr(subprocess, "_c22_popen_wrapped", False):
        return
    original = subprocess.Popen

    class GuardedPopen(original):
        def __init__(self, *a, **k):
            ctx = None
            try:
                import source_subscriptions as ss
                ctx = ss.current_capture_context()
            except Exception:
                ctx = None
            if ctx and INJECT == "launch_interrupt":
                raise OSError("C22 declared launch interruption after launch intent")
            injected = ctx and INJECT in ("spawn_child", "registration_failure")
            if injected:
                sleeper = [sys.executable, "-B", "-c",
                           "import time; time.sleep(%s)" % (
                               os.environ.get("C22_SLEEPER_SECONDS") or "8")]
                a = (sleeper,) + a[1:]
            super().__init__(*a, **k)
            if injected:
                _record_inject_child(self)

    subprocess.Popen = GuardedPopen
    subprocess._c22_popen_wrapped = True


def _wrap_subscriptions(mod):
    original_start = mod.record_child_start
    original_fetch = getattr(mod, "default_http_fetch", None)

    def record_child_start(root, start_id, pid, instance):
        if INJECT == "registration_failure":
            raise OSError("C22 declared registration failure")
        return original_start(root, start_id, pid, instance)

    if INJECT == "registration_failure":
        mod.record_child_start = record_child_start

    if original_fetch is not None:
        FetchResponse = getattr(mod, "FetchResponse", None)

        def default_http_fetch(url, headers, timeout=8, max_bytes=2_000_000, **kw):
            if _is_synthetic_url(str(url)):
                rewritten, mode = _rewrite_synthetic(str(url))
                if mode != "rewrite":
                    raise _denied(
                        "C22 guard: synthetic host has no declared loopback fixture")
                req = urllib.request.Request(rewritten, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = resp.read(max_bytes + 1)
                    if FetchResponse is not None:
                        return FetchResponse(
                            getattr(resp, "status", 200),
                            dict(resp.headers.items()),
                            body,
                        )
                    return body
            return original_fetch(url, headers, timeout=timeout, max_bytes=max_bytes, **kw)

        mod.default_http_fetch = default_http_fetch
    _wrap_popen()
    _wrap_urlopen()
    mod._c22_wrapped = True


def _import(name, globals=None, locals=None, fromlist=(), level=0):
    mod = _real_import(name, globals, locals, fromlist, level)
    if name == "whisper_runner" and id(mod) not in _WRAPPED:
        _wrap_whisper(mod)
        _WRAPPED.add(id(mod))
    elif name == "podcasts" and id(mod) not in _WRAPPED:
        _wrap_podcasts(mod)
        _WRAPPED.add(id(mod))
    elif name == "source_subscriptions" and id(mod) not in _WRAPPED:
        _wrap_subscriptions(mod)
        _WRAPPED.add(id(mod))
    return mod


builtins.__import__ = _import
_wrap_popen()
_wrap_urlopen()
'''


def pth_import_site_is_active(text: str) -> bool:
    """True only when an uncommented `import site` line is present."""
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "import site" or line.startswith("import site "):
            return True
    return False


def bundled_pth_path(installed_app: Path) -> Path | None:
    python_dir = Path(installed_app) / "python"
    for name in ("python._pth", "python311._pth", "python313._pth",
                 "python314._pth"):
        candidate = python_dir / name
        if candidate.is_file():
            return candidate
    return None


def inspect_bundled_pth(installed_app: Path) -> dict[str, Any]:
    """Record exact _pth bytes. Do not modify them. Inactive import site refuses."""
    path = bundled_pth_path(installed_app)
    if path is None:
        return {
            "path": None,
            "present": False,
            "import_site_active": None,
            "bytes": None,
            "sha256": None,
            "note": "no python._pth; non-embeddable interpreter uses default site",
        }
    payload = path.read_bytes()
    text = payload.decode("utf-8", errors="replace")
    active = pth_import_site_is_active(text)
    return {
        "path": str(path),
        "present": True,
        "import_site_active": active,
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "commented_import_site": ("#import site" in text.replace(" ", "")),
        "preserved_exact_bytes": True,
    }


def require_automatic_site_loading(installed_app: Path) -> dict[str, Any]:
    inspected = inspect_bundled_pth(installed_app)
    if inspected.get("present") and inspected.get("import_site_active") is not True:
        raise C22ValidationError(
            "bundled python._pth does not automatically load site/sitecustomize "
            "(import site is missing or commented); refusing")
    return inspected


def write_sitecustomize(directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / SITECUSTOMIZE_NAME
    data = SITECUSTOMIZE_SOURCE.encode("utf-8")
    path.write_bytes(data)
    return {
        "path": str(path),
        "sha256": sha256_bytes(data),
        "bytes": len(data),
    }


def bundled_site_packages(installed_app: Path) -> Path:
    return Path(installed_app) / "python" / "Lib" / "site-packages"


def install_into_bundled_python(installed_app: Path, *,
                                source: Path,
                                children_stopped: bool = True,
                                original_restore: dict[str, Any] | None = None,
                                ) -> dict[str, Any]:
    """Copy receipt sitecustomize into the disposable bundled interpreter.

    Embeddable python._pth ignores PYTHONPATH; site-packages sitecustomize
    is how inherited children of the bundled interpreter get the same
    guards. This mutates only the throwaway install tree and is hashed.
    Raw original bytes are never returned for JSON.
    """
    if not children_stopped:
        raise C22ValidationError(
            "refusing bundled guard install while owned children are running")
    site = bundled_site_packages(installed_app)
    if not site.is_dir():
        raise C22ValidationError(
            f"bundled site-packages missing; cannot install receipt guards: {site}")
    dest = site / SITECUSTOMIZE_NAME
    payload = source.read_bytes()
    if dest.exists():
        existing = dest.read_bytes()
        if existing != payload:
            raise C22ValidationError(
                f"refusing to overwrite a different sitecustomize at {dest}")
        return omit_raw_bytes({
            "path": str(dest),
            "sha256": sha256_bytes(existing),
            "already_present": True,
            "previous_absent": False,
            "previous_sha256": (
                (original_restore or {}).get("previous_sha256")
            ),
        })
    dest.write_bytes(payload)
    return omit_raw_bytes({
        "path": str(dest),
        "sha256": sha256_bytes(payload),
        "already_present": False,
        "bytes": len(payload),
        "previous_sha256": None,
        "previous_absent": True,
    })


def restore_guard_install(path: Path, *, original: bytes | None = None,
                          original_sha256: str | None = None,
                          owned_sha256: str | None = None,
                          children_stopped: bool = True,
                          descendants_stopped: bool = True,
                          descendants_unknown: bool = False) -> dict[str, Any]:
    """Restore exact receipt-owned guard bytes. Refuse a conflict instead of
    deleting changed or preexisting sitecustomize."""
    if not children_stopped or not descendants_stopped:
        raise C22ValidationError(
            "refusing bundled guard restore while owned children or "
            "descendants are still running")
    if descendants_unknown:
        raise C22ValidationError(
            "refusing bundled guard restore: descendant liveness is unknown")
    path = Path(path)
    result: dict[str, Any] = {
        "path": str(path),
        "existed": path.exists(),
        "conflict": False,
    }
    if path.exists():
        current = path.read_bytes()
        result["before_sha256"] = sha256_bytes(current)
        original_digest = (
            sha256_bytes(original) if original is not None else original_sha256)
        if owned_sha256 and result["before_sha256"] == owned_sha256:
            owned_current = True
        elif original_digest and result["before_sha256"] == original_digest:
            owned_current = False
            result["already_original"] = True
        elif original is None and original_sha256 is None and owned_sha256 is None:
            raise C22ValidationError(
                f"refusing to delete sitecustomize without owned digest: {path}")
        else:
            result["conflict"] = True
            raise C22ValidationError(
                "refusing to delete or overwrite a conflicting sitecustomize "
                f"at {path} (current={result['before_sha256']} "
                f"owned={owned_sha256} original={original_digest})")
        if result.get("already_original"):
            result["removed"] = False
            result["restored"] = True
            result["sha256"] = result["before_sha256"]
            result["matches_expected"] = True
            return omit_raw_bytes(result)
        if not owned_current:
            raise C22ValidationError(
                f"refusing guard restore of unexpected bytes at {path}")
        if original is not None:
            path.write_bytes(original)
            result["removed"] = False
            result["restored"] = True
            result["sha256"] = sha256_bytes(original)
            result["matches_expected"] = (
                original_sha256 is None or result["sha256"] == original_sha256)
        else:
            path.unlink()
            result["removed"] = True
            result["restored"] = False
            result["absent_after"] = not path.exists()
            result["original_was_absent"] = True
        return omit_raw_bytes(result)
    if original is not None:
        path.write_bytes(original)
        result["restored"] = True
        result["sha256"] = sha256_bytes(original)
        result["matches_expected"] = (
            original_sha256 is None or result["sha256"] == original_sha256)
    else:
        result["restored"] = False
        result["absent_after"] = True
        result["original_was_absent"] = True
    return omit_raw_bytes(result)


def _canary_is_live_path(canary_file: Path, extra_env: dict[str, str] | None) -> bool:
    """String comparison only. Never open or hash the live index."""
    canary = os.path.normcase(str(Path(canary_file)))
    candidates = [
        os.environ.get("IG_FORBIDDEN_LIVE") or "",
        (extra_env or {}).get("IG_FORBIDDEN_LIVE") or "",
        ORDINARY_LIVE_INDEX,
    ]
    return any(
        text and os.path.normcase(text) == canary
        for text in candidates
    )


def prove_guard_rejects_canary(*, injection: Path, canary_file: Path,
                               extra_env: dict[str, str] | None = None,
                               interpreter: Path | str | None = None,
                               bundled_app: Path | None = None) -> dict[str, Any]:
    """Prove automatic sitecustomize loading with a disposable canary.

    Does not exec the guard and never opens the live index. When *bundled_app*
    is set, the target interpreter must load site automatically via _pth.
    """
    canary_file = Path(canary_file)
    if _canary_is_live_path(canary_file, extra_env):
        raise C22ValidationError(
            "refusing to use the live index path as a canary probe")
    canary_file.parent.mkdir(parents=True, exist_ok=True)
    canary_file.write_bytes(b"c22-disposable-canary-not-live-index")
    pth_info = None
    if bundled_app is not None:
        pth_info = require_automatic_site_loading(bundled_app)
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["C22_FORBIDDEN_LIVE"] = str(canary_file)
    target = Path(interpreter) if interpreter else Path(sys.executable)
    if bundled_app is None:
        env["PYTHONPATH"] = str(injection)
    else:
        env.pop("PYTHONPATH", None)
    if extra_env:
        preserved_pythonpath = env.get("PYTHONPATH")
        env.update(extra_env)
        env.pop("ANTHROPIC_API_KEY", None)
        env["C22_FORBIDDEN_LIVE"] = str(canary_file)
        if bundled_app is None and preserved_pythonpath:
            env["PYTHONPATH"] = preserved_pythonpath
        elif bundled_app is not None:
            env.pop("PYTHONPATH", None)
    # Automatic site import of sitecustomize. No explicit exec of the guard.
    code = (
        "import pathlib, sys\n"
        f"p = pathlib.Path({str(canary_file)!r})\n"
        "try:\n"
        "    p.read_bytes()\n"
        "    print('CANARY_OPENED')\n"
        "    sys.exit(3)\n"
        "except PermissionError as exc:\n"
        "    print('CANARY_REJECTED')\n"
        "    print(exc)\n"
        "    sys.exit(0)\n"
    )
    if "exec(" in code or "sitecustomize" in code:
        raise C22ValidationError("canary probe must not exec the guard")
    argv = [str(target), "-B", "-c", code]
    proc = subprocess.run(
        argv, env=env, capture_output=True, text=True, timeout=15,
    )
    rejected = proc.returncode == 0 and "CANARY_REJECTED" in (proc.stdout or "")
    if not rejected:
        raise C22ValidationError(
            "guard did not reject disposable canary via automatic sitecustomize: "
            f"interpreter={target} exit={proc.returncode} "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
    return {
        "canary": str(canary_file),
        "rejected": True,
        "opened_live_index": False,
        "hashed_live_index": False,
        "automatic_sitecustomize": True,
        "explicit_exec": False,
        "interpreter": str(target),
        "pth": pth_info,
        "stdout": (proc.stdout or "")[:500],
    }


def guard_env(*, isolated_profile: Path, allowed_ports: list[int],
              forbidden_live: Path | str, inject: str = "",
              synthetic: bool = False,
              audio_path: Path | None = None,
              transcript_path: Path | None = None,
              sleeper_seconds: int = 8,
              synthetic_host: str = SYNTHETIC_HOSTNAME,
              fixture_loopback: str | None = None) -> dict[str, str]:
    for port in allowed_ports:
        if port == FORBIDDEN_PORT:
            raise C22ValidationError("guard env must not allow port 5179")
    ig = (os.environ.get("IG_FORBIDDEN_LIVE") or "").strip()
    forbidden = str(forbidden_live)
    env = {
        "C22_ALLOWED_PORTS": ",".join(str(p) for p in allowed_ports),
        "C22_ISOLATED_PROFILE": str(isolated_profile),
        "C22_FORBIDDEN_LIVE": forbidden,
        "C22_INJECT": inject,
        "C22_SLEEPER_SECONDS": str(int(sleeper_seconds)),
        "C22_SYNTHETIC_HOST": synthetic_host,
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "librarian_apply_enabled": "false",
    }
    if ig:
        env["IG_FORBIDDEN_LIVE"] = ig
        env["C22_FORBIDDEN_LIVE"] = ig
    else:
        env["IG_FORBIDDEN_LIVE"] = forbidden
    if synthetic:
        env["C22_SYNTHETIC"] = "1"
    if audio_path:
        env["C22_SYNTHETIC_AUDIO_PATH"] = str(audio_path)
    if transcript_path:
        env["C22_SYNTHETIC_TRANSCRIPT_PATH"] = str(transcript_path)
    if fixture_loopback:
        env["C22_FIXTURE_LOOPBACK"] = str(fixture_loopback).rstrip("/")
    return env
