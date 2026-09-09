"""Shared isolation, hashing and inventory helpers for the Phase 4 installed kit.

These helpers never launch a client, model, Inno installer or the default
helper. Isolation is explicit: ``--isolated-profile`` (absolute) and
``--isolated-port`` (not 5179). The final package hash is Astra's after
build; this module records a manifest and does not invent one.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys


FORBIDDEN_PORT = 5179
LIVE_INDEX_NAME = Path("Uoink") / "index.db"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
RUNTIME_INSTALLED = "installed"
RUNTIME_SOURCE = "source-runtime"
RUNTIME_INSTRUMENT = "instrument-only"
C22_GUARD_MARKERS = (b"C22 receipt guard", b"C22 guard:")
P4_GUARD_MARK = b"P4 receipt guard"
PTH_SITE_MARK = "# p4-receipt-import-site\n"
PTH_SITE_MARK_BYTES = b"# p4-receipt-import-site"
CANDIDATE_SEAL_BINDING_FIELDS = (
    "staged_path", "source_path", "source_git_blob", "checkout_and_staged_sha256",
)
REQUIRED_SEALED_MODULES = (
    "index.py",
    "uoink_mcp.py",
    "uoink_mcp_tools.py",
    "library_cards.py",
    "library_work.py",
    "library_resources.py",
    "library_prompts.py",
    "library_briefs.py",
    "library_mirror.py",
    "library_mirror_vault_io.py",
    "library_media.py",
    "library_faithfulness.py",
    "server.py",
    "scripts/recall_hook.py",
)
SCRATCH_EXCLUDE_NAMES = {
    "build", ".git", "_scratch", "__pycache__", ".venv", "venv", "node_modules",
    ".pytest_cache", ".mypy_cache", "dist", "installer-assets",
}

# Captured at import, before any kit command redirects LOCALAPPDATA.
_LIVE_LOCALAPPDATA_AT_IMPORT = os.environ.get("LOCALAPPDATA")
_LIVE_APPDATA_AT_IMPORT = os.environ.get("APPDATA")
_LIVE_USERPROFILE_AT_IMPORT = os.environ.get("USERPROFILE")

EXPECTED_STDIO_TOOLS = (
    "uoink_video",
    "uoink_playlist",
    "get_job_status",
    "cancel_job",
    "list_recent_uoinks",
    "search_uoinks",
    "search_clips",
    "get_evidence_card",
    "get_uoink_corpus",
    "analyze_comments",
    "classify_hook",
    "get_taxonomy",
    "get_citation_map",
    "get_uoink_health",
    "find_mentions",
    "get_transcript_reliability",
    "add_podcast_feed",
    "list_podcast_feeds",
    "remove_podcast_feed",
    "poll_podcast_feed",
    "list_podcast_episodes",
    "download_podcast_episode",
    "get_whisperx_status",
    "transcribe_podcast_episode",
    "episode_to_corpus",
    "get_library_activity",
    "search_library",
    "get_library_item",
    "read_library_resource",
    "get_library_brief_input",
    "publish_library_brief",
    "export_cited_range",
)
EXPECTED_PROMPTS = (
    "consult-library",
    "evidence-brief",
    "whats-new",
    "reshelve-review",
)
EXPECTED_TEMPLATE_NAMES = (
    "library-card",
    "library-excerpt",
    "library-corpus-chunk",
    "library-shelf-page",
    "library-brief",
)

OPTIONAL_PLAYER_JUMP = {
    "status": "optional_separately_observed",
    "video_id": "D_FCYsshMI4",
    "chapter_title": "Why computer use",
    "start_seconds": 34,
    "url": "https://www.youtube.com/watch?v=D_FCYsshMI4&t=34s",
    "not_a_library_quotation": True,
    "no_fetch": True,
    "no_speaker_accuracy_claim": True,
}

BLOCKED_X_LINK = {
    "status": "blocked_link",
    "url": "https://x.com/NASAAdmin/status/2020984085754282078",
    "prior_condition": "HTTP 403 / net::ERR_HTTP_RESPONSE_CODE_FAILURE",
    "no_retry": True,
    "no_new_fetch": True,
    "not_a_successful_click": True,
}

SYNTHETIC_BANNER = "SYNTHETIC FIXTURE — not a real source quotation"
ITEM_TIMED = "p4fx-timed-01"
ITEM_TEXT = "p4fx-text-01"
ITEM_HOSTILE = "p4fx-hostile-01"
PROTECTED_SENTINEL_BYTES = b"P4-PROTECTED-SENTINEL-BYTES-v1\n"

ENV_ROOT_KEYS = (
    "LOCALAPPDATA",
    "APPDATA",
    "TEMP",
    "TMP",
    "XDG_DATA_HOME",
    "UOINK_OUTPUT_DIR",
)


class IsolationError(ValueError):
    """Fail-closed isolation or provenance error."""


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def save_json_exclusive(path: Path, value) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def require_no_api_key() -> None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        raise IsolationError("ANTHROPIC_API_KEY must be absent")


def original_localappdata() -> Path:
    """Live profile captured before environment redirection.

    Redirected LOCALAPPDATA (the isolated profile) is never treated as the
    live Uoink root. P4_ORIGINAL_LOCALAPPDATA is accepted only when it still
    matches the import-time live path.
    """
    live = Path(_LIVE_LOCALAPPDATA_AT_IMPORT) if _LIVE_LOCALAPPDATA_AT_IMPORT else None
    preserved = os.environ.get("P4_ORIGINAL_LOCALAPPDATA")
    current = os.environ.get("LOCALAPPDATA")
    if live is not None:
        if preserved and Path(preserved) == live:
            return live
        if current and Path(current) != live:
            return live
        return live
    if preserved:
        return Path(preserved)
    if not current:
        raise IsolationError("LOCALAPPDATA is required to locate the live index to refuse")
    return Path(current)


def live_index_path(localappdata: Path | None = None) -> Path:
    return (localappdata or original_localappdata()) / LIVE_INDEX_NAME


def live_data_root(localappdata: Path | None = None) -> Path:
    return (localappdata or original_localappdata()) / "Uoink"


def isolated_index_path(profile: Path) -> Path:
    return Path(profile) / "index.db"


def isolated_token_path(profile: Path) -> Path:
    return Path(profile) / "token.txt"


def isolated_settings_path(profile: Path) -> Path:
    return Path(profile) / "settings.json"


def isolated_output_path(profile: Path) -> Path:
    return Path(profile) / "output"


def is_hex64(value) -> bool:
    return isinstance(value, str) and bool(HEX64.match(value.lower()))


def is_git_sha40(value) -> bool:
    """installer_source_sha is a real 40-hex Git commit, not a 64-char SHA-256."""
    return isinstance(value, str) and bool(HEX40.match(value.lower()))


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(value: str | None) -> bytes | None:
    if not value:
        return None
    return base64.b64decode(value.encode("ascii"), validate=True)


def user_site_dir() -> Path | None:
    candidates = []
    try:
        import site
        path = site.getusersitepackages()
        if path:
            candidates.append(Path(path))
    except Exception:
        pass
    roaming = _LIVE_APPDATA_AT_IMPORT or os.environ.get("APPDATA")
    if roaming:
        base = Path(roaming) / "Python"
        if base.is_dir():
            candidates.extend(sorted(base.glob("Python*/site-packages")))
            candidates.append(base)
    for path in candidates:
        if path.is_dir() and (path / "mcp").is_dir():
            return path
    for path in candidates:
        if path.is_dir():
            return path
    return None


def require_absolute(path: Path, what: str) -> Path:
    if not path.is_absolute():
        raise IsolationError(f"{what} must be an explicit absolute path")
    try:
        return path.resolve()
    except OSError as exc:
        raise IsolationError(f"{what} could not be resolved: {exc}") from exc


def require_port(value) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise IsolationError("--isolated-port must be an integer") from exc
    if port == FORBIDDEN_PORT:
        raise IsolationError(f"--isolated-port must not be {FORBIDDEN_PORT}")
    if not 1 <= port <= 65535:
        raise IsolationError("--isolated-port must be in 1..65535")
    return port


def contained_in(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def load_source_bindings(data) -> list[dict]:
    """Candidate-package same-purpose bindings: staged_path/source_path/git blob/sha256."""
    if not isinstance(data, dict):
        return []
    rows = data.get("files") or data.get("source_bindings") or data.get("bindings") or []
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not all(k in row for k in ("staged_path", "checkout_and_staged_sha256")):
            continue
        digest = row.get("checkout_and_staged_sha256")
        blob = row.get("source_git_blob")
        out.append({
            "staged_path": str(row["staged_path"]).replace("\\", "/"),
            "source_path": str(row.get("source_path") or row["staged_path"]).replace("\\", "/"),
            "source_git_blob": blob if is_git_sha40(blob) else None,
            "checkout_and_staged_sha256": str(digest).lower() if is_hex64(digest) else None,
        })
    return out


def load_source_bindings_file(path: Path) -> dict:
    path = require_absolute(path, "--source-bindings")
    if not path.is_file():
        raise IsolationError("source-bindings file is required and must be a file")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise IsolationError(f"source-bindings is not readable JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise IsolationError("source-bindings must be a JSON object")
    build_source = data.get("build_source") or data.get("installer_source_sha")
    files = load_source_bindings(data)
    if not files:
        raise IsolationError("source-bindings contains no sealed file digests")
    return {
        "path": str(path),
        "sha256": sha_file(path),
        "bytes": path.stat().st_size,
        "build_source": str(build_source).lower() if is_git_sha40(build_source) else None,
        "files": files,
        "schema_fields": list(CANDIDATE_SEAL_BINDING_FIELDS),
        "invented_hash": False,
    }


def make_same_purpose_manifest_from_bytes(app: Path, *, installer_source_sha=None,
                                          origin: Path | None = None) -> dict:
    """Build a candidate-package-shaped bindings document from real bytes.

    Does not invent package_sha256 or git blob ids. installer_source_sha is
    recorded only when it is a real 40-hex Git commit.
    """
    app = require_absolute(app, "installed-app")
    git_sha = str(installer_source_sha).lower() if is_git_sha40(installer_source_sha) else None
    files = []
    for relative in REQUIRED_SEALED_MODULES:
        staged = app / relative
        if not staged.is_file():
            files.append({
                "staged_path": relative,
                "source_path": relative,
                "source_git_blob": None,
                "checkout_and_staged_sha256": None,
                "missing": True,
            })
            continue
        digest = sha_file(staged)
        origin_digest = None
        if origin is not None and (origin / relative).is_file():
            origin_digest = sha_file(origin / relative)
        files.append({
            "staged_path": relative,
            "source_path": relative,
            "source_git_blob": None,
            "checkout_and_staged_sha256": digest,
            "origin_sha256": origin_digest,
            "bytes": staged.stat().st_size,
            "missing": False,
        })
    return {
        "build_source": git_sha,
        "note": (
            "Same-purpose manifest from real installed/source bytes. "
            "Git blob identifiers are not invented. Package SHA-256 is Astra's."
        ),
        "files": files,
        "invented_hash": False,
        "package_sha256": None,
    }


def compare_installed_to_sealed(app: Path, bindings: list[dict], *,
                                required: tuple[str, ...] = REQUIRED_SEALED_MODULES) -> dict:
    """Compare installed source/module files to declared sealed SHA-256 digests."""
    app = Path(app)
    comparisons = []
    missing = []
    mismatched = []
    unverified = []
    for relative in required:
        declared = next((row for row in bindings if row.get("staged_path") == relative), None)
        staged = app / relative
        if declared is None:
            unverified.append(relative)
            comparisons.append({
                "staged_path": relative, "status": "missing_binding",
                "installed_sha256": sha_file(staged) if staged.is_file() else None,
            })
            continue
        expected = declared.get("checkout_and_staged_sha256")
        if not staged.is_file():
            missing.append(relative)
            comparisons.append({
                "staged_path": relative, "status": "missing_file",
                "declared_sha256": expected,
            })
            continue
        actual = sha_file(staged)
        if not is_hex64(expected):
            unverified.append(relative)
            comparisons.append({
                "staged_path": relative, "status": "unverified_digest",
                "installed_sha256": actual, "declared_sha256": expected,
            })
            continue
        equal = actual == str(expected).lower()
        row = {
            "staged_path": relative,
            "status": "equal" if equal else "mismatch",
            "installed_sha256": actual,
            "declared_sha256": str(expected).lower(),
            "source_git_blob": declared.get("source_git_blob"),
        }
        comparisons.append(row)
        if not equal:
            mismatched.append(relative)
    ok = not missing and not mismatched and not unverified
    return {
        "ok": ok,
        "compared": len(comparisons),
        "missing_files": missing,
        "mismatched_files": mismatched,
        "missing_or_unverified_bindings": unverified,
        "comparisons": comparisons,
    }


RUNTIME_PROBE_SOURCE = '''import json, sys
info = {
    "sys_executable": sys.executable,
    "sys_path": list(sys.path),
    "prefix": getattr(sys, "prefix", None),
    "exec_prefix": getattr(sys, "exec_prefix", None),
    "version": sys.version,
    "version_info": list(sys.version_info),
    "flags": {
        "no_user_site": bool(getattr(sys.flags, "no_user_site", False)),
        "isolated": bool(getattr(sys.flags, "isolated", False)),
        "safe_path": bool(getattr(sys.flags, "safe_path", False)),
    },
    "modules": {},
    "dependency_versions": {},
}
for name in ("uoink_mcp", "server", "index", "library_cards", "library_work",
             "library_prompts", "mcp"):
    try:
        mod = __import__(name)
        path = getattr(mod, "__file__", None)
        info["modules"][name] = {"ok": True, "file": path}
        ver = getattr(mod, "__version__", None)
        if ver is None:
            ver = getattr(mod, "VERSION", None)
        if ver is not None:
            info["dependency_versions"][name] = str(ver)
    except Exception as exc:
        info["modules"][name] = {
            "ok": False,
            "error": type(exc).__name__ + ": " + str(exc),
            "file": None,
        }
print(json.dumps(info, ensure_ascii=False))
'''


def probe_runtime_provenance(interpreter: Path, app: Path, env: dict, *,
                             cwd: Path | None = None, timeout_s: float = 8.0) -> dict:
    """Probe actual bundled sys.executable, module __file__, versions, sys.path."""
    from p4_session import spawn_owned
    import subprocess
    import tempfile

    interpreter = require_absolute(interpreter, "installed-interpreter")
    app = require_absolute(app, "installed-app")
    work = Path(cwd or app)
    script = work / "p4-runtime-probe.py"
    created = False
    if not script.is_file():
        script.write_text(RUNTIME_PROBE_SOURCE, encoding="utf-8", newline="\n")
        created = True
    owned = None
    cleanup = None
    stdout_file = tempfile.TemporaryFile()
    stderr_file = tempfile.TemporaryFile()
    try:
        owned = spawn_owned(
            [str(interpreter), "-B", str(script)],
            cwd=work, env=env, label="p4-runtime-probe",
            stdout=stdout_file, stderr=stderr_file,
        )
        try:
            owned.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            cleanup = owned.terminate_tree(timeout=2.0)
            return {
                "ok": False,
                "error": "runtime_probe_timeout",
                "sys_executable": None,
                "modules": {},
                "cleanup": cleanup,
            }
        cleanup = owned.terminate_tree(timeout=2.0)
        if not cleanup.get("cleaned"):
            return {"ok": False, "error": "runtime_probe_cleanup_unconfirmed", "cleanup": cleanup}
        stdout_file.seek(0)
        stdout = stdout_file.read(262145)
        if len(stdout) > 262144:
            return {"ok": False, "error": "runtime_probe_output_limit", "cleanup": cleanup}
        payload = stdout.decode("utf-8", "replace").strip().splitlines()
        parsed = None
        for line in reversed(payload):
            try:
                parsed = json.loads(line)
                break
            except ValueError:
                continue
        if not isinstance(parsed, dict):
            return {
                "ok": False,
                "error": "runtime_probe_unparsed",
                "raw_tail": stdout[-2000:].decode("utf-8", "replace"),
                "exit_code": owned.popen.poll(),
            }
        parsed["ok"] = owned.popen.poll() == 0
        parsed["cleanup"] = cleanup
        parsed["exit_code"] = owned.popen.poll()
        parsed["interpreter_argv"] = str(interpreter)
        return parsed
    finally:
        if owned is not None and cleanup is None:
            owned.terminate_tree(timeout=2.0)
        stdout_file.close()
        stderr_file.close()
        if created and script.is_file():
            try:
                script.unlink()
            except OSError:
                pass


def time_module():
    import time
    return time


def path_is_user_site(path: Path, user_site: Path | None) -> bool:
    if user_site is None:
        return False
    return contained_in(path, user_site)


def evaluate_probe_for_installed(probe: dict, *, app: Path, interpreter: Path,
                                 forbid_checkout: Path | None, user_site: Path | None) -> list[str]:
    reasons = []
    if not probe or not probe.get("ok"):
        reasons.append("bundled runtime provenance probe failed or unverified")
        return reasons
    exe = probe.get("sys_executable")
    try:
        if not exe or Path(exe).resolve() != interpreter.resolve():
            reasons.append("sys.executable is not the bundled interpreter")
    except OSError:
        reasons.append("sys.executable could not be resolved")
    for name, row in (probe.get("modules") or {}).items():
        if not row.get("ok"):
            reasons.append(f"unverified import: {name}")
            continue
        file_path = row.get("file")
        if not file_path:
            reasons.append(f"module {name} has no __file__")
            continue
        resolved = Path(file_path)
        if name == "mcp":
            if forbid_checkout and contained_in(resolved, forbid_checkout):
                reasons.append("mcp resolved inside the checkout")
            if path_is_user_site(resolved, user_site):
                reasons.append("mcp resolved inside user-site")
            continue
        if not contained_in(resolved, app):
            reasons.append(f"{name}.__file__ is not inside the installed app")
        if forbid_checkout and contained_in(resolved, forbid_checkout):
            reasons.append(f"{name} resolved inside the checkout")
        if path_is_user_site(resolved, user_site):
            reasons.append(f"{name} resolved inside user-site")
    for entry in probe.get("sys_path") or []:
        try:
            resolved = Path(entry)
        except (TypeError, ValueError):
            continue
        if forbid_checkout and contained_in(resolved, forbid_checkout):
            reasons.append("sys.path contains the checkout")
            break
        if path_is_user_site(resolved, user_site):
            reasons.append("sys.path contains user-site")
            break
    flags = probe.get("flags") or {}
    if not flags.get("no_user_site"):
        reasons.append("sys.flags.no_user_site is not set")
    return reasons


def load_package_manifest(path: Path, *, package_path: Path | None = None,
                          source_bindings_path: Path | None = None) -> dict:
    """Record Astra's manifest. A 64-character string is not a sealed package.

    installer_source_sha is a real 40-hex Git commit. Package and per-file
    content digests remain SHA-256. This function never invents a hash.
    """
    path = require_absolute(path, "--package-manifest")
    if not path.is_file():
        raise IsolationError("package/source manifest is required and must be a file")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise IsolationError(f"package manifest is not readable JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise IsolationError("package manifest must be a JSON object")
    package_hash = data.get("package_sha256")
    source_sha = data.get("installer_source_sha") or data.get("source_sha") or data.get("build_source")
    hash_hex = is_hex64(package_hash)
    source_git = is_git_sha40(source_sha)
    source_hex64 = is_hex64(source_sha)
    package_record = None
    if package_path is not None:
        package_file = require_absolute(package_path, "--package-path")
        if not package_file.is_file():
            raise IsolationError("package bytes are required for installed eligibility")
        actual = sha_file(package_file)
        size = package_file.stat().st_size
        if size <= 0:
            raise IsolationError("package bytes are empty")
        if hash_hex and actual != str(package_hash).lower():
            raise IsolationError(
                f"package hash differs from manifest (actual={actual} declared={package_hash})"
            )
        package_record = {
            "path": str(package_file),
            "sha256": actual,
            "bytes": size,
            "matched_declared_hash": bool(hash_hex and actual == str(package_hash).lower()),
        }
    bindings = load_source_bindings(data)
    bindings_record = None
    if source_bindings_path is not None:
        bindings_record = load_source_bindings_file(source_bindings_path)
        if not bindings:
            bindings = bindings_record["files"]
        if not source_git and bindings_record.get("build_source"):
            source_sha = bindings_record["build_source"]
            source_git = True
            source_hex64 = False
    sealed = bool(
        hash_hex and source_git and package_record and package_record["matched_declared_hash"]
    )
    return {
        "path": str(path),
        "sha256": sha_file(path),
        "bytes": path.stat().st_size,
        "declared_package_sha256": str(package_hash).lower() if hash_hex else None,
        "declared_hash_is_hex64": hash_hex,
        "package_hash_status": "sealed_and_verified" if sealed else "unsealed_astra_owns_final_hash",
        "installer_source_sha": str(source_sha).lower() if source_git else None,
        "installer_source_is_git_sha40": source_git,
        "installer_source_is_hex64": source_hex64,
        "package_bytes": package_record,
        "source_bindings": bindings,
        "source_bindings_file": bindings_record,
        "status": data.get("status") or ("sealed" if sealed else "unsealed"),
        "body": data,
        "invented_hash": False,
        "hex64_alone_is_not_sealed": True,
        "fabricated_64char_source_commit_rejected": bool(source_hex64 and not source_git),
    }


def _runtime_mode(instrument_only: bool, runtime_mode: str | None) -> str:
    if instrument_only and runtime_mode and runtime_mode != RUNTIME_INSTRUMENT:
        raise IsolationError("--instrument-only cannot be combined with another runtime mode")
    if instrument_only or runtime_mode == RUNTIME_INSTRUMENT:
        return RUNTIME_INSTRUMENT
    if runtime_mode in (RUNTIME_INSTALLED, RUNTIME_SOURCE):
        return runtime_mode
    if runtime_mode:
        raise IsolationError(f"unknown runtime mode: {runtime_mode}")
    return RUNTIME_SOURCE


def bundled_interpreter_path(app: Path) -> Path:
    return app / "python" / "python.exe"


def evaluate_installed_eligibility(binding_inputs: dict) -> dict:
    """Installed credit is not `not instrument_only` and not a 64-char string."""
    reasons = []
    mode = binding_inputs["runtime_mode"]
    if mode != RUNTIME_INSTALLED:
        reasons.append(f"runtime_mode is {mode}, not installed")
    manifest = binding_inputs["package_manifest"]
    if manifest.get("package_hash_status") != "sealed_and_verified":
        reasons.append("package hash is not sealed and verified against package bytes")
    if not manifest.get("installer_source_is_git_sha40"):
        reasons.append("installer_source_sha is missing or not a 40-hex Git commit")
    if manifest.get("fabricated_64char_source_commit_rejected"):
        reasons.append("installer_source_sha is a fabricated 64-character SHA-256, not a Git commit")
    if not manifest.get("package_bytes"):
        reasons.append("package bytes were not supplied")
    app = Path(binding_inputs["installed_app"])
    interpreter = Path(binding_inputs["installed_interpreter"])
    bundled = bundled_interpreter_path(app)
    entry = app / "uoink_mcp.py"
    server = app / "server.py"
    if not entry.is_file() or not server.is_file():
        reasons.append("installed source bindings missing uoink_mcp.py or server.py")
    if not bundled.is_file():
        reasons.append("bundled interpreter python/python.exe is missing")
    elif interpreter.resolve() != bundled.resolve():
        reasons.append("installed interpreter is not the bundled python/python.exe")
    checkout = binding_inputs.get("forbid_checkout")
    if checkout and contained_in(app, Path(checkout)):
        reasons.append("installed app resolves inside the checkout")
    user_site = user_site_dir()
    if user_site and contained_in(interpreter, user_site):
        reasons.append("interpreter resolves inside user-site")
    sealed_compare = None
    bindings = manifest.get("source_bindings") or []
    if mode == RUNTIME_INSTALLED:
        if not bindings:
            reasons.append("sealed per-file source bindings are missing")
        else:
            sealed_compare = compare_installed_to_sealed(app, bindings)
            if sealed_compare["missing_or_unverified_bindings"]:
                reasons.append(
                    "missing binding: " + ", ".join(sealed_compare["missing_or_unverified_bindings"])
                )
            if sealed_compare["missing_files"]:
                reasons.append(
                    "missing sealed source file: " + ", ".join(sealed_compare["missing_files"])
                )
            if sealed_compare["mismatched_files"]:
                reasons.append(
                    "mismatched sealed digest: " + ", ".join(sealed_compare["mismatched_files"])
                )
    probe = binding_inputs.get("runtime_probe")
    if mode == RUNTIME_INSTALLED:
        if not probe:
            reasons.append("bundled runtime provenance probe was not run")
        else:
            reasons.extend(evaluate_probe_for_installed(
                probe, app=app, interpreter=interpreter,
                forbid_checkout=Path(checkout) if checkout else None,
                user_site=user_site,
            ))
    eligible = not reasons and mode == RUNTIME_INSTALLED
    return {
        "eligible": eligible,
        "reasons": reasons,
        "bundled_interpreter": str(bundled) if bundled.is_file() else None,
        "entry_sha256": sha_file(entry) if entry.is_file() else None,
        "server_sha256": sha_file(server) if server.is_file() else None,
        "interpreter_sha256": sha_file(interpreter) if interpreter.is_file() else None,
        "sealed_file_comparison": sealed_compare,
        "runtime_probe": probe,
        "inferred_from_not_instrument_only": False,
        "inferred_from_hex64_string": False,
    }


def validate_isolation(
    *,
    isolated_profile: Path,
    isolated_port,
    receipt_root: Path,
    installed_app: Path,
    installed_interpreter: Path,
    package_manifest: Path,
    forbid_checkout: Path | None = None,
    instrument_only: bool = False,
    original_local: Path | None = None,
    runtime_mode: str | None = None,
    package_path: Path | None = None,
    source_bindings_path: Path | None = None,
    probe_runtime: bool | None = None,
) -> dict:
    """Fail closed before any product import or child launch."""
    require_no_api_key()
    original = original_local or original_localappdata()
    receipt = require_absolute(receipt_root, "--receipt-root")
    profile = require_absolute(isolated_profile, "--isolated-profile")
    app = require_absolute(installed_app, "--installed-app")
    interpreter = require_absolute(installed_interpreter, "--installed-interpreter")
    port = require_port(isolated_port)
    live_root = live_data_root(original)
    live_index = live_index_path(original)
    mode = _runtime_mode(instrument_only, runtime_mode)

    if profile == live_root or contained_in(profile, live_root):
        raise IsolationError("isolated profile must not be or contain the live Uoink data root")
    if profile.anchor == str(profile) or len(profile.parts) < 2:
        raise IsolationError("isolated profile must not be a volume root")
    if not contained_in(profile, receipt):
        raise IsolationError("isolated profile must stay inside --receipt-root")
    if not (app / "uoink_mcp.py").is_file():
        raise IsolationError("installed app must contain the original uoink_mcp.py")
    if not interpreter.is_file():
        raise IsolationError("installed interpreter must be an existing file")
    if forbid_checkout is not None:
        forbidden = require_absolute(forbid_checkout, "--forbid-checkout")
        if contained_in(app, forbidden) and mode == RUNTIME_INSTALLED:
            raise IsolationError(
                "installed app resolves inside the forbidden checkout; "
                "use --runtime-mode source-runtime or --instrument-only"
            )
    elif mode == RUNTIME_INSTALLED:
        raise IsolationError("installed mode requires --forbid-checkout so checkout resolution can be refused")
    if mode == RUNTIME_INSTALLED and package_path is None:
        raise IsolationError("installed mode requires --package-path with actual package bytes")
    if mode == RUNTIME_INSTALLED and source_bindings_path is None:
        raise IsolationError(
            "installed mode requires --source-bindings with sealed per-file SHA-256 digests"
        )
    manifest = load_package_manifest(
        package_manifest, package_path=package_path,
        source_bindings_path=source_bindings_path,
    )
    binding = {
        "isolated_profile": str(profile),
        "isolated_port": port,
        "receipt_root": str(receipt),
        "installed_app": str(app),
        "installed_interpreter": str(interpreter),
        "installed_entry": str(app / "uoink_mcp.py"),
        "live_index_forbidden": str(live_index),
        "live_data_root_forbidden": str(live_root),
        "forbid_checkout": str(forbid_checkout.resolve()) if forbid_checkout else None,
        "instrument_only": mode == RUNTIME_INSTRUMENT,
        "runtime_mode": mode,
        "index_path": str(isolated_index_path(profile)),
        "token_path": str(isolated_token_path(profile)),
        "settings_path": str(isolated_settings_path(profile)),
        "output_path": str(isolated_output_path(profile)),
        "package_manifest": manifest,
        "original_localappdata": str(original),
        "live_path_captured_before_redirect": True,
        "api_key_present": False,
        "live_index_never_opened": True,
        "runtime_probe": None,
    }
    should_probe = probe_runtime if probe_runtime is not None else (mode == RUNTIME_INSTALLED)
    if should_probe:
        env = isolation_env(binding)
        binding["runtime_probe"] = probe_runtime_provenance(
            interpreter, app, env, cwd=profile if profile.is_dir() else app,
        )
    eligibility = evaluate_installed_eligibility(binding)
    if mode == RUNTIME_INSTALLED and not eligibility["eligible"]:
        raise IsolationError(
            "installed eligibility failed closed: " + "; ".join(eligibility["reasons"])
        )
    binding["installed_eligibility"] = eligibility
    binding["installed_credit"] = False
    binding["installed_credit_note"] = (
        "installed_credit stays false until original-installed route results "
        "are complete, measured, and checkout/user-site absent"
    )
    return binding


def isolation_env(binding: dict, *, extra: dict | None = None) -> dict:
    """Child environment bound to the isolated profile.

    Installed children keep checkout and user-site off PYTHONPATH.
    Source-runtime may append the operator user-site so the MCP SDK can
    import; that path is labeled and never installed credit.
    """
    profile = Path(binding["isolated_profile"])
    app = Path(binding["installed_app"])
    tmp = profile / "tmp"
    output = isolated_output_path(profile)
    guard = profile / "guard"
    mode = binding.get("runtime_mode") or (
        RUNTIME_INSTRUMENT if binding.get("instrument_only") else RUNTIME_SOURCE
    )
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    # Preserve integrator IG_FORBIDDEN_LIVE across LOCALAPPDATA redirection.
    # Never recompute it from the redirected profile; never open that path.
    inherited_forbidden = os.environ.get("IG_FORBIDDEN_LIVE")
    pythonpath = [str(guard), str(app)]
    source_runtime_site = None
    if mode == RUNTIME_SOURCE:
        site = user_site_dir()
        if site and site.is_dir():
            pythonpath.append(str(site))
            source_runtime_site = str(site)
    env["P4_ORIGINAL_LOCALAPPDATA"] = binding["original_localappdata"]
    isolation_module = (app / "uoink_install_isolation.py").is_file()
    # Isolation-aware product computes the live Uoink root from LOCALAPPDATA.
    # Redirecting LOCALAPPDATA to the profile makes <profile>/Uoink look like
    # nested normal data and is refused. Keep the captured live path and bind
    # through --isolated-profile / UOINK_ISOLATED_*.
    localappdata = binding["original_localappdata"] if isolation_module else str(profile)
    appdata = _LIVE_APPDATA_AT_IMPORT or str(profile)
    if mode == RUNTIME_INSTALLED:
        env["PYTHONNOUSERSITE"] = "1"
        env["PYTHONSAFEPATH"] = "1"
    else:
        env.pop("PYTHONNOUSERSITE", None)
        env.pop("PYTHONSAFEPATH", None)
    env.update({
        "LOCALAPPDATA": localappdata,
        "APPDATA": appdata if isolation_module else str(profile),
        "TEMP": str(tmp),
        "TMP": str(tmp),
        "XDG_DATA_HOME": str(profile),
        "UOINK_OUTPUT_DIR": str(output),
        "UOINK_INDEX_PATH": str(isolated_index_path(profile)),
        "UOINK_ISOLATED_PROFILE": str(profile),
        "UOINK_ISOLATED_PORT": str(binding["isolated_port"]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "PYTHONPATH": os.pathsep.join(pythonpath),
        "P4_FIXTURE_ROOT": str(profile),
        "P4_ISOLATED_PROFILE": str(profile),
        "P4_ISOLATED_PORT": str(binding["isolated_port"]),
        "P4_INSTALLED_APP": str(app),
        "P4_FORBIDDEN_INDEX": binding["live_index_forbidden"],
        "IG_FORBIDDEN_LIVE": inherited_forbidden or binding["live_index_forbidden"],
        "P4_RUNTIME_MODE": mode,
        "P4_ROUTE_LABEL": extra.get("route_label", "unspecified") if extra else "unspecified",
        "MCP_TIMEOUT": "10000",
        "ENABLE_TOOL_SEARCH": "false",
        "DISABLE_AUTOUPDATER": "1",
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
        "UOINK_RECALL_DISABLED": extra.get("UOINK_RECALL_DISABLED", "0") if extra else "0",
    })
    if source_runtime_site:
        env["P4_SOURCE_RUNTIME_SDK_SITE"] = source_runtime_site
    if extra:
        for key, value in extra.items():
            if key == "route_label":
                continue
            env[key] = str(value)
    return env


def ensure_profile_dirs(profile: Path) -> None:
    for relative in ("tmp", "output", "items", "records", "client", "recall", "guard", "vault"):
        (profile / relative).mkdir(parents=True, exist_ok=True)


P4_SITECUSTOMIZE = '''# P4 receipt guard. Refuse live index, port 5179, model/client/fetch.
import os, sys
from pathlib import Path
from urllib.parse import urlsplit, unquote

def database_path(value):
    if value.startswith('file:'):
        uri = urlsplit(value)
        if uri.netloc.lower() not in ('', 'localhost'):
            raise PermissionError('P4 remote database authority forbidden')
        value = unquote(uri.path)
        if os.name == 'nt' and len(value) > 2 and value[0] == '/' and value[2] == ':':
            value = value[1:]
    return Path(value).resolve()

def audit(event, args):
    forbidden = os.environ.get('P4_FORBIDDEN_INDEX', '')
    absolute_forbidden = os.environ.get('IG_FORBIDDEN_LIVE', '')
    root = os.environ.get('P4_ISOLATED_PROFILE') or os.environ.get('P4_FIXTURE_ROOT')
    if event in ('open', 'sqlite3.connect') and isinstance(args[0], (str, bytes, os.PathLike)):
        value = os.fsdecode(args[0]).replace('\\\\', '/').lower()
        if forbidden and forbidden.replace('\\\\', '/').lower() in value:
            raise PermissionError('P4 live index forbidden')
        if absolute_forbidden and absolute_forbidden.replace('\\\\', '/').lower() in value:
            raise PermissionError('P4 integrator live index forbidden')
    if event == 'sqlite3.connect' and isinstance(args[0], str) and args[0] != ':memory:' and root:
        if not database_path(args[0]).is_relative_to(Path(root).resolve()):
            raise PermissionError('P4 database outside isolated profile')
    if event in ('socket.connect', 'socket.bind', 'socket.sendto', 'socket.getaddrinfo'):
        address = args[:2] if event == 'socket.getaddrinfo' else args[1]
        if isinstance(address, tuple) and (
            str(address[1]) == '5179' or address[0] not in ('127.0.0.1', '::1', 'localhost', '')
        ):
            raise PermissionError('P4 external network or resident port forbidden')
    if event == 'subprocess.Popen':
        command = args[1]
        first = command[0] if isinstance(command, (tuple, list)) else str(command).split()[0]
        name = Path(str(first)).stem.lower()
        if name in ('claude', 'codex', 'grok', 'gemini', 'yt-dlp', 'ffmpeg', 'curl'):
            raise PermissionError('P4 execution/fetch sentinel')

sys.addaudithook(audit)
'''


def _refuse_conflicting_guard(path: Path, payload: bytes) -> None:
    if not path.is_file():
        return
    existing = path.read_bytes()
    if existing == payload:
        return
    if any(marker in existing for marker in C22_GUARD_MARKERS):
        raise IsolationError(
            f"refusing to overwrite conflicting C22 guard state at {path}"
        )
    raise IsolationError(f"refusing to overwrite a different sitecustomize at {path}")


def write_guard(profile: Path, binding: dict) -> Path:
    """sitecustomize for stdio children: refuse live index, 5179, model/fetch."""
    path = profile / "guard" / "sitecustomize.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = P4_SITECUSTOMIZE.encode("utf-8")
    _refuse_conflicting_guard(path, payload)
    if not path.is_file():
        path.write_bytes(payload)
    return path


def interpreter_site_packages(interpreter: Path) -> Path:
    return interpreter.resolve().parent / "Lib" / "site-packages"


def interpreter_pth(interpreter: Path) -> Path | None:
    parent = interpreter.resolve().parent
    matches = list(parent.glob("python*._pth")) + list(parent.glob("*.pth"))
    for candidate in matches:
        if candidate.suffix == "._pth" or candidate.name.endswith("._pth"):
            return candidate
    pths = list(parent.glob("*._pth"))
    return pths[0] if pths else None


def pth_newline(raw: bytes) -> bytes:
    if b"\r\n" in raw:
        return b"\r\n"
    return b"\n"


def pth_active_import_site(raw: bytes) -> bool:
    """True only when an uncommented `import site` line is active.

    A commented `#import site` is not active; embeddable Python then never
    loads sitecustomize.
    """
    for line in raw.splitlines():
        text = line.decode("utf-8", "replace").strip()
        if not text or text.startswith("#"):
            continue
        if text == "import site" or text.startswith("import site#") or text.startswith("import site "):
            return True
    return False


def append_active_import_site(original: bytes) -> bytes:
    nl = pth_newline(original)
    body = original
    if body and not body.endswith((b"\n", b"\r\n")):
        body = body + nl
    return body + PTH_SITE_MARK_BYTES + nl + b"import site" + nl


def install_guard_into_interpreter(interpreter: Path, source: Path, *,
                                   installed_app: Path) -> dict:
    """Install sitecustomize through the interpreter's real startup path.

    Embeddable python._pth ignores PYTHONPATH. Bundled Lib/site-packages plus
    an active `import site` line (recorded as exact original bytes, restorable)
    is the supported mechanism. Never mutate a non-bundled interpreter.
    Conflicting C22 bytes are refused.
    """
    interpreter = interpreter.resolve()
    app = installed_app.resolve()
    record = {
        "interpreter": str(interpreter),
        "bundled": contained_in(interpreter, app),
        "mutations": [],
        "already_present": False,
        "mechanism": None,
        "pth_active_import_site": None,
    }
    if not contained_in(interpreter, app):
        record["mechanism"] = "pythonpath_guard_dir_only"
        record["skipped_reason"] = "interpreter is not the bundled installed python; refusing prefix mutation"
        return record
    payload = source.read_bytes()
    site = interpreter_site_packages(interpreter)
    if not site.is_dir():
        raise IsolationError(f"bundled site-packages missing; cannot install receipt guards: {site}")
    dest = site / "sitecustomize.py"
    _refuse_conflicting_guard(dest, payload)
    if dest.is_file() and dest.read_bytes() == payload:
        record["already_present"] = True
        record["path"] = str(dest)
        record["sha256"] = sha_bytes(payload)
        record["mechanism"] = "bundled_site_packages"
    else:
        dest.write_bytes(payload)
        record["mutations"].append({
            "action": "created", "path": str(dest),
            "sha256": sha_bytes(payload), "bytes": len(payload),
            "payload_b64": _b64(payload),
        })
        record["path"] = str(dest)
        record["mechanism"] = "bundled_site_packages"
    pth = interpreter_pth(interpreter)
    if pth and pth.is_file():
        original = pth.read_bytes()
        active = pth_active_import_site(original)
        record["pth_active_import_site"] = active
        record["pth_commented_import_site_ignored"] = (not active) and (b"import site" in original)
        if not active:
            written = append_active_import_site(original)
            pth.write_bytes(written)
            record["mutations"].append({
                "action": "pth_appended", "path": str(pth),
                "original_b64": _b64(original),
                "written_b64": _b64(written),
                "mark": PTH_SITE_MARK.strip(),
                "newline": pth_newline(original).decode("ascii"),
            })
            record["mechanism"] = "bundled_site_packages_plus_pth_import_site"
        else:
            record["pth_already_imports_site"] = True
    record["restorable"] = True
    return record


def restore_guard(record: dict | None) -> dict:
    """Restore only exact receipt-owned bytes after all children have exited.

    A modified sitecustomize is not deleted merely because its prefix matches.
    A python._pth whose current bytes are not the receipt-written bytes is left.
    Original newline style is preserved by writing the recorded original bytes.
    """
    restored = []
    failures = []
    if not record:
        return {"restored": restored, "ok": True, "failures": failures}
    for item in record.get("mutations") or []:
        path = Path(item["path"])
        action = item.get("action")
        try:
            if action == "created" and path.is_file():
                current = path.read_bytes()
                expected = _unb64(item.get("payload_b64")) if item.get("payload_b64") else None
                if expected is not None and current == expected:
                    path.unlink()
                    restored.append({"path": str(path), "action": "removed", "exact_receipt_bytes": True})
                elif item.get("sha256") and sha_bytes(current) == item.get("sha256"):
                    path.unlink()
                    restored.append({"path": str(path), "action": "removed", "exact_receipt_bytes": True})
                else:
                    restored.append({
                        "path": str(path),
                        "action": "left_modified",
                        "reason": "guard bytes are no longer the receipt-owned payload; prefix match is not deletion",
                    })
            elif action == "pth_appended" and path.is_file():
                original = _unb64(item.get("original_b64"))
                written = _unb64(item.get("written_b64"))
                current = path.read_bytes()
                if original is not None and written is not None and current == written:
                    path.write_bytes(original)
                    restored.append({"path": str(path), "action": "pth_restored", "exact_original_bytes": True})
                elif original is not None and current == original:
                    restored.append({"path": str(path), "action": "pth_already_original"})
                elif "original" in item and isinstance(item["original"], str) and written is None:
                    path.write_text(item["original"], encoding="utf-8")
                    restored.append({"path": str(path), "action": "pth_restored_legacy_text"})
                else:
                    restored.append({
                        "path": str(path),
                        "action": "left_modified",
                        "reason": "python._pth bytes are not the receipt-owned mutation",
                    })
        except OSError as exc:
            failures.append({"path": str(path), "action": action, "error": str(exc)})
    failures.extend(row for row in restored if row.get("action") == "left_modified")
    return {"restored": restored, "ok": not failures, "failures": failures}


def prove_guard_canary(*, interpreter: Path, env: dict, profile: Path, cwd: Path | None = None) -> dict:
    """Prove the installed guard refuses a disposable canary before product execution.

    Never hashes, stats, or opens the live forbidden index. The live path is
    compared as a string only.
    """
    from p4_session import spawn_owned

    profile = Path(profile)
    canary_dir = profile / "guard-canary"
    canary_dir.mkdir(parents=True, exist_ok=True)
    canary_index = canary_dir / "canary-index.db"
    canary_index.write_bytes(b"P4-CANARY-NOT-LIVE-INDEX\n")
    script = canary_dir / "open_canary.py"
    script.write_text(
        "import os, sqlite3, sys\n"
        "path = os.environ['P4_CANARY_INDEX']\n"
        "try:\n"
        "    sqlite3.connect(path)\n"
        "    sys.stdout.write('opened\\n')\n"
        "    raise SystemExit(0)\n"
        "except PermissionError:\n"
        "    sys.stdout.write('refused\\n')\n"
        "    raise SystemExit(2)\n"
        "except Exception as exc:\n"
        "    sys.stdout.write(type(exc).__name__ + ':' + str(exc) + '\\n')\n"
        "    raise SystemExit(1)\n",
        encoding="utf-8", newline="\n",
    )
    child_env = dict(env)
    child_env["P4_CANARY_INDEX"] = str(canary_index)
    child_env["P4_FORBIDDEN_INDEX"] = str(canary_index)
    if os.environ.get("IG_FORBIDDEN_LIVE"):
        child_env["IG_FORBIDDEN_LIVE"] = os.environ["IG_FORBIDDEN_LIVE"]
    pythonpath = [str(profile / "guard")]
    existing = child_env.get("PYTHONPATH")
    if existing:
        pythonpath.append(existing)
    child_env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    owned = spawn_owned(
        [str(interpreter), "-B", str(script)],
        cwd=str(cwd or profile), env=child_env, label="p4-guard-canary",
    )
    try:
        try:
            owned.wait(timeout=8.0)
        except Exception:
            owned.terminate_tree(timeout=2.0)
        stdout = (owned.popen.stdout.read() or b"").decode("utf-8", "replace")
        stderr = (owned.popen.stderr.read() or b"").decode("utf-8", "replace")
        code = owned.popen.poll()
        refused = code == 2 and "refused" in stdout
        return {
            "refused": refused,
            "exit_code": code,
            "stdout": stdout[-500:],
            "stderr_tail": stderr[-500:],
            "canary_path": str(canary_index),
            "live_index_opened": False,
            "live_index_hashed": False,
            "live_index_stat": False,
            "ig_forbidden_live": child_env.get("IG_FORBIDDEN_LIVE"),
        }
    finally:
        owned.terminate_tree(timeout=2.0)


def bind_product_isolation_before_import(binding: dict) -> dict:
    """Apply product isolation before importing any installed module."""
    app = Path(binding["installed_app"])
    module = app / "uoink_install_isolation.py"
    result = {"applied": False, "module": str(module), "present": module.is_file()}
    if not module.is_file():
        result["note"] = "isolation module absent; original product ignores isolation flags"
        return result
    if str(app) not in sys.path:
        sys.path.insert(0, str(app))
    import uoink_install_isolation as iso  # type: ignore
    argv = [
        "--isolated-profile", binding["isolated_profile"],
        "--isolated-port", str(binding["isolated_port"]),
    ]
    try:
        iso.apply_from_process(argv=argv, environ=os.environ)
        result["applied"] = True
        result["profile"] = str(iso.current_binding().profile) if iso.current_binding() else None
        result["index_path"] = str(isolated_index_path(Path(binding["isolated_profile"])))
    except SystemExit as exc:
        result["error"] = f"isolation apply exited {exc.code}"
        raise IsolationError(result["error"]) from exc
    return result


def installed_stdio_command(binding: dict, *, entry: Path | None = None) -> list[str]:
    """Original installed stdio argv, including isolation flags. Never drop the flags."""
    interpreter = binding["installed_interpreter"]
    script = str(entry or Path(binding["installed_entry"]))
    argv = [interpreter]
    if binding.get("runtime_mode") == RUNTIME_INSTALLED:
        argv.extend(["-P", "-B", "-s"])
    else:
        argv.extend(["-B"])
    argv.extend([
        script,
        "--isolated-profile", binding["isolated_profile"],
        "--isolated-port", str(binding["isolated_port"]),
    ])
    return argv


def record_product_finding(*, operation: str, input_value, error: str, route: str) -> dict:
    return {
        "kind": "product_finding",
        "operation": operation,
        "route": route,
        "input": input_value,
        "error": error,
        "hidden_by_special_route": False,
        "status": "failed",
    }


def add_common_args(parser) -> None:
    parser.add_argument("--isolated-profile", type=Path, required=True)
    parser.add_argument("--isolated-port", required=True)
    parser.add_argument("--installed-app", type=Path, required=True)
    parser.add_argument("--installed-interpreter", type=Path, required=True)
    parser.add_argument("--package-manifest", type=Path, required=True)
    parser.add_argument("--receipt-root", type=Path, required=True)
    parser.add_argument("--forbid-checkout", type=Path, default=None)
    parser.add_argument("--package-path", type=Path, default=None,
                        help="Actual package bytes; required for installed eligibility")
    parser.add_argument(
        "--source-bindings", type=Path, default=None,
        help="Candidate-package same-purpose sealed file digests (SHA-256 per file, 40-hex git blobs)",
    )
    parser.add_argument(
        "--runtime-mode",
        choices=(RUNTIME_INSTALLED, RUNTIME_SOURCE, RUNTIME_INSTRUMENT),
        default=None,
        help="installed requires sealed provenance; source-runtime is the pre-Inno path",
    )
    parser.add_argument(
        "--instrument-only",
        action="store_true",
        help="Synthetic instrument check; not installed credit",
    )


def bind_from_args(args) -> dict:
    return validate_isolation(
        isolated_profile=args.isolated_profile,
        isolated_port=args.isolated_port,
        receipt_root=args.receipt_root,
        installed_app=args.installed_app,
        installed_interpreter=args.installed_interpreter,
        package_manifest=args.package_manifest,
        forbid_checkout=args.forbid_checkout,
        instrument_only=bool(args.instrument_only),
        runtime_mode=getattr(args, "runtime_mode", None),
        package_path=getattr(args, "package_path", None),
        source_bindings_path=getattr(args, "source_bindings", None),
    )


def python_exe() -> str:
    return sys.executable
