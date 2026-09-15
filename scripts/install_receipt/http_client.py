"""Token-gated HTTP client for the declared helper loopback port."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .constants import FORBIDDEN_PORT
from .validation import C22ValidationError, validate_port


class HelperClient:
    def __init__(self, port: int, token: str):
        self.port = validate_port(port)
        self.token = token
        self.base = f"http://127.0.0.1:{self.port}"

    def request(self, method: str, path: str, body: dict | None = None,
                timeout: float = 8.0) -> dict[str, Any]:
        if self.port == FORBIDDEN_PORT:
            raise C22ValidationError("refusing HTTP to port 5179")
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "X-Uoink-Token": self.token,
            "X-Uoink-Client": "uoink-extension",
            "Content-Type": "application/json",
            "Origin": self.base,
        }
        req = urllib.request.Request(
            self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read()
                parsed = json.loads(raw.decode("utf-8") or "{}")
                parsed["_http_status"] = response.status
                return parsed
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                parsed = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                parsed = {"error": raw.decode("utf-8", errors="replace")}
            parsed["_http_status"] = exc.code
            parsed.setdefault("ok", False)
            return parsed
