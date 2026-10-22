"""Independent mirror of receiver src/validation.ts, R1 contract 2026-10-22.

Keep these rules independent of uoink_usage. The optional Node parity test
checks this mirror against the receiver without making a request.
"""
import json
import math
import re

FIELDS = {"schema", "install_id", "version", "os", "os_major", "arch", "install_kind",
          "period_hours", "mcp_clients", "transports", "tools", "captures", "searches"}
CLIENTS = {"claude-desktop", "claude-code", "cursor", "cline", "continue", "codex", "chatgpt", "vscode", "other"}
SOURCES = {"youtube", "x", "reddit", "page", "podcast", "image", "note", "other"}
UUID4 = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", re.I)
SEMVER = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-((?:0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?"
)


def matches(pattern, value):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def number(value):
    return type(value) in (int, float) and 0 <= value <= 100_000 and math.isfinite(value)


def count(value):
    return number(value) and int(value) == value


def counters(value, maximum, allowed):
    return (isinstance(value, dict) and len(value) <= maximum
            and all(allowed(key) and count(n) for key, n in value.items()))


def validate_ping(value):
    if (not isinstance(value, dict)
            or set(value) != FIELDS | ({"report_id"} if "report_id" in value else set())):
        raise ValueError("invalid_fields")
    rules = {
        "schema": lambda v: type(v) in (int, float) and v == 1,
        "install_id": lambda v: matches(UUID4, v),
        "version": lambda v: matches(SEMVER, v),
        "os": lambda v: v in ("windows", "macos", "linux"),
        "os_major": lambda v: matches(r"[0-9]{1,3}|unknown", v),
        "arch": lambda v: v in ("x86_64", "arm64", "other"),
        "install_kind": lambda v: v in ("installer", "mcpb", "source"),
        "period_hours": number,
        "tools": lambda v: counters(v, 128, lambda k: matches(r"[a-z0-9_]{3,64}", k)),
        "mcp_clients": lambda v: counters(v, 9, lambda k: k in CLIENTS),
        "transports": lambda v: (isinstance(v, dict) and set(v) == {"stdio", "http"}
                                  and all(count(n) for n in v.values())),
        "captures": lambda v: (isinstance(v, dict) and all(
            s in SOURCES and isinstance(outcomes, dict) and set(outcomes) == {"ok", "failed"}
            and all(count(n) for n in outcomes.values()) for s, outcomes in v.items())),
        "searches": count,
    }
    if "report_id" in value:
        rules["report_id"] = lambda v: matches(UUID4, v)
    for key, valid in rules.items():
        if not valid(value[key]):
            raise ValueError("invalid_" + key)
    if len(json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")) > 4096:
        raise ValueError("body_too_large")
    return value
