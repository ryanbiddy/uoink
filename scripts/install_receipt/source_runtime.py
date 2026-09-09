"""Provision a disposable source-runtime tree with archived isolation.

This is source-runtime synthetic verification, never installed evidence.
Copies current product files into a scratch app, extracts
`uoink_install_isolation.py` from the archived first isolation patch, and
injects apply_from_process / data-root / port / token / suite-registry
bindings. The rejected isolation `--isolated-stop` path is not invoked.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from .hashes import omit_raw_bytes, sha256_bytes, sha256_file
from .validation import C22ValidationError, forbidden_live_path_string

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHIVED_ISOLATION_PATCH = (
    REPO_ROOT / "docs" / "library" / "proof"
    / "ryan-install-review-2026-09-09" / "original.patch"
)
MARKER_NAME = "isolated-install.json"
ISOLATION_MODULE = "uoink_install_isolation.py"

_COPY_SKIP_DIRS = {
    ".git", "__pycache__", "_scratch", "docs", "tests", ".pytest_cache",
    "tauri-ui", "extension", "build-prompts", "vendor", "scripts",
    "installer", "skills",
}


def extract_archived_isolation(dest: Path) -> dict[str, Any]:
    if not ARCHIVED_ISOLATION_PATCH.is_file():
        raise C22ValidationError(
            f"archived isolation patch missing: {ARCHIVED_ISOLATION_PATCH}")
    text = ARCHIVED_ISOLATION_PATCH.read_text(encoding="utf-8")
    marker = "+++ b/uoink_install_isolation.py"
    start = text.find(marker)
    if start < 0:
        raise C22ValidationError(
            "archived isolation patch does not contain uoink_install_isolation.py")
    body_start = text.find("\n", start)
    lines = []
    for line in text[body_start + 1:].splitlines():
        if line.startswith("diff --git "):
            break
        if line.startswith("+"):
            lines.append(line[1:])
        elif line.startswith("\\"):
            continue
        elif line.startswith("-"):
            continue
        else:
            # context line in a new-file patch should not appear; ignore
            continue
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    dest.write_bytes(payload)
    return {
        "path": str(dest),
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "source_patch": str(ARCHIVED_ISOLATION_PATCH),
        "note": "archived first isolation source; rejected --isolated-stop is not run",
    }


def copy_product_tree(dest: Path) -> dict[str, Any]:
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for item in REPO_ROOT.iterdir():
        if item.name in _COPY_SKIP_DIRS or item.name.startswith("."):
            continue
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(
                item, target,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"),
                dirs_exist_ok=True,
            )
        elif item.is_file():
            shutil.copy2(item, target)
        copied.append(item.name)
    return {"dest": str(dest), "copied": sorted(copied)}


def _inject_server_isolation(server_py: Path) -> dict[str, Any]:
    text = server_py.read_text(encoding="utf-8")
    original_sha = sha256_bytes(text.encode("utf-8"))
    if "uoink_install_isolation" in text and "apply_from_process()" in text:
        return {
            "path": str(server_py),
            "already_isolated": True,
            "sha256": original_sha,
        }
    needle = "sys.path.insert(0, str(HERE))\n"
    if needle not in text:
        raise C22ValidationError(
            "source-runtime: cannot find sys.path.insert in scratch server.py")
    insert = (
        needle
        + "\n# C22 source-runtime isolation (scratch copy only).\n"
        + "import uoink_install_isolation as _install_isolation  # noqa: E402\n"
        + "_install_isolation.apply_from_process()\n"
    )
    text = text.replace(needle, insert, 1)
    text = text.replace(
        'HOST = "127.0.0.1"\nPORT = 5179\n',
        'HOST = _install_isolation.listen_host("127.0.0.1")\n'
        "PORT = _install_isolation.listen_port(5179)\n",
        1,
    )
    text = text.replace(
        "TOKEN_PATH = HERE / \"token.txt\"\n",
        "_ISOLATION = _install_isolation.current_binding()\n"
        "TOKEN_PATH = (\n"
        "    _ISOLATION.token_path if _ISOLATION is not None else HERE / \"token.txt\"\n"
        ")\n",
        1,
    )
    text = text.replace(
        "DATA_ROOT = _platform.user_data_dir()\n",
        "DATA_ROOT = _install_isolation.data_root(_platform.user_data_dir())\n",
        1,
    )
    migrate_call = "        _mig = migrate_install.run_migration(app_dir=HERE)\n"
    if migrate_call in text and "skipped_isolated_install" not in text:
        text = text.replace(
            migrate_call,
            "        if _install_isolation.current_binding() is not None:\n"
            "            log.info(\"install migration: skipped_isolated_install\")\n"
            "            _mig = {\"outcome\": \"skipped_isolated_install\"}\n"
            "        else:\n"
            "            _mig = migrate_install.run_migration(app_dir=HERE)\n",
            1,
        )
    server_py.write_text(text, encoding="utf-8")
    return {
        "path": str(server_py),
        "already_isolated": False,
        "original_sha256": original_sha,
        "sha256": sha256_file(server_py),
        "bytes": server_py.stat().st_size,
    }


def _inject_suite_isolation(suite_py: Path) -> dict[str, Any]:
    text = suite_py.read_text(encoding="utf-8")
    original_sha = sha256_bytes(text.encode("utf-8"))
    if "uoink_install_isolation" in text and "suite_registry_dir" in text:
        return {"path": str(suite_py), "already_isolated": True,
                "sha256": original_sha}
    helper = '''
def _active_binding():
    try:
        import uoink_install_isolation as iso
        return iso.current_binding()
    except Exception:
        return None


'''
    if "def _active_binding(" not in text:
        text = text.replace(
            "def utc_now() -> str:",
            helper + "def utc_now() -> str:",
            1,
        )
    old_lease_start = (
        "    \"\"\"Atomically replace Uoink's runtime lease with per-user permissions.\"\"\"\n"
        "    registry = (\n"
        "        runtime_registry_dir() if registry_dir is None else Path(registry_dir)\n"
        "    )\n"
    )
    new_lease_start = (
        "    \"\"\"Atomically replace Uoink's runtime lease with per-user permissions.\"\"\"\n"
        "    if registry_dir is None:\n"
        "        binding = _active_binding()\n"
        "        if binding is not None:\n"
        "            registry = binding.suite_registry_dir()\n"
        "        else:\n"
        "            registry = runtime_registry_dir()\n"
        "    else:\n"
        "        registry = Path(registry_dir)\n"
    )
    if old_lease_start in text:
        text = text.replace(old_lease_start, new_lease_start, 1)
    text = text.replace(
        '        "base_url": BASE_URL,\n'
        '        "health_url": f"{BASE_URL}{HEALTH_PATH}",\n'
        '        "manifest_url": f"{BASE_URL}{MANIFEST_PATH}",\n',
        '        "base_url": (_active_binding().base_url if _active_binding() is not None else BASE_URL),\n'
        '        "health_url": f"{(_active_binding().base_url if _active_binding() is not None else BASE_URL)}{HEALTH_PATH}",\n'
        '        "manifest_url": f"{(_active_binding().base_url if _active_binding() is not None else BASE_URL)}{MANIFEST_PATH}",\n',
        1,
    )
    suite_py.write_text(text, encoding="utf-8")
    return {
        "path": str(suite_py),
        "already_isolated": False,
        "original_sha256": original_sha,
        "sha256": sha256_file(suite_py),
    }


def write_install_marker(app: Path, *, profile: Path, port: int,
                         overwrite: bool = False) -> dict[str, Any]:
    payload = {
        "mode": "isolated",
        "profile": str(profile),
        "port": int(port),
        "app_dir": str(app),
    }
    dest = app / MARKER_NAME
    if dest.is_file() and not overwrite:
        try:
            existing = json.loads(dest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise C22ValidationError(
                f"isolated-install.json is unreadable; refusing rewrite: {exc}") from exc
        if (str(existing.get("profile") or "") != str(profile)
                or int(existing.get("port") or -1) != int(port)):
            raise C22ValidationError(
                "refusing to rewrite isolated-install.json to switch profiles; "
                "use a separate isolated app or the CLI --isolated-profile/"
                "--isolated-port binding that preserves installer ownership")
        return {
            "path": str(dest),
            "sha256": sha256_file(dest),
            "payload": existing,
            "unchanged": True,
        }
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"path": str(dest), "sha256": sha256_file(dest), "payload": payload,
            "unchanged": False}


def _isolation_from_checkout(dest: Path) -> dict[str, Any] | None:
    """Prefer the checkout's integrated isolation when it matches current server.main.

    The archived first isolation patch lacks current_process_executable, which
    current server.main calls. Overlaying that stale module is not a source
    observation of original current server.main. Rejected --isolated-stop is
    still not invoked.
    """
    path = dest / ISOLATION_MODULE
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if "def apply_from_process(" not in text:
        return None
    if "def current_process_executable(" not in text:
        return None
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "source": "checkout_integrated",
        "archived_overlay_skipped": True,
        "rejected_stop_not_run": True,
        "note": (
            "Current uoink_install_isolation.py already matches server.main. "
            "Archived first isolation patch is not overlaid."
        ),
    }


def provision(*, dest: Path, profile: Path, port: int) -> dict[str, Any]:
    """Build a disposable isolated source-runtime tree. Never installed credit."""
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise C22ValidationError(
            f"source-runtime dest must be empty: {dest}")
    live = forbidden_live_path_string()
    copied = copy_product_tree(dest)
    isolation = _isolation_from_checkout(dest)
    if isolation is None:
        isolation = extract_archived_isolation(dest / ISOLATION_MODULE)
    server_patch = _inject_server_isolation(dest / "server.py")
    suite_patch = _inject_suite_isolation(dest / "suite_service.py")
    marker = write_install_marker(dest, profile=profile, port=port)
    # Do not create python/python.exe here: that would flip installed-layout
    # tray/splash. Source-runtime uses the invoking interpreter with cwd=dest.
    return {
        "kind": "source_runtime_synthetic",
        "installed_credit": False,
        "dest": str(dest),
        "copied": copied,
        "isolation": isolation,
        "server_patch": server_patch,
        "suite_patch": suite_patch,
        "marker": marker,
        "live_index_forbidden": str(live),
        "opened_live_index": False,
        "hashed_live_index": False,
        "rejected_stop_not_run": True,
        "interpreter": sys.executable,
        "note": (
            "Source-runtime tree with archived isolation + current server.main. "
            "Not a bundled installed interpreter. Astra owns final bundled verification."
        ),
    }


def restore_guard_file(path: Path, *, original: bytes | None,
                       expected_sha256: str | None,
                       owned_sha256: str | None = None) -> dict[str, Any]:
    """Restore exact receipt-owned bytes. Refuse a conflict instead of deleting."""
    from .guards import restore_guard_install
    return restore_guard_install(
        path, original=original, original_sha256=expected_sha256,
        owned_sha256=owned_sha256, children_stopped=True,
        descendants_stopped=True, descendants_unknown=False,
    )
