"""Render the README install step and website handoff from store-config.json."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from uoink_store import load_store_config

START = "<!-- store-install:start -->"
END = "<!-- store-install:end -->"
SIDELOAD = ('On first launch, Uoink shows a one-time setup splash. Use it to open your browser\'s '
            'extensions page and copy the installed extension path; then enable Developer mode, '
            'click **Load unpacked**, and select that folder.')


def readme_step(url: str) -> str:
    if not url:
        return f"3. **Load the bundled extension.** {SIDELOAD}"
    return (f"3. **[Add to Chrome]({url}).** Open the store page and click **Add to Chrome**, then pin **Uoink** "
            "from Chrome's Extensions menu. Keep the Uoink helper app running.\n\n"
            f"<details>\n<summary>Advanced: load the bundled extension</summary>\n\n{SIDELOAD} "
            "Use one copy of Uoink at a time.\n\n</details>")


def website_copy(url: str) -> str:
    if url:
        return (f"Primary extension button: [Add to Chrome]({url}).\n\n"
                "Install the Uoink helper app, add Uoink to Chrome, then pin Uoink from the Extensions menu. "
                "Keep the helper running to save sources.\n\n"
                f"Advanced fallback: {SIDELOAD}")
    return ("Keep the current download and sideload instructions until the store link is live.\n\n"
            f"Install the Uoink helper app, then load its bundled extension. {SIDELOAD}")


def sync(root: Path = ROOT, *, check: bool = False) -> None:
    url = load_store_config(root / "extension/store-config.json", strict=True)["chrome_web_store_url"]
    for relative, content in (("README.md", readme_step(url)), ("docs/store/website-copy-notes.md", website_copy(url))):
        path = root / relative
        old = path.read_text(encoding="utf-8")
        pattern = re.escape(START) + r"[\s\S]*?" + re.escape(END)
        new, count = re.subn(pattern, lambda _: START + "\n" + content + "\n" + END, old)
        if count != 1:
            raise ValueError(f"Expected one store install block in {relative}")
        if check and old != new:
            raise ValueError(f"Stale store links in {relative}; run python scripts/sync_store_links.py")
        if not check and old != new:
            path.write_text(new, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    sync(check=parser.parse_args().check)
