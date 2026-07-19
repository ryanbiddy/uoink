"""Read-only discovery bridge for the optional local Writer product.

Uoink never reads Writer's token file, database, or data directory. A user or
launcher may provide the peer URL and credential through process environment.
The compatibility window keeps Uoink's Capture and Generate paths unchanged;
this module reports readiness for an explicit later cutover.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_URL = "http://127.0.0.1:5181"
URL_ENV = "UOINK_WRITER_URL"
TOKEN_ENV = "UOINK_WRITER_TOKEN"
MAX_RESPONSE_BYTES = 1024 * 1024

_COMPATIBILITY = {
    "capture": "uoink",
    "generate": "monolith",
    "writes": "single-owner-per-mode",
}


class WriterPeerError(ValueError):
    pass


def _base_url() -> str:
    value = str(os.environ.get(URL_ENV) or DEFAULT_URL).strip()
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in {
            "127.0.0.1", "localhost", "::1"}:
        raise WriterPeerError(
            "Writer URL must be an http loopback address")
    if parsed.port is None:
        raise WriterPeerError("Writer URL requires a loopback port")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise WriterPeerError(
            "Writer URL must contain only scheme, host, and port")
    return value.rstrip("/")


def _read(path: str, *, token: str = "") -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json"}
    if token:
        headers["X-Writer-Token"] = token
    request = urllib.request.Request(
        _base_url() + path, headers=headers)
    status = 200
    try:
        with urllib.request.urlopen(request, timeout=1.5) as response:
            status = int(response.status)
            content_type = response.headers.get_content_type()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        status = int(error.code)
        content_type = error.headers.get_content_type()
        raw = error.read(MAX_RESPONSE_BYTES + 1)
    if content_type != "application/json":
        raise WriterPeerError("Writer returned a non-JSON response")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise WriterPeerError(
            "Writer status exceeded the local safety limit")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WriterPeerError("Writer returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise WriterPeerError("Writer status must be an object")
    return status, payload


def _base(*, configured: bool, availability: str) -> dict[str, Any]:
    return {
        "ok": True,
        "peer": "writer",
        "configured": configured,
        "availability": availability,
        "api_version": 1,
        "standalone": True,
        "compatibility": dict(_COMPATIBILITY),
    }


def status() -> dict[str, Any]:
    token = str(os.environ.get(TOKEN_ENV) or "").strip()
    try:
        _base_url()
    except WriterPeerError as exc:
        return {
            "ok": False,
            "peer": "writer",
            "configured": bool(token),
            "availability": "invalid_configuration",
            "error": str(exc),
        }
    try:
        if not token:
            http_status, payload = _read("/ping")
            if http_status == 200 and payload == {
                    "ok": True,
                    "service": "writer",
                    "version": 1,
                    "status": "ready"}:
                return _base(
                    configured=False,
                    availability="detected_unconfigured",
                )
            return _base(
                configured=False,
                availability="not_running",
            )
        http_status, payload = _read(
            "/api/writer/v1/status", token=token)
    except (urllib.error.URLError, OSError, TimeoutError, WriterPeerError):
        return _base(
            configured=bool(token),
            availability="not_running",
        )
    if http_status in (401, 403):
        return _base(
            configured=True,
            availability="authentication_failed",
        )
    expected = {
        "ok", "contract", "version", "data"}
    if http_status != 200 or set(payload) != expected \
            or payload.get("ok") is not True \
            or payload.get("contract") != "writer.api" \
            or payload.get("version") != 1:
        result = _base(
            configured=True,
            availability="contract_mismatch",
        )
        result["ok"] = False
        return result
    data = payload.get("data")
    if not isinstance(data, dict) \
            or data.get("service") != "writer" \
            or data.get("database") != "ready" \
            or data.get("schema_version") != 1 \
            or not isinstance(data.get("counts"), dict):
        result = _base(
            configured=True,
            availability="contract_mismatch",
        )
        result["ok"] = False
        return result
    result = _base(
        configured=True,
        availability="available",
    )
    result["writer"] = {
        "database": "ready",
        "schema_version": 1,
        "counts": {
            name: int(data["counts"].get(name) or 0)
            for name in (
                "drafts", "pieces", "scripts", "voice_samples")
        },
    }
    return result
