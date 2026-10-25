"""Public store identity shared by the helper and bundled extension. No app state."""
from __future__ import annotations

import json
import re
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "extension" / "store-config.json"
EMPTY_CONFIG = {"chrome_web_store_id": "", "chrome_web_store_url": ""}


def validate_store_config(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != set(EMPTY_CONFIG):
        raise ValueError("store-config.json must contain only the store ID and URL")
    item_id = value["chrome_web_store_id"]
    url = value["chrome_web_store_url"]
    if not isinstance(item_id, str) or not isinstance(url, str):
        raise ValueError("Store ID and URL must be strings")
    if item_id and not re.fullmatch(r"[a-p]{32}", item_id):
        raise ValueError("Paste the 32-letter Chrome Web Store item ID, not an origin or URL")
    if url and (not item_id or not re.fullmatch(
        r"https://chromewebstore\.google\.com/detail/(?:[a-z0-9-]+/)?" + item_id, url
    )):
        raise ValueError("Store URL must be the HTTPS Chrome Web Store detail link for this ID")
    return dict(value)


def load_store_config(path: Path | None = None, *, strict: bool = False) -> dict[str, str]:
    try:
        return validate_store_config(json.loads((path or CONFIG_PATH).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        if strict:
            raise
        # A missing or damaged file must never broaden the trusted origins.
        return dict(EMPTY_CONFIG)
