"""Strict discovery and health probing for Uoink's optional Writer peer.

Uoink receives Writer's credential from its own process environment. It never
opens Writer's token, database, or data directory. The only shared file read is
the token-free ``ryan.suite.runtime-lease`` in the suite registry.
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import socket
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import suite_service

DEFAULT_URL = "http://127.0.0.1:5181"
URL_ENV = "UOINK_WRITER_URL"
TOKEN_ENV = "UOINK_WRITER_TOKEN"
WRITER_CAPABILITIES = (
    "writer.api/1",
    "writer.shot-list/1",
)
MAX_RESPONSE_BYTES = 1024 * 1024

_LEASE_KEYS = {
    "contract",
    "version",
    "service_id",
    "service_version",
    "api_version",
    "base_url",
    "health_url",
    "manifest_url",
    "capabilities",
    "ui",
    "pid",
    "started_at",
}
_SERVICE_KEYS = {
    "id",
    "name",
    "service_version",
    "api_version",
    "resident",
    "default_port",
    "health",
    "capabilities",
    "ui",
    "mcp",
}
_CHECK_KEYS = {"id", "required", "status"}
_WRITER_STATUS_KEYS = {
    "service",
    "schema_version",
    "database",
    "uoink",
    "counts",
}
_WRITER_COUNT_KEYS = {
    "drafts",
    "pieces",
    "scripts",
    "voice_samples",
}
_UTC_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)


class WriterPeerError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class _TransportError(WriterPeerError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        absence_eligible: bool = False,
    ):
        super().__init__(code, message, retryable=retryable)
        self.absence_eligible = absence_eligible


@dataclass(frozen=True)
class WriterTarget:
    base_url: str
    source: str


def _error(
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> WriterPeerError:
    return WriterPeerError(code, message, retryable=retryable)


def _exact(
    value: Any,
    expected: set[str],
    label: str,
    *,
    code: str,
) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise _error(code, f"{label} does not match version 1")
    return value


def _base_url(value: Any, *, code: str) -> str:
    if not isinstance(value, str):
        raise _error(code, "Writer URL must be an HTTP loopback address")
    try:
        parsed = urllib.parse.urlparse(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise _error(
            code,
            "Writer URL must be an HTTP loopback address",
        ) from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or port is None
        or not 1 <= port <= 65535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise _error(code, "Writer URL must be an HTTP loopback address")
    return value.strip().rstrip("/")


def _ui(value: Any, *, code: str) -> dict:
    value = _exact(value, {"home", "routes"}, "ui", code=code)
    if not isinstance(value["home"], str) or not value["home"].startswith("/"):
        raise _error(code, "ui.home must be a relative service path")
    routes = value["routes"]
    if not isinstance(routes, dict) or any(
        not isinstance(name, str)
        or not isinstance(path, str)
        or not path.startswith("/")
        for name, path in routes.items()
    ):
        raise _error(code, "ui.routes must contain relative service paths")
    return value


def _capabilities(value: Any, *, code: str) -> list[str]:
    if (
        not isinstance(value, list)
        or value != sorted(set(value))
        or tuple(value) != WRITER_CAPABILITIES
    ):
        raise _error(code, "Writer capabilities do not match version 1")
    return value


def process_is_live(pid: int) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid < 1:
        return False
    if sys.platform == "win32":
        process_query = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query,
            False,
            pid,
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(
                handle,
                ctypes.byref(exit_code),
            ):
                return False
            return exit_code.value == 259
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def validate_runtime_lease(
    payload: Any,
    *,
    pid_checker: Callable[[int], bool] = process_is_live,
) -> dict:
    code = "invalid_lease"
    payload = _exact(payload, _LEASE_KEYS, "runtime lease", code=code)
    if (
        payload["contract"] != "ryan.suite.runtime-lease"
        or payload["version"] != 1
        or payload["service_id"] != "writer"
        or payload["api_version"] != 1
        or not isinstance(payload["service_version"], str)
        or not payload["service_version"]
    ):
        raise _error(code, "runtime lease identity does not match Writer v1")
    base = _base_url(payload["base_url"], code=code)
    if payload["health_url"] != f"{base}/api/suite/v1/health":
        raise _error(code, "runtime lease health URL is invalid")
    if (
        payload["manifest_url"]
        != f"{base}/.well-known/suite-service.json"
    ):
        raise _error(code, "runtime lease manifest URL is invalid")
    _capabilities(payload["capabilities"], code=code)
    _ui(payload["ui"], code=code)
    pid = payload["pid"]
    if not isinstance(pid, int) or isinstance(pid, bool) or pid < 1:
        raise _error(code, "runtime lease PID is invalid")
    started_at = payload["started_at"]
    if not isinstance(started_at, str) or not _UTC_TIMESTAMP.fullmatch(
        started_at
    ):
        raise _error(code, "runtime lease timestamp is invalid")
    try:
        datetime.fromisoformat(started_at[:-1] + "+00:00")
    except ValueError as exc:
        raise _error(code, "runtime lease timestamp is invalid") from exc
    if not pid_checker(pid):
        raise _error(
            "stale_lease",
            "Writer runtime lease process is no longer running",
            retryable=True,
        )
    return payload


def validate_service_manifest(payload: Any) -> dict:
    code = "contract_mismatch"
    payload = _exact(
        payload,
        {"ok", "contract", "version", "service"},
        "service manifest",
        code=code,
    )
    if (
        payload["ok"] is not True
        or payload["contract"] != "ryan.suite.service"
        or payload["version"] != 1
    ):
        raise _error(code, "service manifest contract does not match version 1")
    service = _exact(
        payload["service"],
        _SERVICE_KEYS,
        "service manifest service",
        code=code,
    )
    if service["id"] != "writer":
        raise _error(
            "wrong_service",
            "configured endpoint is not Writer",
        )
    if (
        service["name"] != "Writer"
        or not isinstance(service["service_version"], str)
        or not service["service_version"]
        or service["api_version"] != 1
        or service["resident"] is not True
        or service["default_port"] != 5181
    ):
        raise _error(code, "Writer service identity does not match version 1")
    health = _exact(
        service["health"],
        {"contract", "version", "href"},
        "service health descriptor",
        code=code,
    )
    if health != {
        "contract": "ryan.suite.health",
        "version": 1,
        "href": "/api/suite/v1/health",
    }:
        raise _error(code, "Writer health descriptor does not match version 1")
    _capabilities(service["capabilities"], code=code)
    _ui(service["ui"], code=code)
    mcp = _exact(
        service["mcp"],
        {"name", "transport"},
        "service mcp descriptor",
        code=code,
    )
    if mcp != {"name": "writer", "transport": "stdio"}:
        raise _error(code, "Writer MCP identity does not match version 1")
    return payload


def validate_health(payload: Any) -> dict:
    code = "contract_mismatch"
    payload = _exact(
        payload,
        {
            "ok",
            "contract",
            "version",
            "service_id",
            "service_version",
            "state",
            "checks",
        },
        "suite health",
        code=code,
    )
    if (
        payload["contract"] != "ryan.suite.health"
        or payload["version"] != 1
        or payload["service_id"] != "writer"
        or not isinstance(payload["service_version"], str)
        or not payload["service_version"]
        or payload["state"]
        not in {"ready", "ready_with_limits", "needs_attention"}
        or not isinstance(payload["ok"], bool)
    ):
        raise _error(code, "Writer health identity does not match version 1")
    checks = payload["checks"]
    if not isinstance(checks, list) or len(checks) != 2:
        raise _error(code, "Writer health checks do not match version 1")
    statuses = []
    for expected_id, check in zip(("core", "database"), checks):
        check = _exact(
            check,
            _CHECK_KEYS,
            "suite health check",
            code=code,
        )
        if (
            check["id"] != expected_id
            or check["required"] is not True
            or check["status"]
            not in {"ready", "busy", "degraded", "failed"}
        ):
            raise _error(code, "Writer health checks do not match version 1")
        statuses.append(check["status"])
    expected_ok = "failed" not in statuses
    if not expected_ok:
        expected_state = "needs_attention"
    elif any(status in {"busy", "degraded"} for status in statuses):
        expected_state = "ready_with_limits"
    else:
        expected_state = "ready"
    if payload["ok"] is not expected_ok or payload["state"] != expected_state:
        raise _error(code, "Writer health state is internally inconsistent")
    return payload


def _check_lease_permissions(path: Path) -> None:
    if sys.platform == "win32":
        return
    details = path.stat()
    if hasattr(os, "getuid") and details.st_uid != os.getuid():
        raise _error("invalid_lease", "runtime lease has the wrong owner")
    if stat.S_IMODE(details.st_mode) & 0o077:
        raise _error(
            "invalid_lease",
            "runtime lease permissions are not per-user",
        )


def resolve_writer_target(
    *,
    environ: dict[str, str] | None = None,
    registry_dir: Path | None = None,
    default_base_url: str = DEFAULT_URL,
    pid_checker: Callable[[int], bool] = process_is_live,
    check_permissions: bool = True,
) -> WriterTarget:
    environ = os.environ if environ is None else environ
    if URL_ENV in environ:
        return WriterTarget(
            base_url=_base_url(
                environ.get(URL_ENV),
                code="invalid_configuration",
            ),
            source="explicit",
        )
    registry = (
        suite_service.runtime_registry_dir()
        if registry_dir is None
        else Path(registry_dir)
    )
    lease_path = registry / "writer.json"
    if lease_path.exists():
        try:
            if check_permissions:
                _check_lease_permissions(lease_path)
            payload = json.loads(lease_path.read_text(encoding="utf-8"))
        except WriterPeerError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _error(
                "invalid_lease",
                "Writer runtime lease cannot be validated",
            ) from exc
        lease = validate_runtime_lease(
            payload,
            pid_checker=pid_checker,
        )
        return WriterTarget(
            base_url=lease["base_url"],
            source="lease",
        )
    return WriterTarget(
        base_url=_base_url(
            default_base_url,
            code="invalid_configuration",
        ),
        source="default",
    )


def _get_json(url: str, *, timeout: float) -> Any:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            content_type = response.headers.get_content_type()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise _TransportError(
            "unavailable",
            f"Writer suite probe returned HTTP {exc.code}",
            retryable=True,
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise _TransportError(
            "timeout",
            "Writer suite probe timed out",
            retryable=True,
            absence_eligible=True,
        ) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            code = "timeout"
            message = "Writer suite probe timed out"
        else:
            code = "unavailable"
            message = "Writer suite probe could not connect"
        raise _TransportError(
            code,
            message,
            retryable=True,
            absence_eligible=True,
        ) from exc
    except OSError as exc:
        raise _TransportError(
            "unavailable",
            "Writer suite probe could not connect",
            retryable=True,
            absence_eligible=True,
        ) from exc
    if status != 200 or content_type != "application/json":
        raise _TransportError(
            "unavailable",
            "Writer suite probe returned an invalid transport response",
            retryable=True,
        )
    if len(raw) > MAX_RESPONSE_BYTES:
        raise _TransportError(
            "unavailable",
            "Writer suite probe exceeded the response limit",
            retryable=True,
        )
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _TransportError(
            "unavailable",
            "Writer suite probe returned invalid JSON",
            retryable=True,
        ) from exc


def _validate_writer_status(payload: Any) -> dict:
    code = "contract_mismatch"
    payload = _exact(
        payload,
        {"ok", "contract", "version", "data"},
        "Writer status",
        code=code,
    )
    if (
        payload["ok"] is not True
        or payload["contract"] != "writer.api"
        or payload["version"] != 1
    ):
        raise _error(code, "Writer status contract does not match version 1")
    data = _exact(
        payload["data"],
        _WRITER_STATUS_KEYS,
        "Writer status data",
        code=code,
    )
    if (
        data["service"] != "writer"
        or data["schema_version"] != 1
        or data["database"] != "ready"
        or not isinstance(data["uoink"], str)
    ):
        raise _error(code, "Writer status identity does not match version 1")
    counts = _exact(
        data["counts"],
        _WRITER_COUNT_KEYS,
        "Writer status counts",
        code=code,
    )
    if any(
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        for value in counts.values()
    ):
        raise _error(code, "Writer status counts are invalid")
    return payload


def _get_writer_status(
    base_url: str,
    token: str,
    *,
    timeout: float,
) -> dict:
    request = urllib.request.Request(
        base_url + "/api/writer/v1/status",
        headers={
            "Accept": "application/json",
            "X-Writer-Token": token,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            content_type = response.headers.get_content_type()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise _error(
                "authentication_failed",
                "Writer rejected the configured credential",
            ) from exc
        raise _TransportError(
            "unavailable",
            f"Writer status returned HTTP {exc.code}",
            retryable=True,
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise _TransportError(
            "timeout",
            "Writer status timed out",
            retryable=True,
        ) from exc
    except urllib.error.URLError as exc:
        code = (
            "timeout"
            if isinstance(exc.reason, (TimeoutError, socket.timeout))
            else "unavailable"
        )
        raise _TransportError(
            code,
            "Writer status could not complete",
            retryable=True,
        ) from exc
    except OSError as exc:
        raise _TransportError(
            "unavailable",
            "Writer status could not complete",
            retryable=True,
        ) from exc
    if status != 200 or content_type != "application/json":
        raise _TransportError(
            "unavailable",
            "Writer status returned an invalid transport response",
            retryable=True,
        )
    if len(raw) > MAX_RESPONSE_BYTES:
        raise _TransportError(
            "unavailable",
            "Writer status exceeded the response limit",
            retryable=True,
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _TransportError(
            "unavailable",
            "Writer status returned invalid JSON",
            retryable=True,
        ) from exc
    return _validate_writer_status(payload)


def _available(capabilities: list[str]) -> dict:
    return {
        "ok": True,
        "contract": "ryan.suite.peer",
        "version": 1,
        "peer": "writer",
        "state": "available",
        "capabilities": list(capabilities),
    }


def _calm(state: str) -> dict:
    return {
        "ok": True,
        "contract": "ryan.suite.peer",
        "version": 1,
        "peer": "writer",
        "state": state,
        "capabilities": [],
    }


def _unhealthy(error: WriterPeerError) -> dict:
    return {
        "ok": False,
        "contract": "ryan.suite.peer",
        "version": 1,
        "peer": "writer",
        "state": "unhealthy",
        "error": {
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
        },
    }


def status(
    *,
    environ: dict[str, str] | None = None,
    registry_dir: Path | None = None,
    default_base_url: str = DEFAULT_URL,
    timeout: float = 1.5,
    pid_checker: Callable[[int], bool] = process_is_live,
    check_permissions: bool = True,
) -> dict[str, Any]:
    """Return Uoink's exact, path-free ``ryan.suite.peer`` v1 view."""
    environ = os.environ if environ is None else environ
    try:
        target = resolve_writer_target(
            environ=environ,
            registry_dir=registry_dir,
            default_base_url=default_base_url,
            pid_checker=pid_checker,
            check_permissions=check_permissions,
        )
    except WriterPeerError as exc:
        return _unhealthy(exc)
    try:
        manifest = validate_service_manifest(
            _get_json(
                target.base_url + "/.well-known/suite-service.json",
                timeout=timeout,
            )
        )
        health = validate_health(
            _get_json(
                target.base_url + "/api/suite/v1/health",
                timeout=timeout,
            )
        )
    except _TransportError as exc:
        if target.source == "default" and exc.absence_eligible:
            return _calm("absent")
        return _unhealthy(exc)
    except WriterPeerError as exc:
        return _unhealthy(exc)
    if not health["ok"]:
        return _unhealthy(
            _error(
                "peer_unhealthy",
                "Writer reported that it needs attention",
                retryable=True,
            )
        )
    token = str(environ.get(TOKEN_ENV) or "").strip()
    if not token:
        return _calm("unconfigured")
    try:
        _get_writer_status(
            target.base_url,
            token,
            timeout=timeout,
        )
    except WriterPeerError as exc:
        return _unhealthy(exc)
    return _available(manifest["service"]["capabilities"])
