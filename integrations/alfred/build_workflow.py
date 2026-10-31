"""Generate src/info.plist and package dist/Uoink.alfredworkflow.

    python build_workflow.py           write info.plist and the package
    python build_workflow.py --check   fail if src/info.plist is stale

The object layout follows Alfred's own Shortcuts and OpenAI workflows:
script type 11 is /bin/zsh --no-rcs, scriptargtype 1 passes the query as $1.
"""
from __future__ import annotations

import argparse
import plistlib
import sys
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
DIST = HERE / "dist"
VERSION = "1.0.0"

SCRIPT_FILTER = "8E2D7B0C-5B1E-4F43-9C3A-0D6A1F2B7C01"
RUN_ACTION = "8E2D7B0C-5B1E-4F43-9C3A-0D6A1F2B7C02"
UNIVERSAL = "8E2D7B0C-5B1E-4F43-9C3A-0D6A1F2B7C03"
RUN_CAPTURE = "8E2D7B0C-5B1E-4F43-9C3A-0D6A1F2B7C04"

PYTHON = (
    'app="${uoink_app:-/Applications/Uoink.app}"\n'
    'py="$app/Contents/Resources/Python/bin/python3"\n'
)

FILTER_SCRIPT = PYTHON + (
    'if [[ ! -x "$py" ]]; then\n'
    "  printf '%s' '{\"items\":[{\"title\":\"Uoink isn’t installed here\","
    "\"subtitle\":\"↩ opens the install page. Installed elsewhere? Set the Uoink app path in the workflow configuration.\","
    "\"arg\":\"https://uoink.app/install\",\"variables\":{\"action\":\"open\"}}]}'\n"
    "  exit 0\n"
    "fi\n"
    'exec "$py" -I -B ./uoink_alfred.py filter "$1"'
)

ACT_SCRIPT = PYTHON + (
    'if [[ ! -x "$py" ]]; then\n'
    '  [[ "$action" == open && "$1" == https://* ]] && /usr/bin/open "$1"\n'
    "  exit 0\n"
    "fi\n"
    'exec "$py" -I -B ./uoink_alfred.py act "${action:-open}" "$1"'
)

CAPTURE_SCRIPT = PYTHON + (
    '[[ -x "$py" ]] || { /usr/bin/open "https://uoink.app/install"; exit 0; }\n'
    'exec "$py" -I -B ./uoink_alfred.py act capture "$1"'
)

README = """## Usage

Search the videos, podcasts, articles and notes you saved with [Uoink](https://uoink.app) via the `uk` keyword.

* <kbd>↩</kbd> Open the source at the matched timestamp.
* <kbd>⌘</kbd><kbd>↩</kbd> Copy a Markdown citation with a timestamped link (<kbd>⌘</kbd><kbd>C</kbd> also copies it).
* <kbd>⌥</kbd><kbd>↩</kbd> Copy the item ID.
* <kbd>⌃</kbd><kbd>↩</kbd> Open the source page.
* <kbd>⌘</kbd><kbd>Y</kbd> Quick Look the source.

With no query, `uk` lists recent captures; <kbd>↩</kbd> reveals one in Finder. Paste a link after `uk` to uoink it, or use the **Uoink** Universal Action on a URL. A notification reports when the capture is saved, and a video's Markdown is copied to the clipboard.

## Setup

Install [Uoink](https://uoink.app/install) for Mac. If Uoink.app isn't in /Applications, set its path in the workflow configuration.

Everything stays on your Mac: the workflow runs the uoink command inside Uoink.app. Searching makes no network calls; a capture fetches only the link you give it.
"""


def script(config_type: int, body: str, **extra) -> dict:
    return {"concurrently": True, "escaping": 0, "script": body, "scriptargtype": 1,
            "scriptfile": "", "type": config_type, **extra}


def info() -> dict:
    link = lambda uid: [{"destinationuid": uid, "modifiers": 0, "modifiersubtext": "", "vitoclose": False}]  # noqa: E731
    return {
        "bundleid": "app.uoink.alfred",
        "category": "Productivity",
        "connections": {SCRIPT_FILTER: link(RUN_ACTION), UNIVERSAL: link(RUN_CAPTURE)},
        "createdby": "Ryan Biddy",
        "description": "Search your Uoink library and cite the exact moment",
        "disabled": False,
        "name": "Uoink",
        "objects": [
            {"type": "alfred.workflow.input.scriptfilter", "uid": SCRIPT_FILTER, "version": 3, "config": {
                "alfredfiltersresults": False, "alfredfiltersresultsmatchmode": 0,
                "argumenttreatemptyqueryasnil": False, "argumenttrimmode": 0, "argumenttype": 1,
                "escaping": 0, "keyword": "{var:keyword}", "queuedelaycustom": 3,
                "queuedelayimmediatelyinitially": True, "queuedelaymode": 0, "queuemode": 1,
                "runningsubtext": "Searching your library…", "script": FILTER_SCRIPT,
                "scriptargtype": 1, "scriptfile": "", "skipuniversalaction": True,
                "subtext": "Search your library, or paste a link to uoink it", "title": "Uoink",
                "type": 11, "withspace": True}},
            {"type": "alfred.workflow.action.script", "uid": RUN_ACTION, "version": 2,
             "config": script(11, ACT_SCRIPT)},
            {"type": "alfred.workflow.trigger.universalaction", "uid": UNIVERSAL, "version": 1, "config": {
                "acceptsfiles": False, "acceptsmulti": 0, "acceptstext": False, "acceptsurls": True,
                "name": "Uoink"}},
            {"type": "alfred.workflow.action.script", "uid": RUN_CAPTURE, "version": 2,
             "config": script(11, CAPTURE_SCRIPT)},
        ],
        "readme": README,
        "uidata": {
            SCRIPT_FILTER: {"note": "Search the library, or offer a pasted link for capture", "xpos": 40.0, "ypos": 40.0},
            RUN_ACTION: {"note": "Open, reveal, copy or capture, per the action variable", "xpos": 260.0, "ypos": 40.0},
            UNIVERSAL: {"note": "Uoink a URL from anywhere", "xpos": 40.0, "ypos": 200.0},
            RUN_CAPTURE: {"note": "Capture the URL", "xpos": 260.0, "ypos": 200.0},
        },
        "userconfigurationconfig": [
            {"config": {"default": "uk", "placeholder": "uk", "required": True, "trim": True},
             "description": "Keyword for searching and uoinking.", "label": "Keyword",
             "type": "textfield", "variable": "keyword"},
            {"config": {"default": "/Applications/Uoink.app", "placeholder": "/Applications/Uoink.app",
                        "required": False, "trim": True},
             "description": "Where Uoink.app is installed.", "label": "Uoink app",
             "type": "textfield", "variable": "uoink_app"},
            {"config": {"default": True, "required": False, "text": "Copy a video's Markdown after a capture"},
             "description": "Like the Uoink browser button: the transcript lands on your clipboard.",
             "label": "After a capture", "type": "checkbox", "variable": "copy_after_capture"},
        ],
        "variablesdontexport": [],
        "version": VERSION,
        "webaddress": "https://uoink.app",
    }


def rendered() -> bytes:
    return plistlib.dumps(info(), fmt=plistlib.FMT_XML, sort_keys=True)


def build(check: bool = False) -> int:
    target = SRC / "info.plist"
    expected = rendered()
    if check:
        if not target.is_file() or target.read_bytes() != expected:
            print(f"{target} is stale; run build_workflow.py", file=sys.stderr)
            return 1
        return 0
    target.write_bytes(expected)
    DIST.mkdir(exist_ok=True)
    package = DIST / "Uoink.alfredworkflow"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("info.plist", "uoink_alfred.py", "icon.png"):
            archive.write(SRC / name, name)
    print(package)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    raise SystemExit(build(parser.parse_args().check))
