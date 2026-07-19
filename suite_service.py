"""Uoink-owned suite discovery, health, and runtime-lease contracts."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SERVICE_ID = "uoink"
SERVICE_NAME = "Uoink"
DEFAULT_PORT = 5179
BASE_URL = f"http://127.0.0.1:{DEFAULT_PORT}"
HEALTH_PATH = "/api/suite/v1/health"
MANIFEST_PATH = "/.well-known/suite-service.json"
CAPABILITIES = (
    "uoink.corpus.read/1",
    "uoink.engagement.ingest/1",
    "uoink.media.handoff/1",
)
UI = {
    "home": "/dashboard",
    "routes": {
        "library": "/dashboard#library",
    },
}


def utc_now() -> str:
    """Return a second-precision RFC 3339 UTC timestamp."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def service_manifest(service_version: str) -> dict:
    """Return the exact public ``ryan.suite.service`` v1 provider shape."""
    return {
        "ok": True,
        "contract": "ryan.suite.service",
        "version": 1,
        "service": {
            "id": SERVICE_ID,
            "name": SERVICE_NAME,
            "service_version": service_version,
            "api_version": 1,
            "resident": True,
            "default_port": DEFAULT_PORT,
            "health": {
                "contract": "ryan.suite.health",
                "version": 1,
                "href": HEALTH_PATH,
            },
            "capabilities": list(CAPABILITIES),
            "ui": {
                "home": UI["home"],
                "routes": dict(UI["routes"]),
            },
            "mcp": {
                "name": SERVICE_ID,
                "transport": "stdio",
            },
        },
    }


def health_payload(
    service_version: str,
    *,
    index_recovering: bool,
    corpus_paths_ok: bool,
) -> dict:
    """Return Uoink's bounded, path-free ``ryan.suite.health`` v1 shape."""
    checks = [
        {"id": "core", "required": True, "status": "ready"},
        {
            "id": "index",
            "required": True,
            "status": "busy" if index_recovering else "ready",
        },
        {
            "id": "corpus_paths",
            "required": True,
            "status": "ready" if corpus_paths_ok else "failed",
        },
    ]
    if any(check["status"] == "failed" for check in checks):
        ok = False
        state = "needs_attention"
    elif any(check["status"] in {"busy", "degraded"} for check in checks):
        ok = True
        state = "ready_with_limits"
    else:
        ok = True
        state = "ready"
    return {
        "ok": ok,
        "contract": "ryan.suite.health",
        "version": 1,
        "service_id": SERVICE_ID,
        "service_version": service_version,
        "state": state,
        "checks": checks,
    }


def runtime_registry_dir(
    *,
    platform_name: str | None = None,
    environ: dict[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Resolve the contract's per-user, non-executable runtime registry."""
    platform_name = platform_name or sys.platform
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    if platform_name == "win32":
        local_app_data = environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else home / "AppData" / "Local"
        return base / "RyanSuite" / "services.d"
    if platform_name == "darwin":
        return home / "Library" / "Application Support" / "RyanSuite" / "services.d"
    state_home = environ.get("XDG_STATE_HOME")
    base = Path(state_home) if state_home else home / ".local" / "state"
    return base / "ryan-suite" / "services.d"


def runtime_lease(
    service_version: str,
    *,
    pid: int,
    started_at: str,
) -> dict:
    """Return Uoink's exact token-free ``ryan.suite.runtime-lease`` v1."""
    return {
        "contract": "ryan.suite.runtime-lease",
        "version": 1,
        "service_id": SERVICE_ID,
        "service_version": service_version,
        "api_version": 1,
        "base_url": BASE_URL,
        "health_url": f"{BASE_URL}{HEALTH_PATH}",
        "manifest_url": f"{BASE_URL}{MANIFEST_PATH}",
        "capabilities": list(CAPABILITIES),
        "ui": {
            "home": UI["home"],
            "routes": dict(UI["routes"]),
        },
        "pid": int(pid),
        "started_at": started_at,
    }


def write_runtime_lease(
    registry_dir: Path | None = None,
    *,
    service_version: str,
    pid: int,
    started_at: str,
) -> Path:
    """Atomically replace Uoink's runtime lease with per-user permissions."""
    registry = (
        runtime_registry_dir() if registry_dir is None else Path(registry_dir)
    )
    registry.mkdir(parents=True, exist_ok=True)
    destination = registry / f"{SERVICE_ID}.json"
    payload = runtime_lease(
        service_version,
        pid=pid,
        started_at=started_at,
    )
    encoded = (
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    temporary: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            prefix=f".{SERVICE_ID}-",
            suffix=".tmp",
            dir=str(registry),
        )
        temporary = Path(raw_path)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, destination)
            temporary = None
            try:
                os.chmod(destination, 0o600)
            except OSError:
                pass
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def remove_runtime_lease(
    lease_path: Path,
    *,
    pid: int,
    started_at: str,
) -> bool:
    """Remove only the lease written by the matching process incarnation."""
    path = Path(lease_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if (
        not isinstance(payload, dict)
        or payload.get("service_id") != SERVICE_ID
        or payload.get("pid") != int(pid)
        or payload.get("started_at") != started_at
    ):
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True
