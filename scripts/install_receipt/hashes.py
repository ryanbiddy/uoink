"""Byte hashing for C22 receipts. Never invents expected package hashes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def file_record(path: Path, *, root: Path | None = None) -> dict[str, Any]:
    path = Path(path)
    rel = str(path.relative_to(root)).replace("\\", "/") if root else str(path)
    data = path.read_bytes() if path.is_file() else b""
    return {
        "path": rel,
        "bytes": len(data) if path.is_file() else None,
        "sha256": sha256_bytes(data) if path.is_file() else None,
        "is_file": path.is_file(),
        "missing": not path.exists(),
    }


def omit_raw_bytes(value: Any) -> Any:
    """JSON-safe form. Raw bytes are replaced by length+digest, never dumped."""
    if isinstance(value, bytes):
        return {
            "omitted_raw_bytes": True,
            "bytes": len(value),
            "sha256": sha256_bytes(value),
        }
    if isinstance(value, dict):
        return {str(key): omit_raw_bytes(item) for key, item in value.items()
                if key != "popen"}
    if isinstance(value, (list, tuple)):
        return [omit_raw_bytes(item) for item in value]
    return value
