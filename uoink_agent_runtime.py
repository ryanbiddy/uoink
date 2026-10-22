"""Shared agent dispatch and resident-helper identity check.

Semantic search uses the resident helper after its process identity is checked.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import uoink_install_isolation as isolation
import uoink_mcp_tools as registry


def helper_running(backend) -> bool:
    """Read process identity only; never probe an HTTP port."""
    binding = isolation.current_binding()
    if binding is not None:
        return isolation.owned_process_status(binding) == "alive"
    if sys.platform == "darwin":
        # macOS keeps the helper's identity record in the data dir, not beside
        # the (read-only) app files; see _platform.darwin_helper_running.
        return backend._platform.darwin_helper_running(backend.HERE, backend.DATA_ROOT)
    try:
        pid_path = backend.HERE / "server.pid"
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        if pid <= 0 or pid == os.getpid():
            return False
        image = isolation._process_executable(pid)
        own_image = isolation.current_process_executable()
        if not image or not own_image:
            return False
        allowed_images = {Path(own_image).resolve()}
        if os.name == "nt":
            allowed_images.add(Path(own_image).with_name("pythonw.exe").resolve())
            allowed_images.add(Path(own_image).with_name("python.exe").resolve())
        if Path(image).resolve() not in allowed_images:
            return False
        if os.name == "nt":
            handle, _ = isolation._windows_open_process(
                pid, isolation._PROCESS_QUERY_LIMITED_INFORMATION)
            if not handle:
                return False
            try:
                created_ms = isolation._windows_process_created_ms(handle)
            finally:
                isolation._windows_close_handle(handle)
        else:
            created_ms = isolation._posix_process_created_ms(pid)
        if created_ms is None or created_ms > pid_path.stat().st_mtime_ns // 1_000_000:
            return False
        return isolation._pid_liveness(pid, created_ms) == "alive"
    except (OSError, ValueError, UnicodeError):
        return False


def dispatch_search(name, arguments, backend, local, *, running=None):
    """Keep the model in the resident helper, including for stdio clients."""
    if name not in ("search_library", "search_uoinks", "search_clips"):
        return local()
    args = arguments if isinstance(arguments, dict) else {}
    if args.get("mode", "auto") not in ("auto", "semantic", "hybrid"):
        return local()
    from uoink_core.local_search import LocalSearch
    if not LocalSearch.enabled_at(backend.DATA_ROOT):
        return local()
    try:
        if running() if running is not None else helper_running(backend):
            result = backend._call_http_registry_tool(name, args, timeout=1.5)
            if result.get("ok") is True and result.get("search_mode") in ("keyword", "semantic", "hybrid"):
                return result
    except Exception:
        pass
    result = local()
    if result.get("ok") is True:
        result.update(search_mode="keyword", requested_mode=args.get("mode", "auto"),
                      fallback_reason="The semantic search helper is unavailable. Open Uoink and retry. Keyword search still works.")
    return result


def call_tool(name, arguments, backend, *, running=None):
    if name == "poll_monitored_playlist" and not (
            running() if running is not None else helper_running(backend)):
        return {"ok": False, "error": "Open Uoink first, then retry polling the monitored playlist. "
                "Its scheduled captures need the running Uoink helper."}
    return dispatch_search(name, arguments, backend, lambda: registry.call_tool(name, arguments), running=running)
